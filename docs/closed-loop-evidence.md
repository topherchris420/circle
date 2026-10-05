# Closed-Loop Evidence

> **ENGINEERING REVIEW ONLY** — Everything described here runs against the simulated physiology twin. It shows that the software's evidence logic behaves as specified under known truth. It is not evidence about hardware, physiology, or any effect on people.

Most sensing systems stop at measurement. CIRCLE is built around what happens after it:

```
sense → preserve → infer → decide → intervene → observe → verify
```

A closed-loop system should not merely act. It should preserve enough to reconstruct, later and independently:

1. what the system knew, and when it knew it;
2. which algorithm and parameters ran;
3. what it decided, and why;
4. what command it sent;
5. what independent physical evidence followed;
6. what alternative interpretations remain.

The design test is short: **measure what happened, preserve what was known, record why the system acted, verify what actually occurred.** The controller does not get to grade its own homework.

## Five things that are not the same thing

| Stage | Question it answers | Recorded as | What it is *not* |
|---|---|---|---|
| **Decision** | Why did the system act? | `MODEL_RESULT`, `MODEL_INFERRED`, with `decision_id`, `decision_time_us`, `input_cutoff_us`, gate results, exact source ranges | Not a command |
| **Command** | What did firmware issue? | `EVENT` `HAPTIC_COMMAND` | Not evidence a motor moved |
| **Physical actuation** | Did current flow and did the actuator move? | `EVENT` `HAPTIC_ELECTRICAL_ONSET` (TLV3201 edge), then `EVENT` `HAPTIC_PHYSICAL_OBSERVATION`, `DERIVED` from IMU samples | Not evidence it reached physiology |
| **Observed effect** | Did signals change afterwards? | Later windows and evaluations | Not attributable to the intervention by timing alone |
| **Interpretation** | Did the intervention cause the change? | Only through matched controls (sham arm, randomized timing, counterfactual) | Never asserted by a session record |

Each `INTERVENTION` record carries a per-cue `execution_chain`. A cue earns `COMMAND_ONLY`, `ELECTRICAL_ONSET_OBSERVED`, or `PHYSICALLY_OBSERVED` only from the evidence ids it cites; the session contract rejects a stage its evidence does not earn, and the auditor recomputes every stage from the events. Every intervention record also carries `EFFECT:NOT_ASSERTED_WITHOUT_MATCHED_CONTROL`.

The sham arm is a negative control for the physical-observation detector: sham commands are examined with the identical IMU detector, and any detection there fails the scorecard.

## Every decision obeys time

Each raw sample has two device times:

- `device_time_us`: when the sample was taken (for FIFO streams, a reconstructed instant);
- `available_us`: when firmware held it in memory (DRDY read completion, or the FIFO batch read).

After a FIFO stall, samples taken at 185.0 s may not exist in memory until 185.4 s. A decision at device time *T* may use a sample only if `available_us ≤ T` and `device_time_us ≤ input_cutoff_us`. `RawSession.until(T)` filters by availability, and the online loop hands the controller exactly that.

The auditor's `temporal_lawfulness` check applies to **every** record that declares `decision_time_us`, whatever produced it: deterministic logic, a statistical model, or an AI model. No intelligence layer gets a time machine.

Adversarial tests (`tests/test_closed_loop_evidence.py`) show that:

- a controller handed every future sample decides exactly as the lawful replay does;
- FIFO samples are invisible until read, including across the longest observable stall;
- a protocol marker logged after a decision cannot influence it;
- a clock-mapping correction does not change decisions (decisions use device time);
- a restart with restored state resumes identically, and a restart that loses state is detectable as a divergence;
- a consistently forged cutoff (CRCs resealed, ledger rebuilt, manifest rehashed) is caught as `TIMING_VIOLATION`;
- a source range silently spanning a declared gap is caught by lineage checks.

### Every source faces the same contract

The loop that runs the twin is the loop for every source (`models/physiology/loop.py`). Before the first evaluation a source must supply every stream the pipeline reads; one that cannot (the Muse Gadget SDK, which carries no physiological signal) is refused with its reasons, and the refusal is recorded as a session. A live device's records reach the controller through the ingestion boundary (`models/acquisition`), where malformed pieces are refused, losses become exact `GAP`s, silence becomes recorded link states, and availability is stamped at host receipt, so that a host-side decision and its replay see the same record. A session delivered over a corrupting, stalling, and dropping link still audits as `REPLAY_MATCH`. See [hardware sources](hardware-sources.md).

