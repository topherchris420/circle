import unittest
from tools.kicad_legacy import Component, LegacySheet, Pin, ProjectSymbol
class LegacyEmitterTest(unittest.TestCase):
    def test_symbol_emits_pin_types_and_review_fields(self):
        text = ProjectSymbol("WINDOW_SUPERVISOR", [Pin("IN", "1", "I"), Pin("GOOD_N", "2", "C")]).emit()
        self.assertIn("X IN 1", text); self.assertIn("X GOOD_N 2", text)
    def test_sheet_emits_component_labels_and_end_marker(self):
        sheet = LegacySheet("EDA Safety"); sheet.add(Component("U1", "WINDOW_SUPERVISOR", 2000, 1500, "TPS3700")); sheet.label("USB_PRESENT", 1200, 1500)
        text = sheet.emit(); self.assertIn("EESchema Schematic File Version 4", text); self.assertIn("USB_PRESENT", text); self.assertTrue(text.endswith("$EndSCHEMATC\n"))
    def test_invariants_fail_closed(self):
        with self.assertRaises(ValueError): Pin("BAD", "", "I")
        with self.assertRaises(ValueError): Component("U1", "X", 12000, 10, "V")
        with self.assertRaises(ValueError): Component("U1", "X", 10, 10, "")
        sheet = LegacySheet("x"); sheet.add(Component("U1", "X", 10, 10, "REVIEW_GATE:VALUE"))
        with self.assertRaises(ValueError): sheet.add(Component("U1", "X", 20, 20, "V"))
        with self.assertRaises(ValueError): sheet.label("BAD LABEL", 10, 10)
if __name__ == "__main__": unittest.main()
