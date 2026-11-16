# Contributing to CIRCLE

Thank you for looking closely. CIRCLE is a research instrument, so a useful contribution makes a concrete question answerable. It also leaves behind evidence that someone else can check.

> **ENGINEERING REVIEW ONLY.** Nothing here is approved for fabrication or human connection. Contributions must not weaken that boundary or the labels that mark simulated results as simulated.

## Ways to help

- **Try the [offline demo](https://topherchris420.github.io/circle/) or the local workbench, and tell us where you got stuck.** First-visit friction is a real bug. Use the *Something doesn't work* issue form.
- **Improve an estimator.** Compare it on fresh seeds and keep the cases where it fails.
- **Connect consent to an application path.** Define the restricted mutations, keep durable UUID bindings, and demonstrate replay and crash-recovery behavior.
- **Strengthen acquisition.** Meet the stream and timing contracts, then exercise loss, delay, refusals, and replay. A Cyton owner can contribute an internal-signal phantom session without collecting personal biosignals.
- **Advance hardware or firmware.** Work through the [review gates](hardware/review-gates.json), the timestamping requirements, and the known-input validation plans.
- **Challenge a research hypothesis.** Define the comparison and a failure condition before you run it, and keep the null result. Use the *Propose an experiment* issue form.

If you are unsure whether an idea fits, open an issue before writing code.

## Set up

You need **Python 3.11+** and Git.

```bash
git clone https://github.com/topherchris420/circle.git
cd circle
python -m pip install -r requirements.txt
```

Two optional tools unlock more of the test suite. Without them, those tests are skipped rather than failed:

- **Node.js** runs the audio-scheduling harness in [`tests/js/`](tests/js).
- **A Chromium-family browser** runs the offline demo's browser test.

## Run the checks

```bash
# Unit, property, and contract suite (about six minutes on a laptop)
python -m unittest discover -s tests

# One module while you iterate
python -m unittest tests.test_resonance_assets

# Software, simulation, and deterministic-artifact verification
python tools/verify_release.py --software-only
```

[CI](.github/workflows/ci.yml) runs the suite on Python 3.11 and 3.12. It also runs the contract checkers in [`tools/`](tools), the physiology twin with its sham arm and scenario suite, and the acquisition self-tests. It then **regenerates diagrams and schematic packages and fails if anything differs from the committed files**. If you change a generator, regenerate its outputs and commit them in the same pull request.

## Where things live

| You want to change… | Edit | Then |
| --- | --- | --- |
| The Resonance Workbench interface | [`models/workbench_assets/resonance/`](models/workbench_assets/resonance) | Run `python tools/run_workbench.py` and check `/resonance` |
| The guided (classic) workbench | [`models/workbench_assets/`](models/workbench_assets) | Run `python tools/run_workbench.py` and check `/` |
| The hosted offline demo | [`tools/build_demo.py`](tools/build_demo.py), not `demo/` | Run `python tools/build_demo.py` and serve `demo/` with `python -m http.server -d demo` |
| Signal processing or the controller | [`models/physiology/`](models/physiology) | Rerun the twin and scenario suite on fresh seeds |
| Acquisition sources | [`models/acquisition/`](models/acquisition), [`models/openbci_cyton/`](models/openbci_cyton) | Run `python tools/run_acquisition_demo.py` |
| Record formats | [`contracts/`](contracts), [`models/session_records.py`](models/session_records.py) | Run `python tools/check_record_schema.py` |
| Documentation | [`docs/`](docs), [`README.md`](README.md) | Keep UTF-8, LF line endings, and the `ENGINEERING REVIEW ONLY` notices |

`demo/` is a build output. CI rebuilds it from `tools/build_demo.py` on every push to `main`, so hand edits to `demo/` are overwritten.

## House rules for evidence

These rules keep CIRCLE's results trustworthy, so reviews hold to them:

1. **State the failure condition first.** A proposal says what result would count against it before anything runs.
2. **Keep the failures.** Failing seeds, divergent replays, and null results stay in the record. Earlier controller rounds remain in [`docs/closed-loop-evidence.md`](docs/closed-loop-evidence.md) for this reason.
3. **Evaluate on fresh seeds.** Tuning seeds and confirmatory seeds are different seeds.
4. **Report what you ran.** Simulation issues include the command, scenario, seed, and replay verdict (`REPLAY_MATCH`, `REPLAY_DIVERGENCE`, …).
5. **Claim no more than the evidence shows.** Software agreement with the twin is not sensor accuracy, and sensor accuracy is not a human outcome. Label simulated results as simulated.
6. **Respect the review gates.** Changes must not imply that fabrication, human connection, or a therapeutic effect has been authorized or shown.

## Pull requests

- Keep each pull request to one question or change, and describe the evidence it produces or affects.
- Add or update tests with behavior changes. A user-interface fix should come with a check that would have caught the bug.
- The [pull request template](.github/pull_request_template.md) lists the checks reviewers look for.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE). The license grants no approval to fabricate the hardware or connect it to a person.
