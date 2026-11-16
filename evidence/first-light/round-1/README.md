# First Light, round 1: preregistered criterion failed

This folder is kept unchanged as evidence history. Round 1 is the first
complete run of First Light's chain on a real recording. It **failed** one of
its four preregistered criteria.

| Criterion (`first-light-criteria/1`) | Required | Measured | Result |
| --- | --- | --- | --- |
| R1 accuracy against chest ECG over the same window | ≥ 0.9 of ACT rates within ±5 bpm | 1.0 (7 of 7) | PASS |
| R2 refused what the dataset's experts rejected | ≥ 0.8 of expert-poor windows | 1.0 | PASS |
| R3 acted when the evidence was good | ≥ 0.5 of expert-good windows | **0.058** | **FAIL** |
| R4 silent while refusing | 0 audible commands | 0 | PASS |

Integrity, replay, and source all held:

- **`REPLAY_MATCH`**: the Python verifier rebuilt all 251 decisions from the
  raw frames and agreed with the browser implementation.
- **`SOURCE_MATCH`**: every frame and every ECG beat time was rebuilt byte for
  byte from the public BUT PPG 2.0.0 archive.

The overall verdict is `PROTOCOL_FAIL`.

## What the failure showed

The session is held-out person 135, records 135029 to 135054 (260 s). It was
chosen by `tools/build_first_light_session.py` from labels and seam continuity
alone. On this person's camera signal the median periodicity was 0.47, below
the calibrated 0.65 threshold, so the system refused 244 of 251 evaluations.
Every one of its 7 actions was within 5 bpm of the ECG.

The system was safe but nearly mute. The R3 requirement of 0.5 was set before
the benchmark ran. The round-1 benchmark (`benchmark.json`) then measured
per-record coverage of expert-good records at only 0.32 on calibration and
0.35 on held-out. On calibration subjects' continuous runs, the same algorithm
acted on 23% of good windows.

## What it changed

Round 2 recalibrates on calibration subjects only. It extends the grid to the
smoothing length and keeps the same selection rule. Its criteria were committed
before its test ran, and the test uses held-out runs that round 1 did not touch.
Subject 135 is excluded from round 2's test.

To re-verify this folder, check out the commit that added it. The verifier at
that commit carries `first-light-algorithm/1` with round-1 thresholds. Later
verifiers report `VERSION_MISMATCH` for this bundle, by design: they will not
judge a record against rules they did not publish.
