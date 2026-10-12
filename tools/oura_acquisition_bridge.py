"""Live acquisition bridge: an Oura ring over Bluetooth LE, through CIRCLE's ingestion boundary.

  scan        list Oura rings advertising nearby (needs bleak)
  record      connect to a ring, stream live heart beats (IBI) and accelerometer
              frames through models/acquisition (Ingestor via pump(), LinkMonitor),
              and write a contract-valid session (needs bleak, the ring's auth key,
              and --wearer-consents)
  self-test   run the decoders against open_oura's known vectors and a scripted,
              damaged synthetic session through the same boundary and exporter;
              needs no ring and no bleak

What the ring sends live, and how it is decoded. The protocol is taken from
open_oura (github.com/Th0rgal/open_oura, commit e57c43c, MIT), which was
verified against a Ring 3 Horizon and a Ring 5. Every frame is `tag | length |
payload`, little-endian, with extended operations under tag 0x2f.

  auth        2f 01 2b -> 2f 10 2c <15-byte nonce>; reply 2f 11 2d
              AES-128-ECB(key, PKCS7(nonce)) -> 2f 02 2e <state> (0 = success).
              Repeated on every connection. The 16-byte key is the one the Oura
              app installed when it onboarded the ring; this tool never sets one.
  live HR     2f 03 22 02 03 (SetFeatureMode DAYTIME_HR, CONNECTED_LIVE). The ring
              then pushes one frame per beat:
              2f len 28 <feature> <status> <state> <time_since u16> <IBI u16>,
              IBI word = 12-bit interval in ms | 4-bit validity << 12 (1 = VALID).
              Restored on exit to the mode read before (2f 02 20 02).
  motion      06 07 <bitmask u32 = 0x20 ACM> <minutes u16> <delay u8>, time-boxed so
              the ring stops by itself; 06 04 00000000 stops it. Frames:
              33 len <rate Hz> <counter u8> x y z [x y z], each axis int16.
  HRV         not a live channel. The ring's own 5-minute HRV (hrv_event 0x5d)
              arrives only through history sync. Here HRV is RMSSD of successive
              valid live IBIs (open_oura's port of the app's ecore hrv), recorded as
              MODEL_INFERRED windows with exact source sequence ranges.

How the session keeps CIRCLE's evidence rules.

  boundary    every decoded piece goes through models.acquisition.live.pump() into
              an Ingestor with host-receipt availability, exactly as the twin's
              simulated link does: malformed pieces are refused as faults, overflow
              is declared lost, silence becomes LINK events.
  timing      the ring's live frames carry no clock. Times are microseconds on the
              host's monotonic clock from the start of the attempt
              (TIMEBASE:HOST_MONOTONIC). available_us is when the host received a
              frame; a beat's sample time is its receipt; an accelerometer sample's
              time is its receipt minus the ring's stated sample period for each
              later sample in the frame. Times only ever increase, and a sample is
              never available before it was taken. The ring's own counters
              (time_since, frame counter) are kept as raw columns.
  gaps        every loss is an exact GAP over the stream's sequence numbers:
                RING_FRAME_COUNTER_DISCONTINUITY  the 8-bit ACM frame counter jumped;
                                                  the missing frames' sample slots
                RING_FRAME_SHORT / _UNDECODABLE   a frame carried fewer samples than
                                                  its slots, or none readable
                RING_PACKET_UNDECODABLE           a beat frame arrived but cannot
                                                  be read; its slot
                LINK_LOST / COUNTER_AMBIGUOUS /   the link dropped, the ring was
                ACM_REARMED / RATE_INCONSISTENT   re-armed, or the counter cannot
                                                  resolve the silence or disagrees
                                                  with the stated rate: one marked
                                                  discontinuity whose size the cause
                                                  states is unknown (never invented)
                HOST_QUEUE_FULL, UNDECLARED_...   from the boundary itself
  minimized   only beats and accelerometer frames are kept. Every other
              notification is counted by type and discarded. No serial number, MAC
              address, or key is stored or printed; the firmware response's MAC
              bytes are never parsed. Output is written owner-only (0700/0600).
  closed loop the ring supplies no EDA, PPG counts, gyroscope, or lab sync stream,
              so the input contract (models/physiology/loop.py) cannot be met. The
              session records why as FAULTs (CLOSED_LOOP_NOT_ELIGIBLE); nothing is
              imputed, and nothing here actuates anything.

Everything stays on this computer: bleak talks to the local Bluetooth adapter and
nothing here opens a network connection or uses an Oura account.

Before recording: close the Oura app or turn off the phone's Bluetooth (the ring
holds one connection at a time), install bleak (`pip install bleak`), and put the
ring's 16-byte auth key in a file as 32 hex characters. On Linux the ring may need
pairing first (`bluetoothctl pair <address>`, or --pair).

  python tools/oura_acquisition_bridge.py self-test
  python tools/oura_acquisition_bridge.py scan
  python tools/oura_acquisition_bridge.py record --key-file ~/.oura/ring.key --wearer-consents --seconds 300
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, deque
from dataclasses import dataclass, field
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import time
from typing import Any, AsyncIterator, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.acquisition.ingest import Ingestor, LinkMonitor, StreamChunk
from models.acquisition.live import Piece, pump
from models.physiology.controller import CONTROLLER_VERSION, ControllerConfig
from models.physiology.evidence import EVENT_KIND_FLAG, SCHEMA_VERSION, dumps, software_revision
from models.physiology.ledger import passport, passport_text
from models.physiology.loop import Capabilities, SignalCapability, capability_problems
from models.physiology.streams import DeviceEvent, Gap, RawSession, Stream
from models.session_records import load_session, seal_record, validate_session

PROTOCOL_REFERENCE = "open_oura e57c43ce5fe0cf9a646afa790bda3731be767507 (github.com/Th0rgal/open_oura, MIT)"
BRIDGE_VERSION = "1.0.0"

# ------------------------------------------------------------------ protocol
OURA_SERVICE = "98ed0001-a541-11e4-b6a0-0002a5d5c51b"
OURA_WRITE = "98ed0002-a541-11e4-b6a0-0002a5d5c51b"
OURA_NOTIFY = "98ed0003-a541-11e4-b6a0-0002a5d5c51b"

TAG_EXT = 0x2F
EXT_AUTH_NONCE_REQUEST, EXT_AUTH_NONCE, EXT_AUTHENTICATE, EXT_AUTH_RESULT = 0x2B, 0x2C, 0x2D, 0x2E
EXT_FEATURE_STATUS_REQUEST, EXT_FEATURE_STATUS = 0x20, 0x21
EXT_SET_FEATURE_MODE, EXT_SET_FEATURE_MODE_RESULT = 0x22, 0x23
EXT_LIVE_INDICATION = 0x28
FEATURE_DAYTIME_HR = 0x02
MODE_AUTOMATIC, MODE_CONNECTED_LIVE = 0x01, 0x03
TAG_REALTIME, TAG_REALTIME_RESULT, TAG_ACM = 0x06, 0x07, 0x33
REALTIME_ACM = 0x20
REQUEST_FIRMWARE = bytes.fromhex("0803000000")      # answered by tag 0x09
REQUEST_HARDWARE_ID = bytes.fromhex("1803180010")   # answered by tag 0x19, e.g. "BLB_03"
AUTH_RESULTS = {0x00: "SUCCESS", 0x01: "AUTHENTICATION_ERROR", 0x02: "IN_FACTORY_RESET",
                0x03: "NOT_ORIGINAL_ONBOARDED_DEVICE"}


@dataclass(frozen=True)
class Packet:
    tag: int
    payload: bytes

    @property
    def ext(self) -> int | None:
        return self.payload[0] if self.tag == TAG_EXT and self.payload else None

    @property
    def label(self) -> str:
        return f"0x{self.tag:02x}" + (f"/0x{self.ext:02x}" if self.ext is not None else "")


def packet(tag: int, payload: bytes = b"") -> bytes:
    if len(payload) > 255:
        raise ValueError("payload too long for one Oura packet")
    return bytes([tag, len(payload)]) + payload


def parse_packets(frame: bytes) -> list[Packet]:
    """Every complete packet concatenated in one notification (open_oura Packet::parse_many)."""
    out, i = [], 0
    while i + 2 <= len(frame):
        end = i + 2 + frame[i + 1]
        if end > len(frame):
            break
        out.append(Packet(frame[i], frame[i + 2:end]))
        i = end
    if not out and len(frame) >= 2:
        out.append(Packet(frame[0], frame[2:2 + frame[1]]))
    return out


def request_auth_nonce() -> bytes:
    return packet(TAG_EXT, bytes([EXT_AUTH_NONCE_REQUEST]))


def request_authenticate(encrypted: bytes) -> bytes:
    return packet(TAG_EXT, bytes([EXT_AUTHENTICATE]) + encrypted)


def request_feature_status(feature: int) -> bytes:
    return packet(TAG_EXT, bytes([EXT_FEATURE_STATUS_REQUEST, feature]))


def request_set_feature_mode(feature: int, mode: int) -> bytes:
    return packet(TAG_EXT, bytes([EXT_SET_FEATURE_MODE, feature, mode]))


def request_realtime(bitmask: int, minutes: int, delay: int = 0) -> bytes:
    """Time-boxed real-time measurement: the ring stops by itself after `minutes`."""
    return packet(TAG_REALTIME, struct.pack("<IHB", bitmask, minutes, delay))


def request_realtime_off() -> bytes:
    return packet(TAG_REALTIME, bytes(4))


def encrypt_nonce(key: bytes, nonce: bytes) -> bytes:
    """AES-128/ECB over the PKCS7-padded nonce, one block (open_oura auth::encrypt_nonce)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if len(key) != 16:
        raise ValueError("the ring's auth key is 16 bytes")
    body = nonce[:16]
    block = body + bytes([16 - len(body)]) * (16 - len(body))
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(block) + encryptor.finalize()


