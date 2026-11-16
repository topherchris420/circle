# First Light: a physical sensor, measured, refused, and verified

> **ENGINEERING REVIEW ONLY.** First Light uses a phone camera, not CIRCLE hardware. It is not a medical device, makes no measurement-performance or therapeutic claim, and closes no hardware review gate.

First Light is CIRCLE's first demonstration on a physical sensor. It shows one chain, end to end, and keeps the evidence for each link:

| Step | What happens | What is recorded |
| --- | --- | --- |
| **Measure** | A phone camera films a lit fingertip. Each frame becomes three numbers: mean red, green, blue. | `raw/frames.csv`: every frame, integer time and integer colour means |
| **Assess** | Once a second, six quality gates judge the last 8 seconds. | `decisions.json`: every gate, its measured value, and the reasons for any failure |
| **Respond** | When every gate passes on a clean window, the pulse is reported and a bounded sound follows it. | `feedback.json`: every command, with level, tempo, and brightness |
| **Disturb** | The sensor is failed on purpose: the finger is lifted, pressed, or moved. | The raw frames show it; the verifier finds it there |
| **Refuse** | The pulse is withheld and the sound is silenced, with the reason named. | The same ledger; a refusal is a decision |
| **Verify** | A second program, sharing no code with the first, rebuilds every decision from the raw frames. | A named verdict |