## Replay has an explicit status

`tools/audit_physiology_run.py` never reconciles silently. It reports exactly one status:

| Status | Meaning |
|---|---|
| `REPLAY_MATCH` | Every derived record and every command re-derived bit-for-bit from the raw bundle and the device events |
| `REPLAY_DIVERGENCE` | The controller's replay disagrees with its recorded baseline, evaluations, or commands; the first divergent record and fields are reported |
| `TIMING_VIOLATION` | A decision cites evidence taken after its cutoff or unavailable at its decision time |
| `VERSION_MISMATCH` | The recorded analysis code differs from the code performing the audit |
| `EVIDENCE_INTEGRITY_FAILURE` | Hashes, CRCs, contract, lineage, execution chains, or a re-derived record, analysis, or ledger do not hold |
| `MISSING_SOURCE` | An artifact replay needs is absent |
| `INSUFFICIENT_EVIDENCE` | No usable controller configuration, no baseline, or no recorded evaluations |

### The auditor rebuilds the whole session

A session record is either a **device record** (header, stream descriptors, controller configuration, device events, declared gaps, trailer) or a **derived record** (clock mapping, physiology windows, controller baseline and evaluations, IMU-observed physical onsets, interventions). Every derived record is a pure function of the device records and the raw bundle. The auditor therefore rebuilds the entire `session.ndjson` from those inputs alone and compares record by record. Controller records are judged by replay (`REPLAY_DIVERGENCE`); every other derived record must match exactly (`EVIDENCE_INTEGRITY_FAILURE` otherwise), and the first mismatching record and fields are named.

Before this, a consistent forgery of a derived record that the controller never read, with its CRC resealed, the ledger rebuilt, and the manifest rehashed, passed the audit as `REPLAY_MATCH`. Tests now show that each of these is caught, and names the record it was found in:

- a physiology window carrying a heart rate nobody measured;
- a physical observation with a physically impossible command-to-vibration latency;
- an execution chain downgraded to `ELECTRICAL_ONSET_OBSERVED` for one cue while the intervention record still claims every cue was physically observed;
- a clock mapping shifted by 500 ppm.

Hashes and CRC-32C detect accidental or inconsistent change. They are not authentication.

## Quality gates have teeth

Holding is a decision. Before acting, the controller requires:

| Gate | Fails when |
|---|---|
| `DATA_STALE` | Any stream's newest usable sample is older than 0.5 s at the cutoff |
| `SATURATION` | Any EDA or PPG code sits at an ADC rail in the window |
| `EDA_CONTACT_LOST` | Fewer than 90 % of the samples used for tonic level read ≥ 0.3 µS |
| `PPG_COUPLING_CHANGED` | Received light in the last 3 s differs from baseline by more than 2× |
| `BEAT_COVERAGE_LOW` | Valid beats cover less than 70 % of the heart-rate window |
| `MOTION_EXCESSIVE` | IMU motion covers more than 20 % of the heart-rate window |
| `MOTION_AT_CUTOFF` | Any motion in the final 3 s before the cutoff: the newest evidence is corrupted |
| `FEATURE_MISSING` | A component of the index cannot be computed |

To trigger, both physiological systems must agree independently: cardiovascular (heart-rate z ≥ 2) **and** electrodermal (tonic conductance z ≥ 2). One system alone produces `HOLD_SIGNALS_DISAGREE`. A hold breaks the trigger streak, so "consecutive" means adjacent, adequately observed evaluations. During guidance, three consecutive gate failures stop the program (`STOP_QUALITY_LOST`): a loop that cannot observe its effect is no longer closed.

### Sustained means observed

Starting guidance claims that arousal has been elevated over the evidence window the index depends on. The gates above judge the newest evidence (the cutoff, the 20 s heart-rate window, the 10 s tonic window). They do not say whether the controller could see the state while it was forming. After a blind spell, the first two adequate evaluations cannot tell a sustained state from the lagging tail of one that resolved unseen: tonic skin conductance recovers with a ~25 s time constant, so for a while it reports a state that is already gone, and a marginal heart-rate excess completes a two-system "agreement" by chance.

