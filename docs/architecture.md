# CIRCLE Rev A Architecture

> **ENGINEERING REVIEW ONLY ? NOT FOR FABRICATION OR HUMAN CONNECTION.**

CIRCLE is a two-board, battery-domain research instrument. `circle-main` contains ESP32-S3 compute, battery/power path, protected EDA, IMU, 4-bit SDMMC, reinforced-isolated SYNC, haptic/expansion, and observability. `circle-ppg` is a keyed replaceable optical contact board preserving raw red/IR data.

`BAT_HUMAN` and `LAB_ISO` are distinct electrical domains separated by ISOW7742. USB, debug, and external-expansion attachment directly force the hardware EDA path off. The architecture is `Sensors ? timestamp capture ? SRAM ? PSRAM ? asynchronous microSD`, with telemetry branching after record assembly. The closed loop is Human ? CIRCLE ? VitalSync ? DRR ? adaptive decision ? locally evidenced feedback ? Human ? measurement.

KiCad 10.0.5 parses, ERC-checks, and exports the generated legacy sources. Its CLI does not import legacy `.sch` into native `.kicad_sch`; native conversion therefore remains open. Architecture-level `NET:` annotations are not fabrication-ready electrical wiring.
