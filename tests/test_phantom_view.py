"""Phantom evidence view: a known-input check, surfaced without losing provenance."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

from models.openbci_cyton import bridge as b
from models.phantom_view import PhantomView, build_phantom_document


def simulated_phantom(directory: Path) -> None:
    """Run the simulated-board phantom through the real bridge and exporter."""
    from tools.openbci_cyton import Scenario, SimulatedCyton, SimulatedPort, VirtualClock, simulated

    async def go():
        return await simulated(Scenario(seed=5), b.phantom_plan(), directory, "PHANTOM-TEST")

    asyncio.run(go())


class PhantomViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name) / "phantom"
        simulated_phantom(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_document_is_built_and_self_consistent(self):
        document = build_phantom_document(self.directory)
        self.assertEqual(document["schema"], "circle-phantom-evidence/1")
        self.assertEqual(document["provenance"], "SIMULATED")
        self.assertIn("simulated board", document["provenance_note"])
        checks = document["phantom"]["checks"]
        self.assertGreater(len(checks), 3)
        for check in checks:
            self.assertIn(check["status"], ("PASS", "FAIL", "REPORTED"))
        self.assertGreater(len(document["clock"]), 0)
        for entry in document["clock"]:
            self.assertIsNotNone(entry["rate_hz"])
        for key in ("analysis_sha256", "session_ndjson_sha256", "manifest_sha256"):
            self.assertTrue(document["artifacts"][key].startswith("sha256:"))

    def test_simulated_provenance_is_never_presented_as_hardware(self):
        document = build_phantom_document(self.directory)
        self.assertNotEqual(document["provenance"], "HARDWARE")
        self.assertIn("rehearsal", document["provenance_note"])

    def test_non_phantom_or_unknown_directories_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp)
            with self.assertRaises(FileNotFoundError):
                build_phantom_document(empty)
            # A directory with a manifest that claims unknown provenance.
            (empty / "manifest.json").write_text('{"provenance": "CLAIMED", "plan": {"mode": "PHANTOM"}}', encoding="utf-8")
            (empty / "analysis.json").write_text("{}", encoding="utf-8")
            (empty / "session.ndjson").write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_phantom_document(empty)

    def test_view_caches_then_refreshes(self):
        view = PhantomView(self.directory)
        first = view.document()
        second = view.document()
        self.assertIs(first, second)
        refreshed = view.refresh()
        self.assertIsNot(first, refreshed)
        self.assertEqual(first["phantom"]["verdict"], refreshed["phantom"]["verdict"])

    def test_document_is_deterministic(self):
        import json
        first = build_phantom_document(self.directory)
        second = build_phantom_document(self.directory)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
