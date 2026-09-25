"""Device-side raw data: the only input the CIRCLE signal pipeline may read.

A RawSession holds integer sensor codes, firmware sequence numbers, native
device timestamps (microseconds), declared gaps, and device-logged events.
It carries no ground truth, and no model output feeds back into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

STREAM_COLUMNS: dict[str, tuple[str, ...]] = {
    "eda": ("code",),
    "ppg": ("red_counts", "ir_counts"),
    "imu": ("ax_lsb", "ay_lsb", "az_lsb", "gx_lsb", "gy_lsb", "gz_lsb"),
    "sync": ("lab_pulse_index",),
}


@dataclass
class Stream:
    name: str
    sequence: np.ndarray
    device_time_us: np.ndarray
    columns: dict[str, np.ndarray]

    def __post_init__(self) -> None:
        n = len(self.sequence)
        if len(self.device_time_us) != n or any(len(v) != n for v in self.columns.values()):
            raise ValueError(f"Stream {self.name} columns differ in length")
        if n and (np.any(np.diff(self.sequence) <= 0) or np.any(np.diff(self.device_time_us) <= 0)):
            raise ValueError(f"Stream {self.name} sequence and time must increase strictly")

    def __len__(self) -> int:
        return len(self.sequence)

    def until(self, device_time_us: int) -> "Stream":
        stop = int(np.searchsorted(self.device_time_us, device_time_us, side="right"))
        return self.slice(0, stop)

    def slice(self, start: int, stop: int) -> "Stream":
        return Stream(self.name, self.sequence[start:stop], self.device_time_us[start:stop],
                      {k: v[start:stop] for k, v in self.columns.items()})

    def window(self, t0_us: int, t1_us: int) -> "Stream":
        """Samples with t0_us <= device_time_us <= t1_us."""
        start = int(np.searchsorted(self.device_time_us, t0_us, side="left"))
        stop = int(np.searchsorted(self.device_time_us, t1_us, side="right"))
        return self.slice(start, stop)


@dataclass(frozen=True)
class Gap:
    stream_id: str
    first_sequence: int
    last_sequence: int
    device_time_us: int
    cause: str


@dataclass(frozen=True)
class DeviceEvent:
    stream_id: str
    sequence: int
    kind: str
    device_time_us: int
    attributes: tuple[tuple[str, float], ...] = ()

    @property
    def evidence_id(self) -> str:
        return f"{self.stream_id}#{self.sequence}"

    def attribute(self, name: str, default: float | None = None) -> float | None:
        for key, value in self.attributes:
            if key == name:
                return value
        return default


@dataclass
class RawSession:
    streams: dict[str, Stream]
    descriptors: dict[str, dict[str, float]]
    gaps: list[Gap] = field(default_factory=list)
    events: list[DeviceEvent] = field(default_factory=list)

    def until(self, device_time_us: int) -> "RawSession":
        """Everything the device had recorded by device_time_us (inclusive)."""
        return RawSession(
            {name: s.until(device_time_us) for name, s in self.streams.items()},
            self.descriptors,
            [g for g in self.gaps if g.device_time_us <= device_time_us],
            [e for e in self.events if e.device_time_us <= device_time_us],
        )

    def events_of(self, prefix: str) -> list[DeviceEvent]:
        return [e for e in self.events if e.kind.startswith(prefix)]

    def phase_bounds_us(self) -> dict[str, tuple[int, int | None]]:
        """Protocol phase device-time bounds from PHASE_START markers."""
        starts = [(e.device_time_us, e.kind.split(":", 1)[1]) for e in self.events_of("PHASE_START:")]
        starts.sort()
        bounds: dict[str, tuple[int, int | None]] = {}
        for i, (t, name) in enumerate(starts):
            bounds[name] = (t, starts[i + 1][0] if i + 1 < len(starts) else None)
        return bounds


def summarize(session: RawSession) -> dict[str, Any]:
    return {
        name: {"samples": len(s), "first_sequence": int(s.sequence[0]) if len(s) else None,
               "last_sequence": int(s.sequence[-1]) if len(s) else None}
        for name, s in session.streams.items()
    }
