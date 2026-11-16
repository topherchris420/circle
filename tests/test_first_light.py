"""First Light: two implementations, named verdicts, and evidence that matches what is published."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from tools import verify_first_light as v

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "evidence" / "first-light" / "sessions"
ILLUSTRATION = SESSIONS / "149055-072.zip"
PREREGISTERED = SESSIONS / "137025-054.zip"
CORE = ROOT / "site" / "first-light-core.js"
NODE = shutil.which("node")

# A synthetic fingertip: bright, red-dominant, green dipping once per beat. Used only to exercise
# the live criteria in software; it is not a measurement and is never written to evidence/.
SYNTHETIC_JS = """
const FL = require(process.argv[1]);
const frames = [];
function green(t) { const p = ((t / 1e6) * 72 / 60) % 1; const dip = p < 0.18 ? p / 0.18 : Math.exp(-4.5 * (p - 0.18) / 0.82);
  return Math.round(70000 * (1 - 0.12 * dip)); }
for (let i = 0; i < 30 * 50; i++) {
  const t = Math.floor(i * 1e6 / 30);
  const lifted = t >= 20e6 && t < 23e6;
  frames.push(lifted ? [t, 8000, 8000, 10000] : [t, 235000, green(t), 30000]);
}
const session = FL.runFrames(frames);
const options = JSON.parse(process.argv[3]);
require("fs").writeFileSync(process.argv[2], FL.bundle(session, options).zip);
"""


def synthetic_frames(lift=(20_000_000, 23_000_000), seconds=50):
    frames = []
    for i in range(30 * seconds):
        t = i * 1_000_000 // 30
        if lift and lift[0] <= t < lift[1]:
            frames.append((t, 8000, 8000, 10000))
            continue
        phase = ((t / 1e6) * 72 / 60) % 1
        dip = phase / 0.18 if phase < 0.18 else math.exp(-4.5 * (phase - 0.18) / 0.82)
        frames.append((t, 235000, math.floor(70000 * (1 - 0.12 * dip) + 0.5), 30000))
    return frames


def extract(bundle: Path, directory: Path) -> Path:
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(directory)
    return directory


def reseal(directory: Path) -> None:
    """Rewrite the manifest's hashes after tampering, as a careful forger would."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name in manifest["files"]:
        data = (directory / name).read_bytes()
        manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")


