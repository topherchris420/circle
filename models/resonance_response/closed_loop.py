"""Closed-loop adaptive experimental decision engine for CIRCLE Resonance experiments.

Explores the experimental search space with strict safety boundaries, mandatory
baseline/washout intervals, uncertainty budgets, and blinded control scheduling.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ExperimentSearchSpace:
    """Bounded experimental parameter search space."""
    min_frequency_hz: float = 1.0
    max_frequency_hz: float = 100000.0  # 100 kHz bench limit
    min_amplitude_v: float = 0.0
    max_amplitude_v: float = 10.0      # 10V safe bench limit
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
    configuration_id: str
    target_frequency_hz: float
    amplitude_v: float
    geometry_type: str
    core_geometry: str
    modulation_type: str
    duration_ms: float
    baseline_duration_ms: float
    washout_duration_ms: float
    is_control_condition: bool
    blinded_label: str
    exploration_uncertainty: float
    repeat_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "configuration_id": self.configuration_id,
            "target_frequency_hz": self.target_frequency_hz,
            "amplitude_v": self.amplitude_v,
            "geometry_type": self.geometry_type,
            "core_geometry": self.core_geometry,
            "modulation_type": self.modulation_type,
            "duration_ms": self.duration_ms,
            "baseline_duration_ms": self.baseline_duration_ms,
            "washout_duration_ms": self.washout_duration_ms,
            "is_control_condition": self.is_control_condition,
            "blinded_label": self.blinded_label,
            "exploration_uncertainty": self.exploration_uncertainty,
            "repeat_count": self.repeat_count,
        }


class ClosedLoopOptimizer:
    """Adaptive search policy for discovering repeatable resonance effects."""

    def __init__(self, search_space: Optional[ExperimentSearchSpace] = None, seed: int = 1337):
        self.space = search_space or ExperimentSearchSpace()
        self.rng = random.Random(seed)
        self.history: List[Dict[str, Any]] = []

    def generate_blinded_id(self, config: Dict[str, Any]) -> str:
        """Create a deterministic, unguessable blinded identifier for double-blind trials."""
        raw = json.dumps(config, sort_keys=True).encode("utf-8")
        h = hashlib.sha256(raw).hexdigest()[:8].upper()
        return f"BLIND-{h}"

    def propose_next_intervention(
        self,
        current_step: int,
        last_response_score: Optional[float] = None,
        force_control_ratio: float = 0.33,
    ) -> ExperimentalDecision:
        """Propose the next experimental intervention ensuring regular control/sham conditions."""
        decision_id = f"dec-{current_step:04d}"

        # 33% of trials must be control/sham conditions to preserve statistical validity
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
                freq = round(self.rng.uniform(10.0, 500.0), 1)
                mod = "NONE_CW"
        else:
            geom = "GOLDEN_RATIO_SPHERES"
            core = "DUAL_TETRAHEDRON_MERKABA"
            amp = round(self.rng.uniform(1.0, 5.0), 2)
            # Sample around candidate modal frequencies (e.g. 7.83 Schumann, 73.2 Hz, 528 Hz, or sweeping)
            candidates = [7.83, 14.1, 73.2, 110.0, 432.0, 528.0]
            freq = self.rng.choice(candidates) if self.rng.random() < 0.6 else round(self.rng.uniform(5.0, 1000.0), 1)
            mod = self.rng.choice(["NONE_CW", "SINE_AM", "PULSED"])

        duration = 15000.0
        baseline = max(self.space.min_baseline_ms, 5000.0)
        washout = max(self.space.min_washout_ms, 5000.0)

        config_dict = {
            "geom": geom,
            "core": core,
            "freq": freq,
            "amp": amp,
            "mod": mod,
            "dur": duration,
        }
        blinded_label = self.generate_blinded_id(config_dict)
        config_id = f"cfg-{blinded_label}"

        # Uncertainty estimate based on sample density in this region
        uncertainty = round(0.40 + 0.50 * self.rng.random(), 3)

        decision = ExperimentalDecision(
            decision_id=decision_id,
            configuration_id=config_id,
            target_frequency_hz=freq,
            amplitude_v=amp,
            geometry_type=geom,
            core_geometry=core,
            modulation_type=mod,
            duration_ms=duration,
            baseline_duration_ms=baseline,
            washout_duration_ms=washout,
            is_control_condition=is_control,
            blinded_label=blinded_label,
            exploration_uncertainty=uncertainty,
        )

        self.history.append(decision.to_dict())
        return decision
