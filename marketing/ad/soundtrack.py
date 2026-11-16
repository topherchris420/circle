"""Original score for the CIRCLE film, synthesized from nothing but arithmetic.

No samples, no loops, no third-party audio: every sound is generated here with
NumPy, so the soundtrack is reproducible and carries no licence but the
repository's own. The score is written on a bar grid (96 BPM, 2.5 s bars) that
the picture is cut to; the same per-bar score renders the 90-second film and
the 30-second cut from their edit decision lists.

One layer is not music: ``--engine`` mixes in CIRCLE's own adaptive audio
engine, rendered by render.mjs from the product's synth.js and the recorded
session's feedback schedule. When the quality gate closes in the film, that is
the engine's real level falling to zero — and the score stops with it.

Usage: python soundtrack.py --cut 90 --output out/circle-film-90s.wav [--engine out/engine.wav]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import wave

import numpy as np

SR = 48_000
BPM = 96.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT                                  # 2.5 s
MASTER_BARS = 36                                # 90 s
CUTS = {                                        # (first master bar, bar count); mirrors CUTS in ad.js
    "90": [(0, 36)],
    "30": [(5, 2), (9, 2), (14, 5), (32, 3)],
}
GATE_BAR = 15                                   # master bar whose downbeat is the DATA_STALE evaluation (37.5 s)
UI_CLICKS_S = (23.70, 43.12, 46.88)             # pointer presses in the picture (master seconds)
REFERENCE_PEAK = 0.95                           # pre-master level that maps to full scale


# ----------------------------------------------------------------- primitives
def midi(note: int) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def seconds(n: int) -> np.ndarray:
    return np.arange(n) / SR


def fade(n: int, attack: float, release: float) -> np.ndarray:
    """Raised-cosine attack and release; flat in between."""
    env = np.ones(n)
    a, r = min(n, int(attack * SR)), min(n, int(release * SR))
    if a > 1:
        env[:a] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    if r > 1:
        env[n - r:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(r) / r)
    return env


def shaped_noise(n: int, rng: np.random.Generator, low: float, high: float, tilt: float = 0.0) -> np.ndarray:
    """Band-limited noise by spectral masking (zero-phase, no filter state)."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    mask = 1.0 / (1.0 + (low / np.maximum(freqs, 1.0)) ** 6) / (1.0 + (freqs / high) ** 6)
    if tilt:
        mask *= np.maximum(freqs, 20.0) ** tilt
    out = np.fft.irfft(spectrum * mask, n)
    return out / (np.max(np.abs(out)) + 1e-12)


class Mix:
    """Stereo buses: dry, plus sends to a shared reverb and a dotted-eighth echo."""

    def __init__(self, duration_s: float) -> None:
        self.n = int(duration_s * SR)
        self.dry = np.zeros((2, self.n))
        self.verb = np.zeros((2, self.n))
        self.echo = np.zeros((2, self.n))

    def add(self, start_s: float, signal: np.ndarray, gain: float = 1.0, pan: float = 0.0,
            verb: float = 0.0, echo: float = 0.0) -> None:
        i = int(round(start_s * SR))
        if i >= self.n or i + len(signal) <= 0:
            return
        if i < 0:
            signal, i = signal[-i:], 0
        signal = signal[: self.n - i]
        angle = (pan + 1.0) * np.pi / 4.0
        left, right = np.cos(angle) * gain, np.sin(angle) * gain
        for bus, amount in ((self.dry, 1.0), (self.verb, verb), (self.echo, echo)):
            if amount:
                bus[0, i:i + len(signal)] += signal * left * amount
                bus[1, i:i + len(signal)] += signal * right * amount


# ---------------------------------------------------------------- instruments
def pluck(note: int, dur: float = 1.3, bright: float = 0.88) -> np.ndarray:
    """A soft mallet: a few harmonics, each decaying faster than the one below, and a felt strike."""
    n = int(dur * SR)
    t = seconds(n)
    f = midi(note)
    out = np.zeros(n)
    for k in range(1, 9):
        if f * k > 9000:
            break
        amp = bright ** (k - 1) / k ** 0.8
        out += amp * np.sin(2 * np.pi * f * k * (1 + 0.0004 * k * k) * t) * np.exp(-t * (2.0 + 0.9 * k))
    strike = int(0.014 * SR)
    phase = 2 * np.pi * ((note * 0.61803) % 1.0)
    out[:strike] += 0.30 * np.sin(2 * np.pi * 3100.0 * t[:strike] + phase) * np.exp(-t[:strike] * 300.0)
    out[:strike] += 0.16 * np.sin(2 * np.pi * 5400.0 * t[:strike] + 2 * phase) * np.exp(-t[:strike] * 420.0)
    return out * fade(n, 0.003, 0.05)


