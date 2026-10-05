"""Live sources: a device's deliveries, through the ingestion boundary, into the closed loop.

A DeliverySource is a device as the host sees it: as acquisition advances it
hands over the pieces that arrived on the link (sample chunks, device events,
declarations of loss), each with its receive time on the device clock. A real
driver and the deterministic SimulatedLink (models/acquisition/simulator.py)
both fit.

IngestingSource turns a DeliverySource into a HardwareSource the closed loop
can run (models/physiology/loop.py). The controller sees only the Ingestor's
view, so everything it decides on has passed the ingestion checks. Because the
controller then runs on the host, availability is stamped with host receipt:
a decision at T uses what the host held at T, and replaying the recorded bundle
reproduces it. An event whose device time precedes a decision but which
arrived after it is kept and flagged LATE_EVENT, since that decision could not
have seen it.

pump() is the asynchronous form for drivers that produce pieces on their own
schedule: a bounded queue between the link and the ingestor. When the queue is
full the newest piece is dropped, and a dropped chunk is declared lost on the
spot with its exact sequence range. Memory stays bounded; loss is never silent.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from typing import AsyncIterator, Protocol, Union

import numpy as np

from models.physiology.loop import Capabilities
from models.physiology.streams import DeviceEvent, Gap, RawSession

from .ingest import LINK_STREAM, Ingestor, LinkMonitor, StreamChunk

Piece = Union[StreamChunk, Gap, DeviceEvent]
Received = Union[int, np.ndarray]


class DeliverySource(Protocol):
    """A device as the host sees it."""

    def capabilities(self) -> Capabilities: ...

    def start(self) -> int | None: ...

    def advance(self, device_time_us: int) -> bool: ...

    def deliveries(self) -> list[tuple[Received, Piece]]:
        """Pieces received since the last call, each with its receive time (device clock; per sample for chunks)."""

    def complete_through_us(self) -> float: ...

    def finish(self) -> None: ...


class IngestingSource:
    """A HardwareSource whose records reach the controller through the ingestion boundary."""

    def __init__(self, device: DeliverySource, capacity: int = 4_000_000, monitor: LinkMonitor | None = None) -> None:
        self.device = device
        caps = device.capabilities()
        self.ingestor = Ingestor({s.stream_id: dict(s.descriptor) for s in caps.signals},
                                 {s.stream_id: s.columns for s in caps.signals}, capacity,
                                 stamp_host_availability=True)
        self.monitor = monitor or LinkMonitor()
        self.outcomes: Counter[str] = Counter()
        self._viewed: list[int] = []

    def capabilities(self) -> Capabilities:
        state = self.monitor.state
        return replace(self.device.capabilities(), connection_state=f"LINK_{state}",
                       connected=None if state == "AWAITING_FIRST_DELIVERY" else state == "LIVE")

    def _drain(self, now_us: int | None) -> None:
        pieces = self.device.deliveries()
        if pieces:
            times = np.concatenate([np.atleast_1d(np.asarray(r, dtype=np.int64)) for r, _ in pieces])
            for event in self.monitor.delivered_many(times):
                self.ingestor.deliver_event(event, event.device_time_us)
        # Declarations of loss first: a device may declare a loss before the chunk that follows it arrives.
        for received, piece in sorted(pieces, key=lambda rp: not isinstance(rp[1], Gap)):
            if isinstance(piece, Gap):
                outcome = self.ingestor.deliver_gap(piece, int(np.min(received)))
            elif isinstance(piece, DeviceEvent):
                outcome = self.ingestor.deliver_event(piece, int(np.min(received)))
                self._check_late(piece, int(np.min(received)))
            else:
                outcome = self.ingestor.deliver_chunk(piece, received)
            self.outcomes[outcome] += 1
        if now_us is not None:
            # Silence is observable only up to the time through which the device has produced its records.
            horizon = min(now_us, self.device.complete_through_us())
            for event in self.monitor.tick(int(horizon)):
                self.ingestor.deliver_event(event, event.device_time_us)

    def _check_late(self, event: DeviceEvent, received_us: int) -> None:
        missed = [t for t in self._viewed if event.device_time_us <= t < received_us]
        if missed:
            self.ingestor.flag(event.stream_id, "LATE_EVENT",
                               f"{event.kind} at {event.device_time_us} us arrived at {received_us} us, after "
                               f"{len(missed)} decision(s) from {missed[0]} us that could not have seen it", received_us)

    def start(self) -> int | None:
        anchor = self.device.start()
        self._drain(anchor)
        return anchor

    def advance(self, device_time_us: int) -> bool:
        if not self.device.advance(device_time_us):
            return False
        self._drain(device_time_us)
        return True

    def view(self, device_time_us: int) -> RawSession:
        self._viewed.append(device_time_us)
        return self.ingestor.view(device_time_us)

    def complete_through_us(self) -> float:
        return self.device.complete_through_us()

    def finish(self) -> RawSession:
        self.device.finish()
        self._drain(None)
        return self.ingestor.view()

    def report(self) -> dict[str, object]:
        """What the boundary did: delivery outcomes, faults, losses, and link transitions."""
        return {"outcomes": dict(sorted(self.outcomes.items())), **self.ingestor.summary(),
                "faults_detail": [asdict(f) for f in self.ingestor.faults],
                "link_states": [e.kind for e in self.monitor.events], "availability": "HOST_RECEIPT"}


@dataclass
class PumpReport:
    received: int = 0
    dropped_chunks: int = 0
    dropped_other: int = 0
    outcomes: Counter = field(default_factory=Counter)


async def pump(pieces: AsyncIterator[tuple[Received, Piece]], ingestor: Ingestor, max_queue: int = 256,
               stop: asyncio.Event | None = None) -> PumpReport:
    """Move pieces from an asynchronous link into the ingestor through a bounded queue.

    The link is never blocked: when the queue is full the newest piece is
    dropped, and a dropped chunk becomes a declared loss immediately. When the
    link ends (or `stop` is set) the queue is drained before returning, so a
    graceful shutdown loses nothing that was already received.
    """
    if max_queue < 1:
        raise ValueError("max_queue must be at least 1")
    queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
    report = PumpReport()
    done = object()

    async def produce() -> None:
        try:
            async for received, piece in pieces:
                if stop is not None and stop.is_set():
                    break
                report.received += 1
                try:
                    queue.put_nowait((received, piece))
                except asyncio.QueueFull:
                    when = int(np.min(np.asarray(received)))
                    if isinstance(piece, StreamChunk) and len(piece):
                        report.dropped_chunks += 1
                        ingestor.deliver_gap(Gap(piece.stream_id, int(piece.sequence[0]), int(piece.sequence[-1]), when,
                                                 f"HOST_QUEUE_FULL: ingestion queue held {max_queue} pieces; chunk dropped"),
                                             when)
                    else:
                        report.dropped_other += 1
                        ingestor.flag(getattr(piece, "stream_id", LINK_STREAM), "DROPPED_AT_QUEUE",
                                      f"{type(piece).__name__} dropped: ingestion queue held {max_queue} pieces", when)
        finally:
            await queue.put(done)

    async def consume() -> None:
        while True:
            item = await queue.get()
            if item is done:
                return
            received, piece = item
            if isinstance(piece, Gap):
                outcome = ingestor.deliver_gap(piece, int(np.min(np.asarray(received))))
            elif isinstance(piece, DeviceEvent):
                outcome = ingestor.deliver_event(piece, int(np.min(np.asarray(received))))
            else:
                outcome = ingestor.deliver_chunk(piece, received)
            report.outcomes[outcome] += 1

    await asyncio.gather(produce(), consume())
    return report