Every evaluation therefore records `clean_since_s`: the time from the latest impaired instant inside the full 40 s feature window (a motion episode, electrode contact below the floor, received light outside the baseline band, a saturated code, or a stale gap in any stream) to the input cutoff, equal to the window length when nothing in it was impaired. While the index is above the trigger but the window has not been clean for its full length, the controller records `HOLD_EVIDENCE_GAP` and the streak resets. Continuing a program needs only that the loop can still observe (the gates); starting one needs the whole window.

This is the same definition the scenario judge uses for an *observable* state (no impairment within the feature window ending at the cutoff), so the controller now acts exactly when the judge would require it to, and never earlier. The clean session is unchanged by the rule: its stressor-phase motion ends more than 40 s before guidance is armed.

The arousal index remains an engineering trigger. It is not a measure of stress, emotion, or any mental state.

## The twin tries to break the loop

`python tools/run_physiology_twin.py --scenarios` runs eight scenario families and judges the loop against hidden truth, not against its own gates. The suite is two-sided: seven scenarios try to make the loop act when it should not; one tries to make it fail to act when it should. A controller that passed only by holding would fail there.

| Scenario | System assumption under test |
|---|---|
| `clean` | The loop acts on a warranted, well-observed state and releases on its own |
| `motion_heavy` | No decision rests on motion-corrupted PPG, and none on the lagging tail of a state that resolved during a blind spell |
| `poor_contact` | A lifted electrode and collapsed optical coupling are recognized as faults, not calm physiology |
| `timing_fault` | Timestamps and exact loss accounting survive extreme oscillator errors and the longest observable FIFO stall |
| `sensor_loss` | A vanished channel yields stale-data holds and an exact declared gap |
| `feedback_artifact` | The actuator's own artifact neither breaks execution evidence nor fools the loop |
| `ambiguous` | A heart-rate rise with no electrodermal change (a different pathway) cannot trigger an intervention |
| `interrupted` | A warranted, sustained state (guidance armed during the stressor) obscured by 10 s of motion as it builds is still acted on in time once a full evidence window is clean: caution must not become timidity |

System checks: replay match; temporal lawfulness; exact gaps; complete execution chains; no start or release on truth-impaired evidence; no guidance started at low latent arousal; timely response once a warranted state is observable; every injected impairment flagged; the expected abstention reasons present.

### How the held-out evaluation went, including what it found

Seed 7 was used during development. Held-out seeds then exposed four controller defects, each fixed on principle and each followed by evaluation on fresh seeds. Once a held-out set has been examined to design a fix, it is no longer held out; the next round uses seeds never seen.

