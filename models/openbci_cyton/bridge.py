"""A Cyton session: configure, verify, stream through the ingestion boundary, restore, and export.

Setup (before anything is ingested). Stop any stream someone else left
running; ask the dongle whether the board answers (0xF0 0x07); soft-reset and
parse the banner (ADS1299 and LIS3DH identities, the Daisy); read the firmware
version with 'V'; turn time stamps off and set the board mode; configure the
channels (or a test signal); then read the ADC's registers back over "?" and
compare them with what the scaling will assume. The gains in every stream
descriptor are the gains read back, not the ones requested. A mismatch is a
FAULT, never silently corrected.

Acquisition. Each 'b' starts a segment. Every read from the port goes through
the Framer and CytonStreams, and every piece through pump() into an Ingestor
with host-receipt availability, with a LinkMonitor watching delivery. In marker
board mode the host sends a marker every probe interval and records when; the
markers that come back in the data bound the clock mapping from below.

Restore. Stop streaming, put the channels back to their defaults ('d') and the
board back in default mode, so the next program to open the board does not
inherit test signals.

Export. session.ndjson (contract-valid, sealed records), raw/*.csv.gz bound by
SHA-256, analysis.json, passport.txt, manifest.json. A session with electrodes
on a person is HUMAN_DATA, needs the wearer's consent, and is written
owner-only. A phantom session has every channel on an internal test condition
and the accelerometer off, so by construction it holds no signal from a body.

The Cyton cannot drive CIRCLE's closed loop: it has no EDA front end, no
MAX30102 red/IR counts, no gyroscope, and no lab sync stream in the input
contract's form (models/physiology/loop.py). The refusal is recorded as FAULTs.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
from typing import Any, AsyncIterator, Callable, Protocol

import numpy as np

from models.acquisition.ingest import Ingestor, LinkMonitor, StreamChunk
from models.acquisition.live import Piece, pump
from models.physiology.controller import CONTROLLER_VERSION, ControllerConfig
from models.physiology.evidence import EVENT_KIND_FLAG, SCHEMA_VERSION, dumps, software_revision
from models.physiology.ledger import passport, passport_text
from models.physiology.loop import Capabilities, SignalCapability, capability_problems
from models.physiology.streams import DeviceEvent, Gap, RawSession, Stream
from models.session_records import seal_record, validate_session

from . import analysis as an
from . import protocol as p
from .framing import Discarded, Framer, Packet, Text
from .streams import (ACCEL_STREAM, AUX_STREAM, CONTROL_STREAM, DAISY_STREAM, EXG_STREAM, LATENCY_BOUND_US,
                      MARKER_STREAM, SERIAL_FAULTS, CytonStreams, StreamLayout)

BRIDGE_VERSION = "1.0.0"
PACKAGE_DIR = Path(__file__).resolve().parent
PROBE_CODES = [ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"]
PHANTOM_SEGMENTS = (("shorted", 8.0), ("pulse-1x-slow", 8.0), ("pulse-2x-slow", 8.0), ("pulse-1x-fast", 6.0),
                    ("pulse-2x-fast", 6.0), ("dc", 3.0))


class Port(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self, timeout_s: float) -> bytes: ...

    def close(self) -> None: ...


class CytonError(RuntimeError):
    """The board or dongle refused or did not answer a step the session needs."""


@dataclass
class Plan:
    """What one session does."""

    mode: str                                         # PHANTOM or RECORD
    segments: tuple[tuple[str, float], ...]           # (TEST_SIGNALS key or "electrodes", seconds)
    board_mode: str = "default"
    gains: tuple[int, ...] | None = None              # electrodes: per channel, default 24
    probe_interval_s: float | None = None             # marker probes (marker board mode only)
    ecg_channel: str | None = None                    # e.g. "ch2"
    stale_after_s: float = 0.25
    disconnected_after_s: float = 1.0
    read_timeout_s: float = 0.02
    queue: int = 1024

    def __post_init__(self) -> None:
        if self.mode not in ("PHANTOM", "RECORD"):
            raise ValueError("mode is PHANTOM or RECORD")
        if self.probe_interval_s and self.board_mode != "marker":
            raise ValueError("marker probes need marker board mode")
        for label, seconds in self.segments:
            if label != "electrodes" and label not in p.TEST_SIGNALS:
                raise ValueError(f"unknown segment {label!r}")
            if seconds <= 0:
                raise ValueError("segments need a positive duration")
        if self.mode == "PHANTOM" and any(label == "electrodes" for label, _ in self.segments):
            raise ValueError("a phantom session uses internal test conditions only")
        if self.mode == "PHANTOM" and self.board_mode not in ("marker",):
            raise ValueError("a phantom session runs in marker mode: the accelerometer stays off")


def phantom_plan(scale: float = 1.0, probe_interval_s: float = 0.5) -> Plan:
    return Plan("PHANTOM", tuple((label, seconds * scale) for label, seconds in PHANTOM_SEGMENTS), "marker",
                probe_interval_s=probe_interval_s)


# ------------------------------------------------------------------ core
_CLOSE = object()


class CytonCore:
    """The byte stream in, pieces queued for pump(), link health, control events, and board text."""

    def __init__(self, layout: StreamLayout, plan: Plan, inbox_limit: int = 65536, capacity: int = 8_000_000) -> None:
        self.layout = layout
        self.framer = Framer()
        self.streams = CytonStreams(layout)
        self.ingestor = Ingestor(layout.descriptors(), self.streams.columns, capacity, stamp_host_availability=True)
        self.monitor = LinkMonitor(int(plan.stale_after_s * 1e6), int(plan.disconnected_after_s * 1e6))
        self.inbox: asyncio.Queue = asyncio.Queue(maxsize=inbox_limit)
        self.control_sequence = 0
        self.inbox_overflow = 0
        self.replies: list[dict[str, Any]] = []
        self.discarded = Counter()
        self.probes_sent: list[tuple[int, int]] = []        # (code, sent_us)
        self.closed = False

    def emit(self, received_us: int, piece: Piece) -> None:
        if self.closed:
            return
        try:
            self.inbox.put_nowait((received_us, piece))
        except asyncio.QueueFull:
            self.inbox_overflow += 1
            if isinstance(piece, StreamChunk):
                self.ingestor.deliver_gap(Gap(piece.stream_id, int(piece.sequence[0]), int(piece.sequence[-1]),
                                              received_us, "HOST_QUEUE_FULL: the bridge inbox was full; chunk dropped"),
                                          received_us)
            else:
                self.ingestor.flag(getattr(piece, "stream_id", CONTROL_STREAM), "DROPPED_AT_QUEUE",
                                   f"{type(piece).__name__} dropped: the bridge inbox was full", received_us)

    def feed(self, data: bytes, received_us: int, final: bool = False) -> None:
        """Bytes read from the port at received_us (host clock)."""
        if self.closed:
            return
        items = self.framer.feed(data) if not final else self.framer.flush()
        batch: list[Packet] = []
        for item in items + [None]:
            if isinstance(item, Packet):
                batch.append(item)
                continue
            if batch:
                pieces = self.streams.packets(batch, received_us)
                if any(isinstance(piece, StreamChunk) for piece in pieces):
                    for event in self.monitor.delivered(received_us):
                        self.emit(received_us, event)
                for piece in pieces:
                    self.emit(received_us, piece)
                batch = []
            if isinstance(item, Text):
                self.text(item, received_us)
            elif isinstance(item, Discarded):
                self.discarded[item.reason] += item.count
                self.ingestor.flag(SERIAL_FAULTS, "BYTES_DISCARDED",
                                   f"{item.count} byte(s) were neither a checked packet nor text ({item.reason})",
                                   received_us)
        self._drain_faults()

    def text(self, item: Text, received_us: int) -> None:
        text = item.text
        self.replies.append({"received_us": received_us, "text": text[:400], "complete": item.complete})
        kind = ("DONGLE_COMMS_TIMEOUT" if "Communications timeout" in text else
                "BOARD_REPLY_FAILURE" if text.startswith("Failure") else "BOARD_REPLY")
        self.control(kind, received_us, characters=len(text), complete=float(item.complete))

    def control(self, kind: str, now_us: int, **attributes: float) -> None:
        """A board-control observation (command, reply, segment, probe): never physiological."""
        event = DeviceEvent(CONTROL_STREAM, self.control_sequence, kind, int(now_us),
                            tuple(sorted((k, float(v)) for k, v in attributes.items())))
        self.control_sequence += 1
        self.emit(now_us, event)

    def link_lost(self, now_us: int, detail: str, code: float = 0.0) -> None:
        for event in self.monitor.failed(now_us, code):
            self.emit(now_us, event)
        for gap in self.streams.link_lost(now_us, detail):
            self.emit(now_us, gap)

    def tick(self, now_us: int) -> None:
        for event in self.monitor.tick(now_us):
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


# ----------------------------------------------------------------- setup
@dataclass
class Setup:
    """What the board said about itself before acquisition."""

    banner: p.Banner | None = None
    version: str | None = None
    dongle: str | None = None
    commands: list[str] = field(default_factory=list)
    events: list[tuple[str, int, dict[str, float]]] = field(default_factory=list)
    replies: list[dict[str, Any]] = field(default_factory=list)
    registers: dict[str, dict[str, int]] = field(default_factory=dict)
    register_problems: list[str] = field(default_factory=list)
    stale_packets_discarded: int = 0
    configuration: list[dict[str, Any]] = field(default_factory=list)   # per segment, read back

    @property
    def daisy(self) -> bool:
        return bool(self.banner and self.banner.daisy)


class Session:
    """One session against one port; synchronous setup, asynchronous acquisition."""

    def __init__(self, port: Port, clock: Callable[[], int], plan: Plan, blocking_reads: bool,
                 stop: asyncio.Event | None = None, status: Callable[[str], None] | None = None) -> None:
        self.port, self.clock, self.plan, self.blocking = port, clock, plan, blocking_reads
        self.t0 = clock()
        self.setup = Setup()
        self.core: CytonCore | None = None
        self.segments: list[dict[str, Any]] = []
        self.terminated = "COMPLETED"
        self.stop = stop or asyncio.Event()
        self.status = status
        self._framer = Framer()
        self._probe = 0

    def now(self) -> int:
        return self.clock() - self.t0

    # ------------------------------------------------------- exchange
    def _note(self, kind: str, **attributes: float) -> None:
        if self.core is not None:
            self.core.control(kind, self.now(), **attributes)
        else:
            self.setup.events.append((kind, self.now(), attributes))

    def send(self, command: bytes) -> None:
        refusal = p.command_refusal(command)
        if refusal is not None:
            raise ValueError(f"CIRCLE does not send {command!r}: {refusal}")
        label = command.hex() if command[:1] == b"\xf0" else command.decode("ascii")
        self.setup.commands.append(label)
        self._note("COMMAND_SENT", characters=len(command), first_byte=command[0])
        self.port.write(command)

    def exchange(self, command: bytes, wait_s: float, until: str = "$$$") -> str:
        """Send one command and collect text until `until` appears or wait_s passes (setup only)."""
        self.send(command)
        deadline = self.clock() + wait_s * 1e6
        texts: list[str] = []
        while self.clock() < deadline:
            data = self.port.read(0.05)
            for item in self._framer.feed(data):
                if isinstance(item, Text):
                    texts.append(item.text)
                    self.setup.replies.append({"received_us": self.now(), "text": item.text[:2000],
                                               "after": command.hex() if command[:1] == b"\xf0" else command.decode()})
                    self._note("BOARD_REPLY_FAILURE" if item.text.startswith("Failure") else "BOARD_REPLY",
                               characters=len(item.text))
                elif isinstance(item, Packet):
                    self.setup.stale_packets_discarded += 1
            if any(until in t for t in texts):
                break
        return "".join(texts)

    def drain(self, seconds: float) -> None:
        deadline = self.clock() + seconds * 1e6
        while self.clock() < deadline:
            for item in self._framer.feed(self.port.read(0.05)):
                if isinstance(item, Packet):
                    self.setup.stale_packets_discarded += 1

    def configure_board(self) -> None:
        """Stop, probe, reset, identify, and set the board mode. Raises CytonError when the board is not there."""
        self.send(p.STOP_STREAMING)
        self.drain(0.3)
        reply = self.exchange(p.DONGLE_SYS_UP, 1.5)
        self.setup.dongle = reply.strip("$") or None
        if "System is Up" not in reply:
            raise CytonError(f"the dongle reports the board unreachable ({reply.strip() or 'no reply'}); is it on, "
                             "in range, and on the same radio channel?")
        banner = p.parse_banner(self.exchange(p.SOFT_RESET, 4.0))
        if banner is None:
            raise CytonError("no soft-reset banner: this does not look like a Cyton on the other end")
        self.setup.banner = banner
        if banner.ads_id != p.ADS1299_ID:
            raise CytonError(f"the board's ADC reports ID 0x{banner.ads_id or 0:02X}, not the ADS1299's 0x3E")
        version = self.exchange(p.QUERY_VERSION, 1.5).replace("$$$", "").strip()
        self.setup.version = version or None
        self.exchange(p.TIME_STAMPS_OFF, 1.5)
        self.exchange(p.board_mode(self.plan.board_mode), 1.5)

    def configure_segment(self, label: str) -> dict[str, Any]:
        """Configure the channels for one segment and verify them against the ADC's registers."""
        n = 16 if self.setup.daisy else 8
        if label == "electrodes":
            gains = self.plan.gains or (p.DEFAULT_GAIN,) * n
            for channel in range(1, n + 1):
                self.exchange(p.channel_settings(channel, gain=gains[channel - 1]), 1.5)
            expected = {"input_type": "NORMAL", "gains": tuple(gains[:n]), "test": None}
        else:
            signal = p.TEST_SIGNALS[label]
            self.exchange(signal.command, 1.5)
            expected = {"input_type": signal.input_type, "gains": (p.DEFAULT_GAIN,) * n,
                        "test": (signal.amplitude_k, signal.frequency) if signal.input_type == "TESTSIG" else None}
        dump = p.parse_register_dump(self.exchange(p.QUERY_REGISTERS, 4.0))
        config = {"label": label, "read_back": bool(dump), "channels": []}
        problems: list[str] = []
        if not dump:
            problems.append(f"{label}: the register dump could not be read; gains are assumed, not verified")
        for name, regs in dump.items():
            self.setup.registers[f"{label}:{name}"] = regs.values
            offset = 0 if name == "board" else 8
            for i, ch in enumerate(regs.channels()):
                number = offset + i + 1
                if number > n:
                    continue
                config["channels"].append({"channel": number, "gain": ch.gain, "input_type": ch.input_type,
                                           "power_down": ch.power_down, "srb2": ch.srb2})
                want_gain = expected["gains"][number - 1]
                if ch.gain != want_gain or ch.input_type != expected["input_type"] or ch.power_down:
                    problems.append(f"{label}: channel {number} reads gain {ch.gain}, input {ch.input_type}, "
                                    f"power_down {ch.power_down}; expected gain {want_gain}, input "
                                    f"{expected['input_type']}, powered")
            test = regs.test_signal
            if expected["test"] is not None and test is not None and \
                    (not test["internal"] or (test["amplitude_k"], test["frequency"]) != expected["test"]):
                problems.append(f"{label}: CONFIG2 holds {test}, expected internal {expected['test']}")
            config["test_signal"] = test
            config["data_rate_hz"] = regs.data_rate_hz
        self.setup.register_problems += problems
        self.setup.configuration.append(config)
        return config

    def layout(self) -> StreamLayout:
        """Gains as read back from the first configured segment (the requested ones where none were read)."""
        n = 16 if self.setup.daisy else 8
        gains = list(self.plan.gains or (p.DEFAULT_GAIN,) * n) + [p.DEFAULT_GAIN] * 16
        if self.setup.configuration:
            for ch in self.setup.configuration[0]["channels"]:
                if ch["gain"] in p.GAINS:
                    gains[ch["channel"] - 1] = ch["gain"]
        return StreamLayout(self.plan.board_mode, self.setup.daisy, tuple(gains[:16]))

    # ---------------------------------------------------- acquisition
    async def read(self) -> bytes:
        if self.blocking:
            return await asyncio.get_running_loop().run_in_executor(None, self.port.read, self.plan.read_timeout_s)
        return self.port.read(self.plan.read_timeout_s)

    async def stream_segment(self, label: str, seconds: float) -> None:
        core = self.core
        assert core is not None
        epochs_before = core.streams.epochs
        core.control("SEGMENT_START", self.now(), segment=len(self.segments),
                     test_condition=list(p.TEST_SIGNALS).index(label) if label in p.TEST_SIGNALS else -1)
        sent = self.now()
        self.send(p.START_STREAMING)
        core.streams.start_segment(sent)
        end = sent + seconds * 1e6
        next_probe = sent + 0.5e6 if self.plan.probe_interval_s else None
        next_status = sent + 5e6
        while not self.stop.is_set() and self.now() < end:
            try:
                data = await self.read()
            except OSError as exc:
                core.link_lost(self.now(), f"the serial port failed ({type(exc).__name__})", 1.0)
                self.terminated = "LINK_LOST"
                self.stop.set()
                break
            received = self.now()
            if data:
                core.feed(data, received)
            core.tick(received)
            if next_probe is not None and received >= next_probe:
                code = PROBE_CODES[self._probe % len(PROBE_CODES)]
                self._probe += 1
                sent_probe = self.now()
                core.probes_sent.append((code, sent_probe))
                core.control("MARKER_SENT", sent_probe, code=code)
                self.send(p.marker(code))
                next_probe = received + self.plan.probe_interval_s * 1e6
            if self.status is not None and received >= next_status:
                next_status = received + 5e6
                self.status(self.status_line(label, received - sent))
            await asyncio.sleep(0)
        if self.terminated != "LINK_LOST":
            for gap in core.streams.end_segment(self.now(), int(self.plan.stale_after_s * 1e6)):
                core.emit(self.now(), gap)
            self.send(p.STOP_STREAMING)
            stop_deadline = self.now() + 0.25e6
            while self.now() < stop_deadline:
                data = await self.read()
                if data:
                    core.feed(data, self.now())
                await asyncio.sleep(0)
        core.control("SEGMENT_END", self.now(), segment=len(self.segments))
        self.segments.append({"label": label, "seconds": seconds, "started_us": sent,
                              "epochs": list(range(epochs_before, core.streams.epochs))})

    def status_line(self, label: str, elapsed_us: int) -> str:
        core = self.core
        assert core is not None
        rows = core.streams.delivered[EXG_STREAM]
        return (f"  {label:<14} t={elapsed_us / 1e6:6.1f}s  packets {core.framer.packets}  lost {core.streams.lost_packets}"
                f"  epochs {core.streams.epochs}  discarded bytes {sum(core.discarded.values())}  link {core.monitor.state}"
                f"  ({rows} rows of {EXG_STREAM})")

    def restore(self) -> None:
        """Leave the board as a next program expects it: stopped, channels default, default board mode; confirmed."""
        try:
            self.send(p.STOP_STREAMING)
            self.drain(0.2)
            confirmed = "default" in self.exchange(p.CHANNELS_DEFAULT, 1.5)
            if self.plan.board_mode != "default":
                confirmed = "Success: default" in self.exchange(p.board_mode("default"), 1.5) and confirmed
            self._note("BOARD_RESTORED" if confirmed else "BOARD_RESTORE_UNCONFIRMED")
        except OSError:
            self._note("BOARD_RESTORE_FAILED")


