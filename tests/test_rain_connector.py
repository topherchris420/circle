"""The live R.A.I.N. connector: bounded choices, validated protocols, honest refusals."""

from __future__ import annotations
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from models.rain_connector import QUESTIONS, ask_rain, build_rain_protocol
from models.protocols import validate

SESSION = "c1c1e0000000000000000000000000f"


def envelope(selected: str | None, reason: str | None = None, attempts: list | None = None) -> bytes:
    return json.dumps({
        "schema": "rain-bethesda/v2", "kind": "proposal-choice", "request_id": "0" * 32,
        "decision": {"schema_version": "rain-bounded-decision/v1", "decision_id": "d-1",
                    "destination": "rain", "selected": selected, "reason": reason,
                    "envelope_hash": "f" * 64, "attempts": attempts or []},
    }).encode()


class FakeRainHandler(BaseHTTPRequestHandler):
    """Faithful to lop-nur-twin's /api/rain/proposal wire contract."""

    choices = {"cue_period_s": "opt_cue_period_s_11", "min_beat_coverage": "opt_min_beat_coverage_0_75",
               "scenario": "opt_scenario_interrupted"}

    def do_POST(self):
        import hashlib
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        assert set(body) == {"question", "options", "session", "request_id"}
        assert len(body["request_id"]) == 32
        # The connector sends md5("circle-" + key) as the request id.
        key = next(k for k in ("cue_period_s", "min_beat_coverage", "scenario")
                   if hashlib.md5(("circle-" + k).encode()).hexdigest() == body["request_id"])
        document = envelope(self.choices[key], "chosen by the engine",
                            [{"engine": "typesafe", "model": "jev-latest", "confidence": 0.9}])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(document)))
        self.end_headers()
        self.wfile.write(document)

    def log_message(self, *args):
        pass


class RainConnectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeRainHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_rain_chooses_among_the_hosts_options(self):
        result = ask_rain({}, self.url)
        for key, spec in QUESTIONS.items():
            self.assertIn(result["answers"][key], spec["values"])
        # Priority 2: the reasoning and the engines consulted are recorded.
        self.assertIn("chosen by the engine", result["reasoning"]["cue_period_s"]["reason"])
        self.assertEqual(result["attempts"]["cue_period_s"][0]["model"], "jev-latest")

    def test_choices_compose_into_a_valid_protocol(self):
        result = ask_rain({}, self.url)
        protocol = build_rain_protocol(result["answers"], [440, 441], 0)
        verdict = validate(protocol)
        self.assertEqual(verdict["status"], "VALID_FOR_SIMULATION", verdict["problems"])
        self.assertEqual(protocol["proposed_by"]["name"], "R.A.I.N. (lop-nur-twin live runtime)")
        self.assertEqual(protocol["intervention"]["cue_period_s"], 11)
        self.assertEqual(protocol["quality_gates"]["min_beat_coverage"], 0.75)
        self.assertEqual(protocol["scenario"], "interrupted")

    def test_a_declined_choice_is_reported_not_guessed(self):
        class Declining(FakeRainHandler):
            def do_POST(self):
                document = envelope(None, "DISABLED")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(document)))
                self.end_headers()
                self.wfile.write(document)
        server = HTTPServer(("127.0.0.1", 0), Declining)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(RuntimeError) as caught:
                ask_rain({}, f"http://127.0.0.1:{server.server_address[1]}")
            self.assertIn("DISABLED", str(caught.exception))
            self.assertIn("TYPESAFE_API_KEY", str(caught.exception))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_out_of_contract_choice_is_refused(self):
        class Wild(FakeRainHandler):
            def do_POST(self):
                document = envelope("opt_not_offered")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(document)))
                self.end_headers()
                self.wfile.write(document)
        server = HTTPServer(("127.0.0.1", 0), Wild)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(RuntimeError):
                ask_rain({}, f"http://127.0.0.1:{server.server_address[1]}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_unreachable_rain_is_reported_not_hidden(self):
        with self.assertRaises(RuntimeError):
            ask_rain({}, "http://127.0.0.1:1", timeout_s=2)


if __name__ == "__main__":
    unittest.main()