**[Run it in a browser](https://topherchris420.github.io/circle/first-light.html).** It has three sources: a real recording (no camera needed), your own phone camera, and a known-input optical phantom.

## Results

All results below come from real smartphone-camera video in the [BUT PPG 2.0.0](https://physionet.org/content/butppg/2.0.0/) dataset (Brno University of Technology, PhysioNet, CC BY 4.0, doi:10.13026/bvsb-mz80). It holds fingertip recordings from Xiaomi Mi9 and Huawei P20 Pro cameras, with chest ECG recorded at the same time and expert quality labels. People were asked to disturb the measurement on purpose: press harder, move the finger, walk, cough, laugh, change the light, talk.

People with even subject ids were used to calibrate thresholds. People with odd ids were held out.

### Round 2: pooled held-out test — passed

56 continuous sessions from 8 held-out people, 7,196 evaluations. The criteria were [committed and pushed before the test ran](../evidence/first-light/round-2/PREREGISTRATION.md), and the test ran once. [Result](../evidence/first-light/round-2/RESULT.md).

| Criterion | Bar | Measured |
| --- | --- | --- |
| R1 reported pulse within ±5 bpm of ECG over the same 8 seconds | ≥ 0.90 | **0.990** (575 of 581) |
| R2 windows the experts labelled unusable were refused | ≥ 0.95 | **0.994** (4,106 of 4,132) |
| R3 windows the experts labelled usable were acted on | ≥ 0.15 | **0.340** (490 of 1,440) |
| R4 audible commands issued with a refusal | 0 | **0** |

Both implementations agreed on all 7,196 decisions (`REPLAY_MATCH`, 56 of 56). Every session was rebuilt byte for byte from the public archive (`SOURCE_MATCH`, 56 of 56).

### Round 1: failed, and kept

Round 1 tested one held-out recording against a bar of 50% for R3. That bar was set without data. The system acted on 5.8% of usable windows and [failed](../evidence/first-light/round-1/README.md). Every action it did take was within 5 bpm of ECG.

Calibration then showed what the system actually does: at 97.8% accuracy it acts on 23% of usable windows, and no controller variant tried reached 50% at 90% accuracy. Round 2 restated R3 from that number, tightened R2, and tested on recordings round 1 had not touched.

### What the results do not show

- **Coverage depends on the person.** Two of eight held-out people account for 478 of the 490 actions. For two people the system never acted. Judged alone, 8 of 56 sessions pass every criterion.
- **Two phone models.** Other cameras are untested.
- **The live path has not been run on a physical device by the authors.** It is exercised with a simulated camera. A real fingertip session is yours to make; see [Add a recording](#add-a-recording).
- **No effect on a person.** The sound commands are recorded. No one heard them in these tests.
- **A camera pulse rate is not a medical measurement.**

## Verify it yourself

The verifier is one file with no dependencies beyond Python 3.11 or later.

```bash
python tools/verify_first_light.py evidence/first-light/sessions/149055-072.zip
```

To also rebuild the session from the public data, download the 91 MB archive from PhysioNet (SHA-256 `9b910fc884f63eca1c5d3a00c5710f838e0053dce94f8a02196bd0adc2ffa33c`):

```bash
python tools/verify_first_light.py evidence/first-light/sessions/149055-072.zip --source butppg-2.0.0.zip
```

To rerun the whole round 2 test, which also needs Node 18 or later:

```bash
python tools/run_first_light_round.py --source butppg-2.0.0.zip --split held-out
```

| Result | Values | Meaning |
| --- | --- | --- |
| integrity | `INTEGRITY_OK`, `INTEGRITY_FAILURE`, `INSUFFICIENT_EVIDENCE` | Every file matches its recorded SHA-256; nothing is missing or extra |
| replay | `REPLAY_MATCH`, `REPLAY_DIVERGENCE`, `VERSION_MISMATCH` | Every gate, decision, and command rebuilt from raw frames |
| protocol | `PROTOCOL_PASS`, `PROTOCOL_FAIL` | The preregistered criteria for the bundle's mode |
| source | `SOURCE_MATCH`, `SOURCE_MISMATCH`, `NOT_CHECKED` | Dataset sessions only: frames and reference rebuilt from the archive |

The verdict is `VERIFIED` only when all of these pass. A bundle that declares its own thresholds is a `VERSION_MISMATCH`: a record cannot loosen the gates it is judged by.

Changing a frame without updating the manifest is an `INTEGRITY_FAILURE`. Changing a frame or a decision and rewriting every hash is a `REPLAY_DIVERGENCE`. [`tests/test_first_light.py`](../tests/test_first_light.py) checks each case.

## The two sessions on the page

| Session | Role | Own verdict |
| --- | --- | --- |
| `149055-072`, 180 s | **Illustration, chosen after the test** because it shows every step | `VERIFIED`: 32 actions, all within 5 bpm of ECG; a deliberate pressure change refused; action resumes |
| `137025-054`, 300 s | **Preregistered**: the longest test session | `PROTOCOL_FAIL`: 291 refusals and no action; this person's signal never met the bar |

The illustration is an example, not evidence of typical performance. The pooled table is the evidence.

## Algorithm (`first-light-algorithm/1`)

Both implementations follow this text. Thresholds marked *calibrated* were chosen on calibration people only, by a rule stated in [`benchmark.json`](../evidence/first-light/benchmark.json). The smoothing length was searched there too and stayed at 7. The rest were fixed beforehand.

**Frames.** Each frame is `t_us, r, g, b`: integer microseconds since the first frame, and channel means in integer thousandths of the 0–255 scale. Time must increase.

**Schedule.** Evaluation *k* has nominal time `t0 + 9 s + k × 1 s`, for every nominal time at or before the last frame. Its cutoff is the time of the last frame at or before the nominal time. Its window holds the frames from `cutoff − 8 s` to `cutoff`.

**Gates.** All six must pass.

| Gate | Passes when | Reasons on failure |
| --- | --- | --- |
| `FRAMES` | At least 120 frames, and no gap longer than 250 ms, including the gap from the window start to the first frame | `TOO_FEW_FRAMES`, `FRAME_GAP` |
| `CONTACT` | Every frame has `r ≥ 100000` and `1000·r ≥ 550·(r+g+b)`: bright and red-dominant, as a torch-lit fingertip is | `NO_CONTACT` |
| `EXPOSURE` | Mean green in each of eight 1-second blocks is between 5,000 and 250,000 | `UNDEREXPOSED`, `SATURATED` |
| `STEADY` | The largest change between adjacent block means, divided by the window mean, is at most 0.05 *(calibrated)* | `UNSTEADY` |
| `PERIODIC` | Periodicity is at least 0.65 *(calibrated)* | `NOT_PERIODIC` |
| `RATE` | The rate is between 50 *(calibrated)* and 180 bpm | `IMPLAUSIBLE_RATE` |

If `FRAMES` fails, the other gates are not evaluated.

**Rate and periodicity.** Green is resampled by linear interpolation onto 400 points at 50 Hz ending at the cutoff. A centered 75-point moving average is subtracted, a centered 7-point moving average is applied, 37 points are dropped from each end, and the sign is flipped. Moving averages shrink at the edges. The normalized autocorrelation `r(L) = Σ z[i]·z[i+L] / √(Σ z[i]² · Σ z[i+L]²)` is computed for lags 14 to 76. Candidates are lags 15 to 75 with `r(L) > r(L−1)` and `r(L) ≥ r(L+1)`. The chosen lag is the earliest candidate with `r` at least 0.7 *(calibrated)* of the best candidate. It is refined by a parabola through its neighbours when the curvature is negative. The rate is `3000 / lag` bpm; periodicity is `r` at the chosen lag.

**Controller.** The decision is `ACT` when all six gates pass and the window starts at or after the cutoff of the most recent evaluation whose gates failed. Otherwise it is `REFUSE`. When the gates pass but the window is not yet clean, the reason is `AWAITING_CLEAN_WINDOW`. The pulse is reported only with `ACT`.

**Feedback (`first-light-feedback/1`).** With `ACT`: tempo starts at the rate after silence and then moves at most 6 bpm per evaluation; level rises by 0.1 per evaluation to a ceiling of 0.3; brightness is `(tempo − 50) / 70`, clamped to 0–1. With `REFUSE`: silent, level 0, tempo cleared.

## Evidence bundle (`circle-first-light-bundle/1`)

A zip, stored uncompressed with fixed timestamps so the same session always produces the same bytes.

| File | Holds |
| --- | --- |
| `manifest.json` | SHA-256 and size of every other file; the software version |
| `protocol.json` | Mode, and the algorithm, feedback mapping, and criteria it claims to follow |
| `raw/frames.csv` | Every frame |
| `decisions.json` · `feedback.json` | Every evaluation and every command |
| `reference.json` | Dataset sessions: ECG beat times, expert labels, and file hashes. Phantom sessions: the programmed rate |
| `device.json` · `raw/marks.csv` | Live sessions: capture settings and when each prompt was shown. No image, audio, or device identifier |

Hashes detect change. They do not show where frames came from.

## Acceptance criteria (`first-light-criteria/2`)

**Dataset sessions** are judged by R1 to R4 above, over one session or pooled over many with `--pool`. A window counts as usable or unusable only when it lies wholly inside segments with that label. An action is judged against ECG when its window holds at least five beats.

**Live sessions.** The verifier takes nothing from the page's prompts. It finds the fault in the raw frames: the first run of out-of-contact frames, after the first action, lasting at least 2 seconds.

| Criterion | Requires |
| --- | --- |
| L1 | At least 5 actions before the fault |
| L2 | A fault is present |
| L3 | The first refusal comes within 1.5 s of the first out-of-contact frame |
| L4 | No action's window contains an out-of-contact frame |
| L5 | No audible command during refusal, or after the refusal deadline until action resumes |
| L6 | Action resumes, on a window that starts after the last fault frame |
| P1 (phantom) | At least 0.9 of reported rates within ±2 bpm of the programmed rate |

The live criteria have been exercised on synthetic input only. They have not been tested on a physical camera.

## Two implementations

[`site/first-light-core.js`](../site/first-light-core.js) runs in the page and, under Node, builds the committed bundles. [`tools/verify_first_light.py`](../tools/verify_first_light.py) is the second implementation. Decisions, gates, reasons, and times must be equal exactly. Derived numbers must agree to a relative 10⁻⁹.

Writing the second implementation exposed details the first left implicit. Each is now fixed in the text above:

| Left implicit | Resolved as |
| --- | --- |
| Which frames an evaluation may use | Only frames at or before the nominal time; the cutoff is the last of them |
| Interpolating the first grid point | Uses the frame just before the window, when one exists |
| Moving-average edges | The average shrinks; nothing is padded |
| Ties between autocorrelation peaks | Strictly greater than the left neighbour, at least the right; earliest qualifying lag |
| Parabolic refinement on a flat peak | Applied only when the curvature is negative |
| Order of summation | Explicit running sums. Python's built-in `sum` compensates for rounding and would differ from JavaScript |
| Contact test rounding | Integer arithmetic only |
| A frame exactly at the cutoff | Belongs to the eighth block |
| Number formatting between languages | Hashes cover file bytes; values are compared after parsing |
| The dataset's reference heart rate | Recomputed from ECG beat times over the same 8 seconds. The dataset's whole-record figure describes 10 seconds |
| The dataset's file layout | Three-channel records only. Single-channel records cannot carry the contact test and are excluded |

## Questions this demonstration answers

The [REA research notes](rea-research/README.md) record patterns in commercial and research systems that motivated parts of CIRCLE. First Light answers some of them on real sensor data:

| Theme | What you can check here | Motivating note |
| --- | --- | --- |
| **Adaptive** | The mapping from pulse to sound is published, bounded, and replayable; every command is in the record | [BioChord](rea-research/biochord.md) |
| **Interpretable** | Each decision names its gates, values, thresholds, and reasons; nothing is scored by a hidden formula | [Healium](rea-research/healium.md) |
| **Auditable** | Raw frames ship with the decisions; a second implementation rebuilds them | [NextSense](rea-research/nextsense.md) |
| **Replicable** | The test reruns from a public archive with one command; the ambiguities replication exposed are listed above | [Inherent Labs](rea-research/inherent.md) |
| **Verified against a baseline** | Criteria were committed before the test; a failed round is kept; the reference is ECG, not self-report | [Autoscience](rea-research/autoscience.md) |

These notes describe publicly observable behaviour only. Nothing here is a claim about any product's quality.

## Add a recording

A session from your own phone is evidence this repository does not yet have.

1. Open the page on a phone, choose **Use your camera**, and follow the prompts.
2. Download the bundle and run `python tools/verify_first_light.py <bundle>`.
3. Open a pull request that adds the bundle under `evidence/first-light/live/`, with the phone model and browser, and the verdict, pass or fail.

A bundle holds per-frame colour averages and timing. It contains a pulse waveform, which is personal physiological data. Publish it only if you are content for it to be public.

## Where this sits

First Light does not advance the [physical evidence ladder](physical-evidence-ladder.md), which concerns CIRCLE's own boards. It rehearses the evidence discipline on a sensor people already own, as the [Cyton phantom](openbci-cyton.md) does for acquisition. The camera stream is not connected to the physiology controller, the consent gate, or the protocol runner.
