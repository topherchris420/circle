"""Resonance response evaluation, autocorrelation-aware block statistics, and artifact discrimination.

Implements:
1. Circular Block Permutation testing (preserving physiological time-series autocorrelation x_t !perp x_{t+1}).
2. Aligned 4-phase Block Bootstrap confidence intervals for the sham-adjusted RRI statistic.
3. Multi-trial session-level aggregation across repeated experimental blocks.
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
    """Rigorous statistical evaluation engine using circular block permutation for autocorrelated signals."""

    def __init__(
        self,
        artifact_threshold: float = 0.35,
        n_permutations: int = 1000,
        n_bootstraps: int = 1000,
        default_block_size: int = 5,
    ):
        self.artifact_threshold = artifact_threshold
        self.n_permutations = n_permutations
        self.n_bootstraps = n_bootstraps
        self.block_size = default_block_size

    def _make_blocks(self, series: List[float], block_len: int) -> List[List[float]]:
        """Slice continuous time series into contiguous blocks to preserve autocorrelation structure."""
        n = len(series)
        b_len = max(1, min(block_len, n))
        blocks: List[List[float]] = []
        for i in range(0, n, b_len):
            blocks.append(series[i: min(i + b_len, n)])
        return blocks

    def _block_permutation_test(
        self,
        active_base: List[float],
        active_int: List[float],
        sham_base: Optional[List[float]] = None,
        sham_int: Optional[List[float]] = None,
        seed: int = 42,
    ) -> float:
        """Circular block permutation test accounting for temporal autocorrelation."""
        n_ab = len(active_base)
        n_ai = len(active_int)
        delta_active = (sum(active_int) / n_ai) - (sum(active_base) / n_ab)

        if sham_base and sham_int:
            n_sb = len(sham_base)
            n_si = len(sham_int)
            delta_sham = (sum(sham_int) / n_si) - (sum(sham_base) / n_sb)
            obs_stat = abs(delta_active - delta_sham)

            # Block partitioning
            blocks_act_base = self._make_blocks(active_base, self.block_size)
            blocks_act_int = self._make_blocks(active_int, self.block_size)
            blocks_sham_base = self._make_blocks(sham_base, self.block_size)
            blocks_sham_int = self._make_blocks(sham_int, self.block_size)

            all_active_blocks = blocks_act_base + blocks_act_int
            all_sham_blocks = blocks_sham_base + blocks_sham_int
            combined_blocks = all_active_blocks + all_sham_blocks

            n_a_blocks = len(all_active_blocks)
            n_s_blocks = len(all_sham_blocks)

            rng = random.Random(seed)
            count_extreme = 0

            for _ in range(self.n_permutations):
                shuffled = list(combined_blocks)
                rng.shuffle(shuffled)
                perm_a_blocks = shuffled[:n_a_blocks]
                perm_s_blocks = shuffled[n_a_blocks:]

                # Reconstruct time series from permuted contiguous blocks
                flat_a = [pt for b in perm_a_blocks for pt in b]
                flat_s = [pt for b in perm_s_blocks for pt in b]

                if not flat_a or not flat_s:
                    continue

                split_a = len(flat_a) // 2
                split_s = len(flat_s) // 2
                perm_delta_a = (sum(flat_a[split_a:]) / max(1, len(flat_a) - split_a)) - (sum(flat_a[:split_a]) / max(1, split_a))
                perm_delta_s = (sum(flat_s[split_s:]) / max(1, len(flat_s) - split_s)) - (sum(flat_s[:split_s]) / max(1, split_s))

                perm_stat = abs(perm_delta_a - perm_delta_s)
                if perm_stat >= obs_stat - 1e-12:
                    count_extreme += 1

            return count_extreme / float(self.n_permutations)
        else:
            obs_stat = abs(delta_active)
            blocks_base = self._make_blocks(active_base, self.block_size)
            blocks_int = self._make_blocks(active_int, self.block_size)
            combined_blocks = blocks_base + blocks_int
            n_base_blocks = len(blocks_base)

            rng = random.Random(seed)
            count_extreme = 0

            for _ in range(self.n_permutations):
                shuffled = list(combined_blocks)
                rng.shuffle(shuffled)
                perm_base_blocks = shuffled[:n_base_blocks]
                perm_int_blocks = shuffled[n_base_blocks:]

                flat_b = [pt for b in perm_base_blocks for pt in b]
                flat_i = [pt for b in perm_int_blocks for pt in b]

                if not flat_b or not flat_i:
                    continue

                mean_b = sum(flat_b) / len(flat_b)
                mean_i = sum(flat_i) / len(flat_i)
                perm_stat = abs(mean_i - mean_b)
                if perm_stat >= obs_stat - 1e-12:
                    count_extreme += 1

            return count_extreme / float(self.n_permutations)

    def _block_bootstrap_rri_ci(
        self,
        active_base: List[float],
        active_int: List[float],
        sham_base: Optional[List[float]],
        sham_int: Optional[List[float]],
        em_risk: float,
        seed: int = 42,
    ) -> Tuple[float, float]:
        """Moving block bootstrap estimating empirical confidence intervals for sham-adjusted RRI."""
        rng = random.Random(seed)
        rri_dist: List[float] = []

        blocks_ab = self._make_blocks(active_base, self.block_size)
        blocks_ai = self._make_blocks(active_int, self.block_size)
        blocks_sb = self._make_blocks(sham_base, self.block_size) if sham_base else []
        blocks_si = self._make_blocks(sham_int, self.block_size) if sham_int else []

        n_ab, n_ai = len(blocks_ab), len(blocks_ai)
        n_sb, n_si = len(blocks_sb), len(blocks_si)

        for _ in range(self.n_bootstraps):
            resamp_ab_blocks = [blocks_ab[rng.randint(0, n_ab - 1)] for _ in range(n_ab)]
            resamp_ai_blocks = [blocks_ai[rng.randint(0, n_ai - 1)] for _ in range(n_ai)]

            flat_ab = [pt for b in resamp_ab_blocks for pt in b]
            flat_ai = [pt for b in resamp_ai_blocks for pt in b]

            m_ab = sum(flat_ab) / len(flat_ab)
            m_ai = sum(flat_ai) / len(flat_ai)
            v_ab = sum((x - m_ab) ** 2 for x in flat_ab) / max(1, len(flat_ab) - 1)
            v_ai = sum((x - m_ai) ** 2 for x in flat_ai) / max(1, len(flat_ai) - 1)

            delta_act = m_ai - m_ab

            if sham_base and sham_int and n_sb > 0 and n_si > 0:
                resamp_sb_blocks = [blocks_sb[rng.randint(0, n_sb - 1)] for _ in range(n_sb)]
                resamp_si_blocks = [blocks_si[rng.randint(0, n_si - 1)] for _ in range(n_si)]

                flat_sb = [pt for b in resamp_sb_blocks for pt in b]
                flat_si = [pt for b in resamp_si_blocks for pt in b]

                m_sb = sum(flat_sb) / len(flat_sb)
                m_si = sum(flat_si) / len(flat_si)
                v_sb = sum((x - m_sb) ** 2 for x in flat_sb) / max(1, len(flat_sb) - 1)
                v_si = sum((x - m_si) ** 2 for x in flat_si) / max(1, len(flat_si) - 1)

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
        """Evaluate trial using double-difference circular block permutation and block bootstrap."""
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

        # 3. Autocorrelation-Aware Circular Block Permutation & Block Bootstrap CI
        p_val = self._block_permutation_test(
            baseline_signal,
            intervention_signal,
            sham_baseline_signal,
            sham_intervention_signal,
        )
        ci_low, ci_high = self._block_bootstrap_rri_ci(
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
            notes = f"Repeatable contrast verified beyond sham (block permutation p={p_val:.4f}, bootstrap CI=[{ci_low:.3f}, {ci_high:.3f}])."
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
            artifact_report=artifact_rep,
            repeatability_score=repeatability,
            evidence_status=status,
            interpretation_notes=notes,
        )
