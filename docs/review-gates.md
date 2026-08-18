# Review Gates

> **ENGINEERING REVIEW ONLY ? NOT FOR FABRICATION OR HUMAN CONNECTION.**

| Gate | Blocking evidence | Affected area | Verification | Release consequence |
|---|---|---|---|---|
| EDA_LIMIT_NETWORK | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| EDA_SWITCH_SELECTION | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| BATTERY_AND_CHARGE_CURRENT | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| POWER_MAGNETICS_AND_THERMALS | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| ISOLATION_CREEPAGE_CLEARANCE | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| PPG_CABLE_SIGNAL_INTEGRITY | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| FOOTPRINT_VERIFICATION | Reviewed value/part/footprint plus measured evidence | Manifest and named schematic sheets | Independent calculation, CAD review, and bench test | Fabrication remains blocked until closed |
| PHYSICAL_ROUTING | All DRC unconnected_items resolved in copper or individually reviewed as intentional; final DRC contains zero unexplained error-severity connectivity items | PCB Layout & CAD models | Automated KiCad PCB DRC and SHA-256 content-fingerprinted allowlist audit | Fabrication remains blocked until closed |

## Resonance Research Module Gates

| Gate | Blocking evidence | Affected area | Verification | Release consequence |
|---|---|---|---|---|
| RESONANCE_SIMULATION_CONTROLS | Multi-geometry coupled simulation with verified energy conservation ($P_\text{out} \le P_\text{in}$) and control matrix | `models/resonance_response/` and contracts | Automated simulation tests and schema validation | Experimental execution remains blocked until verified |
| RESONANCE_ISOLATION_BARRIER | Zero conductive connection to `BAT_HUMAN` domain; isolated SYNC only over ISOW7742 5.0 kVrms barrier | `docs/resonance-safety-boundary.md` and CAD layout | Dielectric withstand calculation and physical slot inspection | Hardware coupling remains blocked until verified |
| RESONANCE_ARTIFACT_DISCRIMINATION | Electronic phantom (resistor/optical) characterization isolating RF/EM rectification from true signals | `experiments/resonance/controls.md` and analyzer | Bench phantom sweep and artifact penalty scoring | Interpretation remains blocked until characterized |

Completion of this review package does not close a fabrication gate.
