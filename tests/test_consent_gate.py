"""Cryptographic consent integration: durable, revocable, and hard to fool.

These tests exercise the workbench's host integration of the standalone
``circle_authority.py`` reducer: proposal, signed execution, revocation, crash
recovery, log integrity, and the negative paths an attacker or accident might
take. Presentation only — no hardware or human actuation is authorized here.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from models.workbench import Workbench, write_json
from models.workbench_timeline import build_timeline

SETTINGS = {"scenario": "clean", "seed": 7, "arm": "active", "compare": False,
            "feedback": {"modalities": ["audio", "visual"], "max_gain": 0.5, "breath_bpm": 6.0},
            "consent": {"audio": True}}


class ConsentGateTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.applied: list[tuple[str, str, dict]] = []

        def executor(operation, run_id, parameters):
            self.applied.append((operation, run_id, dict(parameters)))

        from models.consent_gate import WorkbenchConsent
        self.gate = WorkbenchConsent(self.root, executor)

    def tearDown(self):
        self.temporary.cleanup()

    def test_propose_sign_execute_round_trip(self):
        action = self.gate.propose_enable_audio("a" * 32, {"modalities": ["audio"], "max_gain": 0.5}, "ab" * 32)
        self.assertEqual(self.gate.state(action)["state"], "PENDING_SIGNATURE")
        self.assertEqual(self.applied, [])  # pending consent never mutates
        result = self.gate.consent(action)
        self.assertEqual(result["state"], "EXECUTED")
        self.assertEqual(len(self.applied), 1)
        self.assertEqual(self.applied[0][0], "ENABLE_AUDIO")
        # The durable log holds the proposal and the consented execution.
        log = self.gate.log_path.read_text(encoding="utf-8").splitlines()
        kinds = [json.loads(line)["kind"] for line in log]
        self.assertIn("ACTION_REGISTERED", kinds)
        self.assertIn("CONSENT_PROCESSED", kinds)
        verdict = self.gate.verify_log()
        self.assertTrue(verdict["valid"], verdict["problems"])
        self.assertGreaterEqual(verdict["records"], 2)

    def test_double_consent_executes_once(self):
        action = self.gate.propose_enable_audio("a" * 32, {"modalities": ["audio"], "max_gain": 0.5}, "ab" * 32)
        first = self.gate.consent(action)
        second = self.gate.consent(action)
        self.assertEqual(first["state"], "EXECUTED")
        self.assertEqual(second["state"], "EXECUTED")
        self.assertEqual(len(self.applied), 1)  # exactly-once on the executor path
        kinds = [json.loads(line)["kind"] for line in self.gate.log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(kinds.count("CONSENT_PROCESSED"), 1)
        self.assertIn("CONSENT_IGNORED", kinds)  # the replayed consent is logged, not applied

    def test_executor_refusal_rejects_permanently(self):
        def refusing(operation, run_id, parameters):
            raise ValueError("run record no longer matches")
        from models.consent_gate import WorkbenchConsent
        gate = WorkbenchConsent(self.root, refusing)
        action = gate.propose_enable_audio("a" * 32, {"modalities": ["audio"], "max_gain": 0.5}, "ab" * 32)
        result = gate.consent(action)
        self.assertEqual(result["state"], "REJECTED")
        again = gate.consent(action)
        self.assertEqual(again["state"], "REJECTED")  # no automatic retry

    def test_tampered_log_is_detected(self):
        action = self.gate.propose_enable_audio("a" * 32, {"modalities": ["audio"], "max_gain": 0.5}, "ab" * 32)
        self.gate.consent(action)
        original = self.gate.log_path.read_text(encoding="utf-8")
        # A one-character change inside a record body.
        lines = original.splitlines()
        tampered = json.loads(lines[0])
        tampered["frame"] = 99
        lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
        self.gate.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        verdict = self.gate.verify_log()
        self.assertFalse(verdict["valid"])
        self.assertTrue(any("does not match its hash" in problem for problem in verdict["problems"]))

    def test_revocation_is_a_restricted_mutation(self):
        result = self.gate.revoke_audio("a" * 32, {"modalities": ["audio"], "max_gain": 0.5}, "ab" * 32)
        # The REVOKE_AUDIO mutation itself executes through the gate...
        self.assertEqual(result["state"], "EXECUTED")
        self.assertTrue(result.get("revoke_action_id"))
        self.assertEqual(self.applied[-1][0], "REVOKE_AUDIO")
        log_text = self.gate.log_path.read_text(encoding="utf-8")
        self.assertIn("REVOKE_AUDIO", log_text)
        self.assertIn("CONSENT_PROCESSED", log_text)

    def test_keys_are_stable_across_instances(self):
        from models.consent_gate import WorkbenchConsent
        again = WorkbenchConsent(self.root, lambda *args: None)
        self.assertEqual(again.keys.public_bytes(), self.gate.keys.public_bytes())


class WorkbenchConsentIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workbench = Workbench(Path(self.temporary.name))

    def tearDown(self):
        self.workbench.close()
        self.temporary.cleanup()

    def _run(self) -> dict:
        with patch("models.workbench.run_session") as run_session, patch("models.workbench.export_run") as exporter:
            run_session.return_value = object()
            exporter.return_value = {"manifest": {}, "scorecard": {"checks": []}}
            record = self.workbench.start(dict(SETTINGS))
            self.workbench.worker.join(10)
        return self.workbench.get(record["id"])

    def test_audio_session_proposes_and_consents_through_the_gate(self):
        run = self._run()
        entry = run["consent_record"]
        self.assertEqual(entry["state"], "PENDING_SIGNATURE")
        self.assertTrue(entry["action_id"])
        # Consent arrives after the run started — telemetry is never blocked.
        result = self.workbench.consent_audio(run["id"])
        self.assertEqual(result["state"], "EXECUTED")
        self.assertEqual(self.workbench.get(run["id"])["consent_record"]["state"], "EXECUTED")

    def test_settings_mismatch_rejects_the_mutation(self):
        run = self._run()
        # An attacker (or accident) rewrites the run's feedback settings after
        # the proposal; the executor must refuse to execute the stale envelope.
        with self.workbench.lock:
            record = self.workbench.get(run["id"])
            record["settings"]["feedback"]["max_gain"] = 0.1
            write_json(self.workbench.directory(run["id"]) / "run.json", record)
        result = self.workbench.consent_audio(run["id"])
        self.assertEqual(result["state"], "REJECTED")
        saved = self.workbench.get(run["id"])["consent_record"]
        self.assertEqual(saved["state"], "REJECTED")
        self.assertEqual(saved["reason"], "CONSENT_REJECTED_OR_EXECUTION_REFUSED")
        # And the rejection is permanent: a later consent does not re-execute.
        self.assertEqual(self.workbench.consent_audio(run["id"])["state"], "REJECTED")

    def test_revocation_updates_the_run_record(self):
        run = self._run()
        self.workbench.consent_audio(run["id"])
        result = self.workbench.revoke_audio(run["id"])
        self.assertEqual(result["state"], "REVOKED")
        self.assertEqual(self.workbench.get(run["id"])["consent_record"]["state"], "REVOKED")

    def test_crash_between_proposal_and_consent_never_executes(self):
        run = self._run()
        self.assertEqual(run["consent_record"]["state"], "PENDING_SIGNATURE")
        # Simulate a restart: a fresh workbench over the same output tree.
        self.workbench.close()
        restarted = Workbench(self.workbench.root)
        record = restarted.get(run["id"])
        self.assertEqual(record["consent_record"]["state"], "REJECTED")
        self.assertEqual(record["consent_record"]["reason"], "WORKBENCH_RESTARTED_PENDING_NOT_EXECUTED")
        restarted.close()

    def test_timeline_reports_executed_consent_only(self):
        run = self._run()
        evidence = self.workbench.directory(run["id"]) / "evidence"
        evidence.mkdir(exist_ok=True)
        # A minimal evidence bundle so build_timeline can read it.
        from dataclasses import replace
        from models.physiology.experiment import run_session
        from models.physiology.scenarios import SCENARIOS
        from tools.run_physiology_twin import export_run
        session = run_session(replace(SCENARIOS["clean"].configure(7), actuate=True))
        export_run(session, evidence, None, with_report=False)
        record = self.workbench.get(run["id"])
        self.workbench._update(run["id"], status="completed",
                              summary={"scorecard": {"passed": 19, "total": 19}, "audit_valid": True})
        document = self.workbench.timeline(run["id"])
        # Pending consent: intent true, execution false.
        self.assertFalse(document["session"]["feedback_consent"]["audio"])
        self.assertEqual(document["session"]["feedback_consent"]["state"], "PENDING_SIGNATURE")
        self.workbench.consent_audio(run["id"])
        document = self.workbench.timeline(run["id"])
        self.assertTrue(document["session"]["feedback_consent"]["audio"])
        self.assertEqual(document["session"]["feedback_consent"]["state"], "EXECUTED")
        self.workbench.revoke_audio(run["id"])
        document = self.workbench.timeline(run["id"])
        self.assertFalse(document["session"]["feedback_consent"]["audio"])
        self.assertEqual(document["session"]["feedback_consent"]["state"], "REVOKED")


if __name__ == "__main__":
    unittest.main()