1. **Seeds 100–109** (69/70): two chance spontaneous SCRs against a zero-SCR baseline counted as "agreement". Fix: agreement is judged per physiological system.
2. **Seeds 200–219** (128/140): a quality hold did not reset the trigger streak, so one high index before a long motion episode and one after it counted as "consecutive". Also, phasic SCR counts in a 30 s window crossed a Poisson threshold by chance across many evaluations. Fixes: a hold breaks the streak; electrodermal agreement rests on tonic level.
3. **Seeds 500–529, controller 1.1.0** (199/210): six scenarios passed 30/30. In `motion_heavy`, 11 of 30 seeds started guidance at 305 s, after 45 s of corrupted evidence, when latent arousal had already fallen below the "unwarranted" line (0.35; the eleven runs read 0.22–0.33). The ledgers show the mechanism exactly: the index had fallen monotonically from about 8 to 2.45 across the blind spell; tonic skin conductance, recovering with a ~25 s time constant, still reported the state from before the gap (z 2.3–2.6 while the true level warranted about 1); and a marginal heart-rate excess (z 2.6–2.8) completed the two-system agreement by chance, which is why the other 19 seeds, differing only in noise around the 2.0 threshold, did not trigger. The controller acted lawfully on its evidence, but 10 s of adequate evidence after 55 s of blindness is not a sustained state. Fix: [sustained means observed](#sustained-means-observed). Re-run as a diagnostic after the fix, `motion_heavy` passes 30/30 on these seeds, and the retained decisions at 300–310 s are now `HOLD_EVIDENCE_GAP`.
4. **Confirmatory: seeds 600–629, never examined, controller 1.2.0** — **240/240 runs pass** across all eight scenarios, `interrupted` included ([`scenario-benchmark.json`](scenario-benchmark.json)). In every `interrupted` run the loop held with `HOLD_EVIDENCE_GAP` while the window was still partly impaired and started guidance at 175 s, inside the judge's allowance. A clean round is not a proof: it says that on 240 fresh sessions the loop neither acted on a resolved state nor failed to act on a sustained one, under the twin's disturbance models.

## Session identity: the passport and the ledger

Every run exports:

- `passport.txt`: mode, arm, scenario, hardware model, pipeline and controller versions, seed, streams, declared gaps, evaluations (decisions, gate failures, holds), interventions and how many cues were physically observed, human data, hardware driven, replay status.
- `closed_loop_ledger.json`: every evaluation with formula components, input cutoff, decision time, gate results, and exact source ranges; every decision with a deterministic "why"; every intervention's execution chain with latencies. It is a pure function of `session.ndjson`, and the auditor rebuilds it exactly.

The session report renders both. Clicking a ledger row answers *why did the system act (or hold) here*, down to the samples; the execution table answers *did the system observe that it happened*.

## Lineage, honestly

Controller evaluation records are flagged `LINEAGE:COMPLETE_CAUSAL_INPUT`: each is a pure function of exactly its cited ranges, the recorded baseline record, markers logged before it, and the controller's earlier state. Offline 10 s physiology windows are flagged `OFFLINE_NONCAUSAL` and `LINEAGE:WINDOW_ATTRIBUTION`: their ranges name the samples inside the window, but zero-phase filters also read neighbouring context.

## AI may propose; CIRCLE executes the contract

Models are expected to get much better at multimodal signal reasoning. They belong above the record, never underneath it. More capable models should gain analytical resolution, not authority.

`contracts/experiment-protocol.schema.json`, `models/protocols.py`, and `tools/run_protocol.py` enforce five separate steps:

1. **Proposal** (a person or an AI model, which must name its model version): hypothesis, arms, intervention, decision rule, quality gates, outcomes from a fixed menu, seeds, stopping rule, analysis plan.
2. **Deterministic validation**: target must be `SIMULATION`; a matched sham arm is mandatory; gates may only be tightened; the causality margin cannot be overridden; development seeds cannot be confirmatory; more than one tested outcome requires Holm correction.
3. **Human authorization** bound to the protocol's canonical SHA-256. One changed byte voids it (`PROTOCOL_CHANGED`).
4. **Execution** against the twin, with every session's replay checked.
5. **Measurement**: paired sign-flip permutation tests, Holm-adjusted, with each outcome's evidence class (`CONTROLLER_DERIVED`, `PIPELINE_DERIVED`, `CONTROLLER_RECORD`, `TWIN_TRUTH`). Safety outcomes report `NO_INCREASE_DETECTED (not a demonstration of equivalence)`.

The example in `experiments/protocols/paced-breathing-arousal.json` compiles the request "test whether paced haptic breathing reduces this arousal proxy without increasing motion artifacts". Its result is supported **in simulation**, which validates the analytical machinery under the twin's assumed response model and nothing else.

CIRCLE's command set for a Muse gadget (`models/muse_gadget/commands.py`) applies this rule to a real AI channel. Through it, Meta's Muse assistant may read the capability registry and submit a protocol for validation, which must declare itself `AI_MODEL`; the reply states that nothing was authorized or executed. There is no command to authorize, execute, actuate, read session data, or write files. The command set is wire-compatible with the Muse Gadget SDK's `LinkSession` (tested against the SDK's own code); running it from a paired gadget is not implemented.

An AI system may summarize sessions, find intervals, compare arms, propose thresholds, describe contradictions, and suggest controls. It may not invent readings, interpolate gaps into evidence, change timestamps, rewrite provenance, mark a hypothesis as measured, bypass quality gates, or authorize anything. A future typed critic (for example, a controller critic reading the ledger's evidence for one decision) would return typed judgments, would keep model confidence separate from physiological confidence, and could never override a failed deterministic check.

## What this does not show

- All signals are simulated. Agreement with the twin tests software logic, not physiology or hardware.
- The paced-breathing response is assumed by the twin. The counterfactual shows the evidence chain can resolve an effect, not that one exists.
- Scenario disturbances are models; real failure modes will differ.
- No firmware exists. The availability, FIFO, and timing behavior the twin encodes is a specification firmware must meet.
