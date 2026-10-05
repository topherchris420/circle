"""Validate capabilities.json: every module has an honest status, real paths, and removable extensions.

Architectural test: no instrument-core or closed-loop Python module may import a
research extension or a hardware adapter. Both must be removable without
breaking the instrument: CIRCLE runs with neither.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "capabilities.json"
CORE_LAYERS = {"INSTRUMENT_CORE", "CLOSED_LOOP"}
REMOVABLE_LAYERS = {"RESEARCH_EXTENSION", "HARDWARE_ADAPTER"}


def _python_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    return sorted(path.rglob("*.py")) if path.is_dir() else []


def _evidence_exists(item: str) -> bool:
    if item.startswith("python "):
        return (ROOT / item.split()[1]).is_file()
    return (ROOT / item.split("#", 1)[0]).exists()


def registry_errors(doc: dict) -> list[str]:
    errors = []
    statuses, layers = set(doc["statuses"]), set(doc["layers"])
    ids = [m["id"] for m in doc["modules"]]
    if len(ids) != len(set(ids)):
        errors.append("Module ids must be unique")
    removable_packages = set()
    for module in doc["modules"]:
        name = module["id"]
        if module["status"] not in statuses:
            errors.append(f"{name}: unknown status {module['status']}")
        if module["layer"] not in layers:
            errors.append(f"{name}: unknown layer {module['layer']}")
        if not module.get("not_claimed"):
            errors.append(f"{name}: every module must state what it does not claim")
        for path in module["paths"]:
            if not (ROOT / path).exists():
                errors.append(f"{name}: path {path} does not exist")
        for item in module["evidence"]:
            if not _evidence_exists(item):
                errors.append(f"{name}: evidence {item} does not exist")
        if module["layer"] in REMOVABLE_LAYERS:
            if not module["removable"]:
                errors.append(f"{name}: {module['layer'].lower().replace('_', ' ')} modules must be removable")
            for path in module["paths"]:
                if path.startswith("models/") and (ROOT / path).is_dir():
                    removable_packages.add(path.replace("/", "."))
    for module in doc["modules"]:
        if module["layer"] not in CORE_LAYERS:
            continue
        for path in module["paths"]:
            for file in _python_files(ROOT / path):
                tree = ast.parse(file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = [node.module or ""] if isinstance(node, ast.ImportFrom) else \
                        [a.name for a in node.names] if isinstance(node, ast.Import) else []
                    for imported in names:
                        if any(imported == pkg or imported.startswith(pkg + ".") for pkg in removable_packages):
                            errors.append(f"{file.relative_to(ROOT)} (core) imports removable module {imported}")
    return errors


def main() -> int:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors = registry_errors(doc)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    for layer in doc["layers"]:
        print(layer)
        for module in doc["modules"]:
            if module["layer"] == layer:
                print(f"  {module['id']:<28} {module['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
