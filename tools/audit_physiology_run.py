"""Independently audit an exported CIRCLE physiology run directory.

Recomputes instead of trusting: artifact SHA-256s, the session contract and
CRC-32C, raw-content bindings, every pipeline output (from raw/ alone), every
closed-loop decision (replayed), sample-range lineage, and intervention
evidence chains. Exit status 0 only if every check passes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.physiology.audit import audit_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_directory", type=Path, help="Directory written by tools/run_physiology_twin.py")
    args = parser.parse_args(argv)
    try:
        result = audit_run(args.run_directory)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