def bell(note: int, dur: float = 4.5, soft: float = 1.0) -> np.ndarray:
    """A felted bell: near-harmonic partials with a slow, warm tail."""
    n = int(dur * SR)
    t = seconds(n)
    f = midi(note)
    partials = ((1.0, 1.0, 0.9), (2.0, 0.55, 1.4), (3.01, 0.34, 2.0), (4.2, 0.18, 2.9), (5.43, 0.10, 4.0), (6.8, 0.05, 5.5))
    out = np.zeros(n)
    for ratio, amp, decay in partials:
        if f * ratio > 10_000:
            break
        out += amp * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t * decay * soft)
    return out * fade(n, 0.010, 0.30)


def pad(notes: tuple[int, ...], dur: float, attack: float = 0.5, release: float = 0.6, bright: float = 0.76) -> np.ndarray:
    """Three slightly detuned voices per note; returns stereo (2, n)."""
    n = int(dur * SR)
    t = seconds(n)
    out = np.zeros((2, n))
    for index, note in enumerate(notes):
        f = midi(note)
        for cents, pan in ((-7.0, -0.7), (0.0, 0.0), (6.0, 0.7)):
            fv = f * 2 ** (cents / 1200.0)
            voice = np.zeros(n)
            for k in range(1, 12):
                if fv * k > 7000:
                    break
                voice += (bright ** (k - 1)) / k * np.sin(2 * np.pi * fv * k * t + 0.9 * index + 0.37 * k)
            angle = (pan + 1.0) * np.pi / 4.0
            out[0] += voice * np.cos(angle)
            out[1] += voice * np.sin(angle)
    out *= fade(n, attack, release) * (0.92 + 0.08 * np.sin(2 * np.pi * 0.21 * t))
    return out / (3.0 * max(1, len(notes)) ** 0.5)


def sub(note: int, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = seconds(n)
    f = midi(note)
    tone = np.sin(2 * np.pi * f * t) + 0.12 * np.sin(2 * np.pi * 2 * f * t)
    return np.tanh(1.4 * tone) / np.tanh(1.4) * fade(n, 0.03, 0.22)


def kick(weight: float = 1.0) -> np.ndarray:
    n = int(0.42 * SR)
    t = seconds(n)
    freq = 46.0 + 70.0 * np.exp(-t * 34.0)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 9.5)
    return weight * body * fade(n, 0.002, 0.08)


def hat(rng: np.random.Generator) -> np.ndarray:
    n = int(0.09 * SR)
    return shaped_noise(n, rng, 6500.0, 13_000.0) * np.exp(-seconds(n) * 70.0) * fade(n, 0.001, 0.02)


def riser(dur: float, rng: np.random.Generator) -> np.ndarray:
    """Air that opens upward: several noise bands entering one after another."""
    n = int(dur * SR)
    t = seconds(n) / dur
    out = np.zeros(n)
    for index, (low, high) in enumerate(((300, 700), (700, 1500), (1500, 3200), (3200, 6500), (6500, 11_000))):
        out += shaped_noise(n, rng, low, high) * np.clip((t - 0.14 * index) / 0.55, 0.0, 1.0) ** 2 / (1 + 0.35 * index)
    return out * t ** 1.6 * fade(n, 0.2, 0.03)


def droplet(note: int) -> np.ndarray:
    n = int(0.32 * SR)
    t = seconds(n)
    freq = midi(note) * (1.0 + 0.45 * np.exp(-t * 90.0))
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t * 17.0) * fade(n, 0.002, 0.04)


def click(rng: np.random.Generator) -> np.ndarray:
    n = int(0.03 * SR)
    t = seconds(n)
    return (0.6 * shaped_noise(n, rng, 1800.0, 5200.0) + 0.5 * np.sin(2 * np.pi * 2100.0 * t)) * np.exp(-t * 260.0) * fade(n, 0.0006, 0.004)


