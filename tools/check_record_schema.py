"""Semantic contract checker for session-record.schema.json.

This validates the repository's approved schema shape and business contract.
It is intentionally not a full JSON Schema evaluator.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/session-record.schema.json"
EXPECTED_ROOT_REQUIRED = [
    "schema_version",
    "record_type",
    "provenance",
    "device_time_start_us",
    "device_time_end_us",
    "status_flags",
    "crc32c",
]
EXPECTED_PROVENANCE = [
    "RAW_MEASURED",
    "DERIVED",
    "MODEL_INFERRED",
    "SIMULATED",
    "TEST",
    "INTERVENTION",
]
EXPECTED_RECORD_TYPES = [
    "SESSION_HEADER",
    "STREAM_DESCRIPTOR",
    "SAMPLE_CHUNK",
    "EVENT",
    "CLOCK_MAPPING",
    "CONFIG_CHANGE",
    "GAP",
    "FAULT",
    "MODEL_RESULT",
    "INTERVENTION",
    "SESSION_TRAILER",
]
EXPECTED_CONDITIONALS = {
    ("provenance", "MODEL_INFERRED"): ["source_stream_ids", "source_sequence_ranges", "model"],
    ("provenance", "INTERVENTION"): ["decision_id", "actuation_evidence_ids"],
    ("record_type", "GAP"): ["dropped_first_sequence", "dropped_last_sequence", "cause"],
}
REQUIRED_PROPERTY_DEFINITIONS = [
    *EXPECTED_ROOT_REQUIRED,
    "source_stream_ids",
    "source_sequence_ranges",
    "model",
    "decision_id",
    "actuation_evidence_ids",
    "dropped_first_sequence",
    "dropped_last_sequence",
    "cause",
]


def _load_schema() -> Any:
    try:
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("ERROR: failed to read schema JSON")
        return None


def _conditional_map(all_of: Any) -> dict[tuple[str, str], list[str]] | None:
    if not isinstance(all_of, list):
        print("ERROR: schema allOf must be an array")
        return None

    found: dict[tuple[str, str], list[str]] = {}
    for rule in all_of:
        if not isinstance(rule, dict):
            continue
        if_block = rule.get("if")
        then_block = rule.get("then")
        if not isinstance(if_block, dict) or not isinstance(then_block, dict):
            continue
        properties = if_block.get("properties")
        if not isinstance(properties, dict):
            continue

        for discriminant in ("provenance", "record_type"):
            branch = properties.get(discriminant)
            if isinstance(branch, dict) and isinstance(branch.get("const"), str):
                expected_if_required = [discriminant]
                if if_block.get("required") != expected_if_required:
                    print(
                        f"ERROR: conditional {discriminant}={branch['const']} must require only {expected_if_required}"
                    )
                    return None
                required = then_block.get("required")
                if not isinstance(required, list):
                    print(f"ERROR: conditional {discriminant}={branch['const']} then.required must be an array")
                    return None
                found[(discriminant, branch["const"])] = required
                break
    return found


def validate(schema: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return ["schema root must be an object"]

    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema draft URI mismatch")
    if schema.get("type") != "object":
        errors.append("schema root type must be object")
    if schema.get("additionalProperties") is not False:
        errors.append("schema root must set additionalProperties to false")
    if schema.get("required") != EXPECTED_ROOT_REQUIRED:
        errors.append("schema root required fields mismatch")

    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("schema defs must be an object")
    else:
        provenance = defs.get("provenance")
        record_type = defs.get("recordType")
        if not isinstance(provenance, dict) or provenance.get("enum") != EXPECTED_PROVENANCE:
            errors.append("provenance enum mismatch")
        if not isinstance(record_type, dict) or record_type.get("enum") != EXPECTED_RECORD_TYPES:
            errors.append("record_type enum mismatch")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("schema properties must be an object")
    else:
        for name in REQUIRED_PROPERTY_DEFINITIONS:
            if name not in properties:
                errors.append(f"missing property definition for {name}")

    conditional_map = _conditional_map(schema.get("allOf"))
    if conditional_map is None:
        errors.append("conditional structure invalid")
    else:
        if set(conditional_map) != set(EXPECTED_CONDITIONALS):
            errors.append("conditional set mismatch")
        for key, expected_required in EXPECTED_CONDITIONALS.items():
            if conditional_map.get(key) != expected_required:
                errors.append(f"conditional required mismatch for {key[0]}={key[1]}")

    return errors


def main() -> int:
    schema = _load_schema()
    if schema is None:
        return 1

    errors = validate(schema)
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("record schema: OK")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())