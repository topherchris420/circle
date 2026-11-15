"""R.A.I.N.–CIRCLE bridge: proposals validate before they run, never after."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from models.protocols import validate
from tools.run_rain_bridge import random_baseline, run_bridge, stand_in_proposal

SEEDS = [410, 411]


class StandInProposalTest(unittest.TestCase):
    def test_proposal_is_valid_for_simulation(self):
        verdict = validate(stand_in_proposal(0, SEEDS))
        self.assertEqual(verdict["status"], "VALID_FOR_SIMULATION", verdict["problems"])

    def test_proposal_provenance_is_honest(self):
        proposal = stand_in_proposal(0, SEEDS)
        self.assertIn("stand-in", proposal["proposed_by"]["name"])
        self.assertIn("deterministic", proposal["proposed_by"]["name"])

    def test_unsafe_proposals_are_rejected_by_validation_not_trust(self):
        proposal = stand_in_proposal(0, SEEDS)
        # A proposer tries to loosen a quality gate below the default.
        loose = json.loads(json.dumps(proposal))
        loose["quality_gates"] = {"min_beat_coverage": 0.1}
        self.assertIn("looser than the default", " ".join(validate(loose)["problems"]))
        # A proposer tries a non-simulation target.
        hardware = json.loads(json.dumps(proposal))
        hardware["target"] = "HUMAN_PARTICIPANT"
        self.assertIn("not executable from this repository", " ".join(validate(hardware)["problems"]))
        # A proposer tries to drop the sham arm.
        one_arm = json.loads(json.dumps(proposal))
        one_arm["arms"] = [{"id": "ACTIVE", "actuate": True}]
        problems = " ".join(validate(one_arm)["problems"])
        self.assertTrue("too short" in problems or "SHAM" in problems, problems)

    def test_random_baseline_is_valid(self):
        self.assertEqual(validate(random_baseline(5, SEEDS))["status"], "VALID_FOR_SIMULATION")


class BridgeRunTest(unittest.TestCase):
    def test_bridge_executes_and_compares_against_baselines(self):
        report = run_bridge(candidate_count=1, seeds=SEEDS)
        labels = {item["label"] for item in report["executed"]}
        self.assertIn("HUMAN_DESIGNED", labels)
        self.assertIn("FIXED_DEFAULT", labels)
        self.assertIn("RANDOM_BASELINE", labels)
        self.assertIn("RAIN_STANDIN_00", labels)
        for item in report["executed"]:
            self.assertTrue(item["replays_match"], "every executed arm must replay identically")
            self.assertIn(item["primary"]["conclusion"], ("SUPPORTED_IN_SIMULATION", "NOT_SUPPORTED"))
            self.assertIn("versus_human_baseline", item)
        self.assertEqual(report["rejected"], [])
        self.assertIn("assumed response model", report["interpretation"])

    def test_failure_driven_evaluation_compares_rash_and_corrected(self):
        from tools.run_rain_bridge import failure_driven_evaluation
        section = failure_driven_evaluation([420, 421])
        for label in ("RASH_VARIANT", "CORRECTED_VARIANT"):
            entry = section["variants"][label]
            self.assertTrue(entry["validated"], entry.get("problems"))
            self.assertTrue(entry["replays_match"])
            self.assertIn(entry["primary"]["conclusion"],
                          ("SUPPORTED_IN_SIMULATION", "NOT_SUPPORTED"))
        self.assertIn("documented CIRCLE failure class", section["interpretation"])

    def test_bridge_report_is_deterministic(self):
        first = run_bridge(candidate_count=1, seeds=SEEDS)
        second = run_bridge(candidate_count=1, seeds=SEEDS)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
