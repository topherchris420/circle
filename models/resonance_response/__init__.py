"""CIRCLE Resonance Research Module.

Provides parametric resonator modeling, nonlinear spectral simulation,
closed-loop experimental optimization, and artifact-aware response analysis.
"""

from .simulator import ResonanceSimulator, GeometryConfig, ResonatorSubsystem, SimulationResult, CoupledOscillatorSolver, GeometricParameterExtractor
from .closed_loop import ClosedLoopOptimizer, ExperimentSearchSpace, ExperimentalDecision, HypothesisCandidateLibrary, BlindTrialManifest, GaussianProcessRegressor, FactorialInteractionAnalyzer
from .analyzer import ResonanceAnalyzer, ResponseEvaluation, ArtifactReport

__all__ = [
    "ResonanceSimulator",
    "GeometryConfig",
    "ResonatorSubsystem",
    "SimulationResult",
    "CoupledOscillatorSolver",
    "GeometricParameterExtractor",
    "ClosedLoopOptimizer",
    "ExperimentSearchSpace",
    "ExperimentalDecision",
    "HypothesisCandidateLibrary",
    "BlindTrialManifest",
    "GaussianProcessRegressor",
    "FactorialInteractionAnalyzer",
    "ResonanceAnalyzer",
    "ResponseEvaluation",
    "ArtifactReport",
]
