"""Unit and contract test suite for CIRCLE Resonance research module."""

import json
import math
import pathlib
import unittest

from models.resonance_response.simulator import ResonanceSimulator, GeometryConfig, PHI
from models.resonance_response.closed_loop import ClosedLoopOptimizer, ExperimentSearchSpace
from models.resonance_response.analyzer import ResonanceAnalyzer, ArtifactReport

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ResonanceContractTest(unittest.TestCase):
    def setUp(self):
        self.schema_path = ROOT / "contracts/resonance-intervention.schema.json"
        self.configs_path = ROOT / "experiments/resonance/configurations.example.json"
        self.manifest_path = ROOT / "hardware/design-manifest.json"

    def test_schema_file_exists_and_parses(self):
        self.assertTrue(self.schema_path.exists())
        data = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "Resonance Intervention Record and Configuration Schema")
        self.assertIn("interpretation_level", data["properties"])
        self.assertIn("power_and_energy", data["properties"])

    def test_epistemological_hierarchy_is_strictly_enforced(self):
        data = json.loads(self.schema_path.read_text(encoding="utf-8"))
        levels = data["$defs"]["interpretationLevel"]["enum"]
        self.assertEqual(levels, ["MEASURED", "DERIVED", "MODEL_INFERRED", "HYPOTHESIS_LABEL"])

    def test_provenance_levels_include_all_required_tags(self):
        data = json.loads(self.schema_path.read_text(encoding="utf-8"))
        provenance = data["$defs"]["provenance"]["enum"]
        for p in ["RAW_MEASURED", "DERIVED", "MODEL_INFERRED", "SIMULATED", "TEST", "INTERVENTION"]:
            self.assertIn(p, provenance)

    def test_safety_boundary_rejection_of_human_domain_coupling(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        nets = set(manifest["required_nets"])
        # Verify no resonance drive or chamber RF is coupled into BAT_HUMAN nets
        for forbidden in ["RESONANCE_DRIVE", "R_OUTER_V", "R_CORE_RF", "CHAMBER_HV"]:
            for net in nets:
                self.assertNotIn(forbidden, net)

    def test_parametric_geometry_phi_scaling(self):
        geom = GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0)
        outer, middle, inner = geom.compute_diameters()
        self.assertEqual(outer, 300.0)
        self.assertAlmostEqual(middle, 300.0 / PHI, places=2)
        self.assertAlmostEqual(inner, 300.0 / (PHI ** 2), places=2)

    def test_control_geometries(self):
        equal_geom = GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0)
        e_outer, e_mid, e_inn = equal_geom.compute_diameters()
        self.assertEqual(e_outer, 300.0)
        self.assertEqual(e_mid, 200.0)
        self.assertEqual(e_inn, 100.0)

        sham_geom = GeometryConfig(geometry_type="SHAM_OFF")
        self.assertEqual(sham_geom.compute_diameters(), (0.0, 0.0, 0.0))

    def test_simulator_energy_conservation_invariant(self):
        sim = ResonanceSimulator(GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0))
        result = sim.simulate_run(config_id="test-sim-01", base_freq_hz=73.2, input_voltage_v=5.0)
        pwr = result.power_and_energy
        self.assertGreater(pwr["input_power_w"], 0.0)
        self.assertLessEqual(pwr["measured_output_power_w"], pwr["input_power_w"])
        self.assertTrue(pwr["conservation_verified"])
        self.assertGreaterEqual(pwr["dissipated_thermal_power_w"], 0.0)

    def test_nonlinear_spectral_phenomena_simulation(self):
        sim = ResonanceSimulator(GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0))
        result = sim.simulate_run(config_id="test-sim-spectral", base_freq_hz=73.2)
        spec = result.spectral_features
        self.assertIn(146.4, spec["harmonics_detected"])  # 2f
        self.assertIn(219.6, spec["harmonics_detected"])  # 3f
        self.assertIn(36.6, spec["subharmonics"])         # f/2
        self.assertTrue(len(spec["intermodulation_products"]) > 0)
        self.assertTrue(spec["mode_splitting_detected"])

    def test_closed_loop_decision_generation_and_blinding(self):
        opt = ClosedLoopOptimizer(seed=42)
        dec1 = opt.propose_next_intervention(current_step=1)
        dec2 = opt.propose_next_intervention(current_step=2)
        dec3 = opt.propose_next_intervention(current_step=3)

        self.assertTrue(dec1.blinded_label.startswith("BLIND-"))
        self.assertGreaterEqual(dec1.baseline_duration_ms, 5000.0)
        self.assertGreaterEqual(dec1.washout_duration_ms, 5000.0)
        # Step 3 must enforce control condition
        self.assertTrue(dec3.is_control_condition)

    def test_analyzer_rri_and_artifact_discrimination(self):
        analyzer = ResonanceAnalyzer()

        # 1. Clean biological response without EM artifact
        clean_eval = analyzer.evaluate_trial(
            config_id="cfg-clean",
            blinded_label="BLIND-CLEAN",
            baseline_signal=[10.0, 10.2, 10.1, 10.0, 10.1],
            intervention_signal=[15.0, 15.2, 14.9, 15.1, 15.0],
            washout_signal=[10.1, 10.0, 10.2, 10.1, 10.0],
            phantom_active_signal=[0.01, 0.02, 0.00, 0.01, 0.02],
            rf_field_strength_v_m=0.2,
            temp_delta_c=0.05,
            prior_trial_scores=[0.85, 0.82],
        )
        self.assertIn(clean_eval.evidence_status, ["REPEATABLE_DIFFERENCE", "EXPLORATORY"])
        self.assertGreater(clean_eval.observed_rri, 0.5)
        self.assertTrue(clean_eval.artifact_report.is_valid_signal)

        # 2. EM Artifact case: phantom mirrors the intervention
        artifact_eval = analyzer.evaluate_trial(
            config_id="cfg-artifact",
            blinded_label="BLIND-ART",
            baseline_signal=[10.0, 10.0, 10.0, 10.0, 10.0],
            intervention_signal=[15.0, 15.0, 15.0, 15.0, 15.0],
            washout_signal=[10.0, 10.0, 10.0, 10.0, 10.0],
            phantom_active_signal=[4.8, 4.9, 5.0, 4.9, 5.1],  # Dummy load shows same 5V jump!
            rf_field_strength_v_m=8.5,
            temp_delta_c=1.2,
        )
        self.assertEqual(artifact_eval.evidence_status, "ARTIFACT_LIKELY")
        self.assertFalse(artifact_eval.artifact_report.is_valid_signal)
        self.assertIn("DIRECT_EM_INSTRUMENTATION_PICKUP", artifact_eval.artifact_report.flags)


if __name__ == "__main__":
    unittest.main()
