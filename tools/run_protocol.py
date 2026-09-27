"""Validate, authorize, and execute CIRCLE experiment protocols (simulation only).

  validate   deterministic checks; exit 0 only for VALID_FOR_SIMULATION
  authorize  a named human binds an authorization to the protocol's SHA-256
  run        execute an authorized protocol against the twin and write results

Proposal, validation, authorization, execution, and measurement stay separate
steps. Nothing here can target hardware or a person.
"""

from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.physiology.evidence import dumps
from models.protocols import ProtocolError, authorize, execute, validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("protocol", type=Path)
    a = sub.add_parser("authorize")
    a.add_argument("protocol", type=Path)
    a.add_argument("--reviewer", required=True, help="Name of the human authorizing simulation execution")
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--date", default=datetime.date.today().isoformat())
    r = sub.add_parser("run")
    r.add_argument("protocol", type=Path)
    r.add_argument("--authorization", type=Path, required=True)
    r.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    try:
        if args.command == "validate":
            result = validate(protocol)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "VALID_FOR_SIMULATION" else 1
        if args.command == "authorize":
            args.output.write_bytes(dumps(authorize(protocol, args.reviewer, args.date)))
            print(f"Authorization written to {args.output} (simulation only)")
            return 0
        result = execute(protocol, json.loads(args.authorization.read_text(encoding="utf-8")))
    except ProtocolError as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(dumps(result))
    for key, test in result["tests"].items():
        adjusted = f" (Holm {test['p_adjusted']:.4f})" if "p_adjusted" in test else ""
        print(f"  {key:<16} {test['evidence_class']:<18} diff {test['mean_difference_active_minus_sham']:+.4f}  "
              f"p {test['p_value']:.4f}{adjusted}  {test['conclusion']}")
    print(f"  replays match: {result['replays_match']}")
    print(result["interpretation"])
    return 0 if result["replays_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
