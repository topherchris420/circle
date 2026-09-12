"""CIRCLE Telemetry Bridge and Session Record Adapter for Quantum PNT."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional
import numpy as np

from models.session_records import compute_crc32c, seal_record
from .experiment import PNTExperimentConfig


PNT_STREAM_MAPPINGS = {
    "CIRCLE_IMU_ICM42688": {
        "channel_desc": "6-Axis Inertial Measurement Unit (Accel + Gyro)",
        "units": ["m/s^2", "rad/s"],
        "rate_hz": 100.0,
    },
    "CIRCLE_ATOM_INTERFEROMETER": {
        "channel_desc": "Cold-Atom Light-Pulse Mach-Zehnder Interferometer",
        "units": ["rad", "m/s^2"],
        "rate_hz": 2.0,
    },
    "CIRCLE_GRAVITY_GRADIOMETER": {
        "channel_desc": "Differential Cold-Atom Dual-Cloud Gradiometer",
        "units": ["Eotvos", "m/s^2"],
        "rate_hz": 1.0,
    },
    "CIRCLE_QUANTUM_CLOCK": {
        "channel_desc": "Optical Lattice / Cold-Atom Quantum Clock",
        "units": ["dimensionless", "s"],
        "rate_hz": 100.0,
    }
}


class CirclePNTBridge:
    """Bridges CIRCLE telemetry streams to and from QPNS-X simulation channels."""

    def __init__(self) -> None:
        self.stream_mappings = PNT_STREAM_MAPPINGS

    def package_pnt_telemetry(
        self,
        timestamps_s: np.ndarray,
        f_meas_b: np.ndarray,
        omega_meas_b: np.ndarray,
        ai_accel: Optional[np.ndarray] = None,
        clock_error_s: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Package raw multimodal PNT streams into structured dictionary."""
        n = len(timestamps_s)
        return {
            "stream_count": 4,
            "sample_count": n,
            "duration_s": float(timestamps_s[-1] - timestamps_s[0]) if n > 1 else 0.0,
            "imu_accel_norm_mean": float(np.mean(np.linalg.norm(f_meas_b, axis=1))),
            "imu_gyro_norm_mean": float(np.mean(np.linalg.norm(omega_meas_b, axis=1))),
            "has_quantum_sensors": ai_accel is not None,
            "has_quantum_clock": clock_error_s is not None,
        }


class CirclePNTSessionRecordAdapter:
    """Generates schema-compliant CIRCLE session records (contracts/session-record.schema.json)."""

    @staticmethod
    def create_model_result_record(
        experiment_id: str,
        duration_s: float,
        dt_s: float,
        position_rmse_m: float,
        velocity_rmse_m_s: float,
        drift_rate_m_hr: float,
        device_time_start_us: int = 0,
        artifact_id: str = "quantum_pnt_experiment.json",
    ) -> Dict[str, Any]:
        """Create validated MODEL_INFERRED session record with CRC-32C."""
        config = PNTExperimentConfig(duration_s=duration_s, dt_s=dt_s)
        for name, value in (("position_rmse_m", position_rmse_m), ("velocity_rmse_m_s", velocity_rmse_m_s), ("drift_rate_m_hr", drift_rate_m_hr)):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not experiment_id:
            raise ValueError("experiment_id must not be empty")
        total_frames = round(duration_s / dt_s)
        reference_frames = math.floor(duration_s * config.reference_rate_hz + 1e-9)
        record = {
            "schema_version": "2.0.0",
            "record_type": "MODEL_RESULT",
            "provenance": "MODEL_INFERRED",
            "device_time_start_us": device_time_start_us,
            "device_time_end_us": device_time_start_us + round(duration_s * 1e6),
            "status_flags": ["OK", "SIMULATED_INPUT", "REFERENCE_AIDED_ESTIMATE"],
            "source_stream_ids": ["SIMULATED_IMU", "SIMULATED_REFERENCE_ACCELEROMETER"],
            "source_sequence_ranges": [
                {"stream_id": "SIMULATED_IMU", "first_sequence": 0, "last_sequence": total_frames - 1},
                {"stream_id": "SIMULATED_REFERENCE_ACCELEROMETER", "first_sequence": 0, "last_sequence": reference_frames - 1},
            ],
            "model": {"name": "QPNS_X_TRANSLATION_BIAS_BENCHMARK", "version": "1.1.0", "artifact_id": artifact_id},
        }
        return seal_record(record)
