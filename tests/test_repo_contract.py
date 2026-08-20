import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_README_OPENING = """# CIRCLE Rev A

> **ENGINEERING REVIEW ONLY** — Experimental research hardware. This repository is not approved for fabrication or human connection and does not establish medical-device, electrical-safety, EMC, or measurement-performance claims.

The repository contains the architecture diagrams, safety contracts, validation documents, and KiCad 10 schematics for the CIRCLE Rev A bench validation platform.
"""


class RepoContractTest(unittest.TestCase):
    def test_toolchain_and_release_warning_are_pinned(self):
        toolchain = json.loads((ROOT / "toolchain.json").read_text(encoding="utf-8"))
        self.assertEqual(toolchain["kicad"], "10.0.5")
        self.assertEqual(toolchain["python_min"], "3.11")

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.lower().startswith("# circle"))
        self.assertIn("ENGINEERING REVIEW ONLY", readme)


if __name__ == "__main__":
    unittest.main()
