# CIRCLE 

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This is almost ready for human connection and does not establish medical-device, electrical-safety, EMC, or measurement-performance claims.

This contains the architecture diagrams, safety contracts, validation documents, and KiCad 10 schematics for the CIRCLE Rev A bench validation platform.

The platform combines synchronized physiological sensing, local recording, isolated laboratory synchronization, and evidenced feedback in one reviewable architecture.

## At a glance

| | |
| --- | --- |
| **Purpose** | Architecture, safety-contract, and schematic review |
| **Hardware** | `circle-main` compute/acquisition board and replaceable `circle-ppg` optical board |
| **Electrical model** | Human-connected `BAT_HUMAN` domain separated from `LAB_ISO` by reinforced isolation |
| **Toolchain** | Python 3.11+ and KiCad CLI 10.0.5 |
| **Package status** | Repository checks pass; fabrication and human connection remain blocked |

**Review artifacts:** [system architecture](diagrams/system-architecture.svg) · [main-board schematic](hardware/reports/pdf/circle-main.pdf) · [optical-board schematic](hardware/reports/pdf/circle-ppg.pdf) · [safety analysis](docs/safety-analysis.md) · [review gates](docs/review-gates.md) · [verification summary](hardware/reports/verification-summary.json)

## System overview

- **`circle-main`** combines ESP32-S3 compute, battery and power management, protected electrodermal-activity (EDA) acquisition, IMU capture, microSD storage, isolated synchronization, haptic feedback, and observability.
- **`circle-ppg`** is a keyed, replaceable optical contact board that preserves raw red and infrared measurements.

The capture path is designed around deterministic timestamps and explicit evidence: sensors feed timestamp capture, SRAM and PSRAM absorb bursts, microSD provides asynchronous storage, and telemetry branches only after record assembly.

![CIRCLE Rev A system architecture](diagrams/system-architecture.svg)

## Safety boundary

The design separates the human-connected `BAT_HUMAN` domain from the laboratory `LAB_ISO` domain. USB, debug, and external-expansion attachment force the hardware EDA path off; isolated SYNC is the intended boundary between the two domains. Read the [architecture](docs/architecture.md) and [safety analysis](docs/safety-analysis.md) before reviewing the schematics.

![CIRCLE Rev A safety boundaries](diagrams/safety-boundaries.svg)

## What “verified” means

The checked-in [verification summary](hardware/reports/verification-summary.json) records a successful run of the repository release checks. Those checks establish that the review package is internally consistent and reproducible within the pinned toolchain.

| Scope | Evidence | Status |
| --- | --- | --- |
| Repository contracts | Unit tests plus design-manifest and record-schema validators | Automated checks pass |
| Generated artifacts | Diagrams and both schematic packages regenerate deterministically | Automated checks pass |
| Schematic parsing and ERC | KiCad 10.0.5 parses and ERC-checks both boards against the allowlist | Automated checks pass |
| Safety, power, isolation, signal integrity, and footprints | Evidence requirements are defined in the [review gates](docs/review-gates.md) | Open fabrication blockers |
| Fabrication, powered electrodes, human use, EMC, regulation, and measurement performance | No completed validation evidence | Not validated |

Passing the repository checks does **not** close a review gate or authorize fabrication or human connection.

## Quick start

The Python checks use only the standard library; no package installation is required.

```bash
git clone https://github.com/topherchris420/circle.git
cd circle
python -m unittest discover -s tests
python tools/check_design_manifest.py
python tools/check_record_schema.py
```

These fast checks are platform-independent and do not require KiCad.

### Complete release verification

[`tools/verify_release.py`](tools/verify_release.py) runs the tests and validators, regenerates diagrams and schematics, invokes KiCad ERC for both boards, checks the ERC allowlist, and rewrites [`hardware/reports/verification-summary.json`](hardware/reports/verification-summary.json).

On Windows, the default KiCad location is `%USERPROFILE%\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`:

```powershell
py -3.11 tools/verify_release.py
```

If KiCad is installed elsewhere, set `KICAD_CLI` explicitly. For example, on POSIX systems:

