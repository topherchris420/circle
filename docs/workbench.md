# CIRCLE workbench

The local workbench is a browser interface to CIRCLE's existing physiology twin,
report exporter, and independent auditor. It runs on your computer and needs no
account, API key, or external service. All sessions are simulations.

## Start

Use Python 3.11 or newer. From the repository directory:

```bash
python -m pip install -r requirements.txt
python tools/run_workbench.py
```

Your browser opens at `http://127.0.0.1:8765`. If it does not, open that address
yourself. Keep the terminal running while you use the workbench. Closing a browser
tab does not cancel a session; reopening the address restores its history.

For an isolated environment, create it first with `python -m venv .venv` and
activate it with `source .venv/bin/activate` on macOS/Linux or
`.\.venv\Scripts\Activate.ps1` in Windows PowerShell.

## Your first two sessions

1. Leave **A clear signal**, **Active**, seed **7**, and the matched comparison
   selected. Choose **Run session**. Six minutes of simulated time are generated
   as quickly as your computer allows; this is not a six-minute live recording.
2. Follow the simulation, comparison, export, and audit stages. One session runs
   at a time. **Cancel session** stops after the current stage; it does not
   interrupt a calculation or expose a partial report as complete.
3. Review the measurement checks and independent audit separately. Open the
   interactive report to inspect the traces and decision ledger.
4. Try **A loose sensor** with the same seed. Some measurement checks miss their
   targets even when the independent audit passes. The evidence preserves the
   measurement failure instead of hiding it behind a successful replay.

**Active** enables simulated haptic cues. **Sham** records decisions but withholds
those cues. A matched comparison runs the opposite arm with the same scenario
and seed. Its differences depend on the twin's assumed response model; they do
not establish a physiological benefit in people.

You can also open the committed example report from the sidebar before running
anything. It is labeled with the settings and evidence from that example, not
with settings from the current form.

## History and evidence

Each run receives a unique folder under `outputs/workbench/`. Running the same
settings again creates a new record. Search history by scenario, seed, arm, or
status; selecting a row restores its results. **Use these settings for a new
session** fills the form without automatically executing anything.

Download a ZIP containing the original export plus `audit.json`. Extract it to a
directory and independently audit it with:

```bash
python tools/audit_physiology_run.py path/to/extracted-bundle
```

The export's manifest hashes the simulation artifacts. `audit.json` is the
subsequent auditor result, kept outside the original manifest; it is not a signed
attestation. Rerun the auditor when checking a downloaded or modified bundle.
The workbench displays the audit performed when the run finished; it does not
continuously re-audit files changed afterward. A different pipeline version can
produce `VERSION_MISMATCH`, so preserve the recorded software revision.

An interrupted or cancelled run remains in history with its status and any
partial files on disk. Its report and bundle are unavailable through the UI.
After a restart, unfinished sessions are marked **Interrupted**; nothing is
automatically rerun. If you need disk space, stop the workbench and remove only
the individual run folders you no longer need.

## Options and troubleshooting

```bash
python tools/run_workbench.py --port 8766 --output outputs/my-sessions --no-browser
```

| Situation | What to do |
| --- | --- |
| Missing Python dependency | Run `python -m pip install -r requirements.txt` with the same Python used to launch the workbench. |
| Address already in use | Choose another port with `--port 8766`. |
| Output directory already in use | Close its other workbench, or use a separate `--output` directory. |
| Browser loses connection | Keep or restart the workbench terminal; the page reconnects automatically and refreshes its request token. |
| A session cannot finish | Read the saved error, check disk space and folder permissions, then reuse its settings to create a fresh run. |
| A measurement check misses its target | Inspect the check and scenario; this is distinct from a software exception or failed audit. |
| Shutting down takes a moment | Ctrl+C requests cancellation and waits for the current calculation stage before closing. |

The server binds only to IPv4 loopback, checks request hosts/origins, and requires
a per-launch token for starting or cancelling sessions. It is a local research
tool, not a multi-user hosted service. There are no upload, arbitrary-command,
hardware-control, or remote-sharing endpoints. Downloads are limited to completed
run artifacts. It adds no runtime dependencies beyond `requirements.txt`.

**ENGINEERING REVIEW ONLY.** This interface does not authorize fabrication or
human connection, and it does not connect the standalone consent gate to the
physiology controller. See [the evidence contract](closed-loop-evidence.md) and
[the consent integration contract](consent-by-design.md) for those boundaries.