# ------------------------------------------------------------------ decoders
@dataclass(frozen=True)
class LiveBeat:
    """One live-HR indication: [0]=2f [2]=28 [3]=feature [4]=status [5]=state [6:8]=time_since [8:10]=IBI word."""

    feature: int
    time_since_raw: int
    ibi_ms: int
    validity: int

    @property
    def bpm(self) -> float | None:
        return 60_000.0 / self.ibi_ms if self.validity == 1 and IBI_PLAUSIBLE_MS[0] <= self.ibi_ms <= IBI_PLAUSIBLE_MS[1] \
            else None


@dataclass(frozen=True)
class AcmFrame:
    """One accelerometer frame: [0]=33 [2]=sample rate (Hz) [3]=frame counter [4:10] [10:16] = x,y,z int16."""

    rate_hz: int
    counter: int
    samples: tuple[tuple[int, int, int], ...]


IBI_PLAUSIBLE_MS = (300, 2000)


def is_live_beat_frame(frame: bytes) -> bool:
    return len(frame) >= 3 and frame[0] == TAG_EXT and frame[2] == EXT_LIVE_INDICATION


def decode_live_beat(frame: bytes) -> LiveBeat | None:
    """open_oura parse_live_hr_frame, keeping invalid beats and the raw validity nibble."""
    if len(frame) < 10 or not is_live_beat_frame(frame):
        return None
    word = int.from_bytes(frame[8:10], "little")
    return LiveBeat(frame[3], int.from_bytes(frame[6:8], "little"), word & 0x0FFF, word >> 12)


def decode_acm_frame(frame: bytes) -> AcmFrame | None:
    """open_oura parse_acm_frame: decoded over the whole notification; the declared length is not trusted."""
    if len(frame) < 4 or frame[0] != TAG_ACM:
        return None
    samples = tuple(struct.unpack_from("<hhh", frame, offset) for offset in (4, 10) if len(frame) >= offset + 6)
    return AcmFrame(frame[2], frame[3], samples)


def rmssd_ms(ibi_ms: np.ndarray) -> float:
    """Root mean square of successive differences (open_oura analysis::hrv::rmssd)."""
    return float(np.sqrt(np.mean(np.diff(np.asarray(ibi_ms, dtype=np.float64)) ** 2)))


# ------------------------------------------------------------- CIRCLE streams
IBI_STREAM, ACM_STREAM, CONTROL_STREAM = "oura_ibi", "oura_acm", "oura_control"
STREAM_COLUMNS = {IBI_STREAM: ("ibi_ms", "validity", "time_since_raw"),
                  ACM_STREAM: ("ax_lsb", "ay_lsb", "az_lsb", "frame_counter")}
DESCRIPTORS = {IBI_STREAM: {"ibi_lsb_ms": 1.0, "ibi_bits": 12.0, "validity_valid_code": 1.0},
               ACM_STREAM: {"nominal_rate_hz": 50.0, "slots_per_frame": 2.0, "frame_counter_modulus": 256.0}}
DESCRIPTOR_FLAGS = {
    IBI_STREAM: ["SEQUENCE:HOST_NOTIFICATION_COUNT", "SAMPLE_TIME:HOST_RECEIPT", "ONE_ROW_PER_BEAT_NOTIFICATION",
                 "INVALID_BEATS_KEPT_WITH_VALIDITY"],
    ACM_STREAM: ["SEQUENCE:RING_FRAME_COUNTER_TIMES_SLOTS_PLUS_SLOT", "SAMPLE_TIME:RECEIPT_MINUS_STATED_PERIOD",
                 "SCALE:LSB_PER_G_NOT_PUBLISHED", "ACCELEROMETER_ONLY_NO_GYROSCOPE"],
}
ACM_SLOTS = 2
ACM_BOX_MINUTES = 10              # the ring stops ACM by itself after this, even if the host dies
LATENCY_BOUND_US = 2_000_000      # longest a frame is assumed to wait between sampling and receipt
MAX_STALE_RUN = 2                 # late-looking frames refused in a row before the stated rate is distrusted


