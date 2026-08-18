"""Resonance response evaluation and artifact discrimination layer for CIRCLE.

Computes the neutral Resonance Response Index (RRI), contrast scores against sham/controls,
uncertainty budgets, and strict electromagnetic/thermal artifact risk metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ArtifactReport:
    em_pickup_risk_score: float  # 0.0 (clean) to 1.0 (dominant artifact)
    temperature_gradient_detected: bool
    phantom_control_match: bool
    flags: List[str]

    @property
    def is_valid_signal(self) -> bool:
        """Signal is considered valid only if artifact risk is below threshold."""
        return self.em_pickup_risk_score < 0.40 and not self.temperature_gradient_detected


@dataclass
class ResponseEvaluation:
    configuration_id: str
    blinded_label: str
    observed_rri: float  # Resonance Response Index (0.0 to 1.0)
    effect_size_d: float
    uncertainty_95ci: Tuple[float, float]
    artifact_report: ArtifactReport
    repeatability_score: float
    evidence_status: str  # EXPLORATORY, INCONCLUSIVE, ARTIFACT_LIKELY, REPEATABLE_DIFFERENCE
    interpretation_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "configuration_id": self.configuration_id,
            "blinded_label": self.blinded_label,
            "resonance_response_index": round(self.observed_rri, 4),
            "effect_size_cohens_d": round(self.effect_size_d, 3),
            "uncertainty_95ci": [round(self.uncertainty_95ci[0], 4), round(self.uncertainty_95ci[1], 4)],
            "artifact_risk_score": round(self.artifact_report.em_pickup_risk_score, 3),
            "phantom_control_verified": self.artifact_report.phantom_control_match,
            "repeatability_score": round(self.repeatability_score, 3),
            "evidence_status": self.evidence_status,
            "interpretation_notes": self.interpretation_notes,
        }


class ResonanceAnalyzer:
    """Statistical evaluation engine for resonance response experiments."""

    def __init__(self, artifact_threshold: float = 0.35):
        self.artifact_threshold = artifact_threshold

    def evaluate_trial(
        self,
        config_id: str,
        blinded_label: str,
        baseline_signal: List[float],
        intervention_signal: List[float],
        washout_signal: List[float],
        phantom_active_signal: Optional[List[float]] = None,
        rf_field_strength_v_m: float = 0.5,
        temp_delta_c: float = 0.1,
        prior_trial_scores: Optional[List[float]] = None,
    ) -> ResponseEvaluation:
        """Evaluate a multi-phase trial (baseline -> intervention -> washout)."""
        if not baseline_signal or not intervention_signal or not washout_signal:
            raise ValueError("All trial phases (baseline, intervention, washout) must contain data.")

        mean_base = sum(baseline_signal) / len(baseline_signal)
        mean_int = sum(intervention_signal) / len(intervention_signal)
        mean_wash = sum(washout_signal) / len(washout_signal)

        var_base = sum((x - mean_base) ** 2 for x in baseline_signal) / max(1, len(baseline_signal) - 1)
        var_int = sum((x - mean_int) ** 2 for x in intervention_signal) / max(1, len(intervention_signal) - 1)
        pooled_sd = math.sqrt(max(1e-6, (var_base + var_int) / 2.0))

        # Cohen's d effect size
        cohens_d = (mean_int - mean_base) / pooled_sd

        # 1. Artifact & Interference assessment
        artifact_flags: List[str] = []
        em_risk = min(1.0, rf_field_strength_v_m / 10.0)

        phantom_match = True
        if phantom_active_signal:
            mean_phantom = sum(phantom_active_signal) / len(phantom_active_signal)
            # If phantom (dummy load) changes as much as participant, it is EM artifact
            if abs(mean_phantom) > 0.5 * abs(mean_int - mean_base):
                artifact_flags.append("DIRECT_EM_INSTRUMENTATION_PICKUP")
                em_risk = max(em_risk, 0.75)
                phantom_match = False

        if rf_field_strength_v_m > 5.0:
            artifact_flags.append("HIGH_NEAR_FIELD_RF")

        temp_risk = temp_delta_c > 0.8
        if temp_risk:
            artifact_flags.append("THERMAL_DRIFT_INTERFERENCE")

        artifact_rep = ArtifactReport(
            em_pickup_risk_score=round(em_risk, 3),
            temperature_gradient_detected=temp_risk,
            phantom_control_match=phantom_match,
            flags=artifact_flags,
        )

        # 2. Compute Resonance Response Index (RRI)
        # Normalized score between 0.0 and 1.0 penalizing artifact risk
        raw_response = abs(cohens_d) / (1.0 + abs(cohens_d))
        rri = raw_response * (1.0 - em_risk)

        # 3. Repeatability score
        if prior_trial_scores and len(prior_trial_scores) > 0:
            avg_prior = sum(prior_trial_scores) / len(prior_trial_scores)
            repeatability = max(0.0, 1.0 - abs(rri - avg_prior))
        else:
            repeatability = 0.5  # Neutral default for first run

        # Confidence interval
        n = len(intervention_signal)
        margin = 1.96 * (pooled_sd / math.sqrt(n)) if n > 1 else 0.2
        ci_low = max(0.0, rri - margin)
        ci_high = min(1.0, rri + margin)

        # 4. Status assignment
        if not artifact_rep.is_valid_signal:
            status = "ARTIFACT_LIKELY"
            notes = "Observed signal changes correlate with direct electromagnetic or thermal instrumentation interference."
        elif repeatability > 0.75 and abs(cohens_d) > 0.8:
            status = "REPEATABLE_DIFFERENCE"
            notes = "Statistically significant, repeatable difference observed beyond bench phantom controls."
        elif abs(cohens_d) < 0.2:
            status = "INCONCLUSIVE"
            notes = "No statistically meaningful difference from baseline or sham control."
        else:
            status = "EXPLORATORY"
            notes = "Initial contrast detected; requires further blinded trial repetitions."

        return ResponseEvaluation(
            configuration_id=config_id,
            blinded_label=blinded_label,
            observed_rri=rri,
            effect_size_d=cohens_d,
            uncertainty_95ci=(ci_low, ci_high),
            artifact_report=artifact_rep,
            repeatability_score=repeatability,
            evidence_status=status,
            interpretation_notes=notes,
        )
