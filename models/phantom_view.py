"""Phantom evidence view: a known-input electrical check, first-class in the workbench.

An electronic phantom drives an instrument with a *known* signal, so its output
can be judged against truth without a person. This module reads a Cyton phantom
session directory produced by ``tools/openbci_cyton.py`` (``simulate`` for the
simulated board, ``phantom`` for a physical board on a serial port) and turns it
into one reviewable document for the Resonance Workbench.

Provenance is the headline: the document opens with ``SIMULATED_BOARD`` or
``HARDWARE`` taken from the session manifest, so a simulated phantom can never
be mistaken for physical evidence. When a physical board is connected through
the same bridge, the identical view carries the milestone this repository still
lacks: measured electrical input through real acquisition hardware.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "circle-phantom-evidence/1"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_sha(directory: Path, name: str) -> str:
    return "sha256:" + hashlib.sha256((directory / name).read_bytes()).hexdigest()


def build_phantom_document(directory: Path) -> dict[str, Any]:
    """Assemble the phantom evidence document from a Cyton phantom session."""
    manifest = _read(directory / "manifest.json")
    analysis = _read(directory / "analysis.json")
    provenance = manifest.get("provenance", "UNKNOWN")
    if provenance not in ("SIMULATED", "HARDWARE"):
        raise ValueError("Unrecognized phantom provenance; refuse to present it as evidence.")
    plan_mode = manifest.get("plan", {}).get("mode", "UNKNOWN")
    if plan_mode != "PHANTOM":
        raise ValueError("This session is not a phantom run.")

    phantom = analysis.get("phantom") or {}
    checks = [
        {"id": check["id"], "status": check["status"], "criterion": check.get("criterion"),
         "measured": {k: v for k, v in check.get("measured", {}).items() if isinstance(v, (int, float, str))}}
        for check in phantom.get("checks", [])
    ]
    clock = [
        {"segment": entry.get("segment"), "rate_hz": round(1e6 / entry["slope_us"], 4) if entry.get("slope_us") else None,
         "ppm": entry.get("ppm"), "duration_s": entry.get("duration_s")}
        for entry in analysis.get("clock", [])
    ]
    channels = [
        {"channel": entry.get("channel"), "status": entry.get("status"), "detail": entry.get("detail")}
        for entry in analysis.get("channels", [])
    ]
    ingestion = manifest.get("ingestion", {})
    return {
        "schema": SCHEMA,
        "provenance": provenance,
        "provenance_note": ("Every sample came from the simulated board; this is a rehearsal of the evidence path, "
                            "not physical measurement." if provenance == "SIMULATED" else
                            "Recorded from a physical board through the serial bridge; see passport.txt for the "
                            "board identity and configuration."),
        "bridge_version": manifest.get("bridge_version"),
        "protocol_reference": manifest.get("protocol_reference"),
        "session_id": manifest.get("session_id"),
        "phantom": {
            "verdict": phantom.get("verdict"),
            "checks": checks,
            "failed": [c["id"] for c in checks if c["status"] == "FAIL"],
        },
        "clock": clock,
        "channels": channels,
        "ingestion": {k: v for k, v in ingestion.items() if isinstance(v, (int, float, str, bool))},
        "artifacts": {"analysis_sha256": _artifact_sha(directory, "analysis.json"),
                      "session_ndjson_sha256": _artifact_sha(directory, "session.ndjson"),
                      "manifest_sha256": _artifact_sha(directory, "manifest.json")},
        "interpretation": "A phantom verdict validates the instrument's own signal chain against a known input "
                         "(the ADS1299 test signal through this bridge). It says nothing about CIRCLE Rev B "
                         "hardware, and no person was measured.",
    }


class PhantomView:
    """Optional workbench attachment for one phantom session directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory).resolve()
        self._document: dict[str, Any] | None = None

    def document(self) -> dict[str, Any]:
        if self._document is None:
            self._document = build_phantom_document(self.directory)
        return self._document

    def refresh(self) -> dict[str, Any]:
        """Re-read after a physical run replaces the directory."""
        self._document = None
        return self.document()
