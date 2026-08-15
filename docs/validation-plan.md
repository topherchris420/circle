# Validation Plan

> **ENGINEERING REVIEW ONLY ? NOT FOR FABRICATION OR HUMAN CONNECTION.**

- Timing: verify sample distributions, cross-stream alignment, sequences, ISR/DMA latency; EDA/IMU edge timestamp ?10 microseconds at P99.9 and ?25 microseconds maximum.
- SYNC: ?2 microseconds delay, 250 nanoseconds peak-to-peak jitter, 500 nanoseconds pulse-width error.
- Storage: 24-hour representative-card recording; inject a 45-second write stall; verify buffering, explicit gaps, full-card/removal/brownout recovery.
- Safety: test every power/firmware state, USB/debug/expansion insertion, electrode leakage/current limits, welded-switch bounded behavior, and procedural grounded-probe controls.
- Signal quality: PPG ambient/contact/motion, EDA noise/range/disconnect/saturation, IMU alignment.
- Provenance: reject ambiguous origin; inject simulated/model/gap/clock/storage faults and verify explicit export.

Passing this plan does not itself close any fabrication gate.