```bash
KICAD_CLI=/usr/bin/kicad-cli python tools/verify_release.py
```

A successful run ends with:

```text
CIRCLE Rev A review package: VERIFIED
```

The full command rewrites generated artifacts and reports. Run it from a clean worktree and inspect `git diff` afterward; reproducible output should not introduce an unexplained diff.

## Suggested review path

1. Start with the [architecture](docs/architecture.md) and [system diagram](diagrams/system-architecture.svg).
2. Review the [safety analysis](docs/safety-analysis.md) alongside the [safety-boundary diagram](diagrams/safety-boundaries.svg).
3. Inspect the rendered [main-board](hardware/reports/pdf/circle-main.pdf) and [optical-board](hardware/reports/pdf/circle-ppg.pdf) schematics.
4. Confirm every unresolved item in the [review gates](docs/review-gates.md).
5. Cross-check the [pin allocation](docs/pin-allocation.md), [power budget](docs/preliminary-power-budget.md), and [timing/data model](docs/timing-and-data-model.md) against the manifests and schematics.
6. Evaluate the evidence required by the [validation plan](docs/validation-plan.md).
7. Run the complete release verification and inspect the resulting [verification summary](hardware/reports/verification-summary.json).

## Repository map

| Path | Contents |
| --- | --- |
| [`contracts/`](contracts/) | JSON Schema for session records, provenance, timing, sequence ranges, status, and checksums |
| [`diagrams/`](diagrams/) | System-architecture and safety-boundary diagrams in Mermaid and rendered SVG forms |
| [`docs/`](docs/) | Architecture, safety analysis, pin allocation, timing/data model, power budget, validation plan, and review gates |
| [`hardware/design-manifest.json`](hardware/design-manifest.json) | Board hierarchy, required nets, parts, GPIO allocation, and unresolved review gates |
| [`hardware/interfaces.json`](hardware/interfaces.json) | Connector pin ordering, electrical domains, and EDA attachment policy |
| [`hardware/circle-main/`](hardware/circle-main/) | Main-board KiCad project and generated legacy schematic sheets |
| [`hardware/circle-ppg/`](hardware/circle-ppg/) | Optical-board KiCad project and generated legacy schematic sheet |
| [`hardware/reports/`](hardware/reports/) | ERC inputs and allowlist, BOMs, rendered schematics, toolchain record, and verification summary |
| [`tools/`](tools/) | Deterministic generators and contract, schema, ERC, and release checks |
| [`tests/`](tests/) | Standard-library unit tests for repository and generated-artifact contracts |

## Regenerate individual artifacts

Use the source-controlled generators rather than hand-editing generated output:

```bash
# Render both SVG architecture diagrams
python tools/render_diagrams.py

# Generate the main-board legacy schematic package
python tools/generate_schematics.py

# Generate the optical-board legacy schematic package
python tools/generate_schematics.py --board circle-ppg
```

After regeneration, run at least the fast checks above. Changes intended for a complete review package should also pass `tools/verify_release.py` with the pinned KiCad version.

## Data contract

[`contracts/session-record.schema.json`](contracts/session-record.schema.json) is the machine-readable contract for captured and derived records. It requires explicit record type, provenance, monotonic device-time bounds, status flags, and CRC-32C evidence; stream-oriented records also retain source identities and sequence ranges.

```bash
python tools/check_record_schema.py
```

## Known limitations

- The safety, power, isolation, signal-integrity, and footprint items in the [review gates](docs/review-gates.md) remain fabrication blockers.
- Component values marked `REVIEW_GATE` require independent calculation, CAD review, and bench evidence.
- KiCad 10.0.5 can parse, ERC-check, and export the generated legacy `.sch` review sources. Native `.kicad_sch` conversion remains open because `kicad-cli sch upgrade` does not import legacy `.sch` files.
- ERC validates parser-visible structure. Architecture-level `NET:` annotations are not fabrication-ready electrical connectivity.
- No fabrication, powered-electrode, human-subject, EMC, regulatory, or measurement-performance validation has been completed.

The pinned versions, encoding, and line-ending requirements are recorded in [`toolchain.json`](toolchain.json).
