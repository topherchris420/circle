"""Resonance response evaluation and artifact discrimination layer for CIRCLE.

Implements:
1. Exact double-difference sham subtraction:
     Delta_net = (mu_active - mu_active_base) - (mu_sham - mu_sham_base)
2. Condition-label permutation hypothesis testing testing H0: Delta_active = Delta_sham.
3. Aligned 4-phase empirical bootstrap confidence intervals for the reported RRI statistic.
4. Baseline-subtracted phantom delta evaluation (Delta_phantom = active - base) to eliminate DC false alarms.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ArtifactReport:
    em_pickup_risk_score: float  # 0.0 (clean) to 1.0 (dominant artifact)
    phantom_active_delta: float
    temperature_gradient_detected: bool
    phantom_control_match: bool
    flags: List[str]

    @property
    def is_valid_signal(self) -> bool:
        """Signal is valid only if artifact risk is below threshold."""
        return self.em_pickup_risk_score < 0.35 and not self.temperature_gradient_detected


@dataclass
class ResponseEvaluation:
    configuration_id: str
    blinded_token: str
    observed_rri: float  # Resonance Response Index (0.0 to 1.0)
    effect_size_d: float
    permutation_p_value: float
    bootstrap_95ci: Tuple[float, float]
    artifact_report: ArtifactReport
    repeatability_score: float
    evidence_status: str  # EXPLORATORY, INCONCLUSIVE, ARTIFACT_LIKELY, REPEATABLE_DIFFERENCE
    interpretation_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "configuration_id": self.configuration_id,
            "blinded_token": self.blinded_token,
            "resonance_response_index": round(self.observed_rri, 4),
            "effect_size_cohens_d": round(self.effect_size_d, 3),
            "permutation_p_value": round(self.permutation_p_value, 4),
            "bootstrap_95ci": [round(self.bootstrap_95ci[0], 4), round(self.bootstrap_95ci[1], 4)],
            "artifact_risk_score": round(self.artifact_report.em_pickup_risk_score, 3),
            "phantom_delta": round(self.artifact_report.phantom_active_delta, 4),
            "repeatability_score": round(self.repeatability_score, 3),
            "evidence_status": self.evidence_status,
            "interpretation_notes": self.interpretation_notes,
        }


class ResonanceAnalyzer:
    """Rigorous statistical evaluation engine for resonance response experiments."""

    def __init__(self, artifact_threshold: float = 0.35, n_permutations: int = 1000, n_bootstraps: int = 1000):
        self.artifact_threshold = artifact_threshold
        self.n_permutations = n_permutations
        self.n_bootstraps = n_bootstraps

    def _permutation_test_double_difference(
        self,
        active_base: List[float],
        active_int: List[float],
        sham_base: Optional[List[float]] = None,
        sham_int: Optional[List[float]] = None,
        seed: int = 42,
    ) -> float:
        """Permutation test testing H0: Delta_active = Delta_sham with correct denominator normalization."""
        n_ab = len(active_base)
        n_ai = len(active_int)
        delta_active = (sum(active_int) / n_ai) - (sum(active_base) / n_ab)

        if sham_base and sham_int:
            n_sb = len(sham_base)
            n_si = len(sham_int)
            delta_sham = (sum(sham_int) / n_si) - (sum(sham_base) / n_sb)
            obs_stat = abs(delta_active - delta_sham)

            # Pairwise delta pools for permutation
            # We shuffle condition assignment between active delta and sham delta
            active_deltas = [active_int[i % n_ai] - active_base[i % n_ab] for i in range(max(n_ab, n_ai))]
            sham_deltas = [sham_int[i % n_si] - sham_base[i % n_sb] for i in range(max(n_sb, n_si))]

            n_a = len(active_deltas)
            n_b = len(sham_deltas)
            combined = active_deltas + sham_deltas
            rng = random.Random(seed)
            count_extreme = 0

            for _ in range(self.n_permutations):
                shuffled = list(combined)
                rng.shuffle(shuffled)
                perm_a = shuffled[:n_a]
                perm_b = shuffled[n_a:]
                mean_a = sum(perm_a) / n_a
                mean_b = sum(perm_b) / n_b
                perm_stat = abs(mean_a - mean_b)
                if perm_stat >= obs_stat - 1e-12:
                    count_extreme += 1

            return count_extreme / float(self.n_permutations)
        else:
            # Baseline vs Intervention permutation test with correct matched denominators
            obs_stat = abs(delta_active)
            combined = active_base + active_int
            n_a = n_ab
            n_b = n_ai
            rng = random.Random(seed)
            count_extreme = 0

            for _ in range(self.n_permutations):
                shuffled = list(combined)
                rng.shuffle(shuffled)
                perm_a = shuffled[:n_a]
                perm_b = shuffled[n_a:]
                mean_a = sum(perm_a) / n_a
                mean_b = sum(perm_b) / n_b
                perm_stat = abs(mean_b - mean_a)
                if perm_stat >= obs_stat - 1e-12:
                    count_extreme += 1

            return count_extreme / float(self.n_permutations)

    def _bootstrap_rri_ci_aligned(
        self,
        active_base: List[float],
        active_int: List[float],
        sham_base: Optional[List[float]],
        sham_int: Optional[List[float]],
        em_risk: float,
        seed: int = 42,
    ) -> Tuple[float, float]:
        """Compute empirical 95% bootstrap CI estimating the exact same sham-adjusted RRI statistic."""
        rng = random.Random(seed)
        rri_dist: List[float] = []

        n_ab, n_ai = len(active_base), len(active_int)
        n_sb = len(sham_base) if sham_base else 0
        n_si = len(sham_int) if sham_int else 0

        for _ in range(self.n_bootstraps):
            # Resample active phases
            resamp_ab = [active_base[rng.randint(0, n_ab - 1)] for _ in range(n_ab)]
            resamp_ai = [active_int[rng.randint(0, n_ai - 1)] for _ in range(n_ai)]

            m_ab = sum(resamp_ab) / n_ab
            m_ai = sum(resamp_ai) / n_ai
            v_ab = sum((x - m_ab) ** 2 for x in resamp_ab) / max(1, n_ab - 1)
            v_ai = sum((x - m_ai) ** 2 for x in resamp_ai) / max(1, n_ai - 1)

            delta_act = m_ai - m_ab

            # Resample sham phases if provided
            if sham_base and sham_int and n_sb > 0 and n_si > 0:
                resamp_sb = [sham_base[rng.randint(0, n_sb - 1)] for _ in range(n_sb)]
                resamp_si = [sham_int[rng.randint(0, n_si - 1)] for _ in range(n_si)]

                m_sb = sum(resamp_sb) / n_sb
                m_si = sum(resamp_si) / n_si
                v_sb = sum((x - m_sb) ** 2 for x in resamp_sb) / max(1, n_sb - 1)
                v_si = sum((x - m_si) ** 2 for x in resamp_si) / max(1, n_si - 1)

                delta_sham = m_si - m_sb
                net_delta = delta_act - delta_sham
                pooled_sd = math.sqrt(max(1e-6, (v_ab + v_ai + v_sb + v_si) / 4.0))
            else:
                net_delta = delta_act
                pooled_sd = math.sqrt(max(1e-6, (v_ab + v_ai) / 2.0))

            b_d = net_delta / pooled_sd
            b_rri = (abs(b_d) / (1.0 + abs(b_d))) * (1.0 - em_risk)
            rri_dist.append(b_rri)

        rri_dist.sort()
        ci_low = rri_dist[int(0.025 * self.n_bootstraps)]
        ci_high = rri_dist[int(0.975 * self.n_bootstraps)]
        return (round(ci_low, 4), round(ci_high, 4))

    def evaluate_trial(
        self,
        config_id: str,
        blinded_token: str,
        baseline_signal: List[float],
        intervention_signal: List[float],
        washout_signal: List[float],
        sham_baseline_signal: Optional[List[float]] = None,
        sham_intervention_signal: Optional[List[float]] = None,
        phantom_baseline_signal: Optional[List[float]] = None,
        phantom_active_signal: Optional[List[float]] = None,
        rf_field_strength_v_m: float = 0.5,
        temp_delta_c: float = 0.1,
        prior_trial_scores: Optional[List[float]] = None,
    ) -> ResponseEvaluation:
        """Evaluate trial with aligned double-difference contrast, permutation p-value, and bootstrap CI."""
        if not baseline_signal or not intervention_signal or not washout_signal:
            raise ValueError("All trial phases must contain data.")

        mean_base = sum(baseline_signal) / len(baseline_signal)
        mean_int = sum(intervention_signal) / len(intervention_signal)
        raw_bio_delta = mean_int - mean_base

        var_base = sum((x - mean_base) ** 2 for x in baseline_signal) / max(1, len(baseline_signal) - 1)
        var_int = sum((x - mean_int) ** 2 for x in intervention_signal) / max(1, len(intervention_signal) - 1)

        # 1. Sham Subtraction (Double Difference)
        if sham_baseline_signal and sham_intervention_signal:
            mean_sham_base = sum(sham_baseline_signal) / len(sham_baseline_signal)
            mean_sham_int = sum(sham_intervention_signal) / len(sham_intervention_signal)
            sham_delta = mean_sham_int - mean_sham_base
            net_delta = raw_bio_delta - sham_delta

            var_sb = sum((x - mean_sham_base) ** 2 for x in sham_baseline_signal) / max(1, len(sham_baseline_signal) - 1)
            var_si = sum((x - mean_sham_int) ** 2 for x in sham_intervention_signal) / max(1, len(sham_intervention_signal) - 1)
            pooled_sd = math.sqrt(max(1e-6, (var_base + var_int + var_sb + var_si) / 4.0))
        else:
            net_delta = raw_bio_delta
            pooled_sd = math.sqrt(max(1e-6, (var_base + var_int) / 2.0))

        cohens_d = net_delta / pooled_sd

        # 2. Phantom Baseline-Subtracted Delta Evaluation
        artifact_flags: List[str] = []
        em_risk = min(1.0, rf_field_strength_v_m / 10.0)
        phantom_delta = 0.0
        phantom_match = True

        if phantom_baseline_signal and phantom_active_signal:
            p_base = sum(phantom_baseline_signal) / len(phantom_baseline_signal)
            p_act = sum(phantom_active_signal) / len(phantom_active_signal)
            phantom_delta = p_act - p_base
            if abs(phantom_delta) > 0.40 * abs(raw_bio_delta) and abs(phantom_delta) > 0.10:
                artifact_flags.append("DIRECT_EM_INSTRUMENTATION_PICKUP")
                em_risk = max(em_risk, 0.80)
                phantom_match = False

        if rf_field_strength_v_m > 5.0:
            artifact_flags.append("HIGH_NEAR_FIELD_RF")

        temp_risk = temp_delta_c > 0.80
        if temp_risk:
            artifact_flags.append("THERMAL_DRIFT_INTERFERENCE")

        artifact_rep = ArtifactReport(
            em_pickup_risk_score=round(em_risk, 3),
            phantom_active_delta=round(phantom_delta, 4),
            temperature_gradient_detected=temp_risk,
            phantom_control_match=phantom_match,
            flags=artifact_flags,
        )

        # 3. Aligned Double-Difference Permutation Test & Aligned Bootstrap CI
        p_val = self._permutation_test_double_difference(
            baseline_signal,
            intervention_signal,
            sham_baseline_signal,
            sham_intervention_signal,
        )
        ci_low, ci_high = self._bootstrap_rri_ci_aligned(
            baseline_signal,
            intervention_signal,
            sham_baseline_signal,
            sham_intervention_signal,
            em_risk,
        )

        # 4. Resonance Response Index (RRI)
        raw_response = abs(cohens_d) / (1.0 + abs(cohens_d))
        rri = raw_response * (1.0 - em_risk)

        # 5. Repeatability score
        if prior_trial_scores and len(prior_trial_scores) > 0:
            avg_prior = sum(prior_trial_scores) / len(prior_trial_scores)
            repeatability = max(0.0, 1.0 - abs(rri - avg_prior))
        else:
            repeatability = 0.5

        # 6. Strict Evidence Status Assignment
        if not artifact_rep.is_valid_signal:
            status = "ARTIFACT_LIKELY"
            notes = "Observed variation matches electronic phantom delta or thermal shift (instrumentation pickup)."
        elif p_val < 0.01 and ci_low > 0.20 and repeatability > 0.75 and abs(cohens_d) > 0.80:
            status = "REPEATABLE_DIFFERENCE"
            notes = f"Repeatable contrast verified beyond sham (permutation p={p_val:.4f}, bootstrap CI=[{ci_low:.3f}, {ci_high:.3f}])."
        elif p_val < 0.05 and abs(cohens_d) >= 0.20:
            status = "EXPLORATORY"
            notes = f"Initial exploratory contrast (permutation p={p_val:.4f}); requires multi-trial replication."
        else:
            status = "INCONCLUSIVE"
            notes = f"No statistically significant difference from sham or baseline (permutation p={p_val:.4f})."

        return ResponseEvaluation(
            configuration_id=config_id,
            blinded_token=blinded_token,
            observed_rri=rri,
            effect_size_d=cohens_d,
            permutation_p_value=p_val,
            bootstrap_95ci=(ci_low, ci_high),
            artifact_report=artifact_rep,
            repeatability_score=repeatability,
            evidence_status=status,
            interpretation_notes=notes,
        )
