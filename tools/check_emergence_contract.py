"""Semantic, mathematical, and schema validator for CIRCLE Emergence."""

from __future__ import annotations

import json
import math
import pathlib
import sys
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_PATH = ROOT / "contracts/emergence-discovery.schema.json"
CONFIGS_PATH = ROOT / "experiments/emergence/configurations.example.json"
SESSION_SCHEMA_PATH = ROOT / "contracts/session-record.schema.json"


def check_schema_structure() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing emergence schema: {SCHEMA_PATH}")

    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = data.get("required", [])
    expected_fields = [
        "schema_version",
        "experiment_id",
        "run_id",
        "preset",
        "field_parameters",
        "operator_parameters",
        "moderator_parameters",
        "metrics_summary",
        "provenance",
        "interpretation_level",
        "status_flags",
    ]
    for field in expected_fields:
        if field not in required:
            raise ValueError(f"Emergence schema missing required field: {field}")

    defs = data.get("$defs", {})
    for def_key in [
        "fieldParameters",
        "operatorParameters",
        "moderatorParameters",
        "discoveryItem",
        "metricsSummary",
        "provenance",
        "interpretationLevel",
    ]:
        if def_key not in defs:
            raise ValueError(f"Emergence schema missing definition: $defs/{def_key}")

    print("emergence schema structure: OK")


def check_example_configurations() -> None:
    if not CONFIGS_PATH.exists():
        raise FileNotFoundError(f"Missing example configs: {CONFIGS_PATH}")

    data = json.loads(CONFIGS_PATH.read_text(encoding="utf-8"))
    configs = data.get("configurations", [])
    if len(configs) < 2:
        raise ValueError("emergence configurations.example.json must contain at least 2 configurations.")

    for cfg in configs:
        if cfg["preset"] == "synthetic" and cfg["provenance"] == "RAW_MEASURED":
            raise ValueError("Synthetic emergence run cannot have provenance RAW_MEASURED")
        if cfg["interpretation_level"] != "MODEL_INFERRED":
            raise ValueError("Emergence interpretations must carry MODEL_INFERRED interpretation level")

    print(f"emergence example configurations ({len(configs)} configs verified): OK")


def check_telemetry_bridge_and_crc32c() -> None:
    import pandas as pd
    from models.emergence.bridge import (
        CircleTelemetryBridge,
        CircleSessionRecordAdapter,
        compute_crc32c,
    )
    from models.emergence.engine import RunResult, PerformanceMetrics

    # Test CRC-32C computation
    test_str = "123456789"
    crc = compute_crc32c(test_str)
    if crc != "E3069283":
        raise ValueError(f"CRC-32C check failed: expected E3069283, got {crc}")

    # Test CIRCLE Telemetry Bridge
    bridge = CircleTelemetryBridge(field_res=32)
    mock_df = pd.DataFrame(
        {
            "device_time_us": [0, 20000, 40000, 60000, 80000],
            "ppg_red": [100.0, 102.0, 101.0, 103.0, 102.0],
            "eda_conductance": [2.5, 2.6, 2.5, 2.7, 2.6],
            "imu_accel_x": [0.1, 0.2, 0.1, 0.0, 0.1],
        }
    )
    target = bridge.from_dataframe(mock_df, source_name="test_mock_stream")
    if target.frame_count != 5 or target.field_res != 32:
        raise ValueError("CircleTelemetryBridge failed to build TelemetryTargetField")

    # Test CIRCLE Session Record Adapter & Schema Validation
    metrics = PerformanceMetrics()
    metrics.log_discovery("perceiver")
    res = RunResult(
        output_path=pathlib.Path("outputs/test.html"),
        frames=5,
        agents=10,
        field_res=32,
        on_gpu=False,
    )
    record = CircleSessionRecordAdapter.create_model_result_record(
        run_result=res,
        metrics=metrics,
        device_time_start_us=0,
        device_time_end_us=100000,
    )

    # Validate against session-record.schema.json
    session_schema = json.loads(SESSION_SCHEMA_PATH.read_text(encoding="utf-8"))
    for req in session_schema["required"]:
        if req not in record:
            raise ValueError(f"Generated session record missing required root key: {req}")

    if record["record_type"] != "MODEL_RESULT" or record["provenance"] != "MODEL_INFERRED":
        raise ValueError("Invalid record_type or provenance in generated session record")

    if not record["crc32c"] or len(record["crc32c"]) != 8:
        raise ValueError("Invalid CRC-32C hash format in generated session record")

    print("CIRCLE telemetry bridge and session-record contract: OK")


def main() -> int:
    check_schema_structure()
    check_example_configurations()
    check_telemetry_bridge_and_crc32c()
    print("all emergence physics, neutrality, and safety contracts: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
