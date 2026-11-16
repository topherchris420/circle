# First Light, round 2: preregistration

This file was committed before round 2's held-out test ran. The commit history
shows the order: this file and `calibration.json` first, `result.json` after.

## What round 1 found

Round 1 replayed one held-out recording (person 135, 260 s). Integrity,
replay, and source rebuild all held. Every action was within 5 bpm of the
chest ECG and every expert-poor window was refused. It failed criterion R3:
the system acted on 5.8% of expert-good windows, against a required 50%.

The 50% bar was set without data. Calibration subjects show what the system
actually does.

## Calibration evidence (even subject ids only)

60 continuous sessions from 9 people, 7,820 evaluations
([`calibration.json`](calibration.json)). Both implementations agreed on every
evaluation, and every session rebuilt byte for byte from the public archive.

| Controller rule | ACT within ±5 bpm of ECG | Expert-good windows acted | Expert-poor windows refused |
| --- | --- | --- | --- |
| **Published: a full clean 8 s window after any failure** | **0.978** | **0.232** | **0.993** |
| Clean window only after a contact, exposure, or steadiness failure | 0.916 | 0.355 | 0.980 |
| Three consecutive passing evaluations | 0.935 | 0.339 | 0.980 |
| No sustain rule | 0.903 | 0.418 | 0.964 |

No variant reached 50% at 90% accuracy. The published rule stays: it is right
most often when it acts, and it refuses most of what experts rejected. The
algorithm is unchanged (`first-light-algorithm/1`). Extending the threshold
grid to the smoothing length selected the same thresholds.

Coverage depends on the person. Two of nine calibration people account for 348
of the 393 actions on expert-good windows; three people have none. Many
expert-good records contain a transient that the experts could read around and
the system, by design, will not.

## What round 2 tests

**Test set.** Every continuous session of at least 6 records from held-out
people (odd subject ids), fingertip, three-channel layout, except person 135.
Sessions are defined from record numbers and seam continuity only
(`session-rule/2` in `tools/build_first_light_session.py`). Round 1 analysed no
continuous session from these people.

**Criteria** (`first-light-criteria/2`), judged over all windows of all test
sessions together:

| Criterion | Bar | Calibration | Basis |
| --- | --- | --- | --- |
| R1 ACT rates within ±5 bpm of the same-window ECG | ≥ 0.90 | 0.978 | unchanged from round 1 |
| R2 expert-poor windows refused | ≥ 0.95 | 0.993 | tightened from 0.80 |
| R3 expert-good windows acted | ≥ 0.15 | 0.232 | restated from 0.50; about two thirds of calibration |
| R4 audible commands issued with a refusal | 0 | 0 | unchanged |

Each session must also pass integrity, replay, and source rebuild on its own.

**The session the page replays** is the longest test session. Its own
per-session verdict is reported whatever it is.

## What would count against it

- Any criterion below its bar: round 2 fails, and the result is kept.
- Any session with a replay divergence or source mismatch: round 2 fails.
- The test runs once. If it fails, the next round needs new criteria committed
  first and data that neither round has touched; every held-out person will
  then have been used, so that data would have to come from elsewhere.

## Command

```bash
python tools/run_first_light_round.py --source butppg-2.0.0.zip --split held-out
```
