# First Light: prospective physical-device test

**STATUS: PLANNED, NOT PERFORMED.** No physical-device session is claimed here.
The existing 56-session study used public real-camera recordings from two
phone models; its live browser camera path has only been simulated.

## Pre-register before collecting

Record the code commit, unchanged thresholds, expected outcomes, exclusion
criteria, reference synchronization, and analysis before testing new data.
Recruit consenting adult volunteers using at least three distinct smartphone
models and both iOS and Android where feasible. Collect repeated sessions and
log device model, OS, browser, lighting, permissions and frame cadence.

Primary engineering checks: camera works only after explicit consent; raw
frames/timestamps are recorded locally; admitted windows are accompanied by
quality-gate decisions; deliberate motion, lost contact and changing light
cause a reasoned refusal and silence; evidence bundles independently replay;
no sensor data leaves the browser unexpectedly.

If independent, synchronized ECG reference is available, compute the fraction
of admitted 8-second windows within ±5 bpm of ECG, stratified by person, device
and condition. **Without ECG, do not claim heart-rate accuracy.** Report
attempted windows, admitted windows, expert-usable windows, refused windows,
accuracy denominator, zero-admission participants, errors and uncertainty
intervals. Publish negative and missing outcomes rather than filtering them.

## Per-session steps

1. Confirm HTTPS, browser camera permission and muted audio by default.
2. Record a clean fingertip segment, then deliberate movement/contact loss.
3. Confirm the feedback holds, names its reason and resumes only on clean data.
4. Download the untouched evidence ZIP; run its independent verifier.
5. Retain failures and record whether reproduction passed, diverged or lacked
   evidence. Do not tune thresholds on held-out participants.

Stop on unexplained audio during a refusal, unexpected upload, a camera/privacy
surprise or unrepeatable evidence. No proposed CIRCLE electrode hardware may be
connected to people under this protocol.

Consent, privacy and applicable ethics review are required. De-identify records;
do not publish personally identifying video or physiological data without
permission. These engineering tests cannot establish clinical accuracy,
therapeutic effects, or safety of proposed CIRCLE hardware.

See [First Light methods](first-light.md),
[existing results](../evidence/first-light/round-2/RESULT.md), and
[physical validation ladder](physical-evidence-ladder.md).
