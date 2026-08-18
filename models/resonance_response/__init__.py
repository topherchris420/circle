"""CIRCLE Resonance Research Module.

Provides parametric resonator modeling, nonlinear spectral simulation,
closed-loop experimental optimization, and artifact-aware response analysis.
"""

from .simulator import ResonanceSimulator, GeometryConfig, ResonatorSubsystem, SimulationResult
from .closed_loop import ClosedLoopOptimizer, ExperimentSearchSpace, ExperimentalDecision
from .analyzer import ResonanceAnalyzer, ResponseEvaluation, ArtifactReport

__all__ = [
    "ResonanceSimulator",
    "GeometryConfig",
    "ResonatorSubsystem",
    "SimulationResult",
    "ClosedLoopOptimizer",
    "ExperimentSearchSpace",
    "ExperimentalDecision",
    "ResonanceAnalyzer",
    "ResponseEvaluation",
    "ArtifactReport",
]