class RingStreams:
    """Ring notifications in, CIRCLE pieces out: sample chunks and exact GAPs. No I/O, no clock.

    IBI sequences count beat notifications (the ring numbers none). ACM sequences
    are frame index * 2 + slot, where the frame index follows the ring's 8-bit
    frame counter; a run of counter continuity is an epoch, and anything that
    breaks one (a dropped link, a re-arm the counter did not survive, a silence
    longer than the counter can resolve) is one marked discontinuity.
    """

    def __init__(self, hr: bool = True, acm: bool = True) -> None:
        self.enabled = {IBI_STREAM: hr, ACM_STREAM: acm}
        self.next_beat = 0
        self.next_frame = 0
        self.last_time = {IBI_STREAM: -1, ACM_STREAM: -1}
        self.delivered = {IBI_STREAM: 0, ACM_STREAM: 0}
        self.acm_last: tuple[int, int, int, bytes] | None = None   # frame index, counter, received, raw
        self.acm_rate_hz: float | None = None
        self.rearm_pending = False
        self.stale_run = 0
        self.broken = {IBI_STREAM: False, ACM_STREAM: False}
        self.faults: list[tuple[str, str, str, int]] = []
        self.ignored: Counter[str] = Counter()
        self.duplicate_frames = 0
        self.recent_ibi: deque[tuple[int, int]] = deque(maxlen=31)   # (sequence, ibi_ms) of valid beats

    # ------------------------------------------------------------ input
    def notification(self, frame: bytes, received_us: int) -> list[Piece]:
        if frame[:1] == bytes([TAG_ACM]):
            return self._acm(frame, received_us) if self.enabled[ACM_STREAM] else self._ignore(frame)
        if is_live_beat_frame(frame) and (len(frame) < 4 or frame[3] == FEATURE_DAYTIME_HR):
            return self._beat(frame, received_us) if self.enabled[IBI_STREAM] else self._ignore(frame)
        return self._ignore(frame)

    def link_lost(self, now_us: int, detail: str) -> list[Piece]:
        """The link dropped: one marked discontinuity per stream that has delivered and is not already broken."""
        out: list[Piece] = []
        for name in (IBI_STREAM, ACM_STREAM):
            if self.enabled[name] and self.delivered[name] and not self.broken[name]:
                out.append(self._mark(name, now_us, f"LINK_LOST: {detail}; samples taken while the link was down "
                                                    "were never delivered and their number is unknown"))
        return out

    def acm_rearmed(self) -> None:
        self.rearm_pending = True

    # ------------------------------------------------------------ helpers
    def _ignore(self, frame: bytes) -> list[Piece]:
        for p in parse_packets(frame) or [Packet(frame[0] if frame else 0, b"")]:
            self.ignored[p.label] += 1
        return []

    def _fault(self, stream: str, kind: str, detail: str, received_us: int) -> None:
        self.faults.append((stream, kind, detail, received_us))

    def _stamp(self, stream: str, estimate_us: int) -> int:
        t = max(int(estimate_us), self.last_time[stream] + 1, 0)
        self.last_time[stream] = t
        return t

    def _mark(self, name: str, at_us: int, cause: str) -> Gap:
        """Reserve fresh sequence numbers for a discontinuity of unknown size (one beat slot, or one frame's slots)."""
        self.broken[name] = True
        if name == IBI_STREAM:
            first = last = self.next_beat
            self.next_beat += 1
        else:
            first, last = self.next_frame * ACM_SLOTS, self.next_frame * ACM_SLOTS + ACM_SLOTS - 1
            self.next_frame += 1
            self.acm_last = None
        return Gap(name, first, last, at_us, cause)

    def _beat(self, frame: bytes, received_us: int) -> list[Piece]:
        sequence = self.next_beat
        self.next_beat += 1
        self.broken[IBI_STREAM] = False
        beat = decode_live_beat(frame)
        if beat is None:
            detail = f"live HR notification {sequence} has {len(frame)} bytes; a readable one has 10"
            self._fault(IBI_STREAM, "UNDECODABLE_PACKET", detail, received_us)
            return [Gap(IBI_STREAM, sequence, sequence, received_us,
                        f"RING_PACKET_UNDECODABLE: {detail}; its beat is declared lost")]
        t = self._stamp(IBI_STREAM, received_us)
        self.delivered[IBI_STREAM] += 1
        if beat.bpm is not None:
            self.recent_ibi.append((sequence, beat.ibi_ms))
        return [StreamChunk(IBI_STREAM, np.array([sequence]), np.array([t]), np.array([max(received_us, t)]),
                            {"ibi_ms": np.array([beat.ibi_ms]), "validity": np.array([beat.validity]),
                             "time_since_raw": np.array([beat.time_since_raw])})]

    def _acm(self, frame: bytes, received_us: int) -> list[Piece]:
        decoded = decode_acm_frame(frame)
        if decoded is None:
            self._fault(ACM_STREAM, "UNDECODABLE_PACKET", f"ACM notification of {len(frame)} bytes has no frame counter",
                        received_us)
            return []
        rate = float(decoded.rate_hz or DESCRIPTORS[ACM_STREAM]["nominal_rate_hz"])
        if self.acm_rate_hz is None:
            self.acm_rate_hz = rate
        elif rate != self.acm_rate_hz:
            self._fault(ACM_STREAM, "RATE_CHANGED", f"frame states {rate:g} Hz; the session began at {self.acm_rate_hz:g} Hz",
                        received_us)
        period_us = 1e6 / rate
        out: list[Piece] = []
        if self.acm_last is None:
            index = self.next_frame
        else:
            last_index, last_counter, last_received, last_raw = self.acm_last
            delta = (decoded.counter - last_counter) % 256
            # Frames sampled between the two receipts cannot exceed the elapsed time plus the latency bound.
            reach = (received_us - last_received + LATENCY_BOUND_US) / (ACM_SLOTS * period_us)
            if reach >= 256:
                silence_s = (received_us - last_received) / 1e6
                out.append(self._mark(ACM_STREAM, received_us,
                                      f"COUNTER_AMBIGUOUS: {silence_s:.1f} s without an ACM frame is more than the 8-bit "
                                      "frame counter can resolve; the number of frames lost (possibly none) is unknown"))
                index = self.next_frame
            elif delta == 0:
                if frame == last_raw:
                    self.duplicate_frames += 1
                    return []
                self._fault(ACM_STREAM, "CONFLICTING_RETRANSMISSION",
                            f"frame counter {decoded.counter} arrived again with different contents; the copy is refused",
                            received_us)
                return []
            elif self.rearm_pending and delta != 1:
                out.append(self._mark(ACM_STREAM, received_us,
                                      f"ACM_REARMED: after the time box was renewed the frame counter went {last_counter} -> "
                                      f"{decoded.counter}; the ring restarted it or frames were lost, which cannot be told "
                                      "apart, so the number lost is unknown"))
                index = self.next_frame
            elif delta > reach and self.stale_run < MAX_STALE_RUN:
                self.stale_run += 1
                self._fault(ACM_STREAM, "STALE_FRAME",
                            f"frame counter {decoded.counter} after {last_counter} would mean {delta - 1} frames sampled in "
                            f"{(received_us - last_received) / 1e3:.0f} ms; an old frame arriving late is refused",
                            received_us)
                return []
            elif delta > reach:
                # Frames keep outrunning the stated rate: the rate, not the frames, is wrong. Trust the counter afresh.
                out.append(self._mark(ACM_STREAM, received_us,
                                      f"RATE_INCONSISTENT: {MAX_STALE_RUN + 1} frames in a row advanced the counter faster "
                                      f"than the stated {rate:g} Hz allows; the number of frames lost is unknown"))
                index = self.next_frame
            else:
                index = last_index + delta
                if delta > 1:
                    out.append(Gap(ACM_STREAM, (last_index + 1) * ACM_SLOTS, index * ACM_SLOTS - 1, received_us,
                                   f"RING_FRAME_COUNTER_DISCONTINUITY: ACM frame counter went {last_counter} -> "
                                   f"{decoded.counter}; {delta - 1} frame(s), {(delta - 1) * ACM_SLOTS} sample slots, "
                                   "never arrived"))
        self.rearm_pending = False
        self.stale_run = 0
        self.broken[ACM_STREAM] = False
        self.acm_last = (index, decoded.counter, received_us, frame)
        self.next_frame = index + 1
        n = len(decoded.samples)
        if n:
            times = [self._stamp(ACM_STREAM, round(received_us - (n - 1 - k) * period_us)) for k in range(n)]
            xyz = np.array(decoded.samples, dtype=np.int64)
            self.delivered[ACM_STREAM] += n
            out.append(StreamChunk(ACM_STREAM, np.arange(n) + index * ACM_SLOTS, np.array(times),
                                   np.maximum(received_us, np.array(times)),
                                   {"ax_lsb": xyz[:, 0], "ay_lsb": xyz[:, 1], "az_lsb": xyz[:, 2],
                                    "frame_counter": np.full(n, decoded.counter)}))
        if n < ACM_SLOTS:
            kind = "RING_FRAME_SHORT" if n else "RING_FRAME_UNDECODABLE"
            detail = f"ACM frame (counter {decoded.counter}, {len(frame)} bytes) carried {n} of {ACM_SLOTS} samples"
            if not n:
                self._fault(ACM_STREAM, "UNDECODABLE_PACKET", detail, received_us)
            out.append(Gap(ACM_STREAM, index * ACM_SLOTS + n, index * ACM_SLOTS + ACM_SLOTS - 1, received_us,
                           f"{kind}: {detail}; the empty slots are declared"))
        return out

    def rolling_rmssd(self) -> float | None:
        """RMSSD over the recent run of consecutive valid beats (display only)."""
        run: list[int] = []
        previous: int | None = None
        for sequence, ibi in self.recent_ibi:
            run = run + [ibi] if previous is not None and sequence == previous + 1 else [ibi]
            previous = sequence
        return rmssd_ms(np.array(run)) if len(run) >= 3 else None


# ------------------------------------------------------------- bridge core
_CLOSE = object()


class BridgeCore:
    """Shared by the live bridge and the self-test: pieces queued for pump(), link health, control events."""

    def __init__(self, hr: bool, acm: bool, stale_after_s: float, disconnected_after_s: float,
                 inbox_limit: int = 4096, capacity: int = 4_000_000) -> None:
        names = [n for n, on in ((IBI_STREAM, hr), (ACM_STREAM, acm)) if on]
        if not names:
            raise ValueError("enable at least one stream")
        self.streams = RingStreams(hr, acm)
        self.ingestor = Ingestor({n: dict(DESCRIPTORS[n]) for n in names}, {n: STREAM_COLUMNS[n] for n in names},
                                 capacity, stamp_host_availability=True)
        self.monitor = LinkMonitor(int(stale_after_s * 1e6), int(disconnected_after_s * 1e6))
        self.inbox: asyncio.Queue = asyncio.Queue(maxsize=inbox_limit)
        self.control_sequence = 0
        self.inbox_overflow = 0
        self.closed = False

    def emit(self, received_us: int, piece: Piece) -> None:
        if self.closed:
            return  # the session has ended; what follows is teardown, not acquisition
        try:
            self.inbox.put_nowait((received_us, piece))
        except asyncio.QueueFull:
            # The event loop fell behind the radio: declare the chunk lost now, exactly, as pump() does.
            self.inbox_overflow += 1
            if isinstance(piece, StreamChunk):
                self.ingestor.deliver_gap(Gap(piece.stream_id, int(piece.sequence[0]), int(piece.sequence[-1]), received_us,
                                              "HOST_QUEUE_FULL: the bridge inbox was full; chunk dropped"), received_us)
            else:
                self.ingestor.flag(getattr(piece, "stream_id", CONTROL_STREAM), "DROPPED_AT_QUEUE",
                                   f"{type(piece).__name__} dropped: the bridge inbox was full", received_us)

    def notification(self, frame: bytes, received_us: int) -> None:
        if self.closed or not frame:
            return
        pieces = self.streams.notification(frame, received_us)
        if any(isinstance(p, StreamChunk) for p in pieces):
            for event in self.monitor.delivered(received_us):
                self.emit(received_us, event)
        for piece in pieces:
            self.emit(received_us, piece)
        self._drain_faults()

    def link_lost(self, now_us: int, detail: str, code: float = 0.0) -> None:
        for event in self.monitor.failed(now_us, code):
            self.emit(now_us, event)
        for gap in self.streams.link_lost(now_us, detail):
            self.emit(now_us, gap)

    def tick(self, now_us: int) -> None:
        for event in self.monitor.tick(now_us):
            self.emit(now_us, event)

    def control(self, kind: str, now_us: int, **attributes: float) -> None:
        """A ring-control observation (connect, auth, stream on/off, restore): never physiological."""
        event = DeviceEvent(CONTROL_STREAM, self.control_sequence, kind, int(now_us),
                            tuple(sorted((k, float(v)) for k, v in attributes.items())))
        self.control_sequence += 1
        self.emit(now_us, event)

    def _drain_faults(self) -> None:
        for stream, kind, detail, received in self.streams.faults:
            self.ingestor.flag(stream, kind, detail, received)
        self.streams.faults.clear()

    async def pieces(self) -> AsyncIterator[tuple[int, Piece]]:
        while True:
            item = await self.inbox.get()
            if item is _CLOSE:
                return
            yield item

    async def close(self) -> None:
        self._drain_faults()
        self.closed = True
        await self.inbox.put(_CLOSE)


