import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    design = json.loads((ROOT / "hardware/design-manifest.json").read_text(encoding="utf-8"))
    interfaces = json.loads((ROOT / "hardware/interfaces.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    refs = [part["ref"] for part in design["parts"]]
    if len(refs) != len(set(refs)):
        errors.append("duplicate reference designator")
    for connector in interfaces["connectors"]:
        if connector["domain"] == "LAB_ISO" and "BAT_HUMAN_GND" in connector["pins"]:
            errors.append(f"{connector['name']}: LAB_ISO connector exposes BAT_HUMAN_GND")
        if not connector["pins"]:
            errors.append(f"{connector['name']}: empty pin list")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("design manifest: OK")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
