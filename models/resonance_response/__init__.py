"""CIRCLE Resonance Research Module.

Provides parametric resonator modeling, nonlinear spectral simulation,
closed-loop experimental optimization, and artifact-aware response analysis.
"""

from .simulator import ResonanceSimulator, GeometryConfig, ResonatorSubsystem, SimulationResult, CoupledOscillatorSolver, ConcentricSphericalCapacitanceModel
from .closed_loop import ClosedLoopOptimizer, ExperimentSearchSpace, ExperimentalDecision, HypothesisCandidateLibrary, BlindTrialManifest, GaussianProcessRegressor, FactorialInteractionAnalyzer, HierarchicalTrialEvaluator, get_student_t_critical_value, classify_condition_role
from .analyzer import ResonanceAnalyzer, ResponseEvaluation, ArtifactReport, estimate_autocorrelation_time

__all__ = [
    "ResonanceSimulator",
    "GeometryConfig",
    "ResonatorSubsystem",
    "SimulationResult",
    "CoupledOscillatorSolver",
    "ConcentricSphericalCapacitanceModel",
    "ClosedLoopOptimizer",
    "ExperimentSearchSpace",
    "ExperimentalDecision",
    "HypothesisCandidateLibrary",
    "BlindTrialManifest",
    "GaussianProcessRegressor",
    "FactorialInteractionAnalyzer",
    "HierarchicalTrialEvaluator",
    "get_student_t_critical_value",
    "classify_condition_role",
    "ResonanceAnalyzer",
    "ResponseEvaluation",
    "ArtifactReport",
    "estimate_autocorrelation_time",
]
