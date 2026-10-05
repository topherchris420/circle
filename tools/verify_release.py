"""Verify CIRCLE software or the complete pinned-toolchain engineering package.

Verification always names its scope. The summary reports each scope
separately; no scope implies another:

  SOFTWARE_CONTRACTS      unit tests, schemas, manifest, research contracts, review-gate file
  SIMULATION_BENCHMARK    twin session scored against hidden truth, independent audit, scenario suite
  GENERATED_ARTIFACTS     diagrams and schematics regenerate
  SCHEMATIC_ERC           FRESH_PASS only from a new pinned-KiCad run; ARCHIVED_REPORT_PASS otherwise
  PCB_DRC                 as above, and always qualified by the open routing allowlist
  BENCH_VALIDATION, ELECTRICAL_SAFETY_REVIEW, ISOLATION_WITHSTAND, EMC,
  MEASUREMENT_CHAIN, FABRICATION, HUMAN_USE, CLINICAL
                          read from hardware/review-gates.json; never set by software

Missing KiCad never produces success in full mode. Stale checked-in reports
never satisfy a failed fresh run.
"""

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

GATE_SCOPES = {
    "BENCH_VALIDATION": ("BENCH_BRINGUP", "PERFORMED", "NOT_PERFORMED"),
    "ELECTRICAL_SAFETY_REVIEW": ("INDEPENDENT_ELECTRICAL_SAFETY_REVIEW", "REVIEWED", "NOT_REVIEWED"),
    "ISOLATION_WITHSTAND": ("ISOLATION_CREEPAGE_CLEARANCE", "TESTED", "NOT_TESTED"),
    "EMC": ("EMC_TESTING", "TESTED", "NOT_TESTED"),
    "MEASUREMENT_CHAIN": ("ELECTRONIC_PHANTOM_VALIDATION", "PHANTOM_VALIDATED", "NOT_VALIDATED"),
}


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
    portable = ["python" if part == sys.executable else part for part in command]
    return {"command": portable, "exit_code": code, "elapsed_seconds": round(time.perf_counter() - started, 3)}


def software_commands(py: str) -> list[tuple[str, list[str]]]:
    return [
        ("SOFTWARE_CONTRACTS", [py, "-m", "unittest", "discover", "-s", "tests"]),
        *[("SOFTWARE_CONTRACTS", [py, f"tools/{name}.py"]) for name in (
            "check_design_manifest", "check_record_schema", "check_review_gates", "check_module_registry",
            "check_resonance_contract", "check_emergence_contract", "check_pnt_contract")],
        ("GENERATED_ARTIFACTS", [py, "tools/render_diagrams.py"]),
        ("GENERATED_ARTIFACTS", [py, "tools/generate_schematics.py"]),
        ("GENERATED_ARTIFACTS", [py, "tools/generate_schematics.py", "--board", "circle-ppg"]),
        ("SCHEMATIC_ERC", [py, "tools/check_erc.py"]),
        ("PCB_DRC", [py, "tools/check_drc.py"]),
        ("SIMULATION_BENCHMARK", [py, "tools/run_physiology_twin.py", "--output", "outputs/physiology", "--audit"]),
        ("SIMULATION_BENCHMARK", [py, "tools/run_physiology_twin.py", "--scenarios", "--output", "outputs/scenarios"]),
        ("SIMULATION_BENCHMARK", [py, "tools/run_acquisition_demo.py", "--output", "outputs/acquisition-demo",
                                  "--no-report"]),
    ]


def open_routing_items(root: Path) -> int:
    path = root / "hardware/reports/drc-allowlist.json"
    if not path.is_file():
        return 0
    return sum(1 for a in json.loads(path.read_text(encoding="utf-8")).get("allowlist", []) if a.get("type") == "unconnected_items")


