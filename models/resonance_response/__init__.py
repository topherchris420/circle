"""CIRCLE Resonance Research Module.

Provides parametric resonator modeling, nonlinear spectral simulation,
closed-loop experimental optimization, and artifact-aware response analysis.
"""

from .simulator import ResonanceSimulator, GeometryConfig, ResonatorSubsystem, SimulationResult, CoupledOscillatorSolver, ConcentricMaxwellCapacitanceMatrix
from .closed_loop import ClosedLoopOptimizer, ExperimentSearchSpace, ExperimentalDecision, HypothesisCandidateLibrary, BlindTrialManifest, GaussianProcessRegressor, FactorialInteractionAnalyzer
from .analyzer import ResonanceAnalyzer, ResponseEvaluation, ArtifactReport, estimate_autocorrelation_time

__all__ = [
    "ResonanceSimulator",
    "GeometryConfig",
    "ResonatorSubsystem",
    "SimulationResult",
    "CoupledOscillatorSolver",
    "ConcentricMaxwellCapacitanceMatrix",
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
    "estimate_autocorrelation_time",
]
