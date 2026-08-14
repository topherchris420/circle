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
