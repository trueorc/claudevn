"""Work Planner models for Slim Claude Code.

Models for work planning - analyzing decomposed issues and creating
optimized execution plans with phases, parallelization, and risk assessment.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RiskSeverity(str, Enum):
    """Severity levels for plan risks."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanConstraints(BaseModel):
    """Constraints for work plan creation.

    Allows customizing plan generation based on available resources
    and user preferences.
    """
    max_parallel: Optional[int] = Field(
        default=None,
        description="Maximum concurrent issues to execute"
    )
    priority_override: Optional[List[str]] = Field(
        default=None,
        description="Force these issue temp_ids to be scheduled first"
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Target completion deadline"
    )
    excluded_skills: Optional[List[str]] = Field(
        default=None,
        description="Skills not available for this plan"
    )


class ExecutionPhase(BaseModel):
    """A phase in the execution plan.

    Groups issues that can be executed together, optionally in parallel.
    """
    phase_number: int = Field(..., description="Phase sequence number (1-indexed)")
    issues: List[str] = Field(
        default_factory=list,
        description="Issue temp_ids to execute in this phase"
    )
    parallel: bool = Field(
        default=True,
        description="Whether issues in this phase can run concurrently"
    )
    gate: Optional[str] = Field(
        default=None,
        description="Approval gate description before proceeding to next phase"
    )
    description: str = Field(
        default="",
        description="What this phase accomplishes"
    )


class PlanRisk(BaseModel):
    """A risk identified in the execution plan.

    Represents potential issues that could affect plan execution.
    """
    risk_id: str = Field(..., description="Unique risk identifier")
    description: str = Field(..., description="Description of the risk")
    severity: RiskSeverity = Field(
        default=RiskSeverity.MEDIUM,
        description="Risk severity level"
    )
    mitigation: str = Field(
        default="",
        description="Suggested mitigation strategy"
    )
    affected_issues: List[str] = Field(
        default_factory=list,
        description="Issue temp_ids affected by this risk"
    )


class WorkPlan(BaseModel):
    """An execution plan for decomposed issues.

    Contains phased execution strategy, critical path analysis,
    risk assessment, and optimization recommendations.
    """
    plan_id: str = Field(..., description="Unique plan identifier")
    goal_id: str = Field(..., description="Source goal ID")
    decomposition_id: str = Field(..., description="Source decomposition ID")
    phases: List[ExecutionPhase] = Field(
        default_factory=list,
        description="Ordered execution phases"
    )
    estimated_duration: str = Field(
        default="",
        description="Human-readable duration estimate"
    )
    critical_path: List[str] = Field(
        default_factory=list,
        description="Issue temp_ids on the critical path"
    )
    risks: List[PlanRisk] = Field(
        default_factory=list,
        description="Identified risks"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Optimization recommendations"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WorkPlanRequest(BaseModel):
    """Request to create an execution plan."""
    goal_id: str = Field(..., description="Reference to existing Goal")
    decomposition_id: str = Field(..., description="Reference to decomposition")
    constraints: Optional[PlanConstraints] = Field(
        default=None,
        description="Optional planning constraints"
    )


class WorkPlannerConfig(BaseModel):
    """Configuration for Work Planner service."""

    # Planning settings
    default_max_parallel: int = Field(
        default=5,
        description="Default maximum concurrent issues"
    )
    phase_gate_threshold: int = Field(
        default=5,
        description="Issues in a phase before requiring approval gate"
    )

    # Complexity to duration mapping (in hours)
    complexity_hours: Dict[str, float] = Field(
        default_factory=lambda: {
            "xs": 1.0,
            "s": 2.0,
            "m": 4.0,
            "l": 8.0,
            "xl": 16.0,
        },
        description="Estimated hours per complexity level"
    )

    # Risk thresholds
    high_dependency_threshold: int = Field(
        default=3,
        description="Dependencies count to flag as high-risk"
    )
    complex_issue_threshold: str = Field(
        default="l",
        description="Complexity level considered high-risk (l or xl)"
    )
