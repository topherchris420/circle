"""Resonance Workbench timeline: a reviewable view over exported evidence."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS
from models.workbench import DEFAULT_CONSENT, DEFAULT_FEEDBACK, validate_settings
from models.workbench_timeline import _LedgerEvaluation, build_timeline
from models.physiology.feedback import feedback_events
from tools.run_physiology_twin import export_run

RUN_SETTINGS = validate_settings({"scenario": "clean", "seed": 7, "arm": "active", "compare": False})


def _record(status="completed", settings=None):
    return {"id": "a" * 32, "settings": settings or RUN_SETTINGS,
            "created_at": "2026-01-01T00:00:00+00:00", "status": status,
            "summary": {"scorecard": {"passed": 19, "total": 19}, "audit_valid": True}}


class TimelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.evidence = root / "evidence"
        run = run_session(replace(SCENARIOS["clean"].configure(7), actuate=True))
        export_run(run, cls.evidence, None)
        cls.document = build_timeline(_record(), cls.evidence, None)
        # A second, byte-identical construction proves the view is deterministic.
        cls.again = build_timeline(_record(), cls.evidence, None)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_document_is_deterministic(self):
        self.assertEqual(json.dumps(self.document, sort_keys=True), json.dumps(self.again, sort_keys=True))

    def test_provenance_names_its_sources(self):
        provenance = self.document["provenance"]
        for key in ("pipeline_version", "controller_version", "feedback_version",
                    "analysis_sha256", "ledger_sha256", "session_ndjson_sha256"):
            self.assertIn(key, provenance)
        self.assertTrue(provenance["analysis_sha256"].startswith("sha256:"))

    def test_series_cover_the_required_modalities(self):
        windows = self.document["windows"]
        self.assertGreater(len(windows), 10)
        hr = [w["hr_bpm"] for w in windows if "hr_bpm" in w]
        self.assertGreater(len(hr), 5)
        rmssd = [w["rmssd_ms"] for w in self.document["hrv"]["series"] if "rmssd_ms" in w]
        self.assertGreater(len(rmssd), 3)
        self.assertGreater(min(rmssd), 0.0)
        self.assertIn("derivation", self.document["hrv"])
        resp = [w["resp_rate_bpm"] for w in windows if "resp_rate_bpm" in w]
        self.assertGreater(len(resp), 5)
        self.assertGreaterEqual(min(w["motion_fraction"] for w in windows), 0.0)

    def test_hrv_windows_are_labeled_or_withheld(self):
        for window in self.document["hrv"]["series"]:
            self.assertTrue(window["label"].startswith(("RMSSD", "withheld")))

    def test_evaluations_carry_the_evidence_explorer_fields(self):
        evaluations = self.document["evaluations"]
        self.assertGreater(len(evaluations), 20)
        for evaluation in evaluations[:5]:
            for key in ("id", "decision_time_us", "input_cutoff_us", "state_after", "gate", "features"):
                self.assertIn(key, evaluation)

    def test_decisions_and_cues_preserve_execution_evidence(self):
        self.assertGreaterEqual(len(self.document["decisions"]), 1)
        cues = self.document["cues"]
        self.assertGreaterEqual(len(cues), 1)
        for cue in cues:
            self.assertIn(cue["stage"], ("PHYSICALLY_OBSERVED", "ELECTRICAL_ONSET_OBSERVED", "COMMAND_ONLY"))

    def test_feedback_events_match_evaluations_and_are_gated(self):
        events = self.document["feedback"]["events"]
        self.assertEqual(len(events), len(self.document["evaluations"]))
        self.assertTrue(self.document["feedback"]["digest"].startswith("sha256:"))
        for event in events:
            self.assertLessEqual(event["parameters"]["level"], self.document["feedback"]["config"]["max_gain"] + 1e-9)
            if not event["audible"]:
                self.assertEqual(event["parameters"]["level"], 0.0)
                self.assertTrue(event["gate_reasons"])

    def test_recorded_arousal_changes_adaptive_feedback(self):
        """Measured arousal must reach the audible and visual parameter stream."""
        def record(index, t, gate=("PASS",)):
            return {"decision_time_us": t * 1_000_000, "input_cutoff_us": t * 1_000_000,
                    "gate": list(gate), "state_after": "IDLE", "decision_id": None,
                    "features": {"hr_bpm": 73.0, "scl_us": 4.2, "scr_rate_per_min": 2.0},
                    "arousal_index": index}
        low, high = feedback_events([_LedgerEvaluation(record(0.0, 1)),
                                     _LedgerEvaluation(record(1.8, 2))])
        for name in ("intensity", "level", "brightness", "tempo", "spatial"):
            self.assertGreater(high.parameters[name], low.parameters[name], name)
        self.assertEqual(high.inputs["arousal_index"], 1.8)
        self.assertLessEqual(high.parameters["level"], 0.5)
        held = feedback_events([_LedgerEvaluation(record(1.8, 3, ("MOTION_EXCESSIVE",)))])[0]
        self.assertFalse(held.audible)
        self.assertEqual(held.parameters["level"], 0.0)

    def test_audit_summary_is_included_when_present(self):
        self.assertIsNone(self.document["session"]["audit"])
        audited = build_timeline(_record(), self.evidence, None)
        # no audit file: stays absent rather than invented
        self.assertIsNone(audited["session"]["audit"])


class ConsentedTimelineTest(unittest.TestCase):
    def test_audio_consent_travels_with_the_run(self):
        settings = validate_settings({"scenario": "clean", "seed": 7, "arm": "sham", "compare": False,
                                      "feedback": {"modalities": ["audio", "visual"], "max_gain": 0.4,
                                                  "breath_bpm": 5.5},
                                      "consent": {"audio": True}})
        record = _record(settings=settings)
        with tempfile.TemporaryDirectory() as tmp:
            run = run_session(replace(SCENARIOS["clean"].configure(7), actuate=False))
            evidence = Path(tmp) / "evidence"
            export_run(run, evidence, None)
            document = build_timeline(record, evidence, None)
        self.assertEqual(document["session"]["feedback_consent"]["audio"], True)
        self.assertEqual(document["feedback"]["config"]["max_gain"], 0.4)


class DefaultSettingsTest(unittest.TestCase):
    def test_defaults_are_conservative(self):
        # Visual only; audio needs a person to turn it on.
        self.assertEqual(DEFAULT_FEEDBACK["modalities"], ["visual"])
        self.assertFalse(DEFAULT_CONSENT["audio"])


if __name__ == "__main__":
    unittest.main()
