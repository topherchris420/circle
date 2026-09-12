"""Reject absent, malformed, or mismatched KiCad evidence before allowlist gates."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def pinned_version() -> str:
    return json.loads((ROOT / "toolchain.json").read_text(encoding="utf-8"))["kicad"]


def require_version(version: str) -> None:
    match = re.match(r"^(\d+\.\d+\.\d+)(?:$|[^\d.])", version.strip())
    if match is None or match.group(1) != pinned_version():
        raise ValueError(f"Expected KiCad {pinned_version()}, received {version!r}")


def load_report(path: Path, kind: str, source: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("$schema") != f"https://schemas.kicad.org/{kind}.v1.json":
        raise ValueError(f"{path.name}: invalid {kind.upper()} report schema")
    require_version(data.get("kicad_version", ""))
    if data.get("source") != source:
        raise ValueError(f"{path.name}: source must be {source}")
    if set(data.get("included_severities", [])) != {"error", "warning", "exclusion"}:
        raise ValueError(f"{path.name}: report must include all severities")
    fields = ("sheets",) if kind == "erc" else ("violations", "unconnected_items", "schematic_parity")
    for field in fields:
        if not isinstance(data.get(field), list):
            raise ValueError(f"{path.name}: missing or invalid {field}")
    if kind == "erc":
        if not data["sheets"]:
            raise ValueError(f"{path.name}: ERC report contains no sheets")
        for sheet in data["sheets"]:
            if not isinstance(sheet, dict) or not isinstance(sheet.get("path"), str) or not isinstance(sheet.get("violations"), list):
                raise ValueError(f"{path.name}: invalid ERC sheet")
    return data