# ---------------------------------------------------------------------- score
# Chords: (bass, pad voicing, arpeggio pool). All sit under the product engine's
# own drone (F3 with C4/C5 above it), so no chord contains a tone that fights F or C.
F = (29, (53, 57, 60, 67), (65, 67, 69, 72, 77))        # F add9
DM = (26, (50, 57, 60, 65), (62, 65, 69, 72, 76))       # D minor 7 (add9 in the line)
BB = (34, (46, 53, 60, 62), (58, 62, 65, 72, 74))       # B-flat add9
CS = (24, (48, 55, 60, 65), (60, 65, 67, 72, 77))       # C sus4
C = (24, (48, 55, 64, 67), (60, 64, 67, 72, 76))        # C major (only where the engine is silent)
ARP_A = (0, 2, 3, 2, 4, 2, 3, 1)
ARP_B = (0, 3, 2, 4, 3, 2, 4, 1)

#            bar: chord, arp pattern, arp gain, kick beats, hats, sub, pad level
SCORE: dict[int, dict] = {
    1: dict(chord=F, pad=0.20, dark=True),
    2: dict(chord=F, pad=0.34, dark=True, rise=True),
    3: dict(chord=F, pad=0.60),
    4: dict(chord=F, arp=ARP_A, arp_gain=0.55, sub=True, pad=0.55),
    5: dict(chord=F, arp=ARP_A, arp_gain=0.80, sub=True, pad=0.60, kick=(0, 2)),
    6: dict(chord=DM, arp=ARP_A, arp_gain=0.85, sub=True, pad=0.65, kick=(0, 2)),
    7: dict(chord=DM, arp=ARP_B, arp_gain=0.90, sub=True, pad=0.65, kick=(0, 2)),
    8: dict(chord=BB, arp=ARP_A, arp_gain=0.90, sub=True, pad=0.70, kick=(0, 2)),
    9: dict(chord=BB, arp=ARP_B, arp_gain=0.90, sub=True, pad=0.70, kick=(0, 2), hats=True),
    10: dict(chord=CS, arp=ARP_A, arp_gain=0.95, sub=True, pad=0.72, kick=(0, 2), hats=True),
    11: dict(chord=DM, arp=ARP_B, arp_gain=1.00, sub=True, pad=0.75, kick=(0, 2), hats=True),
    12: dict(chord=BB, arp=ARP_A, arp_gain=1.00, sub=True, pad=0.75, kick=(0, 2), hats=True),
    13: dict(chord=CS, pad=0.70, sub=True, pulse=(72,), rise=True),
    14: dict(chord=CS, pad=0.80, sub=True, pulse=(72, 77), rise=True, kick=(0, 1, 2, 3)),
    17: dict(chord=DM, pad=0.22, dark=True),
    18: dict(chord=DM, pad=0.38, dark=True),
    19: dict(chord=DM, pad=0.42, dark=True),
    20: dict(chord=DM, pad=0.50, rain=5),
    21: dict(chord=DM, arp=ARP_B, arp_gain=0.55, sub=True, pad=0.55, rain=6),
    22: dict(chord=BB, arp=ARP_B, arp_gain=0.75, sub=True, pad=0.62, kick=(0, 2), rain=5),
    23: dict(chord=BB, arp=ARP_A, arp_gain=0.90, sub=True, pad=0.68, kick=(0, 2), hats=True, rain=4),
    24: dict(chord=CS, arp=ARP_B, arp_gain=0.95, sub=True, pad=0.72, kick=(0, 2), hats=True, rain=4, rise=True),
    25: dict(chord=DM, pad=0.40, dark=True, rain=3),
    26: dict(chord=BB, pad=0.72, sub=True, rain=3, rise=True),
    27: dict(chord=F, arp=ARP_A, arp_gain=1.00, sub=True, pad=0.75, kick=(0, 1, 2, 3), hats=True),
    28: dict(chord=C, arp=ARP_B, arp_gain=1.00, sub=True, pad=0.75, kick=(0, 1, 2, 3), hats=True),
    29: dict(chord=DM, arp=ARP_A, arp_gain=1.05, sub=True, pad=0.78, kick=(0, 1, 2, 3), hats=True),
    30: dict(chord=BB, arp=ARP_B, arp_gain=1.05, sub=True, pad=0.80, kick=(0, 1, 2, 3), hats=True),
    31: dict(chord=CS, arp=ARP_A, arp_gain=1.10, sub=True, pad=0.82, kick=(0, 1, 2, 3), hats=True, rise=True),
    32: dict(chord=F, pad=0.95, sub=True, long=True),
    33: dict(chord=F, pad=0.85, sub=True, long=True),
    34: dict(chord=F, pad=0.60, long=True),
}
# Single bell notes: bar -> [(beat, note, gain)]. They land on words and stamps in the picture.
BELLS: dict[int, list[tuple[float, int, float]]] = {
    0: [(1.5, 65, 0.34)],
    1: [(1.0, 72, 0.50), (2.0, 69, 0.40)],
    2: [(0.0, 65, 0.45), (2.0, 67, 0.32)],
    3: [(0.0, 65, 0.75), (0.0, 69, 0.55), (0.0, 72, 0.55), (0.0, 77, 0.38)],
    4: [(0.0, 77, 0.38)],
    13: [(0.0, 72, 0.50)],
    19: [(0.0, 50, 0.70), (0.0, 57, 0.55), (0.0, 65, 0.50), (0.06, 76, 0.42)],
    20: [(0.0, 62, 0.50), (0.0, 69, 0.36)],
    25: [(0.0, 50, 0.72), (0.0, 62, 0.50), (2.0, 57, 0.30)],
    26: [(0.0, 58, 0.60), (0.0, 65, 0.50), (0.0, 74, 0.42), (2.0, 77, 0.30)],
    27: [(0.0, 77, 0.40)],
    30: [(0.0, 77, 0.62), (0.0, 81, 0.48), (0.0, 84, 0.40)],
    32: [(0.0, 53, 0.80), (0.0, 65, 0.62), (0.0, 69, 0.50), (0.0, 72, 0.50), (2.0, 72, 0.50)],
    33: [(0.0, 77, 0.58), (0.0, 69, 0.36), (2.0, 79, 0.26)],
    34: [(0.0, 65, 0.44), (0.0, 72, 0.36)],
}


