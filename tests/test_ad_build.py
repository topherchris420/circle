"""The film's evidence: what marketing/ad shows must be what the repository produced."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from tools.build_ad import AD_SCENARIO, AD_SEED, RAIN_RUN, build_ad

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "marketing" / "ad"


class AdBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name) / "ad"
        cls.summary = build_ad(cls.directory)
        text = (cls.directory / "ad-data.js").read_text(encoding="utf-8")
        cls.data = json.loads(text.split("= ", 1)[1].rstrip().rstrip(";"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_session_is_the_declared_simulation_and_verifies(self):
        self.assertEqual(self.data["session"], {"scenario": AD_SCENARIO, "title": "A missing channel",
                                                "seed": AD_SEED, "arm": "active"})
        run = self.data["workbench"]["runs"][0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["consent_record"]["state"], "EXECUTED")
        self.assertEqual(self.data["verdict"]["verdict"], "REPLAY_MATCH")
        self.assertTrue(all(check["passed"] for check in self.data["verdict"]["checks"].values()))
        self.assertNotIn("directory", self.data["verdict"], "no build-machine path belongs in the film data")

    def test_the_story_the_film_tells_is_in_the_evidence(self):
        timeline = self.data["workbench"]["timeline"]
        stale = [e for e in timeline["evaluations"] if "DATA_STALE" in e["gate"]]
        self.assertTrue(stale, "the film shows a DATA_STALE evaluation")
        self.assertGreater(stale[0]["features"]["ppg_age_s"], 0.5)
        actions = [d["action"] for d in timeline["decisions"]]
        self.assertEqual(actions, ["START_PACED_BREATHING", "STOP_QUALITY_LOST"])
        stop = timeline["decisions"][1]
        self.assertIn("a loop that cannot observe its effect was stopped", stop["why"])
        held = [f for f in timeline["feedback"]["events"] if f["time_us"] == stale[0]["decision_time_us"]]
        self.assertEqual(len(held), 1)
        self.assertFalse(held[0]["audible"])
        self.assertEqual(held[0]["parameters"]["level"], 0.0)
        self.assertIn("DATA_STALE", held[0]["gate_reasons"])

    def test_raw_excerpts_keep_the_declared_gap(self):
        gap = self.data["raw"]["ppg_gap_s"]
        self.assertAlmostEqual(gap["duration"], 14.0, delta=0.2)
        dropout = self.data["raw"]["dropout"]
        inside = [t for t in dropout["ppg_ir"]["t_s"] if gap["start"] < t < gap["end"]]
        self.assertEqual(inside, [], "the missing channel must stay missing: no interpolated samples")
        # The other channels kept answering through the gap.
        for name in ("eda", "imu_ax"):
            self.assertGreater(len([t for t in dropout[name]["t_s"] if gap["start"] < t < gap["end"]]), 500, name)

    def test_rain_record_is_carried_unchanged(self):
        self.assertEqual(self.data["rain"], json.loads(RAIN_RUN.read_text(encoding="utf-8")))
        self.assertEqual(self.data["rain"]["rain_live"]["result"]["conclusion"], "NOT_SUPPORTED")
        self.assertEqual(self.data["rain_analysis_plan"]["alpha"], 0.05)

    def test_workbench_shell_is_the_real_page(self):
        html = (self.directory / "workbench.html").read_text(encoding="utf-8")
        for name in ("resonance.css", "resonance.js", "audio-engine.js", "synth.js", "visual.js"):
            self.assertIn("../../models/workbench_assets/resonance/" + name, html)
        self.assertLess(html.index("workbench-shim.js"), html.index("resonance/resonance.js"))
        self.assertIn("SIMULATION ONLY", html)
        self.assertNotIn('src="/resonance', html)

    def test_committed_film_names_its_limits(self):
        page = (FILM / "index.html").read_text(encoding="utf-8")
        script = (FILM / "ad.js").read_text(encoding="utf-8")
        self.assertIn("SIMULATION ONLY", page)
        self.assertIn("Close the loop.", page)
        self.assertIn("Keep the evidence.", page)
        self.assertIn("Not a medical device", script)
        self.assertIn("no person was measured", script)
        for name in ("index.html", "ad.js", "ad.css", "workbench-shim.js"):
            text = (FILM / name).read_text(encoding="utf-8")
            for match in re.findall(r"https?://[^\"'\s)<>]+", text):
                self.assertTrue(re.match(r"https?://(www\.)?w3\.org/", match), f"{name}: {match}")


if __name__ == "__main__":
    unittest.main()
