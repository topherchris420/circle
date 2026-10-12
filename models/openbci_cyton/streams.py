"""Cyton packets in, CIRCLE pieces out: sample chunks, exact GAPs, and marker events. No I/O, no clock.

Sample numbering. The Cyton counts samples with an 8-bit counter that restarts
at 0 whenever the ADC starts. Within an *epoch*, a run over which the counter
can be followed, every packet gets an unwrapped `sample_index`, the number of
ADC samples since the epoch's origin. A new epoch begins at every acquisition
segment (each 'b' the host sends) and after any discontinuity the counter
cannot resolve. Sequence numbers run across epochs without reuse.

Exact losses. The counter alone resolves a jump of fewer than 256 samples. A
longer silence is resolved by the sample clock: the ADS1299's oscillator is
within +-2.5 % of nominal over its whole temperature range (datasheet), so
the receipt time of the next packet, set against the epoch's minimum-delay
clock line, admits exactly one count of lost samples as long as no packet
waits more than LATENCY_BOUND_US between being sampled and being read. When
more than one count (or none) remains possible, the loss is one marked
discontinuity whose cause says its size is unknown, and a new epoch begins.

  CYTON_COUNTER_DISCONTINUITY   the counter (and, past one wrap, the clock)
                                fixes exactly which samples never arrived
  CYTON_SEGMENT_START_LOST      the counter restarts at 0 on 'b'; the first
                                packets of the segment never arrived
  COUNTER_AMBIGUOUS / LINK_LOST one marked discontinuity of unknown size
  ACCEL_LOSS_UNKNOWN            packets were lost; the accelerometer readings
                                they may have carried (about one in ten) are
                                not countable, so one slot is marked
  CONFLICTING_RETRANSMISSION    a counter repeated with different contents

Timing. Sample times are on the host's monotonic clock (TIMEBASE:HOST_MONOTONIC):
the epoch's MinimumDelayClock line at the sample's index, which never lies
after any receipt seen so far. The device's own clock is never lost: every row
keeps `epoch`, `sample_index`, and the raw `counter`, so exact intervals are
recovered from the ADC, not from the radio. Availability is host receipt.

Daisy. With the Daisy module the board alternates: odd counters carry channels
1-8, even counters channels 9-16, each the average of two consecutive ADC
samples (ADS_writeChannelDataAvgDaisy), so each half is a 125 Hz stream whose
sample instant is the midpoint of the two averaged samples. The first daisy
half after every ADC start averages in a value left from before the start
(updateDaisyData runs after firstDataPacket is cleared); it is kept as sent and
flagged.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from models.acquisition.clock import MinimumDelayClock
from models.acquisition.ingest import StreamChunk
from models.physiology.streams import DeviceEvent, Gap

from . import protocol as p
from .framing import Packet, channel_matrix

EXG_STREAM, DAISY_STREAM = "cyton_exg", "cyton_daisy"
ACCEL_STREAM, AUX_STREAM = "cyton_accel", "cyton_aux"
MARKER_STREAM, CONTROL_STREAM = "cyton_markers", "cyton_control"
SERIAL_FAULTS = "cyton_serial"

INDEX_COLUMNS = ("epoch", "sample_index", "counter")
LATENCY_BOUND_US = 500_000            # longest a packet is assumed to wait between its data-ready and the host's read
MAPPING_MARGIN_US = 25_000            # how far a packet may beat the epoch's fastest delivery so far (USB batching)
WRAP = 256


def exg_columns(first: int) -> tuple[str, ...]:
    return tuple(f"ch{first + i}" for i in range(p.CHANNELS_PER_ADS)) + INDEX_COLUMNS


@dataclass(frozen=True)
class StreamLayout:
    """Which streams a session declares, from the board mode and the Daisy."""

    board_mode: str = "default"
    daisy: bool = False
    gains: tuple[int, ...] = (p.DEFAULT_GAIN,) * 16

    def __post_init__(self) -> None:
        if self.board_mode not in ("default", "analog", "digital", "marker"):
            raise ValueError(f"CIRCLE does not stream in board mode {self.board_mode!r}")

    @property
    def exg_rate_hz(self) -> float:
        return float(p.DAISY_RATE_HZ if self.daisy else p.STREAM_RATE_HZ)

    def columns(self) -> dict[str, tuple[str, ...]]:
        cols = {EXG_STREAM: exg_columns(1)}
        if self.daisy:
            cols[DAISY_STREAM] = exg_columns(9)
        if self.board_mode == "default":
            cols[ACCEL_STREAM] = ("ax_lsb", "ay_lsb", "az_lsb", "epoch", "sample_index")
        elif self.board_mode == "analog":
            cols[AUX_STREAM] = (*p.ANALOG_PINS, "epoch", "sample_index")
        elif self.board_mode == "digital":
            cols[AUX_STREAM] = (*p.DIGITAL_PINS, "epoch", "sample_index")
        return cols

    def descriptors(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for name, first in ((EXG_STREAM, 1), (DAISY_STREAM, 9)):
            if name == DAISY_STREAM and not self.daisy:
                continue
            d = {"nominal_rate_hz": self.exg_rate_hz, "adc_bits": 24.0, "vref_v": p.VREF_V,
                 "adc_max_code": float(p.ADC_MAX_CODE), "counter_modulus": float(WRAP),
                 "oscillator_tolerance": p.OSCILLATOR_TOLERANCE_FULL,
                 "two_sample_average": 1.0 if self.daisy else 0.0}
            for i in range(p.CHANNELS_PER_ADS):
                gain = self.gains[first - 1 + i]
                d[f"ch{first + i}_gain"] = float(gain)
                d[f"ch{first + i}_uv_per_count"] = p.microvolts_per_count(gain)
            out[name] = d
        if self.board_mode == "default":
            out[ACCEL_STREAM] = {"nominal_rate_hz": float(p.ACCEL_RATE_HZ), "accel_g_per_count": p.ACCEL_G_PER_COUNT,
                                 "accel_full_scale_g": p.ACCEL_FULL_SCALE_G}
        elif self.board_mode == "analog":
            out[AUX_STREAM] = {"nominal_rate_hz": float(p.STREAM_RATE_HZ), "analog_max_code": float(p.ANALOG_MAX_CODE)}
        elif self.board_mode == "digital":
            out[AUX_STREAM] = {"nominal_rate_hz": float(p.STREAM_RATE_HZ)}
        return out


@dataclass
class _Epoch:
    number: int
    clock: MinimumDelayClock
    base: dict[str, int]                 # sequence of slot 0, per packet stream
    last_index: int | None = None
    last_counter: int | None = None
    last_received: int | None = None
    last_raw: bytes = b""
    restarted_daisy: bool = False        # the first daisy half of this epoch may average a stale value
    flagged_types: bool = False          # unexpected packet types are reported once per epoch


@dataclass
class _Stamp:
    """Last stamped sample time per stream, so times strictly increase across clock updates."""

    last: dict[str, int] = field(default_factory=dict)

    def __call__(self, stream: str, estimate: np.ndarray) -> np.ndarray:
        out = np.maximum(np.round(estimate).astype(np.int64), 0)
        floor = self.last.get(stream, -1)
        for i in range(len(out)):
            if out[i] <= floor:
                out[i] = floor + 1
            floor = out[i]
        if len(out):
            self.last[stream] = int(out[-1])
        return out


class CytonStreams:
    """Turns the packets of one session into pieces for the ingestion boundary."""

    def __init__(self, layout: StreamLayout, latency_bound_us: int = LATENCY_BOUND_US) -> None:
        self.layout = layout
        self.latency_bound_us = int(latency_bound_us)
        self.columns = layout.columns()
        self.packet_streams = [s for s in (EXG_STREAM, DAISY_STREAM, AUX_STREAM) if s in self.columns]
        self.next_sequence = {name: 0 for name in self.columns}
        self.epoch: _Epoch | None = None
        self.epochs = 0
        self.stamp = _Stamp()
        self.delivered = Counter()
        self.faults: list[tuple[str, str, str, int]] = []
        self.packet_types: Counter[str] = Counter()
        self.duplicates = 0
        self.marker_sequence = 0
        self.lost_packets = 0
        self.broken = False
        self.clocks: list[MinimumDelayClock] = []              # one per epoch; each keeps its receipts' lower hull
        self._pending_start: int | None = None

    # ---------------------------------------------------------- epochs
    def _slot(self, stream: str, index: int) -> int:
        if stream in (EXG_STREAM, DAISY_STREAM) and self.layout.daisy:
            return index // 2
        return index

    def _owns(self, stream: str, index: int) -> bool:
        if not self.layout.daisy:
            return stream != DAISY_STREAM
        if stream == EXG_STREAM:
            return index % 2 == 1
        if stream == DAISY_STREAM:
            return index % 2 == 0
        return True

    def _first_owned(self, stream: str, index: int) -> int:
        return index if self._owns(stream, index) else index + 1

    def _new_epoch(self, first_index: int) -> _Epoch:
        base = {s: self.next_sequence[s] - self._slot(s, self._first_owned(s, first_index)) for s in self.packet_streams}
        clock = MinimumDelayClock(p.NOMINAL_PERIOD_US, p.OSCILLATOR_TOLERANCE_FULL)
        self.epoch = _Epoch(self.epochs, clock, base, restarted_daisy=self.layout.daisy)
        self.clocks.append(clock)
        self.epochs += 1
        return self.epoch

    def start_segment(self, sent_us: int) -> None:
        """The host sent 'b' at sent_us: the ADC restarts and its counter begins again at 0."""
        self.epoch = None
        self._pending_start = int(sent_us)
        self.broken = False

    def _mark(self, stream: str, at_us: int, cause: str) -> Gap:
        first = self.next_sequence[stream]
        self.next_sequence[stream] += 1
        return Gap(stream, first, first, at_us, cause)

    def _mark_all(self, at_us: int, cause: str) -> list[Gap]:
        out = []
        for stream in self.columns:
            if self.delivered[stream]:
                out.append(self._mark(stream, at_us, cause))
        return out

    def end_segment(self, stop_sent_us: int, silence_limit_us: int) -> list[Gap]:
        """The host sent 's'. Samples taken after the last packet that arrived are revealed by no later packet:
        when the link had been silent longer than silence_limit_us before the stop, mark them, size unknown."""
        epoch = self.epoch
        self._pending_start = None
        if epoch is None or epoch.last_received is None or epoch.last_index < 0:
            return []
        silence = stop_sent_us - epoch.last_received
        if silence <= silence_limit_us:
            return []
        self.epoch = None
        return self._mark_all(stop_sent_us,
                              f"SEGMENT_TAIL_LOST: nothing arrived for {silence / 1e6:.3f} s before the stop was sent; "
                              "samples taken in that time were never delivered and their number is unknown")

    def link_lost(self, now_us: int, detail: str) -> list[Gap]:
        """The serial link failed: one marked discontinuity per stream that has delivered, and a new epoch later."""
        if self.broken or self.epoch is None:
            self.epoch = None
            return []
        self.broken = True
        self.epoch = None
        return self._mark_all(now_us, f"LINK_LOST: {detail}; samples taken while the link was down were never "
                                      "delivered and their number is unknown")

    # ------------------------------------------------------------ input
    def packets(self, packets: list[Packet], received_us: int) -> list:
        """One read's packets, received together at received_us (host clock)."""
        out: list = []
        accepted: list[tuple[Packet, int]] = []
        for packet in packets:
            self.packet_types[packet.type_name] += 1
            index = self._place(packet, received_us, out)
            if index is not None:
                accepted.append((packet, index))
                self.epoch.clock.add(index, received_us)
        if accepted:
            out += self._emit(accepted, received_us)
        return out

    def _place(self, packet: Packet, received_us: int, out: list) -> int | None:
        """The packet's unwrapped sample index in the current epoch, declaring what was lost before it."""
        epoch = self.epoch
        pending = self._pending_start
        if epoch is None:
            if pending is not None:
                epoch = self._new_epoch(0)
                self._pending_start = None
                epoch.last_index, epoch.last_counter, epoch.last_received = -1, WRAP - 1, pending
            else:
                epoch = self._new_epoch(packet.counter)
                return self._accept(epoch, packet, packet.counter, received_us)
        delta = (packet.counter - epoch.last_counter) % WRAP
        if delta == 0 and epoch.last_index >= 0 and packet.raw == epoch.last_raw:
            self.duplicates += 1
            return None
        candidates = self._feasible_jumps(epoch, delta or WRAP, received_us)
        if delta == 0 and epoch.last_index >= 0 and not candidates:
            # The same counter, different contents, and too soon for a full wrap: a conflicting copy.
            self.faults.append((EXG_STREAM, "CONFLICTING_RETRANSMISSION",
                                f"counter {packet.counter} arrived again with different contents; the copy is refused",
                                received_us))
            return None
        if len(candidates) != 1:
            silence = (received_us - epoch.last_received) / 1e6
            reason = ("no count of lost samples fits the receipt time" if not candidates
                      else f"{len(candidates)} counts of lost samples fit the receipt time")
            out += self._mark_all(received_us,
                                  f"COUNTER_AMBIGUOUS: counter went {epoch.last_counter} -> {packet.counter} over "
                                  f"{silence:.3f} s and {reason}; the number of samples lost (possibly none) is unknown")
            epoch = self._new_epoch(packet.counter)
            return self._accept(epoch, packet, packet.counter, received_us)
        jump = candidates[0]
        index = epoch.last_index + jump
        if jump > 1:
            first_lost, last_lost = epoch.last_index + 1, index - 1
            self.lost_packets += last_lost - first_lost + 1
            start = epoch.last_index < 0
            kind = "CYTON_SEGMENT_START_LOST" if start else "CYTON_COUNTER_DISCONTINUITY"
            how = ("the counter restarts at 0 on 'b'" if start else
                   f"counter went {epoch.last_counter} -> {packet.counter}")
            wraps = (jump - 1) // WRAP
            by_clock = f"; {wraps} full counter wrap(s) resolved by the sample clock" if wraps else ""
            for stream in self.packet_streams:
                slots = [self._slot(stream, i) for i in range(first_lost, last_lost + 1) if self._owns(stream, i)]
                if not slots:
                    continue
                gap = Gap(stream, epoch.base[stream] + slots[0], epoch.base[stream] + slots[-1], received_us,
                          f"{kind}: {how}; ADC samples {first_lost}..{last_lost} of epoch {epoch.number} "
                          f"({len(slots)} rows of this stream) never arrived{by_clock}")
                out.append(gap)
                self.next_sequence[stream] = gap.last_sequence + 1
            if ACCEL_STREAM in self.columns and self.delivered[ACCEL_STREAM]:
                n = last_lost - first_lost + 1
                out.append(self._mark(ACCEL_STREAM, received_us,
                                      f"ACCEL_LOSS_UNKNOWN: {n} packet(s) were lost; the 25 Hz accelerometer readings "
                                      f"they may have carried (about {n / 10:.1f}, possibly none) cannot be counted"))
        return self._accept(epoch, packet, index, received_us)

    def _feasible_jumps(self, epoch: _Epoch, delta: int, received_us: int) -> list[int]:
        """Counts of samples since the last packet consistent with the counter, the oscillator, and the latency bound."""
        if epoch.last_index < 0:
            # Segment start: the ADC began after 'b' was sent at epoch.last_received.
            elapsed = received_us - epoch.last_received
            most = int(elapsed / (p.NOMINAL_PERIOD_US * (1 - p.OSCILLATOR_TOLERANCE_FULL))) + 1
            return list(range(delta, most + 1, WRAP))[:2]
        line = epoch.clock.line()
        anchor = float(line.at(epoch.last_index)) if line is not None else float(epoch.last_received)
        pmin = p.NOMINAL_PERIOD_US * (1 - p.OSCILLATOR_TOLERANCE_FULL)
        pmax = p.NOMINAL_PERIOD_US * (1 + p.OSCILLATOR_TOLERANCE_FULL)
        margin = MAPPING_MARGIN_US
        out = []
        jump = delta
        while True:
            earliest_taken = anchor + jump * pmin
            latest_taken = anchor + jump * pmax
            if earliest_taken > received_us + margin:
                break                                        # taken after it was received: impossible from here on
            if latest_taken >= received_us - self.latency_bound_us:
                out.append(jump)
            jump += WRAP
            if len(out) > 1:
                break
        return out

    def _accept(self, epoch: _Epoch, packet: Packet, index: int, received_us: int) -> int:
        epoch.last_index, epoch.last_counter, epoch.last_received, epoch.last_raw = index, packet.counter, received_us, \
            packet.raw
        self.broken = False
        return index

    # ----------------------------------------------------------- output
    def _emit(self, accepted: list[tuple[Packet, int]], received_us: int) -> list:
        epoch = self.epoch
        line = epoch.clock.line()
        packets = [pk for pk, _ in accepted]
        index = np.array([i for _, i in accepted], dtype=np.int64)
        counters = np.array([pk.counter for pk in packets], dtype=np.int64)
        codes = channel_matrix(packets)
        received = np.full(len(packets), received_us, dtype=np.int64)
        drdy = np.asarray(line.at(index), dtype=np.float64)
        out: list = []

        def chunk(stream: str, mask: np.ndarray, columns: dict[str, np.ndarray], when: np.ndarray) -> None:
            if not np.any(mask):
                return
            idx = index[mask]
            seq = np.array([epoch.base[stream] + self._slot(stream, int(i)) for i in idx], dtype=np.int64) \
                if stream in epoch.base else None
            if seq is None:
                n = int(np.sum(mask))
                seq = np.arange(self.next_sequence[stream], self.next_sequence[stream] + n, dtype=np.int64)
            t = self.stamp(stream, when[mask])
            avail = np.maximum(t, received[mask])
            cols = {c: np.asarray(v)[mask].astype(np.int64) for c, v in columns.items()}
            cols.update({"epoch": np.full(int(np.sum(mask)), epoch.number, dtype=np.int64), "sample_index": idx})
            if "counter" in self.columns[stream]:
                cols["counter"] = counters[mask]
            out.append(StreamChunk(stream, seq, t, avail, cols))
            self.next_sequence[stream] = int(seq[-1]) + 1
            self.delivered[stream] += len(seq)

        half = 0.5 if self.layout.daisy else 0.0
        sample_time = drdy - half * line.slope_us
        if self.layout.daisy:
            board = index % 2 == 1
            chunk(EXG_STREAM, board, {f"ch{i + 1}": codes[:, i] for i in range(8)}, sample_time)
            daisy = ~board
            chunk(DAISY_STREAM, daisy, {f"ch{i + 9}": codes[:, i] for i in range(8)}, sample_time)
            if epoch.restarted_daisy and np.any(daisy & (index == 0)):
                self.faults.append((DAISY_STREAM, "STALE_AVERAGE_AT_ADC_START",
                                    f"daisy row for sample 0 of epoch {epoch.number} averages a value left from before "
                                    "the ADC started (updateDaisyData after firstDataPacket); kept as sent", received_us))
            epoch.restarted_daisy = False
        else:
            chunk(EXG_STREAM, np.ones(len(index), dtype=bool), {f"ch{i + 1}": codes[:, i] for i in range(8)}, sample_time)

        types = np.array([pk.packet_type for pk in packets])
        words = np.array([pk.aux_words() for pk in packets], dtype=np.int64).reshape(-1, 3)
        if ACCEL_STREAM in self.columns:
            has = (types == p.PACKET_ACCEL) & np.any(words != 0, axis=1)
            chunk(ACCEL_STREAM, has, {"ax_lsb": words[:, 0], "ay_lsb": words[:, 1], "az_lsb": words[:, 2]}, drdy)
        if AUX_STREAM in self.columns:
            raw_aux = types == p.PACKET_RAW_AUX
            # Every packet carries the pins in these modes; a packet of another type leaves its row undeclared.
            if self.layout.board_mode == "analog":
                chunk(AUX_STREAM, raw_aux, dict(zip(p.ANALOG_PINS, words.T)), drdy)
            else:
                w = words & 0xFFFF
                chunk(AUX_STREAM, raw_aux, {"d11": (w[:, 0] >> 8) & 1, "d12": w[:, 0] & 1, "d13": (w[:, 1] >> 8) & 1,
                                            "d17": w[:, 1] & 1, "d18": w[:, 2] & 1}, drdy)
        stamped = int(np.sum(np.isin(types, p.TIME_STAMPED_TYPES) | (types == p.PACKET_USER_DEFINED) | (types > 6)))
        if stamped and not epoch.flagged_types:
            epoch.flagged_types = True
            self.faults.append((EXG_STREAM, "UNEXPECTED_PACKET_TYPE",
                                f"packets of types {sorted({pk.type_name for pk in packets})} in board mode "
                                f"{self.layout.board_mode} (first seen in epoch {epoch.number}); channels kept, aux "
                                "words not interpreted", received_us))
        if self.layout.board_mode == "marker":
            for k in np.flatnonzero((types == p.PACKET_RAW_AUX) & (words[:, 0] != 0)):
                t = int(self.stamp(MARKER_STREAM, drdy[k:k + 1])[0])
                out.append(DeviceEvent(MARKER_STREAM, self.marker_sequence, "MARKER_IN_DATA", t,
                                       (("code", float(words[k, 0])), ("epoch", float(epoch.number)),
                                        ("sample_index", float(index[k])))))
                self.marker_sequence += 1
        return out
