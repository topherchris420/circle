"""Adversarial scenario corpus: frozen expected outcomes the closed loop must keep reproducing.

Every scenario is regenerated deterministically and compared with
tests/fixtures/scenario-outcomes.json. A behavioral change fails here until the
corpus is regenerated deliberately (see the fixture's note).
"""

import json
from pathlib import Path
import unittest

from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS, UNWARRANTED_AROUSAL, system_checks
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

    def test_interrupted_state_is_still_acted_on_in_time(self):
        """The suite is two-sided: the clean-window hold must not make the loop timid."""
        result = self.results["interrupted"]
        timely = next(c for c in result["checks"] if c["id"] == "timely_response")
        self.assertTrue(timely["passed"], timely["detail"])
        self.assertEqual([a for _, a in result["decisions"]][0], "START_PACED_BREATHING")
        self.assertGreater(result["holds_by_reason"].get("EVIDENCE_GAP", 0), 0,
                           "the loop held while the window was still partly impaired, then acted")


class LaggingProxyTest(unittest.TestCase):
    """The defect retained in the 1.1.0 evaluation (seeds 500-529): guidance started at 305 s in motion_heavy,
    after 45 s of corrupted evidence, on an index that was the lagging tail of a state that had already resolved."""

    def test_motion_heavy_seed_503_holds_instead_of_starting(self):
        scenario = SCENARIOS["motion_heavy"]
        run = run_session(scenario.configure(503))
        result = system_checks(run, scenario)
        self.assertTrue(result["passed"], [c for c in result["checks"] if not c["passed"]])
        self.assertFalse(any(action == "START_PACED_BREATHING" for _, action in result["decisions"]))
        holds = [e for e in run.evaluations if e.action == "HOLD_EVIDENCE_GAP"]
        self.assertTrue(holds)
        trigger = run.config.controller.trigger_index
        for ev in holds:
            # Each hold was taken on an index that would otherwise have triggered, over a window not yet fully clean.
            self.assertGreaterEqual(ev.features["arousal_index"], trigger)
            self.assertLess(ev.features["clean_since_s"], run.config.controller.feature_window_s)
        clock = run.rig.clock
        latent = [float(run.twin.arousal[min(run.twin._n - 1, int(round(clock.to_true_s(e.input_cutoff_us) / 0.01)))])
                  for e in holds]
        self.assertTrue(all(a < UNWARRANTED_AROUSAL for a in latent), latent)


if __name__ == "__main__":
    unittest.main()
