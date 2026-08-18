import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parents[1]

class DiagramTests(unittest.TestCase):
    def test_mermaid_system_contains_required_terms(self):
        text = (ROOT / "diagrams/system-architecture.mmd").read_text(encoding="utf-8")
        for term in ("Human", "CIRCLE", "VitalSync", "DRR", "AdaptiveDecision", "Feedback"):
            self.assertIn(term, text)

    def test_mermaid_safety_contains_required_terms(self):
        text = (ROOT / "diagrams/safety-boundaries.mmd").read_text(encoding="utf-8")
        for term in ("BAT_HUMAN", "LAB_ISO", "USB_PRESENT", "DEBUG_ATTACHED", "EXTERNAL_EXPANSION_ATTACHED"):
            self.assertIn(term, text)

    def test_rendered_svgs_exist_and_warn(self):
        for name in ("system-architecture.svg", "safety-boundaries.svg"):
            path = ROOT / "diagrams" / name
            self.assertTrue(path.exists())
            self.assertIn("ENGINEERING REVIEW ONLY", path.read_text(encoding="utf-8"))
            ET.parse(path)

    def test_3d_animation_and_viewer_exist(self):
        gif_path = ROOT / "diagrams" / "circle-3d-animation.gif"
        html_path = ROOT / "diagrams" / "circle-3d-viewer.html"
        self.assertTrue(gif_path.exists())
        self.assertGreater(gif_path.stat().st_size, 10000)
        self.assertTrue(html_path.exists())
        self.assertIn("ENGINEERING REVIEW ONLY", html_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
