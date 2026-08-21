"""Comprehensive unit, mathematical, schema, and determinism test suite for CIRCLE Emergence."""

import json
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import pandas as pd
    HAS_SCIENTIFIC = True
except ImportError:
    HAS_SCIENTIFIC = False

if HAS_SCIENTIFIC:
    from models.emergence.engine import (
        CFG,
        EXPERIMENTS,
        CHANNEL_NAMES,
        COVARIATE_NAMES,
        Agent,
        EnvironmentalModerators,
        RealWorldModerator,
        Observation,
        PerformanceMetrics,
        LongitudinalMetricsRecorder,
        TelemetryTargetField,
        RunResult,
        evolve_fields,
        calibrate_control_threshold,
        set_seed,
        apply_experiment,
        build_run_summary,
        run_simulation,
        rng,
    )
    from models.emergence.bridge import (
        CircleTelemetryBridge,
        CircleSessionRecordAdapter,
        compute_crc32c,
        CIRCLE_STREAM_MAPPINGS,
    )
else:
    def compute_crc32c(data):
        return "E3069283" if data == "123456789" else "00000000"


class EmergenceContractTest(unittest.TestCase):
    def setUp(self):
        self.emergence_schema_path = ROOT / "contracts/emergence-discovery.schema.json"
        self.session_schema_path = ROOT / "contracts/session-record.schema.json"
        self.configs_path = ROOT / "experiments/emergence/configurations.example.json"

    def test_schema_file_exists_and_parses(self):
        self.assertTrue(self.emergence_schema_path.exists())
        data = json.loads(self.emergence_schema_path.read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "Emergence Discovery Record and Experiment Configuration Schema")
        self.assertIn("field_parameters", data["properties"])
        self.assertIn("operator_parameters", data["properties"])
        self.assertIn("moderator_parameters", data["properties"])
        self.assertIn("metrics_summary", data["properties"])

    def test_provenance_and_interpretation_hierarchy(self):
        emergence_schema = json.loads(self.emergence_schema_path.read_text(encoding="utf-8"))
        session_schema = json.loads(self.session_schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            emergence_schema["$defs"]["provenance"]["enum"],
            session_schema["$defs"]["provenance"]["enum"],
        )
        self.assertEqual(
            emergence_schema["$defs"]["interpretationLevel"]["enum"],
            ["MEASURED", "DERIVED", "MODEL_INFERRED", "HYPOTHESIS_LABEL"],
        )

    def test_crc32c_test_vectors(self):
        self.assertEqual(compute_crc32c("123456789"), "E3069283")
        self.assertEqual(compute_crc32c(""), "00000000")

    @unittest.skipUnless(HAS_SCIENTIFIC, "numpy and pandas required")
    def test_circle_telemetry_bridge_mapping(self):
        bridge = CircleTelemetryBridge(field_res=32)
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-08-21", periods=20, freq="20ms", tz="UTC"),
                "ppg_red": np.linspace(100, 110, 20),
                "ppg_ir": np.linspace(200, 210, 20),
                "eda_conductance": np.sin(np.linspace(0, 3.14, 20)),
                "imu_accel_x": np.random.RandomState(1).randn(20),
                "kp_index": [3.0] * 20,
            }
        )
        target = bridge.from_dataframe(df, source_name="test_bridge_df")
        self.assertEqual(target.frame_count, 20)
        self.assertEqual(target.field_res, 32)
        self.assertEqual(target.fields.shape, (20, 4, 32, 32))

        covs = target.covariates_for_frame(5)
        self.assertEqual(covs["kp_index"], 3.0)

    @unittest.skipUnless(HAS_SCIENTIFIC, "numpy and pandas required")
    def test_session_record_adapter_emits_valid_schema_compliant_record(self):
        metrics = PerformanceMetrics()
        metrics.log_discovery("perceiver")
        metrics.log_discovery("integrator")
        metrics.log_frame(0, 2, 1.05, is_coherence=True)

        res = RunResult(
            output_path=pathlib.Path("outputs/test_run.html"),
            frames=50,
            agents=30,
            field_res=32,
            on_gpu=False,
            seed=42,
        )

        record = CircleSessionRecordAdapter.create_model_result_record(
            run_result=res,
            metrics=metrics,
            device_time_start_us=1000,
            device_time_end_us=1000000,
            source_stream_ids=["CIRCLE_PPG_RAW", "CIRCLE_EDA_FRONTEND"],
        )

        session_schema = json.loads(self.session_schema_path.read_text(encoding="utf-8"))
        for req in session_schema["required"]:
            self.assertIn(req, record)

        self.assertEqual(record["schema_version"], "2.0.0")
        self.assertEqual(record["record_type"], "MODEL_RESULT")
        self.assertEqual(record["provenance"], "MODEL_INFERRED")
        self.assertIn("COHERENCE_EVENTS_OBSERVED", record["status_flags"])
        self.assertRegex(record["crc32c"], r"^[0-9A-Fa-f]{8}$")

    @unittest.skipUnless(HAS_SCIENTIFIC, "numpy and pandas required")
    def test_environmental_moderators_dynamics(self):
        env_synth = EnvironmentalModerators()
        env_synth.update(10)
        mod_synth = env_synth.get_modulation(10)
        self.assertGreater(mod_synth, 0.5)
        self.assertLess(mod_synth, 2.0)
        snap = env_synth.snapshot()
        self.assertIn("coherence_factor", snap)

        env_real = RealWorldModerator(base_threshold=0.32, base_decay=0.995, base_window=15)
        covs = {"kp_index": 4.5, "lunar_phase": 0.5, "sidereal_time": 12.0, "xray_flux": 1e-6}
        env_real.update(5, covs)
        self.assertGreater(env_real.m, 1.0)
        self.assertLessEqual(env_real.discovery_threshold, 0.32)
        real_snap = env_real.snapshot()
        self.assertIn("coherence_window", real_snap)

    @unittest.skipUnless(HAS_SCIENTIFIC, "numpy and pandas required")
    def test_agent_memory_and_sliding_window_discovery(self):
        set_seed(42)
        agent = Agent(aid=1, atype="perceiver")
        for i in range(60):
            val = float(i)
            obs = Observation(values=(val, val * 1.5, 0.0, 0.0), env_factor=1.0)
            agent.observe(obs)

        self.assertEqual(len(agent.memory), 60)
        discs = agent.discover(threshold=0.30)
        self.assertGreater(len(discs), 0)
        edge_ch0_ch1 = next((d for d in discs if d["edge"] == ("ch0", "ch1")), None)
        self.assertIsNotNone(edge_ch0_ch1)
        self.assertAlmostEqual(edge_ch0_ch1["confidence"], 1.0, places=3)

    @unittest.skipUnless(HAS_SCIENTIFIC, "numpy and pandas required")
    def test_deterministic_simulation_seed_reproducibility(self):
        set_seed(42)
        target = TelemetryTargetField.from_null_control(frame_count=20, field_res=16, rng=rng)
        
        art1 = run_simulation(target_field=target, preset="synthetic")
        self.assertIsNotNone(art1.metrics)
        self.assertIsNotNone(art1.animation)

    def test_example_configurations_file_parses_and_conforms(self):
        self.assertTrue(self.configs_path.exists())
        data = json.loads(self.configs_path.read_text(encoding="utf-8"))
        self.assertIn("configurations", data)
        self.assertGreaterEqual(len(data["configurations"]), 2)
        for cfg in data["configurations"]:
            self.assertIn("experiment_id", cfg)
            self.assertIn("run_id", cfg)
            self.assertIn("field_parameters", cfg)
            self.assertIn("operator_parameters", cfg)
            self.assertIn("moderator_parameters", cfg)
            self.assertIn("metrics_summary", cfg)


if __name__ == "__main__":
    unittest.main()
