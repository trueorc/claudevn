"""Decomposition service package (Layer 1) — v2.0 architecture.

Transforms ambiguous goals into formally specified, independent
work units with verification criteria. This is the primary value
driver of ClaudeVN v2.0.
"""

from .goal_analyzer import GoalAnalyzer, CodebaseAnalysis, FileInfo, ModuleBoundary
from .boundary_detector import BoundaryDetector, BoundaryAnalysis, IndependenceBoundary, FileOverlap
from .work_unit_builder import WorkUnitBuilder
from .spec_validator import SpecValidator, SpecValidationResult, ValidationIssue
from .context_assembler import ContextAssembler
from .environment_analyzer import EnvironmentAnalyzer

__all__ = [
    # Analysis
    "GoalAnalyzer",
    "CodebaseAnalysis",
    "FileInfo",
    "ModuleBoundary",
    # Boundaries
    "BoundaryDetector",
    "BoundaryAnalysis",
    "IndependenceBoundary",
    "FileOverlap",
    # Building
    "WorkUnitBuilder",
    # Validation
    "SpecValidator",
    "SpecValidationResult",
    "ValidationIssue",
    # Context
    "ContextAssembler",
    # Environment
    "EnvironmentAnalyzer",
]
