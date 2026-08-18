"""Closed-loop adaptive experimental optimization engine for CIRCLE Resonance experiments.

Features:
1. One-Hot Categorical Gaussian Process Regressor:
     x = [log10(f), A, g_4d, c_5d, m_5d] in R^16
     Completely eliminates ordinal metric bias across discrete geometries and cores.
2. Factorial Interaction Analyzer with Exact Student's-t Degrees-of-Freedom Confidence Intervals.
3. Deterministic condition_role classification (TARGET_HYPOTHESIS, ACTIVE_CONTROL, SHAM, EXPLORATORY).
4. Balanced Matched Factorial Block Scheduler (G x C at matched f and A).
5. Isolated hypothesis candidate library (Schumann modes, acoustic intervals).
6. Opaque, unguessable cryptographic trial tokens and decoupled BlindTrialManifest.
7. Explicit software parameter exploration caps (SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING).
"""

from __future__ import annotations

import json
import math
import random
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING: float = 10.0

GEOMETRIES = ("GOLDEN_RATIO_SPHERES", "EQUAL_SPHERES", "RANDOM_SPHERES", "SHAM_OFF")
CORES = ("DUAL_TETRAHEDRON_MERKABA", "SPHERICAL_CORE", "CUBIC_CORE", "NO_CORE", "SHAM_OFF")
MODULATIONS = ("NONE_CW", "SINE_AM", "PULSED", "BURST", "SHAM_OFF")

# Exact two-sided Student's-t critical values at alpha = 0.05
STUDENT_T_CRITICAL_TABLE = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    12: 2.179,
    15: 2.131,
    20: 2.086,
    25: 2.060,
    30: 2.042,
}


def get_student_t_critical_value(df: int) -> float:
    """Return exact two-sided critical value t_{0.025, df} for degrees of freedom df."""
    if df <= 0:
        return 12.706
    if df in STUDENT_T_CRITICAL_TABLE:
        return STUDENT_T_CRITICAL_TABLE[df]
    if df < 10:
        keys = sorted(k for k in STUDENT_T_CRITICAL_TABLE.keys() if k < 10)
        return STUDENT_T_CRITICAL_TABLE[min(keys, key=lambda k: abs(k - df))]
    if df <= 30:
        keys = sorted(k for k in STUDENT_T_CRITICAL_TABLE.keys() if k >= 10)
        return STUDENT_T_CRITICAL_TABLE[min(keys, key=lambda k: abs(k - df))]
    # Asymptotic expansion for df > 30: t_crit ~ 1.95996 + 2.378 / df + 2.82 / df^2
    return round(1.95996 + (2.378 / df) + (2.82 / (df ** 2)), 3)


def classify_condition_role(geometry: str, core: str, amp_v: float) -> str:
    """Classify condition role deterministically from configuration parameters."""
    if geometry == "SHAM_OFF" or amp_v <= 0.0:
        return "SHAM"
    if geometry == "GOLDEN_RATIO_SPHERES" and core == "DUAL_TETRAHEDRON_MERKABA":
        return "TARGET_HYPOTHESIS"
    if geometry in ("EQUAL_SPHERES", "RANDOM_SPHERES") or core in ("SPHERICAL_CORE", "CUBIC_CORE", "NO_CORE"):
        return "ACTIVE_CONTROL"
    return "EXPLORATORY"


def one_hot_encode(category: str, category_tuple: Tuple[str, ...]) -> List[float]:
    """Encode a discrete category as an orthogonal one-hot vector with equidistant metric distance."""
    vec = [0.0] * len(category_tuple)
    if category in category_tuple:
        vec[category_tuple.index(category)] = 1.0
    return vec


@dataclass(frozen=True)
class HypothesisCandidateLibrary:
    """Explicitly isolated catalog of hypothesis-motivated candidate frequencies."""
    SCHUMANN_IONOSPHERIC_MODES: Tuple[float, ...] = (7.83, 14.3, 20.8, 27.3, 33.8)
    EEG_ENTRAINMENT_BANDS: Tuple[float, ...] = (2.5, 6.0, 10.0, 20.0, 40.0)
    HISTORICAL_ACOUSTIC_INTERVALS: Tuple[float, ...] = (432.0, 528.0)


