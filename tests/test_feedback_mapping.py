"""Adaptive feedback mapping: bounds, gates, determinism, and honest holds."""

from __future__ import annotations

import unittest

from models.physiology.controller import Evaluation
from models.physiology.feedback import (FEEDBACK_VERSION, FeedbackConfig, FeedbackEvent, feedback_events,
                                        events_digest, events_from_documents)


def evaluation(t_s: float, features: dict, gate=(), state="IDLE", decision_id=None) -> Evaluation:
    return Evaluation(device_time_us=int(t_s * 1e6), window_start_us=int((t_s - 10) * 1e6),
                      window_end_us=int((t_s - 1) * 1e6), features=features, state=state,
                      gate_reasons=list(gate), decision_id=decision_id)


GOOD = {"hr_bpm": 72.0, "scl_us": 4.0, "scr_rate_per_min": 2.0, "arousal_index": 0.6,
        "motion_fraction": 0.0, "clean_since_s": 10.0, "beat_coverage": 1.0, "eda_contact_fraction": 1.0}


class FeedbackConfigTest(unittest.TestCase):
    def test_limits_are_enforced_not_advisory(self):
        for bad in ({"max_gain": 0.9}, {"max_gain": 0.0}, {"max_gain": -0.1},
                    {"breath_period_min_s": 2.0}, {"breath_period_max_s": 25.0},
                    {"guide_breath_bpm": 12.0}, {"modalities": ("haptic",)},
                    {"brightness_max": 1.5}, {"tempo_min": 2.5}):
            with self.subTest(bad), self.assertRaises(ValueError):
                FeedbackConfig(**{**FeedbackConfig().__dict__, **bad})
        FeedbackConfig()  # defaults are valid

    def test_gain_ceiling_is_quiet(self):
        self.assertLessEqual(FeedbackConfig().max_gain, 0.5)


class FeedbackMappingTest(unittest.TestCase):
    def test_events_follow_evaluations_and_stay_bounded(self):
        events = feedback_events([evaluation(t, GOOD) for t in range(0, 60, 2)])
        self.assertEqual(len(events), 30)
        for event in events:
            self.assertTrue(event.audible)
            self.assertEqual(event.gate_reasons, ())
            self.assertLessEqual(event.parameters["level"], 0.5)
            self.assertLessEqual(event.parameters["intensity"], 1.0)
            self.assertGreaterEqual(event.parameters["breath_period_s"], 6.0)
            self.assertLessEqual(event.parameters["breath_period_s"], 15.0)
            for key in ("hr_bpm", "scl_us", "scr_rate_per_min"):
                self.assertIn(key, event.inputs)

    def test_intensity_maps_the_arousal_index_without_inventing_scale(self):
        calm = feedback_events([evaluation(0, {**GOOD, "arousal_index": 0.0})])[0]
        raised = feedback_events([evaluation(0, {**GOOD, "arousal_index": 2.0})])[0]
        self.assertEqual(calm.parameters["intensity"], 0.0)
        self.assertEqual(raised.parameters["intensity"], 1.0)
        self.assertGreater(raised.parameters["level"], calm.parameters["level"])

    def test_quality_gate_mutes_the_event_and_names_the_reason(self):
        events = feedback_events([evaluation(0, GOOD), evaluation(2, GOOD, gate=("MOTION_EXCESSIVE",)),
                                 evaluation(4, GOOD, gate=("EDA_CONTACT_LOST",))])
        self.assertTrue(events[0].audible)
        for event in events[1:]:
            self.assertFalse(event.audible)
            self.assertEqual(event.parameters["level"], 0.0)
            self.assertTrue(event.gate_reasons)
            # The parameters hold; they are not fabricated from bad evidence.
            self.assertEqual(event.parameters["intensity"], events[0].parameters["intensity"])
            self.assertEqual(event.parameters["breath_period_s"], events[0].parameters["breath_period_s"])

    def test_missing_features_are_reasons_not_zeros(self):
        partial = {"hr_bpm": 70.0}  # no scl_us, scr_rate_per_min
        events = feedback_events([evaluation(0, GOOD), evaluation(2, partial)])
        self.assertFalse(events[1].audible)
        self.assertEqual(events[1].parameters["level"], 0.0)
        self.assertIn("FEATURE_MISSING:scl_us", events[1].gate_reasons)
        self.assertIn("FEATURE_MISSING:scr_rate_per_min", events[1].gate_reasons)

    def test_determinism_and_round_trip(self):
        inputs = [evaluation(t, {**GOOD, "arousal_index": 0.1 * (t % 7)}) for t in range(0, 60, 3)]
        first = feedback_events(inputs)
        second = feedback_events(inputs)
        self.assertEqual([e.comparable() for e in first], [e.comparable() for e in second])
        self.assertEqual(events_digest(first), events_digest(second))
        rebuilt = events_from_documents([e.to_dict() for e in first])
        self.assertEqual(events_digest(rebuilt), events_digest(first))

    def test_respiration_period_uses_only_causal_windows(self):
        windows = [{"device_time_start_us": 0, "device_time_end_us": 30_000_000, "payload": {"resp_rate_bpm": 7.5}},
                   {"device_time_start_us": 30_000_000, "device_time_end_us": 60_000_000, "payload": {"resp_rate_bpm": 30.0}}]
        ev = evaluation(35, GOOD)
        ev.window_end_us = 35_000_000 - 1_000_000  # cutoff at 34 s: only the first window is causal
        events = feedback_events([ev], windows)
        self.assertEqual(events[0].parameters["breath_period_s"], 8.0)  # 60/7.5, not 60/30 clamped

    def test_guided_breathing_falls_back_safely(self):
        events = feedback_events([evaluation(0, GOOD)])  # no windows at all
        self.assertEqual(events[0].parameters["breath_period_s"], 10.0)

    def test_version_is_recorded(self):
        self.assertIsInstance(FEEDBACK_VERSION, str)
        self.assertRegex(FEEDBACK_VERSION, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
