"""Resonance Workbench assets: local-only, structured, and node-testable where available."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "models" / "workbench_assets" / "resonance"
FILES = ["resonance.html", "resonance.css", "resonance.js", "audio-engine.js", "synth.js", "visual.js", "phantom.js"]


class AssetStructureTest(unittest.TestCase):
    def test_all_assets_exist(self):
        for name in FILES:
            path = ASSETS / name
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 500, name)

    def test_assets_stay_local(self):
        """No external origins: the workbench never phones home."""
        for name in FILES:
            text = (ASSETS / name).read_text(encoding="utf-8")
            for match in re.findall(r"https?://[^\"'\s)<>]+", text):
                # W3C namespace URIs and data: favicons are identifiers, not fetches.
                self.assertTrue(re.match(r"https?://(www\.)?w3\.org/", match), f"{name}: {match}")

    def test_pure_scheduling_layer_has_no_audio_api(self):
        text = (ASSETS / "audio-engine.js").read_text(encoding="utf-8")
        self.assertNotIn("AudioContext", text)
        self.assertNotIn("webkitAudioContext", text)

    def test_synthesizer_enforces_the_ceiling(self):
        text = (ASSETS / "synth.js").read_text(encoding="utf-8")
        self.assertIn("ceiling", text)
        self.assertIn("DynamicsCompressor", text)

    def test_html_has_landmarks_and_reduced_motion_support(self):
        text = (ASSETS / "resonance.html").read_text(encoding="utf-8")
        for required in ('id="main"', 'aria-label="Workbench views"', 'class="skip"', "<noscript>",
                         'id="consent-audio"', 'id="audio-enable"', 'id="field-canvas"', 'id="evidence-detail"'):
            self.assertIn(required, text)
        css = (ASSETS / "resonance.css").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("@media (max-width: 980px)", css)

    def test_resonance_js_references_every_view_and_api(self):
        text = (ASSETS / "resonance.js").read_text(encoding="utf-8")
        # Views are switched by name through the shared "view-" prefix.
        self.assertIn('"view-" + v', text)
        for view in ("designer", "dashboard", "studio", "visual", "evidence", "phantom", "history"):
            self.assertIn(f'"{view}"', text)
        self.assertIn("/api/runs/${id}/timeline", text)
        self.assertIn("interpolateAt", text)

    def test_render_loop_never_reads_inputs_off_the_interpolated_point(self):
        """Regression: interpolateAt() returns parameters only, so `point.inputs.x` threw on
        the first frame and halted playback. Inputs come from the recorded feedback event."""
        engine = (ASSETS / "audio-engine.js").read_text(encoding="utf-8")
        interpolate = engine[engine.index("function interpolateAt"):engine.index("function breathPhase")]
        self.assertNotIn("inputs", interpolate)
        text = (ASSETS / "resonance.js").read_text(encoding="utf-8")
        self.assertNotIn("point.inputs", text)
        self.assertIn("feedbackInputsAt", text)


class AudioEngineNodeTest(unittest.TestCase):
    """Runs the node harness when node is available (CI images include it)."""

    @unittest.skipIf(shutil.which("node") is None, "node is not installed")
    def test_scheduling_engine_properties(self):
        result = subprocess.run(["node", str(ROOT / "tests" / "js" / "audio_engine_harness.js")],
                                capture_output=True, text=True, timeout=60, check=True)
        document = json.loads(result.stdout)
        self.assertTrue(document["deterministic"])
        self.assertTrue(document["empty_ok"])
        self.assertEqual(document["summary"]["events"], 3)
        self.assertEqual(document["summary"]["muted"], 1)
        self.assertLessEqual(document["clamped"]["level"], 0.4)
        self.assertGreaterEqual(document["clamped"]["breath_period_s"], 6.0)
        self.assertLessEqual(document["clamped"]["breath_period_s"], 15.0)
        self.assertLess(document["breath_phase"], 1.0)


if __name__ == "__main__":
    unittest.main()
