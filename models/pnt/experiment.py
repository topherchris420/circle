"""Seeded, translation-only PNT benchmark with known simulated ground truth.

This exercises the implemented bias-aiding EKF against the same unaided IMU
stream. The reference sensor is Gaussian specific-force simulation, not a
quantum-state, fringe, gradiometer, clock, or hardware performance model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np

from .estimator import G_STANDARD, PNTStateEstimator


@dataclass(frozen=True)
class PNTExperimentConfig:
    duration_s: float = 10.0
    dt_s: float = 0.01
    seed: int = 42
    reference_rate_hz: float = 2.0
    imu_noise_std: float = 0.002
    reference_noise_std: float = 0.001
    accel_bias_m_s2: tuple[float, float, float] = (0.025, -0.015, 0.01)

    def __post_init__(self) -> None:
        for name in ("duration_s", "dt_s", "reference_rate_hz", "reference_noise_std"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(self.imu_noise_std) or self.imu_noise_std < 0:
            raise ValueError("imu_noise_std must be finite and nonnegative")
        steps = self.duration_s / self.dt_s
        if not math.isfinite(steps) or not 1 <= steps <= 1_000_000:
            raise ValueError("Experiment must contain between 1 and 1,000,000 steps")
        if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-7):
            raise ValueError("duration_s must be an integer multiple of dt_s")
        if self.dt_s * self.reference_rate_hz > 1:
            raise ValueError("Time step cannot skip reference sensor updates")
        if self.duration_s * self.reference_rate_hz < 1:
            raise ValueError("Duration must include at least one reference sensor update")
        if not math.isclose(self.dt_s * 1e6, round(self.dt_s * 1e6), rel_tol=0, abs_tol=1e-7):
            raise ValueError("dt_s must be representable in integer microseconds")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        PNTStateEstimator._vector(self.accel_bias_m_s2, "accel_bias_m_s2")


def run_experiment(config: PNTExperimentConfig) -> dict[str, Any]:
    random_state = np.random.default_rng(config.seed)
    steps = round(config.duration_s / config.dt_s)
    bias = np.asarray(config.accel_bias_m_s2, dtype=np.float64)
    residual_std = math.hypot(config.imu_noise_std, config.reference_noise_std)
    estimators = {
        name: PNTStateEstimator(dt_s=config.dt_s, accel_noise_std=config.imu_noise_std,
                               gyro_noise_std=0, ai_accel_noise_std=residual_std)
        for name in ("classical", "reference_aided")
    }
    position = np.zeros(3)
    velocity = np.zeros(3)
    squared_errors = {name: np.zeros(2) for name in estimators}
    reference_count = 0
    accepted = 0
    trajectory = []
    # Bound exported trace size independently of experiment length.
    trace_stride = max(1, math.ceil(steps / 1000))
    for step in range(steps):
        time_s = (step + 1) * config.dt_s
        acceleration = np.array([0.12 * math.sin(0.8 * time_s), 0.08 * math.cos(0.5 * time_s), 0.0])
        position += velocity * config.dt_s + 0.5 * acceleration * config.dt_s**2
        velocity += acceleration * config.dt_s
        specific_force = acceleration + np.array([0.0, 0.0, G_STANDARD])
        imu = specific_force + bias + random_state.normal(0, config.imu_noise_std, 3)
        for estimator in estimators.values():
            estimator.predict(imu, np.zeros(3))
        due = math.floor(time_s * config.reference_rate_hz + 1e-9)
        if due > reference_count:
            reference = specific_force + random_state.normal(0, config.reference_noise_std, 3)
            update = estimators["reference_aided"].update_quantum_interferometer(reference, imu)
            accepted += int(update["status"] == "AI_UPDATE_SUCCESS")
            reference_count = due
        for name, estimator in estimators.items():
            squared_errors[name] += [
                float(np.sum((estimator.state.position_m - position)**2)),
                float(np.sum((estimator.state.velocity_m_s - velocity)**2)),
            ]
        if step % trace_stride == 0 or step == steps - 1:
            trajectory.append({
                "device_time_us": round(time_s * 1e6), "truth_position_m": position.tolist(),
                **{f"{name}_position_m": estimator.state.position_m.tolist() for name, estimator in estimators.items()},
            })
    metrics = {}
    for name, estimator in estimators.items():
        position_rmse, velocity_rmse = np.sqrt(squared_errors[name] / steps)
        final_error = float(np.linalg.norm(estimator.state.position_m - position))
        metrics[name] = {
            "position_rmse_m": float(position_rmse),
            "velocity_rmse_m_s": float(velocity_rmse),
            "final_position_error_m": final_error,
            "final_error_per_hour_m": final_error * 3600 / config.duration_s,
            "estimated_accel_bias_m_s2": estimator.state.accel_bias_m_s2.tolist(),
        }
    return {
        "schema_version": "1.0.0", "experiment": "TRANSLATION_BIAS_AIDING_BENCHMARK",
        "provenance": "SIMULATED", "config": asdict(config), "sample_count": steps,
        "reference_samples": reference_count, "accepted_reference_updates": accepted,
        "rejected_reference_updates": reference_count - accepted,
        "metrics": metrics, "trajectory": trajectory,
        "limitations": [
            "Known initial pose; translation only; no rotation or clock/gradiometer fusion.",
            "Reference samples use Gaussian specific-force noise, not a quantum-state model.",
            "RMSE is calculated against simulated truth and does not establish hardware accuracy.",
            "Final error per hour is a normalized endpoint error, not a fitted drift rate.",
        ],
    }
