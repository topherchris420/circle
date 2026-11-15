"""Browser audio rendering benchmark: the real Web Audio engine, measured.

Uses the shared driver in tools/run_audio_rendering_benchmark.py to serve the
benchmark page to a real headless browser and read its result. Headless
rendering goes through the null audio sink, so these numbers describe the
browser's audio-graph behavior (start, progression, level, stop, clock
offset), not audible quality on physical speakers. Skipped when no browser is
installed.
"""

from __future__ import annotations

import http.client
from pathlib import Path
import tempfile
import threading
import unittest

from models.workbench import Workbench
from tools.run_audio_rendering_benchmark import find_browser, run_benchmark_page
from tools.run_workbench import make_server


class AudioRenderingBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.browser = find_browser()
        if cls.browser is None:
            raise unittest.SkipTest("no Chromium-family browser installed")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.workbench = Workbench(Path(cls.temporary.name))
        cls.server = make_server(cls.workbench, 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.workbench.close()
        cls.temporary.cleanup()

    def test_real_browser_renders_within_bounds(self):
        document = run_benchmark_page(self.browser, f"http://127.0.0.1:{self.port}/resonance/bench.html")
        self.assertEqual(document["schema"], "circle-audio-rendering-benchmark/1")
        self.assertTrue(document["context_running"], "AudioContext never reached running state")
        self.assertLess(document["start_latency_ms"], 3000)
        self.assertLessEqual(document["underruns"], 2,
                            f"audio clock stalled {document['underruns']} times during render")
        self.assertTrue(document["within_ceiling"], "rendered output exceeded the session ceiling")
        self.assertTrue(document["audible_output"], "engine rendered silence when it should sound")
        if document.get("audio_visual_sync_offset_ms") is not None:
            self.assertLess(abs(document["audio_visual_sync_offset_ms"]), 250,
                            "audio and wall clocks disagree by more than a quarter second")
        self.assertTrue(document["stop_settled"], "engine did not ramp to silence after stop()")

    def test_bench_page_is_served_with_the_synth(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("GET", "/resonance/bench.html")
        body = connection.getresponse().read()
        connection.close()
        self.assertIn(b"audio-engine.js", body)
        self.assertIn(b"synth.js", body)


if __name__ == "__main__":
    unittest.main()
