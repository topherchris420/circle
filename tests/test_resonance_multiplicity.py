"""Resonance comparisons pay for the search: many geometries cannot yield a 'best one' for free."""

import random
import unittest

from models.resonance_response.analyzer import ResonanceAnalyzer


def trial(analyzer, effect, seed, family_size=1, prior=None):
    rng = random.Random(seed)
    base = [rng.gauss(0, 1) for _ in range(60)]
    active = [rng.gauss(effect, 1) for _ in range(60)]
    washout = [rng.gauss(0, 1) for _ in range(60)]
    sham_b = [rng.gauss(0, 1) for _ in range(60)]
    sham_a = [rng.gauss(0, 1) for _ in range(60)]
    return analyzer.evaluate_trial(f"CFG-{seed}", f"TRIAL-{seed:08d}", base, active, washout, sham_b, sham_a,
                                   rf_field_strength_v_m=0.1, temp_delta_c=0.0, prior_trial_scores=prior,
                                   family_size=family_size)


class MultiplicityTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = ResonanceAnalyzer(n_permutations=199)

    def test_family_size_inflates_the_p_value_used_for_status(self):
        single = trial(self.analyzer, 0.6, 1)
        family = trial(ResonanceAnalyzer(n_permutations=199), 0.6, 1, family_size=40)
        self.assertEqual(family.permutation_p_value, single.permutation_p_value)
        self.assertAlmostEqual(family.p_value_adjusted, min(1.0, single.permutation_p_value * 40))
        self.assertEqual(family.to_dict()["comparison_family_size"], 40)

    def test_holm_can_only_downgrade(self):
        evaluations = [trial(self.analyzer, 0.0, seed) for seed in range(10)] + [trial(self.analyzer, 0.5, 99)]
        adjusted = ResonanceAnalyzer.holm_adjust(evaluations)
        rank = {"ARTIFACT_LIKELY": -1, "INCONCLUSIVE": 0, "EXPLORATORY": 1, "REPEATABLE_DIFFERENCE": 2}
        for before, after in zip(evaluations, adjusted):
            self.assertLessEqual(rank[after.evidence_status], rank[before.evidence_status])
            self.assertGreaterEqual(after.p_value_adjusted, before.permutation_p_value)
            self.assertEqual(after.family_size, len(evaluations))

    def test_null_results_are_reported_as_results(self):
        result = trial(self.analyzer, 0.0, 3)
        if result.evidence_status == "INCONCLUSIVE":
            self.assertIn("null result is a result", result.interpretation_notes)
        self.assertNotIn("verified", result.interpretation_notes.lower())


if __name__ == "__main__":
    unittest.main()
