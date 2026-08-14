# CIRCLE Rev A Schematic Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reviewable CIRCLE Rev A architecture package and native KiCad 10 multi-sheet schematics for the mainboard and detachable PPG board, with machine-checked safety, timing, provenance, and release-gate contracts.

**Architecture:** A checked-in JSON design manifest is the source of truth for sheets, parts, interfaces, safety nets, and review gates. Small standard-library Python tools validate that manifest, generate deterministic diagrams and KiCad legacy intermediates, and KiCad 10.0.5 upgrades the intermediates to native `.kicad_sch` files for ERC, BOM, PDF, and SVG export. The engineering-review package stays explicitly separate from a fabrication release.

**Tech Stack:** KiCad 10.0.5, Python 3.11+ standard library, `unittest`, JSON Schema draft 2020-12, Mermaid source, SVG, Markdown, PowerShell, Git

**Design authority:** `docs/superpowers/specs/2026-08-14-circle-rev-a-design.md`

**Safety boundary:** No task authorizes connection to a person, fabrication, powered-electrode testing, or bypass of the USB/debug/expansion interlocks.

**Plan boundary:** This plan delivers CAD, diagrams, review documents, and machine-readable firmware/data contracts. It does not implement firmware, PCB layout, an enclosure, laboratory characterization, or a fabrication release.

---

## File and responsibility map

```text
README.md                                      Project entry point and review-only warning
.gitattributes                                 Stable LF text and binary export rules
.gitignore                                     Generated reports and local KiCad state
toolchain.json                                 Pinned KiCad/Python contract
contracts/session-record.schema.json           Mandatory record/provenance schema
hardware/design-manifest.json                  Boards, sheets, parts, nets, domains, review gates
hardware/interfaces.json                       Connector pinouts and electrical-domain rules
hardware/circle-main/legacy/*.sch              Deterministic KiCad v4 intermediates
hardware/circle-main/legacy/circle-cache.lib   Project symbols used by legacy intermediates
hardware/circle-main/*.kicad_sch               KiCad 10 native mainboard hierarchy
hardware/circle-main/circle-main.kicad_pro     Mainboard project settings and ERC policy
hardware/circle-ppg/legacy/*.sch               Deterministic PPG intermediates
hardware/circle-ppg/legacy/circle-ppg-cache.lib PPG project symbols
hardware/circle-ppg/*.kicad_sch                KiCad 10 native PPG hierarchy
hardware/circle-ppg/circle-ppg.kicad_pro       PPG project settings
hardware/reports/                              ERC, BOM, netlist, PDF, and schematic SVG evidence
diagrams/*.mmd                                 Editable architecture sources
diagrams/*.svg                                 Deterministic rendered diagrams
docs/architecture.md                           System partition and data/control flow
docs/safety-analysis.md                        Interlock truth table and bounded fault claims
docs/timing-and-data-model.md                  Clock mapping, uncertainty, records, provenance
docs/pin-allocation.md                         ESP32 and connector allocation rationale
docs/preliminary-power-budget.md               Rail-by-rail nominal/peak budget and margin
docs/validation-plan.md                        Executable timing, storage, safety, and signal gates
docs/review-gates.md                            Every fabrication-blocking decision and evidence owner
tools/check_design_manifest.py                 Structural and semantic manifest checks
tools/check_record_schema.py                   Positive/negative provenance fixtures
tools/kicad_legacy.py                          Minimal deterministic legacy schematic emitter
tools/generate_schematics.py                   CIRCLE sheet/symbol generation
tools/render_diagrams.py                       Deterministic SVG rendering without new packages
tools/check_erc.py                             ERC allowlist and error gate
tools/verify_release.py                         One-command review-package verification
tests/test_design_manifest.py                  Safety, sheet, connector, and uniqueness contracts
tests/test_record_schema.py                    Provenance rejection and lineage tests
tests/test_kicad_legacy.py                     Emitter syntax and hierarchy tests
tests/test_diagrams.py                          Required nodes, domains, and SVG outputs
tests/test_docs_contract.py                     Warning, review-gate, and cross-document checks
```

## Task 1: Pin the toolchain and repository guardrails

**Files:**
- Create: `.gitattributes`
- Create: `.gitignore`
- Create: `toolchain.json`
- Create: `README.md`
- Create: `tests/test_repo_contract.py`

- [ ] **Step 1: Write the failing repository-contract test**

```python
# tests/test_repo_contract.py
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class RepoContractTest(unittest.TestCase):
    def test_toolchain_and_release_warning_are_pinned(self):
        toolchain = json.loads((ROOT / "toolchain.json").read_text(encoding="utf-8"))
        self.assertEqual(toolchain["kicad"], "10.0.5")
        self.assertGreaterEqual(tuple(toolchain["python_min"].split(".")), ("3", "11"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("ENGINEERING REVIEW ONLY", readme)
        self.assertIn("not approved for fabrication or human connection", readme)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the missing-file failure**

Run: `py -m unittest tests.test_repo_contract -v`

Expected: `ERROR` with `FileNotFoundError: toolchain.json`.

- [ ] **Step 3: Add the pinned files**

```json
{
  "kicad": "10.0.5",
  "python_min": "3.11",
  "record_schema": "2020-12",
  "text_encoding": "UTF-8",
  "line_endings": "LF"
}
```

```gitattributes
* text=auto
*.md text eol=lf
*.json text eol=lf
*.py text eol=lf
*.sch text eol=lf
*.lib text eol=lf
*.kicad_pro text eol=lf
*.kicad_sch text eol=lf
*.svg text eol=lf
*.pdf binary
```

```gitignore
__pycache__/
*.pyc
*.bak
*.lck
*-backups/
hardware/reports/work/
```

Create `README.md` with this exact first block:

```markdown
# CIRCLE Rev A

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This repository is not approved for fabrication or human connection and does not establish medical-device, electrical-safety, EMC, or measurement-performance claims.

