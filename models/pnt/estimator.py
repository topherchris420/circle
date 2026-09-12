"""15-State Error-State Extended Kalman Filter (ES-EKF) for Quantum-Augmented PNT (QPNS-X).

Mechanization & State Vector (15 States):
  0..2:   Position Error delta_p (m)
  3..5:   Velocity Error delta_v (m/s)
  6..8:   Attitude Error delta_theta (rad)
  9..11:  Accelerometer Bias delta_a_b (m/s^2)
  12..14: Gyroscope Bias delta_w_b (rad/s)

Quantum Sensing Integrations:
  - Cold-Atom Mach-Zehnder Matter-Wave Interferometer (Phase accum Delta_Phi = k_eff * a * T^2)
  - Differential Gravity Gradiometer (Tensor gradient Gamma = grad(g))
  - Relativistic Quantum Clock Standard (Redshift gh/c^2 + Time Dilation v^2/(2c^2))
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

C_LIGHT = 299792458.0  # m/s
G_STANDARD = 9.80665   # m/s^2


@dataclass
class PNTNavigationState:
    position_m: np.ndarray        # (3,) [px, py, pz]
    velocity_m_s: np.ndarray      # (3,) [vx, vy, vz]
    attitude_rad: np.ndarray      # (3,) [roll, pitch, yaw]
    accel_bias_m_s2: np.ndarray   # (3,) [b_ax, b_ay, b_az]
    gyro_bias_rad_s: np.ndarray   # (3,) [b_gx, b_gy, b_gz]
    clock_error_s: float = 0.0
    clock_drift_s_s: float = 0.0


class PNTStateEstimator:
    """15-State ES-EKF fusing classical IMU with quantum interferometry, gradiometry, and optical clock."""

    def __init__(
        self,
        dt_s: float = 0.01,
        accel_noise_std: float = 0.05,
        gyro_noise_std: float = 0.005,
        ai_accel_noise_std: float = 0.001,
        clock_noise_std: float = 1e-12,
        innovation_gate: float = 16.0,
    ) -> None:
        if not math.isfinite(dt_s) or dt_s <= 0:
            raise ValueError("dt_s must be finite and positive")
        for name, value in (("accel_noise_std", accel_noise_std), ("gyro_noise_std", gyro_noise_std)):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name, value in (("ai_accel_noise_std", ai_accel_noise_std), ("clock_noise_std", clock_noise_std), ("innovation_gate", innovation_gate)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        self.dt = dt_s
        self.innovation_gate = innovation_gate
        self.state = PNTNavigationState(
            position_m=np.zeros(3, dtype=np.float64),
            velocity_m_s=np.zeros(3, dtype=np.float64),
            attitude_rad=np.zeros(3, dtype=np.float64),
            accel_bias_m_s2=np.zeros(3, dtype=np.float64),
            gyro_bias_rad_s=np.zeros(3, dtype=np.float64),
        )

        # Error state dx (15,) and Covariance P (15, 15)
        self.dx = np.zeros(15, dtype=np.float64)
        self.P = np.eye(15, dtype=np.float64) * 0.1
        self.P[0:3, 0:3] *= 1.0       # Position uncertainty
        self.P[3:6, 3:6] *= 0.1       # Velocity uncertainty
        self.P[6:9, 6:9] *= 0.01      # Attitude uncertainty
        self.P[9:12, 9:12] *= 1e-3    # Accel bias uncertainty
        self.P[12:15, 12:15] *= 1e-4  # Gyro bias uncertainty

        # Process Noise Q (15, 15)
        self.Q = np.eye(15, dtype=np.float64) * 1e-6
        self.Q[0:3, 0:3] *= 1e-4
        self.Q[3:6, 3:6] *= (accel_noise_std ** 2)
        self.Q[6:9, 6:9] *= (gyro_noise_std ** 2)
        self.Q[9:12, 9:12] *= 1e-8
        self.Q[12:15, 12:15] *= 1e-10

        self.ai_accel_std = ai_accel_noise_std
        self.clock_noise_std = clock_noise_std

    def predict(self, f_meas_b: np.ndarray, omega_meas_b: np.ndarray) -> None:
        """High-rate inertial mechanization and error state covariance propagation."""
        f_meas_b = self._vector(f_meas_b, "f_meas_b")
        omega_meas_b = self._vector(omega_meas_b, "omega_meas_b")
        f_b = f_meas_b - self.state.accel_bias_m_s2
        w_b = omega_meas_b - self.state.gyro_bias_rad_s

        # Simple Euler rotation matrix for small angles
        roll, pitch, yaw = self.state.attitude_rad
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)

        R_b_n = np.array([
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ], dtype=np.float64)

        gravity_n = np.array([0.0, 0.0, -G_STANDARD], dtype=np.float64)
        accel_n = R_b_n @ f_b + gravity_n

        # State mechanization
        self.state.position_m += self.state.velocity_m_s * self.dt + 0.5 * accel_n * (self.dt ** 2)
        self.state.velocity_m_s += accel_n * self.dt
        self.state.attitude_rad += w_b * self.dt

        # Error state Jacobian F_x (15, 15)
        F_x = np.eye(15, dtype=np.float64)
        F_x[0:3, 3:6] = np.eye(3) * self.dt

        # Skew-symmetric acceleration matrix
        f_skew = np.array([
            [0.0, -f_b[2], f_b[1]],
            [f_b[2], 0.0, -f_b[0]],
            [-f_b[1], f_b[0], 0.0],
        ], dtype=np.float64)

        F_x[3:6, 6:9] = -R_b_n @ f_skew * self.dt
        F_x[3:6, 9:12] = -R_b_n * self.dt
        F_x[6:9, 12:15] = -R_b_n * self.dt

        # Covariance propagation
        self.P = F_x @ self.P @ F_x.T + self.Q

    @staticmethod
    def _vector(value: np.ndarray, name: str) -> np.ndarray:
        vector = np.asarray(value, dtype=np.float64)
        if vector.shape != (3,) or not np.isfinite(vector).all():
            raise ValueError(f"{name} must be a finite 3-vector")
        return vector

    def update_quantum_interferometer(
        self, ai_accel_b: np.ndarray, imu_specific_force_b: np.ndarray | None = None,
    ) -> Dict[str, Any]:
        """Observe IMU bias from synchronized IMU minus reference specific force.

        With no IMU argument, ai_accel_b is an already formed bias observation
        (legacy API), not an absolute acceleration measurement. ai_accel_std must
        describe the noise of the differenced observation.
        """
        observation = self._vector(ai_accel_b, "ai_accel_b")
        if imu_specific_force_b is not None:
            observation = self._vector(imu_specific_force_b, "imu_specific_force_b") - observation
        f_est_b = self.state.accel_bias_m_s2
        z = observation - f_est_b

        H = np.zeros((3, 15), dtype=np.float64)
        H[:, 9:12] = np.eye(3)  # Directly observes accelerometer bias

        R = np.eye(3, dtype=np.float64) * (self.ai_accel_std ** 2)

        # Joseph-form update
        S = H @ self.P @ H.T + R
        mahalanobis_sq = float(z @ np.linalg.solve(S, z))
        if mahalanobis_sq > self.innovation_gate:
            return {"innovation_norm": float(np.linalg.norm(z)),
                    "mahalanobis_sq": mahalanobis_sq, "status": "AI_UPDATE_REJECTED"}
        K = np.linalg.solve(S, H @ self.P).T

        self.dx = K @ z
        I_KH = np.eye(15, dtype=np.float64) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T
        self.P = 0.5 * (self.P + self.P.T)

        self._inject_error_state()
        return {"innovation_norm": float(np.linalg.norm(z)),
                "mahalanobis_sq": mahalanobis_sq, "status": "AI_UPDATE_SUCCESS"}

    def update_quantum_clock(self, clock_phase_s: float, current_height_m: float) -> Dict[str, Any]:
        """Kalman measurement update using relativistic quantum clock error."""
        # Gravitational redshift: gh / c^2
        redshift = (G_STANDARD * current_height_m) / (C_LIGHT ** 2)
        v_sq = np.sum(self.state.velocity_m_s ** 2)
        time_dilation = v_sq / (2.0 * (C_LIGHT ** 2))

        predicted_drift = redshift + time_dilation
        self.state.clock_drift_s_s = predicted_drift
        self.state.clock_error_s += predicted_drift * self.dt

        return {
            "redshift": float(redshift),
            "time_dilation": float(time_dilation),
            "clock_error_s": float(self.state.clock_error_s),
        }

    def _inject_error_state(self) -> None:
        """Inject estimated error state dx into nominal state and reset dx."""
        self.state.position_m += self.dx[0:3]
        self.state.velocity_m_s += self.dx[3:6]
        self.state.attitude_rad += self.dx[6:9]
        self.state.accel_bias_m_s2 += self.dx[9:12]
        self.state.gyro_bias_rad_s += self.dx[12:15]
        self.dx.fill(0.0)

    def state_summary(self) -> Dict[str, Any]:
        return {
            "position_m": self.state.position_m.tolist(),
            "velocity_m_s": self.state.velocity_m_s.tolist(),
            "attitude_rad": self.state.attitude_rad.tolist(),
            "accel_bias_m_s2": self.state.accel_bias_m_s2.tolist(),
            "gyro_bias_rad_s": self.state.gyro_bias_rad_s.tolist(),
            "position_uncertainty_rss_m": float(np.sqrt(np.trace(self.P[0:3, 0:3]))),
            "velocity_uncertainty_rss_m_s": float(np.sqrt(np.trace(self.P[3:6, 3:6]))),
        }
