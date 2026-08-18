"""Comprehensive unit, statistical, and property test suite for CIRCLE Resonance."""

import json
import math
import pathlib
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
    PHI,
)
from models.resonance_response.closed_loop import (
    ClosedLoopOptimizer,
    GaussianProcessRegressor,
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

    def test_physical_geometric_parameter_derivation(self):
        """Geometry must derive electrostatic capacitance and coupling matrix G -> {C, k}."""
        geom_phi = GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0)
        geom_eq = GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0)
        geom_rnd = GeometryConfig(geometry_type="RANDOM_SPHERES", outer_diameter_mm=300.0)
        geom_sham = GeometryConfig(geometry_type="SHAM_OFF")

        ext_phi = GeometricParameterExtractor(geom_phi)
        ext_eq = GeometricParameterExtractor(geom_eq)
        ext_rnd = GeometricParameterExtractor(geom_rnd)
        ext_sham = GeometricParameterExtractor(geom_sham)

        c_phi, k_phi = ext_phi.extract_coupling_matrix()
        c_eq, k_eq = ext_eq.extract_coupling_matrix()
        c_rnd, k_rnd = ext_rnd.extract_coupling_matrix()
        c_sham, k_sham = ext_sham.extract_coupling_matrix()

        # All non-zero active geometries derive physical capacitances
        self.assertGreater(c_phi[0], 0.0)
        self.assertGreater(c_eq[0], 0.0)
        self.assertEqual(c_sham[0], 0.0)

        # Coupling matrices are symmetric: k_ij == k_ji
        for k_mat in [k_phi, k_eq, k_rnd]:
            for i in range(5):
                for j in range(5):
                    self.assertEqual(k_mat[i][j], k_mat[j][i])

        # Phi spacing naturally has different coupling than equal spacing due to different Delta_r
        self.assertNotEqual(k_phi[0][1], k_eq[0][1])

    def test_exact_gaussian_process_regressor_equations(self):
        """Exact Gaussian Process must fit data and yield rigorous mean and variance."""
        gp = GaussianProcessRegressor(length_scales=(0.5, 2.0), signal_variance=1.0, noise_variance=0.01)

        # Train on synthetic points: (log10(f), amp) -> response
        X_train = [(1.0, 3.0), (2.0, 4.0), (3.0, 2.0)]
        y_train = [0.20, 0.85, 0.30]
        gp.fit(X_train, y_train)

        # At training point (2.0, 4.0), predictive mean should be close to 0.85 and uncertainty should be low
        mu_train, sigma_train = gp.predict((2.0, 4.0))
        self.assertAlmostEqual(mu_train, 0.85, delta=0.08)
        self.assertLess(sigma_train, 0.30)

        # Far away from training points (e.g. log_f = 5.0, amp = 10.0), uncertainty should approach prior (1.0)
        mu_far, sigma_far = gp.predict((5.0, 10.0))
        self.assertAlmostEqual(mu_far, 0.0, delta=0.15)
        self.assertGreater(sigma_far, 0.85)

    def test_permutation_test_with_unequal_group_sizes(self):
        """Verifies that permutation test correctly normalizes when group sizes differ (n_a != n_b)."""
        analyzer = ResonanceAnalyzer(n_permutations=200)

        # Group A (n=4): [10, 10, 10, 10], Group B (n=8): [20, 20, 20, 20, 20, 20, 20, 20]
        p_val = analyzer._permutation_test_double_difference(
            active_base=[10.0, 10.0, 10.0, 10.0],
            active_int=[20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0],
        )
        self.assertLess(p_val, 0.05)

    def test_aligned_double_difference_sham_subtraction(self):
        """Analyzer must compute aligned double-difference contrast, permutation p-value, and bootstrap CI."""
        analyzer = ResonanceAnalyzer(n_permutations=200, n_bootstraps=200)

        eval_res = analyzer.evaluate_trial(
            config_id="cfg-sham-aligned",
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

        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        nets = set(manifest["required_nets"])
        for forbidden in ["RESONANCE_DRIVE", "R_OUTER_V", "R_CORE_RF", "CHAMBER_HV"]:
            for net in nets:
                self.assertNotIn(forbidden, net)


if __name__ == "__main__":
    unittest.main()
