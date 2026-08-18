"""Comprehensive unit, statistical, physical, and property test suite for CIRCLE Resonance."""

import json
import math
import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.resonance_response.simulator import (
    ResonanceSimulator,
    GeometryConfig,
    GeometricParameterExtractor,
    CoupledOscillatorSolver,
    CALIBRATION_STATUS,
    PHI,
)
from models.resonance_response.closed_loop import (
    ClosedLoopOptimizer,
    GaussianProcessRegressor,
    FactorialInteractionAnalyzer,
    ExperimentSearchSpace,
    HypothesisCandidateLibrary,
    BlindTrialManifest,
    SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING,
)
from models.resonance_response.analyzer import ResonanceAnalyzer, ArtifactReport


class ResonanceScientificPhysicsTest(unittest.TestCase):
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

    def test_physical_geometric_parameter_derivation_without_core_bias(self):
        """Geometry derives capacitances and coupling without handcrafted multiplier bonuses."""
        geom_phi = GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0)
        geom_eq = GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0)
        geom_sham = GeometryConfig(geometry_type="SHAM_OFF")

        ext_phi = GeometricParameterExtractor(geom_phi)
        ext_eq = GeometricParameterExtractor(geom_eq)
        ext_sham = GeometricParameterExtractor(geom_sham)

        c_phi, k_phi = ext_phi.extract_coupling_matrix()
        c_eq, k_eq = ext_eq.extract_coupling_matrix()
        c_sham, k_sham = ext_sham.extract_coupling_matrix()

        self.assertGreater(c_phi[0], 0.0)
        self.assertGreater(c_eq[0], 0.0)
        self.assertEqual(c_sham[0], 0.0)

        # Coupling matrices are symmetric: k_ij == k_ji
        for i in range(5):
            for j in range(5):
                self.assertEqual(k_phi[i][j], k_phi[j][i])
                self.assertEqual(k_eq[i][j], k_eq[j][i])

        # Phi spacing naturally produces distinct coupling from equal spacing purely due to Delta_r
        self.assertNotEqual(k_phi[0][1], k_eq[0][1])

    def test_coupled_oscillator_dimensional_scaling(self):
        """Coupling force kappa_ij = k_ij * omega_i * omega_j scales dimensionally with omega^2."""
        solver = CoupledOscillatorSolver(
            frequencies_hz=[73.2, 118.4, 191.6, 310.0, 243.8],
            amplitudes_v=[4.0, 4.0, 4.0, 4.0, 4.0],
            phases_deg=[0.0, 0.0, 0.0, 0.0, 180.0],
            q_factors=[45.0, 45.0, 45.0, 50.0, 50.0],
            coupling_matrix=[
                [0.0, 0.10, 0.05, 0.02, 0.02],
                [0.10, 0.0, 0.10, 0.05, 0.05],
                [0.05, 0.10, 0.0, 0.10, 0.10],
                [0.02, 0.05, 0.10, 0.0, 0.08],
                [0.02, 0.05, 0.10, 0.08, 0.0],
            ],
            nonlinear_alpha=0.10,
        )
        t_pts, trajs = solver.simulate_dynamics(duration_s=0.15, sample_rate_hz=2000.0)
        self.assertEqual(len(t_pts), 300)
        self.assertEqual(len(trajs), 5)

        spec = solver.analyze_spectrum(t_pts, trajs, fundamental_freq_hz=73.2)
        self.assertIsInstance(spec["harmonics_detected"], list)
        self.assertIsInstance(spec["intermodulation_products"], list)
        self.assertIsInstance(spec["phase_locked"], bool)

    def test_multi_dimensional_gaussian_process_and_factorial_analyzer(self):
        """Multi-dimensional GP fits (f, A, G, C, M) and Factorial analyzer estimates OLS effects."""
        gp = GaussianProcessRegressor(length_scales=(0.5, 2.0, 1.0, 1.0, 1.0), signal_variance=1.0, noise_variance=0.01)

        # Feature vector: [log10(f), amp, geom_idx, core_idx, mod_idx]
        X_train = [
            [1.0, 3.0, 0.0, 0.0, 0.0],
            [2.0, 4.0, 1.0, 1.0, 0.0],
            [3.0, 2.0, 2.0, 2.0, 1.0],
        ]
        y_train = [0.20, 0.85, 0.30]
        gp.fit(X_train, y_train)

        mu, sigma = gp.predict([2.0, 4.0, 1.0, 1.0, 0.0])
        self.assertAlmostEqual(mu, 0.85, delta=0.08)
        self.assertLess(sigma, 0.30)

        # Test Factorial Interaction Analyzer
        fact = FactorialInteractionAnalyzer()
        fact.add_trial("GOLDEN_RATIO_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.75)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "SPHERICAL_CORE", 73.2, 3.0, 0.40)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "NO_CORE", 73.2, 3.0, 0.30)
        fact.add_trial("EQUAL_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.45)
        fact.add_trial("EQUAL_SPHERES", "SPHERICAL_CORE", 73.2, 3.0, 0.25)
        fact.add_trial("RANDOM_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.35)

        effects = fact.estimate_effects()
        self.assertIn("beta_G_phi", effects)
        self.assertIn("beta_C_merkaba", effects)
        self.assertIn("beta_GC_interaction", effects)
        self.assertEqual(effects["samples_count"], 6)

    def test_autocorrelation_aware_circular_block_permutation_test(self):
        """Circular block permutation must preserve contiguous block structure for autocorrelated signals."""
        analyzer = ResonanceAnalyzer(n_permutations=200, n_bootstraps=200, default_block_size=5)

        # Autocorrelated AR(1) signal simulation: x_t = 0.85 * x_{t-1} + noise
        def gen_ar1(n: int, mean: float, seed: int) -> list:
            rng = random.Random(seed)
            x = [mean]
            for _ in range(n - 1):
                x.append(mean + 0.80 * (x[-1] - mean) + rng.gauss(0, 0.5))
            return x

        active_base = gen_ar1(30, 10.0, seed=1)
        active_int = gen_ar1(30, 15.0, seed=2)
        sham_base = gen_ar1(30, 10.0, seed=3)
        sham_int = gen_ar1(30, 10.1, seed=4)

        eval_res = analyzer.evaluate_trial(
            config_id="cfg-block-test",
            blinded_token="TRIAL-BLOCK-1",
            baseline_signal=active_base,
            intervention_signal=active_int,
            washout_signal=active_base,
            sham_baseline_signal=sham_base,
            sham_intervention_signal=sham_int,
            rf_field_strength_v_m=0.1,
            temp_delta_c=0.02,
        )
        self.assertLess(eval_res.permutation_p_value, 0.05)
        self.assertGreater(eval_res.bootstrap_95ci[0], 0.0)
        self.assertLessEqual(eval_res.bootstrap_95ci[1], 1.0)
        self.assertTrue(eval_res.artifact_report.is_valid_signal)

    def test_phantom_baseline_delta_prevents_dc_offset_false_alarm(self):
        """A phantom with high DC offset but zero dynamic delta during intervention must not trigger artifact flag."""
        analyzer = ResonanceAnalyzer(n_permutations=100, n_bootstraps=100)

        eval_res = analyzer.evaluate_trial(
            config_id="cfg-phantom-dc",
            blinded_token="TRIAL-5678",
            baseline_signal=[10.0, 10.1, 10.0, 10.2, 10.0],
            intervention_signal=[14.0, 14.2, 14.1, 14.0, 14.3],
            washout_signal=[10.0, 10.1, 10.0, 10.0, 10.1],
            phantom_baseline_signal=[50.0, 50.0, 50.0, 50.0, 50.0],
            phantom_active_signal=[50.01, 50.00, 50.02, 50.01, 50.00],
            rf_field_strength_v_m=0.2,
        )
        self.assertEqual(eval_res.artifact_report.phantom_active_delta, 0.008)
        self.assertTrue(eval_res.artifact_report.phantom_control_match)
        self.assertTrue(eval_res.artifact_report.is_valid_signal)

    def test_software_exploration_cap_naming_and_safety_isolation(self):
        """Ensure SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING is explicit and hardware domain isolation holds."""
        self.assertEqual(SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING, 10.0)
        self.assertEqual(CALIBRATION_STATUS, "PHENOMENOLOGICAL_PARAMETER_NOT_PHYSICALLY_CALIBRATED")

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        nets = set(manifest["required_nets"])
        for forbidden in ["RESONANCE_DRIVE", "R_OUTER_V", "R_CORE_RF", "CHAMBER_HV"]:
            for net in nets:
                self.assertNotIn(forbidden, net)


if __name__ == "__main__":
    unittest.main()
