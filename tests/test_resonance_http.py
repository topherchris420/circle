"""Resonance Workbench HTTP boundaries: routes, consent enforcement, timeline API."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import unittest

from models.workbench import Workbench, write_json
from tools.run_workbench import make_server

SETTINGS = {"scenario": "clean", "seed": 7, "arm": "active", "compare": False}
RUN_ID = "a" * 32


class ResonanceHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workbench = Workbench(Path(self.temporary.name))
        # A completed run backed by a real evidence bundle.
        from dataclasses import replace as _replace
        from models.physiology.experiment import run_session
        from models.physiology.scenarios import SCENARIOS
        from tools.run_physiology_twin import export_run
        directory = self.workbench.root / RUN_ID
        directory.mkdir()
        write_json(directory / "run.json", {"id": RUN_ID, "status": "completed", "settings": SETTINGS,
                   "created_at": "2026-01-01T00:00:00+00:00", "finished_at": None, "stage": "Finished",
                   "step": 5, "error": None,
                   "summary": {"scorecard": {"passed": 19, "total": 19}, "audit_valid": True}})
        run = run_session(_replace(SCENARIOS["clean"].configure(7), actuate=True))
        export_run(run, directory / "evidence", None)
        self.server = make_server(self.workbench, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        import http.client
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("GET", "/api/config")
        self.token = json.loads(connection.getresponse().read())["token"]
        connection.close()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.workbench.close()
        self.temporary.cleanup()

    def request(self, method, path, data=None, headers=None):
        import http.client
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        base = {"Content-Type": "application/json", "X-Circle-Token": self.token}
        status, body, _ = self.request_raw(connection, method, path, data, {**base, **(headers or {})})
        connection.close()
        return status, body

    def request_raw(self, connection, method, path, data, headers):
        connection.request(method, path, body=json.dumps(data).encode() if data is not None else None, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())

    def test_static_resonance_assets_are_served_locally(self):
        for route in ("/resonance", "/resonance.css", "/resonance.js", "/resonance/audio-engine.js",
                      "/resonance/synth.js", "/resonance/visual.js"):
            status, body = self.request("GET", route)
            self.assertEqual(status, 200, route)
            self.assertGreater(len(body), 200, route)

    def test_timeline_route_requires_a_completed_run(self):
        status, body = self.request("GET", f"/api/runs/{RUN_ID}/timeline")
        self.assertEqual(status, 200)
        document = json.loads(body)
        self.assertEqual(document["session"]["run_id"], RUN_ID)
        self.assertIn("feedback", document)
        status, _ = self.request("GET", "/api/runs/" + "b" * 32 + "/timeline")
        self.assertEqual(status, 404)

    def test_audio_consent_is_enforced_at_start(self):
        cases = [
            ({"feedback": {"modalities": ["audio", "visual"], "max_gain": 0.5, "breath_bpm": 6.0},
              "consent": {"audio": False}}, 400),  # audio without consent is refused
            ({"feedback": {"modalities": ["audio", "visual"], "max_gain": 0.5, "breath_bpm": 6.0},
              "consent": {"audio": True}}, 202),   # consented audio starts
            ({"feedback": {"modalities": ["audio"], "max_gain": 0.9, "breath_bpm": 6.0},
              "consent": {"audio": True}}, 400),   # unsafe gain refused
            ({"feedback": {"modalities": ["audio"], "max_gain": 0.5, "breath_bpm": 12.0},
              "consent": {"audio": True}}, 400),   # unsafe breathing rate refused
        ]
        run_ids = []
        for extra, expected in cases:
            settings = {**SETTINGS, "seed": 11, **extra}
            status, body = self.request("POST", "/api/runs", settings)
            self.assertEqual(status, expected, extra)
            if expected == 202:
                run_ids.append(json.loads(body)["id"])
        # Clean up started runs so tearDown is quiet.
        for run_id in run_ids:
            self.workbench.cancel(run_id)
            self.workbench.worker.join(60)
            self.workbench.get(run_id)

    def test_timeline_is_deterministic_across_requests(self):
        _, first = self.request("GET", f"/api/runs/{RUN_ID}/timeline")
        _, second = self.request("GET", f"/api/runs/{RUN_ID}/timeline")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