# ------------------------------------------------------------------ export
def _record(record_type: str, provenance: str, t0: int, t1: int, flags: list[str], **fields: Any) -> dict[str, Any]:
    record = {"schema_version": SCHEMA_VERSION, "record_type": record_type, "provenance": provenance,
              "device_time_start_us": int(t0), "device_time_end_us": int(max(t0, t1)),
              "status_flags": list(dict.fromkeys(flags)), "crc32c": "00000000"}
    record.update({k: v for k, v in fields.items() if v is not None})
    return record


def _csv_bytes(stream: Stream, columns: tuple[str, ...]) -> bytes:
    matrix = np.column_stack([stream.sequence, stream.device_time_us, stream.available_us,
                              *[stream.columns[c] for c in columns]]).astype(np.int64)
    buffer = io.StringIO()
    buffer.write(",".join(["sequence", "device_time_us", "available_us", *columns]) + "\n")
    np.savetxt(buffer, matrix, fmt="%d", delimiter=",")
    return buffer.getvalue().encode("ascii")


def _ranges(name: str, sequences: np.ndarray) -> list[dict[str, Any]]:
    values = np.unique(np.asarray(sequences, dtype=np.int64))
    breaks = np.flatnonzero(np.diff(values) != 1) + 1
    return [{"stream_id": name, "first_sequence": int(run[0]), "last_sequence": int(run[-1])}
            for run in np.split(values, breaks) if len(run)]


def hrv_windows(stream: Stream, window_s: float = 60.0, min_pairs: int = 20) -> list[dict[str, Any]]:
    """RMSSD per window over successive valid beats; a pair never spans a gap, an invalid beat, or a missed sequence."""
    if len(stream) < 2:
        return []
    seq, t = stream.sequence, stream.device_time_us
    ibi = stream.columns["ibi_ms"]
    valid = (stream.columns["validity"] == 1) & (ibi >= IBI_PLAUSIBLE_MS[0]) & (ibi <= IBI_PLAUSIBLE_MS[1])
    pair = valid[:-1] & valid[1:] & (np.diff(seq) == 1)
    width = int(round(window_s * 1e6))
    bins = (t[1:] - t[0]) // width
    out = []
    for b in np.unique(bins[pair]):
        idx = np.flatnonzero(pair & (bins == b))
        if len(idx) < min_pairs:
            continue
        diffs = (ibi[idx + 1] - ibi[idx]).astype(np.float64)
        beats = np.unique(np.concatenate([idx, idx + 1]))
        out.append({"t0": int(t[0] + b * width), "t1": int(min(t[0] + (b + 1) * width - 1, t[idx[-1] + 1])),
                    "decided": int(stream.available_us[idx[-1] + 1]),
                    "ranges": _ranges(stream.name, seq[beats]),
                    "payload": {"rmssd_ms": float(np.sqrt(np.mean(diffs ** 2))),
                                "mean_ibi_ms": float(np.mean(ibi[beats])),
                                "mean_hr_bpm": float(60_000.0 / np.mean(ibi[beats])),
                                "successive_pairs": len(idx), "valid_beats": len(beats), "window_s": window_s}})
    return out


def _gap_evidence(cause: str) -> str:
    if cause.startswith("RING_"):
        return "EVIDENCE:RING_FRAMES"
    if cause.startswith(("LINK_LOST", "COUNTER_AMBIGUOUS", "ACM_REARMED", "RATE_INCONSISTENT")):
        return "EVIDENCE:DISCONTINUITY_OF_UNKNOWN_SIZE"
    return "EVIDENCE:HOST_BOUNDARY"


@dataclass
class SessionInfo:
    session_id: str
    provenance: str                      # RAW_MEASURED (a ring) or SIMULATED (self-test)
    capabilities: Capabilities
    terminated: str
    end_us: int
    ring_commands: tuple[str, ...] = ()
    extra_header_flags: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    hrv_window_s: float = 60.0
    hrv_min_pairs: int = 20


