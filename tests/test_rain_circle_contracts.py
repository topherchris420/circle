import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CIRCLE_PROVENANCE = ["RAW_MEASURED", "DERIVED", "MODEL_INFERRED", "SIMULATED", "TEST", "INTERVENTION"]


class RainCircleContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest_schema = json.loads(
            (ROOT / "contracts/rain-circle/experiment-manifest.schema.json").read_text(encoding="utf-8")
        )
        cls.result_schema = json.loads(
            (ROOT / "contracts/rain-circle/experiment-result.schema.json").read_text(encoding="utf-8")
        )
        cls.analysis_schema = json.loads(
            (ROOT / "contracts/rain-circle/experiment-analysis.schema.json").read_text(encoding="utf-8")
        )
        cls.intervention_schema = json.loads(
            (ROOT / "contracts/resonance-intervention.schema.json").read_text(encoding="utf-8")
        )
        cls.session_schema = json.loads(
            (ROOT / "contracts/session-record.schema.json").read_text(encoding="utf-8")
        )

    def test_schemas_use_draft_2020_12(self):
        expected = "https://json-schema.org/draft/2020-12/schema"
        self.assertEqual(self.manifest_schema["$schema"], expected)
        self.assertEqual(self.result_schema["$schema"], expected)
        self.assertEqual(self.analysis_schema["$schema"], expected)
        self.assertEqual(self.intervention_schema["$schema"], expected)

    def test_provenance_reuses_circle_vocabulary(self):
        session_provenance = self.session_schema["$defs"]["provenance"]["enum"]
        self.assertEqual(session_provenance, CIRCLE_PROVENANCE)

        # Manifest provenance requirements
        manifest_provenance = self.manifest_schema["properties"]["provenance_requirements"]["items"]["enum"]
        self.assertEqual(manifest_provenance, CIRCLE_PROVENANCE)

        # Result provenance
        result_provenance = self.result_schema["properties"]["provenance"]["enum"]
        self.assertEqual(result_provenance, CIRCLE_PROVENANCE)

        # Analysis provenance
        analysis_provenance = self.analysis_schema["properties"]["provenance"]["enum"]
        self.assertEqual(analysis_provenance, CIRCLE_PROVENANCE)

        # Intervention provenance
        intervention_provenance = self.intervention_schema["$defs"]["provenance"]["enum"]
        self.assertEqual(intervention_provenance, CIRCLE_PROVENANCE)

    def test_manifest_schema_requires_preregistration_fields(self):
        required = self.manifest_schema["required"]
        self.assertIn("protocol_version", required)
        self.assertIn("experiment_id", required)
        self.assertIn("trial_id", required)
        self.assertIn("research_question", required)
        self.assertIn("hypothesis", required)
        self.assertIn("null_hypothesis", required)
        self.assertIn("alternative_hypothesis", required)
        self.assertIn("control_conditions", required)
        self.assertIn("preregistered_analysis", required)
        self.assertIn("requires_human_review", required)
        self.assertFalse(self.manifest_schema["additionalProperties"])

    def test_analysis_schema_enforces_tri_state_conclusion(self):
        conclusion_enum = self.analysis_schema["properties"]["conclusion"]["enum"]
        self.assertEqual(conclusion_enum, ["SUPPORTS", "REFUTES", "INCONCLUSIVE"])

    def test_result_schema_supports_simulated_executor(self):
        executors = self.result_schema["properties"]["executor_type"]["enum"]
        self.assertIn("SIMULATED", executors)
        self.assertIn("manifest_sha256", self.result_schema["required"])


if __name__ == "__main__":
    unittest.main()
