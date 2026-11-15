# CIRCLE — the film

**Close the loop. Keep the evidence.**

A 90-second film for CIRCLE by Vers3Dynamics, and a 30-second cut of it.

| File | What it is |
| --- | --- |
| [`circle-film-90s.mp4`](circle-film-90s.mp4) | The film. 1920 × 1080, 30 fps, H.264 + AAC, stereo. |
| [`circle-film-30s.mp4`](circle-film-30s.mp4) | The workbench-only cut: signals, audio and field, gate failure, evidence, end card. |
| [`circle-film-poster.jpg`](circle-film-poster.jpg) | Poster frame (the end card). |
| [`ad/`](ad) | The source: the composition, its data, the score, and the renderer. |

> [!WARNING]
> **ENGINEERING REVIEW ONLY.** Everything the film shows is simulated. No person
> is measured, no hardware is connected, and no effect in people is claimed.
> The film carries a `SIMULATION ONLY` label on every frame that shows data.

## The idea

The film does not animate what CIRCLE might do. It replays what this repository
did: one simulated session, one failure injected on purpose, one recorded
R.A.I.N. run, one verification. The product shots are the product — the real
Resonance Workbench page, embedded and operated through its own tabs,
scrubber, checkbox, and evidence list.

Five chapters close a ring, one arc each: **sensing, adaptation, uncertainty,
reasoning, verification**. When the ring closes, it is the logo.

## Shot list

Times are film seconds. The score is 96 BPM, so a bar is 2.5 s and every cut
lands on a bar line.

| Time | Picture | Words on screen |
| --- | --- | --- |
| 0.0 – 7.5 | Raw PPG, EDA, and IMU traces draw on | *A human state is never one signal.* |
| 7.5 – 10.0 | The ring draws; title | *CIRCLE · Resonance Workbench* |
| 10.0 – 22.5 | **Sensing.** The dashboard plays the session | *Start with a signal whose truth is known.* · *Four signals. One clock.* · *Every trace names its source.* · *Every evaluation is graded.* |
| 22.5 – 32.5 | **Adaptation.** Audio is enabled; the field; the loop starts guidance | *Sound, only by consent.* · *Feedback that follows the evidence.* · *Two systems agree. The loop acts.* |
| 32.5 – 35.0 | Black | *Now break it.* |
| 35.0 – 50.0 | **Uncertainty.** The pulse channel stops; the gate closes; the sound stops; the evidence explorer | `DATA_STALE` · *The audio mutes.* · *No evidence. No feedback.* · *CIRCLE says why.* · *“a loop that cannot observe its effect was stopped”* |
| 50.0 – 67.5 | **Reasoning.** R.A.I.N.'s proposal, CIRCLE's validation, the comparison | *Then ask a better question.* · *It may propose.* · *CIRCLE decides.* · *Run against the baselines.* · *Not supported.* · *Published anyway.* |
| 67.5 – 80.0 | **Verification.** The bundle, the verifier, the verdict | *Don't take our word for it.* · `REPLAY_MATCH` · *Download the evidence. Reproduce the verdict.* |
| 80.0 – 90.0 | The ring closes into the logo | *Close the loop. Keep the evidence.* |

## Every claim, and where it comes from

| On screen | Source |
| --- | --- |
| The three opening traces; the pulse trace that stops | Raw `ppg.csv.gz`, `eda.csv.gz`, `imu.csv.gz` from the session's own export, decimated to 50 Hz. The 14-second gap is the gap in the file; nothing is interpolated across it. |
| The session | `sensor_loss`, seed 7, active arm, audio consent executed through the gate. Built by [`tools/build_ad.py`](../tools/build_ad.py) with the same `Workbench` the local server uses. |
| Every dashboard, field, and evidence frame | The Resonance Workbench itself ([`ad/workbench.html`](ad/workbench.html) is `resonance.html` pointed at the repository's own assets). |
| `level 0.125 of a 0.50 ceiling`, `breath 6.0 s`, `state PROGRAM` | The recorded feedback event at the playhead. |
| `ppg_age_s 4.998 · EVAL-037`, `DATA_STALE` | The controller evaluation that failed the gate, as exported in the ledger. |
| *“a loop that cannot observe its effect was stopped”* | The controller's own rule text for decision `PBR-1-STOP`. |
| The R.A.I.N. proposal, its confidences and envelope hashes, the four results, `NOT_SUPPORTED` | [`docs/rain-live-run-2026-11-15.json`](../docs/rain-live-run-2026-11-15.json), read unchanged. The analysis plan (paired sign-flip permutation, α = 0.05) is the one `models/rain_connector.py` composes. |
| The five validation checks | What `models/protocols.validate` and `authorize` enforce. |
| The verifier command, its three lines of output, the eleven named checks | `tools/verify_replication.py`, run by the builder on the session's export. The build fails if the verdict is not `REPLAY_MATCH`. |
| The sound of the engine in chapters two and three | CIRCLE's own `synth.js`, rendered offline against the recorded feedback schedule. See below. |

What is staged, plainly: the session is played as a time-lapse (six minutes in
about twenty seconds, with cuts); the pointer is drawn by the film, though it
presses the real controls; the R.A.I.N. cards, the terminal, and the comparison
are typeset by the film from the records above; and the opening and dropout
traces are the film's own drawing of raw samples, not a workbench view.

## The sound

- **The score** is original and synthesized from arithmetic in
  [`ad/soundtrack.py`](ad/soundtrack.py) — no samples, no loops, nothing
  licensed. It is written per bar, so the 90-second film and the 30-second cut
  render from the same score through their edit lists.
- **The engine** is not music. From the moment audio is enabled in the film,
  one layer of the mix is the product's adaptive audio engine: the workbench's
  `synth.js` and `audio-engine.js`, run in an offline audio context against the
  recorded feedback schedule, following the same session playhead as the
  picture.
- **The silence** at 37.5 s is the point. The engine's level falls to zero
  because the recorded gate closed; the score is cut with it.

The mix measures about −14 LUFS integrated with a −1 dBFS true peak. It was
balanced by measurement — levels per bar, spectrum per section — not by ear:
it was produced in a headless environment. Listen before you publish it.

## Rebuild it

Needs Python 3.11+ with the repository's requirements, Node with Playwright's
Chromium, and ffmpeg.

```bash
python tools/build_ad.py
```

```bash
node marketing/ad/render.cjs --cut 90
```

```bash
node marketing/ad/render.cjs --cut 30
```

`build_ad.py` runs the session, verifies it, and writes `ad/ad-data.js` and
`ad/workbench.html`. `render.cjs` renders the engine layer, synthesizes the
score, steps the film clock frame by frame at 2× and encodes. Intermediate
audio lands in `ad/out/` (ignored by git). A render of the same data is
frame-identical: the page is a pure function of film time, with no CSS
transitions or timers.

To preview and scrub in a browser, serve the repository root and open the page:

```bash
python -m http.server 8000
```

Then visit `http://127.0.0.1:8000/marketing/ad/` (add `?cut=30` for the short
cut). The preview plays with sound once a render has written `ad/out/`.

Rebuilding the data starts a new session, so the session id and bundle name on
screen change with each build; the evidence they point to does not.

## Type

The reference render uses Inter Display, Inter, and JetBrains Mono as installed
on the render machine. The stylesheet asks for SF Pro first on a Mac. No font
files are bundled.

## Not in the film

- Any claim that a signal, sound, or protocol changes a person's state.
- Any real-device footage. The hardware is designed, not built.
- A supported result. The recorded R.A.I.N. run came back `NOT_SUPPORTED` for
  the proposal and for every baseline. The film says so.
