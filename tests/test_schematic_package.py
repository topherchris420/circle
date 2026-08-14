import json, pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
class SchematicPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.design=json.loads((ROOT/"hardware/design-manifest.json").read_text(encoding="utf-8"))
    def test_required_parts_and_gpio(self):
        parts={p["ref"]:p for p in self.design["parts"]}
        expected={"U1":"ESP32-S3-WROOM-1-N16R8","J1":"USB-C-USB2","U2":"BQ24074","U3":"TPS63070","U4":"TPS3700","U5":"TPS3700","U6":"MCP23017","J2":"LIPO_1S_NTC","F1":"USB_INPUT_FUSE","U10":"ADS1220","U11":"OPA2192","U12":"REF5020","U20":"ICM-42688-P","U30":"ISOW7742","U40":"DRV2605L","U101":"MAX30102","U102":"1V8_LOW_NOISE_LDO","U103":"I2C_LEVEL_TRANSLATOR","U104":"AT24CS02","U105":"LIS2DW12"}
        for ref,value in expected.items(): self.assertEqual(parts[ref]["value"],value)
        self.assertEqual(parts["U105"]["status"],"DNI")
        self.assertEqual(self.design["gpio_allocation"]["GPIO35"],"UNAVAILABLE_OCTAL_PSRAM")
        self.assertEqual(self.design["gpio_allocation"]["GPIO48"],"SYS_STATUS_INT_N")
    def test_eda_review_gates_and_no_heart_rate(self):
        parts={p["ref"]:p for p in self.design["parts"]}
        for ref in ("R_EDA_A1","R_EDA_A2","R_EDA_B1","R_EDA_B2"): self.assertEqual(parts[ref]["value"],"REVIEW_GATE:EDA_LIMIT_NETWORK")
        for ref in ("K1","K2"): self.assertEqual(parts[ref]["value"],"REVIEW_GATE:EDA_SWITCH_SELECTION")
        self.assertNotIn("HEART_RATE", (ROOT/"hardware/circle-ppg/legacy/00_ppg_root.sch").read_text(encoding="utf-8"))
    def test_all_generated_sheets_exist_and_are_review_marked(self):
        for board in ("circle-main","circle-ppg"):
            for sheet in self.design["boards"][board]["sheets"]:
                text=(ROOT/"hardware"/board/"legacy"/(sheet["name"]+".sch")).read_text(encoding="utf-8")
                self.assertIn("ENGINEERING REVIEW ONLY",text); self.assertTrue(text.endswith("$EndSCHEMATC\n"))
if __name__ == "__main__": unittest.main()
