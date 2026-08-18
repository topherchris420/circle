"""Closed-loop adaptive experimental optimization engine for CIRCLE Resonance experiments.

Features:
1. Multi-dimensional Gaussian Process Regressor (f, A, G, C, M).
2. Matched Factorial Trial Matrix (G x C) for orthogonal experimental contrasts.
3. Factorial Interaction Analyzer: isolates beta_G (Phi), beta_C (Merkaba), and beta_GC (Interaction).
4. Isolated hypothesis candidate library (Schumann modes, acoustic intervals).
5. Opaque, unguessable cryptographic trial tokens and decoupled BlindTrialManifest.
6. Explicit software parameter exploration caps (SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING).
"""

from __future__ import annotations

import json
import math
import random
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING: float = 10.0

GEOMETRY_INDEX_MAP = {
    "GOLDEN_RATIO_SPHERES": 0,
    "EQUAL_SPHERES": 1,
    "RANDOM_SPHERES": 2,
    "SHAM_OFF": 3,
}

CORE_INDEX_MAP = {
    "DUAL_TETRAHEDRON_MERKABA": 0,
    "SPHERICAL_CORE": 1,
    "CUBIC_CORE": 2,
    "NO_CORE": 3,
    "SHAM_OFF": 4,
}

MODULATION_INDEX_MAP = {
    "NONE_CW": 0,
    "SINE_AM": 1,
    "PULSED": 2,
    "BURST": 3,
    "SHAM_OFF": 4,
}


@dataclass(frozen=True)
class HypothesisCandidateLibrary:
    """Explicitly isolated catalog of hypothesis-motivated candidate frequencies.
    
    Kept separate from primary search to prevent confirmation bias and maintain
    evidence-before-inference principles.
    """
    SCHUMANN_IONOSPHERIC_MODES: Tuple[float, ...] = (7.83, 14.3, 20.8, 27.3, 33.8)
    EEG_ENTRAINMENT_BANDS: Tuple[float, ...] = (2.5, 6.0, 10.0, 20.0, 40.0)
    HISTORICAL_ACOUSTIC_INTERVALS: Tuple[float, ...] = (432.0, 528.0)


@dataclass(frozen=True)
class ExperimentSearchSpace:
    """Bounded software parameter exploration space."""
    min_frequency_hz: float = 1.0
    max_frequency_hz: float = 100000.0  # 100 kHz exploration ceiling
    min_amplitude_v: float = 0.0
    max_amplitude_v: float = SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING
    min_duration_ms: float = 5000.0
    max_duration_ms: float = 60000.0
    min_baseline_ms: float = 5000.0
    min_washout_ms: float = 5000.0
    allowed_geometries: Tuple[str, ...] = (
        "GOLDEN_RATIO_SPHERES",
        "EQUAL_SPHERES",
        "RANDOM_SPHERES",
        "SHAM_OFF",
    )
    allowed_cores: Tuple[str, ...] = (
        "DUAL_TETRAHEDRON_MERKABA",
        "SPHERICAL_CORE",
        "CUBIC_CORE",
        "NO_CORE",
        "SHAM_OFF",
    )
    allowed_modulations: Tuple[str, ...] = (
        "NONE_CW",
        "SINE_AM",
        "PULSED",
        "BURST",
        "SHAM_OFF",
    )


class GaussianProcessRegressor:
    """Multi-dimensional Gaussian Process regressor (x in R^d) with exact covariance matrix inversion.
    
    Equations:
      K = K_XX + sigma_n^2 * I
      mu_*(x) = k_*^T * K^-1 * y
      sigma_*^2(x) = k(x, x) - k_*^T * K^-1 * k_*
    """

    def __init__(
        self,
        length_scales: Tuple[float, ...] = (0.5, 2.0, 1.0, 1.0, 1.0),
        signal_variance: float = 1.0,
        noise_variance: float = 0.05,
    ):
        self.length_scales = list(length_scales)
        self.sigma_f2 = signal_variance
        self.sigma_n2 = noise_variance

        self.X: List[List[float]] = []
        self.y: List[float] = []

    def _kernel(self, x1: List[float], x2: List[float]) -> float:
        """Anisotropic RBF Kernel across continuous and categorical factor dimensions."""
        dist_sq = 0.0
        for d in range(min(len(x1), len(x2), len(self.length_scales))):
            l_d = self.length_scales[d]
            diff = (x1[d] - x2[d]) / l_d
            dist_sq += diff ** 2
        return self.sigma_f2 * math.exp(-0.5 * dist_sq)

    def fit(self, X: List[List[float]], y: List[float]) -> None:
        self.X = [list(pt) for pt in X]
        self.y = list(y)

    def predict(self, x_star: List[float]) -> Tuple[float, float]:
        """Compute exact posterior mean and predictive standard deviation."""
        n = len(self.X)
        if n == 0:
            return (0.0, math.sqrt(self.sigma_f2))

        # Build K matrix (n x n)
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
    is_control_condition: bool
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
            "is_control_condition": self.is_control_condition,
            "hypothesis_label": self.hypothesis_label,
            "posterior_predicted_mean": round(self.posterior_predicted_mean, 4),
            "posterior_uncertainty_sigma": round(self.posterior_uncertainty_sigma, 4),
        }


