"""Live ingestion: device deliveries in, a lawful RawSession out.

A live device delivers its records in pieces: chunks of samples (a FIFO batch,
a radio notification), device events, and declarations of loss. The Ingestor
checks every piece against the evidence rules the pipeline assumes, assembles
the accepted pieces into the same RawSession the twin and a recorded bundle
produce, and makes every departure explicit:

  malformed or out-of-order pieces   rejected and kept as Faults, never repaired
  missing sequences                  a GAP: the device's own declaration when it
                                     sent one, otherwise one the host declares
                                     with the exact missing range
  a retransmitted prefix             dropped only if identical to what was
                                     accepted; a conflicting one is a Fault
  memory                             each stream holds at most `capacity`
                                     samples; beyond that new samples are lost
                                     and declared lost (the MAX30102 FIFO policy:
                                     keep the old, count the new)
  host-side control                  with stamp_host_availability, a sample's
                                     availability becomes the later of when
                                     firmware held it and when the host received
                                     it, so a loop running on the host decides
                                     only on what the host held, and a replay of
                                     the record reproduces that decision

Every timestamp a device sent is kept. Host receive time never replaces a
device time; when it is used, it can only delay availability.

LinkMonitor turns delivery timing into recorded link events (LIVE, STALE,
DISCONNECTED, RECONNECTED), so a silent link is never mistaken for a subject
who is still producing data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping

import numpy as np

from models.physiology.streams import STREAM_COLUMNS, DeviceEvent, Gap, RawSession, Stream

LINK_STREAM = "acquisition_link"


@dataclass(frozen=True)
class StreamChunk:
    """Consecutive samples of one stream, as a device delivers them."""

    stream_id: str
    sequence: np.ndarray
    device_time_us: np.ndarray
    available_us: np.ndarray
    columns: Mapping[str, np.ndarray]

    def __len__(self) -> int:
        return len(self.sequence)

    @classmethod
    def of(cls, stream: Stream, start: int = 0, stop: int | None = None) -> "StreamChunk":
        part = stream.slice(start, len(stream) if stop is None else stop)
        assert part.available_us is not None
        return cls(part.name, part.sequence, part.device_time_us, part.available_us, dict(part.columns))

    def part(self, start: int, stop: int) -> "StreamChunk":
        return StreamChunk(self.stream_id, self.sequence[start:stop], self.device_time_us[start:stop],
                           self.available_us[start:stop], {c: v[start:stop] for c, v in self.columns.items()})


@dataclass(frozen=True)
class Fault:
    """A delivered piece the ingestor refused or flagged, and why."""

    stream_id: str
    kind: str
    detail: str
    received_us: int


def _code_ranges(descriptors: dict[str, dict[str, float]]) -> dict[str, dict[str, tuple[int, int]]]:
    """Integer codes each converter can produce, per column, where the descriptors state it."""
    ranges: dict[str, dict[str, tuple[int, int]]] = {}
    eda, ppg, imu = descriptors.get("eda", {}), descriptors.get("ppg", {}), descriptors.get("imu", {})
    if "adc_bits" in eda:
        half = 2 ** (int(eda["adc_bits"]) - 1)
        ranges["eda"] = {"code": (-half, half - 1)}
    if "full_scale_counts" in ppg:
        ranges["ppg"] = {c: (0, int(ppg["full_scale_counts"])) for c in ("red_counts", "ir_counts")}
    for kind, axes, scale in (("accel", ("ax_lsb", "ay_lsb", "az_lsb"), "g"), ("gyro", ("gx_lsb", "gy_lsb", "gz_lsb"), "dps")):
        fs, lsb = imu.get(f"{kind}_full_scale_{scale}"), imu.get(f"{kind}_lsb_per_{scale}")
        if fs is not None and lsb is not None:
            half = int(round(fs * lsb))
            ranges.setdefault("imu", {}).update({axis: (-half, half - 1) for axis in axes})
    return ranges


class Ingestor:
    """Assembles delivered pieces into a RawSession, refusing what breaks the evidence rules."""

    def __init__(self, descriptors: dict[str, dict[str, float]],
                 columns: Mapping[str, tuple[str, ...]] = STREAM_COLUMNS,
                 capacity: int | Mapping[str, int] = 4_000_000,
                 stamp_host_availability: bool = False) -> None:
        self.descriptors = {name: dict(d) for name, d in descriptors.items()}
        self.columns = {name: tuple(c) for name, c in columns.items()}
        self.capacity = {name: int(capacity[name] if isinstance(capacity, Mapping) else capacity) for name in self.columns}
        self.stamp_host_availability = stamp_host_availability
        self._ranges = _code_ranges(self.descriptors)
        self._parts: dict[str, list[tuple[np.ndarray, ...]]] = {name: [] for name in self.columns}
        self._cache: dict[str, Stream] = {}
        self._count = {name: 0 for name in self.columns}
        self._last_sequence: dict[str, int] = {}
        self._last_time: dict[str, int] = {}
        self._last_available: dict[str, int] = {}
        self._declared_through: dict[str, int] = {}
        self.gaps: list[Gap] = []
        self.events: list[DeviceEvent] = []
        self._event_keys: dict[tuple[str, int], DeviceEvent] = {}
        self.faults: list[Fault] = []
        self.lost_to_capacity = {name: 0 for name in self.columns}

    # ------------------------------------------------------------ samples
    def deliver_chunk(self, chunk: StreamChunk, received_us: int | np.ndarray) -> str:
        """Ingest one chunk received at received_us (device clock; scalar or per sample).

        Returns ACCEPTED, TRIMMED (an identical retransmitted prefix was
        dropped), DUPLICATE, EMPTY, LOST_TO_CAPACITY, or REJECTED:<fault kind>.
        """
        name = chunk.stream_id
        received = np.atleast_1d(np.asarray(received_us, dtype=np.int64))
        first_received = int(received.min()) if len(received) else 0
        if name not in self.columns:
            return self._reject(name, "UNKNOWN_STREAM", f"stream {name!r} is not declared", first_received)
        problem = self._malformed(chunk)
        if problem:
            return self._reject(name, "MALFORMED", problem, first_received)
        n = len(chunk)
        if n == 0:
            return "EMPTY"
        if len(received) not in (1, n):
            return self._reject(name, "MALFORMED", f"{len(received)} receive times for {n} samples", first_received)
        seq = np.asarray(chunk.sequence, dtype=np.int64)
        dev = np.asarray(chunk.device_time_us, dtype=np.int64)
        avail = np.asarray(chunk.available_us, dtype=np.int64)
        cols = {c: np.asarray(chunk.columns[c], dtype=np.int64) for c in self.columns[name]}
        received = np.broadcast_to(received, (n,))
        outcome = "ACCEPTED"
        last = self._last_sequence.get(name)
        if last is not None and seq[0] <= last:
            overlap = int(np.searchsorted(seq, last, side="right"))
            if not self._matches_accepted(name, seq[:overlap], dev[:overlap], chunk, overlap):
                return self._reject(name, "CONFLICTING_RETRANSMISSION",
                                    f"sequences {int(seq[0])}..{int(seq[overlap - 1])} differ from those already accepted",
                                    first_received)
            if overlap == n:
                return "DUPLICATE"
            seq, dev, avail, received = seq[overlap:], dev[overlap:], avail[overlap:], received[overlap:]
            cols = {c: v[overlap:] for c, v in cols.items()}
            outcome = "TRIMMED"
        if self.stamp_host_availability:
            avail = np.maximum(avail, received)
        if name in self._last_time and (dev[0] <= self._last_time[name] or avail[0] < self._last_available[name]):
            return self._reject(name, "OUT_OF_ORDER",
                                f"sequence {int(seq[0])} taken at {int(dev[0])} us, available at {int(avail[0])} us, "
                                f"after sample {last} taken at {self._last_time[name]} us, available at "
                                f"{self._last_available[name]} us", int(received[0]))
        for gap in self.gaps:
            if gap.stream_id == name and np.any((seq >= gap.first_sequence) & (seq <= gap.last_sequence)):
                return self._reject(name, "CONFLICTS_DECLARED_GAP",
                                    f"chunk carries sequences {gap.first_sequence}..{gap.last_sequence} that were "
                                    f"declared lost ({gap.cause})", int(received[0]))
        # Every missing sequence must be declared: before the chunk, and at any jump inside it.
        through = self._declared_through.get(name)
        if through is not None:
            self._declare_missing(name, through, int(seq[0]), int(received[0]))
        for i in np.flatnonzero(np.diff(seq) > 1):
            self._declare_missing(name, int(seq[i]), int(seq[i + 1]), int(received[i + 1]))
        room = max(self.capacity[name] - self._count[name], 0)
        if room < len(seq):
            self._declare_capacity_loss(name, seq[room:], received[room:])
            outcome = "LOST_TO_CAPACITY"
            if room == 0:
                return outcome
            seq, dev, avail = seq[:room], dev[:room], avail[:room]
            cols = {c: v[:room] for c, v in cols.items()}
        self._parts[name].append((seq, dev, avail, *[cols[c] for c in self.columns[name]]))
        self._cache.pop(name, None)
        self._count[name] += len(seq)
        self._last_sequence[name] = int(seq[-1])
        self._last_time[name] = int(dev[-1])
        self._last_available[name] = int(avail[-1])
        self._declared_through[name] = max(self._declared_through.get(name, -1), int(seq[-1]))
        return outcome

    def _malformed(self, chunk: StreamChunk) -> str | None:
        expected = self.columns[chunk.stream_id]
        if set(chunk.columns) != set(expected):
            return f"columns {sorted(chunk.columns)} differ from the declared {list(expected)}"
        arrays = {"sequence": chunk.sequence, "device_time_us": chunk.device_time_us,
                  "available_us": chunk.available_us, **{c: chunk.columns[c] for c in expected}}
        lengths = set()
        for label, values in arrays.items():
            values = np.asarray(values)
            if values.ndim != 1:
                return f"{label} is not one-dimensional"
            if values.size and not np.issubdtype(values.dtype, np.integer):
                return f"{label} holds {values.dtype} values; device records are integers"
            lengths.add(len(values))
        if len(lengths) != 1:
            return f"arrays differ in length ({sorted(lengths)})"
        seq = np.asarray(chunk.sequence, dtype=np.int64)
        dev = np.asarray(chunk.device_time_us, dtype=np.int64)
        avail = np.asarray(chunk.available_us, dtype=np.int64)
        if len(seq) > 1 and np.any(np.diff(seq) <= 0):
            return "sequence numbers do not increase strictly"
        if len(seq) > 1 and np.any(np.diff(dev) <= 0):
            return "sample times do not increase strictly"
        if len(seq) > 1 and np.any(np.diff(avail) < 0):
            return "availability times decrease"
        if np.any(seq < 0) or np.any(dev < 0):
            return "negative sequence number or sample time"
        if np.any(avail < dev):
            return "a sample is available before it was taken"
        for c, (low, high) in self._ranges.get(chunk.stream_id, {}).items():
            values = np.asarray(chunk.columns[c], dtype=np.int64)
            if np.any(values < low) or np.any(values > high):
                return f"{c} holds codes outside the converter's range [{low}, {high}]"
        return None

    def _matches_accepted(self, name: str, seq: np.ndarray, dev: np.ndarray, chunk: StreamChunk, overlap: int) -> bool:
        stream = self._stream(name)
        a = np.searchsorted(stream.sequence, seq)
        if np.any(a >= len(stream)) or not np.array_equal(stream.sequence[np.minimum(a, len(stream) - 1)], seq):
            return False
        if not np.array_equal(stream.device_time_us[a], dev):
            return False
        return all(np.array_equal(stream.columns[c][a], np.asarray(chunk.columns[c][:overlap], dtype=np.int64))
                   for c in self.columns[name])

    def _declare_missing(self, name: str, after: int, before: int, received_us: int) -> None:
        """Host-declare every sequence strictly between `after` and `before` that no declaration covers."""
        if before <= after + 1:
            return
        covered = sorted((g.first_sequence, g.last_sequence) for g in self.gaps
                         if g.stream_id == name and g.last_sequence > after and g.first_sequence < before)
        cursor = after + 1
        for a, b in covered + [(before, before)]:
            if a > cursor:
                self._add_gap(Gap(name, cursor, a - 1, received_us,
                                  f"UNDECLARED_SEQUENCE_DISCONTINUITY: host received sequence {before} after {after}; "
                                  f"{a - cursor} samples never arrived and the device declared no loss"))
            cursor = max(cursor, b + 1)

    def _declare_capacity_loss(self, name: str, lost: np.ndarray, received: np.ndarray) -> None:
        """Declare samples refused for lack of room, one GAP per contiguous run of sequences."""
        self.lost_to_capacity[name] += len(lost)
        starts = np.concatenate([[0], np.flatnonzero(np.diff(lost) > 1) + 1])
        stops = np.concatenate([starts[1:], [len(lost)]])
        for a, b in zip(starts, stops):
            first, last = int(lost[a]), int(lost[b - 1])
            cause = (f"HOST_BUFFER_FULL: stream holds its capacity of {self.capacity[name]} samples; "
                     f"{self.lost_to_capacity[name]} newer samples lost")
            previous = next((i for i, g in enumerate(self.gaps) if g.stream_id == name
                             and g.cause.startswith("HOST_BUFFER_FULL") and g.last_sequence == first - 1), None)
            if previous is not None:
                self.gaps[previous] = replace(self.gaps[previous], last_sequence=last, cause=cause)
            else:
                self._add_gap(Gap(name, first, last, int(received[a]), cause))
        self._declared_through[name] = max(self._declared_through.get(name, -1), int(lost[-1]))

    def _add_gap(self, gap: Gap) -> None:
        self.gaps.append(gap)
        self.gaps.sort(key=lambda g: (g.stream_id, g.first_sequence))

    def _reject(self, name: str, kind: str, detail: str, received_us: int) -> str:
        self.faults.append(Fault(name, kind, detail, received_us))
        return f"REJECTED:{kind}"

    # ------------------------------------------------- gaps and events
    def deliver_gap(self, gap: Gap, received_us: int) -> str:
        """A device's own declaration of lost samples (it may precede the samples before the loss)."""
        name = gap.stream_id
        if name not in self.columns:
            return self._reject(name, "UNKNOWN_STREAM", f"gap for undeclared stream {name!r}", received_us)
        if gap.last_sequence < gap.first_sequence or gap.first_sequence < 0 or not gap.cause:
            return self._reject(name, "MALFORMED", f"gap {gap.first_sequence}..{gap.last_sequence} is not a valid declaration",
                                received_us)
        if any(g.stream_id == name and (g.first_sequence, g.last_sequence) == (gap.first_sequence, gap.last_sequence)
               and g.cause == gap.cause for g in self.gaps):
            return "DUPLICATE"
        last = self._last_sequence.get(name)
        if (last is not None and gap.first_sequence <= last) or any(
                g.stream_id == name and g.first_sequence <= gap.last_sequence and g.last_sequence >= gap.first_sequence
                for g in self.gaps):
            return self._reject(name, "GAP_OVERLAPS_RECORD",
                                f"declared loss {gap.first_sequence}..{gap.last_sequence} overlaps samples or losses "
                                "already recorded", received_us)
        self._add_gap(gap)
        return "ACCEPTED"

    def deliver_event(self, event: DeviceEvent, received_us: int) -> str:
        """A device-logged event, kept with its device time whenever it arrives."""
        key = (event.stream_id, event.sequence)
        if not event.kind or event.sequence < 0 or event.device_time_us < 0 or not all(
                isinstance(k, str) and isinstance(v, (int, float)) and math.isfinite(v) for k, v in event.attributes):
            return self._reject(event.stream_id, "MALFORMED", f"event {key} is not a valid device event", received_us)
        if key in self._event_keys:
            if self._event_keys[key] == event:
                return "DUPLICATE"
            return self._reject(event.stream_id, "CONFLICTING_RETRANSMISSION",
                                f"event {key} differs from the one already accepted", received_us)
        self._event_keys[key] = event
        self.events.append(event)
        return "ACCEPTED"

    def flag(self, stream_id: str, kind: str, detail: str, received_us: int) -> None:
        """Record a fault found by the caller (for example, an event that arrived after a decision needed it)."""
        self.faults.append(Fault(stream_id, kind, detail, received_us))

    # ---------------------------------------------------------- output
    def _stream(self, name: str) -> Stream:
        if name not in self._cache:
            parts = self._parts[name]
            width = 3 + len(self.columns[name])
            arrays = [np.concatenate([p[i] for p in parts]) if parts else np.zeros(0, dtype=np.int64) for i in range(width)]
            self._cache[name] = Stream(name, arrays[0], arrays[1],
                                       {c: arrays[3 + i] for i, c in enumerate(self.columns[name])}, arrays[2])
        return self._cache[name]

    def view(self, device_time_us: int | None = None) -> RawSession:
        """Everything accepted (or, at device_time_us, everything held in memory by then)."""
        events = sorted(self.events, key=lambda e: (e.device_time_us, e.stream_id, e.sequence))
        session = RawSession({name: self._stream(name) for name in self.columns}, self.descriptors,
                             sorted(self.gaps, key=lambda g: (g.device_time_us, g.stream_id, g.first_sequence)), events)
        return session if device_time_us is None else session.until(device_time_us)

    def summary(self) -> dict[str, object]:
        return {"samples": dict(self._count), "gaps": len(self.gaps),
                "host_declared_gaps": sum(1 for g in self.gaps if g.cause.startswith(("UNDECLARED", "HOST_"))),
                "faults": len(self.faults), "faults_by_kind": _count_by(f.kind for f in self.faults),
                "lost_to_capacity": dict(self.lost_to_capacity), "events": len(self.events)}


