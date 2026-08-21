"""CIRCLE Telemetry Bridge and Session Record Adapter for IONS-X Emergence.

Bridges CIRCLE physiological session streams (PPG optical red/IR, protected EDA,
6-axis IMU, isolated sync, and resonance telemetry) to IONS-X ATOM 4-channel target
fields and converts emergent discoveries into schema-compliant MODEL_INFERRED
session records with CRC-32C integrity hashes.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .engine import (
    CFG,
    CHANNEL_NAMES,
    COVARIATE_NAMES,
    Observation,
    PerformanceMetrics,
    RunResult,
    TelemetryTargetField,
    rng,
)

CRC32C_POLYNOMIAL = 0x82F63B78


def _generate_crc32c_table() -> list[int]:
    table = []
    for i in range(256):
        curr = i
        for _ in range(8):
            if curr & 1:
                curr = (curr >> 1) ^ CRC32C_POLYNOMIAL
            else:
                curr >>= 1
        table.append(curr)
    return table


_CRC32C_TABLE = _generate_crc32c_table()


def compute_crc32c(data: bytes | str) -> str:
    """Compute 8-character uppercase hex CRC-32C checksum."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ byte) & 0xFF]
    crc ^= 0xFFFFFFFF
    return f"{crc:08X}"


CIRCLE_STREAM_MAPPINGS: Mapping[str, str] = {
    # Channel 0: EM/RF / Motion / Inertial
    "ppg_accel": "em_rf",
    "imu_accel_x": "em_rf",
    "imu_accel_y": "em_rf",
    "imu_accel_z": "em_rf",
    "imu_gyro_x": "em_rf",
    "imu_gyro_y": "em_rf",
    "imu_gyro_z": "em_rf",
    "rf_noise": "em_rf",
    "em_rf": "em_rf",
    "electromagnetic_rf": "em_rf",
    # Channel 1: Optical / PPG
    "ppg_red": "optical_ir",
    "ppg_ir": "optical_ir",
    "optical_ir": "optical_ir",
    "optical_raw": "optical_ir",
    "pixel_variance": "optical_ir",
    # Channel 2: EDA / Consciousness Proxy / Resonance Response
    "eda_raw": "consciousness_proxy",
    "eda_conductance": "consciousness_proxy",
    "eda_admittance": "consciousness_proxy",
    "reg_variance": "consciousness_proxy",
    "consciousness_proxy": "consciousness_proxy",
    "resonance_amplitude": "consciousness_proxy",
    "resonance_score": "consciousness_proxy",
    # Channel 3: Control Baseline / Sham
    "control_baseline": "control_baseline",
    "sham_control": "control_baseline",
}


class CircleTelemetryBridge:
    """Adapts CIRCLE biosignal and resonance telemetry into IONS-X target fields."""

    def __init__(self, field_res: int = 128, default_freq_hz: float = 50.0) -> None:
        self.field_res = field_res
        self.default_freq_hz = default_freq_hz

    def from_records(
        self,
        records: Sequence[Mapping[str, Any]],
        source_name: str = "circle_session_records",
    ) -> TelemetryTargetField:
        """Convert a sequence of CIRCLE session records into a TelemetryTargetField."""
        rows: list[dict[str, Any]] = []
        for r in records:
            time_start_us = r.get("device_time_start_us", 0)
            timestamp = pd.Timestamp("1970-01-01", tz="UTC") + pd.Timedelta(microseconds=time_start_us)
            payload = r.get("payload", r)
            row: dict[str, Any] = {"timestamp": timestamp}
            for k, v in payload.items():
                if isinstance(v, (int, float)):
                    row[k] = float(v)
            rows.append(row)

        if not rows:
            df = pd.DataFrame(
                {
                    "timestamp": pd.date_range("1970-01-01", periods=10, freq="min", tz="UTC"),
                    "em_rf": np.zeros(10),
                    "optical_ir": np.zeros(10),
                    "consciousness_proxy": np.zeros(10),
                    "control_baseline": np.zeros(10),
                }
            )
        else:
            df = pd.DataFrame(rows)
        return self.from_dataframe(df, source_name=source_name)

    def from_dataframe(
        self,
        df: pd.DataFrame,
        source_name: str = "circle_telemetry_df",
    ) -> TelemetryTargetField:
        """Convert DataFrame containing CIRCLE stream names to a TelemetryTargetField."""
        target_df = pd.DataFrame(index=range(len(df)))

        # Fill timestamp
        if "timestamp" in df.columns:
            target_df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        elif "device_time_us" in df.columns:
            target_df["timestamp"] = pd.to_datetime(df["device_time_us"], unit="us", utc=True)
        else:
            target_df["timestamp"] = pd.date_range("1970-01-01", periods=len(df), freq="20ms", tz="UTC")

        # Initialize ATOM channels
        for ch in CHANNEL_NAMES:
            target_df[ch] = 0.0

        for col in df.columns:
            canonical_ch = CIRCLE_STREAM_MAPPINGS.get(col.lower())
            if canonical_ch is not None and canonical_ch in CHANNEL_NAMES:
                numeric_val = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype("float64")
                target_df[canonical_ch] = numeric_val

        # Covariates
        for cov in COVARIATE_NAMES:
            if cov in df.columns:
                target_df[cov] = pd.to_numeric(df[cov], errors="coerce").fillna(0.0).astype("float64")
            else:
                target_df[cov] = 0.0

        return TelemetryTargetField.from_dataframe(
            target_df,
            field_res=self.field_res,
            rng=rng,
            source=source_name,
        )


class CircleSessionRecordAdapter:
    """Encapsulates emergence discoveries and summaries into valid CIRCLE session records."""

    SCHEMA_VERSION = "2.0.0"
    MODEL_NAME = "IONS_X_DEEP_EMERGENCE"
    MODEL_VERSION = "0.3.0"

    @classmethod
    def create_model_result_record(
        cls,
        run_result: RunResult,
        metrics: PerformanceMetrics,
        device_time_start_us: int = 0,
        device_time_end_us: int = 1_000_000,
        source_stream_ids: Sequence[str] | None = None,
        status_flags: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Create a schema-compliant MODEL_INFERRED session record adhering to session-record.schema.json."""
        if source_stream_ids is None:
            source_stream_ids = ["CIRCLE_PPG_RAW", "CIRCLE_EDA_FRONTEND", "CIRCLE_IMU_ICM42688"]

        if status_flags is None:
            status_flags = ["OK", "CALIBRATED_EMERGENCE"]
            if metrics.coherence_frames:
                status_flags.append("COHERENCE_EVENTS_OBSERVED")

        source_sequence_ranges = [
            {"stream_id": stream_id, "first_sequence": 0, "last_sequence": run_result.frames}
            for stream_id in source_stream_ids
        ]

        record: dict[str, Any] = {
            "schema_version": cls.SCHEMA_VERSION,
            "record_type": "MODEL_RESULT",
            "provenance": "MODEL_INFERRED",
            "device_time_start_us": int(device_time_start_us),
            "device_time_end_us": int(device_time_end_us),
            "status_flags": list(sorted(set(status_flags))),
            "source_stream_ids": list(source_stream_ids),
            "source_sequence_ranges": source_sequence_ranges,
            "model": {
                "name": cls.MODEL_NAME,
                "version": cls.MODEL_VERSION,
                "artifact_id": str(run_result.output_path.name),
            },
        }

        # Canonical bytes representation for CRC32C computation
        canonical_bytes = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        record["crc32c"] = compute_crc32c(canonical_bytes)
        return record
