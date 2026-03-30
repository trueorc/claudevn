"""Event type definitions for the v2.0 event bus.

All inter-layer communication flows through typed events.
No polling — components subscribe to the events they care about.

Every project-scoped event carries a project_id for multi-tenant
isolation. Subscribers filter by project to ensure independent content.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    """Top-level event categories mapping to system layers."""
    DECOMPOSITION = "decomposition"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    SYSTEM = "system"


# -- Decomposition events (Layer 1) --

class DecompositionStarted(BaseModel):
    """A goal has entered decomposition."""
    event: str = "decomposition.started"
    project_id: str
    goal_id: str
    goal_description: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionUpdated(BaseModel):
    """Work units were added, modified, or removed during decomposition."""
    event: str = "decomposition.updated"
    project_id: str
    goal_id: str
    work_unit_ids: List[str]
    change_type: str = Field(description="created | modified | split | merged | deleted")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionApproved(BaseModel):
    """Decomposition was approved by user — work units are ready for dispatch."""
    event: str = "decomposition.approved"
    project_id: str
    goal_id: str
    work_unit_ids: List[str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionStepStarted(BaseModel):
    """A pipeline step has started."""
    event: str = "decomposition.step_started"
    project_id: str
    goal_id: str
    step_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionStepCompleted(BaseModel):
    """A pipeline step has completed."""
    event: str = "decomposition.step_completed"
    project_id: str
    goal_id: str
    step_name: str
    duration_ms: int
    detail: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionStepFailed(BaseModel):
    """A pipeline step has failed."""
    event: str = "decomposition.step_failed"
    project_id: str
    goal_id: str
    step_name: str
    error: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionCompleted(BaseModel):
    """Decomposition pipeline finished — all steps done, work units ready for review."""
    event: str = "decomposition.completed"
    project_id: str
    goal_id: str
    work_unit_count: int
    confidence_score: Optional[int] = None
    confidence_level: Optional[str] = None
    success: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecompositionFeedback(BaseModel):
    """Verification sent feedback to decomposition (e.g., scope violation)."""
    event: str = "decomposition.feedback"
    project_id: str
    goal_id: str
    work_unit_id: str
    feedback_type: str = Field(description="scope_violation | interface_mismatch | gap_detected")
    details: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Coherence events --

class CoherenceUpdated(BaseModel):
    """Coherence analysis completed for a project."""
    event: str = "coherence.updated"
    project_id: str
    insight_count: int
    goals_analyzed: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Execution events (Layer 2) --

class ExecutionQueued(BaseModel):
    """A work unit entered the dispatch queue."""
    event: str = "execution.queued"
    project_id: str
    work_unit_id: str
    goal_id: str
    queue_position: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionStarted(BaseModel):
    """A Claude Code instance began executing a work unit."""
    event: str = "execution.started"
    project_id: str
    work_unit_id: str
    goal_id: str
    instance_id: str
    branch: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionCompleted(BaseModel):
    """A work unit execution finished (PR submitted)."""
    event: str = "execution.completed"
    project_id: str
    work_unit_id: str
    goal_id: str
    instance_id: str
    branch: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionFailed(BaseModel):
    """A work unit execution failed."""
    event: str = "execution.failed"
    project_id: str
    work_unit_id: str
    goal_id: str
    instance_id: str
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Verification events (Layer 3) --

class VerificationStarted(BaseModel):
    """Verification began for a work unit."""
    event: str = "verification.started"
    project_id: str
    work_unit_id: str
    goal_id: str
    checks: List[str] = Field(description="List of check types being run")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationCompleted(BaseModel):
    """All verification checks passed for a work unit."""
    event: str = "verification.completed"
    project_id: str
    work_unit_id: str
    goal_id: str
    results_summary: Dict[str, str] = Field(description="check_type -> pass/fail")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationFailed(BaseModel):
    """One or more verification checks failed."""
    event: str = "verification.failed"
    project_id: str
    work_unit_id: str
    goal_id: str
    failed_checks: List[str]
    details: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IntegrationConflict(BaseModel):
    """Cross-unit integration check found a conflict."""
    event: str = "verification.integration_conflict"
    project_id: str
    work_unit_ids: List[str] = Field(description="The conflicting units")
    goal_id: str
    conflict_type: str = Field(description="merge_conflict | interface_mismatch | test_failure")
    details: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- System events (global, not project-scoped) --

class SystemHealth(BaseModel):
    """System health status change."""
    event: str = "system.health"
    project_id: Optional[str] = None  # Optional — some health is global
    component: str
    status: str = Field(description="healthy | degraded | offline")
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PresenceChanged(BaseModel):
    """User presence changed (multi-user support)."""
    event: str = "system.presence"
    project_id: Optional[str] = None  # Optional — presence can be global or per-project
    user_id: str
    status: str = Field(description="online | away | offline")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Union type for event routing
Event = (
    DecompositionStarted | DecompositionUpdated | DecompositionApproved | DecompositionFeedback |
    DecompositionStepStarted | DecompositionStepCompleted | DecompositionStepFailed |
    DecompositionCompleted |
    CoherenceUpdated |
    ExecutionQueued | ExecutionStarted | ExecutionCompleted | ExecutionFailed |
    VerificationStarted | VerificationCompleted | VerificationFailed | IntegrationConflict |
    SystemHealth | PresenceChanged
)
