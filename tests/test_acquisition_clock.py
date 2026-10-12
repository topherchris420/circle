"""Host-to-device clock mapping: hulls, the causal minimum-delay line, and what receipts and probes prove."""

from __future__ import annotations

import itertools
import unittest

import numpy as np

from models.acquisition.clock import MinimumDelayClock, bound_mapping, lower_hull, minimum_delay_line, upper_hull

NOMINAL = 4000.0
BOUNDS = (NOMINAL * 0.975, NOMINAL * 1.025)


def receipts(drift_ppm: float, n: int = 15000, seed: int = 0, loss: float = 0.01):
    """A device ticking every 4 ms * (1 + drift), received through a radio and a 16 ms USB latency timer."""
    rng = np.random.default_rng(seed)
    period = NOMINAL * (1 + drift_ppm * 1e-6)
    ticks = np.arange(n)
    truth = 1_000_000.0 + ticks * period
    received = np.ceil((truth + rng.uniform(1000, 3000, n)) / 16000) * 16000 + rng.exponential(200, n)
    keep = rng.random(n) > loss
    return ticks[keep], received[keep], truth[keep], period


class HullTest(unittest.TestCase):
    def test_lower_hull_matches_brute_force(self):
        rng = np.random.default_rng(1)
        x = np.sort(rng.choice(1000, 60, replace=False)).astype(float)
        y = rng.normal(0, 10, 60)
        hull = set(lower_hull(x, y))
        for i, j in itertools.combinations(range(60), 2):
            slope = (y[j] - y[i]) / (x[j] - x[i])
            below = y - (y[i] + slope * (x - x[i]))
            if np.all(below >= -1e-9):          # an edge with every point on or above it joins two hull vertices
                self.assertIn(i, hull)
                self.assertIn(j, hull)
        self.assertEqual(upper_hull(x, -y), lower_hull(x, y))


class MinimumDelayClockTest(unittest.TestCase):
    def test_online_line_never_lies_after_a_receipt_and_recovers_the_drift(self):
        for drift in (-5000.0, 0.0, 3000.0, 24000.0):
            ticks, received, _, _ = receipts(drift)
            clock = MinimumDelayClock(NOMINAL, 0.025)
            for i, (k, y) in enumerate(zip(ticks, received)):
                clock.add(k, y)
                if i % 997 == 0:
                    line = clock.line()
                    self.assertTrue(np.all(line.at(ticks[:i + 1]) <= received[:i + 1] + 1e-6))
            line = clock.line()
            self.assertLess(abs(line.ppm(NOMINAL) - drift), 20.0, drift)
            offline = minimum_delay_line(ticks, received, BOUNDS)
            self.assertAlmostEqual(line.slope_us, offline.slope_us, places=6)
            self.assertAlmostEqual(float(line.at(7000)), float(offline.at(7000)), places=3)

    def test_the_offset_is_the_minimum_latency_not_the_truth(self):
        ticks, received, truth, _ = receipts(1800.0)
        line = minimum_delay_line(ticks, received, BOUNDS)
        error = line.at(ticks) - truth
        self.assertGreater(float(error.min()), 0.0)            # never earlier than the truth
        self.assertLess(float(error.max()), 3500.0)            # within the fastest delivery seen

    def test_slope_is_clamped_to_the_oscillator_tolerance(self):
        clock = MinimumDelayClock(NOMINAL, 0.025)
        clock.add(0, 0.0)
        clock.add(10, 10 * NOMINAL * 1.5)                      # physically impossible tick length
        self.assertAlmostEqual(clock.line().slope_us, NOMINAL * 1.025)

    def test_repeated_tick_keeps_the_earlier_receipt_and_ticks_cannot_go_back(self):
        clock = MinimumDelayClock(NOMINAL, 0.025)
        clock.add(5, 30_000.0)
        clock.add(5, 25_000.0)
        self.assertEqual(clock.count, 1)
        self.assertEqual(clock.hy, [25_000.0])
        with self.assertRaises(ValueError):
            clock.add(4, 40_000.0)


class BoundMappingTest(unittest.TestCase):
    def probes(self, truth_at, period, rng, last_tick):
        sends = np.arange(truth_at(100), truth_at(last_tick - 100), 500_000.0)
        uplink = rng.uniform(1000, 20000, len(sends))
        ticks = np.ceil((sends + uplink - truth_at(0)) / period).astype(int)
        return ticks, sends - NOMINAL                          # one sample of slack, as the Cyton bridge allows

    def test_truth_lies_inside_the_bounds_and_receipts_alone_bound_one_side(self):
        rng = np.random.default_rng(4)
        for drift in (-4000.0, 2500.0):
            ticks, received, truth, period = receipts(drift, seed=int(abs(drift)))
            truth_at = lambda k: 1_000_000.0 + k * period  # noqa: E731
            pt, py = self.probes(truth_at, period, rng, int(ticks[-1]))
            both = bound_mapping(ticks, received, pt, py, BOUNDS)
            self.assertTrue(both.consistent)
            self.assertLessEqual(both.earliest_us, truth_at(both.tick))
            self.assertGreaterEqual(both.latest_us, truth_at(both.tick))
            self.assertLess(both.width_us, 25_000)
            self.assertLessEqual(both.slope_min_us, period)
            self.assertGreaterEqual(both.slope_max_us, period)
            alone = bound_mapping(ticks, received, [], [], BOUNDS)
            self.assertIsNone(alone.earliest_us)
            self.assertIsNone(alone.width_us)
            self.assertAlmostEqual(alone.latest_us, both.latest_us, delta=both.width_us)

    def test_hull_points_and_mean_tick_reproduce_the_full_answer(self):
        ticks, received, _, _ = receipts(1500.0)
        clock = MinimumDelayClock(NOMINAL, 0.025)
        for k, y in zip(ticks, received):
            clock.add(k, y)
        full = bound_mapping(ticks, received, [], [], clock.bounds)
        hull = bound_mapping(clock.hx, clock.hy, [], [], clock.bounds, mean_tick=clock.tick_sum / clock.count)
        self.assertAlmostEqual(full.estimate_us, hull.estimate_us, places=3)
        self.assertAlmostEqual(full.latest_us, hull.latest_us, places=3)

    def test_a_probe_after_its_receipt_is_reported_inconsistent(self):
        ticks = np.arange(100)
        received = 10_000.0 + ticks * NOMINAL + 2000
        bounds = bound_mapping(ticks, received, [50], [10_000.0 + 50 * NOMINAL + 5000], BOUNDS)
        self.assertFalse(bounds.consistent)
        self.assertIsNone(bounds.latest_us)


if __name__ == "__main__":
    unittest.main()