async def run(port: Port, clock: Callable[[], int], plan: Plan, blocking_reads: bool = False,
              stop: asyncio.Event | None = None, status: Callable[[str], None] | None = None
              ) -> tuple["Session", RawSession, Any]:
    """Configure, acquire every segment through pump(), and restore. Raises CytonError before any acquisition."""
    session = Session(port, clock, plan, blocking_reads, stop, status)
    session.configure_board()
    first_label = plan.segments[0][0]
    session.configure_segment(first_label)
    core = CytonCore(session.layout(), plan, inbox_limit=plan.queue * 64)
    session.core = core
    for kind, at, attributes in session.setup.events:
        core.control(kind, at, **attributes)
    pump_task = asyncio.create_task(pump(core.pieces(), core.ingestor, max_queue=plan.queue))
    try:
        for i, (label, seconds) in enumerate(plan.segments):
            if session.stop.is_set():
                break
            if i:
                session.configure_segment(label)
            await session.stream_segment(label, seconds)
    except Exception as exc:  # noqa: BLE001 - a failure must not discard what was already acquired
        session.terminated = f"BRIDGE_ERROR:{type(exc).__name__}"
    finally:
        if session.stop.is_set() and session.terminated == "COMPLETED":
            session.terminated = "OPERATOR_STOP"
        if session.terminated != "LINK_LOST":
            session.restore()
        core.feed(b"", session.now(), final=True)
        await core.close()
    report = await pump_task
    return session, core.ingestor.view(), report


