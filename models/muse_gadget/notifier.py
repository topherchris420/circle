"""Operator notifications through a Muse gadget: CIRCLE tells a researcher how a session ended.

Posting text into the Muse chat is the only thing the Muse Gadget SDK lets a
local program do. CIRCLE uses it for one purpose, reporting session outcomes
to a researcher after the fact, and keeps it from becoming anything more:

  * Its target is OPERATOR_CHANNEL, which run_closed_loop refuses for cues, and
    execute() refuses again: delivery is untimed, unobserved, and the message is
    a chat turn to an AI assistant, not a stimulus.
  * Messages come from fixed templates filled only with whitelisted passport
    fields: session identity, mode, counts, replay status. No physiological
    value, participant identifier, or model-written text can be sent.
  * Nothing it learns feeds back into a decision. Each attempt becomes an EVENT
    record (OPERATOR_NOTIFICATION, NOT_AN_INTERVENTION, OUTSIDE_CLOSED_LOOP)
    kept beside the session's evidence, never inside it.

Messages leave the host for Meta's Muse service, so the whitelist is also the
privacy boundary.
"""

from __future__ import annotations

import re
from typing import Any

from models.physiology.evidence import EVENT_KIND_FLAG, SCHEMA_VERSION
from models.physiology.loop import ActuationRefused
from models.session_records import seal_record

from .client import Exchange, LocalSocketClient

DEFAULT_SIDE_CHAT = "circle-sessions"
FIELDS = ("SESSION", "MODE", "ARM", "CONTROLLER", "EVALUATIONS", "INTERVENTIONS", "HUMAN_DATA", "REPLAY", "SOURCE",
          "TERMINATED")
TEMPLATES = {
    "SESSION_COMPLETE": ("CIRCLE session {SESSION} ended ({MODE}, arm {ARM}, controller {CONTROLLER}). Evaluations: "
                         "{EVALUATIONS}. Interventions: {INTERVENTIONS}. Human data: {HUMAN_DATA}. Replay: {REPLAY}. "
                         "Engineering review only. This is a status report and asks nothing of anyone."),
    "SESSION_REFUSED": ("CIRCLE did not start session {SESSION}: source {SOURCE} cannot supply what the closed loop "
                        "reads ({TERMINATED}). Nothing was measured, decided, or actuated."),
}
_PASSPORT_KEYS = {"HUMAN DATA": "HUMAN_DATA", "REPLAY AT EXPORT": "REPLAY"}
_PLACEHOLDER = re.compile(r"{([A-Z_]+)}")
MAX_VALUE_CHARS = 160


def notification_values(passport: dict[str, str], **extra: str) -> dict[str, str]:
    """Whitelisted template values from a session passport (other fields are dropped, not sent)."""
    values = {_PASSPORT_KEYS.get(k, k): v for k, v in passport.items()}
    values.update(extra)
    return {k: v for k, v in values.items() if k in FIELDS}


class OperatorNotifier:
    """Sends templated session outcomes to the Muse chat and records every attempt."""

    target = "OPERATOR_CHANNEL"

    def __init__(self, client: LocalSocketClient | None = None, side_chat: str | None = DEFAULT_SIDE_CHAT,
                 provenance: str = "RAW_MEASURED") -> None:
        if provenance not in ("RAW_MEASURED", "SIMULATED"):
            raise ValueError("provenance must be RAW_MEASURED (a real gadget) or SIMULATED (the simulator)")
        self.client = client or LocalSocketClient()
        self.side_chat = side_chat
        self.provenance = provenance
        self._t0 = self.client.clock()
        self.records: list[dict[str, Any]] = []

    @staticmethod
    def compose(template: str, values: dict[str, str]) -> str:
        """The exact text that would be sent. Refuses unknown templates, missing fields, or unlisted fields."""
        if template not in TEMPLATES:
            raise ValueError(f"unknown template {template!r}; choose from {sorted(TEMPLATES)}")
        needed = _PLACEHOLDER.findall(TEMPLATES[template])
        unlisted = sorted(set(values) - set(FIELDS))
        if unlisted:
            raise ValueError(f"fields {unlisted} are not on the notification whitelist")
        missing = [f for f in needed if f not in values]
        if missing:
            raise ValueError(f"template {template} needs {missing}")
        clean = {k: _single_line(str(v)) for k, v in values.items()}
        return _PLACEHOLDER.sub(lambda m: clean[m.group(1)], TEMPLATES[template])

    def notify(self, template: str, values: dict[str, str]) -> Exchange:
        message = self.compose(template, values)
        exchange = self.client.send(message, self.side_chat)
        t = max(0, exchange.started_us - self._t0)
        self.records.append(seal_record({
            "schema_version": SCHEMA_VERSION, "record_type": "EVENT", "provenance": self.provenance,
            "device_time_start_us": t, "device_time_end_us": max(t, exchange.finished_us - self._t0),
            "status_flags": [EVENT_KIND_FLAG + "OPERATOR_NOTIFICATION", f"TEMPLATE:{template}",
                             f"DELIVERY:{exchange.outcome}", "NOT_AN_INTERVENTION", "OUTSIDE_CLOSED_LOOP",
                             "CHANNEL:MUSE_GADGET_LOCAL_SOCKET", "TIMEBASE:HOST_MONOTONIC"],
            "stream_id": "operator_notifications", "sequence": len(self.records),
            "payload": {"message_bytes": len(message.encode("utf-8")), "round_trip_us": exchange.round_trip_us},
            "cause": exchange.detail, "crc32c": "00000000"}))
        return exchange

    def execute(self, command_device_us: int, program: int, cue_index: int) -> None:
        raise ActuationRefused("an operator channel cannot carry closed-loop cues")


def _single_line(value: str) -> str:
    text = " ".join("".join(ch if ch.isprintable() else " " for ch in value).split())
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS - 1] + "…"
