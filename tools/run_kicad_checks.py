"""Run the pinned KiCad against current sources and gate only fresh reports."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import check_drc, check_erc
from tools.kicad_reports import require_version


def resolve_kicad_cli() -> Path | None:
    configured = os.environ.get("KICAD_CLI")
    if configured:
        return Path(configured)  # An invalid override must fail, not silently fall back.
    executable = shutil.which("kicad-cli")
    if executable:
        return Path(executable)
    windows = Path.home() / "AppData/Local/Programs/KiCad/10.0/bin/kicad-cli.exe"
    return windows if windows.is_file() else None


def run_checks(executable: Path, output_dir: Path) -> None:
    version = subprocess.run([str(executable), "version"], check=True, text=True, capture_output=True)
    require_version(version.stdout.strip())
    # Empty temporary output prevents a failed command from reusing checked-in
    # reports. Publish evidence only after all commands and allowlists succeed.
    with tempfile.TemporaryDirectory(prefix="circle-kicad-") as temporary:
        directory = Path(temporary)
        for board, root in (("circle-main", "00_root.sch"), ("circle-ppg", "00_ppg_root.sch")):
            for kind, domain, source in (
                ("erc", "sch", ROOT / f"hardware/{board}/legacy/{root}"),
                ("drc", "pcb", ROOT / f"hardware/{board}/{board}.kicad_pcb"),
            ):
                report = directory / f"{board}-{kind}.json"
                command = [str(executable), domain, kind, "--format", "json", "--severity-all", "--output", str(report), str(source)]
                subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
                if not report.is_file():
                    raise ValueError(f"KiCad did not produce {report.name}")
        erc_status = check_erc.main(directory)
        drc_status = check_drc.main(directory)
        if erc_status or drc_status:
            raise ValueError("Fresh KiCad reports did not pass the review gates")
        output_dir.mkdir(parents=True, exist_ok=True)
        for report in directory.glob("*.json"):
            shutil.copy2(report, output_dir / report.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "hardware/reports")
    args = parser.parse_args(argv)
    executable = resolve_kicad_cli()
    if executable is None:
        print("Hardware verification incomplete: pinned KiCad CLI was not found", file=sys.stderr)
        return 1
    try:
        run_checks(executable, args.output_dir)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Hardware verification failed: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stdout or "", file=sys.stderr)
            print(exc.stderr or "", file=sys.stderr)
        return 1
    print("Fresh KiCad ERC/DRC review gates: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