def build_records(raw: RawSession, ingestor: Ingestor, info: SessionInfo,
                  raw_entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Sealed, contract-valid records of one live acquisition."""
    live = info.provenance == "RAW_MEASURED"
    mode = "LIVE_ACQUISITION" if live else "SIMULATED_DATA"
    people = (["HUMAN_DATA", "WEARER_CONSENT:ATTESTED_BY_OPERATOR"] if live else ["NOT_HUMAN_DATA"])
    caps = info.capabilities
    model_id = "sha256:" + hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    ordered: list[tuple[int, int, dict[str, Any]]] = []

    def add(priority: int, record: dict[str, Any]) -> None:
        ordered.append((record["device_time_start_us"], priority, record))

    add(0, _record("SESSION_HEADER", info.provenance, 0, 0,
                   [mode, *people, f"SESSION_ID:{info.session_id}", f"SOURCE:{caps.source}",
                    f"SOURCE_HARDWARE:{caps.hardware}", f"SOURCE_SDK_VERSION:{caps.sdk_version or 'NONE'}",
                    f"BRIDGE_VERSION:{BRIDGE_VERSION}", "TIMEBASE:HOST_MONOTONIC", "AVAILABILITY:HOST_RECEIPT",
                    "ACQUISITION:LIVE_INGESTION_BOUNDARY", "DATA_MINIMIZED:DECODED_STREAMS_ONLY",
                    "NO_DEVICE_IDENTIFIERS", "NO_HARDWARE_DRIVEN", "NO_ACTUATION",
                    *[f"RING_COMMAND:{c}" for c in info.ring_commands], *info.extra_header_flags],
                   stream_id="session", payload={"streams": len(raw.streams), "duration_s": info.end_us / 1e6}))
    for name, stream in raw.streams.items():
        entry = raw_entries[f"raw/{name}.csv.gz"]
        t0, t1 = (int(stream.device_time_us[0]), int(stream.device_time_us[-1])) if len(stream) else (0, 0)
        add(1, _record("STREAM_DESCRIPTOR", info.provenance, t0, t1,
                       [f"RAW_ARTIFACT:raw/{name}.csv.gz", f"CONTENT_SHA256:{entry['content_sha256']}",
                        f"ROWS:{entry['rows']}", f"COLUMNS:{','.join(STREAM_COLUMNS[name])}", *DESCRIPTOR_FLAGS[name]],
                       stream_id=name, payload=dict(raw.descriptors[name])))
    add(2, _record("CONFIG_CHANGE", info.provenance, 0, 0,
                   ["CONTROLLER_CONFIG", f"CONTROLLER_VERSION:{CONTROLLER_VERSION}",
                    f"BASELINE_PHASE:{ControllerConfig().baseline_phase}", f"ARM_PHASE:{ControllerConfig().arm_phase}",
                    "EVALUATION_END_US:0", "NEVER_EVALUATED", "CLOSED_LOOP:NOT_ELIGIBLE"],
                   stream_id="controller", payload=ControllerConfig().numeric_payload()))
    for i, problem in enumerate(capability_problems(caps)):
        add(3, _record("FAULT", "DERIVED", 0, 0, ["INPUT_CONTRACT_UNMET", "CLOSED_LOOP_NOT_ELIGIBLE"],
                       stream_id="input_contract", sequence=i, cause=problem))
    for event in raw.events:
        flags = [EVENT_KIND_FLAG + event.kind, "NOT_PHYSIOLOGICAL", mode,
                 "LINK_STATE" if event.kind.startswith("LINK:") else "RING_CONTROL"]
        payload = {k: v for k, v in event.attributes if math.isfinite(v)}
        add(4, _record("EVENT", info.provenance, event.device_time_us, event.device_time_us, flags,
                       stream_id=event.stream_id, sequence=event.sequence, payload=payload or None))
    for gap in raw.gaps:
        add(5, _record("GAP", info.provenance, gap.device_time_us, gap.device_time_us,
                       ["SAMPLE_LOSS_DECLARED", _gap_evidence(gap.cause), mode], stream_id=gap.stream_id,
                       dropped_first_sequence=gap.first_sequence, dropped_last_sequence=gap.last_sequence, cause=gap.cause))
    for i, fault in enumerate(ingestor.faults):
        add(6, _record("FAULT", "DERIVED", fault.received_us, fault.received_us,
                       ["INGESTION_FAULT", f"FAULT_KIND:{fault.kind}"], stream_id=fault.stream_id or "unknown",
                       sequence=i, cause=fault.detail))
    if IBI_STREAM in raw.streams:
        for window in hrv_windows(raw.streams[IBI_STREAM], info.hrv_window_s, info.hrv_min_pairs):
            add(7, _record("MODEL_RESULT", "MODEL_INFERRED", window["t0"], window["t1"],
                           ["HRV_WINDOW", "RMSSD_SUCCESSIVE_VALID_IBI", "LINEAGE:WINDOW_ATTRIBUTION",
                            "OFFLINE_AFTER_ACQUISITION", "NOT_A_DIAGNOSIS"],
                           stream_id="hrv_windows", payload=window["payload"],
                           decision_time_us=max(window["decided"], window["t1"]), input_cutoff_us=window["t1"],
                           source_stream_ids=[IBI_STREAM], source_sequence_ranges=window["ranges"],
                           model={"name": "RMSSD_FROM_RING_LIVE_IBI", "version": BRIDGE_VERSION, "artifact_id": model_id}))
    counts: dict[str, float] = {f"samples_{name}": len(s) for name, s in raw.streams.items()}
    counts.update({"gaps": len(raw.gaps), "ingestion_faults": len(ingestor.faults),
                   "input_contract_faults": len(capability_problems(caps)), "events": len(raw.events), "evaluations": 0,
                   "interventions": 0})
    add(99, _record("SESSION_TRAILER", info.provenance, info.end_us, info.end_us,
                    [mode, f"TERMINATED:{info.terminated}", "NO_EVALUATIONS", "NO_INTERVENTIONS"],
                    stream_id="session", payload=counts))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [seal_record(record) for _, _, record in ordered]


def _private(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass  # filesystems without POSIX modes


def write_session(directory: Path, raw: RawSession, ingestor: Ingestor, info: SessionInfo) -> dict[str, Any]:
    """session.ndjson, raw/*.csv.gz bound by SHA-256, passport.txt, and manifest.json; owner-only for live data."""
    directory = Path(directory)
    (directory / "raw").mkdir(parents=True, exist_ok=True)
    for folder in (directory, directory / "raw"):
        _private(folder, 0o700)
    documents: dict[str, bytes] = {}
    raw_entries: dict[str, dict[str, Any]] = {}
    for name, stream in raw.streams.items():
        content = _csv_bytes(stream, STREAM_COLUMNS[name])
        packed = gzip.compress(content, compresslevel=9, mtime=0)
        documents[f"raw/{name}.csv.gz"] = packed
        raw_entries[f"raw/{name}.csv.gz"] = {"sha256": hashlib.sha256(packed).hexdigest(),
                                             "content_sha256": hashlib.sha256(content).hexdigest(),
                                             "rows": len(stream), "bytes": len(packed)}
    records = build_records(raw, ingestor, info, raw_entries)
    validate_session(records)
    documents["session.ndjson"] = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n"
                                          for r in records).encode("utf-8")
    human = "YES: the ring wearer's heart beats and motion (consent attested)" if info.provenance == "RAW_MEASURED" \
        else "NONE"
    documents["passport.txt"] = passport_text(passport(records, {
        "SOURCE": info.capabilities.source, "HUMAN DATA": human, "TERMINATED": info.terminated,
        "CLOSED LOOP": "not eligible (input contract unmet; see FAULT records)"})).encode("utf-8")
    for name, data in documents.items():
        (directory / name).write_bytes(data)
        _private(directory / name, 0o600)
    manifest = {
        "schema": "circle-live-acquisition/1", "release_class": "ENGINEERING_REVIEW_ONLY",
        "provenance": info.provenance, "terminated": info.terminated, "protocol_reference": PROTOCOL_REFERENCE,
        "bridge_version": BRIDGE_VERSION, "capabilities": info.capabilities.to_dict(),
        "closed_loop_refusal": capability_problems(info.capabilities), "ingestion": ingestor.summary(),
        "software_revision": software_revision(), **info.details,
        "artifacts": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                      for name, data in sorted(documents.items())},
    }
    (directory / "manifest.json").write_bytes(dumps(manifest))
    _private(directory / "manifest.json", 0o600)
    return manifest


def ring_capabilities(core: BridgeCore, provenance: str, hardware: str, sdk_version: str | None,
                      connection_state: str, connected: bool | None) -> Capabilities:
    descriptors = core.ingestor.descriptors
    if ACM_STREAM in descriptors and core.streams.acm_rate_hz:
        descriptors[ACM_STREAM]["nominal_rate_hz"] = core.streams.acm_rate_hz
    signals = tuple(SignalCapability(name, STREAM_COLUMNS[name], descriptors[name].get("nominal_rate_hz"), provenance,
                                     tuple(sorted(descriptors[name].items()))) for name in descriptors)
    return Capabilities(
        source="oura-ring-ble" if provenance == "RAW_MEASURED" else "oura-ring-ble-self-test", connected=connected,
        connection_state=connection_state, signals=signals, actuators=(), sdk_version=sdk_version, hardware=hardware,
        authentication="Ring app-auth (AES-128 challenge per connection) with a key file held on this host; the key is "
                       "never logged, stored, or sent anywhere but the ring",
        limitations=(
            "Live frames carry no ring clock: sample times are host-receipt estimates on the host's monotonic clock.",
            "IBI notifications carry no counter, so a beat lost with the link is marked, not counted.",
            "The accelerometer scale (LSB per g) is not published; values are raw counts.",
            "The ring streams no EDA, PPG counts, gyroscope, or lab sync pulse; CIRCLE's closed loop cannot run on it.",
            "Validity and plausibility screening of beats is the ring's and open_oura's, not a clinical standard.",
        ))


async def finish(core: BridgeCore, pump_task: asyncio.Task, directory: Path, info_args: dict[str, Any],
                 capabilities: Callable[[], Capabilities]) -> tuple[dict[str, Any], RawSession]:
    """Close the inbox, let pump() drain it, and write the session."""
    await core.close()
    report = await pump_task
    info = SessionInfo(capabilities=capabilities(), **info_args)   # first: it settles the ACM descriptor's rate
    raw = core.ingestor.view()
    info.details.update({"pump": {"received": report.received, "dropped_chunks": report.dropped_chunks,
                                  "dropped_other": report.dropped_other, "outcomes": dict(sorted(report.outcomes.items()))},
                         "bridge": {"inbox_overflow": core.inbox_overflow,
                                    "duplicate_frames_ignored": core.streams.duplicate_frames,
                                    "notifications_discarded_by_type": dict(sorted(core.streams.ignored.items()))},
                         "link_states": [e.kind for e in core.monitor.events]})
    return write_session(directory, raw, core.ingestor, info), raw


# -------------------------------------------------------------- live bridge
class RingError(RuntimeError):
    """The ring refused or did not answer a step the session needs."""


def _monotonic_us() -> int:
    return time.monotonic_ns() // 1000


def load_key(path: Path) -> bytes:
    try:
        text = Path(path).expanduser().read_text(encoding="ascii").strip()
        key = bytes.fromhex(text)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"cannot read the auth key from {path}: {type(exc).__name__}") from None
    if len(key) != 16:
        raise SystemExit(f"{path} must hold the ring's 16-byte auth key as 32 hex characters")
    if os.name == "posix" and stat.S_IMODE(os.stat(Path(path).expanduser()).st_mode) & 0o077:
        print(f"warning: {path} is readable by other accounts; chmod 600 it", file=sys.stderr)
    return key


def _name_matches(advertised: str, needle: str) -> bool:
    """A bonded ring often advertises no name (open_oura issue 13): an unnamed ring passes the default needle."""
    needle = needle.strip().lower()
    if not needle:
        return True
    return needle == "oura" if not advertised else needle in advertised.lower()


async def find_rings(address: str | None, name: str, timeout_s: float) -> list[tuple[Any, Any]]:
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=timeout_s, return_adv=True)
    rings = []
    for device, adv in found.values():
        if OURA_SERVICE not in [u.lower() for u in (adv.service_uuids or [])]:
            continue
        if address and device.address.lower() != address.lower():
            continue
        if not _name_matches(device.name or adv.local_name or "", name):
            continue
        rings.append((device, adv))
    return sorted(rings, key=lambda item: item[1].rssi, reverse=True)


class OuraBridge:
    """One live session: connect, authenticate, stream, reconnect on loss, restore the ring, export."""

    def __init__(self, args: argparse.Namespace, key: bytes, clock: Callable[[], int] = _monotonic_us) -> None:
        self.args, self.key, self.clock = args, key, clock
        self.t0 = clock()
        hr, acm = not args.no_hr, not args.no_acm
        # One beat a second is a live link for HR alone; with ACM, frames arrive about every 40 ms.
        stale = args.stale_after_s or (1.0 if acm else 3.0)
        down = args.disconnected_after_s or (4.0 if acm else 8.0)
        self.core = BridgeCore(hr, acm, stale, down, inbox_limit=args.queue * 16)
        self.hr, self.acm = hr, acm
        self.stop = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.waiters: list[tuple[Callable[[Packet], bool], asyncio.Future]] = []
        self.client: Any = None
        self.closing = False
        self.terminated = "OPERATOR_STOP"
        self.hardware = "Oura ring (model not reported)"
        self.prior_hr_mode: int | None = None
        self.streaming_since: int | None = None
        self.acm_armed_at: int | None = None
        self.commands: list[str] = []
        self.connected_once = False
        self.attempt = 0
        self._last_status = 0

    def now(self) -> int:
        return self.clock() - self.t0

    # ----------------------------------------------------------- callbacks
    def on_notify(self, _sender: Any, data: bytearray) -> None:
        received = self.now()
        frame = bytes(data)
        if frame and not (frame[0] == TAG_ACM or is_live_beat_frame(frame)):
            for p in parse_packets(frame):
                for predicate, future in self.waiters:
                    if not future.done() and predicate(p):
                        future.set_result(p)
        self.core.notification(frame, received)

    def on_disconnect(self, _client: Any) -> None:
        if self.closing or self.disconnected.is_set():
            return  # our own teardown, or a backend reporting the same drop again on context exit
        now = self.now()
        self.core.control("RING_DISCONNECTED", now)
        self.core.link_lost(now, f"the BLE link dropped at {now / 1e6:.3f} s")
        self.disconnected.set()

    # ------------------------------------------------------------- requests
    async def request(self, data: bytes, predicate: Callable[[Packet], bool], timeout_s: float = 4.0) -> Packet | None:
        future = asyncio.get_running_loop().create_future()
        waiter = (predicate, future)
        self.waiters.append(waiter)
        try:
            await self.client.write_gatt_char(OURA_WRITE, data, response=True)
            return await asyncio.wait_for(future, timeout_s)
        except asyncio.TimeoutError:
            return None
        finally:
            self.waiters.remove(waiter)

    async def identify(self) -> None:
        """Model and firmware for provenance. The firmware reply's MAC bytes are never parsed."""
        firmware = await self.request(REQUEST_FIRMWARE, lambda p: p.tag == 0x09 and len(p.payload) >= 6)
        hardware = await self.request(REQUEST_HARDWARE_ID, lambda p: p.tag == 0x19 and p.payload[:1] == b"\x00")
        model = hardware.payload[1:].rstrip(b"\x00").decode("ascii", "replace") if hardware else ""
        model = model if model.isprintable() and 0 < len(model) <= 16 else "model not reported"
        version = ".".join(str(b) for b in firmware.payload[3:6]) if firmware else "unknown"
        self.hardware = f"Oura ring {model}, firmware {version}"

    async def authenticate(self) -> None:
        nonce = await self.request(request_auth_nonce(), lambda p: p.ext == EXT_AUTH_NONCE and len(p.payload) > 1)
        if nonce is None:
            raise RingError("the ring sent no auth nonce (is it paired with this computer, and the phone app closed?)")
        reply = await self.request(request_authenticate(encrypt_nonce(self.key, nonce.payload[1:])),
                                   lambda p: p.ext == EXT_AUTH_RESULT and len(p.payload) > 1)
        state = reply.payload[1] if reply else None
        self.core.control("RING_AUTHENTICATION", self.now(), result=-1 if state is None else state)
        if state != 0:
            name = AUTH_RESULTS.get(state, "NO_REPLY" if state is None else f"STATE_0x{state:02x}")
            raise RingError(f"the ring refused authentication ({name}); the key must be the one this ring was "
                            "onboarded with")

    async def read_hr_mode(self) -> int | None:
        reply = await self.request(request_feature_status(FEATURE_DAYTIME_HR),
                                   lambda p: p.ext == EXT_FEATURE_STATUS and len(p.payload) >= 6
                                   and p.payload[1] == FEATURE_DAYTIME_HR)
        return reply.payload[2] if reply else None

    async def set_hr_mode(self, mode: int) -> int | None:
        reply = await self.request(request_set_feature_mode(FEATURE_DAYTIME_HR, mode),
                                   lambda p: p.ext == EXT_SET_FEATURE_MODE_RESULT and len(p.payload) >= 3
                                   and p.payload[1] == FEATURE_DAYTIME_HR)
        return reply.payload[2] if reply else None

    async def arm_acm(self, rearm: bool = False) -> None:
        if rearm:
            self.core.streams.acm_rearmed()
        reply = await self.request(request_realtime(REALTIME_ACM, ACM_BOX_MINUTES), lambda p: p.tag == TAG_REALTIME_RESULT)
        self.acm_armed_at = self.now()
        status = reply.payload[0] if reply and reply.payload else -1
        self.core.control("ACM_REARMED" if rearm else "ACM_ON", self.acm_armed_at, status=status,
                          box_minutes=ACM_BOX_MINUTES)

    async def rearm_acm(self) -> None:
        """Renew the ACM time box before the ring stops it; a failure here is the link's, seen by on_disconnect."""
        try:
            await self.arm_acm(rearm=True)
        except Exception as exc:  # noqa: BLE001 - recorded, and the reconnect loop owns recovery
            self.core.control("ACM_REARM_FAILED", self.now())
            print(f"ACM re-arm failed: {type(exc).__name__}", file=sys.stderr)

    # --------------------------------------------------------------- session
    async def start_streams(self) -> None:
        if self.hr:
            result = await self.set_hr_mode(MODE_CONNECTED_LIVE)
            self.core.control("LIVE_HR_ON" if result == 0 else "LIVE_HR_REFUSED", self.now(),
                              result=-1 if result is None else result)
            self.commands.append("DAYTIME_HR_CONNECTED_LIVE")
        if self.acm:
            await self.arm_acm()
            self.commands.append("REALTIME_ACM_TIME_BOXED")
        if self.streaming_since is None:
            self.streaming_since = self.now()

    async def restore(self) -> None:
        """Mandatory teardown: stop ACM and put live HR back to the mode it was in before this session."""
        results: dict[str, float] = {}
        if self.acm:
            reply = await self.request(request_realtime_off(), lambda p: p.tag == TAG_REALTIME_RESULT, 2.0)
            results["acm_off"] = reply.payload[0] if reply and reply.payload else -1
        if self.hr:
            mode = self.prior_hr_mode if self.prior_hr_mode in (0, 1, 2) else MODE_AUTOMATIC
            result = await self.set_hr_mode(mode)
            results.update(hr_mode=mode, hr_restore=-1 if result is None else result)
        self.commands.append("RESTORED")
        self.core.control("RING_RESTORED", self.now(), **results)

    async def session_on_link(self, target: Any) -> bool:
        """One connection. Returns True when the session should end (stop or a refusal), False to reconnect."""
        from bleak import BleakClient

        async with BleakClient(target, disconnected_callback=self.on_disconnect, timeout=self.args.connect_timeout) as client:
            self.client = client
            self.core.control("RING_CONNECTED", self.now(), attempt=self.attempt)
            if self.args.pair:
                try:
                    await client.pair()
                except Exception as exc:  # noqa: BLE001 - platform pairing errors vary; the session decides below
                    print(f"pairing: {type(exc).__name__}: {exc}", file=sys.stderr)
            service = client.services.get_service(OURA_SERVICE)
            if service is None:
                raise RingError("the device does not expose the Oura service")
            for characteristic in service.characteristics:
                if {"notify", "indicate"} & set(characteristic.properties):
                    await client.start_notify(characteristic, self.on_notify)
            if not self.connected_once:
                await self.identify()
            await self.authenticate()
            if not self.connected_once and self.hr:
                self.prior_hr_mode = await self.read_hr_mode()
            self.connected_once = True
            await self.start_streams()
            stop = asyncio.create_task(self.stop.wait())
            lost = asyncio.create_task(self.disconnected.wait())
            await asyncio.wait({stop, lost}, return_when=asyncio.FIRST_COMPLETED)
            for task in (stop, lost):
                task.cancel()
            if self.stop.is_set() and not self.disconnected.is_set():
                self.closing = True
                try:
                    await self.restore()
                finally:
                    self.core.closed = True
                return True
        return self.stop.is_set()

    async def run_link(self) -> None:
        from bleak import BleakScanner
        from bleak.exc import BleakError

        try:
            rings = await find_rings(self.args.address, self.args.name, self.args.scan_timeout)
        except (BleakError, OSError) as exc:
            raise RingError(f"Bluetooth is not available: {type(exc).__name__}: {exc}") from exc
        if not rings:
            raise RingError("no Oura ring found (is it charged, near, and not connected to the phone app?)")
        target = rings[0][0]
        while not self.stop.is_set():
            self.disconnected.clear()
            try:
                if await self.session_on_link(target):
                    return
            except RingError:
                if not self.connected_once:
                    raise
                self.terminated = "RING_REFUSED_AFTER_RECONNECT"
                self.stop.set()
                return
            except (BleakError, asyncio.TimeoutError, OSError) as exc:
                if not self.connected_once:
                    raise RingError(f"could not open a session with the ring: {type(exc).__name__}: {exc}") from exc
                now = self.now()
                self.core.control("RING_LINK_ERROR", now, attempt=self.attempt)
                self.core.link_lost(now, f"the BLE link failed ({type(exc).__name__})", 1.0)
            if self.stop.is_set():
                return
            self.attempt += 1
            if self.attempt > self.args.max_reconnects:
                self.terminated = "LINK_LOST"
                self.stop.set()
                return
            print(f"link lost; reconnecting (attempt {self.attempt} of {self.args.max_reconnects})", file=sys.stderr)
            try:
                await asyncio.wait_for(self.stop.wait(), min(self.args.reconnect_delay_s * self.attempt, 10.0))
                return
            except asyncio.TimeoutError:
                pass
            try:
                target = await BleakScanner.find_device_by_address(rings[0][0].address,
                                                                   timeout=self.args.scan_timeout) or rings[0][0]
            except (BleakError, OSError):
                target = rings[0][0]

    async def ticker(self) -> None:
        while not self.stop.is_set():
            await asyncio.sleep(0.2)
            now = self.now()
            self.core.tick(now)
            if self.streaming_since is not None and self.args.seconds and \
                    now - self.streaming_since >= self.args.seconds * 1e6:
                self.terminated = "DURATION_REACHED"
                self.stop.set()
            if self.acm and self.acm_armed_at is not None and self.client is not None and not self.disconnected.is_set() \
                    and now - self.acm_armed_at > (ACM_BOX_MINUTES - 1) * 60e6:
                self.acm_armed_at = now
                asyncio.ensure_future(self.rearm_acm())
            if now - self._last_status >= 5e6 and self.streaming_since is not None:
                self._last_status = now
                print(self.status_line(now), flush=True)

    def status_line(self, now: int) -> str:
        s = self.core.streams
        beats = [ibi for _, ibi in s.recent_ibi]
        hr = f"{60_000 / beats[-1]:5.1f} bpm" if beats else "  --- bpm"
        rmssd = s.rolling_rmssd()
        acm_hz = s.delivered[ACM_STREAM] / max((now - (self.streaming_since or now)) / 1e6, 1e-6)
        return (f"  t={(now - (self.streaming_since or now)) / 1e6:6.0f}s  HR {hr}  RMSSD "
                f"{f'{rmssd:5.1f} ms' if rmssd is not None else '  --- ms'}  beats {s.delivered[IBI_STREAM]}"
                f"  ACM {acm_hz:5.1f} Hz  gaps {len(self.core.ingestor.gaps)}  link {self.core.monitor.state}")

    def capabilities(self) -> Capabilities:
        try:
            from importlib.metadata import version
            sdk = f"bleak {version('bleak')}"
        except Exception:  # noqa: BLE001 - metadata is informative only
            sdk = "bleak"
        return ring_capabilities(self.core, "RAW_MEASURED", self.hardware, sdk,
                                 "SESSION_ENDED:" + self.terminated, None)


async def record(args: argparse.Namespace) -> int:
    key = load_key(args.key_file)
    bridge = OuraBridge(args, key)
    loop = asyncio.get_running_loop()
    import signal
    try:
        loop.add_signal_handler(signal.SIGINT, bridge.stop.set)
    except NotImplementedError:   # Windows: no loop signal handlers, but signal.signal still sees Ctrl-C
        signal.signal(signal.SIGINT, lambda *_: loop.call_soon_threadsafe(bridge.stop.set))
    pump_task = asyncio.create_task(pump(bridge.core.pieces(), bridge.core.ingestor, max_queue=args.queue))
    ticker = asyncio.create_task(bridge.ticker())
    print(f"CIRCLE <- Oura ring over BLE (protocol: {PROTOCOL_REFERENCE})")
    error: Exception | None = None
    try:
        await bridge.run_link()
    except RingError as exc:
        error = exc
    except Exception as exc:  # noqa: BLE001 - a backend failure must not discard what was already acquired
        error = exc
        bridge.terminated = f"BRIDGE_ERROR:{type(exc).__name__}"
        print(f"bridge error: {type(exc).__name__}: {exc}; exporting what was acquired", file=sys.stderr)
    finally:
        bridge.stop.set()
        ticker.cancel()
    if not bridge.connected_once:
        pump_task.cancel()
        print(f"no session recorded: {error or 'stopped before the ring was connected'}", file=sys.stderr)
        return 2
    info = {"session_id": args.session_id, "provenance": "RAW_MEASURED", "terminated": bridge.terminated,
            "end_us": bridge.now(), "ring_commands": tuple(dict.fromkeys(bridge.commands)),
            "details": {"host_clock": {"timebase": "HOST_MONOTONIC_FROM_ATTEMPT_START",
                                       "utc_at_t0": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                  time.gmtime(time.time() - bridge.now() / 1e6))},
                        "wearer_consent": "attested by the operator with --wearer-consents"}}
    manifest, raw = await finish(bridge.core, pump_task, args.output, info, bridge.capabilities)
    print((args.output / "passport.txt").read_text(encoding="utf-8"), end="")
    print(f"ingestion: {manifest['ingestion']['samples']} samples, {manifest['ingestion']['gaps']} gaps, "
          f"{manifest['ingestion']['faults']} faults; terminated {bridge.terminated}")
    print(f"session written to {args.output} (owner-only; it holds the wearer's data)")
    return 0


# ---------------------------------------------------------------- self-test
def beat_frame(ibi_ms: int, validity: int = 1, time_since: int = 0, feature: int = FEATURE_DAYTIME_HR) -> bytes:
    return bytes([TAG_EXT, 0x08, EXT_LIVE_INDICATION, feature, 0x00, 0x02]) + struct.pack("<HH", time_since,
                                                                                          (ibi_ms & 0x0FFF) | validity << 12)


def acm_frame(counter: int, samples: list[tuple[int, int, int]], rate_hz: int = 50) -> bytes:
    body = bytes([rate_hz, counter & 0xFF]) + b"".join(struct.pack("<hhh", *s) for s in samples)
    return bytes([TAG_ACM, len(body)]) + body


def synthetic_script(seconds: float = 40.0, seed: int = 7) -> list[tuple[int, str, bytes]]:
    """A deterministic ring session with every loss the bridge must declare. Times in us from the attempt's start."""
    rng = np.random.default_rng(seed)
    start, outage = 3_000_000, (22_000_000, 27_000_000)
    script: list[tuple[int, str, bytes]] = []
    t, beat = start, 0
    while t < start + seconds * 1e6:
        ibi = int(900 + 45 * math.sin(2 * math.pi * t / 4.5e6) + rng.normal(0, 12))
        t += ibi * 1000
        beat += 1
        frame = beat_frame(ibi, validity=0 if beat == 14 else 1, time_since=beat & 0xFFFF)
        if beat == 17:
            frame = frame[:6]                                    # a beat frame cut short
        if not outage[0] <= t < outage[1]:
            script.append((t + int(rng.integers(5_000, 40_000)), "notify", frame))
    counter, frame_t = 0, start
    while frame_t < start + seconds * 1e6:
        frame_t += 40_000
        if outage[0] <= frame_t < outage[1]:
            counter = 0                                          # the re-armed ring restarts its counter
            continue
        counter = (counter + 1) % 256
        samples = [tuple(int(v) for v in rng.normal(0, 300, 3) + (0, 0, 16384)) for _ in range(2)]
        frame = acm_frame(counter, samples)
        received = frame_t + int(rng.integers(5_000, 45_000))
        if 8_000_000 <= frame_t - start < 8_120_000:
            continue                                             # three frames lost in the air
        if abs(frame_t - start - 12_000_000) < 20_000:
            frame = acm_frame(counter, samples[:1])              # a short frame
        if abs(frame_t - start - 14_000_000) < 20_000:
            frame = frame[:6]                                    # header and counter only
        script.append((received, "notify", frame))
        if abs(frame_t - start - 10_000_000) < 20_000:
            script.append((received + 1, "notify", frame))       # an identical retransmission
    script += [(start + 1_000_000, "notify", bytes.fromhex("0d0639000000360f290100")),   # battery + ack: discarded
               (start + 2_000_000, "notify", bytes.fromhex("4108000000000102030405")),   # a history event: discarded
               (outage[0] + 50_000, "lost", b""), (outage[1] - 400_000, "restored", b"")]
    script.sort(key=lambda item: item[0])
    for i in range(1, len(script)):                              # one radio, one receipt order
        if script[i][0] <= script[i - 1][0]:
            script[i] = (script[i - 1][0] + 1, script[i][1], script[i][2])
    return script


# open_oura's own test vectors (auth.rs known_answer_vector, client.rs live_hr_frame_decodes / acm_frame_decodes_two_samples).
VECTOR_AUTH = ("4431967d8bacc2659743142b68391d9a", "0e2d6a0a08c99b4365f458e6e97382", "a38a8772d3acb6db5c2b516dd56987c8")
VECTOR_LIVE_HR = "2f082802000200005913"                # IBI 857 ms, validity 1 -> 70 bpm
VECTOR_ACM = "330c3201010002000300040005000600"      # 50 Hz, counter 1, (1,2,3) and (4,5,6)


def check_vectors() -> list[str]:
    """open_oura's own test vectors, plus request bytes from its protocol tests."""
    problems = []
    key, nonce, expected = VECTOR_AUTH
    if encrypt_nonce(bytes.fromhex(key), bytes.fromhex(nonce)).hex() != expected:
        problems.append("auth: AES nonce response differs from open_oura's known answer")
    beat = decode_live_beat(bytes.fromhex(VECTOR_LIVE_HR))
    if beat is None or (beat.ibi_ms, beat.validity, int(beat.bpm or 0)) != (857, 1, 70):
        problems.append(f"live HR frame decoded as {beat}")
    frame = decode_acm_frame(bytes.fromhex(VECTOR_ACM))
    if frame is None or (frame.rate_hz, frame.counter, frame.samples) != (50, 1, ((1, 2, 3), (4, 5, 6))):
        problems.append(f"ACM frame decoded as {frame}")
    for got, want in ((request_realtime(REALTIME_ACM, 1), "060720000000010000"), (request_realtime_off(), "060400000000"),
                      (request_set_feature_mode(2, 3), "2f03220203"), (request_auth_nonce(), "2f012b"),
                      (request_feature_status(2), "2f022002")):
        if got.hex() != want:
            problems.append(f"request {got.hex()} should be {want}")
    if [p.tag for p in parse_packets(bytes.fromhex("0d0639000000360f290100"))] != [0x0D, 0x29]:
        problems.append("concatenated packets were not split")
    return problems


async def self_test(output: Path) -> tuple[list[str], dict[str, Any]]:
    problems = check_vectors()
    core = BridgeCore(True, True, 1.0, 4.0, inbox_limit=100_000)
    pump_task = asyncio.create_task(pump(core.pieces(), core.ingestor))
    script = synthetic_script()
    for at, kind, frame in script:
        core.tick(at)
        if kind == "notify":
            core.notification(frame, at)
        elif kind == "lost":
            core.control("RING_DISCONNECTED", at)
            core.link_lost(at, f"the BLE link dropped at {at / 1e6:.3f} s")
        else:
            core.control("RING_CONNECTED", at, attempt=1)
        await asyncio.sleep(0)
    end = script[-1][0] + 1
    info = {"session_id": "OURA-BRIDGE-SELF-TEST", "provenance": "SIMULATED", "terminated": "DURATION_REACHED",
            "end_us": end, "ring_commands": ("SCRIPTED",), "hrv_window_s": 10.0, "hrv_min_pairs": 5,
            "details": {"script": "synthetic_script(seconds=40, seed=7)"}}
    manifest, raw = await finish(core, pump_task, output, info,
                                 lambda: ring_capabilities(core, "SIMULATED", "scripted ring frames (no hardware)", None,
                                                           "SCRIPTED", None))
    records = load_session(output / "session.ndjson")
    causes = [g.cause.split(":", 1)[0] for g in raw.gaps]
    expected = {"RING_FRAME_COUNTER_DISCONTINUITY", "RING_FRAME_SHORT", "RING_FRAME_UNDECODABLE",
                "RING_PACKET_UNDECODABLE", "LINK_LOST"}
    if not expected <= set(causes):
        problems.append(f"declared gaps {sorted(set(causes))} miss {sorted(expected - set(causes))}")
    counter_gap = next((g for g in raw.gaps if g.cause.startswith("RING_FRAME_COUNTER")), None)
    if counter_gap is None or counter_gap.last_sequence - counter_gap.first_sequence + 1 != 3 * ACM_SLOTS:
        problems.append(f"three lost frames should be exactly {3 * ACM_SLOTS} slots, got {counter_gap}")
    if any(c.startswith(("UNDECLARED", "HOST_")) for c in causes):
        problems.append("a loss reached the boundary undeclared by the bridge")
    if core.streams.duplicate_frames != 1:
        problems.append(f"expected one identical retransmission ignored, saw {core.streams.duplicate_frames}")
    if manifest["ingestion"]["faults_by_kind"].get("UNDECODABLE_PACKET") != 2:
        problems.append(f"faults {manifest['ingestion']['faults_by_kind']}")
    if not any(r["record_type"] == "MODEL_RESULT" and "HRV_WINDOW" in r["status_flags"] for r in records):
        problems.append("no HRV window was recorded")
    if not any("CLOSED_LOOP_NOT_ELIGIBLE" in r["status_flags"] for r in records):
        problems.append("the closed-loop refusal is not recorded")
    kinds = [e.kind for e in raw.events]
    if "LINK:DISCONNECTED" not in kinds or "LINK:RECONNECTED" not in kinds:
        problems.append(f"link history {kinds} lacks the outage")
    for name, stream in raw.streams.items():
        if np.any(stream.available_us < stream.device_time_us) or np.any(np.diff(stream.device_time_us) <= 0):
            problems.append(f"{name}: timing invariant broken")
    return problems, manifest


# ---------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def ring(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--address", help="the ring's BLE address (macOS: its CoreBluetooth UUID)")
        p.add_argument("--name", default="Oura", help="advertised-name filter (default Oura; unnamed rings pass)")
        p.add_argument("--scan-timeout", type=float, default=15.0, help="seconds to scan (default 15)")
        return p

    ring(sub.add_parser("scan", help="list Oura rings advertising nearby"))
    rec = ring(sub.add_parser("record", help="stream a ring into a CIRCLE session"))
    rec.add_argument("--key-file", type=Path, required=True, help="file holding the ring's 16-byte auth key as hex")
    rec.add_argument("--wearer-consents", action="store_true",
                     help="required: the person wearing the ring knows this records their heart and motion data to this "
                          "computer and agrees")
    rec.add_argument("--seconds", type=float, default=300.0, help="streaming duration (default 300; 0 = until Ctrl-C)")
    rec.add_argument("--output", type=Path, default=Path("outputs/oura-session"))
    rec.add_argument("--session-id", default="OURA-LIVE")
    rec.add_argument("--no-hr", action="store_true", help="do not stream live heart beats")
    rec.add_argument("--no-acm", action="store_true", help="do not stream the accelerometer")
    rec.add_argument("--pair", action="store_true", help="ask the OS to pair first (Linux/Windows)")
    rec.add_argument("--connect-timeout", type=float, default=30.0)
    rec.add_argument("--max-reconnects", type=int, default=5)
    rec.add_argument("--reconnect-delay-s", type=float, default=2.0, help="backoff step between reconnects (default 2)")
    rec.add_argument("--queue", type=int, default=256, help="pump() queue size before chunks are declared lost")
    rec.add_argument("--stale-after-s", type=float, help="delivery STALE after this silence (default 1 s; HR only 3 s)")
    rec.add_argument("--disconnected-after-s", type=float,
                     help="delivery DISCONNECTED after this silence (default 4 s; HR only 8 s)")
    test = sub.add_parser("self-test", help="check decoders and the export path with no ring and no bleak")
    test.add_argument("--output", type=Path, help="keep the synthetic session here (default: a temporary directory)")
    args = parser.parse_args(argv)

    if args.command == "self-test":
        with tempfile.TemporaryDirectory() as tmp:
            out = args.output or Path(tmp) / "oura-self-test"
            problems, manifest = asyncio.run(self_test(out))
            print(f"open_oura vectors and a scripted damaged session through pump() -> Ingestor -> {out}")
            print(f"  ingestion: {manifest['ingestion']['samples']} samples, {manifest['ingestion']['gaps']} declared gaps, "
                  f"faults {manifest['ingestion']['faults_by_kind']}")
            print(f"  discarded by type: {manifest['bridge']['notifications_discarded_by_type']}")
        print("  self-test passed" if not problems else "  FAILED:\n    " + "\n    ".join(problems))
        return 0 if not problems else 1
    if args.command == "record":
        if not args.wearer_consents:
            print("record stores the ring wearer's heart beats and motion on this computer. Ask them, then pass "
                  "--wearer-consents.", file=sys.stderr)
            return 2
        if args.no_hr and args.no_acm:
            print("nothing to record: --no-hr and --no-acm together disable both streams", file=sys.stderr)
            return 2
        stale = args.stale_after_s or (3.0 if args.no_acm else 1.0)
        if not 0 < stale < (args.disconnected_after_s or (8.0 if args.no_acm else 4.0)):
            print("--stale-after-s must be positive and shorter than --disconnected-after-s", file=sys.stderr)
            return 2
    try:
        import bleak  # noqa: F401
    except ImportError:
        print("this command needs bleak: pip install bleak", file=sys.stderr)
        return 2
    if args.command == "scan":
        rings = asyncio.run(find_rings(args.address, args.name, args.scan_timeout))
        for device, adv in rings:
            print(f"{device.address}  rssi {adv.rssi}  {device.name or adv.local_name or '(unnamed)'}")
        print(f"{len(rings)} Oura ring(s) found" if rings else "no Oura ring found (charged, near, phone app closed?)")
        return 0
    return asyncio.run(record(args))


if __name__ == "__main__":
    raise SystemExit(main())
