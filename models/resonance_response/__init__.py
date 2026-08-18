"""CIRCLE Resonance Research Module.

Provides parametric resonator modeling, nonlinear spectral simulation,
closed-loop experimental optimization, and artifact-aware response analysis.
"""

from .simulator import ResonanceSimulator, GeometryConfig, ResonatorSubsystem, SimulationResult, CoupledOscillatorSolver
from .closed_loop import ClosedLoopOptimizer, ExperimentSearchSpace, ExperimentalDecision, HypothesisCandidateLibrary, BlindTrialManifest
from .analyzer import ResonanceAnalyzer, ResponseEvaluation, ArtifactReport

__all__ = [
    "ResonanceSimulator",
    "GeometryConfig",
    "ResonatorSubsystem",
    "SimulationResult",
    "CoupledOscillatorSolver",
    "ClosedLoopOptimizer",
    "ExperimentSearchSpace",
    "ExperimentalDecision",
    "HypothesisCandidateLibrary",
    "BlindTrialManifest",
    "ResonanceAnalyzer",
    "ResponseEvaluation",
    "ArtifactReport",
]
