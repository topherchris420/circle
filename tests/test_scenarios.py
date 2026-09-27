"""Adversarial scenario corpus: frozen expected outcomes the closed loop must keep reproducing.

Every scenario is regenerated deterministically and compared with
tests/fixtures/scenario-outcomes.json. A behavioral change fails here until the
corpus is regenerated deliberately (see the fixture's note).
"""

import json
from pathlib import Path
import unittest

from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS, system_checks
from tools.run_physiology_twin import corpus

ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / "tests/fixtures/scenario-outcomes.json").read_text(encoding="utf-8"))["outcomes"]


class ScenarioCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        results = [system_checks(run_session(s.configure(7)), s) for s in SCENARIOS.values()]
        cls.results = {r["scenario"]: r for r in results}
        cls.regenerated = corpus({"results": results})["outcomes"]

    def test_corpus_covers_every_scenario(self):
        self.assertEqual(sorted(k.split("@")[0] for k in FROZEN), sorted(SCENARIOS))

    def test_regenerated_outcomes_match_the_frozen_corpus(self):
        for key, expected in FROZEN.items():
            with self.subTest(scenario=key):
                self.assertEqual(self.regenerated[key], expected)

    def test_every_frozen_scenario_passes_its_system_checks(self):
        for name, result in self.results.items():
            with self.subTest(scenario=name):
                self.assertTrue(result["passed"], [c for c in result["checks"] if not c["passed"]])

    def test_ambiguous_physiology_is_held_not_acted_on(self):
        result = self.results["ambiguous"]
        self.assertFalse(any(action == "START_PACED_BREATHING" for _, action in result["decisions"]))
        self.assertGreater(result["holds_by_reason"].get("SIGNALS_DISAGREE", 0), 0)

    def test_contact_faults_are_named_not_mistaken_for_calm(self):
        reasons = set(self.results["poor_contact"]["gate_reasons_seen"])
        self.assertTrue({"EDA_CONTACT_LOST", "PPG_COUPLING_CHANGED"} <= reasons)

    def test_vanished_channel_is_declared_and_stale(self):
        result = self.results["sensor_loss"]
        self.assertIn("DATA_STALE", result["gate_reasons_seen"])
        gaps = next(c for c in result["checks"] if c["id"] == "gaps_exact")
        self.assertTrue(gaps["passed"])
        self.assertEqual(len(gaps["detail"]["declared"]), 2)


if __name__ == "__main__":
    unittest.main()
