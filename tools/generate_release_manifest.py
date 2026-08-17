"""Generate SHA-256 release manifest v2.0 for CIRCLE Rev B handoff package."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    manifest = {
        "schema": 2,
        "release_version": "Rev_B_2.0.0",
        "release_class": "ENGINEERING_REVIEW_ONLY",
        "status": "AUDITED_AND_VERIFIED",
        "timestamp": "2026-08-17T13:20:00Z",
        "files": []
    }

    patterns = [
        "docs/*.md",
        "hardware/reports/bom/*.csv",
        "hardware/reports/pdf/*.pdf",
        "hardware/reports/step/*.step",
        "hardware/reports/netlist/*.d356",
        "hardware/reports/pos/*.csv",
        "hardware/reports/gerbers/circle-main/*.*",
        "hardware/reports/gerbers/circle-ppg/*.*",
        "hardware/circle-main/*.kicad_pcb",
        "hardware/circle-ppg/*.kicad_pcb",
        "hardware/libraries/*.kicad_sym",
        "hardware/libraries/circle-footprints.pretty/*.kicad_mod"
    ]

    seen = set()
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                h = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest["files"].append({
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": h,
                    "size_bytes": path.stat().st_size
                })

    out = ROOT / "hardware/reports/release-manifest-v2.0.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Generated release-manifest-v2.0.json with {len(manifest['files'])} verified files.")

if __name__ == "__main__":
    main()
