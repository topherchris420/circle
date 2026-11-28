# First Light, round 2: result

Dataset citation: [BUT PPG 2.0.0](https://doi.org/10.13026/tn53-8153). See the [citation correction](../README.md#citation-correction) for archived metadata.

The test in [`PREREGISTRATION.md`](PREREGISTRATION.md) ran once, after that
file was committed and pushed. It passed. Full output:
[`result.json`](result.json).

## Pooled held-out test

56 continuous sessions from 8 held-out people, 7,196 evaluations. All data is
real smartphone-camera video from BUT PPG 2.0.0, with chest ECG recorded at the
same time.

| Criterion (`first-light-criteria/2`) | Bar | Measured | Result |
| --- | --- | --- | --- |
| R1 ACT rates within ±5 bpm of the same-window ECG | ≥ 0.90 | **0.990** (575 of 581) | PASS |
| R2 expert-poor windows refused | ≥ 0.95 | **0.994** (4,106 of 4,132) | PASS |
| R3 expert-good windows acted | ≥ 0.15 | **0.340** (490 of 1,440) | PASS |
| R4 audible commands issued with a refusal | 0 | **0** | PASS |

- **Replay: 56 of 56 `REPLAY_MATCH`.** The browser implementation produced each
  bundle; the independent Python implementation rebuilt every decision from the
  raw frames and agreed.
- **Source: 56 of 56 `SOURCE_MATCH`.** Every frame and ECG beat time rebuilt
  byte for byte from the public archive.

## What the result does not show

- **Coverage depends on the person.** Two of the eight people account for 478
  of the 490 actions on expert-good windows. For two people the system never
  acted. Judged alone, 8 of the 56 sessions pass all four criteria; most of the
  rest fail R1 or R3 because the system acted rarely or never.
- **Two phone models.** Xiaomi Mi9 and Huawei P20 Pro. Other cameras are untested.
- **Accuracy is against ECG rate over 8 seconds, within 5 bpm.** A camera pulse
  rate is not a medical measurement.
- **No effect on a person is tested.** The feedback commands are recorded; no
  one heard them.

## The two sessions on the web page

| Session | Role | Own verdict |
| --- | --- | --- |
| [`137025-054`](../sessions/137025-054.zip) (300 s) | Preregistered: the longest test session | `PROTOCOL_FAIL`. The system refused all 291 evaluations; this person's signal never met the bar. Every expert-poor window was refused. |
| [`149055-072`](../sessions/149055-072.zip) (180 s) | Illustration, chosen after the test | `VERIFIED`. 32 actions, all within 5 bpm of ECG; a deliberate, expert-rejected pressure change refused; action resumes afterwards. |

**Deviation from the preregistration.** The preregistration named one page
session, the longest. It shows no action, so it cannot show the adaptive
response. The page therefore also offers a second session, selected by outcome:
the shortest individually verified session with a deliberate, expert-rejected
disturbance that has at least five actions before it, none inside it, and at
least one after it. The page labels it as an illustration chosen after the
test. It is not evidence of typical performance; the pooled table above is.

## Per-record benchmark

[`../benchmark.json`](../benchmark.json) evaluates each 10-second held-out
fingertip record once, without the controller: 125 of 960 admitted, 96.0%
within 5 bpm of ECG, 97.7% of expert-poor records refused, 34.8% of
expert-good records admitted. These numbers are identical to round 1's, because
the algorithm did not change.

## Reproduce

```bash
python tools/run_first_light_round.py --source butppg-2.0.0.zip --split held-out
python tools/verify_first_light.py evidence/first-light/sessions/149055-072.zip --source butppg-2.0.0.zip
```

The archive is the 91 MB download from
<https://physionet.org/content/butppg/2.0.0/> (CC BY 4.0), SHA-256
`9b910fc884f63eca1c5d3a00c5710f838e0053dce94f8a02196bd0adc2ffa33c`.
