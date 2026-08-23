"""Unit and contract tests for CIRCLE Quantum PNT integration."""

import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.pnt.bridge import (
    CirclePNTBridge,
    CirclePNTSessionRecordAdapter,
    compute_crc32c,
    PNT_STREAM_MAPPINGS,
)


class PNTContractTest(unittest.TestCase):
    def setUp(self):
        self.pnt_schema_path = ROOT / "contracts/quantum-pnt.schema.json"
        self.session_schema_path = ROOT / "contracts/session-record.schema.json"
        self.configs_path = ROOT / "experiments/pnt/configurations.example.json"

    def test_schema_file_exists_and_parses(self):
        self.assertTrue(self.pnt_schema_path.exists())
        data = json.loads(self.pnt_schema_path.read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "Quantum PNT Experiment and Discovery Schema")
        self.assertIn("configuration", data["properties"])
        self.assertIn("metrics", data["properties"])
        self.assertIn("provenance", data["properties"])

    def test_provenance_hierarchy_alignment(self):
        pnt_schema = json.loads(self.pnt_schema_path.read_text(encoding="utf-8"))
        session_schema = json.loads(self.session_schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            pnt_schema["$defs"]["provenance"]["enum"],
            session_schema["$defs"]["provenance"]["enum"],
        )
        self.assertEqual(
            pnt_schema["$defs"]["interpretationLevel"]["enum"],
            ["MEASURED", "DERIVED", "MODEL_INFERRED", "HYPOTHESIS_LABEL"],
        )

    def test_crc32c_test_vectors(self):
        self.assertEqual(compute_crc32c("123456789"), "E3069283")
        self.assertEqual(compute_crc32c(""), "00000000")

    def test_stream_mappings_structure(self):
        self.assertIn("CIRCLE_IMU_ICM42688", PNT_STREAM_MAPPINGS)
        self.assertIn("CIRCLE_ATOM_INTERFEROMETER", PNT_STREAM_MAPPINGS)
        self.assertIn("CIRCLE_GRAVITY_GRADIOMETER", PNT_STREAM_MAPPINGS)
        self.assertIn("CIRCLE_QUANTUM_CLOCK", PNT_STREAM_MAPPINGS)

    def test_session_record_adapter_emits_valid_schema_compliant_record(self):
        rec = CirclePNTSessionRecordAdapter.create_model_result_record(
            experiment_id="EXP-QPNS-001",
            duration_s=60.0,
            dt_s=0.01,
            position_rmse_m=1.25,
            velocity_rmse_m_s=0.05,
            drift_rate_m_hr=50.0,
            device_time_start_us=1000,
        )

        session_schema = json.loads(self.session_schema_path.read_text(encoding="utf-8"))
        for req in session_schema["required"]:
            self.assertIn(req, rec)

        self.assertEqual(rec["schema_version"], "2.0.0")
        self.assertEqual(rec["record_type"], "MODEL_RESULT")
        self.assertEqual(rec["provenance"], "MODEL_INFERRED")
        self.assertIn("CALIBRATED_NAVIGATION", rec["status_flags"])
        self.assertIn("QUANTUM_AUGMENTED", rec["status_flags"])
        self.assertRegex(rec["crc32c"], r"^[0-9A-Fa-f]{8}$")

    def test_example_configurations_file_parses_and_conforms(self):
        self.assertTrue(self.configs_path.exists())
        data = json.loads(self.configs_path.read_text(encoding="utf-8"))
        self.assertIn("configurations", data)
        self.assertGreaterEqual(len(data["configurations"]), 2)
        for cfg in data["configurations"]:
            self.assertIn("experiment_id", cfg)
            self.assertIn("configuration", cfg)
            self.assertIn("metrics", cfg)
            self.assertIn("provenance", cfg)


if __name__ == "__main__":
    unittest.main()
