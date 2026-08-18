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
    ConcentricSphericalCapacitanceModel,
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
    classify_condition_role,
    get_student_t_critical_value,
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

    def test_concentric_capacitance_model_physics(self):
        """Concentric spherical conductor physics: C_ab = 4*pi*eps0*(a*b)/(b-a)."""
        geom_phi = GeometryConfig(geometry_type="GOLDEN_RATIO_SPHERES", outer_diameter_mm=300.0)
        geom_eq = GeometryConfig(geometry_type="EQUAL_SPHERES", outer_diameter_mm=300.0)
        geom_sham = GeometryConfig(geometry_type="SHAM_OFF")

        model_phi = ConcentricSphericalCapacitanceModel(geom_phi)
        model_eq = ConcentricSphericalCapacitanceModel(geom_eq)
        model_sham = ConcentricSphericalCapacitanceModel(geom_sham)

        c_phi, k_phi = model_phi.compute_capacitances_and_coupling()
        c_eq, k_eq = model_eq.compute_capacitances_and_coupling()
        c_sham, k_sham = model_sham.compute_capacitances_and_coupling()

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

    def test_exact_student_t_critical_values(self):
        """Verify exact two-sided Student's-t critical values at alpha = 0.05."""
        self.assertEqual(get_student_t_critical_value(1), 12.706)
        self.assertEqual(get_student_t_critical_value(2), 4.303)
        self.assertEqual(get_student_t_critical_value(3), 3.182)
        self.assertEqual(get_student_t_critical_value(5), 2.571)
        self.assertEqual(get_student_t_critical_value(10), 2.228)
        self.assertEqual(get_student_t_critical_value(30), 2.042)
        self.assertAlmostEqual(get_student_t_critical_value(100), 1.984, delta=0.01)

    def test_factorial_regression_small_sample_degrees_of_freedom_warning(self):
        """FactorialInteractionAnalyzer must compute exact Student-t CIs and flag small-sample df."""
        fact = FactorialInteractionAnalyzer()
        # Add exactly 7 trials (df = 7 - 6 = 1)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.75)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "SPHERICAL_CORE", 73.2, 3.0, 0.40)
        fact.add_trial("GOLDEN_RATIO_SPHERES", "NO_CORE", 73.2, 3.0, 0.30)
        fact.add_trial("EQUAL_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.45)
        fact.add_trial("EQUAL_SPHERES", "SPHERICAL_CORE", 73.2, 3.0, 0.25)
        fact.add_trial("RANDOM_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 73.2, 3.0, 0.35)
        fact.add_trial("SHAM_OFF", "SHAM_OFF", 1.0, 0.0, 0.05)

        effects = fact.estimate_effects()
        self.assertEqual(effects["residual_degrees_of_freedom"], 1)
        self.assertEqual(effects["student_t_critical_value"], 12.706)
        self.assertIn("SMALL_SAMPLE_DF_1", effects["warning"])
        # CI width must reflect exact t_crit = 12.706 (not arbitrary 2.3)
        ci_width = effects["beta_G_phi_ci"][1] - effects["beta_G_phi_ci"][0]
        self.assertGreater(ci_width, 10.0 * effects["beta_G_phi_se"])

    def test_condition_role_taxonomy_and_factorial_scheduler(self):
        """Deterministic condition_role assignment and matched factorial block scheduling."""
        self.assertEqual(classify_condition_role("GOLDEN_RATIO_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 3.0), "TARGET_HYPOTHESIS")
        self.assertEqual(classify_condition_role("EQUAL_SPHERES", "NO_CORE", 3.0), "ACTIVE_CONTROL")
        self.assertEqual(classify_condition_role("RANDOM_SPHERES", "DUAL_TETRAHEDRON_MERKABA", 3.0), "ACTIVE_CONTROL")
        self.assertEqual(classify_condition_role("SHAM_OFF", "SHAM_OFF", 0.0), "SHAM")

        opt = ClosedLoopOptimizer()
        opt.schedule_matched_factorial_block(base_freq_hz=73.2, amp_v=3.3)
        self.assertEqual(len(opt.queued_factorial_block), 7)

        dec1 = opt.propose_next_intervention(current_step=1)
        self.assertIn(dec1.condition_role, ["TARGET_HYPOTHESIS", "ACTIVE_CONTROL", "SHAM"])
        self.assertEqual(dec1.hypothesis_label, "MATCHED_FACTORIAL_BLOCK_EXECUTION")

    def test_autocorrelation_time_estimation_and_contiguous_block_swap_permutation(self):
        """Estimate tau_decorr and execute contiguous block swap permutation test."""
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
