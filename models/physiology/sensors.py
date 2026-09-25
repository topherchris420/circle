"""Forward models of the CIRCLE Rev B acquisition hardware and firmware timing.

Each model turns twin physiology into what the firmware would record: integer
codes, sequence numbers, and native device timestamps. Values below come from
the Rev B design documents where they exist and are otherwise labeled
assumptions (see docs/physiology-pipeline.md).

  EDA   ADS1220 24-bit ADC. Four-wire electrode path with 0.500 V excitation
        through the 4 x 49.9 kOhm series limit network (199.6 kOhm total);
        the ADC senses the voltage across that network (loop current). PGA
        gain 4 with the REF5020 2.048 V reference. The ADS1220 has no native
        64 SPS rate, so 64 SPS is modeled as timer-triggered single-shot
        conversions at the 90 SPS setting (11.2 ms conversion, DRDY captured).
  PPG   MAX30102 red (660 nm) / IR (880 nm), 18-bit, 100 SPS from its own
        oscillator, 32-sample FIFO with an almost-full interrupt at 16
        samples and FIFO rollover disabled. Overflow drops the newest samples
        and counts them in the 5-bit OVF_COUNTER.
  IMU   ICM-42688-P at 400 SPS (+/-4 g, +/-500 dps, 16-bit), DRDY captured.
  SYNC  Isolated SYNC_IN capture of a laboratory 1 PPS reference (GPIO1).
  HAPTIC DRV2605L + LRA; TLV3201 current-edge comparator captured on GPIO46.

Firmware timestamping follows docs/timing-and-data-model.md: DRDY and INT
edges are hardware-captured in device time; PPG sample times are
reconstructed from FIFO interrupt anchors with a tracked sample period.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .streams import DeviceEvent, Gap, RawSession, Stream, STREAM_COLUMNS
from .twin import PhysiologyTwin

EDA_EXCITATION_V = 0.500
EDA_SERIES_LIMIT_OHM = 4 * 49.9e3
EDA_VREF_V = 2.048
EDA_PGA_GAIN = 4.0
EDA_BITS = 24
EDA_CONVERSION_US = 11_200
PPG_FULL_SCALE = 2**18 - 1
IMU_ACCEL_LSB_PER_G = 8192.0
IMU_GYRO_LSB_PER_DPS = 65.5


def optical_ratio_of_ratios(spo2_pct: np.ndarray) -> np.ndarray:
    """The twin's 'true' tissue optics: R as a function of SpO2.

    Deliberately NOT the inverse of the pipeline's uncalibrated 110 - 25 R
    curve, so SpO2 scores include a realistic calibration bias instead of
    rewarding an inverse crime.
    """
    return (112.0 - np.asarray(spo2_pct, dtype=np.float64)) / 26.5


@dataclass(frozen=True)
class RigConfig:
    device_boot_offset_s: float = 7.316
    device_clock_ppm: float = 23.7
    imu_rate_hz: float = 400.0
    imu_clock_error_ppm: float = 1100.0
    eda_rate_hz: float = 64.0
    ppg_rate_hz: float = 100.0
    ppg_clock_error_ppm: float = -3500.0
    ppg_fifo_depth: int = 32
    ppg_fifo_threshold: int = 16
    ppg_fifo_stall_at_s: float | None = 185.0
    ppg_fifo_stall_s: float = 0.40
    ppg_dc_ir_counts: float = 96_000.0
    ppg_dc_red_counts: float = 71_000.0
    ppg_perfusion_index_ir: float = 0.018
    haptic_lra_hz: float = 170.0
    haptic_accel_g: float = 0.09
    haptic_pulse_s: float = 0.060
    haptic_rise_s: float = 0.004

    def __post_init__(self) -> None:
        if not 0 < self.ppg_fifo_threshold < self.ppg_fifo_depth:
            raise ValueError("FIFO threshold must lie inside the FIFO depth")
        if self.ppg_fifo_stall_at_s is not None:
            if self.ppg_fifo_stall_s <= 0:
                raise ValueError("ppg_fifo_stall_s must be positive")
            space = self.ppg_fifo_depth - self.ppg_fifo_threshold
            lost = self.ppg_fifo_stall_s * self.ppg_rate_hz - space
            # OVF_COUNTER saturates at 31; beyond that the loss count is not observable.
            if lost >= 31:
                raise ValueError("FIFO stall would saturate OVF_COUNTER; loss count would be unobservable")
        if 1e6 / self.eda_rate_hz <= EDA_CONVERSION_US:
            raise ValueError("EDA rate leaves no time for the single-shot conversion")


@dataclass(frozen=True)
class DeviceClock:
    boot_offset_s: float
    ppm: float

    def to_device_us(self, t_true_s: np.ndarray | float) -> np.ndarray:
        return (self.boot_offset_s + np.asarray(t_true_s, dtype=np.float64) * (1 + self.ppm * 1e-6)) * 1e6

    def to_true_s(self, device_us: np.ndarray | float) -> np.ndarray:
        return (np.asarray(device_us, dtype=np.float64) / 1e6 - self.boot_offset_s) / (1 + self.ppm * 1e-6)


@dataclass(frozen=True)
class HapticOutcome:
    command: DeviceEvent
    electrical_onset: DeviceEvent | None
    completion: DeviceEvent | None
    truth: dict[str, float]


def _capture_latency_us(rng: np.random.Generator, n: int) -> np.ndarray:
    """Edge-capture latency assumption: 1.5 us + Exp(1.2 us), bounded at 25 us."""
    return np.minimum(1.5 + rng.exponential(1.2, n), 25.0)


def descriptors(config: RigConfig) -> dict[str, dict[str, float]]:
    """Numeric stream constants recorded in STREAM_DESCRIPTOR payloads."""
    return {
        "eda": {"nominal_rate_hz": config.eda_rate_hz, "adc_bits": EDA_BITS, "vref_v": EDA_VREF_V,
                "pga_gain": EDA_PGA_GAIN, "excitation_v": EDA_EXCITATION_V,
                "series_limit_ohm": EDA_SERIES_LIMIT_OHM,
                "timestamp_minus_sample_center_us": EDA_CONVERSION_US / 2},
        "ppg": {"nominal_rate_hz": config.ppg_rate_hz, "adc_bits": 18, "full_scale_counts": PPG_FULL_SCALE,
                "fifo_depth": config.ppg_fifo_depth, "fifo_interrupt_threshold": config.ppg_fifo_threshold,
                "red_wavelength_nm": 660, "ir_wavelength_nm": 880},
        "imu": {"nominal_rate_hz": config.imu_rate_hz, "accel_lsb_per_g": IMU_ACCEL_LSB_PER_G,
                "gyro_lsb_per_dps": IMU_GYRO_LSB_PER_DPS, "accel_full_scale_g": 4, "gyro_full_scale_dps": 500},
        "sync": {"nominal_period_s": 1.0},
    }


class SensorRig:
    """Renders twin physiology into Rev B raw records, chunk by chunk."""

    def __init__(self, twin: PhysiologyTwin, config: RigConfig | None = None) -> None:
        self.twin = twin
        self.config = config or RigConfig()
        c = self.config
        self.clock = DeviceClock(c.device_boot_offset_s, c.device_clock_ppm)
        duration = twin.config.duration_s
        seeds = np.random.SeedSequence([twin.config.seed, 0xC12C1E]).spawn(7)
        (self._rng_imu, self._rng_eda, self._rng_ppg, self._rng_sync, self._rng_haptic,
         self._rng_fifo, self._rng_events) = (np.random.default_rng(s) for s in seeds)

        # --- IMU: own oscillator, DRDY edge captured.
        imu_period = 1.0 / (c.imu_rate_hz * (1 + c.imu_clock_error_ppm * 1e-6))
        n_imu = int(math.floor((duration - 0.0013) / imu_period))
        self.imu_t = 0.0013 + np.arange(n_imu) * imu_period
        self.imu_edge_dev_exact = self.clock.to_device_us(self.imu_t)
        self.imu_dev = np.floor(self.imu_edge_dev_exact + _capture_latency_us(self._rng_imu, n_imu)).astype(np.int64)
        self.imu_noise = self._rng_imu.standard_normal((n_imu, 6))
        self.imu_accel_bias = np.array([0.012, -0.008, 0.015])
        self.imu_gyro_bias = np.array([0.4, -0.25, 0.1])

        # --- EDA: device-timer-triggered single-shot conversions.
        period_us = int(round(1e6 / c.eda_rate_hz))
        first = int(math.ceil(self.clock.to_device_us(0.004) / period_us)) * period_us
        n_eda = int(math.floor((self.clock.to_device_us(duration - 0.02) - first - EDA_CONVERSION_US) / period_us))
        trigger_true = self.clock.to_true_s(first + np.arange(n_eda) * period_us)
        drdy_true = trigger_true + EDA_CONVERSION_US * 1e-6
        self.eda_t = trigger_true + EDA_CONVERSION_US * 0.5e-6
        self.eda_edge_dev_exact = self.clock.to_device_us(drdy_true)
        self.eda_dev = np.floor(self.eda_edge_dev_exact + _capture_latency_us(self._rng_eda, n_eda)).astype(np.int64)
        self.eda_noise = self._rng_eda.standard_normal((n_eda, 2))

        # --- PPG: sensor oscillator, FIFO with interrupt-anchored timestamps.
        self.ppg_period_true = 1.0 / (c.ppg_rate_hz * (1 + c.ppg_clock_error_ppm * 1e-6))
        n_ppg = int(math.floor((duration - 0.002) / self.ppg_period_true))
        self.ppg_all_t = 0.002 + np.arange(n_ppg) * self.ppg_period_true
        self._simulate_ppg_fifo()
        self.ppg_noise = self._rng_ppg.standard_normal((len(self.ppg_seq), 2))
        self._ppg_wander_phase = float(self._rng_ppg.uniform(0, 2 * math.pi))

        # --- SYNC: 1 PPS laboratory reference captured through the isolator.
        pulses = np.arange(1, int(math.floor(duration - 0.5)) + 1, dtype=np.float64)
        jitter_us = 0.015 + self._rng_sync.normal(0.0, 0.05, len(pulses))
        self.sync_t = pulses
        self.sync_dev = np.floor(self.clock.to_device_us(pulses) + jitter_us).astype(np.int64)

        # Rendered codes, filled progressively.
        self.imu_codes = np.zeros((n_imu, 6), dtype=np.int64)
        self.eda_codes = np.zeros(n_eda, dtype=np.int64)
        self.ppg_codes = np.zeros((len(self.ppg_seq), 2), dtype=np.int64)
        self._rendered = {"imu": 0, "eda": 0, "ppg": 0, "sync": 0}
        self.horizon_s = 0.0
        self.events: list[DeviceEvent] = []
        self._event_sequences: dict[str, int] = {}
        self.vibrations: list[dict[str, float]] = []
        self.haptic_truth: list[dict[str, float]] = []

    # --------------------------------------------------------------- timing
    def _simulate_ppg_fifo(self) -> None:
        c = self.config
        t = self.ppg_all_t
        n = len(t)
        nominal_us = 1e6 / c.ppg_rate_hz
        period_est = nominal_us
        anchor: tuple[int, float] | None = None
        next_unread = 0
        stalled = False
        seqs: list[np.ndarray] = []
        stamps: list[np.ndarray] = []
        self.ppg_gaps: list[Gap] = []
        self.ppg_anchor_log: list[dict[str, float]] = []
        while True:
            s_int = next_unread + c.ppg_fifo_threshold - 1
            if s_int >= n:
                break
            edge_true = t[s_int] + 20e-6
            edge_dev = math.floor(float(self.clock.to_device_us(edge_true)) + float(_capture_latency_us(self._rng_fifo, 1)[0]))
            stall = (not stalled and c.ppg_fifo_stall_at_s is not None and edge_true >= c.ppg_fifo_stall_at_s)
            service = c.ppg_fifo_stall_s if stall else 0.0004 + 0.0011 * float(self._rng_fifo.random())
            stalled = stalled or stall
            produced_last = min(n - 1, int(np.searchsorted(t, edge_true + service, side="right")) - 1)
            unread = produced_last - next_unread + 1
            stored = min(unread, c.ppg_fifo_depth)
            lost = unread - stored
            if anchor is not None:
                observed = (edge_dev - anchor[1]) / (s_int - anchor[0])
                if abs(observed - period_est) < 0.05 * nominal_us:
                    period_est += 0.2 * (observed - period_est)
            batch = np.arange(next_unread, next_unread + stored)
            seqs.append(batch)
            stamps.append(np.round(edge_dev + (batch - s_int) * period_est).astype(np.int64))
            self.ppg_anchor_log.append({"sequence": s_int, "edge_device_us": edge_dev, "period_estimate_us": period_est})
            if lost:
                read_dev = int(math.floor(float(self.clock.to_device_us(edge_true + service))))
                first_lost = next_unread + stored
                self.ppg_gaps.append(Gap("ppg", int(first_lost), int(first_lost + lost - 1), read_dev,
                                         f"MAX30102_FIFO_OVERFLOW: OVF_COUNTER={min(lost, 31)}; "
                                         f"FIFO service stalled {service * 1e3:.0f} ms after almost-full interrupt"))
            next_unread += stored + lost
            anchor = (s_int, float(edge_dev))
        self.ppg_seq = np.concatenate(seqs).astype(np.int64)
        self.ppg_dev = np.concatenate(stamps)
        self.ppg_t = t[self.ppg_seq]
        self.ppg_edge_dev_exact = self.clock.to_device_us(self.ppg_t)

    def device_us(self, t_true_s: float) -> int:
        return int(math.floor(float(self.clock.to_device_us(t_true_s))))

    # --------------------------------------------------------------- events
    def log_event(self, stream_id: str, kind: str, device_time_us: int, **attributes: float) -> DeviceEvent:
        sequence = self._event_sequences.get(stream_id, 0)
        self._event_sequences[stream_id] = sequence + 1
        event = DeviceEvent(stream_id, sequence, kind, int(device_time_us), tuple(sorted(attributes.items())))
        self.events.append(event)
        return event

    def log_protocol_marker(self, kind: str, t_true_s: float) -> DeviceEvent:
        latency = 30.0 + float(self._rng_events.uniform(0, 20))
        return self.log_event("protocol_events", kind, int(math.floor(float(self.clock.to_device_us(t_true_s)) + latency)))

    def command_haptic(self, command_device_us: int, actuated: bool, program: int, index: int) -> HapticOutcome:
        """Issue a DRV2605L GO command; returns evidence events and hidden truth."""
        c = self.config
        t_cmd = float(self.clock.to_true_s(command_device_us))
        if t_cmd < self.horizon_s:
            raise ValueError("Haptic command precedes already-acquired data")
        kind = "HAPTIC_COMMAND" if actuated else "HAPTIC_COMMAND_SHAM"
        # The firmware knows its DRV2605L configuration: LRA frequency and pulse length.
        command = self.log_event("haptic_events", kind, command_device_us, program=program, cue_index=index,
                                 lra_hz=c.haptic_lra_hz, pulse_ms=c.haptic_pulse_s * 1000)
        truth = {"program": program, "cue_index": index, "command_true_s": t_cmd}
        if not actuated:
            return HapticOutcome(command, None, None, truth)
        # I2C GO write (~75 us at 400 kHz) + DRV2605L start latency (assumption).
        t_e = t_cmd + 280e-6 + float(self._rng_haptic.normal(0, 30e-6))
        edge_dev = int(math.floor(float(self.clock.to_device_us(t_e)) + float(_capture_latency_us(self._rng_haptic, 1)[0])))
        onset = self.log_event("haptic_events", "HAPTIC_ELECTRICAL_ONSET", edge_dev, program=program, cue_index=index)
        t_done = t_e + c.haptic_pulse_s + 0.012
        done_dev = int(math.floor(float(self.clock.to_device_us(t_done)) + float(self._rng_haptic.uniform(0, 1000))))
        completion = self.log_event("haptic_events", "HAPTIC_COMPLETION", done_dev, program=program, cue_index=index)
        physical = t_e + c.haptic_rise_s * math.log(2.0)
        self.vibrations.append({"t_e": t_e, "phase": float(self._rng_haptic.uniform(0, 2 * math.pi))})
        truth.update({"electrical_onset_true_s": t_e, "physical_onset_true_s": physical,
                      "electrical_onset_exact_device_us": float(self.clock.to_device_us(t_e)),
                      "physical_onset_exact_device_us": float(self.clock.to_device_us(physical))})
        self.haptic_truth.append(truth)
        return HapticOutcome(command, onset, completion, truth)

    def _vibration(self, t: np.ndarray) -> np.ndarray:
        c = self.config
        out = np.zeros_like(t)
        for v in self.vibrations:
            tau = t - v["t_e"]
            active = (tau >= 0) & (tau < c.haptic_pulse_s + 0.05)
            if not active.any():
                continue
            ta = tau[active]
            env = np.where(ta < c.haptic_pulse_s, 1 - np.exp(-ta / c.haptic_rise_s),
                           (1 - math.exp(-c.haptic_pulse_s / c.haptic_rise_s)) * np.exp(-(ta - c.haptic_pulse_s) / 0.005))
            out[active] += c.haptic_accel_g * env * np.sin(2 * math.pi * c.haptic_lra_hz * ta + v["phase"])
        return out

    # ------------------------------------------------------------ rendering
    def acquire_until(self, t_true_s: float) -> None:
        """Render every sample whose physical instant precedes t_true_s."""
        if t_true_s <= self.horizon_s:
            return
        self._render_eda(t_true_s)
        self._render_ppg(t_true_s)
        self._render_imu(t_true_s)
        self._rendered["sync"] = int(np.searchsorted(self.sync_t, t_true_s, side="left"))
        self.horizon_s = t_true_s

    def _span(self, name: str, instants: np.ndarray, t_end: float) -> slice:
        start = self._rendered[name]
        stop = int(np.searchsorted(instants, t_end, side="left"))
        self._rendered[name] = max(start, stop)
        return slice(start, max(start, stop))

    def _render_eda(self, t_end: float) -> None:
        span = self._span("eda", self.eda_t, t_end)
        if span.start == span.stop:
            return
        t = self.eda_t[span]
        g_us = self.twin.skin_conductance(t) + 0.002 * self.eda_noise[span, 0]
        g = np.clip(g_us, 0.05, None) * 1e-6
        v_sense = EDA_EXCITATION_V * EDA_SERIES_LIMIT_OHM * g / (1 + EDA_SERIES_LIMIT_OHM * g)
        v_sense = v_sense + 0.6e-6 * self.eda_noise[span, 1]
        full = 2 ** (EDA_BITS - 1)
        code = np.round(v_sense * EDA_PGA_GAIN / EDA_VREF_V * full)
        self.eda_codes[span] = np.clip(code, -full, full - 1).astype(np.int64)

    def _render_ppg(self, t_end: float) -> None:
        span = self._span("ppg", self.ppg_t, t_end)
        if span.start == span.stop:
            return
        c = self.config
        t = self.ppg_t[span]
        volume = self.twin.blood_volume(t)
        ratio = optical_ratio_of_ratios(self.twin.spo2_at(t))
        wander = 0.0035 * self.twin.respiration(t) + 0.002 * np.sin(2 * math.pi * t / 170 + self._ppg_wander_phase)
        common = 1 + wander + self.twin.ppg_motion(t)
        pi_ir = c.ppg_perfusion_index_ir
        ir = c.ppg_dc_ir_counts * common * (1 - pi_ir * volume) + 7.0 * self.ppg_noise[span, 1]
        red = c.ppg_dc_red_counts * common * (1 - ratio * pi_ir * volume) + 9.0 * self.ppg_noise[span, 0]
        self.ppg_codes[span, 0] = np.clip(np.round(red), 0, PPG_FULL_SCALE).astype(np.int64)
        self.ppg_codes[span, 1] = np.clip(np.round(ir), 0, PPG_FULL_SCALE).astype(np.int64)

    def _render_imu(self, t_end: float) -> None:
        span = self._span("imu", self.imu_t, t_end)
        if span.start == span.stop:
            return
        t = self.imu_t[span]
        force, rate = self.twin.gravity_and_motion(t)
        vib = self._vibration(t)
        force = force + np.outer(vib, [0.2, 0.3, 0.93]) + self.imu_accel_bias + 0.001 * self.imu_noise[span, :3]
        rate = rate + self.imu_gyro_bias + 0.04 * self.imu_noise[span, 3:]
        codes = np.column_stack([np.round(force * IMU_ACCEL_LSB_PER_G), np.round(rate * IMU_GYRO_LSB_PER_DPS)])
        self.imu_codes[span] = np.clip(codes, -32768, 32767).astype(np.int64)

    # ------------------------------------------------------------- exports
    def raw_session(self) -> RawSession:
        """Everything rendered so far, exactly as the firmware would have recorded it."""
        n = self._rendered
        streams = {
            "eda": Stream("eda", np.arange(n["eda"], dtype=np.int64), self.eda_dev[:n["eda"]],
                          {"code": self.eda_codes[:n["eda"]]}),
            "ppg": Stream("ppg", self.ppg_seq[:n["ppg"]], self.ppg_dev[:n["ppg"]],
                          {"red_counts": self.ppg_codes[:n["ppg"], 0], "ir_counts": self.ppg_codes[:n["ppg"], 1]}),
            "imu": Stream("imu", np.arange(n["imu"], dtype=np.int64), self.imu_dev[:n["imu"]],
                          {name: self.imu_codes[:n["imu"], i] for i, name in enumerate(STREAM_COLUMNS["imu"])}),
            "sync": Stream("sync", np.arange(n["sync"], dtype=np.int64), self.sync_dev[:n["sync"]],
                           {"lab_pulse_index": self.sync_t[:n["sync"]].astype(np.int64)}),
        }
        last_ppg = int(self.ppg_seq[n["ppg"] - 1]) if n["ppg"] else -1
        gaps = [g for g in self.ppg_gaps if g.last_sequence < last_ppg]
        return RawSession(streams, descriptors(self.config), gaps, sorted(self.events, key=lambda e: (e.device_time_us, e.stream_id, e.sequence)))

    def timing_truth(self) -> dict[str, Any]:
        """Exact device-clock instants of each recorded sample (for scoring only)."""
        n = self._rendered
        return {
            "device_clock_ppm": self.config.device_clock_ppm,
            "device_boot_offset_s": self.config.device_boot_offset_s,
            "eda_edge_error_us": (self.eda_dev[:n["eda"]] - self.eda_edge_dev_exact[:n["eda"]]),
            "imu_edge_error_us": (self.imu_dev[:n["imu"]] - self.imu_edge_dev_exact[:n["imu"]]),
            "ppg_sample_error_us": (self.ppg_dev[:n["ppg"]] - self.ppg_edge_dev_exact[:n["ppg"]]),
            "ppg_lost_sequences": [[g.first_sequence, g.last_sequence] for g in self.ppg_gaps],
            "haptic": self.haptic_truth,
        }