The repository contains the architecture diagrams, safety contracts, validation documents, and KiCad 10 schematics for the CIRCLE Rev A bench validation platform.
```

- [ ] **Step 4: Verify the local tools**

Run: `py --version`

Expected: Python `3.11` or newer.

Run: `kicad-cli version`

Expected: `10.0.5`. If the command is absent, obtain explicit approval for the system dependency, then run `winget install --id KiCad.KiCad --exact --version 10.0.5 --accept-package-agreements --accept-source-agreements`. Do not continue CAD conversion with another major KiCad version.

- [ ] **Step 5: Run the contract test**

Run: `py -m unittest tests.test_repo_contract -v`

Expected: `OK`, 1 test passed.

- [ ] **Step 6: Commit the guardrails**

```powershell
git add .gitattributes .gitignore toolchain.json README.md tests/test_repo_contract.py
git commit -m "Make the CIRCLE review boundary impossible to miss" -m "Pin the CAD toolchain and repository-level warnings before adding design artifacts." -m "Constraint: Engineering-review package only" -m "Confidence: high" -m "Scope-risk: narrow" -m "Tested: py -m unittest tests.test_repo_contract -v"
```

## Task 2: Establish the machine-readable design and interface contracts

**Files:**
- Create: `hardware/design-manifest.json`
- Create: `hardware/interfaces.json`
- Create: `tools/check_design_manifest.py`
- Create: `tests/test_design_manifest.py`

- [ ] **Step 1: Write failing safety and hierarchy tests**

```python
# tests/test_design_manifest.py
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DesignManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads((ROOT / "hardware/design-manifest.json").read_text())
        cls.interfaces = json.loads((ROOT / "hardware/interfaces.json").read_text())

    def test_mainboard_sheet_set_is_exact(self):
        names = [sheet["name"] for sheet in self.design["boards"]["circle-main"]["sheets"]]
        self.assertEqual(names, [
            "00_root", "01_compute_usb", "02_power", "03_eda_safety",
            "04_sensors", "05_storage", "06_sync_isolation",
            "07_feedback_expansion", "08_observability"
        ])

    def test_safety_terms_are_hardware_nets(self):
        nets = set(self.design["required_nets"])
        self.assertTrue({
            "EDA_PREPARE", "EDA_ACTIVE", "BATTERY_VALID", "USB_PRESENT",
            "DEBUG_ATTACHED", "EXTERNAL_EXPANSION_ATTACHED",
            "SAFETY_POWER_GOOD", "EDA_ANALOG_GOOD"
        }.issubset(nets))

    def test_reference_designators_are_unique(self):
        refs = [part["ref"] for part in self.design["parts"]]
        self.assertEqual(len(refs), len(set(refs)))

    def test_external_interfaces_declare_domain_and_eda_policy(self):
        for interface in self.interfaces["connectors"]:
            self.assertIn(interface["domain"], {"BAT_HUMAN", "LAB_ISO"})
            self.assertIn(interface["eda_policy"], {"isolated", "forces_disabled", "internal_only"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm missing-contract failures**

Run: `py -m unittest tests.test_design_manifest -v`

Expected: `ERROR` because both JSON files are absent.

- [ ] **Step 3: Create the design manifest**

Create `hardware/design-manifest.json` with these exact top-level keys and sheet sets:

```json
{
  "schema": 1,
  "release_class": "ENGINEERING_REVIEW_ONLY",
  "boards": {
    "circle-main": {
      "domain": "BAT_HUMAN",
      "sheets": [
        {"name": "00_root", "title": "Hierarchy and safety domains"},
        {"name": "01_compute_usb", "title": "ESP32-S3 compute and USB"},
        {"name": "02_power", "title": "Battery, charging, and partitioned rails"},
        {"name": "03_eda_safety", "title": "EDA acquisition and fail-off interlocks"},
        {"name": "04_sensors", "title": "IMU and optical-head interface"},
        {"name": "05_storage", "title": "4-bit SDMMC recorder"},
        {"name": "06_sync_isolation", "title": "Isolated SYNC IN and OUT"},
        {"name": "07_feedback_expansion", "title": "Haptic and expansion"},
        {"name": "08_observability", "title": "Test points and fault injection"}
      ]
    },
    "circle-ppg": {
      "domain": "BAT_HUMAN",
      "sheets": [
        {"name": "00_ppg_root", "title": "PPG contact board"}
      ]
    }
  },
  "required_nets": [
    "EDA_PREPARE", "EDA_ACTIVE", "BATTERY_VALID", "USB_PRESENT",
    "DEBUG_ATTACHED", "EXTERNAL_EXPANSION_ATTACHED", "SAFETY_POWER_GOOD",
    "EDA_ANALOG_GOOD", "PPG_SDA_3V3", "PPG_SCL_3V3", "PPG_INT",
    "IMU_DRDY", "EDA_DRDY", "SD_D0", "SD_D1", "SD_D2", "SD_D3",
    "SD_CLK", "SD_CMD", "SYNC_IN_CAPTURE", "SYNC_OUT_DRIVE",
    "ISO_HEALTH_CHALLENGE", "ISO_HEALTH_STATUS", "HAPTIC_CURRENT_EDGE"
  ],
  "parts": [],
  "review_gates": [
    "EDA_LIMIT_NETWORK", "EDA_SWITCH_SELECTION", "BATTERY_AND_CHARGE_CURRENT",
    "POWER_MAGNETICS_AND_THERMALS", "ISOLATION_CREEPAGE_CLEARANCE",
    "PPG_CABLE_SIGNAL_INTEGRITY", "FOOTPRINT_VERIFICATION"
  ]
}
```

- [ ] **Step 4: Create the connector-domain contract**

Create `hardware/interfaces.json` with connector entries for `USB_C`, `BATTERY`, `EDA_ELECTRODES`, `PPG_HEAD`, `SYNC_IN_BNC`, `SYNC_OUT_BNC`, `DEBUG`, `INTERNAL_EXPANSION`, `EXTERNAL_EXPANSION`, `HAPTIC`, and `MICROSD`. Assign `LAB_ISO` only to the two BNCs. Assign `forces_disabled` to USB, debug, and external expansion; `isolated` to both BNCs; `internal_only` to all remaining BAT/HUMAN connectors. Give every connector a nonempty ordered `pins` array and never place `BAT_HUMAN_GND` on a BNC.

- [ ] **Step 5: Implement the manifest checker**

```python
# tools/check_design_manifest.py
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    design = json.loads((ROOT / "hardware/design-manifest.json").read_text())
    interfaces = json.loads((ROOT / "hardware/interfaces.json").read_text())
    errors: list[str] = []
    refs = [part["ref"] for part in design["parts"]]
    if len(refs) != len(set(refs)):
        errors.append("duplicate reference designator")
    for connector in interfaces["connectors"]:
        if connector["domain"] == "LAB_ISO" and "BAT_HUMAN_GND" in connector["pins"]:
            errors.append(f"{connector['name']}: LAB_ISO connector exposes BAT_HUMAN_GND")
        if not connector["pins"]:
            errors.append(f"{connector['name']}: empty pin list")
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("design manifest: OK")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run both checks**

Run: `py -m unittest tests.test_design_manifest -v`

Expected: `OK`, 4 tests passed.

Run: `py tools/check_design_manifest.py`

Expected: `design manifest: OK`.

- [ ] **Step 7: Commit the design contracts**

```powershell
git add hardware/design-manifest.json hardware/interfaces.json tools/check_design_manifest.py tests/test_design_manifest.py
git commit -m "Make safety domains and interlock nets machine-checkable" -m "Create one source of truth for board hierarchy, connector domains, and required hardware safety signals." -m "Constraint: External grounded interfaces must never be implicit" -m "Confidence: high" -m "Scope-risk: moderate" -m "Tested: design manifest unit tests and checker"
```

## Task 3: Add enforceable record and provenance contracts

**Files:**
- Create: `contracts/session-record.schema.json`
- Create: `tools/check_record_schema.py`
- Create: `tests/test_record_schema.py`

- [ ] **Step 1: Write failing positive and negative provenance tests**

```python
# tests/test_record_schema.py
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOWED = {"RAW_MEASURED", "DERIVED", "MODEL_INFERRED", "SIMULATED", "TEST", "INTERVENTION"}


class RecordSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "contracts/session-record.schema.json").read_text())

    def test_provenance_enum_is_exact(self):
        self.assertEqual(set(self.schema["$defs"]["provenance"]["enum"]), ALLOWED)

    def test_provenance_is_required(self):
        self.assertIn("provenance", self.schema["required"])

    def test_model_records_require_lineage(self):
        rule = next(rule for rule in self.schema["allOf"] if rule["if"]["properties"]["provenance"].get("const") == "MODEL_INFERRED")
        self.assertEqual(set(rule["then"]["required"]), {"source_stream_ids", "source_sequence_ranges", "model"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the schema is absent**

Run: `py -m unittest tests.test_record_schema -v`

Expected: `ERROR` with `FileNotFoundError`.

- [ ] **Step 3: Create the complete schema**

Create a draft 2020-12 JSON Schema whose root requires `schema_version`, `record_type`, `provenance`, `device_time_start_us`, `device_time_end_us`, `status_flags`, and `crc32c`. Set `additionalProperties` to false. Define the six-value provenance enum exactly as tested. Define record types `SESSION_HEADER`, `STREAM_DESCRIPTOR`, `SAMPLE_CHUNK`, `EVENT`, `CLOCK_MAPPING`, `CONFIG_CHANGE`, `GAP`, `FAULT`, `MODEL_RESULT`, `INTERVENTION`, and `SESSION_TRAILER`. Require `source_stream_ids`, `source_sequence_ranges`, and `model` when provenance is `MODEL_INFERRED`; require `decision_id` and `actuation_evidence_ids` when provenance is `INTERVENTION`; require `dropped_first_sequence`, `dropped_last_sequence`, and `cause` when record type is `GAP`.

- [ ] **Step 4: Add a dependency-free semantic checker**

`tools/check_record_schema.py` shall load the schema, verify the exact enums and conditional required-field sets above, print `record schema: OK`, and exit 1 on any mismatch. It shall not claim full JSON Schema evaluation.

- [ ] **Step 5: Run schema checks**

Run: `py -m unittest tests.test_record_schema -v; py tools/check_record_schema.py`

Expected: 3 passing tests followed by `record schema: OK`.

- [ ] **Step 6: Commit the provenance contract**

```powershell
git add contracts/session-record.schema.json tools/check_record_schema.py tests/test_record_schema.py
git commit -m "Prevent inference from masquerading as measurement" -m "Encode the approved provenance classes, model lineage, intervention evidence, and exact gap requirements as a machine-checked schema." -m "Constraint: Every record has one explicit causal-origin class" -m "Confidence: high" -m "Scope-risk: moderate" -m "Tested: record schema unit and semantic checks"
```

## Task 4: Generate the architecture and safety diagrams

**Files:**
- Create: `diagrams/system-architecture.mmd`
- Create: `diagrams/safety-boundaries.mmd`
- Create: `tools/render_diagrams.py`
- Create: `tests/test_diagrams.py`
- Generate: `diagrams/system-architecture.svg`
- Generate: `diagrams/safety-boundaries.svg`

- [ ] **Step 1: Write the failing diagram contract test**

```python
# tests/test_diagrams.py
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DiagramContractTest(unittest.TestCase):
    def test_architecture_contains_complete_loop(self):
        text = (ROOT / "diagrams/system-architecture.mmd").read_text()
        for node in ["Human", "CIRCLE", "VitalSync", "DRR", "AdaptiveDecision", "Feedback"]:
            self.assertIn(node, text)

    def test_safety_diagram_names_both_domains_and_all_forced_disables(self):
        text = (ROOT / "diagrams/safety-boundaries.mmd").read_text()
        for token in ["BAT_HUMAN", "LAB_ISO", "USB_PRESENT", "DEBUG_ATTACHED", "EXTERNAL_EXPANSION_ATTACHED"]:
            self.assertIn(token, text)

    def test_svg_outputs_carry_review_warning(self):
        for name in ["system-architecture.svg", "safety-boundaries.svg"]:
            self.assertIn("ENGINEERING REVIEW ONLY", (ROOT / "diagrams" / name).read_text())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm missing-diagram failures**

Run: `py -m unittest tests.test_diagrams -v`

Expected: `ERROR` for missing Mermaid sources.

- [ ] **Step 3: Create the Mermaid sources**

`system-architecture.mmd` shall contain the closed loop and a second acquisition path showing `Sensors --> Capture --> SRAM --> PSRAM --> SD`, with telemetry branching after record assembly. `safety-boundaries.mmd` shall place EDA, compute, storage, and haptic inside `BAT_HUMAN`; BNC conditioning inside `LAB_ISO`; ISOW7742 across the boundary; and USB/debug/external-expansion detection feeding the hardware EDA gate.

- [ ] **Step 4: Implement deterministic SVG rendering**

`tools/render_diagrams.py` shall use only `xml.etree.ElementTree`, fixed node coordinates, a fixed color palette, and XML-escaped labels. It shall render the exact node/edge lists used by the Mermaid files and place `ENGINEERING REVIEW ONLY — NOT FOR HUMAN CONNECTION` at the top of each SVG. Its CLI takes no arguments and overwrites only the two declared SVG outputs.

- [ ] **Step 5: Generate and test**

Run: `py tools/render_diagrams.py; py -m unittest tests.test_diagrams -v`

Expected: `rendered 2 diagrams` and 3 passing tests.

- [ ] **Step 6: Commit the diagrams**

```powershell
git add diagrams tools/render_diagrams.py tests/test_diagrams.py
git commit -m "Expose the closed loop and every grounded-interface boundary" -m "Add editable and deterministic rendered diagrams that keep acquisition, feedback, and safety paths visually distinct." -m "Constraint: Diagram domains must match the schematic domains" -m "Confidence: high" -m "Scope-risk: narrow" -m "Tested: diagram contract tests"
```

## Task 5: Build and test the deterministic KiCad legacy emitter

**Files:**
- Create: `tools/kicad_legacy.py`
- Create: `tests/test_kicad_legacy.py`

- [ ] **Step 1: Write the failing emitter tests**

```python
# tests/test_kicad_legacy.py
import pathlib
import tempfile
import unittest
from tools.kicad_legacy import Component, LegacySheet, Pin, ProjectSymbol


class LegacyEmitterTest(unittest.TestCase):
    def test_symbol_emits_pin_types_and_review_fields(self):
        symbol = ProjectSymbol("WINDOW_SUPERVISOR", [Pin("IN", "1", "I"), Pin("GOOD_N", "2", "C")])
        text = symbol.emit()
        self.assertIn("X IN 1", text)
        self.assertIn("X GOOD_N 2", text)

    def test_sheet_emits_component_labels_and_end_marker(self):
        sheet = LegacySheet("EDA Safety")
        sheet.add(Component("U1", "WINDOW_SUPERVISOR", 2000, 1500, "TPS3700"))
        sheet.label("USB_PRESENT", 1200, 1500)
        text = sheet.emit()
        self.assertIn("EESchema Schematic File Version 4", text)
        self.assertIn("USB_PRESENT", text)
        self.assertTrue(text.endswith("$EndSCHEMATC\n"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the module is absent**

Run: `py -m unittest tests.test_kicad_legacy -v`

Expected: import failure for `tools.kicad_legacy`.

- [ ] **Step 3: Implement the emitter data types**

Implement frozen `Pin` and `ProjectSymbol` dataclasses, plus mutable `Component` and `LegacySheet` classes. `ProjectSymbol.emit()` shall output a complete KiCad legacy `DEF`/`DRAW`/`ENDDRAW`/`ENDDEF` block with a rectangular body and the declared pins. `LegacySheet.emit()` shall output the v4 header, A4 description block, `$Comp` blocks, `Text Label`, `Wire Wire Line`, `Text Notes`, and the exact `$EndSCHEMATC` terminator. Add methods `wire(x1, y1, x2, y2)`, `label(name, x, y)`, `note(text, x, y)`, and `add(component)`.

- [ ] **Step 4: Add emitter invariants**

Reject duplicate references, labels containing whitespace, missing pin numbers, coordinates outside the A4 sheet, and any component whose value is empty. Permit `REVIEW_GATE:<gate-name>` values because they are explicit release blockers.

- [ ] **Step 5: Run the emitter tests**

Run: `py -m unittest tests.test_kicad_legacy -v`

Expected: `OK`, 2 tests passed.

- [ ] **Step 6: Commit the emitter**

```powershell
git add tools/kicad_legacy.py tests/test_kicad_legacy.py
git commit -m "Make schematic generation reproducible and reviewable" -m "Add a narrow legacy emitter so KiCad 10 performs the authoritative conversion instead of trusting hand-written native S-expressions." -m "Rejected: Direct native .kicad_sch authoring | embedded symbol syntax is too fragile for unvalidated text generation" -m "Confidence: medium" -m "Scope-risk: moderate" -m "Tested: legacy emitter unit tests"
```

## Task 6: Generate the compute, USB, power, and root hierarchy

**Files:**
- Create: `tools/generate_schematics.py`
- Modify: `hardware/design-manifest.json`
- Generate: `hardware/circle-main/legacy/circle-cache.lib`
- Generate: `hardware/circle-main/legacy/00_root.sch`
- Generate: `hardware/circle-main/legacy/01_compute_usb.sch`
- Generate: `hardware/circle-main/legacy/02_power.sch`
- Modify: `tests/test_design_manifest.py`

- [ ] **Step 1: Add failing part, power-path, and GPIO-allocation assertions**

Add tests requiring these references and values: `U1=ESP32-S3-WROOM-1-N16R8`, `J1=USB-C-USB2`, `U2=BQ24074`, `U3=TPS63070`, `U4=TPS3700`, `U5=TPS3700`, `U6=MCP23017`, `J2=LIPO_1S_NTC`, and `F1=USB_INPUT_FUSE`. Assert `USB_PRESENT` originates ahead of `U2`, `VBAT` passes through the battery-valid monitor, and no root-sheet connection joins `BAT_HUMAN_GND` to `LAB_ISO_GND`. Assert the manifest's `gpio_allocation` object equals the exact allocation in Step 3.

- [ ] **Step 2: Run the focused test and confirm missing parts**

Run: `py -m unittest tests.test_design_manifest.DesignManifestTest -v`

Expected: failures naming the absent part references.

- [ ] **Step 3: Extend the manifest with exact compute and power parts**

Add the references above plus USB CC resistors `R1/R2=5.1k`, USB data resistors `R3/R4=22R`, ESD array `D1=TPD4E05U06`, boot/reset switches, rail switches for SD/PPG LED/haptic/isolation/expansion, and Kelvin shunt/jumper pairs for system, analog, SD, PPG LED, haptic, and isolation rails. Mark charge-current programming, inductor choice, thermal copper, and battery connector footprint with their existing review-gate identifiers.

Encode this exact ESP32 key/value allocation as the `gpio_allocation` JSON object in `hardware/design-manifest.json`:

```text
{
  GPIO0: BOOT_BUTTON_ONLY,
  GPIO1: SYNC_IN_CAPTURE,
  GPIO2: SYNC_OUT_DRIVE,
  GPIO3: RESERVED_STRAP,
  GPIO4: SD_CLK,
  GPIO5: SD_CMD,
  GPIO6: SD_D0,
  GPIO7: SD_D1,
  GPIO8: SYS_I2C_SDA,
  GPIO9: SYS_I2C_SCL,
  GPIO10: IMU_SCLK,
  GPIO11: IMU_MOSI,
  GPIO12: IMU_MISO,
  GPIO13: IMU_CS_N,
  GPIO14: IMU_DRDY,
  GPIO15: SD_D2,
  GPIO16: SD_D3,
  GPIO17: PPG_SDA_3V3,
  GPIO18: PPG_SCL_3V3,
  GPIO19: USB_D_MINUS,
  GPIO20: USB_D_PLUS,
  GPIO21: PPG_INT_N_WIRED_OR,
  GPIO35: UNAVAILABLE_OCTAL_PSRAM,
  GPIO36: UNAVAILABLE_OCTAL_PSRAM,
  GPIO37: UNAVAILABLE_OCTAL_PSRAM,
  GPIO38: ISO_HEALTH_CHALLENGE,
  GPIO39: EDA_SCLK,
  GPIO40: EDA_MOSI,
  GPIO41: EDA_MISO,
  GPIO42: EDA_CS_N,
  GPIO43: DEBUG_UART_TX,
  GPIO44: DEBUG_UART_RX,
  GPIO45: EDA_FW_REQUEST,
  GPIO46: HAPTIC_CURRENT_EDGE,
  GPIO47: EDA_DRDY,
  GPIO48: SYS_STATUS_INT_N
}
```

GPIO45 and GPIO46 are strapping pins. Keep GPIO45 low through reset so `EDA_FW_REQUEST` is fail-off, and require the haptic comparator to hold GPIO46 low through reset. GPIO35–GPIO37 are unavailable on the N16R8 module because its octal PSRAM uses them. U6 shall collect `USB_PRESENT`, `DEBUG_ATTACHED`, `EXTERNAL_EXPANSION_ATTACHED`, `BATTERY_VALID`, `SAFETY_POWER_GOOD`, `EDA_ANALOG_GOOD`, `SD_CARD_DETECT`, `HAPTIC_FAULT`, and `ISO_HEALTH_STATUS`; its interrupt uses GPIO48. U6 is observability only and is not in the hardware EDA permission path.

- [ ] **Step 4: Implement generator entry points**

`tools/generate_schematics.py` shall load both hardware JSON contracts, instantiate project symbols, write one cache library per board, and generate every declared legacy sheet. It shall refuse to run unless `release_class` is `ENGINEERING_REVIEW_ONLY`. The root sheet shall instantiate the eight child sheets with hierarchical labels and show the `BAT_HUMAN` and `LAB_ISO` boundary note.

- [ ] **Step 5: Generate the first three sheets**

Run: `py tools/generate_schematics.py --sheets 00_root,01_compute_usb,02_power`

Expected: `generated 3 mainboard sheets and 1 symbol library`.

- [ ] **Step 6: Inspect required nets**

Run: `rg -n "USB_PRESENT|BATTERY_VALID|SAFETY_POWER_GOOD|BAT_HUMAN_GND|LAB_ISO_GND" hardware/circle-main/legacy`

Expected: USB and power terms appear on their source sheets; both grounds appear on the root but no wire joins them.

- [ ] **Step 7: Run tests and commit**

Run: `py -m unittest tests.test_design_manifest tests.test_kicad_legacy -v`

Expected: all tests pass.

```powershell
git add hardware/design-manifest.json hardware/circle-main/legacy tools/generate_schematics.py tests/test_design_manifest.py
git commit -m "Keep USB attachment upstream of every EDA enable path" -m "Generate the compute and partitioned power hierarchy with pre-charger VBUS detection and explicit review-gated sizing." -m "Constraint: Charger state must not mask USB attachment" -m "Confidence: medium" -m "Scope-risk: broad" -m "Tested: manifest and legacy emitter tests; required-net inspection"
```

## Task 7: Generate the EDA front end and hardware interlocks

**Files:**
- Modify: `hardware/design-manifest.json`
- Generate: `hardware/circle-main/legacy/03_eda_safety.sch`
- Modify: `tests/test_design_manifest.py`
- Create: `docs/safety-analysis.md`

- [ ] **Step 1: Add failing EDA topology assertions**

Require `U10=ADS1220`, `U11=OPA2192`, `U12=REF5020`, separate normally-open electrode switches `K1` and `K2`, four passive limiter references `R_EDA_A1`, `R_EDA_A2`, `R_EDA_B1`, `R_EDA_B2`, three hardware-good terms, and direct unsafe-input paths from USB/debug/external expansion to both relay drive and EDA rail disable. Assert every limiter has value `REVIEW_GATE:EDA_LIMIT_NETWORK` and every relay has `REVIEW_GATE:EDA_SWITCH_SELECTION`.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `py -m unittest tests.test_design_manifest -v`

Expected: failures naming absent EDA parts and paths.

- [ ] **Step 3: Add the EDA circuit to the manifest and generator**

Generate the two-stage sequence exactly as the spec states: primary conditions form `EDA_PREPARE`; that enables the disconnected analog rail; `EDA_ANALOG_GOOD` then permits `EDA_ACTIVE`; `EDA_ACTIVE` energizes two separately packaged normally-open electrode switches. Place the four passive limiters so they remain in series even with a welded switch. Route protected differential nodes to ADS1220 inputs, provide a buffered low-voltage excitation reference, a calibration-injection connector behind the passive limits, electrode-disconnect detection, DRDY, SPI, and safe analog test points.

- [ ] **Step 4: Write the safety analysis**

Include the exact interlock equations, voltage windows, 10 ms qualification times, 10 microsecond asynchronous release requirement, and a table covering normal disabled, battery absent, charger-only, USB insertion, debug insertion, external expansion insertion, analog undervoltage, supervisor power loss, one welded electrode switch, and firmware hang. For a welded switch, state only the bounded claim: the opposite conductor remains open or residual current remains below the analyzed limit. Do not claim medical certification or protection from arbitrary probes.

- [ ] **Step 5: Generate and inspect**

Run: `py tools/generate_schematics.py --sheets 03_eda_safety`

Expected: `generated 1 mainboard sheet`.

Run: `rg -n "EDA_PREPARE|EDA_ACTIVE|USB_PRESENT|DEBUG_ATTACHED|EXTERNAL_EXPANSION_ATTACHED|REVIEW_GATE:EDA" hardware/circle-main/legacy/03_eda_safety.sch docs/safety-analysis.md`

Expected: every safety term and both review gates are present.

- [ ] **Step 6: Run tests and commit**

```powershell
py -m unittest tests.test_design_manifest tests.test_kicad_legacy -v
git add hardware/design-manifest.json hardware/circle-main/legacy/03_eda_safety.sch docs/safety-analysis.md tests/test_design_manifest.py
git commit -m "Make EDA activation fail off under every intended cable state" -m "Encode the two-stage analog qualification, bilateral normal-state disconnection, passive limits, and bounded single-fault claims." -m "Constraint: Firmware cannot override an unsafe hardware input" -m "Confidence: medium" -m "Scope-risk: broad" -m "Directive: Limiter and switch values remain fabrication blockers" -m "Tested: EDA topology contract and generated-net inspection"
```

## Task 8: Generate sensors, storage, isolated SYNC, feedback, and observability sheets

**Files:**
- Modify: `hardware/design-manifest.json`
- Generate: `hardware/circle-main/legacy/04_sensors.sch`
- Generate: `hardware/circle-main/legacy/05_storage.sch`
- Generate: `hardware/circle-main/legacy/06_sync_isolation.sch`
- Generate: `hardware/circle-main/legacy/07_feedback_expansion.sch`
- Generate: `hardware/circle-main/legacy/08_observability.sch`
- Modify: `tests/test_design_manifest.py`

- [ ] **Step 1: Add failing subsystem assertions**

Require `U20=ICM-42688-P` on dedicated SPI plus `IMU_DRDY`; a keyed PPG connector with 3.3 V logic, separate LED power, two grounds, I2C, PPG interrupt, optional motion interrupt, and board ID; a card-detect microSD socket on four SDMMC data lines; `U30=ISOW7742` with `LAB_ISO_GND` only on the external side; protected comparator-based SYNC IN; MOSFET open-drain SYNC OUT; `U40=DRV2605L`; haptic current comparator capture; internal and external expansion connectors with different EDA policies; and test points for every rail and safety term.

- [ ] **Step 2: Run tests and confirm the new assertions fail**

Run: `py -m unittest tests.test_design_manifest -v`

Expected: failures naming the missing subsystem parts and connector rules.

- [ ] **Step 3: Add exact subsystem entries**

Extend the manifest and interfaces with the parts and nets above. Add series-damping footprints on SDMMC and cable I2C, ESD parts that return to the correct domain, switched rails for SD/PPG LED/haptic/isolation, current-shunt hooks, card detect, safe-eject button, actuator connector, haptic current sense, isolation health challenge/status, BNCs, and distinct internal/external expansion connectors. Never connect a BAT/HUMAN test point to LAB_ISO ground.

- [ ] **Step 4: Generate all five sheets**

Run: `py tools/generate_schematics.py --sheets 04_sensors,05_storage,06_sync_isolation,07_feedback_expansion,08_observability`

Expected: `generated 5 mainboard sheets`.

- [ ] **Step 5: Check the isolation boundary and bus separation**

Run: `py tools/check_design_manifest.py`

Expected: `design manifest: OK`.

Run: `rg -n "LAB_ISO_GND|BAT_HUMAN_GND|SD_D[0-3]|IMU_DRDY|HAPTIC_CURRENT_EDGE|ISO_HEALTH" hardware/circle-main/legacy`

Expected: LAB_ISO ground occurs only on the root and isolation sheet; all acquisition evidence nets are present.

- [ ] **Step 6: Run tests and commit**

```powershell
py -m unittest tests.test_design_manifest tests.test_kicad_legacy -v
git add hardware/design-manifest.json hardware/interfaces.json hardware/circle-main/legacy tests/test_design_manifest.py
git commit -m "Keep storage and actuation away from acquisition timing" -m "Generate dedicated sensor, SDMMC, reinforced SYNC, haptic-evidence, expansion, and observability sheets." -m "Constraint: LAB_ISO ground exists only beyond the reinforced barrier" -m "Confidence: medium" -m "Scope-risk: broad" -m "Tested: subsystem manifest tests and ground-domain inspection"
```

## Task 9: Generate the detachable PPG contact board

**Files:**
- Modify: `hardware/design-manifest.json`
- Generate: `hardware/circle-ppg/legacy/circle-ppg-cache.lib`
- Generate: `hardware/circle-ppg/legacy/00_ppg_root.sch`
- Modify: `tests/test_design_manifest.py`

- [ ] **Step 1: Add failing daughterboard assertions**

Require `U101=MAX30102`, `U102=1V8_LOW_NOISE_LDO`, `U103=I2C_LEVEL_TRANSLATOR`, `U104=AT24CS02`, and `U105=LIS2DW12` marked `DNI`. Assert raw red/IR support, separate logic and LED rails, local decoupling, EEPROM identity, PPG interrupt, optional accelerometer interrupt, cable ESD/damping, and no heart-rate signal net.

- [ ] **Step 2: Run the test and confirm the daughterboard is absent**

Run: `py -m unittest tests.test_design_manifest -v`

Expected: failures naming PPG references and the missing DNI state.

- [ ] **Step 3: Add and generate the PPG board**

Place the MAX30102, local 1.8 V rail, 3.3-to-1.8 V bidirectional I2C translation, identity EEPROM, separate LED filtering, interrupt lines, cable protection, optical/mechanical keepout notes, and DNI motion sensor. Use the exact mainboard cable pin order from `hardware/interfaces.json`; generation shall fail if the two ends differ.

- [ ] **Step 4: Verify replaceability and raw-data wording**

Run: `py tools/generate_schematics.py --board circle-ppg; py tools/check_design_manifest.py`

Expected: one PPG sheet and symbol library generated; manifest check passes.

Run: `rg -n "RAW RED/IR|AT24CS02|DNI|HEART_RATE" hardware/circle-ppg/legacy/00_ppg_root.sch`

Expected: raw-data, EEPROM, and DNI markers are present; `HEART_RATE` has no match.

- [ ] **Step 5: Run tests and commit**

```powershell
py -m unittest tests.test_design_manifest tests.test_kicad_legacy -v
git add hardware/design-manifest.json hardware/circle-ppg/legacy tests/test_design_manifest.py
git commit -m "Let optical heads change without rewriting the recorder" -m "Generate a keyed, identified PPG contact board that preserves raw red and IR samples and isolates cable-level decisions from compute." -m "Constraint: Contact accelerometer remains DNI until cable and value analysis passes" -m "Confidence: medium" -m "Scope-risk: moderate" -m "Tested: PPG manifest and generated-sheet checks"
```

## Task 10: Convert to native KiCad 10, run ERC, and export evidence

**Files:**
- Generate: `hardware/circle-main/*.kicad_sch`
- Generate: `hardware/circle-main/circle-main.kicad_pro`
- Generate: `hardware/circle-ppg/*.kicad_sch`
- Generate: `hardware/circle-ppg/circle-ppg.kicad_pro`
- Create: `tools/check_erc.py`
- Create: `hardware/reports/erc-allowlist.json`
- Generate: `hardware/reports/*.json`
- Generate: `hardware/reports/bom/*.csv`
- Generate: `hardware/reports/pdf/*.pdf`
- Generate: `hardware/reports/svg/**/*.svg`

- [ ] **Step 1: Verify the pinned KiCad version**

Run: `kicad-cli version`

Expected: exactly `10.0.5`.

- [ ] **Step 2: Upgrade child sheets before roots**

Create `hardware/circle-main/circle-main.kicad_pro` and `hardware/circle-ppg/circle-ppg.kicad_pro` with the exact JSON content `{}`. Run `kicad-cli sch upgrade` on every child `.sch`, then on `00_root.sch` and `00_ppg_root.sch`. Move the resulting native files into their board roots using the same base names. Run an ERC export immediately; retain any deterministic project settings KiCad 10.0.5 writes while opening the native roots. Do not hand-edit native schematic S-expressions after successful conversion; make electrical changes in the manifest/generator and regenerate.

- [ ] **Step 3: Run ERC in JSON mode**

Run:

```powershell
kicad-cli sch erc --format json --severity-all --output hardware/reports/circle-main-erc.json hardware/circle-main/00_root.kicad_sch
kicad-cli sch erc --format json --severity-all --output hardware/reports/circle-ppg-erc.json hardware/circle-ppg/00_ppg_root.kicad_sch
```

Expected: both files parse and JSON reports are created.

- [ ] **Step 4: Implement the ERC gate**

`hardware/reports/erc-allowlist.json` shall contain only exact warning fingerprints, sheet paths, and written rationales. `tools/check_erc.py` shall fail on every error, every warning not in the allowlist, every stale allowlist entry, and every rationale shorter than 20 characters. It shall print counts per project and `ERC gate: OK` only when the reports match.

- [ ] **Step 5: Resolve or explain every ERC item**

Fix incorrect pin types, missing power flags, unconnected pins, and hierarchy mismatches at the manifest/generator level. Use no-connect flags for deliberately unused pins. Allowlist only engineering-review warnings that cannot be eliminated without choosing a fabrication-gated value or footprint.

- [ ] **Step 6: Export BOM, PDF, SVG, and netlists**

Use `kicad-cli sch export bom`, `sch export pdf`, `sch export svg`, and `sch export netlist` for both projects. Store outputs under `hardware/reports` and include KiCad version metadata in `hardware/reports/toolchain.txt`.

- [ ] **Step 7: Verify and commit native CAD**

Run: `py tools/check_erc.py`

Expected: `ERC gate: OK` and zero unexplained errors.

```powershell
git add hardware/circle-main hardware/circle-ppg hardware/reports tools/check_erc.py
git commit -m "Make KiCad validate the generated electrical hierarchy" -m "Convert through KiCad 10.0.5, gate every ERC result, and check in reviewable BOM and rendering evidence." -m "Constraint: Native schematics are generated artifacts; electrical edits originate in the manifest and generator" -m "Confidence: medium" -m "Scope-risk: broad" -m "Tested: KiCad 10 parse, ERC, BOM, PDF, SVG, and netlist exports"
```

## Task 11: Complete the engineering documents and cross-check them against CAD

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/timing-and-data-model.md`
- Create: `docs/pin-allocation.md`
- Create: `docs/preliminary-power-budget.md`
- Create: `docs/validation-plan.md`
- Create: `docs/review-gates.md`
- Create: `tests/test_docs_contract.py`

- [ ] **Step 1: Write failing document-contract tests**

Test that every document contains `ENGINEERING REVIEW ONLY`; every review-gate ID in the manifest appears in `docs/review-gates.md`; pin allocation names every ESP32 net exported by the manifest; the power budget contains nominal, peak, source, confidence, and margin columns; timing contains 1 microsecond device resolution, 100 microsecond EDA/IMU uncertainty, 1 millisecond PPG uncertainty, and SYNC/haptic limits; validation contains the 24-hour and 45-second storage tests; and safety-analysis language never claims arbitrary grounded probes are prevented.

- [ ] **Step 2: Run the tests and confirm missing-document failures**

Run: `py -m unittest tests.test_docs_contract -v`

Expected: failures for each missing document.

- [ ] **Step 3: Write architecture and timing documents**

`docs/architecture.md` shall describe both electrical domains, both boards, bus allocation, two-stage buffering, isolated SYNC, haptic evidence, and the closed-loop data path. `docs/timing-and-data-model.md` shall define device monotonic time, native-clock mappings, uncertainty flags, PPG FIFO reconstruction, sequence/gap rules, record framing, and provenance causality using the exact schema names.

- [ ] **Step 4: Write pin allocation and power budget**

The pin table shall list GPIO, peripheral function, direction, boot state, strapping risk, pull state, interrupt/DMA role, and owning sheet. The power table shall list VBAT/system, 3V3 digital, EDA analog, PPG 1V8, PPG LED, SD, haptic, and isolated-SYNC rails with nominal and peak estimates, source citation, confidence, margin, and measurement hook. Mark the charger, battery, magnetics, and thermal closure gates explicitly.

- [ ] **Step 5: Write validation and review-gate documents**

Copy every numeric acceptance criterion from the approved spec without weakening it. For each gate, record the decision, blocking evidence, affected sheets/parts, verification method, and release consequence. State that completion of the review package does not close a fabrication gate.

- [ ] **Step 6: Run document tests and commit**

```powershell
py -m unittest tests.test_docs_contract -v
git add docs tests/test_docs_contract.py
git commit -m "Turn open hardware decisions into explicit release blockers" -m "Connect architecture, timing, pin, power, safety, and validation documents to the generated CAD and machine-readable gate IDs." -m "Constraint: Review evidence must remain separate from fabrication approval" -m "Confidence: medium" -m "Scope-risk: moderate" -m "Tested: document contract tests"
```

## Task 12: Add one-command verification and perform final review

**Files:**
- Create: `tools/verify_release.py`
- Modify: `README.md`
- Generate: `hardware/reports/verification-summary.json`

- [ ] **Step 1: Implement the verification runner**

`tools/verify_release.py` shall run, in order: all `unittest` tests, design manifest checker, record schema checker, diagram renderer followed by a clean-diff check, schematic generator followed by a clean-diff check, KiCad version check, ERC exports, ERC checker, BOM/netlist/PDF/SVG exports, and a scan for disallowed placeholder tokens. It shall capture command, exit code, elapsed time, and SHA-256 hashes of the spec, manifests, native root schematics, ERC reports, BOMs, and PDFs in `hardware/reports/verification-summary.json`.

- [ ] **Step 2: Document the exact verification command**

Add this block to `README.md`:

````markdown
## Verify the review package

```powershell
py tools/verify_release.py
```

Success means the generated artifacts are reproducible, both KiCad projects parse, and no unexplained ERC error remains. It does not authorize fabrication or human connection.
````

- [ ] **Step 3: Run the full verification**

Run: `py tools/verify_release.py`

Expected final line: `CIRCLE Rev A review package: VERIFIED`.

- [ ] **Step 4: Confirm a clean reproducible tree**

Run: `git status --short`

Expected: only `hardware/reports/verification-summary.json` is modified before adding it. A clean tree is required after the final commit in Step 6.

- [ ] **Step 5: Perform independent reviews**

Dispatch one architecture/safety reviewer and one completion verifier. The safety reviewer checks the EDA current path, interlocks, ground domains, isolation claims, and review gates. The verifier checks spec-to-task coverage, native KiCad parse/ERC evidence, test outputs, and artifact hashes. Resolve every high or medium finding before the final commit.

- [ ] **Step 6: Commit the verified review package**

```powershell
git add README.md tools/verify_release.py hardware/reports/verification-summary.json
git commit -m "Make every CIRCLE review claim reproducible" -m "Provide one command that regenerates, parses, checks, exports, and hashes the complete engineering-review package." -m "Constraint: Verification proves package consistency, not electrical safety certification" -m "Confidence: medium" -m "Scope-risk: broad" -m "Directive: Re-run verification after any manifest, symbol, net, or review-gate change" -m "Tested: py tools/verify_release.py" -m "Not-tested: Fabrication, powered electrodes, human connection, EMC, or regulatory compliance"
```

## Final acceptance checklist

- [ ] Both native KiCad projects open and export under KiCad 10.0.5.
- [ ] ERC contains zero errors and zero unexplained warnings.
- [ ] Architecture and safety diagrams match schematic domains and interlocks.
- [ ] `BAT_HUMAN_GND` never crosses to either BNC shield or `LAB_ISO_GND`.
- [ ] The schematic contains independent hardware paths by which USB, debug, and external expansion attachment de-energize the EDA path without firmware participation.
- [ ] Both electrode conductors are normally open; single-fault claims remain bounded.
- [ ] PPG raw red/IR, EDA raw ADC, IMU raw samples, sequences, gaps, and native timing evidence are preserved by the contracts.
- [ ] Haptic command, electrical onset, physical observation, completion, and fault remain distinct.
- [ ] Every fabrication-blocking value and footprint appears in `docs/review-gates.md` and the BOM.
- [ ] Full verification passes and the worktree is clean.
- [ ] Repository remains labeled engineering-review-only and not approved for fabrication or human connection.
