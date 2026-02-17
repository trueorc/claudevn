"""Decision traceability models for planning decision logging.

Defines the schema for recording meaningful planning decisions and the
reasoning behind them. The system maintains decision-point traceability:
a structured log of decisions covering profile shifts, bucket reorganizations,
task movements, conflict resolutions, and worker assignments.

Each trace entry captures: what triggered the decision, the context at the
time, what changed, the key factors driving the decision, and the downstream
impact scope.

Reference: docs/work_management_framework.md — Section 11
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DecisionPointType(str, Enum):
    """Types of planning decisions that warrant tracing.

    Each type corresponds to a meaningful planning decision point
    where the system should be able to answer "why" if asked.
    """
    PROFILE_SHIFT = "profile_shift"
    BUCKET_REORGANIZATION = "bucket_reorganization"
    TASK_MOVEMENT = "task_movement"
    CONFLICT_IDENTIFIED = "conflict_identified"
    CONFLICT_RESOLVED = "conflict_resolved"
    WORKER_ASSIGNMENT = "worker_assignment"


class DecisionTrigger(BaseModel):
    """What initiated a planning decision.

    Captures the event or condition that caused the planner to make
    a decision, with references to the source entities.
    """
    trigger_type: str = Field(
        ...,
        description="Category of trigger (e.g., 'new_goal', 'worker_feedback', 'resource_change', 'items_completed')"
    )
    source_id: str = Field(
        default="",
        description="ID of the entity that triggered the decision (goal_id, worker_id, etc.)"
    )
    source_type: str = Field(
        default="",
        description="Type of the source entity (e.g., 'goal', 'feedback_signal', 'resource')"
    )
    description: str = Field(
        default="",
        description="Human-readable description of what triggered the decision"
    )


class DecisionContext(BaseModel):
    """Relevant state at the time a decision was made.

    Captures enough context to understand the decision without
    replaying the full system state.
    """
    profile_version: Optional[int] = Field(
        default=None,
        description="Active planner profile version at decision time"
    )
    profile_id: Optional[str] = Field(
        default=None,
        description="Active planner profile ID"
    )
    bucket_tree_version: Optional[int] = Field(
        default=None,
        description="Bucket tree version at decision time"
    )
    active_goal_ids: List[str] = Field(
        default_factory=list,
        description="Goal IDs active at decision time"
    )
    active_worker_count: Optional[int] = Field(
        default=None,
        description="Number of active compute instances"
    )
    additional: Dict[str, Any] = Field(
        default_factory=dict,
        description="Decision-type-specific context data"
    )


class DecisionImpact(BaseModel):
    """Downstream effects of a planning decision.

    Describes what changed as a result of the decision, including
    affected items, buckets, and any cascading effects.
    """
    affected_item_ids: List[str] = Field(
        default_factory=list,
        description="Work item IDs affected by this decision"
    )
    affected_bucket_ids: List[str] = Field(
        default_factory=list,
        description="Bucket IDs affected by this decision"
    )
    profile_version_before: Optional[int] = Field(
        default=None,
        description="Profile version before the decision"
    )
    profile_version_after: Optional[int] = Field(
        default=None,
        description="Profile version after the decision"
    )
    tree_version_before: Optional[int] = Field(
        default=None,
        description="Bucket tree version before the decision"
    )
    tree_version_after: Optional[int] = Field(
        default=None,
        description="Bucket tree version after the decision"
    )
    cascading_effects: List[str] = Field(
        default_factory=list,
        description="Human-readable descriptions of downstream effects"
    )


class DecisionTrace(BaseModel):
    """Complete trace of a planning decision.

    The primary traceability record. Captures the full decision chain:
    trigger -> context -> decision -> key factors -> impact.

    Used for:
    - Users: Understanding why work is parked, deprioritized, or conflicting
    - Planner: Self-awareness and institutional memory
    - Debugging: Primary tool for understanding planning quality
    """
    trace_id: str = Field(..., description="Unique trace identifier")
    project_id: str = Field(..., description="Project this decision belongs to")
    decision_type: DecisionPointType = Field(
        ...,
        description="Classification of the decision point"
    )
    trigger: DecisionTrigger = Field(
        ...,
        description="What initiated this decision"
    )
    context: DecisionContext = Field(
        default_factory=DecisionContext,
        description="System state at decision time"
    )
    decision_summary: str = Field(
        ...,
        description="Concise description of what was decided"
    )
    key_factors: List[str] = Field(
        default_factory=list,
        description="2-3 most important reasons driving the decision, expressed in ontology weights/policy rules/tradeoffs"
    )
    impact: DecisionImpact = Field(
        default_factory=DecisionImpact,
        description="Downstream effects of this decision"
    )
    related_trace_ids: List[str] = Field(
        default_factory=list,
        description="IDs of related decision traces (for chaining)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