class CommittedEvidenceTest(unittest.TestCase):
    def test_the_illustration_session_verifies(self):
        result = v.verify(ILLUSTRATION)
        self.assertEqual(result["integrity"], "INTEGRITY_OK")
        self.assertEqual(result["replay"], "REPLAY_MATCH", result["problems"])
        self.assertEqual(result["verdict"], "VERIFIED")
        self.assertEqual((result["acts"], result["refusals"]), (32, 139))

    def test_the_preregistered_session_fails_and_says_so(self):
        result = v.verify(PREREGISTERED)
        self.assertEqual(result["replay"], "REPLAY_MATCH", result["problems"])
        self.assertEqual(result["verdict"], "PROTOCOL_FAIL")
        self.assertEqual(result["acts"], 0)
        verdicts = {c["id"]: c["result"] for c in result["criteria"]}
        self.assertEqual(verdicts["R2_REFUSED_WHAT_EXPERTS_REJECTED"], "PASS")
        self.assertEqual(verdicts["R3_ACTED_WHEN_EVIDENCE_WAS_GOOD"], "FAIL")
        self.assertEqual(verdicts["R4_SILENT_WHILE_REFUSED"], "PASS")

    def test_pooling_judges_all_windows_together(self):
        results = [v.verify(ILLUSTRATION), v.verify(PREREGISTERED)]
        pooled = v.pool(results)
        self.assertEqual(pooled["windows"], sum(len(r["windows"]) for r in results))
        self.assertEqual(pooled["acts"], 32)
        self.assertEqual(len(pooled["criteria"]), 4)

    def test_published_numbers_are_the_recorded_result(self):
        result = json.loads((ROOT / "evidence/first-light/round-2/result.json").read_text(encoding="utf-8"))
        pooled = result["pooled"]
        self.assertEqual(pooled["verdict"], "VERIFIED")
        self.assertEqual(result["criteria"], v.CRITERIA["id"])
        self.assertEqual(result["algorithm"], v.ALGORITHM["id"])
        self.assertTrue(all(s["replay"] == "REPLAY_MATCH" and s["source"] == "SOURCE_MATCH" for s in result["sessions"]))
        details = " ".join(c["detail"] for c in pooled["criteria"])
        page = (ROOT / "site" / "first-light.html").read_text(encoding="utf-8")
        report = (ROOT / "evidence/first-light/round-2/RESULT.md").read_text(encoding="utf-8")
        for figure in ("575 of 581", "4106 of 4132", "490 of 1440"):
            self.assertIn(figure, details)
            pretty = re.sub(r"(\d)(\d{3})\b", r"\1,\2", figure)
            self.assertIn(pretty, page)
            self.assertIn(pretty, report)
        self.assertEqual(pooled["windows"], 7196)
        self.assertIn("7,196", page)

    def test_round_one_failure_is_kept(self):
        verdict = json.loads((ROOT / "evidence/first-light/round-1/verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(verdict["verdict"], "PROTOCOL_FAIL")
        self.assertEqual(verdict["replay"], "REPLAY_MATCH")


class TamperTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = extract(ILLUSTRATION, Path(self.temporary.name) / "bundle")

    def tearDown(self):
        self.temporary.cleanup()

    def test_an_extracted_bundle_verifies_like_the_zip(self):
        self.assertEqual(v.verify(self.directory)["verdict"], "VERIFIED")

    def test_a_changed_frame_is_an_integrity_failure(self):
        raw = self.directory / "raw" / "frames.csv"
        raw.write_bytes(raw.read_bytes().replace(b"\n", b"\n ", 1))
        result = v.verify(self.directory)
        self.assertEqual(result["verdict"], "INTEGRITY_FAILURE")
        self.assertTrue(any("frames.csv" in p for p in result["problems"]))

    def test_changed_frames_with_rewritten_hashes_diverge_on_replay(self):
        raw = self.directory / "raw" / "frames.csv"
        lines = raw.read_text(encoding="utf-8").splitlines()
        for i in range(2000, 2300):                     # ten seconds of green pushed out of range
            t, r, g, b = lines[i].split(",")
            lines[i] = f"{t},{r},{int(g) + 40000},{b}"
        raw.write_text("\n".join(lines) + "\n", encoding="utf-8")
        reseal(self.directory)
        result = v.verify(self.directory)
        self.assertEqual(result["integrity"], "INTEGRITY_OK")
        self.assertEqual(result["replay"], "REPLAY_DIVERGENCE")

    def test_a_forged_decision_diverges_on_replay(self):
        path = self.directory / "decisions.json"
        decisions = json.loads(path.read_text(encoding="utf-8"))
        forged = next(d for d in decisions if d["decision"] == "REFUSE")
        forged.update(decision="ACT", rate_bpm=72.0, reasons=[])
        path.write_text(json.dumps(decisions) + "\n", encoding="utf-8")
        reseal(self.directory)
        result = v.verify(self.directory)
        self.assertEqual(result["replay"], "REPLAY_DIVERGENCE")
        self.assertNotEqual(result["verdict"], "VERIFIED")

    def test_a_bundle_cannot_loosen_its_own_gates(self):
        path = self.directory / "protocol.json"
        protocol = json.loads(path.read_text(encoding="utf-8"))
        protocol["algorithm"]["periodicity_min"] = 0.1
        path.write_text(json.dumps(protocol, indent=1) + "\n", encoding="utf-8")
        reseal(self.directory)
        self.assertEqual(v.verify(self.directory)["verdict"], "VERSION_MISMATCH")

    def test_missing_and_extra_files_are_named(self):
        (self.directory / "feedback.json").unlink()
        self.assertEqual(v.verify(self.directory)["verdict"], "INSUFFICIENT_EVIDENCE")
        extract(ILLUSTRATION, self.directory)
        (self.directory / "notes.txt").write_text("unlisted", encoding="utf-8")
        result = v.verify(self.directory)
        self.assertEqual(result["verdict"], "INTEGRITY_FAILURE")
        self.assertTrue(any("notes.txt" in p for p in result["problems"]))


class LiveCriteriaTest(unittest.TestCase):
    """The live criteria, exercised in software on a synthetic fingertip (not a measurement)."""

    def judge(self, frames, mode="live-finger", reference=None):
        decisions, feedback = v.run_controller(frames)
        return decisions, feedback, {c["id"]: c for c in v.live_criteria(frames, decisions, feedback, mode, reference)}

    def test_act_fault_refuse_recover_passes(self):
        decisions, _, criteria = self.judge(synthetic_frames())
        self.assertTrue(all(c["result"] == "PASS" for c in criteria.values()), criteria)
        self.assertLessEqual(criteria["L3_REFUSED_IN_TIME"]["measured"], 1.5)
        rates = [d["rate_bpm"] for d in decisions if d["decision"] == "ACT"]
        self.assertTrue(all(abs(rate - 72) < 1.5 for rate in rates), rates)

    def test_a_session_without_a_fault_cannot_pass(self):
        _, _, criteria = self.judge(synthetic_frames(lift=None))
        self.assertEqual(criteria["L1_ACTED_ON_GOOD_EVIDENCE"]["result"], "PASS")
        self.assertEqual(criteria["L2_FAULT_PRESENT"]["result"], "FAIL")

    def test_acting_through_the_fault_is_caught(self):
        frames = synthetic_frames()
        decisions, feedback = v.run_controller(frames)
        for d, f in zip(decisions, feedback):               # a controller that never refuses
            d.update(decision="ACT", rate_bpm=72.0)
            f.update(audible=True, level=0.3, tempo_bpm=72.0, brightness=0.3)
        criteria = {c["id"]: c["result"] for c in v.live_criteria(frames, decisions, feedback, "live-finger", None)}
        self.assertEqual(criteria["L3_REFUSED_IN_TIME"], "FAIL")
        self.assertEqual(criteria["L4_NO_ACT_ON_BAD_FRAMES"], "FAIL")
        self.assertEqual(criteria["L5_SILENT_WHILE_REFUSED"], "FAIL")

    def test_always_refusing_cannot_pass(self):
        frames = [(t, 8000, 8000, 10000) for t, *_ in synthetic_frames()]
        _, _, criteria = self.judge(frames)
        self.assertEqual(criteria["L1_ACTED_ON_GOOD_EVIDENCE"]["result"], "FAIL")

    def test_recovery_needs_a_window_that_starts_after_the_fault(self):
        decisions, _, _ = self.judge(synthetic_frames())
        after = [d for d in decisions if d["cutoff_us"] > 23_000_000 and d["decision"] == "ACT"]
        self.assertGreater(after[0]["cutoff_us"] - v.ALGORITHM["window_us"], 23_000_000 - 34_000)
        waiting = [d for d in decisions if "AWAITING_CLEAN_WINDOW" in d["reasons"]]
        self.assertTrue(waiting, "the controller should hold after the gates first pass again")

    def test_the_phantom_is_judged_against_its_programmed_rate(self):
        frames = synthetic_frames()
        _, _, right = self.judge(frames, "live-phantom", {"kind": "optical-phantom", "rate_bpm": 72})
        _, _, wrong = self.judge(frames, "live-phantom", {"kind": "optical-phantom", "rate_bpm": 90})
        self.assertEqual(right["P1_PHANTOM_ACCURACY"]["result"], "PASS")
        self.assertEqual(wrong["P1_PHANTOM_ACCURACY"]["result"], "FAIL")

    def test_feedback_is_bounded_and_silent_on_refusal(self):
        decisions, feedback = v.run_controller(synthetic_frames())
        tempos = [f["tempo_bpm"] for f in feedback if f["audible"]]
        for d, f in zip(decisions, feedback):
            self.assertEqual(f["audible"], d["decision"] == "ACT")
            self.assertLessEqual(f["level"], v.FEEDBACK["max_level"] + 1e-12)
            if d["decision"] == "REFUSE":
                self.assertEqual((f["level"], f["tempo_bpm"]), (0.0, None))
        self.assertTrue(tempos)


class ReferenceReadingTest(unittest.TestCase):
    def test_wfdb_annotations_decode_to_beat_samples(self):
        words = [(1 << 10) | 432, (1 << 10) | 661, (59 << 10), 0, 2000, (1 << 10) | 5, 0]
        data = b"".join(w.to_bytes(2, "little") for w in words)
        self.assertEqual(v.read_qrs(data), [432, 1093, 3098])

    def test_reference_rate_is_the_median_interval(self):
        beats = [0, 800_000, 1_600_000, 2_500_000, 3_300_000]
        rate, count = v.reference_rate(beats, 0, 4_000_000)
        self.assertEqual(count, 5)
        self.assertAlmostEqual(rate, 75.0)
        self.assertEqual(v.reference_rate(beats, 0, 100_000), (None, 1))


@unittest.skipIf(NODE is None, "node is not installed")
class TwoImplementationsTest(unittest.TestCase):
    """The browser implementation (under Node) and the Python verifier must agree."""

    def node(self, script: str, *args: str) -> str:
        done = subprocess.run([NODE, "-e", script, *args], capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_published_constants_are_identical(self):
        out = self.node("const FL = require(process.argv[1]); console.log(JSON.stringify("
                        "{a: FL.ALGORITHM, f: FL.FEEDBACK, c: FL.CRITERIA_ID, g: FL.GATES}))", str(CORE))
        doc = json.loads(out)
        self.assertEqual(doc["a"], v.ALGORITHM)
        self.assertEqual(doc["f"], v.FEEDBACK)
        self.assertEqual(doc["c"], v.CRITERIA["id"])
        self.assertEqual(tuple(doc["g"]), v.GATES)

    def test_committed_bundles_rebuild_byte_for_byte(self):
        done = subprocess.run([NODE, str(ROOT / "tools" / "build_first_light_bundle.js"), "--check"],
                              capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout.count("MATCH "), 2)

    def test_a_live_bundle_built_in_javascript_verifies_in_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode, reference, expected in (
                    ("live-finger", None, "VERIFIED"),
                    ("live-phantom", {"kind": "optical-phantom", "rate_bpm": 72}, "VERIFIED"),
                    ("live-phantom", {"kind": "optical-phantom", "rate_bpm": 95}, "PROTOCOL_FAIL")):
                path = Path(tmp) / "live.zip"
                options = {"mode": mode, "created": None, "device": {"source": "synthetic test input"}}
                if reference:
                    options["reference"] = reference
                self.node(SYNTHETIC_JS, str(CORE), str(path), json.dumps(options))
                result = v.verify(path)
                self.assertEqual(result["replay"], "REPLAY_MATCH", result["problems"])
                self.assertEqual(result["verdict"], expected, result.get("criteria"))

    def test_the_javascript_sha256_matches_hashlib(self):
        out = self.node("const FL = require(process.argv[1]); console.log(FL.sha256(FL.utf8('')) + ' ' + "
                        "FL.sha256(FL.utf8('circle'.repeat(40))))", str(CORE))
        self.assertEqual(out.split(), [hashlib.sha256(b"").hexdigest(), hashlib.sha256(b"circle" * 40).hexdigest()])


class PageContractTest(unittest.TestCase):
    def test_the_page_states_its_boundaries(self):
        page = (ROOT / "site" / "first-light.html").read_text(encoding="utf-8")
        for phrase in ("Not a medical device", "Camera frames never leave this page", "chosen after the test",
                       "not CIRCLE's own hardware", "No effect on any person"):
            self.assertIn(phrase, page)
        for asset in ("first-light.css", "first-light-core.js", "first-light.js", "first-light-phantom.html"):
            self.assertIn(asset, page)
        self.assertIsNone(re.search(r'(?:src|href)="/(?!/)', page), "a root-absolute path breaks /circle/")

    def test_the_page_scripts_call_no_other_host(self):
        for name in ("first-light.js", "first-light-core.js"):
            text = (ROOT / "site" / name).read_text(encoding="utf-8")
            self.assertEqual(re.findall(r"https?://[^\"'\s)<>]+", text.replace("http://www.w3.org/2000/svg", "")), [], name)
            self.assertNotIn("XMLHttpRequest", text)
            self.assertNotIn("sendBeacon", text)
        self.assertEqual(re.findall(r"fetch\(([^)]*)\)", (ROOT / "site" / "first-light.js").read_text(encoding="utf-8")),
                         ['"first-light-core.js"'])

    def test_recordings_carry_their_selection_and_licence(self):
        for name, role in (("149055-072", "illustration"), ("137025-054", "preregistered")):
            text = (ROOT / "site" / f"first-light-recording-{name}.js").read_text(encoding="utf-8")
            self.assertIn("CC BY 4.0", text)
            doc = json.loads(text.split(" = ", 2)[2].rstrip().rstrip(";"))
            self.assertEqual(doc["selection"]["role"], role)
            self.assertEqual(doc["reference"]["dataset"]["archive_sha256"], v.BUT_PPG_SHA256)


@unittest.skipUnless(os.environ.get("CIRCLE_E2E") == "1" and NODE, "set CIRCLE_E2E=1 to drive the page in Chromium")
class BrowserTest(unittest.TestCase):
    def test_the_page_runs_both_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([NODE, str(ROOT / "tests" / "js" / "first_light_e2e.js"), "--out", tmp],
                                  capture_output=True, text=True, cwd=ROOT, timeout=300)
            self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-3000:])
            live = json.loads(done.stdout)["live"]["bundle"]
            self.assertEqual(v.verify(Path(live))["verdict"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
