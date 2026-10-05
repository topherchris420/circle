"""The Muse gadget offered to the closed loop as a source of device records, which it cannot be.

MuseGadgetSource answers "can CIRCLE run its closed loop on the Muse Gadget
SDK?" with the same input contract every source faces, and keeps the answer.
capabilities() is the live discovery; view() holds link observations and never
a physiological stream; so run_closed_loop() refuses with InsufficientEvidence
before a single evaluation, and models/acquisition/records.py writes that
refusal as an ordinary session. Nothing is imputed for the missing streams.

The Muse gadget delivers no data, so data staleness cannot arise. What can
change is the link: probes record the service as responding, absent, refusing,
or silent, each as a LINK_STATE event on the host's monotonic clock.
"""

from __future__ import annotations

import math

from models.physiology.loop import Capabilities
from models.physiology.streams import DeviceEvent, RawSession

from .capabilities import discover
from .client import Exchange, LocalSocketClient

LINK_STREAM = "muse_gadget_link"


class MuseGadgetSource:
    """A HardwareSource with no streams: link observations only."""

    def __init__(self, client: LocalSocketClient | None = None) -> None:
        self.client = client or LocalSocketClient()
        self._t0 = self.client.clock()
        self.link_events: list[DeviceEvent] = []
        self._last_probe: Exchange | None = None

    def observe(self) -> Exchange:
        """Probe the gadget service once and record the link state it shows."""
        exchange = self.client.probe()
        self._last_probe = exchange
        self.link_events.append(DeviceEvent(LINK_STREAM, len(self.link_events), f"LINK_STATE:{exchange.outcome}",
                                            max(0, exchange.finished_us - self._t0),
                                            (("round_trip_us", float(exchange.round_trip_us)),)))
        return exchange

    def capabilities(self) -> Capabilities:
        return discover(self.client, self._last_probe or self.observe())

    def start(self) -> int | None:
        self.observe()
        return None  # the gadget logs no protocol markers: there is nothing to anchor a schedule on

    def advance(self, device_time_us: int) -> bool:
        return False

    def view(self, device_time_us: int) -> RawSession:
        return RawSession({}, {}, [], [e for e in self.link_events if e.device_time_us <= device_time_us])

    def complete_through_us(self) -> float:
        return math.inf

    def finish(self) -> RawSession:
        return RawSession({}, {}, [], list(self.link_events))
