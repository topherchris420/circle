"""Workbench lifecycle, HTTP boundaries, and evidence-download contracts."""
from __future__ import annotations

import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from models.workbench import BusyError, Workbench, validate_settings, write_json
from tools.run_workbench import exclusive_directory, make_server

SETTINGS = {"scenario": "clean", "seed": 7, "arm": "active", "compare": True}


class WorkbenchFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workbench = Workbench(self.root)

    def tearDown(self):
        self.workbench.close()
        self.temporary.cleanup()

    def saved(self, status="completed"):
        run_id = "a" * 32
        directory = self.root / run_id
        directory.mkdir(exist_ok=True)
        write_json(directory / "run.json", {"id": run_id, "status": status, "settings": SETTINGS,
                   "created_at": "2026-01-01T00:00:00+00:00", "summary": {"scorecard": {"passed": 1, "total": 2},
                   "audit_valid": True}})
        return run_id, directory


class WorkbenchTest(WorkbenchFixture, unittest.TestCase):
    def test_settings_bound_the_workload_and_refuse_coercion(self):
        for changes in ({"seed": -1}, {"seed": True}, {"seed": 2**32}, {"seed": 1.5},
                        {"seed": "7"}, {"scenario": "../clean"}, {"compare": "false"},
                        {"arm": "hardware"}, {"duration": 100000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_settings({**SETTINGS, **changes})
        for invalid in (None, [], {}, "clean"):
            with self.assertRaises(ValueError):
                validate_settings(invalid)
        self.assertEqual(validate_settings({**SETTINGS, "seed": 0})["seed"], 0)

    def test_cancellation_prevents_export_and_duplicate_execution(self):
        entered, release = threading.Event(), threading.Event()

        def blocked_run(config):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test worker was not released")
            return object()

        with patch("models.workbench.run_session", blocked_run), patch("models.workbench.export_run") as exporter:
            run = self.workbench.start(SETTINGS)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(BusyError):
                    self.workbench.start(SETTINGS)
                self.assertEqual(self.workbench.cancel(run["id"])["status"], "cancelling")
            finally:
                release.set()
                self.workbench.worker.join(5)
            self.assertEqual(self.workbench.get(run["id"])["status"], "cancelled")
            self.assertIsNone(self.workbench.active)
            exporter.assert_not_called()
            with self.assertRaises(FileNotFoundError):
                self.workbench.artifact(run["id"], "report.html")

    def test_worker_failure_is_saved_and_a_retry_gets_a_new_id(self):
        with patch("models.workbench.run_session", side_effect=RuntimeError("test interruption")):
            first = self.workbench.start(SETTINGS)
            self.workbench.worker.join(5)
            self.assertEqual(self.workbench.get(first["id"])["status"], "failed")
            second = self.workbench.start(SETTINGS)
            self.workbench.worker.join(5)
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(len(self.workbench.history()), 2)

    def test_restart_marks_incomplete_runs_and_ignores_corrupt_metadata(self):
        run_id, _ = self.saved("running")
        bad = self.root / ("b" * 32)
        bad.mkdir()
        (bad / "run.json").write_text("[]")
        restarted = Workbench(self.root)
        self.assertEqual(restarted.get(run_id)["status"], "interrupted")
        self.assertEqual(len(restarted.history()), 1)
        self.assertIn("new session", restarted.get(run_id)["error"])

    def test_one_workbench_owns_an_output_directory(self):
        with exclusive_directory(self.root):
            with self.assertRaises(ValueError):
                with exclusive_directory(self.root):
                    self.fail("second owner acquired lock")
        with exclusive_directory(self.root):
            pass

    def test_artifact_traversal_and_symlink_escape_are_refused(self):
        run_id, directory = self.saved()
        evidence = directory / "evidence"
        evidence.mkdir()
        outside = self.root / "private.txt"
        outside.write_text("not an artifact")
        write_json(evidence / "manifest.json", {"artifacts": {"../../private.txt": {}, "escape.txt": {}}})
        with self.assertRaises(FileNotFoundError):
            self.workbench.artifact(run_id, "../../private.txt")
        try:
            (evidence / "escape.txt").symlink_to(outside)
        except OSError:
            self.skipTest("Symlinks unavailable")
        with self.assertRaises(FileNotFoundError):
            self.workbench.artifact(run_id, "escape.txt")
        with self.assertRaises(FileNotFoundError):
            self.workbench.directory("../private.txt")


class WorkbenchHTTPTest(WorkbenchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.workbench, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        _, body, _ = self.request("GET", "/api/config")
        self.token = json.loads(body)["token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        base = {"Content-Type": "application/json"}
        if hasattr(self, "token"):
            base["X-Circle-Token"] = self.token
        connection.request(method, path, body=json.dumps(data).encode() if data is not None else None,
                           headers={**base, **(headers or {})})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_other_websites_cannot_trigger_a_session_or_read_history(self):
        for headers in ({"Origin": "https://unrelated.example"}, {"Host": "unrelated.example"},
                        {"X-Circle-Token": "wrong"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("POST", "/api/runs", SETTINGS, headers)[0], 403)
        self.assertEqual(self.request("GET", "/api/runs", headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.workbench.history(), [])

    def test_invalid_requests_do_not_start_workers(self):
        self.assertEqual(self.request("POST", "/api/runs", {**SETTINGS, "seed": -1})[0], 400)
        self.assertEqual(self.request("GET", "/api/runs/not-a-run")[0], 404)
        self.assertEqual(self.request("GET", "/runs/../../requirements.txt")[0], 404)
        self.assertEqual(self.workbench.history(), [])

    def test_report_and_download_retain_failed_measurement_evidence(self):
        run_id, directory = self.saved()
        evidence = directory / "evidence"
        evidence.mkdir()
        (evidence / "report.html").write_text("<!doctype html><title>Test report</title>")
        write_json(evidence / "scorecard.json", {"passed": False})
        write_json(evidence / "manifest.json", {"artifacts": {"report.html": {}, "scorecard.json": {}}})
        write_json(directory / "audit.json", {"valid": True, "replay_status": "REPLAY_MATCH"})
        self.assertEqual(self.request("GET", f"/runs/{run_id}/report.html")[0], 200)
        status, body, headers = self.request("GET", f"/runs/{run_id}/bundle.zip")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(set(archive.namelist()), {"report.html", "scorecard.json", "manifest.json", "audit.json"})
            self.assertFalse(json.loads(archive.read("scorecard.json"))["passed"])
        compact = json.loads(self.request("GET", "/api/runs")[1])[0]
        self.assertTrue(compact["summary"]["audit_valid"])
        self.assertEqual(compact["summary"]["scorecard"], {"passed": 1, "total": 2})

    def test_static_workbench_and_example_are_self_contained(self):
        for route in ("/", "/app.js", "/app.css", "/example"):
            status, body, headers = self.request("GET", route)
            self.assertEqual(status, 200, route)
            self.assertGreater(len(body), 100)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.request("GET", "/requirements.txt")[0], 404)


if __name__ == "__main__":
    unittest.main()
