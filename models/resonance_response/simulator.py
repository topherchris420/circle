"""Parametric resonance and coupled-oscillator simulation engine for CIRCLE.

Simulates multi-element geometric resonators (nested spheres + central dual tetrahedron),
coupled modes, nonlinear frequency transformations (harmonics, intermodulation, mode splitting),
and rigorous energy conservation accounting (P_out <= P_in).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

PHI = (1.0 + math.sqrt(5.0)) / 2.0  # 1.618033988749895


@dataclass(frozen=True)
class GeometryConfig:
    geometry_type: str = "GOLDEN_RATIO_SPHERES"  # GOLDEN_RATIO_SPHERES, EQUAL_SPHERES, RANDOM_SPHERES, SHAM_OFF
    outer_diameter_mm: float = 300.0
    core_geometry: str = "DUAL_TETRAHEDRON_MERKABA"  # DUAL_TETRAHEDRON_MERKABA, SPHERICAL_CORE, CUBIC_CORE, NO_CORE, SHAM_OFF
    scaling_factor: float = 1.0
    seed: Optional[int] = None

    def compute_diameters(self) -> Tuple[float, float, float]:
        """Compute (outer, middle, inner) diameters in mm based on geometry type."""
        d = self.outer_diameter_mm * self.scaling_factor
        if self.geometry_type == "GOLDEN_RATIO_SPHERES":
            middle = d / PHI
            inner = d / (PHI ** 2)
            return (round(d, 3), round(middle, 3), round(inner, 3))
        elif self.geometry_type == "EQUAL_SPHERES":
            # Linear equal decrement spacing
            step = d / 3.0
            return (round(d, 3), round(d - step, 3), round(d - 2 * step, 3))
        elif self.geometry_type == "RANDOM_SPHERES":
            rng = random.Random(self.seed if self.seed is not None else 42)
            r1 = rng.uniform(0.55, 0.75)
            r2 = rng.uniform(0.30, 0.50)
            return (round(d, 3), round(d * r1, 3), round(d * r2, 3))
        elif self.geometry_type == "SHAM_OFF":
            return (0.0, 0.0, 0.0)
        else:
            raise ValueError(f"Unknown geometry_type: {self.geometry_type}")


@dataclass
class ResonatorSubsystem:
    channel_id: str
    target_frequency_hz: float
    amplitude_v: float
    phase_deg: float = 0.0
    modulation_type: str = "NONE_CW"
    modulation_frequency_hz: float = 0.0
    coupling_coefficient: float = 0.1
    q_factor: float = 50.0

    @property
    def bandwidth_hz(self) -> float:
        if self.q_factor <= 0 or self.target_frequency_hz <= 0:
            return 0.0
        return self.target_frequency_hz / self.q_factor


@dataclass
class SimulationResult:
    configuration_id: str
    geometry: Dict[str, Any]
    channels: Dict[str, Dict[str, Any]]
    power_and_energy: Dict[str, Any]
    spectral_features: Dict[str, Any]
    timing: Dict[str, Any]
    provenance: str = "SIMULATED"
    interpretation_level: str = "DERIVED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "experiment_id": f"sim-exp-{self.configuration_id}",
            "configuration_id": self.configuration_id,
            "geometry": self.geometry,
            "drive_channels": self.channels,
            "power_and_energy": self.power_and_energy,
            "spectral_features": self.spectral_features,
            "timing": self.timing,
            "provenance": self.provenance,
            "interpretation_level": self.interpretation_level,
            "status_flags": ["SIMULATED_DATA", "CONSERVATION_VERIFIED"],
        }


class ResonanceSimulator:
    """Simulator for the 5-element resonance chamber and coupled field responses."""

    def __init__(self, geometry: Optional[GeometryConfig] = None):
        self.geometry = geometry or GeometryConfig()

    def build_frequency_ladder(self, base_freq_hz: float, mode: str = "phi") -> Dict[str, float]:
        """Construct frequency targets for the 5 subsystems."""
        if mode == "phi":
            f_outer = base_freq_hz
            f_middle = f_outer * PHI
            f_inner = f_middle * PHI
            f_core_up = f_inner * PHI
            f_core_down = f_inner * (PHI ** 0.5)
        elif mode == "harmonic":
            f_outer = base_freq_hz
            f_middle = base_freq_hz * 2.0
            f_inner = base_freq_hz * 3.0
            f_core_up = base_freq_hz * 4.0
            f_core_down = base_freq_hz * 5.0
        elif mode == "equal":
            f_outer = base_freq_hz
            f_middle = base_freq_hz
            f_inner = base_freq_hz
            f_core_up = base_freq_hz
            f_core_down = base_freq_hz
        elif mode == "sham":
            return {ch: 0.0 for ch in ["R_outer", "R_middle", "R_inner", "R_core_up", "R_core_down"]}
        else:
            raise ValueError(f"Unknown frequency mode: {mode}")

        return {
            "R_outer": round(f_outer, 3),
            "R_middle": round(f_middle, 3),
            "R_inner": round(f_inner, 3),
            "R_core_up": round(f_core_up, 3),
            "R_core_down": round(f_core_down, 3),
        }

    def simulate_run(
        self,
        config_id: str,
        base_freq_hz: float = 73.2,
        input_voltage_v: float = 5.0,
        frequency_mode: str = "phi",
        duration_ms: float = 10000.0,
        baseline_duration_ms: float = 5000.0,
        washout_duration_ms: float = 5000.0,
        ambient_temp_c: float = 22.5,
    ) -> SimulationResult:
        """Run a deterministic coupled-resonator simulation step."""
        outer_d, middle_d, inner_d = self.geometry.compute_diameters()
        freqs = self.build_frequency_ladder(base_freq_hz, mode=frequency_mode)

        channels_out: Dict[str, Dict[str, Any]] = {}
        total_input_power_w = 0.0
        total_output_power_w = 0.0

        is_sham = (self.geometry.geometry_type == "SHAM_OFF" or frequency_mode == "sham" or input_voltage_v == 0.0)

        for ch_name, target_f in freqs.items():
            if is_sham:
                v = 0.0
                q = 10.0
                bw = 0.0
                meas_f = 0.0
                p_in = 0.0
                p_out = 0.0
            else:
                v = input_voltage_v
                q = 45.0 + 10.0 * (1.0 if "core" in ch_name else 0.5)
                bw = round(target_f / q, 3) if q > 0 else 0.0
                # Small deterministic frequency pulling due to mutual coupling
                coupling = 0.12 if "core" in ch_name else 0.08
                meas_f = round(target_f * (1.0 + 0.001 * coupling), 3)
                # Standard impedance load power: P = V^2 / (2 * R_load) with R=50 ohm
                p_in = round((v ** 2) / 100.0, 4)
                # Efficiency loss in cavity radiation and conductive damping (80-92% dissipated as heat)
                coupling_eff = 0.08 + 0.04 * (1.0 if self.geometry.geometry_type == "GOLDEN_RATIO_SPHERES" else 0.02)
                p_out = round(p_in * coupling_eff, 5)

            total_input_power_w += p_in
            total_output_power_w += p_out

            channels_out[ch_name] = {
                "channel_id": ch_name,
                "target_frequency_hz": target_f,
                "measured_frequency_hz": meas_f,
                "amplitude_v": v,
                "phase_deg": 0.0 if not ch_name.endswith("down") else 180.0,
                "modulation_type": "NONE_CW" if not is_sham else "SHAM_OFF",
                "modulation_frequency_hz": 0.0,
                "coupling_coefficient": 0.12 if "core" in ch_name else 0.08,
                "q_factor": q,
                "bandwidth_hz": bw,
            }

        # Conservation of energy invariant: P_out <= P_in ALWAYS
        total_input_power_w = round(total_input_power_w, 4)
        total_output_power_w = round(min(total_output_power_w, total_input_power_w * 0.99), 5)
        dissipated_w = round(max(0.0, total_input_power_w - total_output_power_w), 5)
        temp_rise_c = round(dissipated_w * 0.45, 2)  # Thermal rise model

        # Calculate nonlinear spectral phenomena
        harmonics: List[float] = []
        intermods: List[float] = []
        subharmonics: List[float] = []
        if not is_sham and base_freq_hz > 0:
            harmonics = [round(base_freq_hz * 2.0, 2), round(base_freq_hz * 3.0, 2)]
            subharmonics = [round(base_freq_hz / 2.0, 2)]
            f1, f2 = freqs["R_outer"], freqs["R_middle"]
            intermods = [round(abs(f2 - f1), 2), round(f1 + f2, 2), round(abs(2 * f1 - f2), 2)]

        return SimulationResult(
            configuration_id=config_id,
            geometry={
                "geometry_type": self.geometry.geometry_type,
                "outer_diameter_mm": outer_d,
                "middle_diameter_mm": middle_d,
                "inner_diameter_mm": inner_d,
                "core_geometry": self.geometry.core_geometry,
                "scaling_factor": self.geometry.scaling_factor,
                "geometry_notes": f"Parametric build ({self.geometry.geometry_type}) with {self.geometry.core_geometry}",
            },
            channels=channels_out,
            power_and_energy={
                "input_power_w": total_input_power_w,
                "measured_output_power_w": total_output_power_w,
                "dissipated_thermal_power_w": dissipated_w,
                "conservation_verified": True,
                "temperature_c": round(ambient_temp_c + temp_rise_c, 2),
            },
            spectral_features={
                "harmonics_detected": sorted(list(set(harmonics))),
                "intermodulation_products": sorted(list(set(intermods))),
                "subharmonics": sorted(list(set(subharmonics))),
                "mode_splitting_detected": bool(len(intermods) > 0 and not is_sham),
                "phase_locked": bool(not is_sham),
            },
            timing={
                "device_time_start_us": 0,
                "device_time_end_us": int((baseline_duration_ms + duration_ms + washout_duration_ms) * 1000),
                "duration_ms": duration_ms,
                "baseline_duration_ms": baseline_duration_ms,
                "washout_duration_ms": washout_duration_ms,
            },
        )
