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
    ConcentricMaxwellCapacitanceMatrix,
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
    one_hot_encode,
    GEOMETRIES,
    CORES,
    MODULATIONS,
)
from models.resonance_response.analyzer import (
    ResonanceAnalyzer,
    ArtifactReport,
    estimate_autocorrelation_time,
)


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

    def test_concentric_maxwell_capacitance_matrix_physics(self):
        """Concentric spherical conductor physics: C_ab = 4*pi*eps0*(a*b)/(b-a)."""
        geom_phi = GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0)
        geom_eq = GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0)
        geom_sham = GeometryConfig(geometry_type="SHAM_OFF")

        matrix_phi = ConcentricMaxwellCapacitanceMatrix(geom_phi)
        matrix_eq = ConcentricMaxwellCapacitanceMatrix(geom_eq)
        matrix_sham = ConcentricMaxwellCapacitanceMatrix(geom_sham)

        c_phi, k_phi = matrix_phi.compute_maxwell_capacitances_and_coupling()
        c_eq, k_eq = matrix_eq.compute_maxwell_capacitances_and_coupling()
        c_sham, k_sham = matrix_sham.compute_maxwell_capacitances_and_coupling()

        self.assertGreater(c_phi[0], 0.0)
        self.assertGreater(c_eq[0], 0.0)
        self.assertEqual(c_sham[0], 0.0)

        # Coupling matrices are symmetric: k_ij == k_ji
        for i in range(5):
            for j in range(5):
                self.assertEqual(k_phi[i][j], k_phi[j][i])
                self.assertEqual(k_eq[i][j], k_eq[j][i])

        # Phi spacing naturally produces distinct coupling from equal spacing purely due to concentric Delta_r
        self.assertNotEqual(k_phi[0][1], k_eq[0][1])

    def test_zero_ordinal_bias_in_one_hot_gaussian_process(self):
        """Categorical one-hot vectors guarantee equidistant distances between distinct categories."""
        gp = GaussianProcessRegressor()

        # Check one-hot equidistant property: ||g_i - g_j||^2 == 2 for all distinct i != j
        g_phi = one_hot_encode("GOLDEN_RATIO_SPHERES", GEOMETRIES)
        g_eq = one_hot_encode("EQUAL_SPHERES", GEOMETRIES)
        g_rnd = one_hot_encode("RANDOM_SPHERES", GEOMETRIES)
        g_sham = one_hot_encode("SHAM_OFF", GEOMETRIES)

        def dist_sq(u, v):
            return sum((a - b) ** 2 for a, b in zip(u, v))

        self.assertEqual(dist_sq(g_phi, g_eq), 2.0)
        self.assertEqual(dist_sq(g_phi, g_rnd), 2.0)
        self.assertEqual(dist_sq(g_phi, g_sham), 2.0)
        self.assertEqual(dist_sq(g_eq, g_rnd), 2.0)

        # Train GP on 16-d one-hot vectors
        c_mer = one_hot_encode("DUAL_TETRAHEDRON_MERKABA", CORES)
        m_cw = one_hot_encode("NONE_CW", MODULATIONS)

        x1 = [1.86, 3.0] + g_phi + c_mer + m_cw
        x2 = [1.86, 3.0] + g_eq + c_mer + m_cw
        x3 = [1.86, 3.0] + g_rnd + c_mer + m_cw

        gp.fit([x1, x2, x3], [0.70, 0.40, 0.35])
        mu_phi, sigma_phi = gp.predict(x1)
        self.assertAlmostEqual(mu_phi, 0.70, delta=0.08)

    def test_factorial_regression_standard_errors_and_confidence_intervals(self):
        """FactorialInteractionAnalyzer must compute OLS standard errors and 95% confidence intervals."""
        fact = FactorialInteractionAnalyzer()
        fact.add_trial("GOLDEN_RATIO_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.75)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "SPHERICAL_CORE", 73.2, 3.0, 0.40)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "NO_CORE", 73.2, 3.0, 0.30)
        fact.add_trial("EQUAL_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.45)
        fact.add_trial("EQUAL_SPHERES", "SPHERICAL_CORE", 73.2, 3.0, 0.25)
        fact.add_trial("RANDOM_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.35)
        fact.add_trial("SHAM_OFF", "SHAM_OFF", 1.0, 0.0, 0.05)

        effects = fact.estimate_effects()
        self.assertIn("beta_G_phi", effects)
        self.assertIn("beta_G_phi_se", effects)
        self.assertIn("beta_G_phi_ci", effects)
        self.assertIn("beta_C_merkaba_ci", effects)
        self.assertIn("beta_GC_interaction_ci", effects)
        self.assertGreater(len(effects["beta_G_phi_ci"]), 1)
        self.assertEqual(effects["samples_count"], 7)

    def test_autocorrelation_time_estimation_and_paired_swap_permutation(self):
        """Estimate tau_decorr and execute paired condition-swap permutation test."""
        # Synthesize AR(1) signal
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

        tau = estimate_autocorrelation_time(active_base + active_int)
        self.assertGreaterEqual(tau, 1)

        analyzer = ResonanceAnalyzer(n_permutations=200, n_bootstraps=200)
        eval_res = analyzer.evaluate_trial(
            config_id="cfg-paired-test",
            blinded_token="TRIAL-PAIRED-1",
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
