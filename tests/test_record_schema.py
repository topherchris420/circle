import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED = ["RAW_MEASURED", "DERIVED", "MODEL_INFERRED", "SIMULATED", "TEST", "INTERVENTION"]
RECORD_TYPES = [
    "SESSION_HEADER",
    "STREAM_DESCRIPTOR",
    "SAMPLE_CHUNK",
    "EVENT",
    "CLOCK_MAPPING",
    "CONFIG_CHANGE",
    "GAP",
    "FAULT",
    "MODEL_RESULT",
    "INTERVENTION",
    "SESSION_TRAILER",
]
ROOT_REQUIRED = [
    "schema_version",
    "record_type",
    "provenance",
    "device_time_start_us",
    "device_time_end_us",
    "status_flags",
    "crc32c",
]


class RecordSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "contracts/session-record.schema.json").read_text(encoding="utf-8"))

    def test_provenance_enum_is_exact(self):
        self.assertEqual(self.schema["$defs"]["provenance"]["enum"], ALLOWED)

    def test_record_type_enum_is_exact(self):
        self.assertEqual(self.schema["$defs"]["recordType"]["enum"], RECORD_TYPES)

    def test_provenance_is_required(self):
        self.assertIn("provenance", self.schema["required"])

    def test_root_contract_is_closed_and_requires_expected_fields(self):
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(self.schema["required"], ROOT_REQUIRED)

    def test_model_records_require_lineage(self):
        rule = next(
            rule for rule in self.schema["allOf"]
            if rule["if"]["properties"].get("provenance", {}).get("const") == "MODEL_INFERRED"
        )
        self.assertEqual(
            set(rule["then"]["required"]),
            {"source_stream_ids", "source_sequence_ranges", "model"},
        )

    def test_interventions_require_evidence(self):
        rule = next(
            rule for rule in self.schema["allOf"]
            if rule["if"]["properties"].get("provenance", {}).get("const") == "INTERVENTION"
        )
        self.assertEqual(
            set(rule["then"]["required"]),
            {"decision_id", "actuation_evidence_ids"},
        )

    def test_gap_records_require_dropped_ranges_and_cause(self):
        rule = next(
            rule for rule in self.schema["allOf"]
            if rule["if"]["properties"].get("record_type", {}).get("const") == "GAP"
        )
        self.assertEqual(
            set(rule["then"]["required"]),
            {"dropped_first_sequence", "dropped_last_sequence", "cause"},
        )


if __name__ == "__main__":
    unittest.main()