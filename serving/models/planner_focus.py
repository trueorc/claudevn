"""Models for planner focus summary and goal alignment views.

Provides human-readable planner focus summaries and goal-to-execution
alignment metrics for frontend visualization.

Reference: Issue #528
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Planner Focus Summary Models
# =============================================================================


class WeightEntry(BaseModel):
    """A single ontology weight with display metadata."""
    key: str = Field(..., description="Ontology category key (e.g., 'feature', 'build')")
    weight: float = Field(..., ge=0.0, le=1.0, description="Weight value")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, low")
    label: str = Field(default="", description="Human-readable label for display")


class WeightCategory(BaseModel):
    """A category of ontology weights for display."""
    category: str = Field(..., description="Category name (e.g., 'work_type')")
    label: str = Field(..., description="Human-readable category label")
    weights: List[WeightEntry] = Field(default_factory=list)


class PolicyRuleSummary(BaseModel):
    """Simplified policy rule for display."""
    name: str
    description: str
    action: str = Field(..., description="Human-readable action description")
    confidence: str = Field(default="medium")
    enabled: bool = Field(default=True)
    source_goal_title: Optional[str] = Field(default=None)


class PlannerFocusSummary(BaseModel):
    """Human-readable summary of what the planner is optimizing for."""
    project_id: str
    has_profile: bool = Field(default=False, description="Whether an active profile exists")

    # Active preset info
    active_preset: Optional[str] = Field(
        default=None,
        description="Name of the active work profile preset"
    )
    active_preset_label: Optional[str] = Field(
        default=None,
        description="Human-readable label for the active preset"
    )
    active_preset_color: Optional[str] = Field(
        default=None,
        description="CSS color for the active preset"
    )

    # Human-readable description
    optimization_target: str = Field(
        default="No active profile",
        description="Human-readable description of current optimization target"
    )
    primary_intent: Optional[str] = Field(
        default=None,
        description="Dominant intent across active goals"
    )

    # Weight visualization data
    weight_categories: List[WeightCategory] = Field(
        default_factory=list,
        description="Ontology weights organized by category for visualization"
    )

    # Active policy rules
    active_rules: List[PolicyRuleSummary] = Field(
        default_factory=list,
        description="Currently active policy rules"
    )

    # Profile metadata
    active_goal_count: int = Field(default=0)
    profile_version: int = Field(default=0)
    last_updated: Optional[datetime] = Field(default=None)
    last_trigger: Optional[str] = Field(
        default=None,
        description="What caused the last profile update"
    )


# =============================================================================
# Goal Alignment Models
# =============================================================================


class AlignedWorkItem(BaseModel):
    """A work item aligned with a goal."""
    issue_id: str
    title: str
    status: str
    serves_multiple_goals: bool = Field(default=False)
    other_goal_ids: List[str] = Field(default_factory=list)


class GoalAlignmentEntry(BaseModel):
    """Alignment metrics for a single goal."""
    goal_id: str
    goal_title: str
    goal_status: str
    goal_priority: str
    primary_intent: Optional[str] = Field(default=None)

    # Alignment metrics
    total_issues: int = Field(default=0, description="Total issues for this goal")
    active_issues: int = Field(default=0, description="Issues currently in progress")
    completed_issues: int = Field(default=0, description="Issues completed")
    alignment_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of execution plan aligned with this goal"
    )

    # Gap detection
    has_gaps: bool = Field(default=False, description="Goal areas with no active work")
    gap_description: Optional[str] = Field(default=None)

    # Multi-goal items
    shared_work_items: List[AlignedWorkItem] = Field(
        default_factory=list,
        description="Work items serving this and other goals"
    )

    # Conflict indicators
    competing_goal_ids: List[str] = Field(
        default_factory=list,
        description="Goal IDs that compete with this one"
    )
    has_conflicts: bool = Field(default=False)


class GoalAlignmentSummary(BaseModel):
    """Complete goal alignment view for a project."""
    project_id: str
    total_goals: int = Field(default=0)
    total_issues: int = Field(default=0)
    overall_alignment: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Overall alignment percentage across all goals"
    )
    unaligned_issue_count: int = Field(
        default=0,
        description="Issues not linked to any goal"
    )
    goals: List[GoalAlignmentEntry] = Field(
        default_factory=list,
        description="Per-goal alignment entries"
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
