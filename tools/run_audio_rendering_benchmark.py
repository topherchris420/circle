"""Run the browser audio rendering benchmark and record its result.

Serves the workbench's benchmark page to the installed Chromium-family browser
in headless mode and records what the real Web Audio engine measured: context
start latency, output-timestamp progression (underruns), rendered output
level against the session ceiling, stop ramp-down, and audio-clock to
wall-clock offset. The page runs in real time (no virtual clock), because an
audio benchmark needs a running audio clock.

Headless output goes through the browser's null audio sink: the result
describes the browser's audio-graph behavior on this machine, not audible
quality on physical speakers.

Usage: python tools/run_audio_rendering_benchmark.py [--output docs/audio-rendering-benchmark.json]
"""

from __future__ import annotations

import argparse
import http.client
from html import unescape
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_browser() -> str | None:
    for path in BROWSER_CANDIDATES:
        if Path(path).is_file():
            return path
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome") or None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_benchmark_page(browser: str, url: str, timeout_s: float = 90) -> dict:
    """Serve the bench page to a real headless browser; return its result document."""
    with tempfile.TemporaryDirectory(prefix="circle-audio-browser-") as profile:
        return _render_in_browser(browser, url, timeout_s, profile)


def _render_in_browser(browser: str, url: str, timeout_s: float, profile: str) -> dict:
    debug_port = free_port()
    process = subprocess.Popen(
        [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--disable-extensions", "--autoplay-policy=no-user-gesture-required",
         "--no-sandbox", "--disable-dev-shm-usage",  # CI containers require these.
         f"--user-data-dir={profile}", f"--remote-debugging-port={debug_port}", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"benchmark browser exited with status {process.returncode}")
            try:
                connection = http.client.HTTPConnection("127.0.0.1", debug_port, timeout=5)
                connection.request("GET", "/json/list")
                targets = json.loads(connection.getresponse().read())
                connection.close()
            except (OSError, json.JSONDecodeError):
                time.sleep(0.5)
                continue
            for target in targets:
                # The DevTools list endpoint HTML-escapes titles; undo that.
                title = unescape(target.get("title") or "")
                if title.startswith("BENCH-DONE "):
                    return json.loads(title[len("BENCH-DONE "):])
            time.sleep(0.5)
        raise TimeoutError("the benchmark page did not report a result in time")
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "audio-rendering-benchmark.json")
    args = parser.parse_args(argv)
    browser = find_browser()
    if browser is None:
        print("No Chromium-family browser found; nothing to measure.", file=sys.stderr)
        return 1
    from models.workbench import Workbench
    from tools.run_workbench import make_server
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Workbench(Path(tmp))
        server = make_server(workbench, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            document = run_benchmark_page(browser, f"http://127.0.0.1:{server.server_address[1]}/resonance/bench.html")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            workbench.close()
    document["browser"] = Path(browser).name
    document["note"] = ("Headless render through the browser's null audio sink on one machine; describes the "
                       "browser's audio-graph behavior, not audible quality on physical speakers, and not "
                       "behavior on other devices.")
    args.output.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"start {document.get('start_latency_ms')} ms · underruns {document.get('underruns')} · "
          f"peak RMS {document.get('peak_output_rms')} · stop settled {document.get('stop_settled')}")
    print(f"Report: {args.output}")
    ok = (document.get("context_running") and document.get("within_ceiling") and document.get("audible_output")
          and document.get("stop_settled") and document.get("underruns", 99) <= 2
          and document.get("start_latency_ms", 1e9) < 3000)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
