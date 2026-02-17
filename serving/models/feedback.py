"""Worker feedback models for the planner profile feedback loop.

Defines the data structures for worker feedback signals, pattern detection,
and decision trace entries that enable bottom-up influence on the planner
profile.

Reference: docs/work_management_framework.md — Sections 8.2, 9
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    """Classification of worker feedback signals."""
    BLOCKER = "blocker"
    CHALLENGE = "challenge"
    REQUIREMENT = "requirement"
    PROGRESS_PATTERN = "progress_pattern"


class ChallengeType(str, Enum):
    """Classification of structured worker challenges.

    Challenges are distinct from blockers — they influence planning
    strategy rather than pausing individual work items.
    """
    TASK_INFEASIBILITY = "task_infeasibility"
    SCOPE_DISCOVERY = "scope_discovery"
    DEPENDENCY_CORRECTION = "dependency_correction"
    QUALITY_CONCERN = "quality_concern"


class FeedbackSeverity(str, Enum):
    """How impactful a feedback signal is."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackSignal(BaseModel):
    """An individual worker feedback signal.

    Represents a single piece of feedback from a compute instance that
    may influence the planner profile. Signals are aggregated and analyzed
    for patterns before triggering profile changes.
    """
    signal_id: str = Field(..., description="Unique signal identifier")
    project_id: str = Field(..., description="Project this signal belongs to")
    worker_id: str = Field(..., description="Compute instance that sent the signal")
    task_id: str = Field(..., description="Work item the signal relates to")
    feedback_type: FeedbackType = Field(..., description="Classification of this feedback")
    severity: FeedbackSeverity = Field(
        default=FeedbackSeverity.MEDIUM,
        description="Impact level of this signal"
    )
    description: str = Field(..., description="Human-readable description of the feedback")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific feedback data"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class FeedbackPattern(BaseModel):
    """A detected pattern across multiple worker feedback signals.

    When multiple workers report similar issues (same feedback type,
    overlapping domains or clusters), this represents a systemic signal
    that warrants weight shifts rather than just policy adjustments.
    """
    pattern_id: str = Field(..., description="Unique pattern identifier")
    project_id: str = Field(..., description="Project this pattern belongs to")
    feedback_type: FeedbackType = Field(..., description="Common feedback type")
    signal_ids: List[str] = Field(
        default_factory=list,
        description="Signal IDs that contribute to this pattern"
    )
    signal_count: int = Field(
        default=0,
        description="Number of signals forming this pattern"
    )
    description: str = Field(
        default="",
        description="Summary of the detected pattern"
    )
    affected_clusters: List[str] = Field(
        default_factory=list,
        description="Domain clusters affected by this pattern"
    )
    affected_work_types: List[str] = Field(
        default_factory=list,
        description="Work types affected by this pattern"
    )
    first_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class DecisionTraceEntry(BaseModel):
    """Record of a profile change triggered by worker feedback.

    Maintains traceability for why the profile changed, what signals
    contributed, and what the impact was.

    Reference: docs/work_management_framework.md — Section 11
    """
    trace_id: str = Field(..., description="Unique trace identifier")
    project_id: str = Field(..., description="Project affected")
    trigger_type: str = Field(
        ...,
        description="What initiated the change (e.g., 'individual_signal', 'pattern_detected')"
    )
    source_signal_ids: List[str] = Field(
        default_factory=list,
        description="Signal IDs that triggered this decision"
    )
    pattern_id: Optional[str] = Field(
        default=None,
        description="Pattern ID if triggered by pattern detection"
    )
    previous_profile_version: int = Field(
        ...,
        description="Profile version before the change"
    )
    new_profile_version: int = Field(
        ...,
        description="Profile version after the change"
    )
    rule_changes: List[str] = Field(
        default_factory=list,
        description="Rule IDs added, modified, or removed"
    )
    weight_changes: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Weight changes: category -> key -> new_weight"
    )
    rationale: str = Field(
        default="",
        description="Human-readable explanation of the decision"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
