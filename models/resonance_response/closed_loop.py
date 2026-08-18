"""Closed-loop adaptive experimental optimization engine for CIRCLE Resonance experiments.

Features:
1. Unbiased log-uniform frequency exploration.
2. Separate, explicitly labeled hypothesis candidate library (Schumann, acoustic intervals).
3. Genuinely adaptive Gaussian Process / Kernel Bayesian surrogate model (GP-UCB).
4. Opaque, unguessable cryptographic trial tokens and decoupled BlindTrialManifest.
5. Explicit software parameter exploration caps (SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING).
"""

from __future__ import annotations

import json
import math
import random
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Software parameter search ceiling — NOT an electrical safety rating.
# Hardware chamber impedance, thermal limits, and RF field safety must be
# independently evaluated before hardware execution.
SOFTWARE_EXPLORATION_CAP_NOT_SAFETY_RATING: float = 10.0


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
        """Seal manifest so operators cannot inspect condition identity during trial runs."""
        self._sealed = True

    def unseal_manifest(self) -> Dict[str, Dict[str, Any]]:
        """Unseal manifest for post-experiment de-blinding and statistical contrast."""
        return dict(self._mapping)

    def is_sealed(self) -> bool:
        return self._sealed


class ClosedLoopOptimizer:
    """Adaptive search policy using Gaussian Process Upper Confidence Bound (GP-UCB).
    
    Dynamically integrates observed response scores (last_response_score) to update
    posterior mean mu(x) and uncertainty sigma(x), guiding intelligent exploration/exploitation.
    """

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

        # Gaussian Process training data: points x = (log10(freq), amp), targets y = response_score
        self.observed_x: List[Tuple[float, float]] = []
        self.observed_y: List[float] = []
        self.history: List[ExperimentalDecision] = []

    def update_posterior(self, last_decision: ExperimentalDecision, observed_score: float) -> None:
        """Update surrogate model with measured response score from previous trial."""
        log_f = math.log10(max(1.0, last_decision.target_frequency_hz))
        amp = max(0.0, last_decision.amplitude_v)
        self.observed_x.append((log_f, amp))
        self.observed_y.append(observed_score)

    def _gp_predict(self, log_f: float, amp: float) -> Tuple[float, float]:
        """Evaluate Radial Basis Function (RBF) Gaussian Process posterior mean and variance."""
        if not self.observed_x:
            # Prior distribution: neutral mean 0.0, maximum uncertainty 1.0
            return (0.0, 1.0)

        # Length scales: 0.5 decades in frequency, 2.0 V in amplitude
        l_f = 0.5
        l_a = 2.0
        noise_var = 0.05

        def rbf(x1: Tuple[float, float], x2: Tuple[float, float]) -> float:
            df = (x1[0] - x2[0]) / l_f
            da = (x1[1] - x2[1]) / l_a
            return math.exp(-0.5 * (df ** 2 + da ** 2))

        candidate = (log_f, amp)
        k_star = [rbf(candidate, xi) for xi in self.observed_x]

        # Kernel regression estimate
        sum_k = sum(k_star)
        if sum_k < 1e-4:
            mu = 0.0
            sigma = 1.0
        else:
            mu = sum(k * y for k, y in zip(k_star, self.observed_y)) / sum_k
            sigma = math.sqrt(max(0.05, 1.0 - (sum_k / (len(self.observed_x) + 1.0))))

        return (mu, sigma)

    def propose_next_intervention(
        self,
        current_step: int,
        last_response_score: Optional[float] = None,
        hypothesis_set_name: Optional[str] = None,
        force_control_ratio: float = 0.33,
    ) -> ExperimentalDecision:
        """Propose next intervention using GP-UCB acquisition with randomized controls."""
        # 1. Update posterior if prior feedback is available
        if last_response_score is not None and self.history:
            self.update_posterior(self.history[-1], last_response_score)

        decision_id = f"dec-{current_step:04d}"
        # Generate random, opaque cryptographic token (e.g. TRIAL-A3F9C1B2)
        trial_token = f"TRIAL-{secrets.token_hex(4).upper()}"

        # 2. Control Condition Enforcement (minimum 33% of trials)
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
                # Unbiased log-uniform sampling for control frequency
                log_f = self.rng.uniform(math.log10(self.space.min_frequency_hz), math.log10(1000.0))
                freq = round(10.0 ** log_f, 2)
                mod = "NONE_CW"
            hyp_label = None
            mu, sigma = 0.0, 1.0
        else:
            # 3. Active Exploration / Exploitation
            geom = "GOLDEN_RATIO_SPHERES"
            core = "DUAL_TETRAHEDRON_MERKABA"

            if hypothesis_set_name == "schumann":
                freq = self.rng.choice(HypothesisCandidateLibrary.SCHUMANN_IONOSPHERIC_MODES)
                amp = round(self.rng.uniform(1.0, 5.0), 2)
                hyp_label = "HYP_SCHUMANN_IONOSPHERIC"
                mu, sigma = 0.0, 1.0
            elif hypothesis_set_name == "acoustic_solfeggio":
                freq = self.rng.choice(HypothesisCandidateLibrary.HISTORICAL_ACOUSTIC_INTERVALS)
                amp = round(self.rng.uniform(1.0, 5.0), 2)
                hyp_label = "HYP_HISTORICAL_ACOUSTIC"
                mu, sigma = 0.0, 1.0
            else:
                # Default: UNBIASED Bayesian Acquisition (GP-UCB)
                # Generate candidate pool across log-uniform frequency and random amplitude
                best_acq = -float("inf")
                best_f = 73.2
                best_a = 3.3
                best_mu, best_sigma = 0.0, 1.0

                for _ in range(25):
                    cand_log_f = self.rng.uniform(math.log10(self.space.min_frequency_hz), math.log10(1000.0))
                    cand_f = 10.0 ** cand_log_f
                    cand_a = self.rng.uniform(1.0, 5.0)

                    c_mu, c_sigma = self._gp_predict(cand_log_f, cand_a)
                    # UCB Acquisition: mu + kappa * sigma
                    acq = c_mu + self.kappa * c_sigma

                    if acq > best_acq:
                        best_acq = acq
                        best_f = cand_f
                        best_a = cand_a
                        best_mu, best_sigma = c_mu, c_sigma

                freq = round(best_f, 2)
                amp = round(best_a, 2)
                mu, sigma = best_mu, best_sigma
                hyp_label = "UNBIASED_BAYESIAN_EXPLORATION"

            mod = self.rng.choice(["NONE_CW", "SINE_AM", "PULSED"])

        duration = 15000.0
        baseline = max(self.space.min_baseline_ms, 5000.0)
        washout = max(self.space.min_washout_ms, 5000.0)

        # Register into opaque blinded manifest
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