# ---------------------------------------------------------------- export
def _record(record_type: str, provenance: str, t0: int, t1: int, flags: list[str], **fields: Any) -> dict[str, Any]:
    record = {"schema_version": SCHEMA_VERSION, "record_type": record_type, "provenance": provenance,
              "device_time_start_us": int(max(t0, 0)), "device_time_end_us": int(max(t0, t1, 0)),
              "status_flags": list(dict.fromkeys(flags)), "crc32c": "00000000"}
    record.update({k: v for k, v in fields.items() if v is not None})
    return record


def _finite(values: dict[str, Any]) -> dict[str, float]:
    out = {}
    for k, v in values.items():
        if isinstance(v, (bool, int, float, np.integer, np.floating)) and math.isfinite(float(v)):
            out[k] = float(v)
    return out


def _csv_bytes(stream: Stream, columns: tuple[str, ...]) -> bytes:
    matrix = np.column_stack([stream.sequence, stream.device_time_us, stream.available_us,
                              *[stream.columns[c] for c in columns]]).astype(np.int64) if len(stream) else \
        np.zeros((0, 3 + len(columns)), dtype=np.int64)
    buffer = io.StringIO()
    buffer.write(",".join(["sequence", "device_time_us", "available_us", *columns]) + "\n")
    np.savetxt(buffer, matrix, fmt="%d", delimiter=",")
    return buffer.getvalue().encode("ascii")


