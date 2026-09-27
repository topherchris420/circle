# Physical Evidence Ladder

> **ENGINEERING REVIEW ONLY — NOT FOR FABRICATION OR HUMAN CONNECTION.** Nothing on this page has been performed. It defines the order in which evidence must be earned.

Don't make the body the first test instrument. If a question can be answered with simulation, a fixture, an electrical or optical phantom, a mechanical fixture, or a loopback, answer it there first. Only questions that are genuinely human-specific belong in later, separately approved human research.

```
SIMULATED SIGNAL            physiology twin (exists)
  → ELECTRONIC PHANTOM      known injected truth on the real acquisition chain
  → BENCH SENSOR            real sensors on fixtures, no person
  → ISOLATED SYSTEM TEST    barrier, interlocks, fault current, withstand
  → HARDWARE LOOPBACK       SYNC in/out, haptic command → edge → IMU on a fixture
  → PHYSICAL ACTUATION OBSERVATION
  → only then, after independent safety review and ethics approval, any human-connected session
```

Every layer keeps the same evidence architecture: the same session contract, availability times, declared gaps, execution chains, audit, and replay statuses. A phantom session should pass `tools/audit_physiology_run.py` exactly as a twin session does, with measured truth replacing simulated truth.

## Phantoms extend the twin's known-truth philosophy

| Phantom | Injected truth | Tests |
|---|---|---|
| EDA resistor / conductance ladder | Switched precision conductances, including steps and ramps | ADC transfer, noise, drift, SCR detection on known steps, contact-loss gate |
| Optical PPG phantom | LED-driven absorber with programmed pulse timing and amplitude | Beat timing, FIFO timestamp reconstruction, coupling-change gate, SpO₂ ratio behavior |
| Motion fixture | Shaker with known acceleration profile | Motion gating, PPG motion artifact discrimination |
| Haptic loopback | LRA mounted on a fixture with the IMU | Command → TLV3201 edge → IMU observation latencies (the twin predicts ±3 ms resolution) |
| FIFO stress firmware | Deliberately delayed service | Exact GAP declaration, availability times, the OVF_COUNTER observability limit |
| SYNC generator | Laboratory 1 PPS and pulse trains | Clock fit, capture latency, jitter |
| Disconnected / shielded / dummy-load channels | No physiology at all | Instrumentation pickup: a "response" that appears here is an artifact |

## Hardware design decisions are propositions

Each becomes a bring-up test before fabrication and is closed only by recorded evidence ([bring-up plan](board-bringup-and-validation-plan.md), [review gates](../hardware/review-gates.json)):

| Proposition | Test that earns it |
|---|---|
| The isolation layout is sufficient | Creepage review plus witnessed withstand test |
| The power architecture meets EDA noise needs | Ripple and analog noise measurement under load |
| The EDA front end stays inside its fault-current limit | Independent calculation plus measured short-circuit current |
| The SD path withstands stalls | Injected stall with zero undeclared loss |
| The PPG head gives usable signal | Optical phantom, then bench sensor |
| The haptic motor is observable through the IMU | Haptic loopback on a fixture |
| FIFO timestamps meet 1 ms | Optical phantom with known pulse timing |

The twin's findings for firmware (ADS1220 has no native 64 SPS mode; anchor PPG timestamps on the FIFO interrupt; hold the first FIFO batch until the period is measured; service the FIFO within the OVF_COUNTER budget; motion-gate SpO₂) are hypotheses about hardware until these tests run.
