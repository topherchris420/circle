"""CIRCLE Telemetry Bridge and Session Record Adapter for IONS-X Emergence.

Bridges CIRCLE physiological session streams (PPG optical red/IR, protected EDA,
6-axis IMU, isolated sync, and resonance telemetry) to IONS-X ATOM 4-channel target
fields and converts emergent discoveries into schema-compliant MODEL_INFERRED
session records with CRC-32C integrity hashes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from models.session_records import compute_crc32c, seal_record, validate_session
from .engine import CHANNEL_NAMES, COVARIATE_NAMES, PerformanceMetrics, RunResult, TelemetryTargetField


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
    """Adapts aligned CIRCLE telemetry without silently replacing observations.

    Multiple columns can describe the same ATOM channel. Select one explicitly
    with channel_sources, or use the stable priority in CIRCLE_STREAM_MAPPINGS
    (the canonical channel name always takes precedence). All input columns and
    the selected mapping are retained on the target field.
    """

    def __init__(
        self, field_res: int = 128, default_freq_hz: float = 50.0,
        seed: int = 42, channel_sources: Mapping[str, str] | None = None,
    ) -> None:
        if isinstance(field_res, bool) or not isinstance(field_res, int) or field_res < 2:
            raise ValueError("field_res must be an integer >= 2")
        if not math.isfinite(default_freq_hz) or default_freq_hz <= 0:
            raise ValueError("default_freq_hz must be finite and positive")
        self.field_res = field_res
        self.default_freq_hz = default_freq_hz
        self.seed = seed
        self.channel_sources = dict(channel_sources or {})
        if set(self.channel_sources) - set(CHANNEL_NAMES):
            raise ValueError("channel_sources contains an unknown ATOM channel")

    def from_records(
        self, records: Sequence[Mapping[str, Any]],
        source_name: str = "circle_session_records",
    ) -> TelemetryTargetField:
        """Replay CRC-checked, aligned telemetry snapshots; never invent samples."""
        validate_session(records)
        if any(r["record_type"] == "GAP" for r in records):
            raise ValueError("Select a gap-free session segment before emergence analysis")
        rows: dict[int, dict[str, Any]] = {}
        for record in records:
            if record["record_type"] != "SAMPLE_CHUNK":
                continue
            timestamp = record["device_time_start_us"]
            reserved = {"timestamp", "device_time_us", "device_time_start_us", "device_time_end_us"}
            if any(key.strip().lower() in reserved for key in record["payload"]):
                raise ValueError("Telemetry payload must not override record timestamps")
            row = rows.setdefault(timestamp, {"device_time_us": timestamp})
            overlap = set(row) & set(record["payload"])
            if overlap:
                raise ValueError(f"Duplicate telemetry channels at {timestamp} us: {sorted(overlap)}")
            row.update(record["payload"])
        if not rows:
            raise ValueError("Session has no SAMPLE_CHUNK telemetry snapshots to analyze")
        return self.from_dataframe(pd.DataFrame([rows[t] for t in sorted(rows)]), source_name)

    def from_dataframe(
        self, df: pd.DataFrame, source_name: str = "circle_telemetry_df",
    ) -> TelemetryTargetField:
        if df.empty:
            raise ValueError("Input telemetry data must contain at least one row")
        # Pandas aligns assignments by label; reset before constructing a new frame.
        df = df.reset_index(drop=True).copy()
        if any(not isinstance(col, str) for col in df.columns):
            raise ValueError("Telemetry column names must be strings")
        lookup = {col.strip().lower(): col for col in df.columns}
        if len(lookup) != len(df.columns):
            raise ValueError("Telemetry column names must be unique ignoring case and whitespace")
        target_df = pd.DataFrame(index=df.index)
        if "timestamp" in lookup:
            target_df["timestamp"] = pd.to_datetime(df[lookup["timestamp"]], errors="raise", utc=True)
        elif "device_time_us" in lookup:
            values = df[lookup["device_time_us"]]
            if not pd.api.types.is_integer_dtype(values) or (values < 0).any():
                raise ValueError("device_time_us must contain nonnegative integer microseconds")
            target_df["timestamp"] = pd.to_datetime(values, unit="us", utc=True)
        else:
            target_df["timestamp"] = pd.to_datetime(
                np.arange(len(df)) / self.default_freq_hz, unit="s", utc=True,
            )

        selected: dict[str, str] = {}
        for channel in CHANNEL_NAMES:
            explicit = self.channel_sources.get(channel)
            candidates = [channel] + [alias for alias, target in CIRCLE_STREAM_MAPPINGS.items() if target == channel]
            if explicit is not None:
                if explicit not in df.columns:
                    raise ValueError(f"Selected channel source is missing: {explicit}")
                column = explicit
            else:
                column = next((lookup[alias] for alias in candidates if alias in lookup), None)
            if column is not None:
                target_df[channel] = df[column]
                selected[channel] = column
        if not selected:
            raise ValueError("No recognized CIRCLE telemetry channels were supplied")
        for covariate in COVARIATE_NAMES:
            if covariate in lookup:
                target_df[covariate] = df[lookup[covariate]]
        target = TelemetryTargetField.from_dataframe(
            target_df, field_res=self.field_res, rng=np.random.RandomState(self.seed), source=source_name,
        )
        target.input_values = df
        target.channel_sources = selected
        return target


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
        source_sequence_ranges: Sequence[Mapping[str, Any]] | None = None,
        status_flags: Sequence[str] | None = None,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a schema-compliant MODEL_INFERRED session record adhering to session-record.schema.json."""
        if run_result.frames < 1:
            raise ValueError("At least one evaluated frame is required")
        if source_stream_ids is None:
            source_stream_ids = ["SIMULATED_ATOM_FIELDS" if run_result.preset != "empirical" else "INPUT_TELEMETRY"]

        if status_flags is None:
            status_flags = ["OK", "SIMULATED_INPUT" if run_result.preset != "empirical" else "TELEMETRY_INPUT"]
            if metrics.coherence_frames:
                status_flags.append("COHERENCE_EVENTS_OBSERVED")

        if source_sequence_ranges is None:
            source_sequence_ranges = [
                {"stream_id": stream_id, "first_sequence": 0, "last_sequence": run_result.frames - 1}
                for stream_id in source_stream_ids
            ]

        record: dict[str, Any] = {
            "schema_version": cls.SCHEMA_VERSION,
            "record_type": "MODEL_RESULT",
            "provenance": "MODEL_INFERRED",
            "device_time_start_us": device_time_start_us,
            "device_time_end_us": device_time_end_us,
            "status_flags": list(sorted(set(status_flags))),
            "source_stream_ids": list(source_stream_ids),
            "source_sequence_ranges": list(source_sequence_ranges),
            "model": {
                "name": cls.MODEL_NAME,
                "version": cls.MODEL_VERSION,
                "artifact_id": artifact_id or str(run_result.output_path.name),
            },
        }

        return seal_record(record)
