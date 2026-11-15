# Sychedelic — Evidence report

Sychedelic is a consumer neurotechnology product from Pankhtech India Pvt. Ltd. (Gurugram, India; founded by Ria Rustagi and Bhavya Madan, previously of Neuphony, India's first consumer EEG neurofeedback wearable). It is a pair of over-ear headphones with three integrated capabilities: (1) a 100 Hz PPG sensor at the temporal artery that estimates heart rate and HRV to classify cognitive/stress state; (2) an adaptive "audio recommendation engine" of soundscape entrainment (including alpha binaural beats) intended to shift the user toward a target state; and (3) a tDCS neurostimulation module (2.0 mA, 20 min, AF3/AF4 over the dlPFC) that is *gated* by the physiological state reading — stimulation only unlocks when the stress model judges the user ready. As of late 2026 the product is in pre-order/Kickstarter phase (Founding Edition $549, ships December 2026), CDSCO-approved as Class B in India, with a companion app on Google Play (100+ downloads, updated Sep 2026) and a $3.5M seed round closed in May 2026.

## Sources consulted

- https://sychedelic.com — homepage: product concept ("reads stress → music → tDCS focus"), regulatory claims (CDSCO Class B, IEC 60601-1-2, ISO 10993), pricing and Dec 2026 ship date.
- https://sychedelic.com/how-it-works/ — the richest UX source: setup ritual (spray sponges, place band, impedance check), the Detect/Reset/Ready feedback-state machine, app screenshot walkthrough, session arc, safety envelope, FAQ (incl. data export roadmap).
- https://sychedelic.com/product — spec table, session timeline (0/3/10/30/120 min), app screens (baseline read, entrainment, boost active, insights), in-the-box contents.
- https://sychedelic.com/reviews — 600+ sessions beta claims, 89% reported measurable shift, categorized testimonials.
- https://play.google.com/store/apps/details?id=com.sychedelic.app — app listing: companion app description, data-safety declarations, what's-new notes (accessibility improvements to onboarding), update date.
- https://sychedelic.com/blogs/sychedelic-reviews-6-month-beta-testers (via websearch) — beta FAQ: closed-loop vs open-loop differentiation, session cadence.
- https://thegadgetflow.com/blog/sychedelic-neuroacoustic-headphones-review/ (via websearch) — third-party review of the closed-loop gating concept.
- https://www.gizmocrowd.com/post/sychedelic-headphones-review (via websearch) — beta stats (80 users, 2,700+ sessions, HRV gains 11–16 ms), three modes (Tune/Boost/sleep), founders' background.
- https://www.founderland.ai/articles/sychedelic-raises-35m-for-tdcs-enabled-wellness-headphones-mpf9q5gm (via websearch) — funding, team, skepticism notes (registry confirmation of CDSCO claim not readily found).
- https://thecodersblog.com/sychedelics-3.5m-headache-... (via websearch) — critical technical analysis: PPG artifact susceptibility, algorithm opacity, closed-loop latency questions.
- https://www.youtube.com/watch?v=oYETYUwHIpE (via websearch) — official co-founder app walkthrough video transcript fragments (device settings, boost setup).
- https://www.reddit.com/r/Neurofeedback/... (via websearch) — founder engagement citing clinical literature and unfavorable results.

## Findings

### Session onboarding / setup flow

- **OBSERVED** (in app screenshots on /how-it-works and /product): a guided "Setting up for Boost" ritual with side-profile illustrations: (1) spray sponges 20–25 times with included saline, (2) pivot the centre arm forward and place the band across the hairline over the dlPFC, (3) wait for the impedance check. Screens show a disabled "Checking conductivity" button and an enabled "Let's Go" button once contact is good.
- **OBSERVED** (Play Store "What's new"): the latest app update shipped "Accessibility improvements for onboarding screen" — evidence that onboarding is a maintained, screen-by-screen guided flow.
- **DOCUMENTED** (FAQ): headband adjustability, rare-earth magnets aligning electrodes to AF3/AF4, impedance reading before every session as final placement confirmation.
- **INFERRED**: the walkthrough video ("put your hair behind your ears because you want the PPG sensor to touch this part of your head"; telescopic arms) suggests onboarding also covers PPG contact positioning, not just the tDCS electrodes.

### Physiological-state visualization

- **OBSERVED** (app screenshots): Home screen shows live heart rate in BPM (e.g., 102 BPM), an emotional-state label ("Anxious", "Brain Fog"), and a slider/spectrum from Drowsy to Focused. Insights screen shows a timeline graph tracking mood change from anxious to focused, heart-rate data 110–76 bpm, and a highlighted boost session.
- **DOCUMENTED**: PPG samples at 100 Hz, classifying state in real time "from Drowsy through Brain Fog to Focused"; "Anxious" zone = sympathetic overdrive with stimulation suppressed.
- **INFERRED**: the Drowsy→Focused slider with discrete labeled zones appears to be the primary state visualization, with a numeric mood/coherence scale; exact visual treatment beyond screenshots is unconfirmed.
- **UNVERIFIED**: how the underlying HRV features map to the five states; the classification algorithm's accuracy, training data, or validation metrics are not published (noted by thecodersblog.com as a black box).

### Audio selection / adaptive audio engine

- **OBSERVED** (app screenshots): a "Soundscapes" tab; Deep Work soundscape playing "Spiti Valley Monastery"; soundscape thumbnails (scenic landscapes); music player card on the home screen.
- **DOCUMENTED** (/product): "Audio Recommendation Engine — Adaptive · Coherence-matched. Not a playlist — a real-time protocol. The frequency shifts as your coherence shifts, matching your zone on every session." Soundscape selected for the current zone and goal.
- **DOCUMENTED** (/how-it-works): entrainment phase uses alpha binaural beats (10 Hz) first, then lower frequencies introduced gradually in short bursts "once your PPG confirms tolerance," with continuous monitoring.
- **OBSERVED** (walkthrough video transcript): audio settings screen with EQ, bass personalization (bass/acoustic/electronic), ANC modes, volume control; some screens are plain music playback rather than therapy.
- **INFERRED**: audio behaves as the *first-stage actuator* of the closed loop — selected by state, modulated in frequency/intensity over the session, and used to earn the unlock of tDCS. Not independently verified whether frequency adaptation is per-track DSP or pre-composed branches.

### Device connection and quality checks

- **OBSERVED** (app screenshots + spec table): explicit impedance gate — "10 kΩ+ — Locked; 0–10 kΩ — Session begins"; a "Checking conductivity" state with disabled CTA; spec lists "Impedance <10 kΩ (gated)". Connection is Bluetooth (+ USB-C).
- **DOCUMENTED** (/how-it-works, hardware safety): live impedance monitoring during the session; electrode drying mid-session triggers a controlled current ramp-down (not a spike or cut). Constant-current topology; hardware 4 mA ceiling; hardware-enforced 20-minute auto-shutdown independent of the app.
- **DOCUMENTED** (/product): "the session only opens when the reading is clean" — PPG signal-quality gating before the session commits.
- **INFERRED**: baseline read phase (0 min) is both a state classification and an implicit signal-quality check; the UI wording "Assessed, not committed" supports this.

### Feedback transitions (closed-loop state machine)

- **OBSERVED** (three app screenshots on /how-it-works, labeled 01·Detect / 02·Reset / 03·Ready): "Boost locked" (Anxious, 102 BPM) → "Time to break" reminder with soundscape active → "Boost enabled" (Brain Fog, 95 BPM). The UI visibly moves from a locked to an available boost state.
- **DOCUMENTED**: three-phase model — Detect (stimulation off in Anxious zone), Reset (soundscape matched to zone shifts state), Ready ("when the stress model registers sufficient improvement, the boost unlocks on its own — no timer to set").
- **DOCUMENTED** (/product session timeline): 0 min baseline read → 3 min entrainment → 10 min boost active → 30 min peak begins → 120 min peak window. Session-active screen shows progress ring, live HR (80 BPM average), stimulation intensity control at 100%, and options to adjust or end.
- **INFERRED**: the boost gate is a threshold on an internal "stress model" score; hysteresis/tolerance parameters are not published.
- **UNVERIFIED**: closed-loop latency figures (sensor → inference → actuator) at any stage; flagged as missing by third-party commentary.

### Loading, error, and degraded states

- **OBSERVED**: "Checking conductivity" disabled-button state (loading/gate check); "Boost locked" state with explanatory copy and a nudging micro-intervention ("Time to break — take a 5-minute pause with music") instead of a bare error.
- **DOCUMENTED**: mid-session electrode drying → controlled current ramp-down; hardware auto-shutdown at 20 min regardless of software state.
- **INFERRED**: guidance "above 10 kΩ — re-spray and reseat" implies a remediation loop back to the setup step on failed impedance check; exact UI for repeated failures unobserved.
- **UNVERIFIED**: Bluetooth disconnection handling, app-side error toasts, or session-resume behavior — not shown in any accessible material.

### Session arc and progress

- **DOCUMENTED**: 25-session protocol: sessions 1–5 calibration (1→2 mA ramp), 6–15 first signal (~session 10 off-day differences), 16–25 consolidation (session 20 clinical benchmark), 26+ maintenance with alternating active/rest weeks. 3–4 sessions per week.
- **DOCUMENTED** (FAQ): session data logged locally in the app from day one; CSV export, Apple Health, and Oura sync on roadmap "shipping Q4 2026" — as of this writing not confirmed shipped.
- **DOCUMENTED** (beta claims via /reviews and press): 600+ sessions, 80–100+ users, 89–92% reported measurable shift, HRV gains 11–16 ms — self-reported company figures, not independently audited.

## Evidence log

| Claim | Classification | Source URL |
|---|---|---|
| Guided setup: spray sponges (20–25 sprays), place band over hairline, impedance check before session | OBSERVED (screenshots) | https://sychedelic.com/how-it-works/ |
| Impedance gate: <10 kΩ to start; >10 kΩ locked, re-spray and reseat | OBSERVED | https://sychedelic.com/how-it-works/ |
| PPG at 100 Hz classifies Drowsy→Brain Fog→Focused→Anxious zones in real time | DOCUMENTED | https://sychedelic.com/how-it-works/ |
| Home screen shows live BPM, state label, Drowsy–Focused slider | OBSERVED (screenshots) | https://sychedelic.com/how-it-works/ , /product |
| Boost locked → soundscape active → boost unlocked state machine | OBSERVED (screenshots) | https://sychedelic.com/how-it-works/ |
| Alpha binaural beats (10 Hz) first, then lower frequencies in short bursts gated by PPG tolerance | DOCUMENTED | https://sychedelic.com/how-it-works/ |
| Audio recommendation engine adapts frequency to "coherence" | DOCUMENTED | https://sychedelic.com/product |
| Soundscapes tab, "Spiti Valley Monastery" Deep Work soundscape, EQ/ANC settings | OBSERVED (screenshots/video) | https://sychedelic.com/product , https://www.youtube.com/watch?v=oYETYUwHIpE |
| 2.0 mA constant current, 20 min hardware-timed session, 4 mA hardware ceiling, AF3/AF4 targets | DOCUMENTED | https://sychedelic.com/product , /how-it-works/ |
| Mid-session electrode drying triggers controlled current ramp-down | DOCUMENTED | https://sychedelic.com/how-it-works/ |
| Session timeline 0/3/10/30/120 min (read → entrain → boost → peak → window) | DOCUMENTED | https://sychedelic.com/product |
| Insights timeline graph: mood anxious→focused, HR 110–76 bpm, boost highlighted | OBSERVED (screenshot) | https://sychedelic.com/product |
| 25-session arc, session-20 clinical benchmark, alternating rest weeks | DOCUMENTED | https://sychedelic.com/how-it-works/ |
| Session-active screen: progress ring, live HR, intensity control, end-session option | OBSERVED (screenshot) | https://sychedelic.com/product |
| Companion app on Android; onboarding accessibility improvements shipped Sep 2026 | OBSERVED | https://play.google.com/store/apps/details?id=com.sychedelic.app |
| Data logged locally; CSV export/Apple Health/Oura on roadmap Q4 2026 | DOCUMENTED | https://sychedelic.com/how-it-works/ (FAQ) |
| Beta: 600+ sessions, 89–92% measurable shift, HRV +11–16 ms | DOCUMENTED (company-claimed) | https://sychedelic.com/reviews , https://www.gizmocrowd.com/post/sychedelic-headphones-review |
| State-classification accuracy/validation metrics, closed-loop latency | UNVERIFIED | https://thecodersblog.com/sychedelics-3.5m-headache-... (critique) |
| CDSCO Class B approval; ISO 60601-1-2 | DOCUMENTED (registry confirmation not independently found) | https://sychedelic.com , https://www.founderland.ai/articles/... |

## Missing evidence and inaccessible functionality

- Live app experience requires Sychedelic hardware and an account; the walkthrough video is the closest public proxy for actual flow behavior. Could not install/use the Android app in this research.
- No public documentation of the state-classification model (architecture, training data, precision/recall per state), the "coherence" metric definition, or the boost-unlock threshold/hysteresis.
- No published closed-loop latency benchmarks; no artifact-rejection performance under realistic movement.
- CSV export, Apple Health and Oura integration are roadmap items — functionality not yet publicly demonstrated.
- Three modes (Tune / Boost / night-time sleep session) are mentioned in third-party coverage but not fully visible on the fetched pages; sleep-mode UX is UNVERIFIED here.
- Beta statistics are self-reported by the company; no independent replication or published study of the device itself.

## Relevance to CIRCLE

- **Adaptive audio engine**: Sychedelic is a strong reference for zone-matched, coherence-driven soundscape selection with graded frequency progression (alpha binaural → lower frequencies in short bursts), and for treating audio as a *first-stage actuator* that earns the unlock of a stronger intervention. CIRCLE's simulated PPG/EDA streams + closed-loop controller can replicate this pattern exactly, and do it better by exposing the gate threshold and the frequency-adaptation logic to the researcher instead of hiding it.
- **Physiological dashboard**: the Home screen pattern — live BPM, a named state label, and a Drowsy→Focused spectrum slider — is a compact, glanceable state visualization. CIRCLE can adopt the labeled-zone-over-continuous-scale idea but should show the underlying features (HRV time-domain values, signal-quality gates) alongside the label for transparency.
- **Session designer**: Sychedelic's phased session arc (read → entrain → stimulate → peak window) with hardware-enforced safety limits is essentially a scripted closed-loop protocol. CIRCLE's session designer could formalize this as configurable phases with explicit gate conditions, ramp profiles, and auto-shutdown — with the protocol definition exportable as part of the evidence bundle.
- **Evidence explorer**: Sychedelic's "we include the papers that say no" evidence brief (null results listed alongside positives) is rhetorically excellent but closed (email-gated PDF). CIRCLE's evidence export / independent replay audit can operationalize the same honesty: every session export carries raw signals, gate decisions, and the exact protocol version so a third party can replay it.
- **Quality gates**: the impedance <10 kΩ gate and "session only opens when the reading is clean" mirror CIRCLE's signal-quality gates; Sychedelic adds a *remediation micro-intervention* (re-spray guidance, "time to break" nudge) rather than a bare failure — worth copying in CIRCLE's gate-failure UX.
- **What CIRCLE can do better**: publish the classifier and thresholds (open-source), expose latency and artifact metrics per stage, make active-vs-sham comparisons first-class (Sychedelic claims a single-blind protocol for its reviews but publishes no data), and avoid unverifiable marketing percentages by exporting raw per-session evidence.

## Suggested original implementation ideas for CIRCLE

1. **Gate-unlock timeline widget**: a session view showing the locked/available state machine as a trackable timeline (like Sychedelic's Insights screen), where each gate transition is an annotated, exportable event with the triggering physiological values — turning "boost unlocked on its own" into an auditable decision.
2. **Remediation-aware quality gates**: when a PPG/EDA/IMU quality gate fails, offer Sychedelic-style physical remediation hints (reseat sensor, pause) plus a simulated re-check, and log the remediation attempt in the session evidence.
3. **Coherence-adaptive soundscape with visible parameters**: an adaptive audio engine where the frequency-progression schedule (alpha → lower bands, burst duration, tolerance gate) is a researcher-editable table, not a black box — and every parameter change is recorded for replay.
4. **Labeled-zone state spectrum**: a Drowsy→Focus-style spectrum with named zones over a continuous score, where hovering a zone reveals the underlying HRV/EDA features and the gate threshold that separates it from its neighbor.
5. **"Includes the nulls" evidence panel**: a study-citation panel in the workbench that deliberately lists disconfirming literature for each intervention type, with links — CIRCLE's version links to full-text public papers rather than an email-gated brief.
6. **Hardware-limit-style safety envelope in simulation**: mirror Sychedelic's hardwired ceiling concept in CIRCLE's controller as a non-bypassable software-independent safety module (max stimulus intensity, max session duration) whose limits are stamped into every exported session file.
7. **Session-arc milestones**: protocol-templates with named phases (read/entrain/stimulate/peak) and per-arc progress indicators (session 10/20 style milestones), making multi-session study designs legible in the workbench UI.
