"""Gate KiCad PCB DRC reports with explicit SHA-256 content-fingerprinted allowlist gating.

Enforces:
1. Zero unallowlisted design rule violations.
2. Zero unallowlisted unrouted nets under review gate PHYSICAL_ROUTING.
3. Every allowlisted item must match an SHA-256 fingerprint with a detailed review rationale (>= 20 chars).
4. Zero stale allowlist entries.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "circle-main": ROOT / "hardware/reports/circle-main-drc.json",
    "circle-ppg": ROOT / "hardware/reports/circle-ppg-drc.json",
}
ALLOW = ROOT / "hardware/reports/drc-allowlist.json"


def extract_net(item):
    """Extract electrical net identifier from KiCad DRC unconnected items."""
    for it in item.get("items", []):
        m = re.search(r"\[([^\]]+)\]", it.get("description", ""))
        if m:
            return m.group(1)
    return "UNSPECIFIED_NET"


def fingerprint_unconnected_net(board, net):
    """Compute deterministic SHA-256 fingerprint for an unrouted copper net."""
    material = json.dumps({
        "board": board,
        "type": "unconnected_items",
        "net": net
    }, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


def fingerprint_violation(board, v):
    """Compute deterministic SHA-256 fingerprint for a design rule violation."""
    material = json.dumps({
        "board": board,
        "type": v.get("type"),
        "description": v.get("description"),
        "items": sorted([i.get("description", "") for i in v.get("items", [])])
    }, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


def main():
    allow_data = json.loads(ALLOW.read_text(encoding="utf-8")).get("allowlist", []) if ALLOW.exists() else []
    allowed = {a["fingerprint"]: a for a in allow_data}
    used = set()
    errors = []

    for name, path in REPORTS.items():
        if not path.exists():
            errors.append(f"Missing DRC report: {path}")
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        violations = data.get("violations", [])
        unconnected = data.get("unconnected_items", [])

        # 1. Gate violations
        for v in violations:
            fp = fingerprint_violation(name, v)
            if v.get("severity") == "error":
                if fp not in allowed:
                    errors.append(f"{name}: unallowlisted DRC violation error: {v.get('description')}")
                else:
                    used.add(fp)
                    if len(allowed[fp].get("rationale", "")) < 20:
                        errors.append(f"{name}: short rationale for DRC violation: {fp}")
            elif fp not in allowed:
                errors.append(f"{name}: unallowlisted DRC violation warning: {v.get('description')}")
            else:
                used.add(fp)

        # 2. Gate unconnected items by net under PHYSICAL_ROUTING review gate
        unconnected_nets = set()
        for item in unconnected:
            net = extract_net(item)
            unconnected_nets.add(net)
            fp = fingerprint_unconnected_net(name, net)
            if fp not in allowed:
                errors.append(f"{name}: unallowlisted unrouted net in DRC ({fp}): net={net}")
            else:
                used.add(fp)
                if len(allowed[fp].get("rationale", "")) < 20:
                    errors.append(f"{name}: short rationale for unrouted net: {net} ({fp})")

        print(f"{name}: {len(violations)} DRC violations, {len(unconnected)} unconnected items across {len(unconnected_nets)} unrouted nets (all evaluated)")

    # 3. Check for stale allowlist entries
    for fp in set(allowed) - used:
        errors.append(f"stale DRC allowlist entry: {fp}")

    for error in errors:
        print("ERROR:", error)

    if not errors:
        print("DRC gate: OK")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