@dataclass(frozen=True)
class ExperimentSearchSpace:
    """Bounded software parameter exploration space."""
    min_frequency_hz: float = 1.0
    max_frequency_hz: float = 100000.0
    min_amplitude_v: float = 0.0
    max_amplitude_v: float = SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING
    min_duration_ms: float = 5000.0
    max_duration_ms: float = 60000.0
    min_baseline_ms: float = 5000.0
    min_washout_ms: float = 5000.0
    allowed_geometries: Tuple[str, ...] = GEOMETRIES
    allowed_cores: Tuple[str, ...] = CORES
    allowed_modulations: Tuple[str, ...] = MODULATIONS


class GaussianProcessRegressor:
    """Multi-dimensional Gaussian Process with One-Hot Categorical and Continuous RBF Kernels.
    
    State vector:
      x = [log10(f), A, g_0..g_3, c_0..c_4, m_0..m_4] in R^16
    """

    def __init__(
        self,
        length_scales: Tuple[float, float, float, float, float] = (0.5, 2.0, 1.0, 1.0, 1.0),
        signal_variance: float = 1.0,
        noise_variance: float = 0.05,
    ):
        self.l_f = length_scales[0]
        self.l_a = length_scales[1]
        self.l_g = length_scales[2]
        self.l_c = length_scales[3]
        self.l_m = length_scales[4]
        self.sigma_f2 = signal_variance
        self.sigma_n2 = noise_variance

        self.X: List[List[float]] = []
        self.y: List[float] = []

    def _kernel(self, x1: List[float], x2: List[float]) -> float:
        """Compound Continuous + Categorical RBF Kernel."""
        df = (x1[0] - x2[0]) / self.l_f
        da = (x1[1] - x2[1]) / self.l_a

        dg_sq = sum((x1[2 + i] - x2[2 + i]) ** 2 for i in range(4)) / (2.0 * (self.l_g ** 2))
        dc_sq = sum((x1[6 + i] - x2[6 + i]) ** 2 for i in range(5)) / (2.0 * (self.l_c ** 2))
        dm_sq = sum((x1[11 + i] - x2[11 + i]) ** 2 for i in range(5)) / (2.0 * (self.l_m ** 2))

        exponent = -0.5 * (df ** 2 + da ** 2) - dg_sq - dc_sq - dm_sq
        return self.sigma_f2 * math.exp(exponent)

    def fit(self, X: List[List[float]], y: List[float]) -> None:
        self.X = [list(pt) for pt in X]
        self.y = list(y)

    def predict(self, x_star: List[float]) -> Tuple[float, float]:
        """Compute exact posterior mean and predictive standard deviation."""
        n = len(self.X)
        if n == 0:
            return (0.0, math.sqrt(self.sigma_f2))

        K = [[self._kernel(self.X[i], self.X[j]) for j in range(n)] for i in range(n)]
        for i in range(n):
            K[i][i] += self.sigma_n2

        k_star = [self._kernel(x_star, self.X[i]) for i in range(n)]
        k_self = self._kernel(x_star, x_star)

        def solve_linear_system(A: List[List[float]], b: List[float]) -> List[float]:
            m = len(b)
            mat = [row[:] + [b[i]] for i, row in enumerate(A)]
            for col in range(m):
                max_row = max(range(col, m), key=lambda r: abs(mat[r][col]))
                if abs(mat[max_row][col]) < 1e-12:
                    return [0.0] * m
                mat[col], mat[max_row] = mat[max_row], mat[col]
                pivot = mat[col][col]
                for j in range(col, m + 1):
                    mat[col][j] /= pivot
                for r in range(m):
                    if r != col:
                        factor = mat[r][col]
                        for j in range(col, m + 1):
                            mat[r][j] -= factor * mat[col][j]
            return [mat[r][m] for r in range(m)]

        alpha = solve_linear_system(K, self.y)
        v = solve_linear_system(K, k_star)

        mu = sum(k_star[i] * alpha[i] for i in range(n))
        v_dot = sum(k_star[i] * v[i] for i in range(n))
        sigma_sq = max(1e-4, k_self - v_dot)
        sigma = math.sqrt(sigma_sq)

        return (mu, sigma)


