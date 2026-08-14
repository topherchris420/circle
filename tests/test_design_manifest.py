import io
import json
import pathlib
import unittest
from contextlib import redirect_stdout
from unittest import mock

import tools.check_design_manifest as checker

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_CIRCLE_MAIN_SHEETS = [
    "00_root",
    "01_compute_usb",
    "02_power",
    "03_eda_safety",
    "04_sensors",
    "05_storage",
    "06_sync_isolation",
    "07_feedback_expansion",
    "08_observability",
]
EXPECTED_CIRCLE_PPG_SHEETS = ["00_ppg_root"]
EXPECTED_CONNECTORS = [
    {"name": "USB_C", "domain": "BAT_HUMAN", "eda_policy": "forces_disabled", "pins": ["VBUS_5V", "USB_DN", "USB_DP", "USB_CC1", "USB_CC2", "USB_SHIELD"]},
    {"name": "BATTERY", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["BAT_POS", "BAT_NEG", "BAT_NTC"]},
    {"name": "EDA_ELECTRODES", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["EDA_DRIVE_P", "EDA_DRIVE_N", "EDA_SENSE_P", "EDA_SENSE_N"]},
    {"name": "PPG_HEAD", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["PPG_3V3", "PPG_SDA_3V3", "PPG_SCL_3V3", "PPG_INT", "BAT_HUMAN_GND"]},
    {"name": "SYNC_IN_BNC", "domain": "LAB_ISO", "eda_policy": "isolated", "pins": ["SYNC_IN_LAB", "LAB_ISO_GND"]},
    {"name": "SYNC_OUT_BNC", "domain": "LAB_ISO", "eda_policy": "isolated", "pins": ["SYNC_OUT_LAB", "LAB_ISO_GND"]},
    {"name": "DEBUG", "domain": "BAT_HUMAN", "eda_policy": "forces_disabled", "pins": ["UART_TX", "UART_RX", "DEBUG_ATTACHED", "BAT_HUMAN_GND"]},
    {"name": "INTERNAL_EXPANSION", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["I2C_SDA_3V3", "I2C_SCL_3V3", "GPIO_EXP_INT", "BAT_HUMAN_GND"]},
    {"name": "EXTERNAL_EXPANSION", "domain": "BAT_HUMAN", "eda_policy": "forces_disabled", "pins": ["EXP_3V3", "EXP_UART_TX", "EXP_UART_RX", "EXTERNAL_EXPANSION_ATTACHED", "BAT_HUMAN_GND"]},
    {"name": "HAPTIC", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["HAPTIC_VDRV", "HAPTIC_CURRENT_EDGE", "BAT_HUMAN_GND"]},
    {"name": "MICROSD", "domain": "BAT_HUMAN", "eda_policy": "internal_only", "pins": ["SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_CLK", "SD_CMD", "BAT_HUMAN_GND"]},
]


class DesignManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads((ROOT / "hardware/design-manifest.json").read_text(encoding="utf-8"))
        cls.interfaces = json.loads((ROOT / "hardware/interfaces.json").read_text(encoding="utf-8"))

    def test_mainboard_sheet_set_is_exact(self):
        names = [sheet["name"] for sheet in self.design["boards"]["circle-main"]["sheets"]]
        self.assertEqual(names, EXPECTED_CIRCLE_MAIN_SHEETS)

    def test_ppg_sheet_set_is_exact(self):
        names = [sheet["name"] for sheet in self.design["boards"]["circle-ppg"]["sheets"]]
        self.assertEqual(names, EXPECTED_CIRCLE_PPG_SHEETS)

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

    def test_connector_contract_is_exact(self):
        self.assertEqual(self.interfaces["connectors"], EXPECTED_CONNECTORS)

    def test_lab_iso_ground_only_appears_on_lab_iso_connectors(self):
        for connector in self.interfaces["connectors"]:
            if "LAB_ISO_GND" in connector["pins"]:
                self.assertEqual(connector["domain"], "LAB_ISO")

    def test_lab_iso_connectors_never_expose_bat_human_ground(self):
        for connector in self.interfaces["connectors"]:
            if connector["domain"] == "LAB_ISO":
                self.assertNotIn("BAT_HUMAN_GND", connector["pins"])


class DesignManifestCheckerTest(unittest.TestCase):
    def test_validate_reports_missing_required_structure(self):
        errors = checker.validate({}, {})
        self.assertIn("design: missing or invalid boards", errors)
        self.assertIn("interfaces: missing or invalid connectors", errors)

    def test_validate_reports_non_dict_root_objects(self):
        errors = checker.validate([], [])
        self.assertIn("design: root must be an object", errors)
        self.assertIn("interfaces: root must be an object", errors)

    def test_main_reports_stable_error_for_unreadable_json(self):
        output = io.StringIO()
        with mock.patch("tools.check_design_manifest.json.loads", side_effect=json.JSONDecodeError("bad json", "x", 0)):
            with redirect_stdout(output):
                exit_code = checker.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(output.getvalue().splitlines(), ["ERROR: failed to read design/interface JSON"])


if __name__ == "__main__":
    unittest.main()
