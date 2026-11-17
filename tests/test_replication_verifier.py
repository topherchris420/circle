"""Independent replication: verdicts for match, tamper, and missing evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import unittest

from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS
from tools.run_physiology_twin import export_run
from tools.verify_replication import verify
from tools.run_workbench import add_verification_support


class ReplicationVerifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name) / "run"
        run = run_session(replace(SCENARIOS["clean"].configure(7), actuate=True))
        export_run(run, cls.directory, None, with_report=False)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_a_faithful_package_replays(self):
        result = verify(self.directory)
        self.assertEqual(result["verdict"], "REPLAY_MATCH", result.get("problems"))
        self.assertIn("physical truth", result["note"])

    def test_tampering_is_an_integrity_failure_not_a_silent_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "run"
            copy.mkdir()
            for path in self.directory.rglob("*"):
                if path.is_file():
                    target = copy / path.relative_to(self.directory)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            raw = copy / "raw" / "ppg.csv.gz"
            raw.write_bytes(raw.read_bytes() + b"\x00")  # one appended byte
            result = verify(copy)
            self.assertEqual(result["verdict"], "INTEGRITY_FAILURE")
            self.assertTrue(any("ppg.csv.gz" in problem for problem in result["problems"]))

    def test_missing_evidence_is_named_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "run"
            copy.mkdir()
            for path in self.directory.rglob("*"):
                if path.is_file() and path.name != "analysis.json":
                    target = copy / path.relative_to(self.directory)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
            result = verify(copy)
            # Deleting a derived artifact leaves the raw truth intact: the verdict
            # must be a named failure mode, never a quiet success.
            self.assertIn(result["verdict"], ("INSUFFICIENT_EVIDENCE", "REPLAY_DIVERGENCE", "INTEGRITY_FAILURE"))
            self.assertTrue(result.get("problems") or result.get("replay_status"))

    def test_downloaded_bundle_replays_outside_checkout(self):
        """Extraction must replay from its own files, not the producer checkout."""
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "portable.zip"
            extracted = Path(tmp) / "external"
            extracted.mkdir()
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for source in self.directory.rglob("*"):
                    if source.is_file():
                        archive.write(source, source.relative_to(self.directory).as_posix())
                add_verification_support(archive)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extracted)
            result = subprocess.run(
                [sys.executable, "-I", str(extracted / "verify_replication.py"), str(extracted)],
                cwd=extracted, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("VERDICT: REPLAY_MATCH", result.stdout)

    def test_empty_directory_is_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = verify(Path(tmp))
            self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
