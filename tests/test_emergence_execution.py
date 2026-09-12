"""Regression tests for data preservation, actual execution, and reproducibility."""

import json
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from models.emergence import engine
from models.emergence.bridge import CircleTelemetryBridge
from models.session_records import load_session
from tools.run_emergence_lab import main
from test_session_records import snapshot


class TelemetryReplayTest(unittest.TestCase):
    def test_nondefault_dataframe_index_and_measured_control_are_preserved(self):
        source = pd.DataFrame({"ppg_red": [1., 2., 3.], "control_baseline": [10., 20., 30.]}, index=[10, 11, 12])
        target = CircleTelemetryBridge(field_res=4).from_dataframe(source)
        np.testing.assert_array_equal(target.raw_values.optical_ir, source.ppg_red)
        np.testing.assert_array_equal(target.raw_values.control_baseline, source.control_baseline)
        self.assertFalse(target.generated_control)

    def test_channel_choice_is_explicit_stable_and_raw_columns_retained(self):
        source = pd.DataFrame({"ppg_red": [1., 2.], "ppg_ir": [8., 9.]})
        bridge = CircleTelemetryBridge(field_res=4)
        first = bridge.from_dataframe(source)
        second = bridge.from_dataframe(source[source.columns[::-1]])
        np.testing.assert_array_equal(first.fields, second.fields)
        self.assertEqual(first.channel_sources, {"optical_ir": "ppg_red"})
        self.assertIn("ppg_ir", first.input_values)
        selected = CircleTelemetryBridge(field_res=4, channel_sources={"optical_ir": "ppg_ir"}).from_dataframe(source)
        np.testing.assert_array_equal(selected.raw_values.optical_ir, [8., 9.])

    def test_bridge_seed_is_independent_of_global_random_activity(self):
        bridge = CircleTelemetryBridge(field_res=4, seed=23)
        source = pd.DataFrame({"ppg_red": [1., 2., 5.]})
        first = bridge.from_dataframe(source)
        engine.set_seed(911)
        engine.rng.normal(size=1000)
        second = bridge.from_dataframe(source)
        np.testing.assert_array_equal(first.fields, second.fields)
        self.assertTrue(first.generated_control)

    def test_configured_sampling_rate_is_used(self):
        target = CircleTelemetryBridge(field_res=4, default_freq_hz=100).from_dataframe(pd.DataFrame({"ppg_red": [1., 2., 3.]}))
        self.assertEqual((target.timestamps.iloc[1] - target.timestamps.iloc[0]).value, 10_000_000)

    def test_bad_samples_are_not_silently_replaced_with_zero(self):
        for values in ([1., np.nan], [1., np.inf], [1., "bad"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                CircleTelemetryBridge(field_res=4).from_dataframe(pd.DataFrame({"ppg_red": values}))

    def test_invalid_timing_and_empty_or_unknown_data_fail(self):
        for frame in (pd.DataFrame(), pd.DataFrame({"unknown": [1]}),
                      pd.DataFrame({"ppg_red": [1, 2], "device_time_us": [20, 10]}),
                      pd.DataFrame({"ppg_red": [1, 2], "timestamp": ["2026-01-01", "bad"]}),
                      pd.DataFrame({"ppg_red": [1, 2], "timestamp": [None, None]})):
            with self.subTest(frame=str(frame)), self.assertRaises((ValueError, TypeError)):
                CircleTelemetryBridge(field_res=4).from_dataframe(frame)

    def test_record_replay_validates_crc_and_aligns_streams(self):
        records = [snapshot(i, 100 + i * 20, "PPG") for i in range(3)]
        records += [snapshot(i, 100 + i * 20, "EDA", {"eda_raw": float(i)}) for i in range(3)]
        target = CircleTelemetryBridge(field_res=4).from_records(records)
        self.assertEqual(target.frame_count, 3)
        np.testing.assert_array_equal(target.raw_values.consciousness_proxy, [0., 1., 2.])
        records[0]["payload"]["ppg_red"] = 5
        with self.assertRaisesRegex(ValueError, "CRC-32C mismatch"):
            CircleTelemetryBridge(field_res=4).from_records(records)

    def test_empty_session_never_creates_fake_samples(self):
        with self.assertRaises(ValueError):
            CircleTelemetryBridge(field_res=4).from_records([])


class EmergenceExecutionTest(unittest.TestCase):
    def test_runs_are_seeded_and_animation_redraw_does_not_change_metrics(self):
        config = engine.SimulationConfig(FIELD_RES=8, AGENTS=3, FRAMES=12, MEMORY=8, CORR_WINDOW=5)
        first = engine.run_simulation(config=config, render=False)
        engine.set_seed(321)
        second = engine.run_simulation(config=config, render=False)
        self.assertEqual(first.metrics.discovery_rate_history, second.metrics.discovery_rate_history)
        self.assertEqual(len(first.metrics.discovery_rate_history), 12)
        rendered = engine.run_simulation(config=config)
        self.assertEqual(first.metrics.discovery_rate_history, rendered.metrics.discovery_rate_history)
        before = list(rendered.metrics.discovery_rate_history)
        rendered.animation._func(0)
        rendered.animation._func(0)
        rendered.animation._func(11)
        self.assertEqual(before, rendered.metrics.discovery_rate_history)
        import matplotlib.pyplot as plt
        rendered.animation._draw_was_started = True
        plt.close(rendered.animation._fig)

    def test_headless_cli_reports_actual_arguments_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run.html"
            record = Path(temporary) / "record.json"
            args = ["--headless", "--quick", "--frames", "7", "--agents", "3", "--field-res", "8", "--seed", "123",
                    "--output", str(output), "--export-session-records", str(record)]
            self.assertEqual(main(args), 0)
            first = output.with_suffix('.metrics.json').read_bytes()
            self.assertEqual(main(args), 0)
            self.assertEqual(first, output.with_suffix('.metrics.json').read_bytes())
            summary = json.loads(first)
            self.assertEqual((summary['frames'], summary['agents'], summary['field_res'], summary['seed']), (7, 3, 8, 123))
            self.assertEqual(len(summary['discovery_rate_history']), 7)
            exported = load_session(record)[0]
            self.assertEqual(exported['model']['artifact_id'], 'sha256:' + hashlib.sha256(first).hexdigest())
            self.assertEqual(exported['source_sequence_ranges'][0]['last_sequence'], 6)
            self.assertEqual(exported['device_time_end_us'], 120_000)
            self.assertIn('SIMULATED_INPUT', exported['status_flags'])
            self.assertFalse(output.exists())

    def test_replay_export_preserves_native_time_and_used_sequence_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'input.json'
            source.write_text(json.dumps([snapshot(100+i, 5_000_000+i*10_000) for i in range(5)]))
            destination = root / 'record.json'
            self.assertEqual(main(['--headless', '--circle-session', str(source), '--frames', '3', '--agents', '2', '--field-res', '4',
                                   '--output', str(root/'run.html'), '--export-session-records', str(destination)]), 0)
            record = load_session(destination)[0]
            self.assertEqual((record['device_time_start_us'], record['device_time_end_us']), (5_000_000, 5_020_000))
            self.assertEqual(record['source_stream_ids'], ['SENSOR'])
            self.assertEqual(record['source_sequence_ranges'][0], {'stream_id':'SENSOR','first_sequence':100,'last_sequence':102})
            self.assertIn('TEST_INPUT', record['status_flags'])
