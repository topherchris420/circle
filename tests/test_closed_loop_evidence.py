"""Closed-loop evidence: temporal lawfulness, replay status, execution chains, and hidden-truth isolation.

These tests try to break CIRCLE's evidence chain. Each forgery below is
*consistent*: CRCs are resealed, the ledger is rebuilt, and manifest hashes are
updated, so only the auditor's semantic checks can catch it.
"""

from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from models.physiology.audit import audit_run, temporal_violations
from models.physiology.controller import ClosedLoopController, replay
from models.physiology.evidence import dumps
from models.physiology.experiment import SessionConfig, run_session
from models.physiology.ledger import build_ledger
from models.physiology.sensors import RigConfig
from models.physiology.streams import DeviceEvent, RawSession, Stream
from models.session_records import SessionRecordError, seal_record, validate_record
from tools.run_physiology_twin import export_run

ROOT = Path(__file__).resolve().parents[1]


def forge(run_dir: Path, edit) -> None:
    """Apply edit(records) and rewrite every derived binding so the forgery is self-consistent."""
    path = run_dir / "session.ndjson"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records = edit(records)
    records = [seal_record({k: v for k, v in r.items() if k != "crc32c"}) for r in records]
    path.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records))
    (run_dir / "closed_loop_ledger.json").write_bytes(dumps(build_ledger(records)))
    manifest = json.loads((run_dir / "manifest.json").read_text())
    for name in ("session.ndjson", "closed_loop_ledger.json"):
        manifest["artifacts"][name]["sha256"] = hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
    (run_dir / "manifest.json").write_bytes(dumps(manifest))


class ClosedLoopEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sr = run_session(SessionConfig())
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "run"
        export_run(cls.sr, cls.out, counterfactual=None, with_report=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy(self, name: str) -> Path:
        target = self.tmp / name
        shutil.copytree(self.out, target)
        return target

    # ------------------------------------------------------------ causality
    def test_controller_handed_the_future_decides_exactly_as_replay(self):
        """No time machine: even given every future sample, decisions equal the lawful ones."""
        controller = ClosedLoopController(self.sr.config.controller)
        full = self.sr.raw
        seen = [controller.evaluate(full, ev.device_time_us) for ev in self.sr.evaluations]
        self.assertEqual([e.comparable() for e in seen], [e.comparable() for e in self.sr.evaluations])

    def test_fifo_samples_are_invisible_until_read(self):
        ppg = self.sr.raw.streams["ppg"]
        late = np.flatnonzero(ppg.available_us - ppg.device_time_us > 100_000)
        self.assertGreater(len(late), 0, "the FIFO stall should delay some samples by > 100 ms")
        i = int(late[0])
        between = int(ppg.device_time_us[i]) + 1
        self.assertNotIn(int(ppg.sequence[i]), set(ppg.until(between).sequence.tolist()))
        self.assertIn(int(ppg.sequence[i]), set(ppg.until(int(ppg.available_us[i])).sequence.tolist()))

    def test_decisions_carry_decision_time_and_input_cutoff(self):
        margin = int(self.sr.config.controller.decision_margin_s * 1e6)
        for ev in self.sr.evaluations:
            self.assertEqual(ev.decision_time_us - ev.input_cutoff_us, margin)

    def test_marker_logged_after_a_decision_is_invisible_to_it(self):
        decision = next(e for e in self.sr.evaluations if e.decision_id == "PBR-1")
        warm = ClosedLoopController(self.sr.config.controller)
        for ev in self.sr.evaluations:
            if ev.device_time_us >= decision.device_time_us:
                break
            warm.evaluate(self.sr.raw, ev.device_time_us)
        bogus = DeviceEvent("protocol_events", 999, "PHASE_START:STRESSOR", decision.device_time_us + 1)
        with_future_marker = replace(self.sr.raw, events=self.sr.raw.events + [bogus])
        self.assertEqual(warm.evaluate(with_future_marker, decision.device_time_us).comparable(), decision.comparable())

    def test_clock_correction_does_not_change_decisions(self):
        sync = self.sr.raw.streams["sync"]
        shifted = Stream("sync", sync.sequence, sync.device_time_us + 40, sync.columns, sync.available_us + 40)
        raw = replace(self.sr.raw, streams={**self.sr.raw.streams, "sync": shifted})
        again = replay(raw, self.sr.config.controller, self.sr.evaluation_end_us)
        self.assertEqual([e.comparable() for e in again], [e.comparable() for e in self.sr.evaluations])

    def test_restart_with_restored_state_resumes_identically(self):
        config = self.sr.config.controller
        start = next(i for i, e in enumerate(self.sr.evaluations) if e.decision_id == "PBR-1")
        first = ClosedLoopController(config)
        for ev in self.sr.evaluations[:start + 2]:
            first.evaluate(self.sr.raw.until(ev.device_time_us), ev.device_time_us)
        resumed = ClosedLoopController.restore(config, first.snapshot())
        cold = ClosedLoopController(config)
        rest = self.sr.evaluations[start + 2:]
        warm_out = [resumed.evaluate(self.sr.raw.until(e.device_time_us), e.device_time_us) for e in rest]
        cold_out = [cold.evaluate(self.sr.raw.until(e.device_time_us), e.device_time_us) for e in rest]
        self.assertEqual([e.comparable() for e in warm_out], [e.comparable() for e in rest])
        self.assertNotEqual([e.comparable() for e in cold_out], [e.comparable() for e in rest],
                            "a restart that loses state must be detectable as a divergence")
        with self.assertRaises(ValueError):
            ClosedLoopController.restore(config, {"state": "PROGRAM"})

    def test_temporal_validator_flags_evidence_from_the_future(self):
        record = next(r for r in (json.loads(x) for x in (self.out / "session.ndjson").read_text().splitlines())
                      if r.get("decision_id") == "PBR-1")
        forged = dict(record, input_cutoff_us=record["input_cutoff_us"] - 5_000_000)
        problems = temporal_violations([forged], self.sr.raw)
        self.assertTrue(any("after cutoff" in p for p in problems), problems)
        unavailable = dict(record, decision_time_us=record["input_cutoff_us"])
        self.assertTrue(any("available at" in p for p in temporal_violations([unavailable], self.sr.raw)))

    def test_contract_rejects_a_cutoff_after_the_decision(self):
        record = next(json.loads(x) for x in (self.out / "session.ndjson").read_text().splitlines()
                      if '"decision_id":"PBR-1"' in x and "CONTROLLER_EVALUATION" in x)
        with self.assertRaises(SessionRecordError):
            seal_record(dict(record, input_cutoff_us=record["decision_time_us"] + 1))

    # ----------------------------------------------------- replay statuses
    def test_clean_run_is_replay_match(self):
        result = audit_run(self.out)
        self.assertEqual(result["replay_status"], "REPLAY_MATCH", json.dumps(result["checks"], indent=1))
        self.assertTrue(result["valid"])

    def test_consistent_forgery_of_a_cutoff_is_a_timing_violation(self):
        run_dir = self.copy("forged-cutoff")

        def edit(records):
            for r in records:
                if r.get("decision_id") == "PBR-1" and r["record_type"] == "MODEL_RESULT":
                    r["input_cutoff_us"] -= 3_000_000
            return records
        forge(run_dir, edit)
        result = audit_run(run_dir)
        self.assertEqual(result["replay_status"], "TIMING_VIOLATION")
        self.assertFalse(result["valid"])

    def test_consistent_forgery_of_a_decision_is_a_divergence(self):
        run_dir = self.copy("forged-decision")

        def edit(records):
            for r in records:
                if r.get("decision_id") == "PBR-1" and r["record_type"] == "MODEL_RESULT":
                    r["payload"]["arousal_index"] = 1.5
            return records
        forge(run_dir, edit)
        result = audit_run(run_dir)
        self.assertEqual(result["replay_status"], "REPLAY_DIVERGENCE")
        divergence = result["checks"]["decisions_replayed"]["detail"]["first_divergence"]
        self.assertIn("payload", divergence["fields"])

    def test_recorded_code_identity_mismatch_is_a_version_mismatch(self):
        run_dir = self.copy("forged-version")

        def edit(records):
            for r in records:
                if "model" in r:
                    r["model"]["artifact_id"] = "sha256:" + "0" * 64
            return records
        forge(run_dir, edit)
        self.assertEqual(audit_run(run_dir)["replay_status"], "VERSION_MISMATCH")

    def test_missing_raw_stream_is_missing_source(self):
        run_dir = self.copy("missing-raw")
        (run_dir / "raw" / "ppg.csv.gz").unlink()
        result = audit_run(run_dir)
        self.assertEqual(result["replay_status"], "MISSING_SOURCE")
        self.assertFalse(result["valid"])

    def test_missing_session_is_missing_source(self):
        run_dir = self.copy("missing-session")
        (run_dir / "session.ndjson").unlink()
        self.assertEqual(audit_run(run_dir)["replay_status"], "MISSING_SOURCE")

    def test_source_range_spanning_a_gap_fails_lineage(self):
        run_dir = self.copy("gap-span")
        gap = next(g for g in self.sr.raw.gaps)

        def edit(records):
            for r in records:
                if "PHYSIOLOGY_WINDOW" not in r["status_flags"]:
                    continue
                ppg = [x for x in r["source_sequence_ranges"] if x["stream_id"] == "ppg"]
                if len(ppg) == 2 and ppg[0]["last_sequence"] == gap.first_sequence - 1:
                    # Claim one contiguous range across the loss, as if it were interpolated.
                    ppg[0]["last_sequence"] = ppg[1]["last_sequence"]
                    r["source_sequence_ranges"].remove(ppg[1])
                    return records
            raise AssertionError("no window is split by the gap")
        forge(run_dir, edit)
        result = audit_run(run_dir)
        self.assertFalse(result["checks"]["lineage_on_recorded_samples"]["passed"])
        self.assertEqual(result["replay_status"], "EVIDENCE_INTEGRITY_FAILURE")

    # ---------------------------------------------------- execution chains
    def test_every_cue_has_a_complete_independent_execution_chain(self):
        records = [json.loads(x) for x in (self.out / "session.ndjson").read_text().splitlines()]
        intervention = next(r for r in records if r["record_type"] == "INTERVENTION")
        commands = [r for r in records if "EVENT_KIND:HAPTIC_COMMAND" in r["status_flags"]]
        self.assertEqual(len(intervention["execution_chain"]), len(commands))
        self.assertTrue(all(link["stage"] == "PHYSICALLY_OBSERVED" for link in intervention["execution_chain"]))
        self.assertIn("EFFECT:NOT_ASSERTED_WITHOUT_MATCHED_CONTROL", intervention["status_flags"])
        observation_ids = {link["physical_observation_id"] for link in intervention["execution_chain"]}
        observations = [r for r in records if f"{r.get('stream_id')}#{r.get('sequence')}" in observation_ids]
        self.assertTrue(all(r["provenance"] == "DERIVED" for r in observations))

    def test_contract_rejects_a_stage_the_evidence_does_not_earn(self):
        record = next(json.loads(x) for x in (self.out / "session.ndjson").read_text().splitlines() if '"INTERVENTION"' in x)
        link = dict(record["execution_chain"][0])
        link.pop("physical_observation_id")
        forged = dict(record, execution_chain=[link] + record["execution_chain"][1:])
        with self.assertRaisesRegex(SessionRecordError, "not what its evidence shows"):
            seal_record({k: v for k, v in forged.items() if k != "crc32c"})

    def test_dropped_execution_link_is_caught(self):
        run_dir = self.copy("dropped-link")

        def edit(records):
            for r in records:
                if r["record_type"] == "INTERVENTION":
                    r["execution_chain"] = r["execution_chain"][1:]
            return records
        forge(run_dir, edit)
        result = audit_run(run_dir)
        self.assertFalse(result["checks"]["execution_chains"]["passed"])
        self.assertFalse(result["valid"])

    def test_ledger_explains_why_and_keeps_effect_unasserted(self):
        ledger = json.loads((self.out / "closed_loop_ledger.json").read_text())
        start = next(d for d in ledger["decisions"] if d["action"] == "START_PACED_BREATHING")
        self.assertIn("consecutive evaluations", start["why"])
        self.assertIn("quality gates passed", start["why"])
        self.assertEqual(start["execution"], "ALL_CUES_PHYSICALLY_OBSERVED")
        self.assertTrue(all(link["physical_observation"]["latency_from_command_us"] > 0 for link in start["execution_chain"]))
        self.assertIn("matched control", ledger["interpretation"])
        evaluation = next(e for e in ledger["evaluations"] if e["id"] == start["evaluation"])
        total = sum(c["contribution"] for c in evaluation["formula"].values())
        self.assertAlmostEqual(total, evaluation["arousal_index"], places=4)


class ShamArmTest(unittest.TestCase):
    """The sham arm is a negative control for the physical-observation detector."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "sham"
        cls.sr = run_session(SessionConfig(actuate=False))
        export_run(cls.sr, cls.out, counterfactual=None, with_report=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_sham_export_audits_and_observes_nothing(self):
        result = audit_run(self.out)
        self.assertEqual(result["replay_status"], "REPLAY_MATCH")
        card = json.loads((self.out / "scorecard.json").read_text())
        negative = next(c for c in card["checks"] if c["id"] == "haptic_sham_negative")
        self.assertTrue(negative["passed"])
        records = [json.loads(x) for x in (self.out / "session.ndjson").read_text().splitlines()]
        self.assertFalse([r for r in records if r["record_type"] == "INTERVENTION"])
        ledger = json.loads((self.out / "closed_loop_ledger.json").read_text())
        start = next(d for d in ledger["decisions"] if d["action"] == "START_PACED_BREATHING")
        self.assertEqual(start["execution"], "NOT_ACTUATED_SHAM_ARM")


class LateDataTest(unittest.TestCase):
    def test_longest_observable_fifo_stall_keeps_decisions_lawful(self):
        run = run_session(SessionConfig(rig=RigConfig(ppg_fifo_stall_s=0.44)))
        margin = int(run.config.controller.decision_margin_s * 1e6)
        ppg = run.raw.streams["ppg"]
        self.assertGreater(int(np.max(ppg.available_us - ppg.device_time_us)), 400_000)
        for ev in run.evaluations:
            visible = run.raw.until(ev.device_time_us).streams["ppg"]
            window = visible.window(ev.window_start_us, ev.input_cutoff_us)
            self.assertTrue(np.all(window.available_us <= ev.device_time_us))
            self.assertEqual(ev.device_time_us - ev.input_cutoff_us, margin)
        again = replay(run.raw, run.config.controller, run.evaluation_end_us)
        self.assertEqual([e.comparable() for e in again], [e.comparable() for e in run.evaluations])


class HiddenTruthIsolationTest(unittest.TestCase):
    """The production-like path must never see twin ground truth."""

    PRODUCTION = ("dsp.py", "pipeline.py", "controller.py", "streams.py", "evidence.py", "audit.py", "ledger.py")
    FORBIDDEN = {"twin", "sensors", "validation", "experiment", "report"}

    def test_production_modules_never_import_the_twin_or_scoring(self):
        for name in self.PRODUCTION:
            tree = ast.parse((ROOT / "models/physiology" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = (node.module or "").split(".")[-1]
                    self.assertNotIn(module, self.FORBIDDEN, f"{name} imports {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[-1], self.FORBIDDEN, f"{name} imports {alias.name}")

    def test_raw_session_carries_only_device_data(self):
        self.assertEqual(set(RawSession.__dataclass_fields__), {"streams", "descriptors", "gaps", "events"})
        self.assertEqual(set(Stream.__dataclass_fields__), {"name", "sequence", "device_time_us", "columns", "available_us"})

    def test_exported_evidence_contains_no_truth_fields(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            export_run(run_session(SessionConfig(twin=replace(SessionConfig().twin, seed=3))), tmp,
                       counterfactual=None, with_report=False)
            evidence = (tmp / "session.ndjson").read_text() + (tmp / "analysis.json").read_text()
            for leaked in ("_true_s", "exact_device_us", "latent", "truth", "entrainment", "spo2_true"):
                self.assertNotIn(leaked, evidence)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
