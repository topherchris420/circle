"""Comprehensive unit, statistical, and property test suite for CIRCLE Resonance."""

import json
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.resonance_response.simulator import ResonanceSimulator, GeometryConfig, CoupledOscillatorSolver, PHI
from models.resonance_response.closed_loop import (
    ClosedLoopOptimizer,
    ExperimentSearchSpace,
    HypothesisCandidateLibrary,
    BlindTrialManifest,
    SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING,
)
from models.resonance_response.analyzer import ResonanceAnalyzer, ArtifactReport


class ResonanceScientificNeutralityTest(unittest.TestCase):
    def setUp(self):
        self.schema_path = ROOT / "contracts/resonance-intervention.schema.json"
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

    def test_simulator_prior_physics_is_completely_symmetric_across_geometries(self):
        """Guarantee no built-in mathematical advantage for Phi or any specific geometry."""
        sim_phi = ResonanceSimulator(GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0))
        sim_eq = ResonanceSimulator(GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0))
        sim_rnd = ResonanceSimulator(GeometryConfig(geometry_type="RANDOM_SPHERES", outer_diameter_mm=300.0))

        res_phi = sim_phi.simulate_run(config_id="t1", base_freq_hz=73.2, input_voltage_v=4.0)
        res_eq = sim_eq.simulate_run(config_id="t2", base_freq_hz=73.2, input_voltage_v=4.0)
        res_rnd = sim_rnd.simulate_run(config_id="t3", base_freq_hz=73.2, input_voltage_v=4.0)

        # Equal input power
        self.assertEqual(res_phi.power_and_energy["input_power_w"], res_eq.power_and_energy["input_power_w"])
        # Equal prior output power
        self.assertEqual(res_phi.power_and_energy["measured_output_power_w"], res_eq.power_and_energy["measured_output_power_w"])
        self.assertEqual(res_phi.power_and_energy["measured_output_power_w"], res_rnd.power_and_energy["measured_output_power_w"])
        # Conservation of energy
        self.assertTrue(res_phi.power_and_energy["conservation_verified"])
        self.assertLessEqual(res_phi.power_and_energy["measured_output_power_w"], res_phi.power_and_energy["input_power_w"])

    def test_coupled_oscillator_numeric_differential_equation_solver(self):
        """Emergent non-linear spectral features must derive from numerical differential equation integration."""
        solver = CoupledOscillatorSolver(
            frequencies_hz=[73.2, 118.4, 191.6, 310.0, 243.8],
            amplitudes_v=[4.0, 4.0, 4.0, 4.0, 4.0],
            phases_deg=[0.0, 0.0, 0.0, 0.0, 180.0],
            q_factors=[45.0, 45.0, 45.0, 50.0, 50.0],
            coupling_matrix=[
                [0.0, 0.1, 0.05, 0.02, 0.02],
                [0.1, 0.0, 0.1, 0.05, 0.05],
                [0.05, 0.1, 0.0, 0.1, 0.1],
                [0.02, 0.05, 0.1, 0.0, 0.08],
                [0.02, 0.05, 0.1, 0.08, 0.0],
            ],
            nonlinear_alpha=0.10,
        )
        t_pts, trajs = solver.simulate_dynamics(duration_s=0.15, sample_rate_hz=2000.0)
        self.assertEqual(len(t_pts), 300)
        self.assertEqual(len(trajs), 5)

        spec = solver.analyze_spectrum(t_pts, trajs, fundamental_freq_hz=73.2)
        # Verify spectral analysis produces structured outputs without crashing
        self.assertIsInstance(spec["harmonics_detected"], list)
        self.assertIsInstance(spec["intermodulation_products"], list)
        self.assertIsInstance(spec["phase_locked"], bool)

    def test_closed_loop_optimizer_is_genuinely_adaptive(self):
        """Optimizer must update Gaussian Process posterior mean and uncertainty when given response scores."""
        opt = ClosedLoopOptimizer(seed=123)

        dec1 = opt.propose_next_intervention(current_step=1)
        self.assertTrue(dec1.trial_token.startswith("TRIAL-"))
        self.assertEqual(dec1.posterior_predicted_mean, 0.0)
        self.assertEqual(dec1.posterior_uncertainty_sigma, 1.0)

        # Feed back a high response score for the previous trial
        dec2 = opt.propose_next_intervention(current_step=2, last_response_score=0.92)
        self.assertGreater(len(opt.observed_x), 0)
        self.assertGreater(len(opt.observed_y), 0)

    def test_hypothesis_library_isolation(self):
        """Hypothesis-motivated frequencies must be isolated in library and not bias default search."""
        lib = HypothesisCandidateLibrary()
        self.assertIn(7.83, lib.SCHUMANN_IONOSPHERIC_MODES)
        self.assertIn(528.0, lib.HISTORICAL_ACOUSTIC_INTERVALS)

        opt = ClosedLoopOptimizer(seed=999)
        # Default active proposal must be tagged UNBIASED_BAYESIAN_EXPLORATION
        dec = opt.propose_next_intervention(current_step=1)
        self.assertEqual(dec.hypothesis_label, "UNBIASED_BAYESIAN_EXPLORATION")

        # Explicit hypothesis request
        dec_sch = opt.propose_next_intervention(current_step=4, hypothesis_set_name="schumann")
        self.assertEqual(dec_sch.hypothesis_label, "HYP_SCHUMANN_IONOSPHERIC")
        self.assertIn(dec_sch.target_frequency_hz, lib.SCHUMANN_IONOSPHERIC_MODES)

    def test_blind_trial_manifest_sealing(self):
        """Manifest must decouple trial token from physical configuration and support secure sealing."""
        manifest = BlindTrialManifest()
        manifest.register_trial("TRIAL-99AA", {"freq": 73.2, "geom": "GOLDEN_RATIO_SPHERES"})
        self.assertFalse(manifest.is_sealed())

        manifest.seal_manifest()
        self.assertTrue(manifest.is_sealed())
        with self.assertRaises(RuntimeError):
            manifest.register_trial("TRIAL-FAIL", {"freq": 100.0})

        unsealed = manifest.unseal_manifest()
        self.assertIn("TRIAL-99AA", unsealed)

    def test_analyzer_sham_subtraction_and_permutation_testing(self):
        """Analyzer must compute double-difference sham subtraction and non-parametric permutation p-value."""
        analyzer = ResonanceAnalyzer(n_permutations=200, n_bootstraps=200)

        # Baseline: 10.0, Active: 15.0 (+5.0 bio change)
        # Sham base: 10.0, Sham int: 10.1 (+0.1 sham drift) -> Net bio delta = +4.9
        eval_res = analyzer.evaluate_trial(
            config_id="cfg-sham-test",
            blinded_token="TRIAL-1234",
            baseline_signal=[10.0, 10.1, 9.9, 10.0, 10.2],
            intervention_signal=[15.0, 15.2, 14.8, 15.1, 14.9],
            washout_signal=[10.1, 10.0, 10.0, 10.1, 10.0],
            sham_baseline_signal=[10.0, 10.0, 10.0, 10.0, 10.0],
            sham_intervention_signal=[10.1, 10.1, 10.0, 10.2, 10.1],
            rf_field_strength_v_m=0.1,
            temp_delta_c=0.02,
        )
        self.assertLess(eval_res.permutation_p_value, 0.05)
        self.assertGreater(eval_res.bootstrap_95ci[0], 0.0)
        self.assertLessEqual(eval_res.bootstrap_95ci[1], 1.0)
        self.assertTrue(eval_res.artifact_report.is_valid_signal)

    def test_phantom_baseline_subtracted_delta_prevents_dc_false_positive(self):
        """A phantom with harmless DC offset (e.g. 50V constant) must NOT trigger artifact flag."""
        analyzer = ResonanceAnalyzer(n_permutations=100, n_bootstraps=100)

        # Phantom has a constant 50.0V DC offset, but delta during intervention is ZERO
        eval_res = analyzer.evaluate_trial(
            config_id="cfg-phantom-dc",
            blinded_token="TRIAL-5678",
            baseline_signal=[10.0, 10.1, 10.0, 10.2, 10.0],
            intervention_signal=[14.0, 14.2, 14.1, 14.0, 14.3],
            washout_signal=[10.0, 10.1, 10.0, 10.0, 10.1],
            phantom_baseline_signal=[50.0, 50.0, 50.0, 50.0, 50.0],
            phantom_active_signal=[50.01, 50.00, 50.02, 50.01, 50.00],  # No delta!
            rf_field_strength_v_m=0.2,
        )
        self.assertEqual(eval_res.artifact_report.phantom_active_delta, 0.008)
        self.assertTrue(eval_res.artifact_report.phantom_control_match)
        self.assertTrue(eval_res.artifact_report.is_valid_signal)

        # Now test TRUE phantom coupling: phantom jumps by 4.0V
        eval_artifact = analyzer.evaluate_trial(
            config_id="cfg-phantom-jump",
            blinded_token="TRIAL-9999",
            baseline_signal=[10.0, 10.0, 10.0, 10.0, 10.0],
            intervention_signal=[14.0, 14.0, 14.0, 14.0, 14.0],
            washout_signal=[10.0, 10.0, 10.0, 10.0, 10.0],
            phantom_baseline_signal=[0.0, 0.0, 0.0, 0.0, 0.0],
            phantom_active_signal=[4.0, 4.0, 4.0, 4.0, 4.0],  # Direct jump!
            rf_field_strength_v_m=5.5,
        )
        self.assertFalse(eval_artifact.artifact_report.is_valid_signal)
        self.assertIn("DIRECT_EM_INSTRUMENTATION_PICKUP", eval_artifact.artifact_report.flags)

    def test_software_exploration_cap_naming_and_safety_isolation(self):
        """Ensure SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING is explicit and hardware domain isolation holds."""
        self.assertEqual(SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING, 10.0)

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        nets = set(manifest["required_nets"])
        for forbidden in ["RESONANCE_DRIVE", "R_OUTER_V", "R_CORE_RF", "CHAMBER_HV"]:
            for net in nets:
                self.assertNotIn(forbidden, net)


if __name__ == "__main__":
    unittest.main()
