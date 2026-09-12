"""Session record serialization, schema validation, and replay integrity checks.

CRC-32C detects accidental corruption; it is not authentication. Checksums cover
sorted, compact, ASCII-escaped UTF-8 JSON with the crc32c field omitted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "contracts/session-record.schema.json"


class SessionRecordError(ValueError):
    """A record cannot be used as valid experimental evidence."""


def _crc_table() -> tuple[int, ...]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
        table.append(crc)
    return tuple(table)


CRC32C_TABLE = _crc_table()


def compute_crc32c(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ CRC32C_TABLE[(crc ^ byte) & 0xFF]
    return f"{crc ^ 0xFFFFFFFF:08X}"


def canonical_record_bytes(record: Mapping[str, Any]) -> bytes:
    body = {key: value for key, value in record.items() if key != "crc32c"}
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SessionRecordError(f"Record must contain finite JSON values: {exc}") from exc


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_record(record: Any) -> None:
    """Check actual record contents, semantic ranges, and the complete checksum."""
    errors = sorted(_validator().iter_errors(record), key=lambda e: str(e.json_path))
    if errors:
        raise SessionRecordError("; ".join(f"{e.json_path}: {e.message}" for e in errors))
    if record["device_time_end_us"] < record["device_time_start_us"]:
        raise SessionRecordError("device_time_end_us precedes device_time_start_us")

    ranges = record.get("source_sequence_ranges", [])
    stream_ids = record.get("source_stream_ids", [])
    if ranges or stream_ids:
        if {r["stream_id"] for r in ranges} != set(stream_ids):
            raise SessionRecordError("Source sequence ranges must cover exactly source_stream_ids")
        previous: dict[str, int] = {}
        for item in sorted(ranges, key=lambda r: (r["stream_id"], r["first_sequence"])):
            first, last = item["first_sequence"], item["last_sequence"]
            if last < first:
                raise SessionRecordError("Source sequence range is reversed")
            if first <= previous.get(item["stream_id"], -1):
                raise SessionRecordError("Source sequence ranges overlap")
            previous[item["stream_id"]] = last
    if record["record_type"] == "GAP":
        if record["dropped_last_sequence"] < record["dropped_first_sequence"]:
            raise SessionRecordError("Dropped sequence range is reversed")
    if record["record_type"] == "SAMPLE_CHUNK":
        if record["device_time_start_us"] != record["device_time_end_us"]:
            raise SessionRecordError("A telemetry snapshot must have equal start and end times")
    expected = compute_crc32c(canonical_record_bytes(record))
    if record["crc32c"].upper() != expected:
        raise SessionRecordError(f"CRC-32C mismatch: expected {expected}")


def seal_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return an independent, validated record with a freshly calculated checksum."""
    canonical = canonical_record_bytes(record)
    sealed = json.loads(canonical)
    sealed["crc32c"] = compute_crc32c(canonical)
    validate_record(sealed)
    return sealed


def validate_session(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate records and per-stream snapshot ordering, including explicit gaps."""
    if not records:
        raise SessionRecordError("Session contains no records")
    next_sequence: dict[str, int] = {}
    last_time: dict[str, int] = {}
    for index, record in enumerate(records, 1):
        try:
            validate_record(record)
            stream = record.get("stream_id")
            if record["record_type"] == "GAP" and stream is not None:
                first = record["dropped_first_sequence"]
                if first != next_sequence.get(stream, first):
                    raise SessionRecordError(f"GAP does not follow stream {stream}'s last sequence")
                next_sequence[stream] = record["dropped_last_sequence"] + 1
            if record["record_type"] == "SAMPLE_CHUNK":
                sequence = record["sequence"]
                if sequence != next_sequence.get(stream, sequence):
                    raise SessionRecordError(f"Stream {stream} has a duplicate, reversed, or undeclared missing sequence")
                timestamp = record["device_time_start_us"]
                if timestamp <= last_time.get(stream, -1):
                    raise SessionRecordError(f"Stream {stream} timestamps must increase strictly")
                next_sequence[stream] = sequence + 1
                last_time[stream] = timestamp
        except SessionRecordError as exc:
            raise SessionRecordError(f"Record {index}: {exc}") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise SessionRecordError(f"Duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise SessionRecordError(f"Non-finite JSON constant: {value}")


def load_session(path: str | Path) -> list[dict[str, Any]]:
    """Read a single JSON record, a JSON array, or newline-delimited records."""
    text = Path(path).read_text(encoding="utf-8")
    options = {"object_pairs_hook": _unique_object, "parse_constant": _reject_constant}
    try:
        parsed = json.loads(text, **options)
    except json.JSONDecodeError:
        try:
            parsed = [json.loads(line, **options) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise SessionRecordError(f"Invalid session JSON: {exc}") from exc
    records = parsed if isinstance(parsed, list) else [parsed]
    validate_session(records)
    return records
