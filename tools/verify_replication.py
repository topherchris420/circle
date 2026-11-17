"""Verify a CIRCLE experiment package locally, without trusting its producer.

Given a directory exported by ``tools/run_physiology_twin.py`` (or a workbench
``bundle.zip``, extracted), this script checks the evidence's own integrity and
then independently reconstructs the session from its raw samples:

  1. Every artifact's SHA-256 is recomputed against the manifest.
  2. The analysis, ledger, and every controller decision are rebuilt from raw/.
  3. The verdict is named explicitly:

       REPLAY_MATCH          reconstruction agrees with the export
       REPLAY_DIVERGENCE     decisions or analysis disagree with the export
       INTEGRITY_FAILURE     files do not match their recorded hashes
       INSUFFICIENT_EVIDENCE files are missing or unreadable

A verdict of REPLAY_MATCH establishes that the package is internally
consistent and reproducible from its inputs. It does NOT establish that the
inputs describe the physical world, that the software was correct for the
question asked, or any clinical claim. Cryptographic integrity is not proof of
scientific accuracy; it is only the floor on which replication stands.

Usage in a checkout: python tools/verify_replication.py <run-directory> [--json out.json]
Usage in an extracted bundle: install requirements-verifier.txt then run
python verify_replication.py . from the extracted directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

# Support both repository layout (tools/) and extracted bundles (root).
HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "models" / "physiology" / "audit.py").is_file() else HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VERIFIER_VERSION = "1.0.0"


def check_integrity(directory: Path) -> tuple[str, list[str]]:
    """Recompute every recorded artifact hash; refuse to proceed on mismatch."""
    problems = []
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "INSUFFICIENT_EVIDENCE", [f"manifest.json unreadable: {exc}"]
    artifacts = manifest.get("artifacts", {})
    if not artifacts:
        return "INSUFFICIENT_EVIDENCE", ["the manifest lists no artifacts"]
    for name, meta in sorted(artifacts.items()):
        path = directory / name
        if not path.is_file():
            problems.append(f"missing artifact {name}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta.get("sha256"):
            problems.append(f"{name} does not match its recorded SHA-256")
    if problems:
        return "INTEGRITY_FAILURE", problems
    return "OK", []


def verify(directory: Path) -> dict:
    result = {"schema": "circle-replication-verdict/1", "verifier_version": VERIFIER_VERSION,
              "directory": str(directory)}
    status, problems = check_integrity(directory)
    if status != "OK":
        result.update({"verdict": status, "problems": problems})
        return result
    try:
        from models.physiology.audit import audit_run
        audit = audit_run(directory)
    except (OSError, ValueError, KeyError) as exc:
        result.update({"verdict": "INSUFFICIENT_EVIDENCE", "problems": [f"reconstruction failed: {exc}"]})
        return result
    result.update({
        "verdict": "REPLAY_MATCH" if audit.get("valid") else "REPLAY_DIVERGENCE",
        "replay_status": audit.get("replay_status"),
        "checks": audit.get("checks"),
        "note": "Reconstruction from the package's own raw inputs agrees (or disagrees) with its exported "
                "records. This says nothing about physical truth or any effect in people.",
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="exported run directory (with manifest.json)")
    parser.add_argument("--json", type=Path, default=None, help="also write the verdict as JSON")
    args = parser.parse_args(argv)
    result = verify(args.directory)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"VERDICT: {result['verdict']}")
    for problem in result.get("problems", []):
        print(f"  problem: {problem}")
    if result.get("replay_status"):
        print(f"  replay status: {result['replay_status']}")
    print("A matching replay shows the package reproduces from its inputs — not that it measured the world.")
    return 0 if result["verdict"] == "REPLAY_MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
