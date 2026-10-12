"""The dongle's byte stream in, packets and text out. No I/O, no clock.

The host reads an undifferentiated byte stream from the dongle's USB serial
port: 33-byte stream packets (0xA0 ... 0xCX) and ASCII text ending in "$$$".
`Framer` splits it without trusting anything it has not checked:

  * A packet is 0xA0, 31 bytes, and a stop byte whose high nibble is 0xC, the
    same test the radios apply (isATailByte).
  * After any byte had to be discarded, a candidate packet is accepted only
    when the byte after it starts another packet, when its counter continues
    the last accepted packet's (one to four ahead), or when the stream is
    flushed: 0xA0 appears inside channel data, and a stray 0xA0 followed 32
    bytes later by a 0xCX byte is otherwise one chance in sixteen.
  * Bytes outside packets are text when printable ASCII; text is released at
    each "$$$". Anything else is counted as discarded, never guessed at.

`decode_channels` and the aux helpers read a packet the way the firmware wrote
it (sendChannelDataSerial and the board-mode branches of updateChannelData).
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

import numpy as np

from . import protocol as p


@dataclass(frozen=True)
class Packet:
    """One stream packet as the dongle delivered it."""

    counter: int
    channels: tuple[int, ...]       # eight signed 24-bit codes, channel order as sent
    aux: bytes                      # six bytes, meaning set by packet type and board mode
    stop_byte: int
    raw: bytes

    @property
    def packet_type(self) -> int:
        return self.stop_byte & 0x0F

    @property
    def type_name(self) -> str:
        return p.PACKET_TYPE_NAMES.get(self.packet_type, f"UNKNOWN_0x{self.stop_byte:02X}")

    def aux_words(self) -> tuple[int, int, int]:
        """AUX1..3 as the signed 16-bit big-endian words the firmware wrote (writeAuxDataSerial)."""
        return struct.unpack(">hhh", self.aux)

    def accel(self) -> tuple[int, int, int] | None:
        """ACCEL packets: the LIS3DH reading, or None when the triple is the firmware's zero fill."""
        if self.packet_type != p.PACKET_ACCEL:
            return None
        words = self.aux_words()
        return None if words == (0, 0, 0) else words

    def board_millis(self) -> int | None:
        """Time-stamped packets: the board's millis() at the data-ready that produced this sample."""
        if self.packet_type not in p.TIME_STAMPED_TYPES:
            return None
        return struct.unpack(">I", self.aux[2:6])[0]

    def time_sync_word(self) -> int:
        """Time-stamped packets: the two bytes ahead of the time stamp (one accel axis, or AUX1)."""
        return struct.unpack(">h", self.aux[:2])[0]


@dataclass(frozen=True)
class Text:
    """Text between packets: a board reply or a dongle message, ending in "$$$" unless the stream ended first."""

    text: str
    complete: bool


@dataclass(frozen=True)
class Discarded:
    """Bytes that were neither a checked packet nor text."""

    count: int
    reason: str


def decode_channels(raw: bytes) -> tuple[int, ...]:
    """Eight 24-bit big-endian two's-complement codes from bytes 2..25 of a packet (updateBoardData)."""
    return tuple(int.from_bytes(raw[2 + 3 * i:5 + 3 * i], "big", signed=True) for i in range(p.CHANNELS_PER_ADS))


def decode_packet(raw: bytes) -> Packet:
    if len(raw) != p.PACKET_SIZE or raw[0] != p.START_BYTE or raw[-1] >> 4 != p.STOP_NIBBLE >> 4:
        raise ValueError("not a dongle stream packet")
    return Packet(raw[1], decode_channels(raw), bytes(raw[26:32]), raw[32], bytes(raw))


def channel_matrix(packets: list[Packet]) -> np.ndarray:
    """All packets' channel codes as an (n, 8) int64 array."""
    if not packets:
        return np.zeros((0, p.CHANNELS_PER_ADS), dtype=np.int64)
    data = np.frombuffer(b"".join(pk.raw[2:26] for pk in packets), dtype=np.uint8).reshape(len(packets), 8, 3)
    words = (data[:, :, 0].astype(np.int64) << 16) | (data[:, :, 1].astype(np.int64) << 8) | data[:, :, 2]
    return np.where(words >= 1 << 23, words - (1 << 24), words)


def encode_packet(counter: int, channels: tuple[int, ...] | list[int], aux: bytes = bytes(6),
                  packet_type: int = p.PACKET_ACCEL) -> bytes:
    """A packet as the dongle writes it; used by the simulator and the tests."""
    if len(channels) != p.CHANNELS_PER_ADS or len(aux) != p.AUX_BYTES:
        raise ValueError("a packet carries eight channels and six aux bytes")
    body = b"".join((int(c) & 0xFFFFFF).to_bytes(3, "big") for c in channels)
    return bytes([p.START_BYTE, counter & 0xFF]) + body + bytes(aux) + bytes([p.STOP_NIBBLE | (packet_type & 0x0F)])


def _printable(byte: int) -> bool:
    return byte in (0x09, 0x0A, 0x0D) or 0x20 <= byte <= 0x7E


class Framer:
    """Incremental splitter for the dongle's byte stream."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.text = bytearray()
        self.resync = False
        self.packets = 0
        self.discarded = 0
        self.last_counter: int | None = None

    def feed(self, data: bytes) -> list[Packet | Text | Discarded]:
        self.buffer.extend(data)
        return self._split(final=False)

    def flush(self) -> list[Packet | Text | Discarded]:
        """The stream ended: release what is left, judged without a following packet."""
        out = self._split(final=True)
        if self.buffer:
            self.discarded += len(self.buffer)
            out.append(Discarded(len(self.buffer), "TRUNCATED_AT_END"))
            self.buffer.clear()
        if self.text:
            out.append(Text(self.text.decode("ascii"), False))
            self.text.clear()
        return out

    def _split(self, final: bool) -> list[Packet | Text | Discarded]:
        out: list[Packet | Text | Discarded] = []
        buf, n, i, junk = self.buffer, len(self.buffer), 0, 0

        def release_junk() -> None:
            nonlocal junk
            if junk:
                out.append(Discarded(junk, "NOT_A_PACKET_OR_TEXT"))
                self.discarded += junk
                junk = 0

        while i < n:
            head = buf[i]
            if head == p.START_BYTE:
                end = i + p.PACKET_SIZE
                if end > n:
                    break                                       # wait for the rest of the packet
                if buf[end - 1] >> 4 != p.STOP_NIBBLE >> 4:
                    junk, i, self.resync = junk + 1, i + 1, True
                    continue
                if self.resync:
                    follows = self.last_counter is not None and 1 <= (buf[i + 1] - self.last_counter) % 256 <= 4
                    if not follows and end == n and not final:
                        break                                   # wait for the next byte to confirm
                    if not follows and end < n and buf[end] != p.START_BYTE:
                        junk, i = junk + 1, i + 1
                        continue
                release_junk()
                out.append(decode_packet(bytes(buf[i:end])))
                self.last_counter = buf[i + 1]
                self.packets += 1
                self.resync = False
                i = end
                continue
            if _printable(head):
                release_junk()
                self.text.append(head)
                i += 1
                if self.text.endswith(p.EOT):
                    out.append(Text(self.text.decode("ascii"), True))
                    self.text.clear()
                continue
            junk, i, self.resync = junk + 1, i + 1, True
        release_junk()
        del buf[:i]
        return out