def model_id() -> str:
    digest = hashlib.sha256()
    for name in ("analysis.py", "streams.py", "framing.py", "protocol.py"):
        digest.update(name.encode() + b"\0" + (PACKAGE_DIR / name).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return "sha256:" + digest.hexdigest()


DESCRIPTOR_FLAGS = {
    EXG_STREAM: ["SEQUENCE:ADC_SAMPLE_COUNT_ACROSS_EPOCHS", "SAMPLE_TIME:MINIMUM_DELAY_CLOCK_LINE",
                 "DEVICE_CLOCK:EPOCH_SAMPLE_INDEX_COLUMN", "CODES:ADS1299_24BIT_TWOS_COMPLEMENT",
                 "SCALE:GAIN_READ_BACK_FROM_REGISTERS"],
    DAISY_STREAM: ["SEQUENCE:ADC_SAMPLE_PAIR_COUNT_ACROSS_EPOCHS", "SAMPLE_TIME:CENTER_OF_TWO_SAMPLE_AVERAGE",
                   "DEVICE_CLOCK:EPOCH_SAMPLE_INDEX_COLUMN", "CODES:ADS1299_24BIT_TWOS_COMPLEMENT",
                   "FIRST_ROW_AFTER_ADC_START_AVERAGES_A_STALE_VALUE"],
    ACCEL_STREAM: ["SEQUENCE:READING_COUNT", "SAMPLE_TIME:CARRYING_PACKET_DATA_READY",
                   "ZERO_TRIPLE_MEANS_NO_NEW_READING", "ACCELEROMETER_ONLY_NO_GYROSCOPE", "LIS3DH_4G_HIGH_RESOLUTION"],
    AUX_STREAM: ["SEQUENCE:ADC_SAMPLE_COUNT_ACROSS_EPOCHS", "SAMPLE_TIME:CARRYING_PACKET_DATA_READY",
                 "PIC32_10BIT_ADC_OR_DIGITAL_PINS"],
}


@dataclass
class SessionInfo:
    session_id: str
    provenance: str                       # RAW_MEASURED (a board) or SIMULATED (the simulated Cyton)
    human_data: bool
    hardware: str
    end_us: int
    details: dict[str, Any] = field(default_factory=dict)


def cyton_capabilities(layout: StreamLayout, provenance: str, hardware: str, connection_state: str,
                       firmware: str | None) -> Capabilities:
    descriptors = layout.descriptors()
    signals = tuple(SignalCapability(name, cols, descriptors[name].get("nominal_rate_hz"), provenance,
                                     tuple(sorted(descriptors[name].items())))
                    for name, cols in layout.columns().items())
    return Capabilities(
        source="openbci-cyton" if provenance == "RAW_MEASURED" else "openbci-cyton-simulated", connected=None,
        connection_state=connection_state, signals=signals, actuators=(), sdk_version=firmware, hardware=hardware,
        authentication="none: the dongle's radio link is unauthenticated and unencrypted; anyone in range on the same "
                       "radio channel could listen",
        limitations=(
            "Sample times are host-clock estimates (the minimum-delay line); exact intervals come from the ADC's "
            "sample index, whose tick is within +-2.5 % of 4 ms until the clock mapping measures it.",
            "The ADS1299 is a biopotential front end: EEG, ECG, EMG. It measures no skin conductance, no optical "
            "PPG counts, no gyroscope, and no lab sync pulse in the input contract's form.",
            "Analog mode reads three 10-bit PIC32 pins; what is attached to them is not known to CIRCLE.",
            "The accelerometer reports only when it has a new reading (about 25 Hz); readings in lost packets "
            "cannot be counted.",
            "Not a medical device. Electrodes must be attached only with the board on battery power and the "
            "computer link through the radio dongle.",
        ))


def build_records(raw: RawSession, core: CytonCore, session: Session, info: SessionInfo,
                  raw_entries: dict[str, dict[str, Any]], results: dict[str, Any]) -> list[dict[str, Any]]:
    """Sealed, contract-valid records of one Cyton session."""
    live = info.provenance == "RAW_MEASURED"
    mode = "LIVE_ACQUISITION" if live else "SIMULATED_DATA"
    phantom = session.plan.mode == "PHANTOM"
    people = (["HUMAN_DATA", "WEARER_CONSENT:ATTESTED_BY_OPERATOR"] if info.human_data else
              ["NOT_HUMAN_DATA", *(["BY_CONSTRUCTION:INTERNAL_TEST_CONDITIONS_ONLY"] if phantom else [])])
    caps = cyton_capabilities(core.layout, info.provenance, info.hardware, "SESSION_ENDED:" + session.terminated,
                              session.setup.version)
    mid = model_id()
    ordered: list[tuple[int, int, dict[str, Any]]] = []

    def add(priority: int, record: dict[str, Any]) -> None:
        ordered.append((record["device_time_start_us"], priority, record))

    add(0, _record("SESSION_HEADER", info.provenance, 0, 0,
                   [mode, *people, f"SESSION_ID:{info.session_id}", f"SESSION_MODE:{session.plan.mode}",
                    f"SOURCE:{caps.source}", f"SOURCE_HARDWARE:{info.hardware}",
                    f"SOURCE_FIRMWARE:{session.setup.version or 'UNKNOWN'}", f"BRIDGE_VERSION:{BRIDGE_VERSION}",
                    f"PROTOCOL:OpenBCI_Cyton_Library@{p.LIBRARY_COMMIT[:7]}", f"PROTOCOL:OpenBCI_Radios@{p.RADIOS_COMMIT[:7]}",
                    f"BOARD_MODE:{session.plan.board_mode}", f"DAISY:{'PRESENT' if core.layout.daisy else 'ABSENT'}",
                    "TIMEBASE:HOST_MONOTONIC", "AVAILABILITY:HOST_RECEIPT", "SAMPLE_CLOCK:ADS1299_INTERNAL_OSCILLATOR",
                    "ACQUISITION:LIVE_INGESTION_BOUNDARY", "NO_DEVICE_IDENTIFIERS", "NO_ACTUATION",
                    "BOARD_CONFIGURATION_COMMANDS_ONLY",
                    *[f"BOARD_COMMAND:{c}" for c in dict.fromkeys(session.setup.commands) if not c.startswith("`")]],
                   stream_id="session", payload={"streams": len(raw.streams), "duration_s": info.end_us / 1e6,
                                                 "segments": len(session.segments)}))
    for name, stream in raw.streams.items():
        entry = raw_entries[f"raw/{name}.csv.gz"]
        t0, t1 = (int(stream.device_time_us[0]), int(stream.device_time_us[-1])) if len(stream) else (0, 0)
        add(1, _record("STREAM_DESCRIPTOR", info.provenance, t0, t1,
                       [f"RAW_ARTIFACT:raw/{name}.csv.gz", f"CONTENT_SHA256:{entry['content_sha256']}",
                        f"ROWS:{entry['rows']}", f"COLUMNS:{','.join(core.streams.columns[name])}",
                        *DESCRIPTOR_FLAGS[name]], stream_id=name, payload=dict(raw.descriptors[name])))
    add(2, _record("CONFIG_CHANGE", info.provenance, 0, 0,
                   ["CONTROLLER_CONFIG", f"CONTROLLER_VERSION:{CONTROLLER_VERSION}",
                    f"BASELINE_PHASE:{ControllerConfig().baseline_phase}", f"ARM_PHASE:{ControllerConfig().arm_phase}",
                    "EVALUATION_END_US:0", "NEVER_EVALUATED", "CLOSED_LOOP:NOT_ELIGIBLE"],
                   stream_id="controller", payload=ControllerConfig().numeric_payload()))
    for i, config in enumerate(session.setup.configuration):
        segment = next((s for s in session.segments if s["label"] == config["label"]), None)
        at = segment["started_us"] if segment else 0
        payload = {"channels_read_back": len(config["channels"])}
        for ch in config["channels"]:
            payload[f"ch{ch['channel']}_gain"] = float(ch["gain"] or 0)
            payload[f"ch{ch['channel']}_input_code"] = float(p.INPUT_TYPES.get(ch["input_type"], "-1"))
            payload[f"ch{ch['channel']}_powered"] = float(not ch["power_down"])
        test = config.get("test_signal") or {}
        payload.update(_finite({"test_internal": test.get("internal", False), "test_amplitude_k": test.get("amplitude_k", 0),
                                "data_rate_hz": config.get("data_rate_hz") or 0}))
        add(2, _record("CONFIG_CHANGE", info.provenance, at, at,
                       ["BOARD_CONFIGURATION", f"SEGMENT_CONDITION:{config['label']}",
                        "READ_BACK_FROM_ADS_REGISTERS" if config["read_back"] else "ASSUMED_NOT_READ_BACK"],
                       stream_id="board_configuration", sequence=i, payload=payload))
    for i, problem in enumerate(capability_problems(caps)):
        add(3, _record("FAULT", "DERIVED", 0, 0, ["INPUT_CONTRACT_UNMET", "CLOSED_LOOP_NOT_ELIGIBLE"],
                       stream_id="input_contract", sequence=i, cause=problem))
    for i, problem in enumerate(session.setup.register_problems):
        add(3, _record("FAULT", "DERIVED", 0, 0, ["BOARD_CONFIGURATION_MISMATCH"], stream_id="board_configuration_check",
                       sequence=i, cause=problem))
    exg = raw.streams[EXG_STREAM]
    for bounds in results["clock"]:
        rows = np.flatnonzero(exg.columns["epoch"] == int(bounds["epoch"])) if len(exg) else np.zeros(0, dtype=int)
        if not len(rows):
            continue
        flags = ["HOST_TO_DEVICE_SAMPLE_CLOCK", "MINIMUM_DELAY_LINE", f"EPOCH:{int(bounds['epoch'])}",
                 "PROBE_BOUNDED" if bounds["probes"] else "UPPER_BOUND_ONLY_LATENCY_FLOOR_UNKNOWN"]
        if not bounds["consistent"]:
            flags.append("RECEIPTS_AND_PROBES_INCONSISTENT")
        add(3, _record("CLOCK_MAPPING", "DERIVED", int(exg.device_time_us[rows[0]]), int(exg.device_time_us[rows[-1]]),
                       flags, stream_id=EXG_STREAM, payload=_finite(bounds), source_stream_ids=[EXG_STREAM],
                       source_sequence_ranges=an.ranges(exg, rows)))
    for event in raw.events:
        flags = [EVENT_KIND_FLAG + event.kind, "NOT_PHYSIOLOGICAL", mode,
                 "LINK_STATE" if event.kind.startswith("LINK:") else
                 "MARKER_OBSERVED_IN_DATA" if event.stream_id == MARKER_STREAM else "BOARD_CONTROL"]
        payload = {k: v for k, v in event.attributes if math.isfinite(v)}
        add(4, _record("EVENT", info.provenance, event.device_time_us, event.device_time_us, flags,
                       stream_id=event.stream_id, sequence=event.sequence, payload=payload or None))
    for gap in raw.gaps:
        evidence = ("EVIDENCE:SAMPLE_COUNTER" if gap.cause.startswith("CYTON_") else
                    "EVIDENCE:DISCONTINUITY_OF_UNKNOWN_SIZE" if gap.cause.startswith(
                        ("LINK_LOST", "COUNTER_AMBIGUOUS", "ACCEL_LOSS_UNKNOWN")) else "EVIDENCE:HOST_BOUNDARY")
        add(5, _record("GAP", info.provenance, gap.device_time_us, gap.device_time_us,
                       ["SAMPLE_LOSS_DECLARED", evidence, mode], stream_id=gap.stream_id,
                       dropped_first_sequence=gap.first_sequence, dropped_last_sequence=gap.last_sequence, cause=gap.cause))
    for i, fault in enumerate(core.ingestor.faults):
        add(6, _record("FAULT", "DERIVED", fault.received_us, fault.received_us,
                       ["INGESTION_FAULT", f"FAULT_KIND:{fault.kind}"], stream_id=fault.stream_id or "unknown",
                       sequence=i, cause=fault.detail))
    end = int(exg.device_time_us[-1]) if len(exg) else info.end_us
    phantom_card = results.get("phantom")
    if phantom_card:
        for i, item in enumerate(phantom_card["checks"]):
            payload = _finite(item["measured"]) or {}
            payload["passed"] = float(item["status"] == "PASS")
            add(7, _record("MODEL_RESULT", "DERIVED", end, end,
                           ["PHANTOM_CHECK", f"CHECK:{item['id']}", f"STATUS:{item['status']}",
                            "KNOWN_TRUTH:DATASHEET_AND_FIRMWARE", "NOT_HUMAN_DATA"],
                           stream_id="phantom_checks", sequence=i, payload=payload,
                           source_stream_ids=[EXG_STREAM] if len(exg) else None,
                           source_sequence_ranges=an.ranges(exg) if len(exg) else None))
        add(7, _record("MODEL_RESULT", "DERIVED", end, end,
                       ["PHANTOM_VERDICT", f"VERDICT:{phantom_card['verdict']}", "CYTON_SIGNAL_CHAIN_ONLY",
                        "NOT_A_CIRCLE_REV_B_RESULT"], stream_id="phantom_checks", sequence=len(phantom_card["checks"]),
                       payload={"judged": float(sum(c["status"] in ("PASS", "FAIL") for c in phantom_card["checks"])),
                                "failed": float(sum(c["status"] == "FAIL" for c in phantom_card["checks"]))}))
    for i, q in enumerate(results.get("quality", [])):
        stream = raw.streams[q["stream"]]
        add(8, _record("MODEL_RESULT", "DERIVED", end, end,
                       ["CHANNEL_QUALITY", f"CHANNEL:{q['channel']}", "LONGEST_CONTIGUOUS_RUN",
                        *(["RAILED"] if q["railed_fraction"] > 0.01 else [])],
                       stream_id="channel_quality", sequence=i,
                       payload=_finite({k: v for k, v in q.items() if k not in ("stream", "channel", "ranges")}),
                       source_stream_ids=[stream.name], source_sequence_ranges=q["ranges"] or an.ranges(stream)))
    for window in results.get("hrv", []):
        add(9, _record("MODEL_RESULT", "MODEL_INFERRED", window["t0"], window["t1"],
                       ["HRV_WINDOW", "RMSSD_SUCCESSIVE_ECG_R_PEAKS", "INTERVALS_FROM_ADC_SAMPLE_INDEX",
                        "LINEAGE:WINDOW_ATTRIBUTION", "OFFLINE_AFTER_ACQUISITION", "NOT_A_DIAGNOSIS"],
                       stream_id="hrv_windows", payload=window["payload"],
                       decision_time_us=max(window["decided"], window["t1"]), input_cutoff_us=window["t1"],
                       source_stream_ids=[window["ranges"][0]["stream_id"]], source_sequence_ranges=window["ranges"],
                       model={"name": "CYTON_ECG_R_PEAK_RMSSD", "version": BRIDGE_VERSION, "artifact_id": mid}))
    counts: dict[str, float] = {f"samples_{name}": len(s) for name, s in raw.streams.items()}
    counts.update({"gaps": len(raw.gaps), "ingestion_faults": len(core.ingestor.faults),
                   "input_contract_faults": len(capability_problems(caps)), "events": len(raw.events),
                   "evaluations": 0, "interventions": 0, "epochs": core.streams.epochs})
    add(99, _record("SESSION_TRAILER", info.provenance, max(info.end_us, end), max(info.end_us, end),
                    [mode, f"TERMINATED:{session.terminated}", "NO_EVALUATIONS", "NO_INTERVENTIONS"],
                    stream_id="session", payload=counts))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [seal_record(record) for _, _, record in ordered]


def analyze(raw: RawSession, core: CytonCore, session: Session) -> dict[str, Any]:
    """Every result computed from the raw records (and the clocks built from their receipts)."""
    clocks = core.streams.clocks
    observed = [e for e in raw.events if e.stream_id == MARKER_STREAM]
    probes: list[tuple[int, int, int]] = []
    sent = {code: [t for c, t in core.probes_sent if c == code] for code in PROBE_CODES}
    for event in observed:
        code = int(event.attribute("code") or 0)
        epoch, index = int(event.attribute("epoch") or 0), int(event.attribute("sample_index") or 0)
        queue = [t for t in sent.get(code, []) if t <= event.device_time_us + LATENCY_BOUND_US]
        if queue:
            t = queue[0]
            sent[code].remove(t)
            probes.append((epoch, index, t))
    results: dict[str, Any] = {"clock": an.clock_bounds(clocks, probes), "probes_paired": len(probes),
                               "probes_sent": len(core.probes_sent), "markers_observed": len(observed)}
    if session.plan.mode == "PHANTOM":
        results["phantom"] = an.phantom_scorecard(raw, session.segments, clocks, probes,
                                                  session.setup.register_problems)
    else:
        results["quality"] = an.channel_quality(raw)
        if session.plan.ecg_channel:
            ecg = an.ecg_beats(raw, session.plan.ecg_channel, clocks)
            results["ecg"] = {"channel": ecg["channel"], "beats": len(ecg["beats"]),
                              "beat_sample_index": [round(b["sample_index"], 3) for b in ecg["beats"]],
                              "beat_epoch": [b["epoch"] for b in ecg["beats"]]}
            results["hrv"] = an.hrv_windows(raw, ecg)
            results["_beats_us"] = [b["time_us"] for b in ecg["beats"]]
    return results


def _private(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def write_session(directory: Path, raw: RawSession, core: CytonCore, session: Session, info: SessionInfo,
                  results: dict[str, Any], pump_report: Any = None) -> dict[str, Any]:
    """session.ndjson, raw/*.csv.gz bound by SHA-256, analysis.json, passport.txt, and manifest.json; owner-only."""
    directory = Path(directory)
    (directory / "raw").mkdir(parents=True, exist_ok=True)
    for folder in (directory, directory / "raw"):
        _private(folder, 0o700)
    documents: dict[str, bytes] = {}
    raw_entries: dict[str, dict[str, Any]] = {}
    for name, stream in raw.streams.items():
        content = _csv_bytes(stream, core.streams.columns[name])
        packed = gzip.compress(content, compresslevel=9, mtime=0)
        documents[f"raw/{name}.csv.gz"] = packed
        raw_entries[f"raw/{name}.csv.gz"] = {"sha256": hashlib.sha256(packed).hexdigest(),
                                             "content_sha256": hashlib.sha256(content).hexdigest(),
                                             "rows": len(stream), "bytes": len(packed)}
    records = build_records(raw, core, session, info, raw_entries, results)
    validate_session(records)
    documents["session.ndjson"] = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n"
                                          for r in records).encode("utf-8")
    public = {k: v for k, v in results.items() if not k.startswith("_")}
    documents["analysis.json"] = dumps(_jsonable(public))
    phantom = results.get("phantom")
    human = ("YES: biopotentials (and motion) of the person wearing the electrodes (consent attested)"
             if info.human_data else "NONE (internal test conditions only, accelerometer off)"
             if session.plan.mode == "PHANTOM" else "NONE")
    extra = {"SOURCE": "OpenBCI Cyton" + (" + Daisy" if core.layout.daisy else "") +
                       (" (simulated)" if info.provenance == "SIMULATED" else ""),
             "FIRMWARE": session.setup.version or "unknown", "HUMAN DATA": human, "TERMINATED": session.terminated,
             "HARDWARE DRIVEN": "board configuration commands only (listed in the header); nothing actuated",
             "CLOSED LOOP": "not eligible (input contract unmet; see FAULT records)"}
    if phantom:
        failed = [c["id"] for c in phantom["checks"] if c["status"] == "FAIL"]
        extra["PHANTOM"] = phantom["verdict"] + (f" ({', '.join(failed)})" if failed else "")
    if results.get("clock"):
        longest = max(results["clock"], key=lambda b: b["duration_s"])
        extra["SAMPLE CLOCK"] = f"{1e6 / longest['slope_us']:.4f} Hz ({longest['ppm']:+.0f} ppm against the host clock)"
    documents["passport.txt"] = passport_text(passport(records, extra)).encode("utf-8")
    for name, data in documents.items():
        (directory / name).write_bytes(data)
        _private(directory / name, 0o600)
    setup = session.setup
    manifest = {
        "schema": "circle-live-acquisition/1", "release_class": "ENGINEERING_REVIEW_ONLY",
        "provenance": info.provenance, "terminated": session.terminated, "protocol_reference": p.PROTOCOL_REFERENCE,
        "bridge_version": BRIDGE_VERSION, "plan": {"mode": session.plan.mode, "segments": list(session.plan.segments),
                                                   "board_mode": session.plan.board_mode,
                                                   "probe_interval_s": session.plan.probe_interval_s,
                                                   "ecg_channel": session.plan.ecg_channel},
        "capabilities": cyton_capabilities(core.layout, info.provenance, info.hardware,
                                           "SESSION_ENDED:" + session.terminated, setup.version).to_dict(),
        "closed_loop_refusal": capability_problems(cyton_capabilities(core.layout, info.provenance, info.hardware, "",
                                                                      setup.version)),
        "board": {"banner": None if setup.banner is None else {
                      "ads_id": setup.banner.ads_id, "daisy_ads_id": setup.banner.daisy_ads_id,
                      "lis3dh_id": setup.banner.lis3dh_id, "banner_firmware": setup.banner.banner_firmware},
                  "version": setup.version, "dongle": setup.dongle, "commands": setup.commands,
                  "registers": setup.registers, "register_problems": setup.register_problems,
                  "stale_packets_discarded_before_start": setup.stale_packets_discarded,
                  "replies_during_setup": setup.replies, "replies_during_acquisition": core.replies},
        "segments": session.segments, "ingestion": core.ingestor.summary(),
        "framing": {"packets": core.framer.packets, "bytes_discarded": dict(core.discarded),
                    "packet_types": dict(core.streams.packet_types), "duplicates_ignored": core.streams.duplicates,
                    "lost_packets_declared": core.streams.lost_packets, "epochs": core.streams.epochs,
                    "inbox_overflow": core.inbox_overflow},
        "link_states": [e.kind for e in core.monitor.events], "software_revision": software_revision(),
        **info.details,
        "artifacts": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                      for name, data in sorted(documents.items())},
    }
    if pump_report is not None:
        manifest["pump"] = {"received": pump_report.received, "dropped_chunks": pump_report.dropped_chunks,
                            "dropped_other": pump_report.dropped_other,
                            "outcomes": dict(sorted(pump_report.outcomes.items()))}
    (directory / "manifest.json").write_bytes(dumps(_jsonable(manifest)))
    _private(directory / "manifest.json", 0o600)
    return manifest


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    return value


# ------------------------------------------------------------- serial port
class SerialPort:
    """A real dongle through pyserial (imported only here)."""

    def __init__(self, device: str) -> None:
        import serial  # noqa: PLC0415 - optional dependency

        self.device = device
        self.port = serial.Serial(device, p.BAUD_RATE, timeout=0.05)

    def write(self, data: bytes) -> None:
        self.port.write(data)
        self.port.flush()

    def read(self, timeout_s: float) -> bytes:
        self.port.timeout = timeout_s
        first = self.port.read(1)
        if not first:
            return b""
        waiting = self.port.in_waiting
        return first + (self.port.read(waiting) if waiting else b"")

    def close(self) -> None:
        self.port.close()


def usb_latency_timer_ms(device: str) -> int | None:
    """Linux only: the FTDI latency timer of a /dev/ttyUSB* port (OpenBCI recommends 1 ms; the default is 16)."""
    path = Path("/sys/bus/usb-serial/devices") / Path(device).name / "latency_timer"
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def monotonic_us() -> int:
    return time.monotonic_ns() // 1000
