"""A deterministic Cyton, its radios, and the dongle's USB port, on a virtual clock, with known truth.

This is CIRCLE's test bench for the Cyton bridge: no board, no dongle, no
pyserial. It follows the pinned firmware where the bridge depends on it:

  commands     the subset of processChar CIRCLE sends, with the firmware's own
               reply text and EOT, multi-character commands of exactly the
               firmware's lengths, replies suppressed while streaming, and
               stream-safe changes that stop and restart the ADC (restarting
               the counter)
  packets      0xA0, counter, eight 24-bit codes, aux, 0xC0 | type, as the
               dongle writes them; accelerometer words zeroed after each ACCEL
               packet; analog, digital, and marker aux words by board mode;
               time-stamped packet types with board millis(); the Daisy's
               alternating, two-sample-averaged halves, including the stale
               average in the first daisy half after each ADC start
  clocks       the ADS1299 runs on its own oscillator (drift_ppm from nominal);
               the internal test signal shares that clock, so its edges fall at
               exact sample counts; the LIS3DH runs on a third clock
  transport    radio latency and loss, radio dropouts, a USB serial converter
               that sends 62-byte transfers or flushes on its latency timer,
               USB stalls, corrupted bytes, and stray bytes

Every rendered value comes from a stated truth (EEG-like background, an ECG on
a chosen channel with known R-peak times, a pulse sensor and a skin
conductance sensor on the analog pins, a 1 Hz TTL on D17, the datasheet test
signal), recorded in `truth` for scoring. The truth never enters a session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math

import numpy as np

from . import protocol as p
from .framing import encode_packet


@dataclass(frozen=True)
class Scenario:
    seed: int = 7
    drift_ppm: float = 1800.0                     # ADS1299 oscillator against the host clock
    accel_drift_ppm: float = -9000.0              # LIS3DH oscillator
    millis_drift_ppm: float = 30.0                # PIC32 millis() timer
    daisy: bool = False
    radio_latency_us: tuple[int, int] = (600, 2600)
    radio_loss: float = 0.0                       # independent loss probability per stream packet
    dropouts_s: tuple[tuple[float, float], ...] = ()       # radio silent: stream packets lost
    usb_stalls_s: tuple[tuple[float, float], ...] = ()     # USB transfers held, then delivered together
    corrupt_packets: tuple[int, ...] = ()         # ordinals (from power-on) whose stop byte is damaged on USB
    phantom_packets: tuple[int, ...] = ()         # after these ordinals, a packet the counter counts but the ADC never
                                                  # took (a firmware fault): a negative control for the phantom
    ignore_channel_commands: bool = False         # replies "Success" but leaves CHnSET alone (a fault read-back catches)
    stray_bytes: tuple[tuple[float, bytes], ...] = ()      # bytes the USB stream carries at a time
    power_off_s: float | None = None              # the board stops answering and streaming
    usb_transfer_bytes: int = 62
    latency_timer_us: int = 16_000
    ecg_channel: int | None = 2                   # 1-based; None: no ECG
    heart_rate_bpm: float = 64.0
    railed_channel: int | None = None             # electrode offset beyond the gain-24 input range
    eeg_alpha_uv: float = 18.0


@dataclass
class Truth:
    """What the simulated world did; for scoring only."""

    drdy_us: dict[tuple[int, int], float] = field(default_factory=dict)      # (segment, sample index) -> host time
    beats_s: list[float] = field(default_factory=list)                       # ECG R-peaks, host seconds
    pulse_transit_s: float = 0.21
    segments: list[dict] = field(default_factory=list)
    lost_in_air: list[tuple[int, int]] = field(default_factory=list)         # (segment, sample index)
    accel: list[tuple[int, int, tuple[int, int, int]]] = field(default_factory=list)   # (segment, index, xyz)
    markers: list[tuple[int, int, int]] = field(default_factory=list)        # (segment, index, code)
    sync_edges_s: list[float] = field(default_factory=list)


_BANNER = ("OpenBCI V3 8-16 channel\nOn Board ADS1299 Device ID: 0x3E\n{daisy}LIS3DH Device ID: 0x33\n"
           "Firmware: v3.1.2\n$$$")


class SimulatedCyton:
    """The board and its radios as the host's serial port sees them."""

    def __init__(self, scenario: Scenario = Scenario()) -> None:
        self.s = scenario
        self.rng = np.random.default_rng(scenario.seed)
        self.truth = Truth()
        self.period_us = p.NOMINAL_PERIOD_US * (1 + scenario.drift_ppm * 1e-6)
        self.fclk_hz = p.FCLK_HZ / (1 + scenario.drift_ppm * 1e-6)
        self._events: list[tuple[float, int, str, object]] = []
        self._order = 0
        self._usb_pending = bytearray()
        self._usb_first_us: float | None = None
        self._deliveries: list[tuple[float, bytes]] = []
        self._ordinal = 0
        self.daisy_present = scenario.daisy
        self.channel_offsets_uv = self.rng.uniform(-15_000, 15_000, 16)
        self.shorted_offsets_uv = self.rng.uniform(-40, 40, 16)
        if scenario.railed_channel:
            self.channel_offsets_uv[scenario.railed_channel - 1] = 260_000
        self._beats(3600.0)
        self.sync_period_s = 1.0
        self._reset_state()
        self.board_mode = "default"
        self.time_sync = False
        self.powered = True
        for at, data in scenario.stray_bytes:
            self._push(at * 1e6, "usb", bytes(data))

    # --------------------------------------------------------------- truth
    def _beats(self, horizon_s: float) -> None:
        t, beats = 0.4, []
        while t < horizon_s:
            rr = 60.0 / self.s.heart_rate_bpm * (1 + 0.05 * math.sin(2 * math.pi * 0.25 * t)) \
                + float(self.rng.normal(0, 0.012))
            t += rr
            beats.append(t)
        self.truth.beats_s = beats
        self._beat_array = np.array(beats)

    def _ecg_uv(self, t: float) -> float:
        waves = ((-0.2, 0.025, 150.0), (-0.03, 0.01, -100.0), (0.0, 0.01, 1200.0), (0.03, 0.012, -250.0),
                 (0.25, 0.06, 300.0))
        i = int(np.searchsorted(self._beat_array, t))
        value = 0.0
        for b in self._beat_array[max(i - 2, 0):i + 2]:
            for shift, width, amp in waves:
                value += amp * math.exp(-0.5 * ((t - b - shift) / width) ** 2)
        return value + 100 * math.sin(2 * math.pi * 0.3 * t)

    def _pulse(self, t: float) -> float:
        i = int(np.searchsorted(self._beat_array, t - self.truth.pulse_transit_s))
        value = 0.0
        for b in self._beat_array[max(i - 2, 0):i + 1]:
            dt = t - b - self.truth.pulse_transit_s
            if dt >= 0:
                value += math.exp(-dt / 0.25) * (1 - math.exp(-dt / 0.04))
        return value

    def _channel_uv(self, channel: int, t: float, setting: dict) -> float:
        if setting["power_down"]:
            return 0.0
        kind = setting["input_type"]
        if kind == "SHORTED":
            return self.shorted_offsets_uv[channel] + float(self.rng.normal(0, p.NOISE_GAIN24_250SPS_UVRMS))
        if kind == "TESTSIG":
            return 0.0                                     # rendered from the clock in _render
        if kind != "NORMAL":
            return 0.0
        value = self.channel_offsets_uv[channel] + 3.0 * math.sin(2 * math.pi * 60 * t)
        value += float(self.rng.normal(0, 4.0))
        if self.s.ecg_channel is not None and channel == self.s.ecg_channel - 1:
            return value + self._ecg_uv(t)
        envelope = 1 + 0.5 * math.sin(2 * math.pi * 0.1 * t + channel)
        return value + self.s.eeg_alpha_uv * envelope * math.sin(2 * math.pi * 10.2 * t + 0.7 * channel)

    # ----------------------------------------------------------- the board
    def _reset_state(self) -> None:
        n = 16 if self.daisy_present else 8
        self.settings = [{"power_down": False, "gain": p.DEFAULT_GAIN, "input_type": "NORMAL", "bias": True,
                          "srb2": True, "srb1": False} for _ in range(n)]
        self.test_amp, self.test_freq = 1, "SLOW"
        self.streaming = False
        self.counter = 0
        self.segment = -1
        self.marker_pending: int | None = None
        self.axis = (0, 0, 0)
        self.axis_new = False
        self.held_axis = (0, 0, 0)
        self.time_sync_set = False
        self.last_board = np.zeros(8, dtype=np.int64)
        self.last_daisy = np.zeros(8, dtype=np.int64)
        self.mean_board = np.zeros(8, dtype=np.int64)
        self.mean_daisy = np.zeros(8, dtype=np.int64)

    def _push(self, at_us: float, kind: str, payload: object) -> None:
        heapq.heappush(self._events, (float(at_us), self._order, kind, payload))
        self._order += 1

    def write(self, data: bytes, at_us: float) -> None:
        """The host writes `data` to the dongle at host time at_us."""
        arrive = at_us + 500
        if data[:2] == p.DONGLE_SYS_UP:
            up = self.powered and not self._off(arrive)
            self._reply(arrive + 300, "Success: System is Up$$$" if up else "Failure: System is Down$$$", radio=False)
            return
        poll = p.NOMINAL_PERIOD_US if self.streaming else 48_000
        self._push(arrive + float(self.rng.uniform(500, 500 + poll)), "command", bytes(data))

    def _off(self, t_us: float) -> bool:
        return self.s.power_off_s is not None and t_us >= self.s.power_off_s * 1e6

    def _reply(self, at_us: float, text: str, radio: bool = True) -> None:
        if radio:
            at_us += float(self.rng.uniform(*self.s.radio_latency_us))
        self._push(at_us, "usb", text.encode("ascii"))

    def _process(self, data: bytes, t: float) -> None:
        if self._off(t):
            return
        i = 0
        while i < len(data):
            c = chr(data[i])
            need = {"x": 9, "z": 5, "/": 2, "~": 2, "`": 2}.get(c, 1)
            command = data[i:i + need]
            i += need
            self._command(command, t)

    def _command(self, command: bytes, t: float) -> None:
        c = chr(command[0])
        quiet = self.streaming
        if c == "b":
            self._start(t)
        elif c == "s":
            self.streaming = False
        elif c == "v":
            self.streaming = False
            self._reset_state()
            self._reply(t + 600_000, _BANNER.format(daisy="On Daisy ADS1299 Device ID: 0x3E\n" if self.daisy_present
                                                    else ""))
        elif c == "V":
            self._reply(t, "v3.1.5$$$")
        elif c == "?" and not self.streaming:
            self._reply(t + 400_000, self._register_dump())
        elif c == "d":
            if not quiet:
                self._reply(t, "updating channel settings to default$$$")
            self._restart_if_streaming(t, lambda: [s.update(power_down=False, gain=24, input_type="NORMAL", bias=True,
                                                            srb2=True, srb1=False) for s in self.settings])
        elif c == "D":
            self._reply(t, "060110$$$")
        elif c == "c":
            if self.daisy_present:
                self.daisy_present = False
                self.settings = self.settings[:8]
                if not quiet:
                    self._reply(t, "daisy removed$$$")
            elif not quiet:
                self._reply(t, "no daisy to remove!$$$")
        elif c == "C":
            attached = ""
            if not self.daisy_present:
                self.daisy_present = self.s.daisy
                if self.daisy_present:
                    self.settings += [dict(self.settings[0], power_down=False) for _ in range(8)]
                attached = "daisy attached" if self.daisy_present else "no daisy to attach!"
            self._reply(t, ("" if quiet else attached) + ("16" if self.daisy_present else "8") + "$$$")
        elif c in "<>":
            self.time_sync = c == "<"
            self.time_sync_set = False
            if not quiet:
                self._reply(t, f"Time stamp {'ON' if self.time_sync else 'OFF'}$$$")
        elif c in p.CHANNEL_OFF or c in p.CHANNEL_ON:
            n = (p.CHANNEL_OFF if c in p.CHANNEL_OFF else p.CHANNEL_ON).index(c)
            if n < len(self.settings):
                self._restart_if_streaming(t, lambda: self.settings[n].update(power_down=c in p.CHANNEL_OFF))
        elif any(c == ts.command.decode() for ts in p.TEST_SIGNALS.values()):
            ts = next(ts for ts in p.TEST_SIGNALS.values() if ts.command.decode() == c)

            def apply() -> None:
                if ts.amplitude_k is not None:
                    self.test_amp, self.test_freq = ts.amplitude_k, ts.frequency
                for s in self.settings:
                    s["input_type"] = ts.input_type
            self._restart_if_streaming(t, apply)
            if not quiet:
                self._reply(t, "Success: Configured internal test signal.$$$")
        elif c == "x" and len(command) == 9 and command[-1:] == b"X":
            body = command.decode()
            n = p.CHANNEL_SELECT.index(body[1]) if body[1] in p.CHANNEL_SELECT else 0
            gain = {v: k for k, v in p.GAIN_CHARS.items()}.get(body[3], 24)
            kind = {v: k for k, v in p.INPUT_TYPES.items()}.get(body[4], "NORMAL")
            if n < len(self.settings) and not self.s.ignore_channel_commands:
                self._restart_if_streaming(t, lambda: self.settings[n].update(
                    power_down=body[2] == "1", gain=gain, input_type=kind, bias=body[5] == "1", srb2=body[6] == "1",
                    srb1=body[7] == "1"))
            if not quiet:
                self._reply(t, f"Success: Channel set for {n + 1}$$$")
        elif c == "z" and len(command) == 5:
            if not quiet:
                n = p.CHANNEL_SELECT.index(command.decode()[1]) if chr(command[1]) in p.CHANNEL_SELECT else 0
                self._reply(t, f"Success: Lead off set for {n + 1}$$$")
        elif c == "/" and len(command) == 2:
            arg = chr(command[1])
            if arg.isdigit() and int(arg) in p.BOARD_MODES:
                self.board_mode = p.BOARD_MODES[int(arg)]
            self._reply(t, f"Success: {self.board_mode}$$$")
        elif c == "~" and len(command) == 2:
            if not quiet:
                self._reply(t, "Success: Sample rate is 250Hz$$$")
        elif c == "`" and len(command) == 2:
            self.marker_pending = command[1]

    def _restart_if_streaming(self, t: float, change) -> None:
        was = self.streaming
        change()
        if was:
            self._start(t + 2_000)                         # streamStop + streamStart: the counter restarts

    def _register_dump(self) -> str:
        def ads(settings: list[dict]) -> str:
            values = {"ADS_ID": 0x3E, "CONFIG1": (0xB0 if self.daisy_present else 0x90) | 6,
                      "CONFIG2": 0xD0 | (0x04 if self.test_amp == 2 else 0) | {"SLOW": 0, "FAST": 1, "DC": 3}[self.test_freq],
                      "CONFIG3": 0xEC, "LOFF": 0x02}
            for i, s in enumerate(settings[:8]):
                values[f"CH{i + 1}SET"] = p.channel_register_value(s["power_down"], s["gain"], s["input_type"], s["srb2"])
            return p.register_dump_lines(values)
        text = "\nBoard ADS Registers\n" + ads(self.settings[:8])
        if self.daisy_present:
            text += "\nDaisy ADS Registers\n" + ads(self.settings[8:])
        return text + "\nLIS3DH Registers\n0x07 00\n0x0F 33\n$$$"

    # ------------------------------------------------------------ streaming
    def _start(self, t: float) -> None:
        self.streaming = True
        self.counter = 0
        self.segment += 1
        self.first_packet = True
        self.start_clock = int(round(t * 1e-6 * self.fclk_hz))
        self.sample_k = 0
        self.truth.segments.append({"segment": self.segment, "started_us": t, "board_mode": self.board_mode,
                                    "input_types": [s["input_type"] for s in self.settings],
                                    "gains": [s["gain"] for s in self.settings], "test_amp": self.test_amp,
                                    "test_freq": self.test_freq, "daisy": self.daisy_present})
        first = t + 4 * self.period_us
        self._push(first, "drdy", self.segment)
        if self.board_mode == "default":
            self.accel_period_us = 40_000 * (1 + self.s.accel_drift_ppm * 1e-6)
            self._push(first + float(self.rng.uniform(0, self.accel_period_us)), "lis3dh", self.segment)
        self.axis = (0, 0, 0)

    def _test_signal_uv(self, k: int) -> float:
        half = (2 ** 20 if self.test_freq == "SLOW" else 2 ** 19)
        amp_uv = self.test_amp * p.VREF_V / 2400 * 1e6
        if self.test_freq == "DC":
            return amp_uv
        end = self.start_clock + p.CLOCKS_PER_SAMPLE_250 * (k + 4)
        begin = end - p.CLOCKS_PER_SAMPLE_250

        def high_clocks(c: int) -> int:                  # clocks in [0, c) spent high (high on even half-periods)
            full, rem = divmod(c, 2 * half)
            return full * half + min(rem, half)
        frac = (high_clocks(end) - high_clocks(begin)) / p.CLOCKS_PER_SAMPLE_250
        return amp_uv * (2 * frac - 1)

    def _render(self, t: float, settings: list[dict], k: int, offset: int) -> np.ndarray:
        codes = np.zeros(8, dtype=np.int64)
        ts = t * 1e-6
        for i, s in enumerate(settings):
            uv = self._test_signal_uv(k) if s["input_type"] == "TESTSIG" and not s["power_down"] else \
                self._channel_uv(offset + i, ts, s)
            code = round(uv * 1e-6 * s["gain"] / p.VREF_V * p.ADC_MAX_CODE)
            codes[i] = min(max(code, p.ADC_MIN_CODE), p.ADC_MAX_CODE)
        return codes

    def _drdy(self, t: float, segment: int) -> None:
        if segment != self.segment or not self.streaming or self._off(t):
            return
        k = self.sample_k
        self.truth.drdy_us[(segment, k)] = t
        board = self._render(t, self.settings[:8], k, 0)
        daisy_codes = None
        if self.daisy_present:
            daisy_codes = self._render(t, self.settings[8:16], k, 8)
            if not self.first_packet:
                self.mean_board = (self.last_board + board) // 2
            self.mean_daisy = (self.last_daisy + daisy_codes) // 2   # first packet: averaged with a stale value
            self.last_board, self.last_daisy = board, daisy_codes
            channels = self.mean_board if self.counter % 2 else self.mean_daisy
        else:
            channels = board
        self.first_packet = False
        aux = self._aux(t, k, segment)
        packet_type = self._packet_type()
        if packet_type in p.TIME_STAMPED_TYPES:
            millis = int(t * 1e-3 * (1 + self.s.millis_drift_ppm * 1e-6)) & 0xFFFFFFFF
            if packet_type in (p.PACKET_ACCEL_TIME_SET, p.PACKET_ACCEL_TIME_SYNC):
                axis = p.TIME_SYNC_AXIS_BY_COUNTER_MOD_10.get(self.counter % 10)
                word = self.held_axis[axis] if axis is not None else 0
            else:
                word = int(np.frombuffer(aux[:2], ">i2")[0])
            aux = int(word).to_bytes(2, "big", signed=True) + millis.to_bytes(4, "big")
        raw = encode_packet(self.counter, [int(c) for c in channels], aux, packet_type)
        if self.time_sync and packet_type in (p.PACKET_ACCEL_TIME_SET, p.PACKET_RAW_AUX_TIME_SET):
            self.time_sync_set = True
        self._ordinal += 1
        if self._ordinal in self.s.corrupt_packets:
            raw = raw[:-1] + b"\x5a"
        lost = (self.rng.random() < self.s.radio_loss) or any(a * 1e6 <= t < b * 1e6 for a, b in self.s.dropouts_s)
        if lost:
            self.truth.lost_in_air.append((segment, k))
        else:
            self._push(t + float(self.rng.uniform(*self.s.radio_latency_us)), "usb", raw)
        if self._ordinal in self.s.phantom_packets:
            self.counter = (self.counter + 1) & 0xFF
            self._push(t + 1_000 + float(self.rng.uniform(*self.s.radio_latency_us)), "usb",
                       encode_packet(self.counter, [int(c) for c in channels], aux, packet_type))
        self.counter = (self.counter + 1) & 0xFF
        self.sample_k += 1
        self._push(t + self.period_us, "drdy", segment)

    def _packet_type(self) -> int:
        accel = self.board_mode == "default"
        if self.time_sync:
            first = not self.time_sync_set
            if accel:
                return p.PACKET_ACCEL_TIME_SET if first else p.PACKET_ACCEL_TIME_SYNC
            return p.PACKET_RAW_AUX_TIME_SET if first else p.PACKET_RAW_AUX_TIME_SYNC
        return p.PACKET_ACCEL if accel else p.PACKET_RAW_AUX

    def _aux(self, t: float, k: int, segment: int) -> bytes:
        ts = t * 1e-6
        if self.board_mode == "default":
            words = self.axis
            if self.axis_new:
                self.truth.accel.append((segment, k, words))
                self.held_axis = words
                self.axis_new = False
            if not self.time_sync:
                self.axis = (0, 0, 0)                        # LIS3DH_zeroAxisData after an ACCEL packet
        elif self.board_mode == "analog":
            ppg = 300 + 400 * self._pulse(ts) + float(self.rng.normal(0, 2))
            gsr = 420 + 60 * math.sin(2 * math.pi * ts / 47.0) + float(self.rng.normal(0, 1))
            words = (int(np.clip(round(ppg), 0, 1023)), int(np.clip(round(gsr), 0, 1023)), 0)
        elif self.board_mode == "digital":
            high = int(ts / self.sync_period_s * 2) % 2 == 0
            if high and (not self.truth.sync_edges_s or ts - self.truth.sync_edges_s[-1] > self.sync_period_s / 2):
                self.truth.sync_edges_s.append(ts)
            words = (0, int(high), 0)                        # D17 in the low byte of AUX2
        elif self.board_mode == "marker":
            words = (self.marker_pending or 0, 0, 0)
            if self.marker_pending:
                self.truth.markers.append((segment, k, self.marker_pending))
            self.marker_pending = None
        else:
            words = (0, 0, 0)
        return b"".join(int(w).to_bytes(2, "big", signed=True) for w in words)

    def _lis3dh(self, t: float, segment: int) -> None:
        if segment != self.segment or not self.streaming or self.board_mode != "default":
            return
        ts = t * 1e-6
        tilt = 0.15 * math.sin(2 * math.pi * ts / 9.0)
        motion = 0.4 * math.sin(2 * math.pi * 2.5 * ts) if 12 < ts % 30 < 14 else 0.0
        g = (math.sin(tilt) + float(self.rng.normal(0, 0.01)), motion + float(self.rng.normal(0, 0.01)),
             math.cos(tilt) + float(self.rng.normal(0, 0.01)))
        self.axis = tuple(int(round(v / p.ACCEL_G_PER_COUNT / 16)) * 16 for v in g)
        self.axis_new = True
        self._push(t + self.accel_period_us, "lis3dh", segment)

    # --------------------------------------------------------------- the USB
    def _usb_bytes(self, t: float, data: bytes) -> None:
        if not self._usb_pending:
            self._usb_first_us = t
        self._usb_pending.extend(data)
        size = self.s.usb_transfer_bytes
        while len(self._usb_pending) >= size:
            self._deliver(t, bytes(self._usb_pending[:size]))
            del self._usb_pending[:size]
            self._usb_first_us = t if self._usb_pending else None

    def _deliver(self, t: float, data: bytes) -> None:
        for a, b in self.s.usb_stalls_s:
            if a * 1e6 <= t < b * 1e6:
                t = b * 1e6
        if self._deliveries and t < self._deliveries[-1][0]:
            t = self._deliveries[-1][0]
        self._deliveries.append((t, data))

    def run_until(self, t_us: float) -> None:
        while True:
            flush_at = None if self._usb_first_us is None else self._usb_first_us + self.s.latency_timer_us
            nxt = self._events[0][0] if self._events else None
            if flush_at is not None and (nxt is None or flush_at <= nxt) and flush_at <= t_us:
                self._deliver(flush_at, bytes(self._usb_pending))
                self._usb_pending.clear()
                self._usb_first_us = None
                continue
            if nxt is None or nxt > t_us:
                return
            at, _, kind, payload = heapq.heappop(self._events)
            if kind == "command":
                self._process(payload, at)
            elif kind == "drdy":
                self._drdy(at, payload)
            elif kind == "lis3dh":
                self._lis3dh(at, payload)
            elif kind == "usb":
                self._usb_bytes(at, payload)

    def next_delivery_us(self, horizon_us: float) -> float | None:
        self.run_until(horizon_us)
        return self._deliveries[0][0] if self._deliveries else None

    def take(self, t_us: float) -> bytes:
        """Everything the USB delivered by t_us."""
        self.run_until(t_us)
        out = bytearray()
        while self._deliveries and self._deliveries[0][0] <= t_us:
            out.extend(self._deliveries.pop(0)[1])
        return bytes(out)


