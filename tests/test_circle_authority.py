"""Consent, immutability, event ordering, failure handling and deterministic replay."""

from base64 import b64decode
from collections import deque
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import unittest
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from circle_authority import (ActionEnvelope, ActionState, CircleAuthority, HumanConsentEvent,
                              Mutation, RestrictedActionEvent, TelemetryEvent, canonical_json,
                              verify_human_consent)
from tools.run_authority_demo import run_demo


class AuthorityTest(unittest.TestCase):
    def setUp(self):
        self.signer = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.action = ActionEnvelope(Mutation("SET_LEVEL", '{"level":2}'), 0, "a" * 64,
                                     UUID("8f136ffc-7dd2-4e27-8ab1-21186598b620"))
        self.executions = []
        self.telemetry = []
        self.authority = CircleAuthority(self.signer.public_key(),
                                         lambda *args: self.executions.append(args), self.telemetry.append)

    def consent(self, action=None):
        action = action or self.action
        return HumanConsentEvent(action.action_id, self.signer.sign(action.action_id.bytes))

    def register(self):
        return self.authority.step(0, 0, deque([RestrictedActionEvent(self.action)]))

    def test_waiting_keeps_telemetry_running_and_executes_at_exact_consent_frame(self):
        self.register()
        for frame in range(1, 4):
            self.authority.step(frame, frame * 100, deque([TelemetryEvent("hr", 70 + frame)]))
            self.assertEqual(self.executions, [])
            self.assertEqual(self.authority.pending_registry[self.action.action_id].state,
                             ActionState.PENDING_SIGNATURE)
        result = self.authority.step(4, 400, deque([self.consent()]))
        executed, frame, timestamp = self.executions[0]
        self.assertEqual((frame, timestamp), (4, 400))
        self.assertEqual(executed.signature, self.consent().signature)
        record = json.loads(result.replay_payloads[0])
        self.assertEqual(record["execution_frame"], 4)
        self.assertEqual(record["state"], "EXECUTED")
        self.assertEqual(record["action"]["state_history_hash"], "a" * 64)
        self.assertEqual(record["envelope_hash"], self.action.envelope_hash)
        self.assertEqual(b64decode(record["signature_b64"]), executed.signature)
        self.assertTrue(verify_human_consent(HumanConsentEvent(executed.action_id, executed.signature),
                                           self.signer.public_key()))
        self.assertEqual(len(self.telemetry), 3)
        self.assertFalse(self.authority.pending_registry)

    def test_signature_verifier_uses_binary_uuid_and_registered_key(self):
        self.assertTrue(verify_human_consent(self.consent(), self.signer.public_key()))
        other_key = Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32))))
        for signature in (b"", b"x" * 63, b"x" * 64, b"x" * 65,
                          self.signer.sign(str(self.action.action_id).encode()),
                          other_key.sign(self.action.action_id.bytes)):
            with self.subTest(signature=signature):
                self.assertFalse(verify_human_consent(HumanConsentEvent(self.action.action_id, signature),
                                                    self.signer.public_key()))

    def test_signature_for_another_uuid_cannot_execute(self):
        self.register()
        wrong_signature = self.signer.sign(UUID(int=1).bytes)
        self.authority.step(1, 100, deque([HumanConsentEvent(self.action.action_id, wrong_signature)]))
        self.assertEqual(self.executions, [])
        self.assertEqual(self.authority.action_registry[self.action.action_id].reason, "INVALID_SIGNATURE")

    def test_invalid_consent_is_terminal_and_cannot_be_retried(self):
        self.register()
        result = self.authority.step(1, 100, deque([HumanConsentEvent(self.action.action_id, b"x" * 64),
                                                   self.consent(), TelemetryEvent("hr", 75)]))
        self.assertEqual(self.executions, [])
        self.assertEqual(self.authority.action_registry[self.action.action_id].state, ActionState.REJECTED)
        self.assertEqual(json.loads(result.replay_payloads[1])["kind"], "CONSENT_IGNORED")
        self.assertEqual(len(self.telemetry), 1)

    def test_duplicate_consent_and_re_registration_never_repeat_execution(self):
        self.register()
        self.authority.step(1, 100, deque([self.consent(), self.consent(), RestrictedActionEvent(self.action)]))
        self.assertEqual(len(self.executions), 1)
        self.assertEqual(self.authority.action_registry[self.action.action_id].state, ActionState.EXECUTED)

    def test_rebinding_uuid_cannot_change_approved_mutation(self):
        self.register()
        changed = replace(self.action, mutation=Mutation("SET_LEVEL", '{"level":999}'))
        self.authority.step(1, 100, deque([RestrictedActionEvent(changed), self.consent()]))
        self.assertEqual(self.executions[0][0].mutation.parameters(), {"level": 2})

    def test_immutable_envelope_and_readonly_registry(self):
        self.register()
        with self.assertRaises(FrozenInstanceError):
            self.action.timestamp_us = 999
        with self.assertRaises(TypeError):
            self.authority.pending_registry[self.action.action_id] = None
        decoded = self.action.mutation.parameters()
        decoded["level"] = 999
        self.assertEqual(self.action.mutation.parameters(), {"level": 2})

    def test_consent_before_registration_is_not_retained_as_authorization(self):
        self.authority.step(0, 0, deque([self.consent(), RestrictedActionEvent(self.action)]))
        self.assertEqual(self.executions, [])
        self.assertIn(self.action.action_id, self.authority.pending_registry)

    def test_prefilled_signature_and_future_action_are_rejected(self):
        for action, reason in ((replace(self.action, signature=self.consent().signature),
                                "SIGNATURE_MUST_ARRIVE_AS_CONSENT_EVENT"),
                               (replace(self.action, timestamp_us=1), "ACTION_FROM_FUTURE")):
            with self.subTest(reason=reason):
                authority = CircleAuthority(self.signer.public_key(), lambda *args: self.fail(), lambda e: None)
                authority.step(0, 0, deque([RestrictedActionEvent(action), self.consent()]))
                self.assertEqual(authority.action_registry[action.action_id].reason, reason)

    def test_bounded_batch_and_callback_injection_wait_for_next_frame(self):
        incoming = deque([RestrictedActionEvent(self.action), self.consent()])

        def execute(*args):
            self.executions.append(args)
            incoming.append(TelemetryEvent("hr", 80))

        authority = CircleAuthority(self.signer.public_key(), execute, self.telemetry.append,
                                    max_events_per_frame=1)
        authority.step(0, 0, incoming)
        authority.step(1, 100, incoming)
        self.assertEqual(len(self.executions), 1)
        self.assertEqual(self.telemetry, [])
        authority.step(2, 200, incoming)
        self.assertEqual(self.telemetry, [TelemetryEvent("hr", 80)])

    def test_pending_capacity_rejects_without_interrupting_telemetry(self):
        authority = CircleAuthority(self.signer.public_key(), lambda *args: self.fail(), self.telemetry.append,
                                    max_pending_actions=1)
        second = replace(self.action, action_id=UUID(int=2))
        authority.step(0, 0, deque([RestrictedActionEvent(self.action), RestrictedActionEvent(second),
                                   TelemetryEvent("hr", 80)]))
        self.assertEqual(authority.action_registry[second.action_id].reason, "PENDING_REGISTRY_FULL")
        self.assertEqual(len(authority.pending_registry), 1)
        self.assertEqual(len(self.telemetry), 1)

    def test_execution_failure_is_logged_terminal_and_telemetry_continues(self):
        calls = []

        def fail(*args):
            calls.append(args)
            raise ValueError("deterministic mutation refused")

        authority = CircleAuthority(self.signer.public_key(), fail, self.telemetry.append)
        result = authority.step(0, 0, deque([RestrictedActionEvent(self.action), self.consent(),
                                            self.consent(), TelemetryEvent("hr", 80)]))
        self.assertEqual(len(calls), 1)
        record = json.loads(result.replay_payloads[1])
        self.assertEqual(record["reason"], "EXECUTION_FAILED")
        self.assertEqual(record["state"], "REJECTED")
        self.assertIsNone(record["execution_frame"])
        self.assertEqual(len(self.telemetry), 1)

    def test_failed_observer_does_not_drop_consent(self):
        def fail(event):
            raise ValueError("bad observation")

        authority = CircleAuthority(self.signer.public_key(), lambda *args: self.executions.append(args), fail)
        result = authority.step(0, 0, deque([TelemetryEvent("hr", 80), RestrictedActionEvent(self.action),
                                            self.consent()]))
        self.assertEqual(json.loads(result.replay_payloads[0])["kind"], "TELEMETRY_REJECTED")
        self.assertEqual(len(self.executions), 1)

    def test_frame_and_timestamp_checks_precede_queue_consumption(self):
        self.register()
        incoming = deque([self.consent()])
        for frame, timestamp in ((0, 100), (2, 100), (1, 0), (True, 100), (1, 1.5)):
            with self.subTest(frame=frame, timestamp=timestamp), self.assertRaises(ValueError):
                self.authority.step(frame, timestamp, incoming)
        self.assertEqual(len(incoming), 1)
        self.authority.step(1, 100, incoming)
        self.assertEqual(len(self.executions), 1)

    def test_empty_frames_do_not_discharge_pending_action(self):
        self.register()
        for frame in range(1, 10):
            self.assertEqual(self.authority.step(frame, frame, deque()).processed_events, 0)
        self.assertEqual(self.executions, [])
        self.assertIn(self.action.action_id, self.authority.pending_registry)

    def test_reentrant_step_cannot_execute_same_action_twice(self):
        def execute(*args):
            with self.assertRaises(RuntimeError):
                authority.step(0, 0, deque([self.consent()]))
            self.executions.append(args)

        authority = CircleAuthority(self.signer.public_key(), execute, self.telemetry.append)
        authority.step(0, 0, deque([RestrictedActionEvent(self.action), self.consent()]))
        self.assertEqual(len(self.executions), 1)

    def test_demo_replays_byte_for_byte_and_chain_hashes_bind_records(self):
        logs, state = run_demo()
        self.assertEqual(run_demo(), (logs, state))
        self.assertEqual(state, {"heart_rate": 75, "simulated_feedback_level": 2})
        previous = "0" * 64
        for sequence, payload in enumerate(logs):
            record = json.loads(payload)
            digest = record.pop("record_hash")
            self.assertEqual(record["sequence"], sequence)
            self.assertEqual(record["previous_record_hash"], previous)
            self.assertEqual(hashlib.sha256(canonical_json(record).encode()).hexdigest(), digest)
            record["frame"] += 1
            self.assertNotEqual(hashlib.sha256(canonical_json(record).encode()).hexdigest(), digest)
            previous = digest

    def test_nonfinite_parameters_and_mutable_signature_are_refused_at_ingress(self):
        for parameters in ('{"x":NaN}', '{"x":Infinity}', '[]'):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                Mutation("X", parameters)
        with self.assertRaises(TypeError):
            HumanConsentEvent(self.action.action_id, bytearray(64))


if __name__ == "__main__":
    unittest.main()
