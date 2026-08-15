# Timing and Data Model

> **ENGINEERING REVIEW ONLY ? NOT FOR FABRICATION OR HUMAN CONNECTION.**

The authoritative timebase is the device monotonic clock with 1 microsecond resolution. Host-clock mapping is metadata and never replaces native time. EDA/IMU reconstruction uncertainty is bounded at 100 microseconds; PPG FIFO reconstruction uncertainty is bounded at 1 millisecond and is carried as quality metadata.

Every record uses the session schema names `schema_version`, `record_type`, `provenance`, `device_time_start_us`, `device_time_end_us`, `status_flags`, and `crc32c`. Streams carry sequence ranges; exact missing ranges become `GAP` records. PPG raw red/IR, EDA ADC, and IMU acceleration/angular-rate remain `RAW_MEASURED`; derived/model data retains lineage.

SYNC target: ?2 microseconds calibrated delay, 250 nanoseconds peak-to-peak jitter, and 500 nanoseconds pulse-width error for pulses ?10 microseconds. Haptic command, electrical onset, physical observation, completion, and fault are distinct events; measured command-to-physical latency is required before claims.
