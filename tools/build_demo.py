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
SOCIAL_CARD = ROOT / "diagrams" / "social-card.png"
DEMO_SCENARIO = "clean"
DEMO_SEED = 7
REPO_URL = "https://github.com/topherchris420/circle"
PAGES_URL = "https://topherchris420.github.io/circle/"

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
  // Self-test (only with ?selftest in the URL, so visitors keep a real tab title):
  // report how many API calls the interface made and whether any script failed.
  if (!/[?&]selftest\\b/.test(window.location.search)) { return; }
  let served = 0;
  let uncaught = 0;
  window.addEventListener("error", function () { uncaught += 1; });
  window.addEventListener("unhandledrejection", function () { uncaught += 1; });
  const counting = window.fetch;
  window.fetch = function (url, options) {
    return counting(url, options).then(function (response) { served += 1; return response; });
  };
  window.addEventListener("load", function () {
    setTimeout(function () {
      const state = !window.CIRCLE_DEMO ? "BROKEN" : (uncaught ? uncaught + " UNCAUGHT ERRORS" : "READY");
      document.title = "DEMO " + served + " API CALLS · " + state;
    }, 3500);
  });
})();
"""


GUIDE = """/* CIRCLE demo guide: no instructions required.
 * Arrives on the dashboard with silent playback running (unless the visitor
 * prefers reduced motion), offers one click to hear the recorded adaptive
 * audio, and makes "inspect a decision" one click: it opens the Evidence view
 * on the first recorded decision.
 */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  function openView(name) {
    const tab = document.querySelector('.view-tab[data-view="' + name + '"]');
    if (tab) { tab.click(); }
  }
  function revealView(name) {
    const view = $("view-" + name);
    if (!view) { return; }
    const masthead = document.querySelector(".masthead");
    const sticky = masthead && getComputedStyle(masthead).position === "sticky" ? masthead.offsetHeight : 0;
    window.scrollTo({ top: Math.max(0, view.getBoundingClientRect().top + window.scrollY - sticky - 12), behavior: "smooth" });
  }
  ready(function () {
    // "Open the evidence": switch views and select the first recorded decision.
    document.querySelectorAll("[data-open-view]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        const name = link.dataset.openView;
        openView(name);
        if (name === "evidence") {
          const buttons = document.querySelectorAll("#evidence-list button");
          const decision = Array.prototype.find.call(buttons, function (b) {
            const kind = b.querySelector(".ev-kind");
            return kind && kind.textContent.indexOf("eval") !== 0;
          }) || buttons[0];
          if (decision) { decision.click(); }
        }
        revealView(name);
      });
    });

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
    const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setTimeout(function () {
      openView("dashboard");
      const play = $("play");
      if (!still && play && !play.disabled && play.textContent.indexOf("Play") !== -1) { play.click(); }
    }, 1800);
  });
})();
"""


DESCRIPTION = ("Replay a six-minute simulated physiology session in your browser: synchronized sensor charts, "
               "quality-gated decisions, adaptive audio, and the evidence behind every decision. "
               "Open source; nothing installed, nothing sent.")

# Share metadata and demo-only styles, placed in <head>. Link previews use the committed social card.
HEAD_EXTRA = f"""  <meta name="description" content="{DESCRIPTION}">
  <link rel="canonical" href="{PAGES_URL}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="CIRCLE">
  <meta property="og:title" content="CIRCLE · Resonance Workbench, live in your browser">
  <meta property="og:description" content="{DESCRIPTION}">
  <meta property="og:url" content="{PAGES_URL}">
  <meta property="og:image" content="{PAGES_URL}social-card.png">
  <meta property="og:image:width" content="1280">
  <meta property="og:image:height" content="640">
  <meta property="og:image:alt" content="CIRCLE: a human state is never one signal. The Resonance Workbench dashboard replaying a simulated session.">
  <meta name="twitter:card" content="summary_large_image">
  <style>
    .demo-intro {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 16px 32px; align-items: end;
      margin-bottom: 18px; border-left: 3px solid var(--teal); }}
    .demo-intro .lead {{ max-width: 74ch; }}
    .demo-steps {{ margin: 8px 0 0; padding-left: 1.3em; color: var(--ink-dim); display: grid; gap: 4px; max-width: 84ch; }}
    .demo-steps b {{ color: var(--ink); }}
    .demo-cta {{ display: flex; flex-direction: column; gap: 8px; min-width: 210px; }}
    .demo-cta p {{ margin: 2px 0 0; max-width: 28ch; }}
    .demo-button {{ display: block; text-align: center; text-decoration: none; padding: 10px 18px; border-radius: var(--radius);
      border: 1px solid var(--line); background: var(--panel-2); color: var(--ink); font-weight: 600; white-space: nowrap; }}
    .demo-button:hover {{ border-color: var(--teal-dim); }}
    .demo-button.primary {{ background: var(--teal); border-color: var(--teal); color: var(--bg); }}
    .demo-button:focus-visible {{ outline: 2px solid var(--teal); outline-offset: 2px; }}
    @media (max-width: 760px) {{
      .demo-intro {{ grid-template-columns: 1fr; }}
      .demo-more {{ display: none; }}
      .demo-cta {{ flex-direction: row; flex-wrap: wrap; }}
      .demo-cta .demo-button {{ flex: 1 1 140px; }}
    }}
  </style>"""

# Orientation for a first visit: what this is, three things to do, and where the source lives.
INTRO = f"""<section class="panel demo-intro" aria-labelledby="demo-intro-title">
        <div>
          <p class="eyebrow">OFFLINE DEMO · NOTHING INSTALLED · NOTHING SENT</p>
          <h2 id="demo-intro-title">What you are looking at</h2>
          <p class="lead">A prerecorded simulated session (clean · seed 7 · active): six minutes of a simulated
            person's pulse (PPG), skin conductance (EDA), and motion (IMU), the decisions made from them, and the
            adaptive sound those decisions allowed. No server, no sensors, no live data.</p>
          <ol class="demo-steps">
            <li><b>Watch.</b> The session replays second by second<span class="demo-more">. The top charts are what
              the instrument measured; <b>Sensor confidence</b> shows when the evidence was good enough to act on</span>.</li>
            <li><b>Listen.</b> Press <b>Hear this session</b><span class="demo-more"> once (browsers need a click
              before sound). The sound follows the recorded signals and holds when the evidence is impaired</span>.</li>
            <li><b>Inspect.</b> <a href="#view-evidence" data-open-view="evidence">Open the evidence</a><span
              class="demo-more">: every action shows its measurements, the rule that authorized it, and whether
              replay reproduces it</span>.</li>
          </ol>
        </div>
        <div class="demo-cta">
          <a class="demo-button primary" href="{REPO_URL}#quick-start">Run it locally</a>
          <a class="demo-button" href="{REPO_URL}">Source on GitHub ↗</a>
          <p class="quiet small">MIT licensed. Python 3.11+; no account, device, or API key.</p>
        </div>
      </section>"""


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
    # Data and fetch shim run before every other script, so no module can reach the network first.
    html = html.replace('<script src="audio-engine.js" defer></script>',
                       '<script src="demo-data.js" defer></script>\n'
                       '  <script src="demo-shim.js" defer></script>\n'
                       '  <script src="audio-engine.js" defer></script>', 1)
    html = html.replace("<title>CIRCLE · Resonance Workbench</title>",
                       "<title>CIRCLE · Resonance Workbench — offline demo</title>\n" + HEAD_EXTRA)
    html = html.replace('<span class="badge" id="arm-badge">SIMULATION ONLY</span>',
                       '<span class="badge" id="arm-badge">SIMULATION ONLY · OFFLINE DEMO</span>')
    # The local workbench links its classic view; the demo has none, so link the source instead.
    html = html.replace('<a class="quiet-link" href="index.html">Classic view ↗</a>',
                        f'<a class="quiet-link" href="{REPO_URL}">Source on GitHub ↗</a>')
    # Orientation lives in the page body, not the sticky masthead, so small screens keep their charts.
    html = html.replace('<div id="connection" class="notice" role="status" hidden></div>',
                        INTRO + '\n      <div id="connection" class="notice" role="status" hidden></div>', 1)
    html = html.replace('<script src="resonance.js" defer></script>',
                       '<script src="demo-guide.js" defer></script>\n  <script src="resonance.js" defer></script>')
    for marker in ("social-card.png", "demo-intro", 'quiet-link" href="' + REPO_URL):
        if marker not in html:
            raise RuntimeError(f"demo shell changed: could not place {marker!r}")
    (output / "index.html").write_text(html, encoding="utf-8")
    shutil.copyfile(SOCIAL_CARD, output / "social-card.png")
    (output / "demo-data.js").write_text(
        "window.CIRCLE_DEMO = " + json.dumps(demo_data, allow_nan=False) + ";\n", encoding="utf-8")
    (output / "demo-shim.js").write_text(SHIM, encoding="utf-8")
    (output / "demo-guide.js").write_text(GUIDE, encoding="utf-8")
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
