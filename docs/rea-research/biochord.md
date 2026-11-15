# BioChord — Evidence report

**Product:** BioChord physiological audio-biofeedback engine (licensable SDK)
**Vendor:** BioChord Software, Inc. (Delaware C-Corporation; 2–10 employees per LinkedIn)
**Research date:** November 15, 2026. All URLs were publicly accessible at research time; no logins, paywalls, or proprietary assets were bypassed. Proprietary algorithms and unpublished implementation details are treated as unknown throughout.

BioChord is a licensable, on-device software engine that converts a wearable's heartbeat signal — specifically the stream of beat-to-beat intervals — into real-time, adaptive generative audio intended to guide the listener toward resonance breathing (~6 breaths/minute) and autonomic calm. It is a B2B product: BioChord does not sell a consumer app; wearable makers and health/wellbeing platforms license the engine and ship it inside their own products. As of late 2026 the company is very young — incorporated Q1 2026, MVP and showcase apps in Q2 2026, pilot programs and first LOIs in Q3 2026, with first licensing partners claimed for Q4 2026 — and its public footprint is essentially one marketing website plus a LinkedIn page. The publicly documented signal chain is unusually specific for a marketing site (seven named stages, latency and update-rate figures), but the patent-pending control core and DSP internals are proprietary and unverifiable from public sources. Note: an unrelated hackathon project also named "BioChord" (Devpost, FigBuild 2026, plant-biofrequency concept) exists; it is a namesake, not this company, and is excluded from findings.

## Sources consulted

| URL | What it contributed |
|---|---|
| https://biochord.health (rendered) | Full marketing site: seven-stage signal chain, SDK architecture claims, performance figures, licensing model, milestones, research citations, partner categories |
| https://biochord.health (raw HTML) | FAQ answers via embedded schema.org FAQPage JSON-LD (site accordions): mechanism, hardware support, integration time, privacy, licensing; org/software structured data (BioChord Software, Inc.; B2B license; "hardware-agnostic SDK") |
| https://www.linkedin.com/company/145200217 (via search) | Company profile: founding positioning, 2–10 employees, launch announcement post (~Oct 2026), restated technical claims |
| https://devpost.com/software/biochord (via search) | Confirmed as an unrelated namesake project (plant bio-frequencies); used only to disambiguate |
| PubMed links cited on biochord.health (Lehrer 2020; Goessl 2017; Zucker 2009; JAMA Psychiatry 2025) | Study titles/venues as cited by the vendor; used as vendor-cited background evidence for HRV biofeedback, not independently fetched |
| https://www.linkedin.com/company/145200217 and site footer | Contact channel (partners@biochord.health), demo-by-request model — implies no public self-serve demo exists |

## Findings

### Publicly documented heartbeat-to-audio signal chain

- **DOCUMENTED** — The site describes a seven-stage closed loop (marketing page, "How it works"):
  1. **01 · SENSE** — "Wearable PPG": beat-to-beat intervals stream from any supported wearable over BLE.
  2. **02 · CLEAN** — "Signal processing": quality check, pulse detection, inter-beat-interval (IBI) extraction.
  3. **03 · MEASURE** — "HRV engine": sliding-window analysis deriving continuous heart-rate variability.
  4. **04 · REGULATE** — "Layered Control Core": parallel regulation across timescales with RSA phase-locked control; labeled "patent-pending core."
  5. **05 · MAP** — "Audio mapping": control signals map to musical parameters — timbre, density, space.
  6. **06 · SYNTHESIZE** — "DSP audio engine": a low-latency synthesizer renders sound in real time.
  7. **07 · DELIVER** — "Audio output" through headphones or speaker.
  8. **↺ THE LOOP** — "Closed feedback": the listener's changing physiology re-enters the loop moment to moment.
