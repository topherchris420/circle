"""CIRCLE physiology twin, Rev B signal pipeline, closed-loop controller, and evidence audit.

Everything in this package is simulation and software. It never drives
hardware, and its twin is not a model of any person. See
docs/physiology-pipeline.md for methods, scoring conventions, and limitations.

Typical use:

    from models.physiology import SessionConfig, run_session, score

    run = run_session(SessionConfig())
    card = score(run, run.truth())
"""

from .audit import audit_run
from .controller import ClosedLoopController, ControllerConfig, replay
from .experiment import SessionConfig, SessionRun, run_session
from .pipeline import PIPELINE_VERSION, analyze
from .sensors import RigConfig
from .twin import TwinConfig
from .validation import score

__all__ = [
    "PIPELINE_VERSION",
    "ClosedLoopController",
    "ControllerConfig",
    "RigConfig",
    "SessionConfig",
    "SessionRun",
    "TwinConfig",
    "analyze",
    "audit_run",
    "replay",
    "run_session",
    "score",
]
