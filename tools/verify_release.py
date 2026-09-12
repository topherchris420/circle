"""Verify CIRCLE software or the complete pinned-toolchain engineering package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_kicad_checks import resolve_kicad_cli


def run(command: list[str]) -> dict:
    started = time.perf_counter()
    print("$", " ".join(command), flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        code = result.returncode
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        code = 1
    return {"command": command, "exit_code": code, "elapsed_seconds": round(time.perf_counter() - started, 3)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software-only", action="store_true", help="Check software and archived report contracts; does not verify hardware")
    parser.add_argument("--output", type=Path, help="Write verification summary to this path")
    args = parser.parse_args(argv)
    py = sys.executable
    commands = [
        [py, "-m", "unittest", "discover", "-s", "tests"],
        *[[py, f"tools/{name}.py"] for name in (
            "check_design_manifest", "check_record_schema", "check_resonance_contract",
            "check_emergence_contract", "check_pnt_contract", "render_diagrams", "generate_schematics",
        )],
        [py, "tools/generate_schematics.py", "--board", "circle-ppg"],
        [py, "tools/check_erc.py"],
        [py, "tools/check_drc.py"],
    ]
    steps = []
    for command in commands:
        step = run(command)
        steps.append(step)
        if step["exit_code"]:
            break
    software_ok = len(steps) == len(commands) and all(s["exit_code"] == 0 for s in steps)
    disallowed = []
    placeholder_pattern = re.compile(r"\b(TODO|TBD|PLACEHOLDER)\b")
    for path in sorted(list((ROOT / "hardware").rglob("*.json")) + list((ROOT / "docs").rglob("*.md"))):
        if placeholder_pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            disallowed.append(str(path.relative_to(ROOT)))
    software_ok = software_ok and not disallowed
    hardware_checked = False
    hardware_ok = False
    reason = "Full hardware verification was not requested" if args.software_only else None
    if software_ok and not args.software_only:
        if resolve_kicad_cli() is None:
            reason = "Pinned KiCad CLI is unavailable; fresh ERC/DRC checks were not performed"
        else:
            hardware_checked = True
            step = run([py, "tools/run_kicad_checks.py"])
            steps.append(step)
            hardware_ok = step["exit_code"] == 0
    verified = software_ok and hardware_ok
    status = "VERIFIED" if verified else (
        "SOFTWARE_VERIFIED" if software_ok and args.software_only else
        "INCOMPLETE" if software_ok and not hardware_checked else "FAILED"
    )
    artifacts = []
    for pattern in ("hardware/*.json", "contracts/*.json", "hardware/reports/*-erc.json", "hardware/reports/*-drc.json", "hardware/reports/*-allowlist.json"):
        for path in sorted(ROOT.glob(pattern)):
            artifacts.append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    summary = {
        "verified": verified, "software_verified": software_ok,
        "hardware_checked": hardware_checked, "status": status,
        "release_class": "ENGINEERING_REVIEW_ONLY", "steps": steps,
        "artifacts": artifacts, "disallowed_placeholders": disallowed,
        "incomplete_reason": reason,
        "limitations": [
            "Archived report validation does not establish fresh hardware verification.",
            "ERC structure and explicitly allowlisted routing do not authorize fabrication.",
            "No fabrication, powered-electrode, human, EMC, or regulatory validation performed.",
        ],
    }
    output = args.output or ROOT / ("outputs/software-verification-summary.json" if args.software_only else "hardware/reports/verification-summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"CIRCLE Rev B review package: {status}")
    if reason:
        print(reason)
    return 0 if verified or (software_ok and args.software_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