- **DOCUMENTED** — Stated performance figures: **≤ 250 ms end-to-end latency**, **≥ 1 Hz HRV update rate**, **≥ 5 Hz RSA phase update rate**. These are vendor claims on a marketing page; no independent measurement exists.
- **DOCUMENTED** — Differentiator claim: generic adaptive audio reacts to "a heart-rate number," whereas BioChord "phase-locks the sound to the respiratory–cardiac rhythm itself" (respiratory sinus arrhythmia, RSA — the coupling between breathing and heart rate) and "drifts each listener toward their individual resonance frequency," the breathing pace where the autonomic nervous system responds most strongly. Target rhythm stated as "about six breaths per minute."
- **INFERRED** — Reading the stages together, the engine's input contract is a single IBI time-series; pulse detection/IBI extraction is listed as a stage, which suggests the SDK can also accept a rawer PPG-like input on at least some paths, but the "hardware-agnostic" FAQ text says the only required input is the interval stream. Whether both input modes ship is unknown.
- **UNVERIFIED** — The actual algorithms inside the Layered Control Core (control-law structure, how "parallel regulation across timescales" is implemented), the audio mapping functions, and the synthesizer architecture. These are explicitly patent-pending/proprietary; treat as unknown.

### SDK architecture and interface

- **DOCUMENTED** — Ships as "a self-contained library with a clean interface": `start()`, `stop()`, `reset()`. "Stateless to initialise, stable public interface, integrated in under a day" (marketing and FAQ structured data agree).
- **DOCUMENTED** — Integration claim: "typical integration takes under one day"; requires no in-house DSP, audio-engineering, or signal-processing team; the partner "streams beat-to-beat data in and gets adaptive biofeedback audio out."
- **DOCUMENTED** — "Licence-clean": built exclusively from permissive components (Apache 2.0, MIT, BSD); no GPL/copyleft; ships with third-party notices for legal review.
- **DOCUMENTED** — Target operating environment per schema.org structured data: "Any (SDK, hardware-agnostic)." Specific platforms (iOS/Android/embedded), binary formats, language bindings, and API details beyond `start()/stop()/reset()` are **UNVERIFIED** — no public developer documentation exists.
- **INFERRED** — Given "on-device," "no cloud round-trip," and phone/wearable framing, the SDK most plausibly runs in the partner's mobile app (and potentially on wearable silicon), but the deployment target is not explicitly stated anywhere public.

### Beat-interval processing

- **DOCUMENTED** — Beat-interval handling per the public chain: quality check → pulse detection → IBI extraction → sliding-window HRV at ≥ 1 Hz → RSA phase estimation at ≥ 5 Hz feeding the control core.
- **DOCUMENTED** — The engine "reads the cardiac–respiratory rhythm (HRV and RSA phase), not just a heart-rate number" (LinkedIn about section, consistent with the site).
- **INFERRED** — A "quality check" stage implies artifact/interval-outlier rejection before HRV computation, but no public detail exists on what the check tests or how failures are handled (see Quality/error states below).
- **UNVERIFIED** — Window lengths, HRV metrics used (e.g., RMSSD vs. spectral), resonance-frequency estimation method, and how the "individual" resonance frequency is learned per listener. All proprietary.

### Real-time audio mapping

