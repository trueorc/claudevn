"""Plan Executor models for Slim Claude Code.

Models for executing approved work plans - creating issues with
proper dependency mapping and approval audit trail.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Status of plan execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class IssueMapping(BaseModel):
    """Mapping between temporary and real issue IDs."""
    temp_id: str = Field(..., description="Temporary ID from decomposition")
    issue_id: str = Field(..., description="Real issue ID in system")
    title: str = Field(..., description="Issue title")
    phase_number: int = Field(..., description="Phase where issue was created")


class ApprovalRecord(BaseModel):
    """Record of plan approval."""
    approved_by: str = Field(..., description="User ID who approved the plan")
    approved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of approval"
    )
    plan_id: str = Field(..., description="ID of the approved plan")
    goal_id: str = Field(..., description="ID of the goal being executed")
    notes: Optional[str] = Field(
        default=None,
        description="Optional approval notes"
    )


class ExecutionError(BaseModel):
    """Error that occurred during execution."""
    temp_id: str = Field(..., description="Issue temp_id that failed")
    error_message: str = Field(..., description="Error description")
    phase_number: int = Field(..., description="Phase where error occurred")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class IssueBatchCreateResponse(BaseModel):
    """Response from batch issue creation.

    Contains the mapping of temporary IDs to real issue IDs,
    along with execution metadata.
    """
    success: bool = Field(..., description="Whether execution succeeded")
    goal_id: str = Field(..., description="Source goal ID")
    plan_id: str = Field(..., description="Executed plan ID")
    decomposition_id: str = Field(..., description="Source decomposition ID")
    status: ExecutionStatus = Field(
        default=ExecutionStatus.COMPLETED,
        description="Execution status"
    )
    created_issues: List[IssueMapping] = Field(
        default_factory=list,
        description="Mapping of temp_ids to real issue IDs"
    )
    approval: ApprovalRecord = Field(..., description="Approval record")
    errors: List[ExecutionError] = Field(
        default_factory=list,
        description="Errors encountered during execution"
    )
    rolled_back_issues: List[str] = Field(
        default_factory=list,
        description="Issue IDs that were rolled back on failure"
    )
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    execution_duration_ms: Optional[int] = Field(
        default=None,
        description="Execution time in milliseconds"
    )


class ExecutePlanRequest(BaseModel):
    """Request to execute an approved plan."""
    goal_id: str = Field(..., description="Goal ID to execute")
    plan_id: str = Field(..., description="Plan ID to execute")
    approved_by: str = Field(..., description="User ID approving execution")
    approval_notes: Optional[str] = Field(
        default=None,
        description="Optional notes from approver"
    )


class PlanExecutorConfig(BaseModel):
    """Configuration for Plan Executor service."""

    # Execution behavior
    rollback_on_failure: bool = Field(
        default=True,
        description="Whether to rollback created issues on failure"
    )
    continue_on_error: bool = Field(
        default=False,
        description="Whether to continue creating issues after an error"
    )

    # Storage settings (for persisting decompositions/plans)
    decomposition_ttl_hours: int = Field(
        default=24,
        description="Hours to keep unapproved decompositions"
    )
    plan_ttl_hours: int = Field(
        default=24,
        description="Hours to keep unapproved plans"
    )
