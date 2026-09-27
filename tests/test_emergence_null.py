"""The emergence discovery engine must be good at embarrassing itself."""

import unittest

import numpy as np

from models.emergence import engine
from models.emergence.null_model import circular_shift_null, discovery_counts


def small_run(frames=160, agents=10, field_res=16, seed=3):
    config = engine.SimulationConfig(FRAMES=frames, AGENTS=agents, FIELD_RES=field_res, MEMORY=100, SEED=seed)
    artifacts = engine.run_simulation(config=config, render=False)
    return config, artifacts.metrics


class NullModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.metrics = small_run()
        cls.history = np.array(cls.metrics.observation_history)

    def test_null_counter_reproduces_the_engine_exactly(self):
        counts = discovery_counts(self.history, self.metrics.threshold_history, self.config.CORR_WINDOW)
        self.assertEqual(int(counts.sum()), self.metrics.total_discoveries)

    def test_engine_finds_the_injected_couplings_and_only_those(self):
        null = circular_shift_null(self.history, self.metrics.threshold_history, self.config.CORR_WINDOW,
                                   surrogates=39, seed=1, synthetic=True)
        score = null["known_truth_score"]
        self.assertEqual(score["false_pairs_found"], [])
        self.assertIn("ch0-ch1", score["injected_found"])

    def test_independent_noise_still_produces_chance_discoveries_that_the_null_absorbs(self):
        rng = np.random.default_rng(11)
        frames, agents = 160, 10
        smooth = np.cumsum(rng.standard_normal((frames, agents, 4)), axis=0)  # autocorrelated, independent channels
        thresholds = [self.config.DISCOVER_THRESH] * frames
        null = circular_shift_null(smooth, thresholds, self.config.CORR_WINDOW, surrogates=39, seed=2)
        self.assertGreater(null["observed_total"], 0, "random walks correlate by chance")
        self.assertGreaterEqual(null["p_total"], 0.05)
        self.assertEqual(null["pairs_significant_fwer_0_05"], [])

    def test_short_runs_report_insufficient_length_instead_of_a_p_value(self):
        null = circular_shift_null(self.history[:60], self.metrics.threshold_history[:60], 50, surrogates=9, seed=0)
        self.assertEqual(null["status"], "INSUFFICIENT_LENGTH")
        self.assertNotIn("p_total", null)


if __name__ == "__main__":
    unittest.main()