def render_bar(mix: Mix, master_bar: int, at_s: float, rng: np.random.Generator, last_bar: bool) -> None:
    for beat, note, gain in BELLS.get(master_bar, ()):
        mix.add(at_s + beat * BEAT, bell(note), gain * 0.20, pan=0.25 * np.sin(note), verb=0.55, echo=0.10)
    part = SCORE.get(master_bar)
    if not part:
        return
    bass, voicing, pool = part["chord"]
    level = part.get("pad", 0.0)
    if level:
        long = part.get("long", False)
        dark = part.get("dark", False)
        dur = BAR + (2.6 if (long and last_bar) else 0.7)
        body = pad(voicing[:3] if dark else voicing, dur, attack=1.1 if dark else 0.55, release=2.4 if (long and last_bar) else 0.7,
                   bright=0.44 if dark else 0.76)
        start = int(round((at_s - 0.25) * SR))
        start = max(0, start)
        stop = min(mix.n, start + body.shape[1])
        mix.dry[:, start:stop] += body[:, : stop - start] * level * 0.34
        mix.verb[:, start:stop] += body[:, : stop - start] * level * 0.34 * 0.5
    if part.get("sub"):
        mix.add(at_s, sub(bass + 12, BAR * 0.96), 0.13)
    for beat in part.get("kick", ()):
        mix.add(at_s + beat * BEAT, kick(), 0.36 if beat in (0, 2) else 0.24)
    if part.get("hats"):
        for step in range(8):
            mix.add(at_s + step * BEAT / 2, hat(rng), 0.20 if step % 2 else 0.10, pan=0.3 if step % 2 else -0.2, verb=0.08)
    pattern = part.get("arp")
    if pattern:
        for step, index in enumerate(pattern):
            accent = 1.0 if step in (0, 4) else 0.72
            mix.add(at_s + step * BEAT / 2, pluck(pool[index]), 0.17 * accent * part["arp_gain"],
                    pan=0.45 * (1 if step % 2 else -1), verb=0.30, echo=0.34)
            # the same line an octave above, quieter, and a glint two octaves up on the accents
            mix.add(at_s + step * BEAT / 2, pluck(pool[index] + 12, 0.9), 0.075 * accent * part["arp_gain"],
                    pan=0.6 * (-1 if step % 2 else 1), verb=0.40, echo=0.40)
            if step in (0, 4):
                mix.add(at_s + step * BEAT / 2, pluck(pool[index] + 24, 0.7, 0.8), 0.04 * part["arp_gain"],
                        pan=0.7 * (1 if step else -1), verb=0.55, echo=0.45)
    pulse = part.get("pulse")
    if pulse:
        for step in range(8):
            swell = 0.35 + 0.65 * (step / 7.0)
            mix.add(at_s + step * BEAT / 2, pluck(pulse[step % len(pulse)], 0.7, 0.45), 0.13 * swell,
                    pan=0.3 * (1 if step % 2 else -1), verb=0.35, echo=0.25)
    if part.get("rise"):
        mix.add(at_s, riser(BAR, rng), 0.085, verb=0.35)
    for _ in range(part.get("rain", 0)):
        note = int(rng.choice((84, 86, 88, 91, 93, 96)))
        mix.add(at_s + float(rng.uniform(0, BAR)), droplet(note), float(rng.uniform(0.035, 0.075)),
                pan=float(rng.uniform(-0.8, 0.8)), verb=0.7, echo=0.45)


