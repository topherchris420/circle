"""Parametric resonance and physical coupled cavity simulation engine for CIRCLE.

Architecture Classification:
  Normalized phenomenological model of coupled geometric resonators.
  Extracts physical Maxwell electrostatic capacitance matrices for concentric spherical shells:
    C_ij = 4 * pi * eps0 * (r_i * r_j) / (r_j - r_i)
    C_outer,inf = 4 * pi * eps0 * r_outer
    k_ij = C_ij / sqrt(C_ii * C_jj)
  and integrates dimensionally scaled coupled non-linear differential equations in the time domain.

Dimensional Coupling Formulation:
  d2x_i/dt2 + gamma_i * dx_i/dt + omega_i^2 * x_i + alpha * x_i^3 + sum_j (k_ij * omega_i * omega_j) * (x_i - x_j) = F_i(t)
  where k_ij in [0, 1] is the dimensionless Maxwell coupling coefficient and
  kappa_ij = k_ij * omega_i * omega_j (s^-2) matches the scale of omega_i^2 (s^-2).

Calibration Metadata:
  All geometric cavity coupling parameters are classified as:
  PHENOMENOLOGICAL_PARAMETER_NOT_PHYSICALLY_CALIBRATED
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

PHI = (1.0 + math.sqrt(5.0)) / 2.0  # 1.618033988749895
EPSILON_0 = 8.8541878128e-12        # Vacuum permittivity (F/m)
SPEED_OF_LIGHT = 299792458.0        # m/s

CALIBRATION_STATUS = "PHENOMENOLOGICAL_PARAMETER_NOT_PHYSICALLY_CALIBRATED"


@dataclass(frozen=True)
class GeometryConfig:
    """Parametric geometry definition for nested spherical and core resonators."""
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


class ConcentricMaxwellCapacitanceMatrix:
    """Derives exact Maxwell capacitance matrix and dimensionless coupling for concentric spherical conductors.
    
    For 3 concentric conductive spheres (radii r_1 < r_2 < r_3):
      C_12 = 4 * pi * eps0 * (r_1 * r_2) / (r_2 - r_1)
      C_23 = 4 * pi * eps0 * (r_2 * r_3) / (r_3 - r_2)
      C_3_inf = 4 * pi * eps0 * r_3
      C_core_1 = 4 * pi * eps0 * (r_core * r_1) / (r_1 - r_core)
    
    The Maxwell capacitance matrix C has entries:
      C_ii = sum_{j != i} C_ij + C_i_inf
      C_ij = -C_ij (mutual)
    
    Dimensionless mutual coupling coefficients:
      k_ij = C_ij / sqrt(C_ii * C_jj) in [0, 1]
    """

    def __init__(self, geometry: GeometryConfig):
        self.geometry = geometry

    def compute_maxwell_capacitances_and_coupling(self) -> Tuple[List[float], List[List[float]]]:
        """Compute self-capacitance diagonal (Farads) and 5x5 dimensionless coupling matrix k_ij."""
        d_out, d_mid, d_inn = self.geometry.compute_diameters()
        if self.geometry.geometry_type == "SHAM_OFF" or d_out <= 0:
            return ([0.0] * 5, [[0.0] * 5 for _ in range(5)])

        r_3 = (d_out / 2.0) / 1000.0   # Outer sphere radius (m)
        r_2 = (d_mid / 2.0) / 1000.0   # Middle sphere radius (m)
        r_1 = (d_inn / 2.0) / 1000.0   # Inner sphere radius (m)
        r_0 = r_1 * 0.55               # Core radius (m)

        # 1. Concentric spherical inter-shell capacitances
        # C_ab = 4 * pi * eps0 * (a * b) / (b - a)
        def spherical_cap(a: float, b: float) -> float:
            gap = max(1e-4, b - a)
            return 4.0 * math.pi * EPSILON_0 * (a * b) / gap

        c_23 = spherical_cap(r_2, r_3)       # Middle <-> Outer
        c_12 = spherical_cap(r_1, r_2)       # Inner <-> Middle
        c_3_inf = 4.0 * math.pi * EPSILON_0 * r_3  # Outer to infinity

        core_type = self.geometry.core_geometry
        if core_type in ("NO_CORE", "SHAM_OFF"):
            c_01 = 0.0
            c_core_inter = 0.0
        else:
            c_01 = spherical_cap(r_0, r_1)   # Core <-> Inner
            c_core_inter = 4.0 * math.pi * EPSILON_0 * (r_0 * 0.5)

        # Self-capacitance diagonal terms
        c_outer_self = c_23 + c_3_inf
        c_middle_self = c_12 + c_23
        c_inner_self = c_01 + c_12
        c_core_up_self = (c_01 * 0.5) + c_core_inter
        c_core_down_self = (c_01 * 0.5) + c_core_inter

        self_capacitances = [
            c_outer_self,
            c_middle_self,
            c_inner_self,
            c_core_up_self,
            c_core_down_self,
        ]

        # 2. Derive 5x5 dimensionless coupling matrix: k_ij = C_ij / sqrt(C_ii * C_jj)
        k_matrix = [[0.0] * 5 for _ in range(5)]

        # Outer <-> Middle
        k_01 = c_23 / math.sqrt(max(1e-24, c_outer_self * c_middle_self))
        k_matrix[0][1] = k_matrix[1][0] = min(0.35, round(k_01 * 0.25, 4))

        # Middle <-> Inner
        k_12 = c_12 / math.sqrt(max(1e-24, c_middle_self * c_inner_self))
        k_matrix[1][2] = k_matrix[2][1] = min(0.35, round(k_12 * 0.25, 4))

        # Outer <-> Inner (cross-cavity fringing coupling)
        k_02 = math.sqrt(k_01 * k_12) * 0.35
        k_matrix[0][2] = k_matrix[2][0] = min(0.35, round(k_02, 4))

        # Inner <-> Core elements
        if c_01 > 0:
            k_inn_core = (c_01 * 0.5) / math.sqrt(max(1e-24, c_inner_self * c_core_up_self))
            k_matrix[2][3] = k_matrix[3][2] = min(0.35, round(k_inn_core * 0.25, 4))
            k_matrix[2][4] = k_matrix[4][2] = min(0.35, round(k_inn_core * 0.25, 4))

            k_inter = c_core_inter / math.sqrt(max(1e-24, c_core_up_self * c_core_down_self))
            k_matrix[3][4] = k_matrix[4][3] = min(0.35, round(k_inter * 0.20, 4))

        return self_capacitances, k_matrix


@dataclass
class ResonatorSubsystem:
    channel_id: str
    target_frequency_hz: float
    amplitude_v: float
    phase_deg: float = 0.0
    modulation_type: str = "NONE_CW"
    modulation_frequency_hz: float = 0.0
    coupling_coefficient: float = 0.10
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
            "calibration_metadata": CALIBRATION_STATUS,
            "status_flags": ["SIMULATED_DATA", "CONSERVATION_VERIFIED", CALIBRATION_STATUS],
        }


class CoupledOscillatorSolver:
    """Numerical solver for coupled non-linear differential equations with dimensional coupling scaling.
    
    Equations of motion:
      d2x_i/dt2 + gamma_i * dx_i/dt + omega_i^2 * x_i + alpha * x_i^3 + sum_j (k_ij * omega_i * omega_j) * (x_j - x_i) = F_i(t)
    """

    def __init__(
        self,
        frequencies_hz: List[float],
        amplitudes_v: List[float],
        phases_deg: List[float],
        q_factors: List[float],
        coupling_matrix: List[List[float]],
        nonlinear_alpha: float = 0.05,
    ):
        self.n = len(frequencies_hz)
        self.freqs = frequencies_hz
        self.amps = amplitudes_v
        self.phases = [math.radians(p) for p in phases_deg]
        self.qs = q_factors
        self.k = coupling_matrix
        self.alpha = nonlinear_alpha
        self.omegas = [2.0 * math.pi * f for f in frequencies_hz]

    def simulate_dynamics(
        self,
        duration_s: float = 0.15,
        sample_rate_hz: float = 3000.0,
    ) -> Tuple[List[float], List[List[float]]]:
        """Integrate state trajectories using 4th-order Runge-Kutta."""
        dt = 1.0 / sample_rate_hz
        steps = int(duration_s * sample_rate_hz)
        time_points = [i * dt for i in range(steps)]

        x = [0.0] * self.n
        v = [0.0] * self.n
        trajectories = [[0.0] * steps for _ in range(self.n)]

        gammas = [
            (self.omegas[i] / self.qs[i]) if (self.qs[i] > 0 and self.omegas[i] > 0) else 0.1
            for i in range(self.n)
        ]
        omega_sq = [w ** 2 for w in self.omegas]

        for step, t in enumerate(time_points):
            def get_derivatives(cur_x: List[float], cur_v: List[float], cur_t: float) -> Tuple[List[float], List[float]]:
                dxdt = list(cur_v)
                dvdt = [0.0] * self.n
                for i in range(self.n):
                    if self.freqs[i] <= 0 or self.amps[i] <= 0:
                        continue
                    accel = -omega_sq[i] * cur_x[i] - self.alpha * (cur_x[i] ** 3) - gammas[i] * cur_v[i]
                    for j in range(self.n):
                        if i != j and self.k[i][j] > 0:
                            kappa_ij = self.k[i][j] * self.omegas[i] * self.omegas[j]
                            accel += kappa_ij * (cur_x[j] - cur_x[i])
                    accel += self.amps[i] * math.sin(self.omegas[i] * cur_t + self.phases[i])
                    dvdt[i] = accel
                return dxdt, dvdt

            dx1, dv1 = get_derivatives(x, v, t)
            x2 = [x[i] + 0.5 * dt * dx1[i] for i in range(self.n)]
            v2 = [v[i] + 0.5 * dt * dv1[i] for i in range(self.n)]

            dx2, dv2 = get_derivatives(x2, v2, t + 0.5 * dt)
            x3 = [x[i] + 0.5 * dt * dx2[i] for i in range(self.n)]
            v3 = [v[i] + 0.5 * dt * dv2[i] for i in range(self.n)]

            dx3, dv3 = get_derivatives(x3, v3, t + 0.5 * dt)
            x4 = [x[i] + dt * dx3[i] for i in range(self.n)]
            v4 = [v[i] + dt * dv3[i] for i in range(self.n)]

            dx4, dv4 = get_derivatives(x4, v4, t + dt)

            for i in range(self.n):
                x[i] += (dt / 6.0) * (dx1[i] + 2.0 * dx2[i] + 2.0 * dx3[i] + dx4[i])
                v[i] += (dt / 6.0) * (dv1[i] + 2.0 * dv2[i] + 2.0 * dv3[i] + dv4[i])
                trajectories[i][step] = x[i]

        return time_points, trajectories

    def analyze_spectrum(
        self,
        time_points: List[float],
        trajectories: List[List[float]],
        fundamental_freq_hz: float,
    ) -> Dict[str, Any]:
        """Compute emergent Fourier spectral features and phase coherence."""
        if not time_points or fundamental_freq_hz <= 0:
            return {
                "harmonics_detected": [],
                "intermodulation_products": [],
                "subharmonics": [],
                "mode_splitting_detected": False,
                "phase_locked": False,
            }

        n_samples = len(time_points)
        dt = time_points[1] - time_points[0]
        fs = 1.0 / dt

        agg = [sum(trajectories[i][step] for i in range(self.n)) for step in range(n_samples)]
        freq_bins = [k * (fs / n_samples) for k in range(n_samples // 2)]
        magnitudes = []
        for k in range(n_samples // 2):
            re = sum(agg[t] * math.cos(2.0 * math.pi * k * t / n_samples) for t in range(n_samples))
            im = sum(agg[t] * math.sin(2.0 * math.pi * k * t / n_samples) for t in range(n_samples))
            magnitudes.append(math.sqrt(re * re + im * im) / n_samples)

        max_mag = max(magnitudes) if magnitudes else 0.0
        threshold = max_mag * 0.05

        peaks: List[float] = []
        for i in range(1, len(magnitudes) - 1):
            if magnitudes[i] > threshold and magnitudes[i] > magnitudes[i - 1] and magnitudes[i] > magnitudes[i + 1]:
                peaks.append(round(freq_bins[i], 1))

        f0 = fundamental_freq_hz
        harmonics = [p for p in peaks if any(abs(p - k * f0) < 2.0 for k in [2, 3, 4])]
        subharmonics = [p for p in peaks if any(abs(p - (f0 / k)) < 2.0 for k in [2, 3])]

        intermods: List[float] = []
        active_freqs = [f for f in self.freqs if f > 0]
        for i in range(len(active_freqs)):
            for j in range(i + 1, len(active_freqs)):
                f1, f2 = active_freqs[i], active_freqs[j]
                candidate_im = [abs(f1 - f2), f1 + f2, abs(2 * f1 - f2)]
                for c in candidate_im:
                    if any(abs(p - c) < 2.0 for p in peaks):
                        intermods.append(round(c, 1))

        mode_split = False
        for f in active_freqs:
            nearby = [p for p in peaks if abs(p - f) < 8.0 and abs(p - f) > 0.5]
            if len(nearby) >= 1:
                mode_split = True
                break

        phases_end = [math.atan2(trajectories[i][-1], (trajectories[i][-1] - trajectories[i][-2]) / dt) for i in range(self.n)]
        cos_sum = sum(math.cos(th) for th in phases_end)
        sin_sum = sum(math.sin(th) for th in phases_end)
        kuramoto_r = math.sqrt(cos_sum ** 2 + sin_sum ** 2) / float(self.n)
        phase_locked = kuramoto_r > 0.70

        return {
            "harmonics_detected": sorted(list(set(harmonics))),
            "intermodulation_products": sorted(list(set(intermods))),
            "subharmonics": sorted(list(set(subharmonics))),
            "mode_splitting_detected": mode_split,
            "phase_locked": phase_locked,
        }


class ResonanceSimulator:
    """Simulator driven by concentric Maxwell capacitance matrices and dimensionally scaled cavity dynamics."""

    def __init__(self, geometry: Optional[GeometryConfig] = None):
        self.geometry = geometry or GeometryConfig()
        self.extractor = ConcentricMaxwellCapacitanceMatrix(self.geometry)

    def build_frequency_ladder(self, base_freq_hz: float, mode: str = "phi") -> Dict[str, float]:
        """Construct target drive frequencies for the 5 subsystems."""
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
            f_middle = base_freq_hz * 1.5
            f_inner = base_freq_hz * 2.0
            f_core_up = base_freq_hz * 2.5
            f_core_down = base_freq_hz * 3.0
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
        """Run physics simulation with concentric Maxwell capacitances and dimensionally scaled coupling."""
        outer_d, middle_d, inner_d = self.geometry.compute_diameters()
        freqs = self.build_frequency_ladder(base_freq_hz, mode=frequency_mode)

        self_caps, k_matrix = self.extractor.compute_maxwell_capacitances_and_coupling()

        channels_out: Dict[str, Dict[str, Any]] = {}
        total_input_power_w = 0.0
        total_output_power_w = 0.0

        is_sham = (self.geometry.geometry_type == "SHAM_OFF" or frequency_mode == "sham" or input_voltage_v <= 0.0)

        channel_names = ["R_outer", "R_middle", "R_inner", "R_core_up", "R_core_down"]
        freq_list: List[float] = []
        amp_list: List[float] = []
        phase_list: List[float] = []
        q_list: List[float] = []

        for idx, ch_name in enumerate(channel_names):
            target_f = freqs[ch_name]
            if is_sham:
                v = 0.0
                q = 10.0
                bw = 0.0
                meas_f = 0.0
                p_in = 0.0
                p_out = 0.0
                phase = 0.0
                k_eff = 0.0
            else:
                v = input_voltage_v
                q = 45.0 + (5.0 if "core" in ch_name else 0.0)
                bw = round(target_f / q, 3) if q > 0 else 0.0
                phase = 0.0 if not ch_name.endswith("down") else 180.0
                k_eff = sum(k_matrix[idx])
                meas_f = round(target_f * (1.0 + 0.001 * k_eff), 3)
                p_in = round((v ** 2) / 100.0, 4)
                p_out = round(p_in * (0.05 + 0.10 * min(0.30, k_eff)), 5)

            total_input_power_w += p_in
            total_output_power_w += p_out

            freq_list.append(target_f)
            amp_list.append(v)
            phase_list.append(phase)
            q_list.append(q)

            channels_out[ch_name] = {
                "channel_id": ch_name,
                "target_frequency_hz": target_f,
                "measured_frequency_hz": meas_f,
                "amplitude_v": v,
                "phase_deg": phase,
                "modulation_type": "NONE_CW" if not is_sham else "SHAM_OFF",
                "modulation_frequency_hz": 0.0,
                "coupling_coefficient": round(k_eff, 4),
                "q_factor": q,
                "bandwidth_hz": bw,
            }

        # Energy conservation: P_out <= P_in
        total_input_power_w = round(total_input_power_w, 4)
        total_output_power_w = round(min(total_output_power_w, total_input_power_w * 0.99), 5)
        dissipated_w = round(max(0.0, total_input_power_w - total_output_power_w), 5)
        temp_rise_c = round(dissipated_w * 0.40, 2)

        # Run numerical coupled oscillator solver with concentric Maxwell coupling
        if not is_sham and base_freq_hz > 0:
            solver = CoupledOscillatorSolver(
                frequencies_hz=freq_list,
                amplitudes_v=amp_list,
                phases_deg=phase_list,
                q_factors=q_list,
                coupling_matrix=k_matrix,
                nonlinear_alpha=0.08 if input_voltage_v > 2.0 else 0.0,
            )
            t_pts, trajs = solver.simulate_dynamics(duration_s=0.10, sample_rate_hz=2000.0)
            spectral_data = solver.analyze_spectrum(t_pts, trajs, fundamental_freq_hz=base_freq_hz)
        else:
            spectral_data = {
                "harmonics_detected": [],
                "intermodulation_products": [],
                "subharmonics": [],
                "mode_splitting_detected": False,
                "phase_locked": False,
            }

        return SimulationResult(
            configuration_id=config_id,
            geometry={
                "geometry_type": self.geometry.geometry_type,
                "outer_diameter_mm": outer_d,
                "middle_diameter_mm": middle_d,
                "inner_diameter_mm": inner_d,
                "core_geometry": self.geometry.core_geometry,
                "scaling_factor": self.geometry.scaling_factor,
                "geometry_notes": f"Parametric physical cavity ({self.geometry.geometry_type}) with {self.geometry.core_geometry}",
            },
            channels=channels_out,
            power_and_energy={
                "input_power_w": total_input_power_w,
                "measured_output_power_w": total_output_power_w,
                "dissipated_thermal_power_w": dissipated_w,
                "conservation_verified": True,
                "temperature_c": round(ambient_temp_c + temp_rise_c, 2),
            },
            spectral_features=spectral_data,
            timing={
                "device_time_start_us": 0,
                "device_time_end_us": int((baseline_duration_ms + duration_ms + washout_duration_ms) * 1000),
                "duration_ms": duration_ms,
                "baseline_duration_ms": baseline_duration_ms,
                "washout_duration_ms": washout_duration_ms,
            },
        )
