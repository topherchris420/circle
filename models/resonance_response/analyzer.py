"""Resonance response evaluation, overlapping moving-block bootstrap, and artifact discrimination.

Implements:
1. Phase-stationary autocorrelation time estimation (tau = max(tau_base, tau_int) on separate stationary phases).
2. Identical sample window alignment for observed T_obs and permuted T_perm statistics.
3. Contiguous Block-Level Sham Permutation (swapping entire contiguous blocks L = max(2, 2*tau)).
4. True Overlapping Moving Block Bootstrap (Künsch 1989 / Politis & Romano 1994).
5. True Circular-Shift Permutation (x_{(t + tau) mod N}) preserving 100% of time-series autocorrelation.
6. Baseline-subtracted phantom delta evaluation (Delta_phantom = active - base) to eliminate DC false alarms.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def estimate_autocorrelation_time(series: List[float], max_lag: int = 20) -> int:
    """Estimate empirical decorrelation time tau_decorr from the sample autocorrelation function."""
    n = len(series)
    if n < 4:
        return 1

    mean = sum(series) / n
    var = sum((x - mean) ** 2 for x in series)
    if var < 1e-12:
        return 1

    limit_lag = min(max_lag, n // 2)
    threshold = 1.0 / math.e  # ~0.3678

    for k in range(1, limit_lag + 1):
        cov = sum((series[t] - mean) * (series[t + k] - mean) for t in range(n - k))
        rho_k = cov / var
        if rho_k <= threshold or rho_k <= 0:
            return k

    return max(1, limit_lag // 2)


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
    autocorrelation_tau: int
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
            "autocorrelation_tau": self.autocorrelation_tau,
            "artifact_risk_score": round(self.artifact_report.em_pickup_risk_score, 3),
            "phantom_delta": round(self.artifact_report.phantom_active_delta, 4),
            "repeatability_score": round(self.repeatability_score, 3),
            "evidence_status": self.evidence_status,
            "interpretation_notes": self.interpretation_notes,
        }


class ResonanceAnalyzer:
    """Rigorous statistical evaluation engine using circular shift, contiguous block sham permutation, and moving block bootstrap."""

    def __init__(
        self,
        artifact_threshold: float = 0.35,
        n_permutations: int = 1000,
        n_bootstraps: int = 1000,
    ):
        self.artifact_threshold = artifact_threshold
        self.n_permutations = n_permutations
        self.n_bootstraps = n_bootstraps

    def _permutation_test_contiguous_blocks_or_circular(
        self,
        active_base: List[float],
        active_int: List[float],
        sham_base: Optional[List[float]] = None,
        sham_int: Optional[List[float]] = None,
        seed: int = 42,
    ) -> Tuple[float, int]:
        """Permutation testing swapping entire contiguous blocks over an identical sample window."""
        # 1. Phase-stationary autocorrelation estimation (avoids step artifact between phases)
        tau_base = estimate_autocorrelation_time(active_base)
        tau_int = estimate_autocorrelation_time(active_int)
        tau = max(tau_base, tau_int)

        if sham_base and sham_int:
            # Determine common sample length across all four streams
            n_common = min(len(active_base), len(active_int), len(sham_base), len(sham_int))
            max_b_len = max(2, n_common // 4)
            block_len = max(2, min(max_b_len, max(2, 2 * tau)))
            num_blocks = n_common // block_len
            n_used = num_blocks * block_len

            # Truncate all four series to exact identical sample window
            ab_used = active_base[:n_used]
            ai_used = active_int[:n_used]
            sb_used = sham_base[:n_used]
            si_used = sham_int[:n_used]

            # Compute observed test statistic on exact used window
            delta_act = (sum(ai_used) / n_used) - (sum(ab_used) / n_used)
            delta_sham = (sum(si_used) / n_used) - (sum(sb_used) / n_used)
            obs_stat = abs(delta_act - delta_sham)

            # Sliced contiguous blocks
            blocks_ab = [ab_used[i * block_len: (i + 1) * block_len] for i in range(num_blocks)]
            blocks_ai = [ai_used[i * block_len: (i + 1) * block_len] for i in range(num_blocks)]
            blocks_sb = [sb_used[i * block_len: (i + 1) * block_len] for i in range(num_blocks)]
            blocks_si = [si_used[i * block_len: (i + 1) * block_len] for i in range(num_blocks)]

            rng = random.Random(seed)
            count_extreme = 0

            for _ in range(self.n_permutations):
                p_ab, p_ai = [], []
                p_sb, p_si = [], []
                for b_idx in range(num_blocks):
                    if rng.random() < 0.5:
                        p_ab.extend(blocks_ab[b_idx])
                        p_ai.extend(blocks_ai[b_idx])
                        p_sb.extend(blocks_sb[b_idx])
                        p_si.extend(blocks_si[b_idx])
                    else:
                        p_ab.extend(blocks_sb[b_idx])
                        p_ai.extend(blocks_si[b_idx])
                        p_sb.extend(blocks_ab[b_idx])
                        p_si.extend(blocks_ai[b_idx])

                m_ab = sum(p_ab) / n_used
                m_ai = sum(p_ai) / n_used
                m_sb = sum(p_sb) / n_used
                m_si = sum(p_si) / n_used

                perm_delta_act = m_ai - m_ab
                perm_delta_sham = m_si - m_sb
                perm_stat = abs(perm_delta_act - perm_delta_sham)

                if perm_stat >= obs_stat - 1e-12:
                    count_extreme += 1

            p_val = count_extreme / float(self.n_permutations)
            return p_val, tau
        else:
            n_ab = len(active_base)
            n_ai = len(active_int)
            delta_active = (sum(active_int) / n_ai) - (sum(active_base) / n_ab)
            obs_stat = abs(delta_active)

            combined = active_base + active_int
            n_total = len(combined)
            rng = random.Random(seed)
            count_extreme = 0

            for _ in range(self.n_permutations):
                shift = rng.randint(1, n_total - 1)
                shifted = [combined[(t + shift) % n_total] for t in range(n_total)]
                shifted_base = shifted[:n_ab]
                shifted_int = shifted[n_ab:]

                m_b = sum(shifted_base) / n_ab
                m_i = sum(shifted_int) / n_ai
                perm_stat = abs(m_i - m_b)
                if perm_stat >= obs_stat - 1e-12:
                    count_extreme += 1

            p_val = count_extreme / float(self.n_permutations)
            return p_val, tau

    def _overlapping_moving_block_bootstrap(
        self,
        active_base: List[float],
        active_int: List[float],
        sham_base: Optional[List[float]],
        sham_int: Optional[List[float]],
        em_risk: float,
        tau: int,
        seed: int = 42,
    ) -> Tuple[float, float]:
        """True Overlapping Moving Block Bootstrap (Künsch 1989 / Politis & Romano 1994)."""
        block_len = max(5, min(len(active_base) // 2, 2 * tau))
        rng = random.Random(seed)
        rri_dist: List[float] = []

        def extract_overlapping_blocks(series: List[float], L: int) -> List[List[float]]:
            n = len(series)
            if n <= L:
                return [series]
            return [series[i: i + L] for i in range(n - L + 1)]

        blocks_ab = extract_overlapping_blocks(active_base, block_len)
        blocks_ai = extract_overlapping_blocks(active_int, block_len)
        blocks_sb = extract_overlapping_blocks(sham_base, block_len) if sham_base else []
        blocks_si = extract_overlapping_blocks(sham_int, block_len) if sham_int else []

        n_ab_pts, n_ai_pts = len(active_base), len(active_int)
        n_sb_pts = len(sham_base) if sham_base else 0
        n_si_pts = len(sham_int) if sham_int else 0

        def sample_series(overlap_blocks: List[List[float]], target_n: int) -> List[float]:
            out: List[float] = []
            while len(out) < target_n:
                b = overlap_blocks[rng.randint(0, len(overlap_blocks) - 1)]
                out.extend(b)
            return out[:target_n]

        for _ in range(self.n_bootstraps):
            resamp_ab = sample_series(blocks_ab, n_ab_pts)
            resamp_ai = sample_series(blocks_ai, n_ai_pts)

            m_ab = sum(resamp_ab) / n_ab_pts
            m_ai = sum(resamp_ai) / n_ai_pts
            v_ab = sum((x - m_ab) ** 2 for x in resamp_ab) / max(1, n_ab_pts - 1)
            v_ai = sum((x - m_ai) ** 2 for x in resamp_ai) / max(1, n_ai_pts - 1)

            delta_act = m_ai - m_ab

            if sham_base and sham_int and n_sb_pts > 0 and n_si_pts > 0:
                resamp_sb = sample_series(blocks_sb, n_sb_pts)
                resamp_si = sample_series(blocks_si, n_si_pts)

                m_sb = sum(resamp_sb) / n_sb_pts
                m_si = sum(resamp_si) / n_si_pts
                v_sb = sum((x - m_sb) ** 2 for x in resamp_sb) / max(1, n_sb_pts - 1)
                v_si = sum((x - m_si) ** 2 for x in resamp_si) / max(1, n_si_pts - 1)

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
        """Evaluate trial using double-difference contiguous block permutation and moving block bootstrap."""
        if not baseline_signal or not intervention_signal or not washout_signal:
            raise ValueError("All trial phases must contain data.")

        mean_base = sum(baseline_signal) / len(baseline_signal)
        mean_int = sum(intervention_signal) / len(intervention_signal)
        raw_bio_delta = mean_int - mean_base

        var_base = sum((x - mean_base) ** 2 for x in baseline_signal) / max(1, len(baseline_signal) - 1)
        var_int = sum((x - mean_int) ** 2 for x in intervention_signal) / max(1, len(intervention_signal) - 1)

        # 1. Double-Difference Sham Subtraction
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

        # 3. Autocorrelation-Aware Contiguous Block Permutation & Moving Block Bootstrap
        p_val, tau = self._permutation_test_contiguous_blocks_or_circular(
            baseline_signal,
            intervention_signal,
            sham_baseline_signal,
            sham_intervention_signal,
        )
        ci_low, ci_high = self._overlapping_moving_block_bootstrap(
            baseline_signal,
            intervention_signal,
            sham_baseline_signal,
            sham_intervention_signal,
            em_risk,
            tau=tau,
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
            notes = f"Repeatable contrast verified beyond sham (block permutation p={p_val:.4f}, moving-block bootstrap CI=[{ci_low:.3f}, {ci_high:.3f}], tau={tau})."
        elif p_val < 0.05 and abs(cohens_d) >= 0.20:
            status = "EXPLORATORY"
            notes = f"Initial exploratory contrast (block permutation p={p_val:.4f}); requires multi-trial replication."
        else:
            status = "INCONCLUSIVE"
            notes = f"No statistically significant difference from sham or baseline (block permutation p={p_val:.4f})."

        return ResponseEvaluation(
            configuration_id=config_id,
            blinded_token=blinded_token,
            observed_rri=rri,
            effect_size_d=cohens_d,
            permutation_p_value=p_val,
            bootstrap_95ci=(ci_low, ci_high),
            autocorrelation_tau=tau,
            artifact_report=artifact_rep,
            repeatability_score=repeatability,
            evidence_status=status,
            interpretation_notes=notes,
        )
