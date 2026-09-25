"""Exact Student-t critical values and valid Monte Carlo permutation p-values."""

import unittest

from models.resonance_response.analyzer import ResonanceAnalyzer
from models.resonance_response.closed_loop import get_student_t_critical_value, student_t_two_sided_p

# Two-sided alpha = 0.05 critical values from standard tables.
REFERENCE = {1: 12.706, 2: 4.303, 3: 3.182, 5: 2.571, 10: 2.228, 11: 2.201, 13: 2.160, 17: 2.110,
             25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


class StudentTTest(unittest.TestCase):
    def test_critical_values_match_tables_for_every_df(self):
        for df, expected in REFERENCE.items():
            self.assertAlmostEqual(get_student_t_critical_value(df), expected, delta=6e-4, msg=f"df={df}")

    def test_other_alpha_and_round_trip(self):
        self.assertAlmostEqual(get_student_t_critical_value(10, alpha=0.01), 3.169, delta=6e-4)
        for df in (1, 4, 9, 33):
            t = get_student_t_critical_value(df)
            self.assertAlmostEqual(student_t_two_sided_p(t, df), 0.05, places=9)

    def test_nonpositive_df_is_conservative(self):
        self.assertAlmostEqual(get_student_t_critical_value(0), get_student_t_critical_value(1))


class PermutationPValueTest(unittest.TestCase):
    def test_p_value_is_never_zero(self):
        analyzer = ResonanceAnalyzer(n_permutations=199, n_bootstraps=50)
        base = [0.0 + 0.01 * (i % 3) for i in range(60)]
        intervention = [5.0 + 0.01 * (i % 3) for i in range(60)]
        result = analyzer.evaluate_trial("CFG", "TRIAL-0000", base, intervention, base)
        # Phipson & Smyth: p = (b + 1) / (m + 1) with b >= 0 extreme permutations.
        extreme = result.permutation_p_value * 200 - 1
        self.assertGreaterEqual(result.permutation_p_value, 1 / 200)
        self.assertAlmostEqual(extreme, round(extreme), places=6)


if __name__ == "__main__":
    unittest.main()
