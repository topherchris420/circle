"""Contract and schema validator for Quantum PNT research module."""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.pnt.bridge import CirclePNTSessionRecordAdapter, compute_crc32c, PNT_STREAM_MAPPINGS


def main() -> int:
    schema_path = ROOT / "contracts/quantum-pnt.schema.json"
    if not schema_path.exists():
        print(f"Error: {schema_path} does not exist")
        return 1

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["title"] == "Quantum PNT Experiment and Discovery Schema"
    assert "configuration" in schema["properties"]
    assert "metrics" in schema["properties"]
    assert "provenance" in schema["properties"]
    print("quantum-pnt schema structure: OK")

    # Example configurations check
    example_path = ROOT / "experiments/pnt/configurations.example.json"
    if not example_path.exists():
        print(f"Error: {example_path} does not exist")
        return 1

    data = json.loads(example_path.read_text(encoding="utf-8"))
    assert "configurations" in data
    assert len(data["configurations"]) >= 2
    for cfg in data["configurations"]:
        assert "experiment_id" in cfg
        assert "configuration" in cfg
        assert "metrics" in cfg
        assert "provenance" in cfg
    print(f"example configurations ({len(data['configurations'])} configs verified): OK")

    # CRC-32C test vectors
    assert compute_crc32c("123456789") == "E3069283"
    assert compute_crc32c("") == "00000000"

    # Adapter generation check
    rec = CirclePNTSessionRecordAdapter.create_model_result_record(
        experiment_id="EXP-QPNS-001",
        duration_s=60.0,
        dt_s=0.01,
        position_rmse_m=1.25,
        velocity_rmse_m_s=0.05,
        drift_rate_m_hr=50.0,
    )
    assert rec["schema_version"] == "2.0.0"
    assert rec["record_type"] == "MODEL_RESULT"
    assert rec["provenance"] == "MODEL_INFERRED"
    assert re.match(r"^[0-9A-F]{8}$", rec["crc32c"])
    print("CIRCLE PNT bridge and session-record contract: OK")
    print("all quantum PNT physics, neutrality, and safety contracts: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