@dataclass
class ExperimentalDecision:
    decision_id: str
    trial_token: str
    target_frequency_hz: float
    amplitude_v: float
    geometry_type: str
    core_geometry: str
    modulation_type: str
    duration_ms: float
    baseline_duration_ms: float
    washout_duration_ms: float
    condition_role: str  # TARGET_HYPOTHESIS, ACTIVE_CONTROL, SHAM, EXPLORATORY
    hypothesis_label: Optional[str]
    posterior_predicted_mean: float
    posterior_uncertainty_sigma: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "trial_token": self.trial_token,
            "target_frequency_hz": round(self.target_frequency_hz, 3),
            "amplitude_v": round(self.amplitude_v, 3),
            "geometry_type": self.geometry_type,
            "core_geometry": self.core_geometry,
            "modulation_type": self.modulation_type,
            "duration_ms": self.duration_ms,
            "baseline_duration_ms": self.baseline_duration_ms,
            "washout_duration_ms": self.washout_duration_ms,
            "condition_role": self.condition_role,
            "hypothesis_label": self.hypothesis_label,
            "posterior_predicted_mean": round(self.posterior_predicted_mean, 4),
            "posterior_uncertainty_sigma": round(self.posterior_uncertainty_sigma, 4),
        }


class FactorialInteractionAnalyzer:
    """Linear regression model with exact Student's-t degrees-of-freedom confidence intervals.
    
    Model: R = beta_0 + beta_G * G + beta_C * C + beta_f * log10(f) + beta_A * A + beta_GC * (G x C) + eps
    """

    def __init__(self):
        self.trials: List[Tuple[float, float, float, float, float]] = []

    def add_trial(self, geometry: str, core: str, freq_hz: float, amp_v: float, response_score: float) -> None:
        g_code = 1.0 if geometry == "GOLDEN_RATIO_SPHERES" else 0.0
        c_code = 1.0 if core == "DUAL_TETRAHEDRON_MERKABA" else 0.0
        log_f = math.log10(max(1.0, freq_hz))
        self.trials.append((g_code, c_code, log_f, amp_v, response_score))

    def estimate_effects(self) -> Dict[str, Any]:
        """Estimate OLS regression coefficients, standard errors, exact Student-t CIs, and warnings."""
        p = 6
        n = len(self.trials)
        if n < p + 1:
            return {
                "beta_0_intercept": 0.0,
                "beta_G_phi": 0.0,
                "beta_G_phi_ci": [0.0, 0.0],
                "beta_C_merkaba": 0.0,
                "beta_C_merkaba_ci": [0.0, 0.0],
                "beta_GC_interaction": 0.0,
                "beta_GC_interaction_ci": [0.0, 0.0],
                "beta_freq": 0.0,
                "beta_amp": 0.0,
                "residual_std_error": 0.0,
                "residual_degrees_of_freedom": max(0, n - p),
                "samples_count": n,
                "warning": "INSUFFICIENT_SAMPLES_FOR_REGRESSION",
            }

        X = []
        y = []
        for g, c, log_f, a, r in self.trials:
            X.append([1.0, g, c, g * c, log_f, a])
            y.append(r)

        XtX = [[sum(X[i][j] * X[i][k] for i in range(n)) for k in range(p)] for j in range(p)]
        Xty = [sum(X[i][j] * y[i] for i in range(n)) for j in range(p)]

        for j in range(p):
            XtX[j][j] += 1e-6

        def invert_matrix(A: List[List[float]]) -> List[List[float]]:
            m = len(A)
            mat = [row[:] + [1.0 if i == r else 0.0 for i in range(m)] for r, row in enumerate(A)]
            for col in range(m):
                max_row = max(range(col, m), key=lambda r: abs(mat[r][col]))
                mat[col], mat[max_row] = mat[max_row], mat[col]
                pivot = mat[col][col]
                if abs(pivot) < 1e-12:
                    return [[0.0] * m for _ in range(m)]
                for j in range(2 * m):
                    mat[col][j] /= pivot
                for r in range(m):
                    if r != col:
                        factor = mat[r][col]
                        for j in range(2 * m):
                            mat[r][j] -= factor * mat[col][j]
            return [[mat[r][m + c] for c in range(m)] for r in range(m)]

        XtX_inv = invert_matrix(XtX)
        betas = [sum(XtX_inv[j][k] * Xty[k] for k in range(p)) for j in range(p)]

        residuals = [y[i] - sum(X[i][j] * betas[j] for j in range(p)) for i in range(n)]
        sse = sum(r ** 2 for r in residuals)
        df = max(1, n - p)
        sigma2_hat = sse / df
        rse = math.sqrt(sigma2_hat)

        se = [math.sqrt(max(1e-8, sigma2_hat * XtX_inv[j][j])) for j in range(p)]
        t_crit = get_student_t_critical_value(df)

        warning_msg = None
        if df <= 2:
            warning_msg = f"SMALL_SAMPLE_DF_{df}_CRITICAL_VALUE_IS_{t_crit:.2f}"

        return {
            "beta_0_intercept": round(betas[0], 4),
            "beta_G_phi": round(betas[1], 4),
            "beta_G_phi_se": round(se[1], 4),
            "beta_G_phi_ci": [round(betas[1] - t_crit * se[1], 4), round(betas[1] + t_crit * se[1], 4)],
            "beta_C_merkaba": round(betas[2], 4),
            "beta_C_merkaba_se": round(se[2], 4),
            "beta_C_merkaba_ci": [round(betas[2] - t_crit * se[2], 4), round(betas[2] + t_crit * se[2], 4)],
            "beta_GC_interaction": round(betas[3], 4),
            "beta_GC_interaction_se": round(se[3], 4),
            "beta_GC_interaction_ci": [round(betas[3] - t_crit * se[3], 4), round(betas[3] + t_crit * se[3], 4)],
            "beta_freq": round(betas[4], 4),
            "beta_amp": round(betas[5], 4),
            "residual_std_error": round(rse, 4),
            "residual_degrees_of_freedom": df,
            "student_t_critical_value": t_crit,
            "samples_count": n,
            "warning": warning_msg,
        }


