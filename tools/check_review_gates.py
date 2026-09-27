"""Validate machine-readable review gates and derive what they authorize.

A gate may be CLOSED only with a named reviewer, a closure date, and artifacts
that exist. Gates needing physical measurement, accredited testing,
independent review, or ethics approval cannot be closed by any automated check.
The derived authorizations are printed; with any blocking gate open they are
NOT_AUTHORIZED. Exit status 0 means the gate file is well formed, not that
anything is authorized.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
GATES = ROOT / "hardware/review-gates.json"
SCHEMA = ROOT / "contracts/review-gates.schema.json"
MANIFEST = ROOT / "hardware/design-manifest.json"
HUMAN_ONLY_EVIDENCE = {"INDEPENDENT_REVIEW", "PHYSICAL_MEASUREMENT", "ACCREDITED_TEST", "ETHICS_APPROVAL"}
AUTHORIZATIONS = ("FABRICATION", "POWERED_BENCH_TEST", "HUMAN_CONNECTION", "INTERPRETATION", "RESEARCH_EXECUTION")


def load_gates(path: Path = GATES) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def gate_errors(doc: dict, root: Path = ROOT) -> list[str]:
    errors = [f"{'/'.join(map(str, e.path))}: {e.message}"
              for e in Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(doc)]
    if errors:
        return errors
    ids = [g["id"] for g in doc["gates"]]
    if len(ids) != len(set(ids)):
        errors.append("Gate ids must be unique")
    manifest_gates = set(json.loads(MANIFEST.read_text(encoding="utf-8"))["review_gates"])
    for missing in sorted(manifest_gates - set(ids)):
        errors.append(f"Design-manifest gate {missing} has no machine-readable entry")
    for gate in doc["gates"]:
        for artifact in gate["artifacts"]:
            if not (root / artifact).exists():
                errors.append(f"{gate['id']}: artifact {artifact} does not exist")
        if gate.get("automated_check") and not (root / gate["automated_check"]).is_file():
            errors.append(f"{gate['id']}: automated check {gate['automated_check']} does not exist")
        if gate["status"] == "CLOSED":
            if not gate["reviewer"] or not gate.get("closed_on") or not gate["artifacts"]:
                errors.append(f"{gate['id']}: CLOSED requires reviewer, closed_on, and artifacts")
            if set(gate["evidence_kind"]) & HUMAN_ONLY_EVIDENCE and (gate["reviewer"] or "").lower().startswith(("ci", "automated", "claude", "bot")):
                errors.append(f"{gate['id']}: evidence of kind {sorted(set(gate['evidence_kind']) & HUMAN_ONLY_EVIDENCE)} "
                              "cannot be closed by an automated reviewer")
    return errors


def authorizations(doc: dict) -> dict[str, dict]:
    """Each authorization is granted only when every gate that blocks it is CLOSED."""
    out = {}
    for name in AUTHORIZATIONS:
        blocking = [g["id"] for g in doc["gates"] if name in g["blocks"] and g["status"] != "CLOSED"]
        out[name] = {"status": "AUTHORIZED_BY_GATES" if not blocking else "NOT_AUTHORIZED", "open_gates": blocking}
    return out


def main() -> int:
    doc = load_gates()
    errors = gate_errors(doc)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    open_gates = [g for g in doc["gates"] if g["status"] != "CLOSED"]
    print(f"Review gates: {len(doc['gates'])} defined, {len(open_gates)} open")
    for name, entry in authorizations(doc).items():
        suffix = f" ({len(entry['open_gates'])} open gates)" if entry["open_gates"] else ""
        print(f"  {name:<20} {entry['status']}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
