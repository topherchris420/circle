# CIRCLE Rev A EDA Safety Analysis

> **ENGINEERING REVIEW ONLY — NOT FOR HUMAN CONNECTION.** Values marked `REVIEW_GATE` are unresolved fabrication blockers. This analysis is not medical certification and cannot prevent an arbitrary grounded probe from bypassing intended attachment detection.

## Hardware equations

`EDA_PREPARE = EDA_FW_REQUEST & BATTERY_VALID & !USB_PRESENT & !DEBUG_ATTACHED & !EXTERNAL_EXPANSION_ATTACHED & SAFETY_POWER_GOOD`

`EDA_ACTIVE = EDA_PREPARE & EDA_ANALOG_GOOD`

Firmware requests operation but cannot override any hardware safety term. Every unsafe cable input directly removes the EDA rail and the two separately packaged normally-open switch drives.

## Qualification windows

- `BATTERY_VALID`: cell 3.20–4.25 V, permitted cell-temperature window, at least 100 mV hysteresis; false with battery absent or charger-only operation.
- `SAFETY_POWER_GOOD`: safety rail 3.15–3.45 V for at least 10 ms; asynchronous deassertion within 10 microseconds below 3.00 V, above 3.55 V, or on supervisor-power loss.
- `EDA_ANALOG_GOOD`: selected analog rail inside its component-qualified window for at least 10 ms; asynchronous deassertion on under/overvoltage, regulator fault, or monitor-power loss.

## State and single-fault table

| State or fault | Hardware result |
|---|---|
| Normal disabled | Analog rail off; K1/K2 open |
| Battery absent | BATTERY_VALID false; K1/K2 open |
| Charger only | BATTERY_VALID false; K1/K2 open |
| USB insertion | USB_PRESENT asynchronously removes rail and switch drive |
| Debug insertion | DEBUG_ATTACHED asynchronously removes rail and switch drive |
| External expansion insertion | EXTERNAL_EXPANSION_ATTACHED asynchronously removes rail and switch drive |
| Analog undervoltage | EDA_ANALOG_GOOD false; K1/K2 open |
| Supervisor power loss | Fail-safe output polarity removes permission |
| One welded electrode switch | Opposite conductor remains open or residual current remains below the analyzed limit; passive limiters remain in series |
| Firmware hang | Hardware terms dominate EDA_FW_REQUEST and watchdog evidence is logged |

Exact limiter, switch, leakage, and fault-current values remain gated for independent electrical safety review.
