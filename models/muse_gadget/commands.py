"""CIRCLE's command set for a Muse gadget: everything the Muse may ask CIRCLE to do.

In the SDK, commands flow from the Muse, an AI assistant in a cloud VM, to the
device: the device lists commands in link.register and answers each
link.invoke. The stock Linux gadget offers system.run, file.read, and
file.write. On a CIRCLE host that would let the Muse run
tools/run_protocol.py authorize under any name, rewrite evidence, or edit the
review gates. This command set replaces it and keeps the Muse above the record:

  circle.capabilities       CIRCLE's capability registry: what exists, what is
                            simulation only, and what is not claimed
  circle.protocol.validate  deterministic validation of a proposed experiment
                            protocol; the reply gives the verdict, the problems,
                            and the protocol's SHA-256, and says that nothing was
                            authorized or executed

There is no command to authorize, execute, actuate, read session data, or write
files. A protocol arriving this way is an AI proposal by construction: it must
declare proposed_by.kind AI_MODEL, and only a named human running
tools/run_protocol.py authorize on the CIRCLE host can bind an authorization
to its hash. More capable models get more analytical resolution, not authority.

COMMAND_SPECS follows the SDK's command-spec format (musegadget
executor.COMMAND_SPECS; parameters typed string, integer, or boolean), and
CircleCommandHandler matches LinkSession's run_command(command, params,
timeout_ms) signature and result shape ({"ok": true, "payload": ...} or
{"ok": false, "error": ...}). A gadget built on
musegadget.link_client.LinkSession can therefore advertise and serve exactly
this set. Deploying such a gadget is a security decision for the lab and is
not implemented here (docs/hardware-sources.md).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities.json"
MAX_PROTOCOL_BYTES = 64 * 1024
MAX_RESULT_BYTES = 96 * 1024  # the SDK caps command output at 96 KiB per stream

AUTHORITY = ("This channel can read CIRCLE's capability registry and validate proposed protocols. It cannot authorize, "
             "execute, actuate, read session data, or change files. Authorization is a named human's act on the CIRCLE "
             "host, bound to a protocol's SHA-256.")

COMMAND_SPECS: dict[str, dict[str, Any]] = {
    "circle.capabilities": {
        "description": ("Describe the CIRCLE research instrument: each module's status (implemented, simulation "
                        "validated, designed but not built, speculative) and what it does not claim. Read-only. All "
                        "physiological data in CIRCLE is simulated; no person has been measured."),
        "required": {},
        "optional": {},
    },
    "circle.protocol.validate": {
        "description": ("Validate a proposed CIRCLE experiment protocol (JSON, schema circle-experiment-protocol/1, "
                        "proposed_by.kind AI_MODEL with model_version) against CIRCLE's deterministic rules: simulation "
                        "target only, matched sham arm, quality gates may only tighten, held-out seeds, Holm correction. "
                        "Returns VALID_FOR_SIMULATION or REJECTED with problems and the protocol SHA-256. Never "
                        "authorizes or runs anything; a named human must review and authorize the exact protocol."),
        "required": {
            "protocol_json": {"type": "string", "description": "The protocol document as a JSON string (at most 64 KiB)."},
        },
        "optional": {},
    },
}


def ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "payload": payload}


def error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str) -> float:
    raise ValueError(f"non-finite number {value}")


class CircleCommandHandler:
    """Serves COMMAND_SPECS; callable as LinkSession's run_command. Never raises; never writes files."""

    def __init__(self, registry: Path = REGISTRY, validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.registry = Path(registry)
        self._validator = validator
        self.log: list[dict[str, Any]] = []

    def __call__(self, command: str, params: dict[str, Any] | None, timeout_ms: int | None = None) -> dict[str, Any]:
        try:
            if command == "circle.capabilities":
                result = ok(self._capabilities())
            elif command == "circle.protocol.validate":
                result = self._validate(params if isinstance(params, dict) else {})
            else:
                result = error(f"unsupported command: {command}")
        except Exception as exc:  # a handler that raises leaves the Muse waiting out its timeout
            result = error(f"{type(exc).__name__}: {exc}")
        if len(json.dumps(result)) > MAX_RESULT_BYTES:
            result = error("result exceeds the gadget output budget")
        self.log.append({"command": str(command)[:80], "ok": result["ok"],
                         **({"protocol_sha256": result["payload"]["protocol_sha256"],
                             "status": result["payload"]["status"]}
                            if result["ok"] and command == "circle.protocol.validate" else {})})
        return result

    def _capabilities(self) -> dict[str, Any]:
        doc = json.loads(self.registry.read_text(encoding="utf-8"))
        return {"instrument": "CIRCLE", "release_class": "ENGINEERING_REVIEW_ONLY",
                "human_data": "NONE: every physiological signal in this repository is simulated",
                "authority": AUTHORITY,
                "modules": [{"id": m["id"], "layer": m["layer"], "status": m["status"], "not_claimed": m["not_claimed"]}
                            for m in doc["modules"]]}

    def _validate(self, params: dict[str, Any]) -> dict[str, Any]:
        text = params.get("protocol_json")
        if not isinstance(text, str) or not text.strip():
            return error("protocol_json is required: the protocol as a JSON string")
        size = len(text.encode("utf-8"))
        if size > MAX_PROTOCOL_BYTES:
            return error(f"protocol_json is {size} bytes; the limit is {MAX_PROTOCOL_BYTES}")
        try:
            protocol = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
        except ValueError as exc:
            return error(f"protocol_json is not valid JSON: {exc}")
        if not isinstance(protocol, dict):
            return error("protocol_json must hold a JSON object")
        proposer = protocol.get("proposed_by")
        if isinstance(proposer, dict) and proposer.get("kind") != "AI_MODEL":
            return error("a protocol received from the Muse is an AI proposal: proposed_by.kind must be AI_MODEL")
        validator = self._validator
        if validator is None:
            from models.protocols import validate as validator  # deferred: imports the whole simulation stack
        verdict = validator(protocol)
        return ok({"status": verdict["status"], "problems": verdict["problems"],
                   "protocol_sha256": verdict["protocol_sha256"],
                   "received_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "authorized": False, "executed": False,
                   "next_step": ("Nothing has been authorized or executed. A named human must review this exact "
                                 "protocol and run tools/run_protocol.py authorize on the CIRCLE host; any change "
                                 "to it voids the authorization.")})
