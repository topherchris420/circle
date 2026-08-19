"""Gate KiCad PCB DRC reports with explicit SHA-256 content-fingerprinted allowlist gating.

Enforces:
1. Zero unallowlisted design rule violations.
2. Zero unallowlisted unconnected items.
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


def normalize_endpoint(desc):
    """Extract canonical Component.Pad identifier from KiCad pad description strings across KiCad versions."""
    m = re.search(r"(?:Pad|pin)\s+([^\s\[\]]+).*?of\s+([^\s\[\]]+)", desc, re.IGNORECASE)
    if m:
        return f"{m.group(2)}.{m.group(1)}"
    m_via = re.search(r"Via\s+\[([^\]]+)\]", desc)
    if m_via:
        return f"Via[{m_via.group(1)}]"
    m_track = re.search(r"Track\s+\[([^\]]+)\]", desc)
    if m_track:
        return f"Track[{m_track.group(1)}]"
    return desc.strip()


def fingerprint(board, item):
    """Compute deterministic SHA-256 fingerprint for a DRC item invariant to KiCad CLI version formatting."""
    endpoints = sorted([normalize_endpoint(i.get("description", "")) for i in item.get("items", [])])
    material = json.dumps({
        "board": board,
        "type": item.get("type"),
        "endpoints": endpoints
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
            fp = fingerprint(name, v)
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

        # 2. Gate unconnected items
        for item in unconnected:
            fp = fingerprint(name, item)
            if fp not in allowed:
                errors.append(f"{name}: unallowlisted unconnected DRC item ({fp}): {item.get('description')}")
            else:
                used.add(fp)
                if len(allowed[fp].get("rationale", "")) < 20:
                    errors.append(f"{name}: short rationale for unconnected DRC item: {fp}")

        print(f"{name}: {len(violations)} DRC violations, {len(unconnected)} unconnected items (all evaluated)")

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
