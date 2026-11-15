"""The live R.A.I.N. connector: bounded choices, validated protocols, honest fallbacks."""

from __future__ import annotations
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from models.rain_connector import QUESTIONS, ask_rain, build_rain_protocol
from models.protocols import validate


class FakeRainHandler(BaseHTTPRequestHandler):
    """A faithful stand-in for lop-nur-twin's /api/rain/proposal contract."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        chosen = {"cue_period_s": 11, "min_beat_coverage": 0.75, "scenario": "interrupted"}[body["session"]["question_key"]]
        document = json.dumps({"choice": chosen, "reason": "bounded choice among the host's options"}).encode()
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
            self.assertIn(result["answers"][key], spec["options"])
        self.assertIn("R.A.I.N.", result["provenance"]["proposer"])

    def test_choices_compose_into_a_valid_protocol(self):
        result = ask_rain({}, self.url)
        protocol = build_rain_protocol(result["answers"], [440, 441], 0)
        verdict = validate(protocol)
        self.assertEqual(verdict["status"], "VALID_FOR_SIMULATION", verdict["problems"])
        self.assertEqual(protocol["proposed_by"]["name"], "R.A.I.N. (lop-nur-twin live runtime)")
        self.assertEqual(protocol["intervention"]["cue_period_s"], 11)
        self.assertEqual(protocol["quality_gates"]["min_beat_coverage"], 0.75)
        self.assertEqual(protocol["scenario"], "interrupted")

    def test_out_of_contract_choice_is_refused(self):
        class Wild(FakeRainHandler):
            def do_POST(self):
                document = json.dumps({"choice": 99}).encode()
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
