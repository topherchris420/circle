"""Build the evidence behind the CIRCLE marketing film.

The film in ``marketing/ad/`` is a rendering of things this repository actually
did, not an animation of things it might do. This tool produces every number,
label, hash, and trace the film shows:

1. Runs one fixed simulated session (``sensor_loss`` / seed 7 / active, audio
   consent executed through the gate) with the real workbench.
2. Builds its timeline document — the same one the Resonance Workbench renders.
3. Verifies the exported evidence with ``tools/verify_replication.py`` and
   records the verdict and its named checks.
4. Cuts short excerpts of the raw PPG / EDA / IMU streams from the export,
   including the declared gap where the pulse sensor stops answering.
5. Reads the recorded R.A.I.N. bridge run (``docs/rain-live-run-*.json``)
   unchanged; nothing about that run is recomputed or restated here.

It writes ``ad-data.js`` (the data) and ``workbench.html`` (the unmodified
Resonance Workbench shell, pointed at the repository's own assets and served
the recorded session by a fetch shim). The film embeds that page: the product
shots are the product.

Everything is simulated. No person is measured and no effect is claimed.

Usage: python tools/build_ad.py [--output marketing/ad]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.physiology.scenarios import SCENARIOS
from models.rain_connector import build_rain_protocol
from models.workbench import LABELS, Workbench, validate_settings
from tools.verify_replication import verify

ASSETS = ROOT / "models" / "workbench_assets" / "resonance"
AD_SCENARIO = "sensor_loss"
AD_SEED = 7
RAIN_RUN = ROOT / "docs" / "rain-live-run-2026-11-15.json"

# Raw-stream excerpts shown as traces (device time, seconds).
OPENING_WINDOW = (40.0, 54.0)      # quiet rest: a clean pulse wave
DROPOUT_WINDOW = (236.0, 276.0)    # spans the declared PPG gap
EXCERPT_HZ = 50.0


def _excerpt(path: Path, column: str, window: tuple[float, float], hz: float = EXCERPT_HZ) -> dict:
    """Decimated samples of one raw column inside a device-time window.

    Decimation keeps the first sample at or after each 1/hz step; gaps stay
    gaps (no interpolation), so a missing channel is visibly missing.
    """
    step_us = int(1e6 / hz)
    start_us, end_us = int(window[0] * 1e6), int(window[1] * 1e6)
    t, v = [], []
    next_us = start_us
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            time_us = int(row["device_time_us"])
            if time_us < next_us:
                continue
            if time_us > end_us:
                break
            t.append(round(time_us / 1e6, 3))
            v.append(int(row[column]))
            next_us = time_us - (time_us - start_us) % step_us + step_us
    return {"t_s": t, "v": v}


def _raw_excerpts(evidence: Path) -> dict:
    raw = evidence / "raw"
    out = {}
    for name, window in (("opening", OPENING_WINDOW), ("dropout", DROPOUT_WINDOW)):
        out[name] = {
            "window_s": list(window), "hz": EXCERPT_HZ,
            "ppg_ir": _excerpt(raw / "ppg.csv.gz", "ir_counts", window),
            "eda": _excerpt(raw / "eda.csv.gz", "code", window),
            "imu_ax": _excerpt(raw / "imu.csv.gz", "ax_lsb", window),
        }
    # The declared gap: the longest run without a PPG sample inside the dropout window.
    t = out["dropout"]["ppg_ir"]["t_s"]
    gaps = [(t[i + 1] - t[i], t[i], t[i + 1]) for i in range(len(t) - 1)]
    longest = max(gaps) if gaps else (0.0, 0.0, 0.0)
    out["ppg_gap_s"] = {"start": longest[1], "end": longest[2], "duration": round(longest[0], 3)}
    return out


def _commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _workbench_shell() -> str:
    """The Resonance Workbench page, unmodified except for where it loads from."""
    html = (ASSETS / "resonance.html").read_text(encoding="utf-8")
    base = "../../models/workbench_assets/resonance/"
    html = html.replace('href="/resonance.css"', f'href="{base}resonance.css"')
    html = html.replace('src="/resonance.js"', f'src="{base}resonance.js"')
    html = re.sub(r'src="/resonance/([a-z.-]+\.js)"', rf'src="{base}\1"', html)
    html = html.replace('href="/resonance"', 'href="#"').replace('href="/"', 'href="#"')
    marker = f'<script src="{base}resonance.js" defer></script>'
    if marker not in html:
        raise RuntimeError("resonance.html no longer loads resonance.js the way the film expects")
    return html.replace(marker, '<script src="ad-data.js" defer></script>\n'
                                '  <script src="workbench-shim.js" defer></script>\n  ' + marker)


def build_ad(output: Path) -> dict:
    settings = validate_settings({"scenario": AD_SCENARIO, "seed": AD_SEED, "arm": "active", "compare": False,
                                 "feedback": {"modalities": ["audio", "visual"], "max_gain": 0.5, "breath_bpm": 6.0},
                                 "consent": {"audio": True}})
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Workbench(Path(tmp))
        try:
            record = workbench.start(settings)
            workbench.worker.join()
            workbench.consent_audio(record["id"])
            run_record = workbench.get(record["id"])
            if run_record["status"] != "completed":
                raise RuntimeError("film session did not complete: " + str(run_record.get("error")))
            timeline = workbench.timeline(record["id"])
            evidence = workbench.artifact(record["id"], "manifest.json").parent
            manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
            verdict = verify(evidence)
            verdict.pop("directory", None)
            raw = _raw_excerpts(evidence)
            passport = (evidence / "passport.txt").read_text(encoding="utf-8")
            bundle_bytes = sum(meta["bytes"] for meta in manifest["artifacts"].values())
        finally:
            workbench.close()

    if verdict["verdict"] != "REPLAY_MATCH":
        raise RuntimeError("the film shows a matching replay; this build produced " + verdict["verdict"])

    rain = json.loads(RAIN_RUN.read_text(encoding="utf-8"))
    scenarios = [{"id": key, "title": LABELS[key][0], "category": LABELS[key][1], "description": LABELS[key][2],
                  "question": SCENARIOS[key].tests} for key in SCENARIOS]
    data = {
        "schema": "circle-ad-data/1",
        "note": "Every value here was produced by this repository: one simulated session, its verifier "
                "verdict, raw-stream excerpts from its export, and the recorded R.A.I.N. bridge run.",
        "commit": _commit(),
        "session": {"scenario": AD_SCENARIO, "title": LABELS[AD_SCENARIO][0], "seed": AD_SEED, "arm": "active"},
        "workbench": {
            "config": {"token": "film", "scenarios": scenarios, "output": "inside this page (recorded session)"},
            "runs": [run_record],
            "timeline": timeline,
        },
        "raw": raw,
        "bundle": {
            "name": f"circle-{run_record['id'][:8]}.zip",
            "artifact_bytes": bundle_bytes,
            "artifacts": [{"name": name, "bytes": meta["bytes"], "sha256": meta["sha256"]}
                          for name, meta in sorted(manifest["artifacts"].items())],
            "passport": passport,
        },
        "verdict": verdict,
        "rain": rain,
        "rain_source": RAIN_RUN.relative_to(ROOT).as_posix(),
        # The preregistered analysis plan of the protocol the bridge composes from R.A.I.N.'s choices.
        "rain_analysis_plan": build_rain_protocol(rain["rain_live"]["answers"], rain["seeds"], 0)["analysis_plan"],
    }

    output.mkdir(parents=True, exist_ok=True)
    (output / "ad-data.js").write_text(
        "window.CIRCLE_AD = " + json.dumps(data, allow_nan=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (output / "workbench.html").write_text(_workbench_shell(), encoding="utf-8")
    return {"output": str(output), "run_id": run_record["id"], "verdict": verdict["verdict"],
            "feedback_digest": timeline["feedback"]["digest"], "ppg_gap_s": raw["ppg_gap_s"]["duration"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "marketing" / "ad")
    args = parser.parse_args(argv)
    summary = build_ad(args.output)
    print(f"film data built: session {summary['run_id']} · verdict {summary['verdict']} · {summary['output']}")
    print(f"feedback digest: {summary['feedback_digest']}")
    print(f"declared PPG gap in the excerpt: {summary['ppg_gap_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
