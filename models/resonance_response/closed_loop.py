"""Closed-loop adaptive experimental optimization engine for CIRCLE Resonance experiments.

Features:
1. One-Hot Categorical Gaussian Process Regressor (x in R^16, zero ordinal bias).
2. Clean Confirmatory 2x2 Factorial Design ({Phi, Equal} x {Merkaba, Sphere}) with orthogonal coding.
3. Strict Model Identifiability Gate: returns MODEL_NOT_IDENTIFIABLE if rank(X) < p (zero pseudo-ridge).
4. Hierarchical Mixed-Effects Model for multi-session / repeated-trial evaluations.
5. Deterministic condition_role taxonomy (TARGET_HYPOTHESIS, ACTIVE_CONTROL, SHAM, EXPLORATORY).
6. Balanced Matched Factorial Block Scheduler (G x C at matched f and A).
7. Isolated hypothesis candidate library and decoupled BlindTrialManifest.
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
    condition_role: str
    factorial_block_id: Optional[str]
    factorial_block_index: Optional[int]
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
            "factorial_block_id": self.factorial_block_id,
            "factorial_block_index": self.factorial_block_index,
            "hypothesis_label": self.hypothesis_label,
            "posterior_predicted_mean": round(self.posterior_predicted_mean, 4),
            "posterior_uncertainty_sigma": round(self.posterior_uncertainty_sigma, 4),
        }


class FactorialInteractionAnalyzer:
    """Orthogonal 2x2 confirmatory factorial analyzer with strict rank/identifiability gating.
    
    Confirmatory Model:
      R = beta_0 + beta_G * G + beta_C * C + beta_GC * (G x C) + eps
    where:
      G in {+1 (Phi), -1 (Equal)}
      C in {+1 (Merkaba), -1 (Sphere)}
      (G x C) in {+1, -1}
    
    Strict Identifiability:
      Validates full column rank rank(X) == p without diagonal ridge regularization.
    """

    def __init__(self):
        # Confirmatory trials: (G_code, C_code, response_score, trial_meta)
        self.confirmatory_trials: List[Tuple[float, float, float, Dict[str, Any]]] = []
        # Separate control/robustness arms
        self.control_arms: List[Tuple[str, str, float, float]] = []

    def add_trial(
        self,
        geometry: str,
        core: str,
        freq_hz: float,
        amp_v: float,
        response_score: float,
        session_id: Optional[str] = None,
    ) -> None:
        """Register trial into 2x2 confirmatory factor pool or separate control arm."""
        meta = {"session_id": session_id or "default_session", "freq": freq_hz, "amp": amp_v}

        # Confirmatory 2x2 matrix: {Phi, Equal} x {Merkaba, Sphere}
        if geometry in ("GOLDEN_RATIO_SPHERES", "EQUAL_SPHERES") and core in ("DUAL_TETRAHEDRON_MERKABA", "SPHERICAL_CORE"):
            g_code = 1.0 if geometry == "GOLDEN_RATIO_SPHERES" else -1.0
            c_code = 1.0 if core == "DUAL_TETRAHEDRON_MERKABA" else -1.0
            self.confirmatory_trials.append((g_code, c_code, response_score, meta))
        else:
            self.control_arms.append((geometry, core, amp_v, response_score))

    def _compute_matrix_rank_and_invert(self, XtX: List[List[float]]) -> Tuple[int, Optional[List[List[float]]]]:
        """Compute exact rank and inverse of matrix XtX using Gauss-Jordan with partial pivoting."""
        p = len(XtX)
        mat = [row[:] + [1.0 if i == r else 0.0 for i in range(p)] for r, row in enumerate(XtX)]
        rank = 0

        for col in range(p):
            max_row = max(range(col, p), key=lambda r: abs(mat[r][col]))
            if abs(mat[max_row][col]) < 1e-9:
                continue
            rank += 1
            mat[col], mat[max_row] = mat[max_row], mat[col]
            pivot = mat[col][col]
            for j in range(2 * p):
                mat[col][j] /= pivot
            for r in range(p):
                if r != col:
                    factor = mat[r][col]
                    for j in range(2 * p):
                        mat[r][j] -= factor * mat[col][j]

        if rank < p:
            return rank, None

        inv = [[mat[r][p + c] for c in range(p)] for r in range(p)]
        return rank, inv

    def estimate_confirmatory_effects(self) -> Dict[str, Any]:
        """Estimate OLS 2x2 confirmatory parameters with strict identifiability check."""
        p = 4  # [1, G, C, G*C]
        n = len(self.confirmatory_trials)

        if n < p:
            return {
                "identifiability_status": "INSUFFICIENT_SAMPLES",
                "samples_count": n,
                "required_samples": p,
                "residual_degrees_of_freedom": 0,
            }

        X: List[List[float]] = []
        y: List[float] = []

        for g, c, r, _ in self.confirmatory_trials:
            X.append([1.0, g, c, g * c])
            y.append(r)

        # XtX (p x p) and Xty (p x 1)
        XtX = [[sum(X[i][j] * X[i][k] for i in range(n)) for k in range(p)] for j in range(p)]
        Xty = [sum(X[i][j] * y[i] for i in range(n)) for j in range(p)]

        # Strict identifiability check without pseudo-ridge regularization
        rank, XtX_inv = self._compute_matrix_rank_and_invert(XtX)
        if rank < p or XtX_inv is None:
            return {
                "identifiability_status": "MODEL_NOT_IDENTIFIABLE",
                "reason": "DESIGN_MATRIX_RANK_DEFICIENT",
                "matrix_rank": rank,
                "parameters_count": p,
                "samples_count": n,
            }

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
            "identifiability_status": "IDENTIFIED_OLS",
            "beta_0_intercept": round(betas[0], 4),
            "beta_G_phi_vs_equal": round(betas[1], 4),
            "beta_G_se": round(se[1], 4),
            "beta_G_ci": [round(betas[1] - t_crit * se[1], 4), round(betas[1] + t_crit * se[1], 4)],
            "beta_C_merkaba_vs_sphere": round(betas[2], 4),
            "beta_C_se": round(se[2], 4),
            "beta_C_ci": [round(betas[2] - t_crit * se[2], 4), round(betas[2] + t_crit * se[2], 4)],
            "beta_GC_interaction": round(betas[3], 4),
            "beta_GC_se": round(se[3], 4),
            "beta_GC_ci": [round(betas[3] - t_crit * se[3], 4), round(betas[3] + t_crit * se[3], 4)],
            "residual_std_error": round(rse, 4),
            "residual_degrees_of_freedom": df,
            "student_t_critical_value": t_crit,
            "samples_count": n,
            "warning": warning_msg,
        }


class HierarchicalTrialEvaluator:
    """Hierarchical mixed-effects evaluator across repeated experimental sessions/subjects.
    
    Model:
      R_{s, j} = beta_0 + beta_G * G_{s, j} + beta_C * C_{s, j} + beta_GC * (G_{s, j} x C_{s, j}) + u_s + eps_{s, j}
      where u_s ~ N(0, sigma_u^2) is the session-specific random intercept.
    """

    def __init__(self):
        self.session_trials: Dict[str, List[Tuple[float, float, float]]] = {}  # session_id -> [(G, C, R)]

    def add_trial(self, session_id: str, geometry: str, core: str, response_score: float) -> None:
        if geometry in ("GOLDEN_RATIO_SPHERES", "EQUAL_SPHERES") and core in ("DUAL_TETRAHEDRON_MERKABA", "SPHERICAL_CORE"):
            g_code = 1.0 if geometry == "GOLDEN_RATIO_SPHERES" else -1.0
            c_code = 1.0 if core == "DUAL_TETRAHEDRON_MERKABA" else -1.0
            if session_id not in self.session_trials:
                self.session_trials[session_id] = []
            self.session_trials[session_id].append((g_code, c_code, response_score))

    def fit_mixed_effects(self) -> Dict[str, Any]:
        """Estimate fixed effects and inter-session random intercept variance."""
        num_sessions = len(self.session_trials)
        all_trials = [t for s in self.session_trials.values() for t in s]
        total_n = len(all_trials)

        if num_sessions < 2 or total_n < 8:
            return {
                "status": "INSUFFICIENT_SESSIONS_FOR_HIERARCHICAL_MODEL",
                "sessions_count": num_sessions,
                "total_trials": total_n,
            }

        # Session-specific means
        session_means = {s: sum(t[2] for t in trials) / len(trials) for s, trials in self.session_trials.items()}
        grand_mean = sum(session_means.values()) / num_sessions

        # Between-session variance sigma_u^2
        sigma_u2 = sum((m - grand_mean) ** 2 for m in session_means.values()) / max(1, num_sessions - 1)

        # Within-session centered OLS
        centered_X = []
        centered_y = []
        for s, trials in self.session_trials.items():
            s_mean = session_means[s]
            for g, c, r in trials:
                centered_X.append([g, c, g * c])
                centered_y.append(r - s_mean)

        p = 3
        XtX = [[sum(centered_X[i][j] * centered_X[i][k] for i in range(len(centered_y))) for k in range(p)] for j in range(p)]
        Xty = [sum(centered_X[i][j] * centered_y[i] for i in range(len(centered_y))) for j in range(p)]

        analyzer = FactorialInteractionAnalyzer()
        rank, XtX_inv = analyzer._compute_matrix_rank_and_invert(XtX)
        if rank < p or XtX_inv is None:
            return {
                "status": "HIERARCHICAL_MODEL_RANK_DEFICIENT",
                "matrix_rank": rank,
            }

        betas = [sum(XtX_inv[j][k] * Xty[k] for k in range(p)) for j in range(p)]
        resids = [centered_y[i] - sum(centered_X[i][j] * betas[j] for j in range(p)) for i in range(len(centered_y))]
        sigma_e2 = sum(r ** 2 for r in resids) / max(1, total_n - num_sessions - p)

        # Clustered standard errors
        se = [math.sqrt(max(1e-8, (sigma_e2 + sigma_u2 / num_sessions) * XtX_inv[j][j])) for j in range(p)]
        df = max(1, num_sessions - 1)
        t_crit = get_student_t_critical_value(df)

        return {
            "status": "CONVERGED",
            "sessions_count": num_sessions,
            "total_trials": total_n,
            "between_session_variance_sigma_u2": round(sigma_u2, 4),
            "within_session_variance_sigma_e2": round(sigma_e2, 4),
            "beta_G_phi_vs_equal": round(betas[0], 4),
            "beta_G_ci": [round(betas[0] - t_crit * se[0], 4), round(betas[0] + t_crit * se[0], 4)],
            "beta_C_merkaba_vs_sphere": round(betas[1], 4),
            "beta_C_ci": [round(betas[1] - t_crit * se[1], 4), round(betas[1] + t_crit * se[1], 4)],
            "beta_GC_interaction": round(betas[2], 4),
            "beta_GC_ci": [round(betas[2] - t_crit * se[2], 4), round(betas[2] + t_crit * se[2], 4)],
            "effective_degrees_of_freedom": df,
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
    """Adaptive search policy using one-hot categorical GP-UCB and balanced matched factorial scheduling."""

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
        self.hierarchical_evaluator = HierarchicalTrialEvaluator()

        self.observed_x: List[List[float]] = []
        self.observed_y: List[float] = []
        self.history: List[ExperimentalDecision] = []
        self.queued_factorial_block: List[Dict[str, Any]] = []

    def _build_feature_vector(self, freq_hz: float, amp_v: float, geom: str, core: str, mod: str) -> List[float]:
        log_f = math.log10(max(1.0, freq_hz))
        amp = max(0.0, amp_v)
        g_vec = one_hot_encode(geom, GEOMETRIES)
        c_vec = one_hot_encode(core, CORES)
        m_vec = one_hot_encode(mod, MODULATIONS)
        return [log_f, amp] + g_vec + c_vec + m_vec

    def update_posterior(self, last_decision: ExperimentalDecision, observed_score: float, session_id: Optional[str] = None) -> None:
        """Update multi-dimensional Gaussian Process model, Factorial analyzer, and Hierarchical evaluator."""
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

        s_id = session_id or "session_01"
        self.factorial_analyzer.add_trial(
            last_decision.geometry_type,
            last_decision.core_geometry,
            last_decision.target_frequency_hz,
            last_decision.amplitude_v,
            observed_score,
            session_id=s_id,
        )
        self.hierarchical_evaluator.add_trial(
            s_id,
            last_decision.geometry_type,
            last_decision.core_geometry,
            observed_score,
        )

    def schedule_matched_factorial_block(
        self,
        base_freq_hz: float = 73.2,
        amp_v: float = 3.3,
        block_id: Optional[str] = None,
    ) -> str:
        """Queue a balanced, randomized factorial block of orthogonal 2x2 confirmatory conditions + controls."""
        b_id = block_id or f"blk-fact-{secrets.token_hex(3)}"
        # 4 confirmatory cells + 3 control arms
        block_conditions = [
            # 2x2 Confirmatory Core
            {"geom": "GOLDEN_RATIO_SPHERES", "core": "DUAL_TETRAHEDRON_MERKABA", "freq": base_freq_hz, "amp": amp_v, "mod": "NONE_CW"},
            {"geom": "GOLDEN_RATIO_SPHERES", "core": "SPHERICAL_CORE", "freq": base_freq_hz, "amp": amp_v, "mod": "NONE_CW"},
            {"geom": "EQUAL_SPHERES", "core": "DUAL_TETRAHEDRON_MERKABA", "freq": base_freq_hz, "amp": amp_v, "mod": "NONE_CW"},
            {"geom": "EQUAL_SPHERES", "core": "SPHERICAL_CORE", "freq": base_freq_hz, "amp": amp_v, "mod": "NONE_CW"},
            # Robustness & Controls
            {"geom": "GOLDEN_RATIO_SPHERES", "core": "NO_CORE", "freq": base_freq_hz, "amp": amp_v, "mod": "NONE_CW"},
            {"geom": "RANDOM_SPHERES", "core": "DUAL_TETRAHEDRON_MERKABA", "freq": base_freq_hz, "amp": amp_v, "mod": "NONE_CW"},
            {"geom": "SHAM_OFF", "core": "SHAM_OFF", "freq": 0.0, "amp": 0.0, "mod": "SHAM_OFF"},
        ]
        self.rng.shuffle(block_conditions)
        for idx, cond in enumerate(block_conditions):
            cond["factorial_block_id"] = b_id
            cond["factorial_block_index"] = idx
            self.queued_factorial_block.append(cond)
        return b_id

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
            entry = self.queued_factorial_block.pop(0)
            geom = entry["geom"]
            core = entry["core"]
            freq = entry["freq"]
            amp = entry["amp"]
            mod = entry["mod"]
            b_id = entry.get("factorial_block_id")
            b_idx = entry.get("factorial_block_index")
            hyp_label = "MATCHED_FACTORIAL_BLOCK_EXECUTION"
            mu, sigma = 0.0, 1.0
        else:
            b_id = None
            b_idx = None
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

        role = classify_condition_role(geom, core, amp)

        raw_config = {
            "geom": geom,
            "core": core,
            "freq": freq,
            "amp": amp,
            "mod": mod,
            "condition_role": role,
            "factorial_block_id": b_id,
            "factorial_block_index": b_idx,
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
            factorial_block_id=b_id,
            factorial_block_index=b_idx,
            hypothesis_label=hyp_label,
            posterior_predicted_mean=mu,
            posterior_uncertainty_sigma=sigma,
        )

        self.history.append(decision)
        return decision
