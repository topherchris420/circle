"""Standalone replication: a downloaded bundle verifies outside the CIRCLE repository.

The README promises that every downloaded evidence bundle ships ``verify_replication.py`` and that
anyone can run it. Until this test existed, the script imported ``models.physiology.audit`` from the
repository, so outside a checkout it crashed with ``ModuleNotFoundError`` before naming any verdict.

Each test assembles a bundle the way a stranger receives one (evidence, verifier, and the shipped
``circle-replay/`` reconstruction code) in a directory outside the repository, then runs the
verifier in a fresh interpreter in isolated mode, so nothing from this checkout can leak in.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS
from tools.run_physiology_twin import export_run
from tools.verify_replication import KIT_DIR, replay_kit

ROOT = Path(__file__).resolve().parents[1]


def stranger_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class StandaloneReplicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.export = Path(cls.temporary.name) / "export"
        run = run_session(replace(SCENARIOS["clean"].configure(7), actuate=True))
        export_run(run, cls.export, None, with_report=False)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def bundle(self, with_kit: bool = True) -> Path:
        """A fresh copy of the bundle, outside the repository, as a stranger extracts it."""
        place = Path(tempfile.mkdtemp(dir=self.temporary.name)) / "circle-bundle"
        shutil.copytree(self.export, place)
        shutil.copy(ROOT / "tools" / "verify_replication.py", place / "verify_replication.py")
        if with_kit:
            for arcname, content in replay_kit():
                target = place / arcname
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        self.assertFalse(str(place.resolve()).startswith(str(ROOT)), "the bundle must live outside the repo")
        return place

    def run_verifier(self, place: Path, *args: str, flags: tuple[str, ...] = ("-I",)):
        return subprocess.run([sys.executable, *flags, "verify_replication.py", ".", *args], cwd=place,
                              capture_output=True, text=True, timeout=300, env=stranger_env())

    def test_a_bundle_replays_outside_the_repository(self):
        done = self.run_verifier(self.bundle(), "--json", "verdict.json")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("VERDICT: REPLAY_MATCH", done.stdout)
        self.assertIn("shipped with this bundle", done.stdout)
        self.assertNotIn("Traceback", done.stderr)

    def test_the_verdict_names_the_code_that_rebuilt_it(self):
        place = self.bundle()
        self.run_verifier(place, "--json", "verdict.json")
        verdict = json.loads((place / "verdict.json").read_text(encoding="utf-8"))
        code = verdict["reconstruction_code"]
        self.assertEqual(code["source"], "bundle")
        self.assertTrue(code["pipeline_source"].startswith("sha256:"))
        manifest = json.loads((place / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(code["pipeline_source"], manifest["pipeline_source"])

    def test_altered_reconstruction_code_cannot_pass(self):
        place = self.bundle()
        pipeline = place / KIT_DIR / "models" / "physiology" / "pipeline.py"
        pipeline.write_text(pipeline.read_text(encoding="utf-8") + "\n# altered\n", encoding="utf-8")
        done = self.run_verifier(place)
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("VERDICT: REPLAY_DIVERGENCE", done.stdout)

    def test_without_reconstruction_code_the_verdict_is_named_not_a_crash(self):
        done = self.run_verifier(self.bundle(with_kit=False))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("VERDICT: INSUFFICIENT_EVIDENCE", done.stdout)
        self.assertIn("--circle-root", done.stdout)
        self.assertNotIn("Traceback", done.stderr)

    def test_missing_python_packages_are_named_with_the_install_command(self):
        # -S drops site-packages, so numpy and jsonschema are unavailable, as on a bare Python.
        done = self.run_verifier(self.bundle(), flags=("-I", "-S"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("VERDICT: INSUFFICIENT_EVIDENCE", done.stdout)
        self.assertIn("pip install -r circle-replay/REQUIREMENTS.txt", done.stdout)
        self.assertIn("every recorded SHA-256 matches", done.stdout)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_skeptic_can_rebuild_with_their_own_checkout(self):
        done = self.run_verifier(self.bundle(with_kit=False), "--circle-root", str(ROOT))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("VERDICT: REPLAY_MATCH", done.stdout)
        self.assertIn("--circle-root", done.stdout)

    def test_the_kit_is_complete_and_declares_its_requirements(self):
        names = {arcname for arcname, _ in replay_kit()}
        for required in ("models/physiology/audit.py", "models/session_records.py",
                         "contracts/session-record.schema.json", "hardware/review-gates.json",
                         "REQUIREMENTS.txt", "SOURCE.json"):
            self.assertIn(f"{KIT_DIR}/{required}", names)
        requirements = dict(replay_kit())[f"{KIT_DIR}/REQUIREMENTS.txt"].decode("utf-8")
        self.assertIn("numpy", requirements)
        self.assertIn("jsonschema", requirements)
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))


class WorkbenchBundleTest(unittest.TestCase):
    """End to end: a real workbench session, downloaded as bundle.zip, verified by a stranger."""

    def test_a_downloaded_bundle_zip_verifies_outside_the_repository(self):
        import http.client
        import io
        import threading
        import time
        import zipfile
        from models.workbench import Workbench
        from tools.run_workbench import make_server

        with tempfile.TemporaryDirectory() as tmp:
            workbench = Workbench(Path(tmp) / "runs")
            server = make_server(workbench, 0)
            threading.Thread(target=server.serve_forever, daemon=True).start()

            def request(method, path, data=None, token=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
                headers = {"Content-Type": "application/json", **({"X-Circle-Token": token} if token else {})}
                connection.request(method, path, json.dumps(data).encode() if data is not None else None, headers)
                response = connection.getresponse()
                body = response.read()
                connection.close()
                return response.status, body

            try:
                token = json.loads(request("GET", "/api/config")[1])["token"]
                status, body = request("POST", "/api/runs", {"scenario": "clean", "seed": 7, "arm": "active",
                                                             "compare": False}, token)
                self.assertEqual(status, 202, body)
                run_id = json.loads(body)["id"]
                deadline = time.monotonic() + 240
                while json.loads(request("GET", f"/api/runs/{run_id}", token=token)[1])["status"] != "completed":
                    self.assertLess(time.monotonic(), deadline, "the session did not finish")
                    time.sleep(0.5)
                status, archive = request("GET", f"/runs/{run_id}/bundle.zip", token=token)
                self.assertEqual(status, 200)
            finally:
                server.shutdown()
                server.server_close()
                workbench.close()

            place = Path(tmp) / "downloads" / "circle-bundle"
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                bundle.extractall(place)
            done = subprocess.run([sys.executable, "-I", "verify_replication.py", "."], cwd=place,
                                  capture_output=True, text=True, timeout=300, env=stranger_env())
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("VERDICT: REPLAY_MATCH", done.stdout)
            self.assertIn("shipped with this bundle", done.stdout)


if __name__ == "__main__":
    unittest.main()
