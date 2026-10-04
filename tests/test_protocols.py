"""Proposal -> validation -> human authorization -> execution stays a hard boundary."""

import copy
import json
from pathlib import Path
import unittest

import numpy as np

from models.physiology.controller import CONTROLLER_VERSION, ControllerConfig
from models.protocols import ProtocolError, authorize, controller_config, execute, holm, sign_flip_p, validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "experiments/protocols/paced-breathing-arousal.json").read_text(encoding="utf-8"))


def variant(**changes):
    protocol = copy.deepcopy(EXAMPLE)
    protocol.update(changes)
    return protocol


class ProtocolValidationTest(unittest.TestCase):
    def test_example_is_valid_for_simulation_only(self):
        self.assertEqual(validate(EXAMPLE)["status"], "VALID_FOR_SIMULATION")

    def test_hardware_and_human_targets_are_rejected(self):
        for target in ("ELECTRONIC_PHANTOM", "HARDWARE_BENCH", "HUMAN_PARTICIPANT"):
            with self.subTest(target=target):
                result = validate(variant(target=target))
                self.assertEqual(result["status"], "REJECTED")
                self.assertTrue(any("not executable" in p for p in result["problems"]))

    def test_quality_gates_may_only_tighten(self):
        result = validate(variant(quality_gates={"max_motion_fraction": 0.5}))
        self.assertTrue(any("looser" in p for p in result["problems"]))
        self.assertEqual(validate(variant(quality_gates={"max_motion_fraction": 0.1}))["status"], "VALID_FOR_SIMULATION")

    def test_causality_margin_cannot_be_overridden(self):
        protocol = variant()
        protocol["decision_rule"]["overrides"] = {"decision_margin_s": 0.0}
        self.assertTrue(any("not permitted" in p for p in validate(protocol)["problems"]))

    def test_sham_arm_is_mandatory(self):
        protocol = variant(arms=[{"id": "ACTIVE", "actuate": True}, {"id": "SHAM", "actuate": True}])
        self.assertTrue(any("SHAM" in p for p in validate(protocol)["problems"]))

    def test_development_seeds_cannot_be_confirmatory(self):
        self.assertTrue(any("develop" in p for p in validate(variant(seeds=[7, 300]))["problems"]))

    def test_ai_proposals_must_identify_the_model(self):
        protocol = variant(proposed_by={"kind": "AI_MODEL", "name": "some model"})
        self.assertTrue(any("model_version" in p for p in validate(protocol)["problems"]))

    def test_multiple_tested_outcomes_require_correction(self):
        protocol = variant()
        protocol["analysis_plan"] = dict(protocol["analysis_plan"], correction="NONE")
        self.assertTrue(any("HOLM" in p for p in validate(protocol)["problems"]))


class AuthorizationBoundaryTest(unittest.TestCase):
    def test_authorization_requires_a_named_reviewer_and_a_valid_protocol(self):
        with self.assertRaises(ProtocolError):
            authorize(EXAMPLE, "  ", "2026-09-27")
        with self.assertRaises(ProtocolError):
            authorize(variant(target="HUMAN_PARTICIPANT"), "Reviewer", "2026-09-27")

    def test_any_change_after_authorization_voids_it(self):
        token = authorize(EXAMPLE, "Reviewer", "2026-09-27")
        changed = variant(hypothesis=EXAMPLE["hypothesis"] + " (edited after review)")
        with self.assertRaisesRegex(ProtocolError, "PROTOCOL_CHANGED"):
            execute(changed, token)

    def test_unauthorized_execution_is_refused(self):
        with self.assertRaises(ProtocolError):
            execute(EXAMPLE, {"protocol_sha256": validate(EXAMPLE)["protocol_sha256"], "target": "SIMULATION"})

    def test_small_authorized_protocol_executes_with_replayable_sessions(self):
        protocol = variant(seeds=[400, 401], outcomes=[
            {"id": "arousal_proxy", "metric": "recovery_arousal_index_mean", "role": "PRIMARY", "direction": "DECREASE"}])
        result = execute(protocol, authorize(protocol, "Reviewer", "2026-09-27"))
        self.assertTrue(result["replays_match"])
        test = result["tests"]["arousal_proxy"]
        self.assertEqual(test["evidence_class"], "CONTROLLER_DERIVED")
        self.assertEqual(test["n_pairs"], 2)
        self.assertGreaterEqual(test["p_value"], 0.25, "two pairs can never reach significance")
        self.assertIn("assumed response model", result["interpretation"])
        self.assertEqual(result["controller_version"], CONTROLLER_VERSION)
        self.assertTrue(result["pipeline_source"].startswith("sha256:"))

    def test_protocol_keeps_the_scenario_arming_but_tightens_its_gates(self):
        config = controller_config(variant(quality_gates={"max_motion_fraction": 0.1}), ControllerConfig(arm_phase="STRESSOR"))
        self.assertEqual(config.arm_phase, "STRESSOR")
        self.assertEqual(config.max_motion_fraction, 0.1)


class StatisticsTest(unittest.TestCase):
    def test_exact_sign_flip_minimum_is_one_over_two_to_the_n(self):
        self.assertAlmostEqual(sign_flip_p(np.full(8, -1.0), "DECREASE", 999, 0), 1 / 256)
        self.assertEqual(sign_flip_p(np.full(8, 1.0), "DECREASE", 999, 0), 1.0)

    def test_holm_is_monotone_and_capped(self):
        adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(adjusted["a"], 0.03)
        self.assertAlmostEqual(adjusted["c"], 0.06)
        self.assertAlmostEqual(adjusted["b"], 0.06)
        self.assertEqual(holm({"a": 0.9, "b": 0.8})["a"], 1.0)


if __name__ == "__main__":
    unittest.main()