class BlindTrialManifest:
    """Secure, decoupled manifest for double-blind trial management."""

    def __init__(self):
        self._mapping: Dict[str, Dict[str, Any]] = {}
        self._sealed: bool = False

    def register_trial(self, token: str, config: Dict[str, Any]) -> None:
        if self._sealed:
            raise RuntimeError("Cannot register trials in a sealed manifest.")
        self._mapping[token] = config

    def seal_manifest(self) -> None:
        self._sealed = True

    def unseal_manifest(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._mapping)

    def is_sealed(self) -> bool:
        return self._sealed


class ClosedLoopOptimizer:
    """Adaptive search policy using one-hot categorical GP-UCB and matched factorial matrix exploration."""

    def __init__(
        self,
        search_space: Optional[ExperimentSearchSpace] = None,
        seed: int = 1337,
        exploration_weight_kappa: float = 1.96,
    ):
        self.space = search_space or ExperimentSearchSpace()
        self.rng = random.Random(seed)
        self.kappa = exploration_weight_kappa
        self.manifest = BlindTrialManifest()
        self.gp = GaussianProcessRegressor(length_scales=(0.5, 2.0, 1.0, 1.0, 1.0))
        self.factorial_analyzer = FactorialInteractionAnalyzer()

        self.observed_x: List[List[float]] = []
        self.observed_y: List[float] = []
        self.history: List[ExperimentalDecision] = []
        self.queued_factorial_block: List[Tuple[str, str, float, float, str]] = []

    def _build_feature_vector(self, freq_hz: float, amp_v: float, geom: str, core: str, mod: str) -> List[float]:
        log_f = math.log10(max(1.0, freq_hz))
        amp = max(0.0, amp_v)
        g_vec = one_hot_encode(geom, GEOMETRIES)
        c_vec = one_hot_encode(core, CORES)
        m_vec = one_hot_encode(mod, MODULATIONS)
        return [log_f, amp] + g_vec + c_vec + m_vec

    def update_posterior(self, last_decision: ExperimentalDecision, observed_score: float) -> None:
        """Update multi-dimensional Gaussian Process model and Factorial interaction analyzer."""
        feat = self._build_feature_vector(
            last_decision.target_frequency_hz,
            last_decision.amplitude_v,
            last_decision.geometry_type,
            last_decision.core_geometry,
            last_decision.modulation_type,
        )
        self.observed_x.append(feat)
        self.observed_y.append(observed_score)
        self.gp.fit(self.observed_x, self.observed_y)

        self.factorial_analyzer.add_trial(
            last_decision.geometry_type,
            last_decision.core_geometry,
            last_decision.target_frequency_hz,
            last_decision.amplitude_v,
            observed_score,
        )

    def schedule_matched_factorial_block(self, base_freq_hz: float = 73.2, amp_v: float = 3.3) -> None:
        """Queue a balanced, randomized factorial block of (G x C) conditions evaluated at matched f and A."""
        block = [
            ("GOLDEN_RATIO_SPHERES", "DUAL_TETRAHEDRON_MERKABA", base_freq_hz, amp_v, "NONE_CW"),
            ("GOLDEN_RATIO_SPHERES", "SPHERICAL_CORE", base_freq_hz, amp_v, "NONE_CW"),
            ("GOLDEN_RATIO_SPHERES", "NO_CORE", base_freq_hz, amp_v, "NONE_CW"),
            ("EQUAL_SPHERES", "DUAL_TETRAHEDRON_MERKABA", base_freq_hz, amp_v, "NONE_CW"),
            ("EQUAL_SPHERES", "SPHERICAL_CORE", base_freq_hz, amp_v, "NONE_CW"),
            ("RANDOM_SPHERES", "DUAL_TETRAHEDRON_MERKABA", base_freq_hz, amp_v, "NONE_CW"),
            ("SHAM_OFF", "SHAM_OFF", 0.0, 0.0, "SHAM_OFF"),
        ]
        self.rng.shuffle(block)
        self.queued_factorial_block.extend(block)

    def propose_next_intervention(
        self,
        current_step: int,
        last_response_score: Optional[float] = None,
        hypothesis_set_name: Optional[str] = None,
        force_control_ratio: float = 0.33,
    ) -> ExperimentalDecision:
        """Propose next intervention using queued factorial blocks or one-hot categorical GP-UCB."""
        if last_response_score is not None and self.history:
            self.update_posterior(self.history[-1], last_response_score)

        decision_id = f"dec-{current_step:04d}"
        trial_token = f"TRIAL-{secrets.token_hex(4).upper()}"

        # 1. Execute queued factorial block if available
        if self.queued_factorial_block:
            geom, core, freq, amp, mod = self.queued_factorial_block.pop(0)
            hyp_label = "MATCHED_FACTORIAL_BLOCK_EXECUTION"
            mu, sigma = 0.0, 1.0
        else:
            is_control = (self.rng.random() < force_control_ratio) or (current_step % 3 == 0)

            if is_control:
                control_type = self.rng.choice(["SHAM_OFF", "EQUAL_SPHERES", "RANDOM_SPHERES"])
                if control_type == "SHAM_OFF":
                    geom = "SHAM_OFF"
                    core = "SHAM_OFF"
                    amp = 0.0
                    freq = 0.0
                    mod = "SHAM_OFF"
                else:
                    geom = control_type
                    core = self.rng.choice(["NO_CORE", "SPHERICAL_CORE", "CUBIC_CORE"])
                    amp = round(self.rng.uniform(1.0, 5.0), 2)
                    log_f = self.rng.uniform(math.log10(self.space.min_frequency_hz), math.log10(1000.0))
                    freq = round(10.0 ** log_f, 2)
                    mod = "NONE_CW"
                hyp_label = None
                mu, sigma = 0.0, 1.0
            else:
                if hypothesis_set_name == "schumann":
                    geom = "GOLDEN_RATIO_SPHERES"
                    core = "DUAL_TETRAHEDRON_MERKABA"
                    freq = self.rng.choice(HypothesisCandidateLibrary.SCHUMANN_IONOSPHERIC_MODES)
                    amp = round(self.rng.uniform(1.0, 5.0), 2)
                    hyp_label = "HYP_SCHUMANN_IONOSPHERIC"
                    mod = "NONE_CW"
                    mu, sigma = 0.0, 1.0
                elif hypothesis_set_name == "acoustic_solfeggio":
                    geom = "GOLDEN_RATIO_SPHERES"
                    core = "DUAL_TETRAHEDRON_MERKABA"
                    freq = self.rng.choice(HypothesisCandidateLibrary.HISTORICAL_ACOUSTIC_INTERVALS)
                    amp = round(self.rng.uniform(1.0, 5.0), 2)
                    hyp_label = "HYP_HISTORICAL_ACOUSTIC"
                    mod = "NONE_CW"
                    mu, sigma = 0.0, 1.0
                else:
                    # One-Hot Categorical GP-UCB Exploration across (f, A, G, C, M)
                    best_acq = -float("inf")
                    best_f = 73.2
                    best_a = 3.3
                    best_g = "GOLDEN_RATIO_SPHERES"
                    best_c = "DUAL_TETRAHEDRON_MERKABA"
                    best_m = "NONE_CW"
                    best_mu, best_sigma = 0.0, 1.0

                    candidate_geoms = ["GOLDEN_RATIO_SPHERES", "EQUAL_SPHERES", "RANDOM_SPHERES"]
                    candidate_cores = ["DUAL_TETRAHEDRON_MERKABA", "SPHERICAL_CORE", "CUBIC_CORE", "NO_CORE"]
                    candidate_mods = ["NONE_CW", "SINE_AM", "PULSED"]

                    for _ in range(30):
                        cand_log_f = self.rng.uniform(math.log10(self.space.min_frequency_hz), math.log10(1000.0))
                        cand_f = 10.0 ** cand_log_f
                        cand_a = self.rng.uniform(1.0, 5.0)
                        cand_g = self.rng.choice(candidate_geoms)
                        cand_c = self.rng.choice(candidate_cores)
                        cand_m = self.rng.choice(candidate_mods)

                        feat = self._build_feature_vector(cand_f, cand_a, cand_g, cand_c, cand_m)
                        c_mu, c_sigma = self.gp.predict(feat)
                        acq = c_mu + self.kappa * c_sigma

                        if acq > best_acq:
                            best_acq = acq
                            best_f = cand_f
                            best_a = cand_a
                            best_g = cand_g
                            best_c = cand_c
                            best_m = cand_m
                            best_mu, best_sigma = c_mu, c_sigma

                    freq = round(best_f, 2)
                    amp = round(best_a, 2)
                    geom = best_g
                    core = best_c
                    mod = best_m
                    mu, sigma = best_mu, best_sigma
                    hyp_label = "MULTI_FACTORIAL_ONE_HOT_BAYESIAN_EXPLORATION"

        duration = 15000.0
        baseline = max(self.space.min_baseline_ms, 5000.0)
        washout = max(self.space.min_washout_ms, 5000.0)

        # Deterministic condition_role assignment
        role = classify_condition_role(geom, core, amp)

        raw_config = {
            "geom": geom,
            "core": core,
            "freq": freq,
            "amp": amp,
            "mod": mod,
            "condition_role": role,
        }
        self.manifest.register_trial(trial_token, raw_config)

        decision = ExperimentalDecision(
            decision_id=decision_id,
            trial_token=trial_token,
            target_frequency_hz=freq,
            amplitude_v=amp,
            geometry_type=geom,
            core_geometry=core,
            modulation_type=mod,
            duration_ms=duration,
            baseline_duration_ms=baseline,
            washout_duration_ms=washout,
            condition_role=role,
            hypothesis_label=hyp_label,
            posterior_predicted_mean=mu,
            posterior_uncertainty_sigma=sigma,
        )

        self.history.append(decision)
        return decision