# -------------------------------------------------------------------- effects
def convolve(signal: np.ndarray, impulse: np.ndarray) -> np.ndarray:
    n = signal.shape[-1] + impulse.shape[-1] - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(impulse, size), size)[..., : signal.shape[-1]]


def reverb(send: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A dark hall: decaying noise with the top rolled away, different per ear."""
    n = int(3.4 * SR)
    t = seconds(n)
    out = np.zeros_like(send)
    mono = send.mean(axis=0)
    for channel in range(2):
        tail = shaped_noise(n, rng, 180.0, 5200.0, tilt=-0.35) * np.exp(-t * 2.1)
        tail[: int(0.018 * SR)] = 0.0
        tail /= np.sqrt(np.sum(tail ** 2))
        out[channel] = convolve(0.65 * mono + 0.35 * send[channel], tail)
    return out


def echo(send: np.ndarray) -> np.ndarray:
    """Dotted-eighth echoes that cross the stereo field and fade."""
    out = np.zeros_like(send)
    step = int(0.75 * BEAT * SR)
    for tap in range(1, 5):
        gain = 0.52 ** tap
        shifted = np.zeros_like(send)
        shifted[:, tap * step:] = send[:, : send.shape[1] - tap * step]
        out += gain * (shifted[::-1] if tap % 2 else shifted)
    return out


def tilt(audio: np.ndarray) -> np.ndarray:
    """Mastering EQ, zero-phase: ease the lowest octave and the low mids, lift presence and air."""
    spectrum = np.fft.rfft(audio, axis=-1)
    freqs = np.fft.rfftfreq(audio.shape[-1], 1 / SR)
    low_shelf = 10 ** (-3.0 / 20 / (1.0 + (freqs / 95.0) ** 4))
    octaves = np.log2(np.maximum(freqs, 1.0) / 330.0)
    low_shelf *= 10 ** (-4.0 / 20 * np.exp(-0.5 * (octaves / 0.75) ** 2))      # clear the low-mid wash
    presence = 10 ** (9.0 / 20 * (1.0 - 1.0 / (1.0 + (freqs / 1700.0) ** 2)))
    presence *= 10 ** (5.0 / 20 * (1.0 - 1.0 / (1.0 + (freqs / 6500.0) ** 2)))
    rumble = 1.0 / np.sqrt(1.0 + (28.0 / np.maximum(freqs, 1.0)) ** 8)
    return np.fft.irfft(spectrum * low_shelf * presence * rumble, audio.shape[-1], axis=-1)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != SR or handle.getsampwidth() != 2:
            raise ValueError(f"{path} must be 16-bit at {SR} Hz")
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
        return data.reshape(-1, handle.getnchannels()).T


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio.T, -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes((pcm * 32767.0).astype("<i2").tobytes())


def conform(master: np.ndarray, edl: list[tuple[int, int]], total: int) -> np.ndarray:
    """Cut a master-timeline track to the film's edit, with 20 ms edges."""
    out = np.zeros((2, total))
    at = 0
    for first, count in edl:
        a, n = int(first * BAR * SR), int(count * BAR * SR)
        piece = np.zeros((2, n))
        have = master[:, a:a + n]
        piece[:, : have.shape[1]] = have
        if len(edl) > 1:
            piece *= fade(n, 0.02, 0.02)
        out[:, at:at + n] = piece
        at += n
    return out


# ------------------------------------------------------------------- assembly
def render(cut: str, engine: Path | None, engine_gain: float) -> tuple[np.ndarray, dict]:
    edl = CUTS[cut]
    bars = sum(count for _, count in edl)
    duration = bars * BAR
    rng = np.random.default_rng(20261115)
    mix = Mix(duration)

    placed: list[tuple[int, float]] = []
    at = 0.0
    for first, count in edl:
        for master_bar in range(first, first + count):
            placed.append((master_bar, at))
            at += BAR
    for index, (master_bar, at_s) in enumerate(placed):
        render_bar(mix, master_bar, at_s, rng, last_bar=(index == len(placed) - 1) or master_bar == 34)

    music = tilt(mix.dry + 0.55 * reverb(mix.verb, rng) + 0.5 * echo(mix.echo))

    # The gate: when the recorded quality gate closes, the score stops with it.
    gate_at = next((at_s for master_bar, at_s in placed if master_bar == GATE_BAR), None)
    if gate_at is not None:
        a = int(gate_at * SR)
        close, hold = int(0.035 * SR), int(4.0 * SR)
        envelope = np.ones(mix.n)
        envelope[a:a + close] = 0.5 + 0.5 * np.cos(np.pi * np.arange(min(close, mix.n - a)) / close)
        envelope[a + close:a + hold] = 0.0
        reopen = slice(a + hold, min(mix.n, a + hold + int(0.5 * SR)))
        envelope[reopen] = np.linspace(0.0, 1.0, reopen.stop - reopen.start)
        music *= envelope

    # Things tied to the picture's master clock: pointer presses, and the product's own audio.
    master_n = int(MASTER_BARS * BAR * SR)
    extras = np.zeros((2, master_n))
    for when in UI_CLICKS_S:
        tick = click(rng)
        i = int(when * SR)
        extras[:, i:i + len(tick)] += tick * 0.10
    report = {"engine": "not mixed"}
    if engine is not None and engine.is_file():
        product = read_wav(engine)
        if product.shape[0] == 1:
            product = np.vstack([product, product])
        n = min(master_n, product.shape[1])
        extras[:, :n] += product[:, :n] * engine_gain
        report["engine"] = f"{engine.name} at x{engine_gain:g} (peak {np.max(np.abs(product)):.3f} before gain)"
    out = music + conform(extras, edl, mix.n)

    # Never digital black: a breath of air under everything.
    air = np.vstack([shaped_noise(mix.n, rng, 120.0, 5000.0, tilt=-0.5) for _ in range(2)]) * 10 ** (-58 / 20)
    out += air

    # Master: slow fades at the ends, gentle saturation, fixed headroom.
    out *= fade(mix.n, 0.6 if cut == "90" else 0.25, 1.4 if cut == "90" else 0.6)
    # One fixed reference for every cut, so the film and its cut-downs play at the same loudness.
    peak = float(np.max(np.abs(out)))
    out = np.tanh(out * (1.05 / REFERENCE_PEAK)) / np.tanh(1.05)
    out *= 10 ** (-1.0 / 20) / max(1.0, float(np.max(np.abs(out))))
    report.update({"cut": cut, "seconds": duration, "bars": bars, "pre_master_peak": round(peak, 4),
                   "rms_dbfs": round(20 * np.log10(np.sqrt(np.mean(out ** 2)) + 1e-12), 2)})
    return out, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", choices=sorted(CUTS), default="90")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", type=Path, default=None, help="master-timeline render of the product's audio engine")
    parser.add_argument("--engine-gain", type=float, default=0.6,
                        help="playback level for the engine layer (a listening level, like a volume knob)")
    args = parser.parse_args(argv)
    audio, report = render(args.cut, args.engine, args.engine_gain)
    write_wav(args.output, audio)
    print(f"soundtrack {args.output}: " + ", ".join(f"{k}={v}" for k, v in report.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