class VirtualClock:
    """Host microseconds for a simulated session: advanced only by reads, so runs are exact and fast."""

    def __init__(self, start_us: int = 1_000_000) -> None:
        self.now_us = int(start_us)

    def __call__(self) -> int:
        return self.now_us


class SimulatedPort:
    """The serial-port surface the bridge uses (write, read with a timeout, close), backed by a SimulatedCyton."""

    def __init__(self, board: SimulatedCyton, clock: VirtualClock) -> None:
        self.board, self.clock = board, clock
        self.closed = False
        self.written: list[tuple[int, bytes]] = []

    def write(self, data: bytes) -> None:
        if self.closed:
            raise OSError("port closed")
        self.written.append((self.clock(), bytes(data)))
        self.board.write(bytes(data), self.clock())

    def read(self, timeout_s: float) -> bytes:
        """Bytes from the first USB transfer within the timeout, and any others already delivered by then.

        The board is run ahead in steps of at most 1 ms, less than any command's
        trip to the board, so a write right after this read stays causal.
        """
        if self.closed:
            raise OSError("port closed")
        now = self.clock()
        horizon = now + timeout_s * 1e6
        t = now
        while True:
            step = min(horizon, t + 1_000)
            first = self.board.next_delivery_us(step)
            if first is not None and first <= step:
                self.clock.now_us = max(now, int(math.ceil(first)))
                return self.board.take(self.clock.now_us)
            if step >= horizon:
                self.clock.now_us = int(math.ceil(horizon))
                return b""
            t = step

    def close(self) -> None:
        self.closed = True
