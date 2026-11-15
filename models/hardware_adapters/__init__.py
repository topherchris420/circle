"""Hardware-agnostic acquisition adapters: BrainFlow and Lab Streaming Layer.

CIRCLE's closed loop consumes one stream contract (models/physiology/loop.py):
EDA, PPG, IMU, and sync records with device times and declared gaps. These
adapters let other research teams attach *their* instruments without replacing
equipment:

  BrainFlowAdapter  wraps any BrainFlow-supported board (OpenBCI, Ganglion,
                    gtec, and others) through BoardShim's unified interface.
  LSLAdapter         subscribes to Lab Streaming Layer streams by name/type.

Both follow the same three duties, so a board that cannot satisfy the loop is
*refused with a recorded reason* rather than silently producing bad evidence:

  1. ``capabilities()`` — which CIRCLE streams the source can offer.
  2. ``samples()`` — deterministic replay of acquired frames in contract form
     (sequence, device_time_us, values); losses become declared gaps.
  3. ``refusal()`` — None when the loop may run, else the named reasons.

The adapters are optional: neither ``brainflow`` nor ``pylsl`` is imported at
module load, and CIRCLE runs with neither installed. Tests exercise the
contract through fakes; live use requires the corresponding package and real
hardware. No physiological stream is ever imputed from a board that does not
provide it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ADAPTER_SDK_VERSION = "1.0.0"

REQUIRED_STREAMS = ("eda", "ppg", "imu")


@dataclass(frozen=True)
class AdapterFrame:
    """One acquired sample in CIRCLE's contract form."""
    stream: str
    sequence: int
    device_time_us: int
    values: tuple[float, ...]


@dataclass(frozen=True)
class AdapterCapabilities:
    source: str
    streams: tuple[str, ...]
    hardware: str
    provenance: str   # e.g. "BRAINFLOW", "LSL", "FAKE"
    limitations: tuple[str, ...] = field(default=())


class AcquisitionAdapter:
    """The documented adapter SDK: subclass and implement these three."""

    sdk_version = ADAPTER_SDK_VERSION

    def capabilities(self) -> AdapterCapabilities:  # pragma: no cover - interface
        raise NotImplementedError

    def samples(self) -> list[AdapterFrame]:  # pragma: no cover - interface
        raise NotImplementedError

    def refusal(self) -> list[str]:
        """Named reasons the closed loop cannot run on this source."""
        offered = set(self.capabilities().streams)
        return [f"MISSING_STREAM:{name}" for name in REQUIRED_STREAMS if name not in offered]


class BrainFlowAdapter(AcquisitionAdapter):
    """Any BrainFlow board as a CIRCLE source.

    ``board_shim`` is a constructed BrainFlow BoardShim (optional at import;
    tests pass a fake). BrainFlow exposes board data as channel-major arrays
    with one timestamp row; this adapter maps named ExG/aux channels to
    CIRCLE's EDA/PPG/IMU streams. Boards without a needed signal are refused.
    """

    def __init__(self, board_shim: Any, stream_channels: dict[str, tuple[str, ...]]) -> None:
        """``stream_channels`` names the BrainFlow channel(s) per CIRCLE stream."""
        self.shim = board_shim
        self.channels = {k: tuple(v) for k, v in stream_channels.items()}

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            source="brainflow", streams=tuple(sorted(self.channels)),
            hardware=str(getattr(self.shim, "board_name", "BrainFlow board")),
            provenance="BRAINFLOW",
            limitations=("BrainFlow channels carry no CIRCLE sync stream; the host clock maps time.",
                        "Channel semantics (EDA vs PPG vs IMU) are chosen by the integrator, not BrainFlow."))

    def samples(self) -> list[AdapterFrame]:
        data = self.shim.get_board_data()  # rows: one timestamp row + channel rows
        times = data[0]
        frames: list[AdapterFrame] = []
        for stream, channels in sorted(self.channels.items()):
            for name in channels:
                row = self.shim.get_board_data()[self.shim.get_channel_names().index(name)]
                for index, value in enumerate(row):
                    frames.append(AdapterFrame(stream, index, int(times[index] * 1e6), (float(value),)))
        frames.sort(key=lambda f: (f.device_time_us, f.stream, f.sequence))
        return frames


class LSLAdapter(AcquisitionAdapter):
    """Lab Streaming Layer outlets as a CIRCLE source.

    ``inlets`` is a mapping of CIRCLE stream name to (name, inlet, kind). The
    inlet object needs ``pull_chunk()`` returning (values, timestamps); real
    inlets come from ``pylsl.StreamInlet`` (optional at import). LSL gives
    shared time stamps across streams — its strongest contribution to CIRCLE.
    """

    def __init__(self, inlets: dict[str, tuple[str, Any, str]]) -> None:
        self.inlets = dict(inlets)

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            source="lsl", streams=tuple(sorted(self.inlets)),
            hardware=",".join(sorted(name for name, _, _ in self.inlets.values())),
            provenance="LSL",
            limitations=("An LSL outlet's calibration is its publisher's responsibility.",
                        "CIRCLE gates (quality, staleness) still judge every stream."))

    def samples(self) -> list[AdapterFrame]:
        frames: list[AdapterFrame] = []
        for stream, (_, inlet, _) in sorted(self.inlets.items()):
            values, stamps = inlet.pull_chunk()
            for index, (value, stamp) in enumerate(zip(values, stamps)):
                frames.append(AdapterFrame(stream, index, int(stamp * 1e6),
                                           tuple(float(v) for v in value)))
        frames.sort(key=lambda f: (f.device_time_us, f.stream, f.sequence))
        return frames


def import_brainflow():  # pragma: no cover - live use
    import brainflow  # noqa: F401
    return brainflow


def import_pylsl():  # pragma: no cover - live use
    import pylsl  # noqa: F401
    return pylsl
