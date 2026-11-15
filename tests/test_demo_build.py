"""The offline demo: a prerecorded session, served with nothing installed."""

from __future__ import annotations

import http.server
from html import unescape
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from tools.build_demo import build_demo
from tools.run_audio_rendering_benchmark import BROWSER_CANDIDATES

DEMO_FILES = ("index.html", "demo-data.js", "demo-shim.js", "resonance.css", "resonance.js",
              "audio-engine.js", "synth.js", "visual.js", "phantom.js")


def find_browser() -> str | None:
    for path in BROWSER_CANDIDATES:
        if Path(path).is_file():
            return path
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome") or None


class DemoBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name) / "demo"
        cls.summary = build_demo(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_demo_is_complete_and_self_contained(self):
        for name in DEMO_FILES:
            path = self.directory / name
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 100, name)

    def test_demo_uses_relative_assets_only(self):
        html = (self.directory / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('href="/resonance', html)
        self.assertNotIn('src="/resonance', html)
        for name in DEMO_FILES:
            if name.endswith((".js", ".css")):
                self.assertIn(name, html)

    def test_demo_is_labeled_as_simulation_and_offline(self):
        html = (self.directory / "index.html").read_text(encoding="utf-8")
        self.assertIn("OFFLINE DEMO", html)
        self.assertIn("SIMULATION ONLY", html)
        self.assertIn("prerecorded simulated session", html)

    def test_demo_data_holds_a_completed_consented_timeline(self):
        text = (self.directory / "demo-data.js").read_text(encoding="utf-8")
        self.assertIn("window.CIRCLE_DEMO", text)
        data = json.loads(text.split("= ", 1)[1].rstrip().rstrip(";"))
        run = data["runs"][0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["consent_record"]["state"], "EXECUTED")
        timeline = data["timeline"]
        self.assertEqual(timeline["session"]["run_id"], run["id"])
        self.assertTrue(timeline["session"]["feedback_consent"]["audio"])
        self.assertTrue(timeline["feedback"]["digest"].startswith("sha256:"))
        self.assertGreater(len(timeline["windows"]), 10)
        self.assertGreater(len(timeline["feedback"]["events"]), 20)

    def test_no_external_network_targets(self):
        for name in ("demo-shim.js", "resonance.js", "demo-data.js"):
            text = (self.directory / name).read_text(encoding="utf-8")
            for match in re.findall(r"https?://[^\"'\s)<>]+", text):
                self.assertTrue(re.match(r"https?://(www\.)?w3\.org/", match) or
                                match.startswith("https://github.com"), f"{name}: {match}")


class DemoBrowserTest(unittest.TestCase):
    """Serves the built demo statically and loads it in a real browser."""

    @classmethod
    def setUpClass(cls):
        cls.browser = find_browser()
        if cls.browser is None:
            raise unittest.SkipTest("no Chromium-family browser installed")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name) / "demo"
        build_demo(cls.directory)
        import functools
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(cls.directory))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server.server_close()
        if hasattr(cls, "thread"):
            cls.thread.join()
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_offline_page_serves_its_own_data(self):
        with socket.socket() as probe:
            debug_port = probe.bind(("127.0.0.1", 0)) or probe.getsockname()[1]
        process = subprocess.Popen(
            [self.browser, "--headless=new", "--disable-gpu", "--disable-extensions", "--no-first-run",
             f"--remote-debugging-port={debug_port}", f"http://127.0.0.1:{self.port}/index.html"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            import http.client
            deadline = time.monotonic() + 60
            title = None
            while time.monotonic() < deadline:
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", debug_port, timeout=5)
                    connection.request("GET", "/json/list")
                    targets = json.loads(connection.getresponse().read())
                    connection.close()
                except (OSError, json.JSONDecodeError):
                    time.sleep(0.5)
                    continue
                for target in targets:
                    if "index.html" in (target.get("url") or ""):
                        title = unescape(target.get("title") or "")
                if title and title.startswith("DEMO"):
                    break
                time.sleep(0.5)
            self.assertIsNotNone(title, "the demo page never reported")
            self.assertRegex(title, r"^DEMO \d+ API CALLS · READY$")
            calls = int(re.match(r"^DEMO (\d+)", title).group(1))
            self.assertGreaterEqual(calls, 3, "the interface made too few calls to have loaded its data")
        finally:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    unittest.main()
