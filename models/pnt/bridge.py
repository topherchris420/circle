"""CIRCLE Telemetry Bridge and Session Record Adapter for Quantum PNT."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

# Pure-Python Castagnoli CRC-32C (0x82F63B78 polynomial)
CRC32C_TABLE = []
for i in range(256):
    crc = i
    for _ in range(8):
        if crc & 1:
            crc = (crc >> 1) ^ 0x82F63B78
        else:
            crc = crc >> 1
    CRC32C_TABLE.append(crc)


def compute_crc32c(data: str | bytes) -> str:
    """Compute 8-character uppercase hex CRC-32C checksum."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ CRC32C_TABLE[(crc ^ byte) & 0xFF]
    return f"{crc ^ 0xFFFFFFFF:08X}"


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
        duration_us = int(round(duration_s * 1e6))
        end_us = device_time_start_us + duration_us
        total_frames = int(round(duration_s / dt_s))

        status_flags = ["OK", "CALIBRATED_NAVIGATION"]
        if position_rmse_m < 5.0:
            status_flags.append("HIGH_PRECISION_FIX")
        status_flags.append("QUANTUM_AUGMENTED")

        record = {
            "schema_version": "2.0.0",
            "record_type": "MODEL_RESULT",
            "provenance": "MODEL_INFERRED",
            "device_time_start_us": device_time_start_us,
            "device_time_end_us": end_us,
            "status_flags": status_flags,
            "source_stream_ids": [
                "CIRCLE_IMU_ICM42688",
                "CIRCLE_ATOM_INTERFEROMETER",
                "CIRCLE_GRAVITY_GRADIOMETER",
                "CIRCLE_QUANTUM_CLOCK"
            ],
            "source_sequence_ranges": [
                {
                    "stream_id": "CIRCLE_IMU_ICM42688",
                    "first_sequence": 0,
                    "last_sequence": total_frames
                },
                {
                    "stream_id": "CIRCLE_ATOM_INTERFEROMETER",
                    "first_sequence": 0,
                    "last_sequence": int(round(duration_s * 2.0))
                },
                {
                    "stream_id": "CIRCLE_GRAVITY_GRADIOMETER",
                    "first_sequence": 0,
                    "last_sequence": int(round(duration_s * 1.0))
                },
                {
                    "stream_id": "CIRCLE_QUANTUM_CLOCK",
                    "first_sequence": 0,
                    "last_sequence": total_frames
                }
            ],
            "model": {
                "name": "QPNS_X_QUANTUM_PNT",
                "version": "1.0.0",
                "artifact_id": artifact_id
            }
        }

        canonical_json = json.dumps(record, sort_keys=True, separators=(",", ":"))
        record["crc32c"] = compute_crc32c(canonical_json)
        return record
