"""Local workbench orchestration; the physiology pipeline remains the authority.

One background worker owns execution. Only finished exports become downloadable.
Metadata is separate from the evidence manifest and written atomically so a closed
tab does not lose a run. Cancellation is cooperative at stage boundaries.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from uuid import uuid4

from models.physiology.audit import audit_run
from models.physiology.experiment import run_session
from models.physiology.scenarios import SCENARIOS
from tools.run_physiology_twin import export_run

ACTIVE = {"running", "cancelling"}
LABELS = {
    "clean": ("A clear signal", "Start here", "Follow a complete session from rest to recovery, with a matched control for comparison."),
    "motion_heavy": ("Movement & noise", "Signal quality", "See how typing and gestures affect the evidence available to the controller."),
    "poor_contact": ("A loose sensor", "Signal quality", "Explore what happens when skin contact and optical coupling deteriorate."),
    "timing_fault": ("When clocks drift", "Timing", "Challenge timestamp reconstruction with clock errors and delayed sensor delivery."),
    "sensor_loss": ("A missing channel", "Missing data", "Watch the controller respond when the pulse sensor disappears for 14 seconds."),
    "feedback_artifact": ("Feedback meets sensing", "Interference", "Test whether simulated haptic feedback contaminates the signals used to decide."),
    "ambiguous": ("Signals disagree", "Uncertainty", "Raise heart rate without an accompanying skin-conductance change."),
    "interrupted": ("Recovering the evidence", "Recovery", "Check how guidance resumes after motion briefly obscures a warranted state."),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def scenarios() -> list[dict]:
    return [{"id": key, "title": LABELS[key][0], "category": LABELS[key][1],
             "description": LABELS[key][2], "question": scenario.tests}
            for key, scenario in SCENARIOS.items()]


def validate_settings(data: object) -> dict:
    if not isinstance(data, dict) or set(data) != {"scenario", "seed", "arm", "compare"}:
        raise ValueError("Choose a scenario, seed, arm, and comparison setting.")
    if not isinstance(data["scenario"], str) or data["scenario"] not in SCENARIOS:
        raise ValueError("Choose one of the available scenarios.")
    if type(data["seed"]) is not int or not 0 <= data["seed"] <= 2**32 - 1:
        raise ValueError("Seed must be a whole number from 0 to 4294967295.")
    if data["arm"] not in ("active", "sham") or type(data["compare"]) is not bool:
        raise ValueError("Choose Active or Sham and whether to include a matched comparison.")
    return dict(data)


class BusyError(ValueError):
    """A bounded workbench runs one experiment at a time."""


class Cancelled(Exception):
    pass


class Workbench:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.worker: threading.Thread | None = None
        self.active: str | None = None
        self.cancel_requested = threading.Event()
        self.closing = False
        # A previous process may have stopped between writes. Never present its
        # partial bundle as complete or silently rerun it.
        for record in self.history():
            if record["status"] in ACTIVE:
                self._update(record["id"], status="interrupted", stage="Session interrupted",
                             finished_at=now(), error="The workbench stopped before this session finished. Run it again to create a new session.")

    def directory(self, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise FileNotFoundError("Session not found.")
        directory = self.root / run_id
        if directory.is_symlink() or not directory.is_dir():
            raise FileNotFoundError("Session not found.")
        return directory

    def get(self, run_id: str) -> dict:
        with self.lock:
            record = read_json(self.directory(run_id) / "run.json")
            if not isinstance(record, dict) or record.get("id") != run_id or record.get("status") not in (
                    *ACTIVE, "completed", "cancelled", "failed", "interrupted"):
                raise ValueError("Invalid saved session metadata.")
            validate_settings(record.get("settings"))
            if record["status"] == "completed" and not isinstance(record.get("summary"), dict):
                raise ValueError("Completed session has no result summary.")
            return record

    def history(self, *, compact: bool = False) -> list[dict]:
        records = []
        with self.lock:
            for path in self.root.glob("*/run.json"):
                try:
                    record = self.get(path.parent.name)
                    if compact and record.get("summary"):
                        record["summary"] = {key: record["summary"][key] for key in ("scorecard", "audit_valid")}
                    records.append(record)
                except (OSError, ValueError, KeyError):
                    continue
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)

    def _update(self, run_id: str, **changes: object) -> dict:
        with self.lock:
            record = self.get(run_id)
            record.update(changes)
            write_json(self.directory(run_id) / "run.json", record)
            return record

    def start(self, data: object) -> dict:
        settings = validate_settings(data)
        with self.lock:
            if self.active or self.closing:
                raise BusyError("A session is already running. Wait for it to finish or cancel it first.")
            run_id = uuid4().hex
            directory = self.root / run_id
            directory.mkdir()
            record = {"id": run_id, "settings": settings, "created_at": now(), "finished_at": None,
                      "status": "running", "stage": "Preparing the simulation", "step": 0,
                      "error": None, "summary": None}
            write_json(directory / "run.json", record)
            self.active = run_id
            self.cancel_requested.clear()
            self.worker = threading.Thread(target=self._run, args=(run_id, settings), name="circle-session")
            self.worker.start()
            return record

    def cancel(self, run_id: str) -> dict:
        with self.lock:
            record = self.get(run_id)
            if self.active == run_id and record["status"] in ACTIVE:
                self.cancel_requested.set()
                return self._update(run_id, status="cancelling", stage="Stopping after the current stage")
            return record

    def _stage(self, run_id: str, step: int, label: str) -> None:
        with self.lock:
            if self.cancel_requested.is_set():
                raise Cancelled()
            self._update(run_id, step=step, stage=label)

    def _run(self, run_id: str, settings: dict) -> None:
        try:
            config = replace(SCENARIOS[settings["scenario"]].configure(settings["seed"]),
                             actuate=settings["arm"] == "active")
            self._stage(run_id, 1, "Simulating six minutes of sensor data")
            run = run_session(config)
            opposite = None
            self._stage(run_id, 2, "Running the matched comparison" if settings["compare"] else "Preparing the evidence")
            if settings["compare"]:
                opposite = run_session(replace(config, actuate=not config.actuate))
            self._stage(run_id, 3, "Building the report and evidence bundle")
            output = self.directory(run_id) / "evidence"
            exported = export_run(run, output, opposite)
            self._stage(run_id, 4, "Independently reconstructing and auditing the session")
            audit = audit_run(output)
            write_json(self.directory(run_id) / "audit.json", audit)
            manifest = exported["manifest"]
            summary = {"scorecard": manifest["scorecard"], "audit_valid": audit["valid"],
                       "replay_status": audit["replay_status"],
                       "export_replay_status": manifest["decision_replay"]["status"],
                       "checks": exported["scorecard"]["checks"],
                       "audit_checks": audit["checks"],
                       "decisions": [{"time_s": round(e.device_time_us / 1e6, 1), "action": e.action}
                                     for e in run.evaluations if e.decision_id],
                       "pipeline_version": manifest["pipeline_version"],
                       "controller_version": manifest["controller_version"]}
            with self.lock:
                self._stage(run_id, 5, "Finished")
                self._update(run_id, status="completed", summary=summary, finished_at=now())
        except Cancelled:
            self._update(run_id, status="cancelled", stage="Cancelled", finished_at=now())
        except Exception as exc:
            self._update(run_id, status="failed", stage="Unable to finish this session", finished_at=now(),
                         error=f"{type(exc).__name__}: {exc}")
        finally:
            with self.lock:
                self.active = None

    def artifact(self, run_id: str, name: str) -> Path:
        record = self.get(run_id)
        if record["status"] != "completed":
            raise FileNotFoundError("This session has no completed export.")
        directory = self.directory(run_id)
        if name == "audit.json":
            path = directory / name
        else:
            output = directory / "evidence"
            allowed = set(read_json(output / "manifest.json")["artifacts"]) | {"manifest.json"}
            if name not in allowed:
                raise FileNotFoundError("Artifact not found.")
            path = output / name
        # Never follow a symlink out of the run, even if a local manifest changed.
        if not path.resolve().is_relative_to(directory) or not path.is_file():
            raise FileNotFoundError("Artifact not found.")
        return path

    def close(self) -> None:
        with self.lock:
            self.closing = True
            if self.active:
                self.cancel(self.active)
        if self.worker:
            self.worker.join()
