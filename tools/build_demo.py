"""Build the static Resonance Workbench demo for GitHub Pages.

Runs one fixed simulated session, records its consent through the gate, builds
its timeline, and emits a fully offline ``demo/`` directory: the same
Resonance Workbench interface with a fetch shim serving the recorded data. A
visitor can play the session back, hear the adaptive audio, watch the visual
field, and inspect the evidence — with nothing installed and nothing sent
anywhere.

Everything is clearly labeled simulation. The recorded session is clean /
seed 7 / active with audio consent executed, so the demo is reproducible:
running the same scenario and seed locally recreates the same evidence.

Usage: python tools/build_demo.py [--output demo]
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS
from models.workbench import Workbench, validate_settings
from tools.run_physiology_twin import export_run

ASSETS = ROOT / "models" / "workbench_assets" / "resonance"
DEMO_SCENARIO = "clean"
DEMO_SEED = 7

SHIM = """/* CIRCLE offline demo shim: serves the recorded session to the workbench UI.
 * No network: every fetch the interface makes resolves from this page's data.
 */
(function () {
  "use strict";
  const data = window.CIRCLE_DEMO;
  const json = (value) => new Response(JSON.stringify(value), {"content-type": "application/json"});
  window.fetch = function (url, options) {
    const path = String(url);
    const suffix = (p) => path === p || path.endsWith(p) || path.split("?")[0] === p;
    if (options && options.method === "POST") {
      if (suffix("/api/runs")) { return Promise.resolve(json(data.runs[0])); }
      if (/\\/consent$/.test(path)) { return Promise.resolve(json({"state": "EXECUTED"})); }
      if (/\\/revoke$/.test(path)) { return Promise.resolve(json({"state": "REVOKED"})); }
      if (/\\/cancel$/.test(path)) { return Promise.resolve(json(data.runs[0])); }
    }
    if (suffix("/api/config")) { return Promise.resolve(json(data.config)); }
    if (suffix("/api/runs")) { return Promise.resolve(json(data.runs)); }
    if (/\\/timeline$/.test(path)) { return Promise.resolve(json(data.timeline)); }
    if (/\\/api\\/runs\\/[0-9a-f]{32}$/.test(path)) {
      return Promise.resolve(json(data.runs[0]));
    }
    if (suffix("/api/phantom")) {
      return Promise.resolve(new Response(JSON.stringify({"error": "offline demo"}), {"status": 404}));
    }
    return Promise.reject(new Error("offline demo: unexpected request " + path));
  };
  // Self-report: how many API calls the interface made against the recorded data.
  let served = 0;
  const counting = window.fetch;
  window.fetch = function (url, options) {
    return counting(url, options).then(function (response) { served += 1; return response; });
  };
  window.addEventListener("load", function () {
    setTimeout(function () {
      document.title = "DEMO " + served + " API CALLS · " + (window.CIRCLE_DEMO ? "READY" : "BROKEN");
    }, 2500);
  });
})();
"""


GUIDE = """/* CIRCLE demo guide: no instructions required.
 * Opens on the dashboard, starts silent playback, explains what each trace is,
 * and offers one click to hear the recorded adaptive audio. A first decision
 * is opened in the evidence explorer so "inspect a decision" is one tab away.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function () {
    // One explainer, in plain words, above everything.
    const intro = document.createElement("section");
    intro.className = "panel";
    intro.style.marginBottom = "14px";
    intro.innerHTML = "<h2>What you are looking at</h2>" +
      "<p class='lead'>A simulated person's <b>sensors</b> — heart pulse (PPG), skin conductance (EDA), and motion (IMU) — " +
      "replayed second by second. The <b>top charts</b> are what the instrument measured. " +
      "<b>Sensor confidence</b> shows when the evidence was good enough to act on. The <b>feedback engine</b> strip is " +
      "the sound level that was presented, held, and released.</p>" +
      "<p class='lead'><b>Listen:</b> click <b>Hear this session</b> once (browsers require one click before sound). " +
      "The sound follows the recorded signals — calmer stretches are quieter and darker, impaired evidence holds it. " +
      "<b>Inspect a decision:</b> open the <b>Evidence</b> tab; every action shows its measurements, its rule, and " +
      "whether replay reproduces it.</p>";
    const main = $("main");
    main.insertBefore(intro, main.firstChild);

    // One-click hearing: the only deliberate gesture a visitor needs.
    const hear = document.createElement("button");
    hear.className = "primary";
    hear.type = "button";
    hear.textContent = "\\u266B Hear this session";
    hear.style.marginRight = "10px";
    hear.addEventListener("click", function () {
      const enable = $("audio-enable");
      if (enable && !enable.disabled) { enable.checked = true; enable.dispatchEvent(new Event("change")); }
      const play = $("play");
      if (play && play.textContent.indexOf("Play") !== -1) { play.click(); }
      hear.textContent = "\\u266A Playing \\u2014 mute any time";
    });
    const bar = document.querySelector(".playback");
    if (bar) { bar.insertBefore(hear, bar.firstChild); }

    // Arrive already watching: dashboard view, silent playback running.
    setTimeout(function () {
      const tabs = document.querySelectorAll(".view-tab");
      const dash = Array.prototype.find.call(tabs, (t) => t.dataset.view === "dashboard");
      if (dash) { dash.click(); }
      const play = $("play");
      if (play && !play.disabled && play.textContent.indexOf("Play") !== -1) { play.click(); }
    }, 1800);
  });
})();
"""


def build_demo(output: Path) -> dict:
    settings = validate_settings({"scenario": DEMO_SCENARIO, "seed": DEMO_SEED, "arm": "active", "compare": False,
                                 "feedback": {"modalities": ["audio", "visual"], "max_gain": 0.5, "breath_bpm": 6.0},
                                 "consent": {"audio": True}})
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Workbench(Path(tmp))
        try:
            record = workbench.start(settings)
            workbench.worker.join()
            # Execute the recorded audio consent through the gate so the demo can sound.
            workbench.consent_audio(record["id"])
            run_record = workbench.get(record["id"])
            if run_record["status"] != "completed":
                raise RuntimeError("demo session did not complete: " + str(run_record.get("error")))
            timeline = workbench.timeline(record["id"])
            scenarios = [{"id": key, "title": label[0], "category": label[1], "description": label[2],
                          "question": scenario.tests}
                         for key, (label, scenario) in _labeled_scenarios().items()]
        finally:
            workbench.close()

    demo_data = {
        "config": {"token": "offline-demo", "scenarios": scenarios, "output": "inside this page (offline demo)"},
        "runs": [run_record],
        "timeline": timeline,
    }

    output.mkdir(parents=True, exist_ok=True)
    for name in ("resonance.css", "resonance.js", "audio-engine.js", "synth.js", "visual.js", "phantom.js"):
        shutil.copyfile(ASSETS / name, output / name)

    # Index: the resonance shell with relative asset paths, demo data, and the shim first.
    html = (ASSETS / "resonance.html").read_text(encoding="utf-8")
    html = html.replace('href="/resonance.css"', 'href="resonance.css"')
    html = html.replace('src="/resonance.js"', 'src="resonance.js"')
    html = html.replace('href="/resonance"', 'href="index.html"')
    html = html.replace('href="/"', 'href="index.html"')
    html = re.sub(r'src="/resonance/([a-z.-]+\.js)"', r'src="\1"', html)
    html = html.replace('<script src="resonance.js" defer></script>',
                       '<script src="demo-data.js" defer></script>\n'
                       '  <script src="demo-shim.js" defer></script>\n'
                       '  <script src="resonance.js" defer></script>')
    html = html.replace("<title>CIRCLE · Resonance Workbench</title>",
                       "<title>CIRCLE · Resonance Workbench — offline demo</title>")
    html = html.replace('<span class="badge" id="arm-badge">SIMULATION ONLY</span>',
                       '<span class="badge" id="arm-badge">SIMULATION ONLY · OFFLINE DEMO</span>')
    html = html.replace('<nav class="views" aria-label="Workbench views">',
                        '<div class="notice" role="status">This is a prerecorded simulated session '
                        '(clean · seed 7 · active). No server, no sensors, no live data. '
                        'Run <code>python tools/run_workbench.py</code> from the repository for live use.</div>\n'
                        '      <nav class="views" aria-label="Workbench views">')
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "demo-data.js").write_text(
        "window.CIRCLE_DEMO = " + json.dumps(demo_data, allow_nan=False) + ";\n", encoding="utf-8")
    (output / "demo-shim.js").write_text(SHIM, encoding="utf-8")
    (output / "demo-guide.js").write_text(GUIDE, encoding="utf-8")
    html = html.replace('<script src="resonance.js" defer></script>',
                       '<script src="demo-guide.js" defer></script>\n  <script src="resonance.js" defer></script>')
    return {"output": str(output), "run_id": run_record["id"],
            "feedback_digest": timeline["feedback"]["digest"],
            "bytes": sum(path.stat().st_size for path in output.rglob("*") if path.is_file())}


def _labeled_scenarios() -> dict:
    from models.workbench import LABELS
    return {key: (LABELS[key], SCENARIOS[key]) for key in SCENARIOS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "demo")
    args = parser.parse_args(argv)
    summary = build_demo(args.output)
    print(f"demo built: {summary['run_id']} · {summary['bytes']} bytes · {summary['output']}")
    print(f"feedback digest: {summary['feedback_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