- **DOCUMENTED** — Control signals map to "musical parameters — timbre, density, space." Sound is described as generative ("the music you hear is not composed" is from the namesake Devpost project — do not attribute; BioChord's own wording is "generative sound" on LinkedIn and "real-time, adaptive sound" on the site).
- **DOCUMENTED** — The user-facing experience is audio delivered via headphones or speaker; the sound "is shaped by the listener's own physiology and changes as their body changes" (LinkedIn).
- **INFERRED** — Mapping musical parameters (timbre/density/space) rather than pitch or tempo suggests an ambient-texture design that avoids a literal "heartbeat sonification" — plausible design intent, but the actual sound character is undocumented.
- **UNVERIFIED** — What the audio actually sounds like. No public audio demo, video, or playable showcase was found; demos are by request ("Request a live demo of the BioChord engine running on your device").

### Hardware-independent interface design

- **DOCUMENTED** — Hardware-agnostic by contract: "The only input is a beat-to-beat interval time-series. If a device can expose it, BioChord runs on it — insulated from any wearable's SDK internals" (marketing; FAQ structured data echoes: only required input is a beat-to-beat interval stream over BLE).
- **DOCUMENTED** — Live integrations today: chest straps and fitness watches that stream beat-to-beat intervals. Roadmap categories: smartwatches, smart rings, recovery bands, and other BLE heart-rate sensors.
- **INFERRED** — The design pattern (accept intervals, not raw PPG, from any device) is the same hardware-decoupling strategy CIRCLE uses with simulated streams; BioChord's contribution is the control/sonification layer, not sensing.
- **UNVERIFIED** — Names of any actual integration partners, showcase apps, or pilots. The Q3 2026 "pilot programs & first LOIs" milestone names no customers.

### Session flow, quality and error states

- **DOCUMENTED** — Intended user experience (from partner/user descriptions): the listener hears adaptive sound; as their body changes, the sound responds; the engine gently tunes them toward ~6 breaths/minute resonance breathing. There is no publicly documented session start/end UX, scoring, progress tracking, or history — consistent with a licensed engine whose partners own the app UX.
- **DOCUMENTED** — A signal-quality check exists as stage 02 of the public chain.
- **UNVERIFIED** — Error states: behavior on BLE dropout, poor-quality signal, invalid intervals, or inadequate data for HRV estimation; whether `reset()` clears learned state; any minimum data requirements. Nothing public describes these.
- **UNVERIFIED** — Session outcomes or efficacy of the BioChord product itself. The site cites HRV-biofeedback literature (Lehrer 2020 meta-analysis; Goessl 2017 meta-analysis on stress/anxiety; Zucker 2009 RSA-biofeedback pilot; a 2025 JAMA Psychiatry RCT) as evidence for the *mechanism*, and explicitly disclaims: "Research is cited to describe the mechanism BioChord is built on, not to claim equivalent outcomes." No BioChord-specific study exists.
- **DOCUMENTED** — Regulatory posture: explicitly not a medical device; "no diagnostic or therapeutic claims."

### Privacy architecture

- **DOCUMENTED** — 100% on-device signal processing; no cloud round-trip; no raw physiological data leaves the device ("only anonymised usage events"); GDPR-compatible by design. Stated repeatedly and consistently across the site and LinkedIn.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| Seven-stage signal chain (sense → clean → measure → regulate → map → synthesize → deliver, closed loop) | DOCUMENTED | https://biochord.health |
| ≤ 250 ms end-to-end latency; ≥ 1 Hz HRV update; ≥ 5 Hz RSA phase update | DOCUMENTED (vendor claim) | https://biochord.health |
| SDK interface is start()/stop()/reset(); stateless init; < 1 day integration | DOCUMENTED (vendor claim) | https://biochord.health |
| Only input is beat-to-beat interval time-series over BLE; hardware-agnostic | DOCUMENTED | https://biochord.health |
| Audio mapping targets timbre, density, space | DOCUMENTED | https://biochord.health |
| RSA phase-locking, multi-timescale control core; guides toward individual resonance frequency (~6 breaths/min) | DOCUMENTED (mechanism claim, patent-pending) | https://biochord.health ; https://www.linkedin.com/company/145200217 |
| Built from permissive-license components only (Apache-2.0/MIT/BSD) | DOCUMENTED (vendor claim) | https://biochord.health |
| All processing on-device; no raw physiological data leaves device; GDPR-compatible | DOCUMENTED (vendor claim) | https://biochord.health |
| Live integrations: chest straps, fitness watches; rings/smartwatches on roadmap | DOCUMENTED (vendor claim) | https://biochord.health |
| Company milestones: Q1 2026 incorporation → Q4 2026 first licensing partners | DOCUMENTED | https://biochord.health |
| HRV-biofeedback research base (Lehrer 2020; Goessl 2017; Zucker 2009; JAMA Psychiatry 2025) | DOCUMENTED (vendor-cited literature) | https://biochord.health |
| Not a medical device; no therapeutic claims | DOCUMENTED | https://biochord.health |
| Quality-check stage implies artifact rejection before HRV | INFERRED | https://biochord.health |
| Control-core and audio-mapping internals | UNVERIFIED (proprietary/patent-pending) | — |
| Actual sound character; any public audio demo | UNVERIFIED | — |
| Drop-out/artifact/error-state behavior; partner names; product efficacy | UNVERIFIED | — |

## Missing evidence and inaccessible functionality

- **Demo-gated:** the engine itself is only experienceable via a requested partner demo (partners@biochord.health). No public audio sample, video of a live session, or downloadable showcase app was found. All runtime behavior is DOCUMENTED-from-vendor, not OBSERVED.
- **No public developer docs:** API beyond `start()/stop()/reset()`, language bindings, platform targets, package format, and license terms are not published; the SDK itself was not obtainable.
- **Proprietary/unknown:** Layered Control Core algorithms, resonance-frequency estimation, audio mapping functions, synthesizer design, quality-check criteria, and window parameters are patent-pending or unpublished and were deliberately not speculated about.
- **Third-party coverage:** no independent press, reviews, or customer reports of BioChord (biochord.health) were found — consistent with a company founded in 2026 that licenses rather than sells to consumers. The Devpost "BioChord" is a different, unrelated project of the same name.

## Relevance to CIRCLE

Patterns worth adopting:

- **Adaptive audio engine** — the clearest takeaway for CIRCLE. BioChord's public chain (IBI in → quality gate → HRV → control layer → parameter mapping → synth → listener, in a closed loop under a latency budget) is a well-architected template for CIRCLE's audio feedback path. CIRCLE's browser workbench can implement the same stages with Web Audio: simulated PPG → IBI extraction → sliding-window HRV → control state → mapped synth parameters.
- **Latency and update-rate budgets as design contracts** — publishing explicit targets (≤ 250 ms end-to-end, ≥ 1 Hz HRV, ≥ 5 Hz phase) and instrumenting against them is a discipline CIRCLE should copy for its closed-loop controller; BioChord states the numbers but (publicly) proves nothing — CIRCLE can measure and export them per session.
- **Hardware-independent interface design** — BioChord's "only input is a beat-to-beat interval time-series" contract is exactly the decoupling CIRCLE already benefits from with simulated streams. The pattern generalizes: define the physiological input as an abstract interval/sample stream, and any real sensor can later replace the simulator without touching the control or mapping layers.
- **Minimal, stable SDK surface** — `start()/stop()/reset()` with stateless init shows how a closed-loop engine can be embeddable. CIRCLE's controller could expose an equally small surface to the workbench UI.
- **Session designer / evidence explorer** — BioChord offers neither publicly (partners own app UX); this is whitespace. CIRCLE's session designer (protocol, duration, mapping parameters, active-vs-sham arm) plus evidence explorer over exported bundles would exceed what BioChord's partners' users get, at least publicly.

What CIRCLE could do better:

- **Transparency and reproducibility** — BioChord's core is patent-pending and closed; its figures are unmeasured claims. CIRCLE can publish the exact chain, parameters, and versions, and make every audio-feedback session replayable and auditable independently — the evidence export can include the IBI stream, quality-gate decisions, control state, and the audio-parameter trajectory, so the mapping is verifiable end to end.
- **Quality gates with visible error states** — BioChord names a "quality check" but documents no failure behavior. CIRCLE's explicit signal-quality gates (and deliberate artifact/dropout injection via the simulator) turn the weakest documented part of BioChord's story into a tested feature.
- **Self-serve demonstration** — BioChord requires a sales demo; CIRCLE, running on simulated streams in a browser, can demonstrate the full chain to anyone with no hardware at all.

## Suggested original implementation ideas for CIRCLE

1. **Web-Audio biofeedback chain mirroring the BioChord template:** simulated PPG → IBI extraction with outlier rejection → sliding-window HRV (≥ 1 Hz) → RSA phase estimate → a simple phase-locked control state nudging a paced-breathing target (~0.1 Hz, user-adjustable) → synthesis parameters (timbre/density/space as filter cutoff, event density, reverb wetness) in a low-latency Web Audio graph. Budget and instrument end-to-end latency; record it in the evidence bundle.
2. **Interval-stream abstraction layer:** define the workbench's physiological input as a versioned "interval/event stream" interface (matching BioChord's hardware-independent contract) so the simulator, a file replay, or a future BLE sensor are interchangeable behind one interface, with per-source quality metadata.
3. **Quality-gated audio:** silence or musically degrade the adaptive layer when the quality gate fails (dropouts, ectopic intervals, flat signal) and log every gate decision into the evidence export — making error states audible *and* auditable.
4. **Parameter-trajectory evidence:** log the control state and mapped audio parameters at control rate alongside the physiological streams, so an independent replay audit can verify that what the listener heard was a deterministic function of the (recorded) input and protocol — something neither studied product publicly offers.
5. **Active-vs-sham audio arm:** because BioChord's efficacy rests on borrowed mechanism literature, CIRCLE can run genuine comparisons: the same generative audio engine with physiology-driven mapping (active) vs. pre-rendered or open-loop mapping (sham), with the session designer randomizing arms and the evidence explorer summarizing outcomes per arm.
