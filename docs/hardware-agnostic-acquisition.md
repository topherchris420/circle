# Hardware-agnostic acquisition: the adapter SDK

CIRCLE's closed loop does not care which instrument produced a sample. It
consumes one contract — EDA, PPG, IMU, and sync records with device times,
sequence numbers, and declared gaps ([`models/physiology/loop.py`](../models/physiology/loop.py)).
This SDK lets a research team attach **their** equipment without replacing it.

> [!WARNING]
> **ENGINEERING REVIEW ONLY.** These adapters are contract-checked against
> deterministic fakes. No physical BrainFlow board or live LSL outlet has been
> run in this repository, and nothing here authorizes human-connected use.

## The three duties of an adapter

Subclass `models.hardware_adapters.AcquisitionAdapter` (or use the provided
BrainFlow/LSL adapters) and implement:

1. **`capabilities()`** — which CIRCLE streams the source offers, its
   provenance, and its honest limitations.
2. **`samples()`** — acquired frames in contract form:
   `(stream, sequence, device_time_us, values)`, ordered by device time.
   Losses must become declared gaps, never silent drops.
3. **`refusal()`** — named reasons the closed loop cannot run (the default
   implementation refuses any source missing EDA, PPG, or IMU).

A board that cannot satisfy the loop is refused *with a recorded reason* — the
same discipline as the existing Cyton, Oura, and Muse adapters.

## BrainFlow

```python
from models.hardware_adapters import BrainFlowAdapter
# board_shim: a constructed brainflow.BoardShim (pip install brainflow)
adapter = BrainFlowAdapter(board_shim, {"eda": ("eda_ch",), "ppg": ("ppg_ch",),
                                        "imu": ("ax", "ay", "az")})
adapter.refusal()   # [] when the board offers all three streams
adapter.samples()  # contract-form frames
```

BrainFlow's unified `BoardShim` already supports OpenBCI boards, g.tec, and
others; the integrator names which channels mean EDA/PPG/IMU. BrainFlow
provides no CIRCLE sync stream — the host clock maps time (a stated
limitation, like every adapter here).

## Lab Streaming Layer

```python
from models.hardware_adapters import LSLAdapter
# inlets: pylsl.StreamInlet per outlet (pip install pylsl)
adapter = LSLAdapter({"ppg": ("ppg-outlet", ppg_inlet, "PPG")})
```

LSL's shared timestamps across streams are its strongest contribution to
multi-instrument timing; CIRCLE's quality and staleness gates still judge
every stream.

## What is not claimed

- No adapter imputes a physiological stream the instrument does not provide.
- Adapter validity does not authorize the closed loop: quality gates, consent,
  and the acquisition contract still apply.
- A contract-checked fake is not physical evidence; the first physical run
  should be a known-input phantom, recorded in the [phantom view](resonance-workbench.md).
