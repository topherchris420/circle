"""Audit a saved CIRCLE session without running a model or driving hardware."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.session_records import SessionRecordError, canonical_record_bytes, load_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="Single JSON record, JSON array, or NDJSON session")
    args = parser.parse_args(argv)
    try:
        records = load_session(args.session)
    except (OSError, ValueError) as exc:
        print(f"Session invalid: {exc}", file=sys.stderr)
        return 1
    content = b"\n".join(canonical_record_bytes(record) for record in records)
    print(json.dumps({
        "valid": True,
        "record_count": len(records),
        "record_types": dict(sorted(Counter(r["record_type"] for r in records).items())),
        "provenance": dict(sorted(Counter(r["provenance"] for r in records).items())),
        "device_time_start_us": min(r["device_time_start_us"] for r in records),
        "device_time_end_us": max(r["device_time_end_us"] for r in records),
        "canonical_content_sha256": hashlib.sha256(content).hexdigest(),
        "authentication_verified": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