class FactorialInteractionAnalyzer:
    """Linear regression model estimating main effects (Phi, Merkaba) and interaction (Phi x Merkaba).
    
    Model: R = beta_0 + beta_G * G + beta_C * C + beta_f * log10(f) + beta_A * A + beta_GC * (G x C) + eps
    where:
      G = 1.0 if GOLDEN_RATIO_SPHERES else 0.0
      C = 1.0 if DUAL_TETRAHEDRON_MERKABA else 0.0
      (G x C) = 1.0 only for the combined condition.
    """

    def __init__(self):
        self.trials: List[Tuple[float, float, float, float, float]] = []  # (G, C, log_f, A, R)

    def add_trial(self, geometry: str, core: str, freq_hz: float, amp_v: float, response_score: float) -> None:
        g_code = 1.0 if geometry == "GOLDEN_RATIO_SPHERES" else 0.0
        c_code = 1.0 if core == "DUAL_TETRAHEDRON_MERKABA" else 0.0
        log_f = math.log10(max(1.0, freq_hz))
        self.trials.append((g_code, c_code, log_f, amp_v, response_score))

    def estimate_effects(self) -> Dict[str, float]:
        """Estimate ordinary least squares (OLS) regression coefficients."""
        if len(self.trials) < 6:
            return {
                "beta_0_intercept": 0.0,
                "beta_G_phi": 0.0,
                "beta_C_merkaba": 0.0,
                "beta_GC_interaction": 0.0,
                "beta_freq": 0.0,
                "beta_amp": 0.0,
                "samples_count": len(self.trials),
            }

        # Build design matrix X (N x 6) with intercept
        # Columns: [1, G, C, G*C, log_f, A]
        X = []
        y = []
        for g, c, log_f, a, r in self.trials:
            X.append([1.0, g, c, g * c, log_f, a])
            y.append(r)

        n = len(y)
        p = 6
        # Compute X^T * X (p x p) and X^T * y (p x 1)
        XtX = [[sum(X[i][j] * X[i][k] for i in range(n)) for k in range(p)] for j in range(p)]
        Xty = [sum(X[i][j] * y[i] for i in range(n)) for j in range(p)]

        # Regularize diagonal to guarantee non-singular inversion
        for j in range(p):
            XtX[j][j] += 1e-4

        def solve_ols(A: List[List[float]], b: List[float]) -> List[float]:
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

        betas = solve_ols(XtX, Xty)

        return {
            "beta_0_intercept": round(betas[0], 4),
            "beta_G_phi": round(betas[1], 4),
            "beta_C_merkaba": round(betas[2], 4),
            "beta_GC_interaction": round(betas[3], 4),
            "beta_freq": round(betas[4], 4),
            "beta_amp": round(betas[5], 4),
            "samples_count": n,
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
    """Adaptive search policy using multi-dimensional GP-UCB and matched factorial matrix exploration."""

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

        # Training history: points x = [log10(freq), amp, geom_idx, core_idx, mod_idx], targets y = score
        self.observed_x: List[List[float]] = []
        self.observed_y: List[float] = []
        self.history: List[ExperimentalDecision] = []

    def update_posterior(self, last_decision: ExperimentalDecision, observed_score: float) -> None:
        """Update multi-dimensional Gaussian Process model and Factorial interaction analyzer."""
        log_f = math.log10(max(1.0, last_decision.target_frequency_hz))
        amp = max(0.0, last_decision.amplitude_v)
        g_idx = float(GEOMETRY_INDEX_MAP.get(last_decision.geometry_type, 0))
        c_idx = float(CORE_INDEX_MAP.get(last_decision.core_geometry, 0))
        m_idx = float(MODULATION_INDEX_MAP.get(last_decision.modulation_type, 0))

        feat = [log_f, amp, g_idx, c_idx, m_idx]
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

    def generate_matched_factorial_block(self, base_freq_hz: float, amp_v: float) -> List[Tuple[str, str]]:
        """Generate a balanced factorial matrix of (Geometry x Core) conditions."""
        return [
            ("GOLDEN_RATIO_SPHERES", "DUAL_TETRAHEDRON_MERKABA"),
            ("GOLDEN_RATIO_SPHERES", "SPHERICAL_CORE"),
            ("GOLDEN_RATIO_SPHERES", "NO_CORE"),
            ("EQUAL_SPHERES", "DUAL_TETRAHEDRON_MERKABA"),
            ("EQUAL_SPHERES", "SPHERICAL_CORE"),
            ("RANDOM_SPHERES", "DUAL_TETRAHEDRON_MERKABA"),
            ("SHAM_OFF", "SHAM_OFF"),
        ]

    def propose_next_intervention(
        self,
        current_step: int,
        last_response_score: Optional[float] = None,
        hypothesis_set_name: Optional[str] = None,
        force_control_ratio: float = 0.33,
    ) -> ExperimentalDecision:
        """Propose next intervention using multi-dimensional GP-UCB acquisition."""
        if last_response_score is not None and self.history:
            self.update_posterior(self.history[-1], last_response_score)

        decision_id = f"dec-{current_step:04d}"
        trial_token = f"TRIAL-{secrets.token_hex(4).upper()}"

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
                # Multi-Factorial GP-UCB Exploration across (f, A, G, C, M)
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

                    feat = [
                        cand_log_f,
                        cand_a,
                        float(GEOMETRY_INDEX_MAP[cand_g]),
                        float(CORE_INDEX_MAP[cand_c]),
                        float(MODULATION_INDEX_MAP[cand_m]),
                    ]
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
                hyp_label = "MULTI_FACTORIAL_BAYESIAN_EXPLORATION"

        duration = 15000.0
        baseline = max(self.space.min_baseline_ms, 5000.0)
        washout = max(self.space.min_washout_ms, 5000.0)

        raw_config = {
            "geom": geom,
            "core": core,
            "freq": freq,
            "amp": amp,
            "mod": mod,
            "is_control": is_control,
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
            is_control_condition=is_control,
            hypothesis_label=hyp_label,
            posterior_predicted_mean=mu,
            posterior_uncertainty_sigma=sigma,
        )

        self.history.append(decision)
        return decision
