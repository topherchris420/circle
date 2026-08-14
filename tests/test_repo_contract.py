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