def gate_scopes(root: Path) -> dict[str, str]:
    path = root / "hardware/review-gates.json"
    if not path.is_file():
        return {name: "UNKNOWN_NO_GATE_FILE" for name in (*GATE_SCOPES, "FABRICATION", "HUMAN_USE")} | {
            "CLINICAL": "OUT_OF_SCOPE_NOT_VALIDATED"}
    gates = {g["id"]: g for g in json.loads(path.read_text(encoding="utf-8"))["gates"]}
    scopes = {}
    for scope, (gate, done, not_done) in GATE_SCOPES.items():
        scopes[scope] = done if gates.get(gate, {}).get("status") == "CLOSED" else not_done
    for scope, blocked in (("FABRICATION", "FABRICATION"), ("HUMAN_USE", "HUMAN_CONNECTION")):
        open_gates = [g for g in gates.values() if blocked in g["blocks"] and g["status"] != "CLOSED"]
        scopes[scope] = "NOT_AUTHORIZED" if open_gates else "GATES_CLOSED_REQUIRES_HUMAN_SIGNOFF"
    scopes["CLINICAL"] = "OUT_OF_SCOPE_NOT_VALIDATED"
    return scopes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--software-only", action="store_true", help="Check software and archived report contracts; does not verify hardware")
    parser.add_argument("--output", type=Path, help="Write verification summary to this path")
    args = parser.parse_args(argv)
    py = sys.executable
    commands = software_commands(py)
    steps = []
    for scope, command in commands:
        step = run(command)
        step["scope"] = scope
        steps.append(step)
        if step["exit_code"]:
            break
    ran = {s["scope"] for s in steps}
    failed_scopes = {s["scope"] for s in steps if s["exit_code"]}
    software_ok = len(steps) == len(commands) and not failed_scopes
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
            step["scope"] = "FRESH_ERC_DRC"
            steps.append(step)
            hardware_ok = step["exit_code"] == 0
    verified = software_ok and hardware_ok
    status = "REPOSITORY_VERIFIED" if verified else (
        "SOFTWARE_VERIFIED" if software_ok and args.software_only else
        "INCOMPLETE" if software_ok and not hardware_checked else "FAILED"
    )

    def scope_status(scope: str) -> str:
        if scope in failed_scopes:
            return "FAIL"
        return "PASS" if scope in ran else "NOT_RUN"

    routing = open_routing_items(ROOT)
    erc, drc = scope_status("SCHEMATIC_ERC"), scope_status("PCB_DRC")
    if hardware_checked:
        erc = drc = "FRESH_PASS" if hardware_ok else "FRESH_FAIL"
    elif erc == "PASS":
        erc = "ARCHIVED_REPORT_PASS_NOT_RERUN"
    if drc == "PASS":
        drc = "ARCHIVED_REPORT_PASS_NOT_RERUN"
    if drc.endswith("PASS") or drc.endswith("NOT_RERUN"):
        drc += f"_WITH_OPEN_ALLOWLIST_{routing}_UNROUTED_NETS" if routing else ""
    scopes = {
        "SOFTWARE_CONTRACTS": scope_status("SOFTWARE_CONTRACTS"),
        "SIMULATION_BENCHMARK": scope_status("SIMULATION_BENCHMARK"),
        "GENERATED_ARTIFACTS": scope_status("GENERATED_ARTIFACTS"),
        "SCHEMATIC_ERC": erc,
        "PCB_DRC": drc,
        **gate_scopes(ROOT),
    }
    artifacts = []
    for pattern in ("hardware/*.json", "contracts/*.json", "hardware/reports/*-erc.json", "hardware/reports/*-drc.json", "hardware/reports/*-allowlist.json"):
        for path in sorted(ROOT.glob(pattern)):
            artifacts.append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    summary = {
        "status": status,
        "verified": verified,
        "verified_scope": "REPOSITORY (software, simulation, generated artifacts, fresh ERC/DRC)" if verified else None,
        "software_verified": software_ok,
        "hardware_checked": hardware_checked,
        "scopes": scopes,
        "release_class": "ENGINEERING_REVIEW_ONLY",
        "steps": steps,
        "artifacts": artifacts, "disallowed_placeholders": disallowed,
        "incomplete_reason": reason,
        "limitations": [
            "Each scope stands alone. No scope implies another.",
            "Simulation results are scored against a twin's assumed physiology; they validate software, not biology or hardware.",
            "Archived report validation does not establish fresh hardware verification.",
            "ERC structure and an open routing allowlist do not authorize fabrication.",
            "Automated KiCad checks are not an independent electrical-safety review.",
            "No fabrication, bench, powered-electrode, human, EMC, or regulatory validation has been performed.",
        ],
    }
    output = args.output or ROOT / ("outputs/software-verification-summary.json" if args.software_only else "outputs/verification-summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"CIRCLE Rev B review package: {status}")
    for scope, value in scopes.items():
        print(f"  {scope:<26} {value}")
    if reason:
        print(reason)
    return 0 if verified or (software_ok and args.software_only) else 1


if __name__ == "__main__":
    raise SystemExit(main())