def _count_by(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


class LinkMonitor:
    """Delivery health of a live link, recorded as device events on the acquisition_link stream.

    Silence is measured from the last delivery. A transition is stamped at the
    device time its threshold was crossed, so the record shows when the link
    actually went quiet, not when someone next looked.
    """

    def __init__(self, stale_after_us: int = 500_000, disconnected_after_us: int = 2_000_000) -> None:
        if not 0 < stale_after_us < disconnected_after_us:
            raise ValueError("need 0 < stale_after_us < disconnected_after_us")
        self.stale_after_us, self.disconnected_after_us = stale_after_us, disconnected_after_us
        self.state = "AWAITING_FIRST_DELIVERY"
        self.last_delivery_us: int | None = None
        self.events: list[DeviceEvent] = []

    def _emit(self, state: str, device_time_us: int, **attributes: float) -> DeviceEvent:
        self.state = state
        event = DeviceEvent(LINK_STREAM, len(self.events), f"LINK:{state}", int(device_time_us),
                            tuple(sorted(attributes.items())))
        self.events.append(event)
        return event

    def tick(self, now_us: int) -> list[DeviceEvent]:
        """Record every threshold the silence has crossed by now_us."""
        out = []
        if self.last_delivery_us is None:
            return out
        silence = now_us - self.last_delivery_us
        if self.state == "LIVE" and silence >= self.stale_after_us:
            out.append(self._emit("STALE", self.last_delivery_us + self.stale_after_us, silence_us=self.stale_after_us))
        if self.state == "STALE" and silence >= self.disconnected_after_us:
            out.append(self._emit("DISCONNECTED", self.last_delivery_us + self.disconnected_after_us,
                                  silence_us=self.disconnected_after_us))
        return out

    def delivered(self, received_us: int) -> list[DeviceEvent]:
        """A piece arrived at received_us."""
        out = self.tick(received_us)
        if self.state == "AWAITING_FIRST_DELIVERY":
            out.append(self._emit("LIVE", received_us))
        elif self.state in ("STALE", "DISCONNECTED"):
            silence = received_us - (self.last_delivery_us if self.last_delivery_us is not None else received_us)
            out.append(self._emit("RECONNECTED" if self.state == "DISCONNECTED" else "LIVE", received_us,
                                  silence_us=silence))
            self.state = "LIVE"
        if self.last_delivery_us is None or received_us > self.last_delivery_us:
            self.last_delivery_us = received_us
        return out

    def delivered_many(self, received_us: np.ndarray) -> list[DeviceEvent]:
        """Many pieces arrived; only silences long enough to cross a threshold can change the state."""
        times = np.unique(np.asarray(received_us, dtype=np.int64))
        if not len(times):
            return []
        previous = np.concatenate([[self.last_delivery_us if self.last_delivery_us is not None else times[0]], times[:-1]])
        notable = (times - previous >= self.stale_after_us)
        notable[0] = notable[-1] = True
        out = []
        for i in np.flatnonzero(notable):
            if i > 0 and (self.last_delivery_us is None or times[i - 1] > self.last_delivery_us):
                self.last_delivery_us = int(times[i - 1])  # the deliveries in between happened
            out += self.delivered(int(times[i]))
        return out

    def failed(self, now_us: int, code: float = 0.0) -> list[DeviceEvent]:
        """The transport reported an error: the link is down now, whatever the silence says."""
        if self.state == "DISCONNECTED":
            return []
        return [self._emit("DISCONNECTED", now_us, transport_error=code)]
