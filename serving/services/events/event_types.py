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


# -- Plan reconciliation events --

class PlanReconciled(BaseModel):
    """Plan reconciliation completed for a directive."""
    event: str = "decomposition.plan_reconciled"
    project_id: str
    directive_id: str
    superseded_count: int
    conflict_count: int
    new_unit_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkUnitSuperseded(BaseModel):
    """A work unit was superseded by a newer directive's unit."""
    event: str = "decomposition.unit_superseded"
    project_id: str
    old_unit_id: str
    new_unit_id: str
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlanConflictDetected(BaseModel):
    """A conflict was detected between work units requiring user review."""
    event: str = "decomposition.conflict_detected"
    project_id: str
    conflict_id: str
    unit_ids: List[str]
    severity: str
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


# -- Compute lifecycle events --

class InstanceRegistered(BaseModel):
    """A compute instance was registered."""
    event: str = "compute.instance_registered"
    instance_id: str
    capabilities: List[str] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstanceRemoved(BaseModel):
    """A compute instance was deregistered."""
    event: str = "compute.instance_removed"
    instance_id: str
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstanceApproved(BaseModel):
    """A compute instance was approved (PENDING -> ONLINE)."""
    event: str = "compute.instance_approved"
    instance_id: str
    project_ids: List[str] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstanceRejected(BaseModel):
    """A compute instance was rejected."""
    event: str = "compute.instance_rejected"
    instance_id: str
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComputeDrainStarted(BaseModel):
    """Drain initiated for a compute instance."""
    event: str = "compute.drain_started"
    instance_id: str
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComputeDrainCancelled(BaseModel):
    """Drain cancelled for a compute instance (DRAINING -> ONLINE)."""
    event: str = "compute.drain_cancelled"
    instance_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InstanceHealthChanged(BaseModel):
    """Compute instance health status changed (ONLINE/DEGRADED/OFFLINE)."""
    event: str = "compute.health_changed"
    instance_id: str
    old_status: str
    new_status: str
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComputeAuthChanged(BaseModel):
    """Compute instance auth status changed."""
    event: str = "compute.auth_changed"
    instance_id: str
    old_status: str
    new_status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComputeConnected(BaseModel):
    """Compute SSE connection established."""
    event: str = "compute.connected"
    instance_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ComputeDisconnected(BaseModel):
    """Compute SSE connection lost."""
    event: str = "compute.disconnected"
    instance_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Work lifecycle events --

class WorkReadyForDispatch(BaseModel):
    """A work unit is ready for dispatch."""
    event: str = "work.ready_for_dispatch"
    project_id: str
    work_unit_id: str
    goal_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkStuckDetected(BaseModel):
    """A work unit has been executing too long — timeout fired."""
    event: str = "work.stuck_detected"
    project_id: str
    work_unit_id: str
    stuck_duration_seconds: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkTimeoutRecovered(BaseModel):
    """Stuck work returned to PENDING for retry."""
    event: str = "work.timeout_recovered"
    project_id: str
    work_unit_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkTimeoutFailed(BaseModel):
    """Stuck work exhausted retries, marked FAILED."""
    event: str = "work.timeout_failed"
    project_id: str
    work_unit_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Error events (observability for silent failures) --

class MCPToolError(BaseModel):
    """Error in an MCP tool handler."""
    event: str = "error.mcp_tool"
    tool_name: str
    error_code: str = ""
    error_message: str = ""
    compute_id: Optional[str] = None
    project_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DispatchError(BaseModel):
    """Error during work dispatch."""
    event: str = "error.dispatch"
    error_message: str = ""
    work_id: Optional[str] = None
    project_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthCheckError(BaseModel):
    """Error in health monitoring."""
    event: str = "error.health_check"
    error_message: str = ""
    instance_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SSEConnectionError(BaseModel):
    """Error in SSE connection management."""
    event: str = "error.sse_connection"
    error_message: str = ""
    instance_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Union type for event routing
Event = (
    DecompositionStarted | DecompositionUpdated | DecompositionApproved | DecompositionFeedback |
    DecompositionStepStarted | DecompositionStepCompleted | DecompositionStepFailed |
    DecompositionCompleted |
    PlanReconciled | WorkUnitSuperseded | PlanConflictDetected |
    CoherenceUpdated |
    ExecutionQueued | ExecutionStarted | ExecutionCompleted | ExecutionFailed |
    VerificationStarted | VerificationCompleted | VerificationFailed | IntegrationConflict |
    InstanceRegistered | InstanceRemoved | InstanceApproved | InstanceRejected |
    ComputeDrainStarted | ComputeDrainCancelled | InstanceHealthChanged | ComputeAuthChanged |
    ComputeConnected | ComputeDisconnected |
    WorkReadyForDispatch | WorkStuckDetected | WorkTimeoutRecovered | WorkTimeoutFailed |
    MCPToolError | DispatchError | HealthCheckError | SSEConnectionError |
    SystemHealth | PresenceChanged
)
