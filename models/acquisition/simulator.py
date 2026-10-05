"""Deterministic link faults over any source of device records.

SimulatedLink turns a HardwareSource (normally the twin's TwinSource) into a
DeliverySource: the pieces a host would receive from that device over a link,
damaged on a fixed script so that every run is identical. Times in a FaultPlan
are seconds after the source's first protocol marker.

  latency_s    every piece arrives this long after the device held it
  stalls       the link stops; the device buffers, and everything it held during
               the stall arrives when the stall ends (stale data, then a burst)
  outages      the link drops; samples the device held during the outage are never
               delivered (missing samples, which the host must declare lost)
  corrupt      a malformed copy of a chunk arrives before, or with corrupt_replaces
               instead of, the real one: non-integer values, wrong columns, reversed
               or impossible timestamps, mismatched lengths, out-of-range codes, or
               an undeclared stream
  retransmit   a chunk arrives a second time

Device events and the device's own loss declarations travel on a reliable
control path: during a stall or outage they are held and delivered when the
link returns, never dropped. Commands from the host to the device are not
modeled; they are assumed to arrive.

Signal content is not this module's business. Stable, changing, and noisy
physiology come from the twin's protocol phases and scenarios
(models/physiology/scenarios.py); this module damages only delivery. It does
not imitate any vendor's device.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from models.physiology.loop import Capabilities, HardwareSource
from models.physiology.streams import DeviceEvent, RawSession

from .ingest import StreamChunk
from .live import Piece, Received

CORRUPTIONS = ("FLOAT_VALUES", "WRONG_COLUMNS", "REVERSED_TIME", "LENGTH_MISMATCH", "UNKNOWN_STREAM", "OUT_OF_RANGE",
               "AVAILABLE_BEFORE_TAKEN")


@dataclass(frozen=True)
class FaultPlan:
    latency_s: float = 0.0
    stalls: tuple[tuple[float, float], ...] = ()
    outages: tuple[tuple[float, float], ...] = ()
    corrupt: tuple[tuple[str, float, str], ...] = ()
    corrupt_replaces: bool = False
    retransmit: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.latency_s < 10:
            raise ValueError("latency_s must be in [0, 10) s")
        for a, b in self.stalls + self.outages:
            if not 0 <= a < b:
                raise ValueError("stall and outage intervals need 0 <= start < end")
        for _, at, kind in self.corrupt:
            if kind not in CORRUPTIONS or at < 0:
                raise ValueError(f"corruption {kind!r} at {at} s is not one of {CORRUPTIONS}")
        for _, at in self.retransmit:
            if at < 0:
                raise ValueError("retransmission times must be nonnegative")


def corrupted(chunk: StreamChunk, kind: str) -> StreamChunk:
    """A malformed copy of `chunk` of the given kind."""
    first = next(iter(chunk.columns))
    columns = {c: np.array(v, copy=True) for c, v in chunk.columns.items()}
    if kind == "FLOAT_VALUES":
        values = columns[first].astype(np.float64)
        values[0] = np.nan
        return replace(chunk, columns={**columns, first: values})
    if kind == "WRONG_COLUMNS":
        return replace(chunk, columns={**{c: v for c, v in columns.items() if c != first}, f"{first}_renamed": columns[first]})
    if kind == "REVERSED_TIME":
        times = chunk.device_time_us[::-1].copy() if len(chunk) > 1 else chunk.device_time_us - 1_000_000
        return replace(chunk, device_time_us=times)
    if kind == "LENGTH_MISMATCH":
        return replace(chunk, columns={**columns, first: columns[first][:-1]})
    if kind == "UNKNOWN_STREAM":
        return replace(chunk, stream_id=f"undeclared_{chunk.stream_id}")
    if kind == "OUT_OF_RANGE":
        columns[first][0] = np.int64(2) ** 40
        return replace(chunk, columns=columns)
    if kind == "AVAILABLE_BEFORE_TAKEN":
        return replace(chunk, available_us=chunk.device_time_us - 1)
    raise ValueError(f"unknown corruption {kind!r}")


class SimulatedLink:
    """A device behind a damaged link: a deterministic DeliverySource over a HardwareSource."""

    def __init__(self, source: HardwareSource, plan: FaultPlan = FaultPlan()) -> None:
        self.source, self.plan = source, plan
        self._anchor: int | None = None
        self._taken: dict[str, int] = {}
        self._held: dict[str, list[tuple[np.ndarray, StreamChunk]]] = {}
        self._control_seen: set[tuple] = set()
        self._held_control: list[tuple[int, Piece]] = []
        self._outbox: list[tuple[Received, Piece]] = []
        self._corrupt = sorted(plan.corrupt, key=lambda c: c[1])
        self._retransmit = sorted(plan.retransmit, key=lambda r: r[1])
        self.lost_in_outages: dict[str, int] = {}

    def capabilities(self) -> Capabilities:
        caps = self.source.capabilities()
        return replace(caps, source=f"{caps.source} over a simulated link", connection_state="SIMULATED_LINK")

    def start(self) -> int | None:
        self._anchor = self.source.start()
        if self._anchor is not None:
            self._collect(self.source.view(self._anchor), self._anchor)
        return self._anchor

    def advance(self, device_time_us: int) -> bool:
        if not self.source.advance(device_time_us):
            return False
        self._collect(self.source.view(device_time_us), device_time_us)
        return True

    def complete_through_us(self) -> float:
        return self.source.complete_through_us()

    def finish(self) -> None:
        raw = self.source.finish()
        self._collect(raw, None)

    def deliveries(self) -> list[tuple[Received, Piece]]:
        out, self._outbox = self._outbox, []
        return out

    # ------------------------------------------------------------ timing
    def _seconds(self, device_us: np.ndarray) -> np.ndarray:
        assert self._anchor is not None
        return (np.asarray(device_us, dtype=np.int64) - self._anchor) / 1e6

    def _receipt(self, held_us: np.ndarray) -> np.ndarray:
        """When the host receives what the device held at held_us (stalls hold it back)."""
        assert self._anchor is not None
        received = np.asarray(held_us, dtype=np.int64) + int(round(self.plan.latency_s * 1e6))
        s = self._seconds(held_us)
        for a, b in self.plan.stalls + self.plan.outages:
            inside = (s >= a) & (s < b)
            received = np.where(inside, np.maximum(received, self._anchor + int(round(b * 1e6))), received)
        return received

    def _in_outage(self, held_us: np.ndarray) -> np.ndarray:
        s = self._seconds(held_us)
        lost = np.zeros(len(s), dtype=bool)
        for a, b in self.plan.outages:
            lost |= (s >= a) & (s < b)
        return lost

    # -------------------------------------------------------- collection
    def _collect(self, raw: RawSession, now_us: int | None) -> None:
        """Gather what the device newly holds, then hand over everything received by now_us (None: everything)."""
        for name, stream in raw.streams.items():
            start = self._taken.get(name, 0)
            if len(stream) > start:
                chunk = StreamChunk.of(stream, start)
                self._taken[name] = len(stream)
                lost = self._in_outage(chunk.available_us)
                if lost.any():
                    self.lost_in_outages[name] = self.lost_in_outages.get(name, 0) + int(lost.sum())
                    keep = np.flatnonzero(~lost)
                    chunk = StreamChunk(name, chunk.sequence[keep], chunk.device_time_us[keep], chunk.available_us[keep],
                                        {c: v[keep] for c, v in chunk.columns.items()})
                if len(chunk):
                    self._held.setdefault(name, []).append((self._receipt(chunk.available_us), chunk))
        for gap in raw.gaps:
            key = ("gap", gap.stream_id, gap.first_sequence, gap.last_sequence)
            if key not in self._control_seen:
                self._control_seen.add(key)
                self._held_control.append((int(self._receipt(np.array([gap.device_time_us]))[0]), gap))
        for event in raw.events:
            key = ("event", event.stream_id, event.sequence)
            if key not in self._control_seen:
                self._control_seen.add(key)
                self._held_control.append((int(self._receipt(np.array([event.device_time_us]))[0]), event))
        self._release(now_us)

    def _release(self, now_us: int | None) -> None:
        due = [(r, p) for r, p in self._held_control if now_us is None or r <= now_us]
        self._held_control = [(r, p) for r, p in self._held_control if not (now_us is None or r <= now_us)]
        self._outbox.extend(sorted(due, key=lambda rp: (rp[0], isinstance(rp[1], DeviceEvent))))
        session_s = None if now_us is None else float(self._seconds(np.array([now_us]))[0])
        for name in sorted(self._held):
            parts = self._held[name]
            if not parts:
                continue
            received = np.concatenate([r for r, _ in parts])
            chunk = _join([c for _, c in parts])
            ready = len(received) if now_us is None else int(np.searchsorted(received, now_us, side="right"))
            if ready == 0:
                continue
            out, rest = chunk.part(0, ready), chunk.part(ready, len(received))
            self._held[name] = [(received[ready:], rest)] if len(rest) else []
            self._deliver_chunk(received[:ready], out, session_s)

    def _deliver_chunk(self, received: np.ndarray, chunk: StreamChunk, session_s: float | None) -> None:
        replaced = False
        due = [c for c in self._corrupt if c[0] == chunk.stream_id and (session_s is None or c[1] <= session_s)]
        for c in due:
            self._corrupt.remove(c)
            self._outbox.append((received, corrupted(chunk, c[2])))
            replaced = replaced or self.plan.corrupt_replaces
        if not replaced:
            self._outbox.append((received, chunk))
        again = [r for r in self._retransmit if r[0] == chunk.stream_id and (session_s is None or r[1] <= session_s)]
        for r in again:
            self._retransmit.remove(r)
            self._outbox.append((received, chunk))


def _join(chunks: list[StreamChunk]) -> StreamChunk:
    if len(chunks) == 1:
        return chunks[0]
    first = chunks[0]
    return StreamChunk(first.stream_id, np.concatenate([c.sequence for c in chunks]),
                       np.concatenate([c.device_time_us for c in chunks]), np.concatenate([c.available_us for c in chunks]),
                       {k: np.concatenate([c.columns[k] for c in chunks]) for k in first.columns})
