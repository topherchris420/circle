"""Gate KiCad PCB DRC reports for 0 design rule violations."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "circle-main": ROOT / "hardware/reports/circle-main-drc.json",
    "circle-ppg": ROOT / "hardware/reports/circle-ppg-drc.json",
}


def main():
    errors = []
    for name, path in REPORTS.items():
        if not path.exists():
            errors.append(f"Missing DRC report: {path}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        violations = data.get("violations", [])
        if len(violations) > 0:
            errors.append(f"{name}: {len(violations)} DRC rule violations detected")
        unconnected = len(data.get("unconnected_items", []))
        print(f"{name}: {len(violations)} DRC violations, {unconnected} unconnected nets")

    for error in errors:
        print("ERROR:", error)

    if not errors:
        print("DRC gate: OK")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
