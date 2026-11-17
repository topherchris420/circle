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

Standalone use: a workbench ``bundle.zip`` ships this script next to ``circle-replay/``, the exact
CIRCLE reconstruction code (and its two data files) that rebuilds the session, laid out as in the
repository. It needs Python 3.11+ with numpy and jsonschema:

    python -m pip install -r circle-replay/REQUIREMENTS.txt
    python verify_replication.py <directory-containing-manifest.json>

Shipped code is the producer's code, so it is checked, not trusted: the analysis sources it runs
must hash to the ``pipeline_source`` the export recorded, or the verdict is REPLAY_DIVERGENCE, and
``circle-replay/SOURCE.json`` names the commit it came from. A skeptic can instead rebuild with
their own checkout of the public repository at that commit: ``--circle-root <checkout>``.

Exit status: 0 REPLAY_MATCH; 1 REPLAY_DIVERGENCE or INTEGRITY_FAILURE; 2 INSUFFICIENT_EVIDENCE
(including "this machine cannot run the reconstruction", which is named with its remedy).

Usage: python tools/verify_replication.py <run-directory> [--json out.json] [--circle-root DIR]
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import sys

VERIFIER_VERSION = "1.1.0"
# The reconstruction code shipped inside a bundle, laid out as in the repository.
KIT_DIR = "circle-replay"
KIT_ENTRY = "models/physiology/audit.py"
# Data files the reconstruction reads, relative to the repository root.
KIT_DATA = ("contracts/session-record.schema.json", "hardware/review-gates.json")
KIT_PACKAGES = ("numpy", "jsonschema")
INSTALL_HINT = f"python -m pip install -r {KIT_DIR}/REQUIREMENTS.txt"
SOURCES = {
    "bundle": f"the reconstruction code shipped with this bundle ({KIT_DIR}/)",
    "checkout": "this CIRCLE checkout",
    "circle-root": "the checkout named by --circle-root",
}


def find_reconstruction_code(circle_root: Path | None = None) -> tuple[Path | None, str | None]:
    """Where the code that rebuilds a session lives: --circle-root, else the bundle's kit, else this checkout."""
    if circle_root is not None:
        return Path(circle_root).resolve(), "circle-root"
    here = Path(__file__).resolve().parent
    if (here / KIT_DIR / KIT_ENTRY).is_file():
        return here / KIT_DIR, "bundle"
    if (here.parent / KIT_ENTRY).is_file():
        return here.parent, "checkout"
    return None, None


@lru_cache(maxsize=1)
def replay_kit() -> tuple[tuple[str, bytes], ...]:
    """Every file a bundle must ship for verify_replication.py to rebuild a session outside the repository.

    The Python modules are found by importing the reconstruction entry point in a clean interpreter
    and keeping each module loaded from this repository, so the kit follows the code as it changes.
    Returns (arcname, content) pairs under KIT_DIR/.
    """
    root = Path(__file__).resolve().parents[1]
    probe = ("import json, sys; sys.path.insert(0, sys.argv[1]); import models.physiology.audit; "
             "print(json.dumps([m.__file__ for m in list(sys.modules.values()) if getattr(m, '__file__', None)]))")
    loaded = subprocess.run([sys.executable, "-I", "-c", probe, str(root)], capture_output=True, text=True,
                            check=True, timeout=120).stdout
    modules = sorted({path.relative_to(root).as_posix() for path in map(lambda f: Path(f).resolve(), json.loads(loaded))
                      if path.suffix == ".py" and path.is_relative_to(root)})
    files = {name: (root / name).read_bytes() for name in (*modules, *KIT_DATA)}
    requirements = [line for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
                    if line.split(">")[0].split("=")[0].split("<")[0].strip() in KIT_PACKAGES]
    files["REQUIREMENTS.txt"] = ("# What verify_replication.py needs to rebuild this session: " + INSTALL_HINT
                                 + "\n" + "\n".join(requirements) + "\n").encode("utf-8")
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                                check=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = "UNAVAILABLE"
    source = {"schema": "circle-replay-kit/1", "git_commit": commit,
              "repository": "https://github.com/topherchris420/circle",
              "note": "The CIRCLE code that rebuilds this session. It is the producer's code, checked rather than "
                      "trusted: its analysis sources must hash to the export's pipeline_source. To use your own "
                      "checkout of this commit instead, pass --circle-root.",
              "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["SOURCE.json"] = (json.dumps(source, indent=1, sort_keys=True) + "\n").encode("utf-8")
    return tuple((f"{KIT_DIR}/{name}", data) for name, data in sorted(files.items()))


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


def verify(directory: Path, circle_root: Path | None = None) -> dict:
    result = {"schema": "circle-replication-verdict/1", "verifier_version": VERIFIER_VERSION,
              "directory": str(directory)}
    status, problems = check_integrity(directory)
    if status != "OK":
        result.update({"verdict": status, "problems": problems})
        return result
    intact = "the evidence itself is intact (every recorded SHA-256 matches)"
    code_root, source = find_reconstruction_code(circle_root)
    if code_root is None or not (code_root / KIT_ENTRY).is_file():
        where = f"{circle_root} has no {KIT_ENTRY}" if circle_root else f"no {KIT_DIR}/ folder beside this script"
        result.update({"verdict": "INSUFFICIENT_EVIDENCE", "problems": [
            f"{intact}, but the code that rebuilds it is missing: {where}. Use the complete bundle.zip, or "
            "pass --circle-root <a checkout of https://github.com/topherchris420/circle>."]})
        return result
    if str(code_root) not in sys.path:
        sys.path.insert(0, str(code_root))
    try:
        from models.physiology.audit import audit_run
        from models.physiology.evidence import source_digest
    except ImportError as exc:
        missing = getattr(exc, "name", None) or str(exc)
        result.update({"verdict": "INSUFFICIENT_EVIDENCE", "problems": [
            f"{intact}, but this Python cannot run the reconstruction: {missing} is not installed. "
            f"Install what it needs with: {INSTALL_HINT}"]})
        return result
    result["reconstruction_code"] = {"source": source, "pipeline_source": source_digest()}
    kit_source = code_root / "SOURCE.json"
    if source == "bundle" and kit_source.is_file():
        try:
            result["reconstruction_code"]["git_commit"] = json.loads(kit_source.read_text(encoding="utf-8"))["git_commit"]
        except (OSError, ValueError, KeyError):
            pass
    try:
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
    parser.add_argument("--circle-root", type=Path, default=None,
                        help="rebuild with this CIRCLE checkout instead of the code shipped with the bundle")
    args = parser.parse_args(argv)
    result = verify(args.directory, args.circle_root)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"VERDICT: {result['verdict']}")
    for problem in result.get("problems", []):
        print(f"  problem: {problem}")
    if result.get("replay_status"):
        print(f"  replay status: {result['replay_status']}")
    code = result.get("reconstruction_code")
    if code:
        commit = f", commit {code['git_commit']}" if code.get("git_commit") else ""
        print(f"  rebuilt with: {SOURCES[code['source']]}{commit}; analysis code {code['pipeline_source']}")
        if code["source"] == "bundle":
            print("  for a check independent of whoever made this bundle, rebuild with your own checkout of that "
                  "commit: --circle-root <checkout>")
    print("A matching replay shows the package reproduces from its inputs — not that it measured the world.")
    return {"REPLAY_MATCH": 0, "INSUFFICIENT_EVIDENCE": 2}.get(result["verdict"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
