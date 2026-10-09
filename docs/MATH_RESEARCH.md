# Mathematics intake: CIRCLE

**Research design only, not an implemented mathematics algorithm or a new experimental result.**

[OpenAI's math collection](https://github.com/openai/math) publishes mathematical manuscripts and some Lean proof artifacts. Its results have different review/formalization states. The collection is not a package to install and **does not automatically validate this project's software**.

R.A.I.N. Lab in [Lop Nur Twin](https://github.com/topherchris420/lop-nur-twin) is the canonical location for a **read-only, pinned index** of the catalog. Use the [portfolio math scout](https://github.com/topherchris420/lop-nur-twin/blob/main/docs/MATH_PORTFOLIO.md) to surface candidate references without copying papers or adding authority to this runtime. At the time of this review, the upstream catalog was inspected at [`fd4aeeb2ee4f`](https://github.com/openai/math/tree/fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb); R.A.I.N.'s actual index can pin a different commit, which its report must identify.

## Proposed research question

**Can a recorded error envelope survive dropped, delayed and reordered synthetic sensor packets?**

Search phrase: `stochastic noise bounds estimation recovery`

From a checkout of `topherchris420/lop-nur-twin`:

```sh
npm run rain:math:verify
npm run rain:math:portfolio -- --project circle --json
```

The output ranks lexical candidates. A match is **not** a theorem-to-application mapping; the matching phrases may be unrelated to the mechanism here. The tool does not compile Lean.

## Bridge assumptions to check

1. A measurement timestamp has a declared clock mapping and uncertainty.
2. The decision audit rejects any sample acquired after the input cutoff.
3. Simulation observations cannot be upgraded to real sensor measurements.

## Existing baseline

`python tools/run_physiology_twin.py --output outputs/physiology --audit` followed by `python tools/audit_physiology_run.py outputs/physiology`

## Next falsifiable experiment

Preregister a range of packet-loss and clock-drift perturbations on fresh synthetic seeds; compare bounded timestamp error and audit refusal rates on matched cases.

**Negative control:** Drop a clock anchor, reorder two synthetic packets or forge a later sample into an earlier decision. The independent auditor must detect unsupported lineage or insufficient evidence.

**Deliverable:** Inputs and seeds, cutoff and timestamp error distributions, audit verdicts, a negative-control trace and the scope of the simulator.

## Current scientific boundary

A theorem about ideal stochastic estimators does not establish sensor hardware performance, safety or clinical usefulness. CIRCLE is still an experimental hardware design, with no built boards or human experiments.

This document changes no controller or game logic and establishes no experimental result. Before implementation, review source assumptions, define acceptance/failure thresholds, then run the comparator with a fixed protocol and keep failures. A formalized mathematical statement may support a **narrow mathematical lemma**, never an unrelated physical, model-skill or human claim.

**Current status:** `PROPOSED / NOT TESTED`.

[Inspect the upstream mathematics catalog](https://github.com/openai/math/blob/fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb/CONTENTS.md) · [Shared R.A.I.N. protocol](https://github.com/topherchris420/lop-nur-twin/blob/main/docs/MATH_PORTFOLIO.md)
