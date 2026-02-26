"""MCP request and response models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task status values."""
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW_REQUESTED = "review_requested"
    COMPLETED = "completed"


class BlockerType(str, Enum):
    """Types of blockers that can prevent task completion."""
    DEPENDENCY = "dependency"
    CLARIFICATION = "clarification"
    ACCESS = "access"
    TECHNICAL = "technical"
    OTHER = "other"


class MergeStatus(str, Enum):
    """Merge status for completed tasks."""
    QUEUED = "queued"
    MERGED = "merged"
    CONFLICT = "conflict"
    REVIEW_REQUIRED = "review_required"


class ContextType(str, Enum):
    """Types of context that can be requested."""
    FILES = "files"
    HISTORY = "history"
    RELATED_TASKS = "related_tasks"
    DEPENDENCIES = "dependencies"
    ALL = "all"


# Tool Inputs
class GetAssignmentInput(BaseModel):
    """Input for claudevn_get_assignment tool."""
    compute_id: str = Field(..., description="The compute instance ID")
    capabilities: Optional[List[str]] = Field(None, description="Filter by capabilities")


class ReportProgressInput(BaseModel):
    """Input for claudevn_report_progress tool."""
    task_id: str = Field(..., description="Task being updated")
    status: TaskStatus = Field(..., description="Current status")
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    message: Optional[str] = Field(None)
    commits: Optional[List[str]] = Field(None)


class RequestReviewInput(BaseModel):
    """Input for claudevn_request_review tool."""
    branch: str = Field(..., description="Branch to submit")
    task_id: str = Field(..., description="Associated task ID")
    title: Optional[str] = Field(None)
    description: Optional[str] = Field(None)
    test_results: Optional[Dict[str, Any]] = Field(None)


class GetContextInput(BaseModel):
    """Input for claudevn_get_context tool."""
    task_id: str = Field(..., description="Task to get context for")
    context_types: Optional[List[ContextType]] = Field(None)
    file_patterns: Optional[List[str]] = Field(None)


class SignalBlockerInput(BaseModel):
    """Input for claudevn_signal_blocker tool."""
    task_id: str = Field(..., description="Task that is blocked")
    blocker_type: BlockerType = Field(...)
    description: str = Field(...)
    suggested_resolution: Optional[str] = Field(None)
    blocking_task_id: Optional[str] = Field(None)


class CompleteTaskInput(BaseModel):
    """Input for claudevn_complete_task tool."""
    task_id: str = Field(...)
    branch: str = Field(...)
    summary: str = Field(...)
    deliverables: Optional[List[str]] = Field(None)
    test_results: Optional[Dict[str, Any]] = Field(None)


class GetSkillInput(BaseModel):
    """Input for claudevn_get_skill tool."""
    skill_id: str = Field(..., description="Skill identifier")


class NotifyConflictInput(BaseModel):
    """Input for claudevn_notify_conflict tool.

    Used by the serving component to notify compute instances
    when their branch has a merge conflict with main.
    """
    task_id: str = Field(..., description="Task ID associated with the conflicting branch")
    branch: str = Field(..., description="Branch name that has conflicts")
    conflicting_files: List[str] = Field(..., description="List of files with merge conflicts")
    base_branch: str = Field(default="main", description="Branch being merged into (usually main)")


class AddIssuesInput(BaseModel):
    """Input for claudevn_add_issues tool.

    Accepts a goal_id and a list of issues with their details.
    Dependencies can reference other issues in the batch using array indices.
    """
    goal_id: str = Field(..., description="Goal ID that these issues belong to")
    issues: List[Dict[str, Any]] = Field(
        ...,
        description="List of issues to create. Each issue can have: title, description, type, area, priority, required_skills, depends_on"
    )


class AddRequirementInput(BaseModel):
    """Input for claudevn_add_requirement tool.

    Used by Compute instances to report new work discovered during
    task execution that wasn't in the original task definition.
    """
    title: str = Field(..., description="Brief title for the new work")
    description: str = Field(..., description="Detailed description of the requirement")
    parent_task_id: str = Field(..., description="Task ID that spawned this requirement")
    suggested_skills: Optional[List[str]] = Field(
        None,
        description="Skills that might be needed for this work"
    )
    dependencies: Optional[List[str]] = Field(
        None,
        description="Task IDs this requirement depends on"
    )
    priority: Optional[str] = Field(
        None,
        description="Priority level: critical, high, normal, low"
    )


class DecomposedIssueInput(BaseModel):
    """A single decomposed issue from the compute instance."""
    temp_id: str = Field(..., description="Temporary ID (e.g., 'issue-1')")
    title: str = Field(..., description="Issue title")
    description: str = Field(default="", description="Issue description")
    issue_type: str = Field(default="feature", description="Issue type: feature, bug, refactor, test, docs")
    priority: str = Field(default="P2", description="Priority: P0, P1, P2, P3")
    area: str = Field(default="api", description="Area: api, database, frontend, infra, other")
    required_skills: List[str] = Field(default_factory=list, description="Required skill IDs")
    estimated_complexity: str = Field(default="m", description="Complexity: xs, s, m, l, xl")
    blocked_by: List[str] = Field(default_factory=list, description="Temp IDs this issue is blocked by")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Acceptance criteria")


class SubmitDecompositionInput(BaseModel):
    """Input for claudevn_submit_decomposition tool.

    Used by compute instances to return goal decomposition results
    back to serving. The compute instance performs the actual
    decomposition using Claude Code (with OAuth credentials).
    """
    decomposition_id: str = Field(..., description="Decomposition ID assigned by serving")
    goal_id: str = Field(..., description="Goal being decomposed")
    issues: List[DecomposedIssueInput] = Field(..., description="List of decomposed issues")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(default="", description="Explanation of decomposition approach")


class ReportChallengeInput(BaseModel):
    """Input for claudevn_submit_challenge tool.

    Used by compute instances to report structured challenges beyond
    simple blockers. Challenges indicate the task may not be achievable
    as specified or that significant scope changes are needed.
    """
    task_id: str = Field(..., description="Task encountering the challenge")
    worker_id: str = Field(..., description="Compute instance reporting the challenge")
    challenge_type: str = Field(
        ...,
        description=(
            "Type of challenge: task_infeasibility, scope_discovery, "
            "dependency_correction, quality_concern"
        ),
    )
    description: str = Field(..., description="Detailed description of the challenge")
    severity: str = Field(
        default="medium",
        description="Severity: low, medium, high, critical"
    )
    impact_assessment: Optional[str] = Field(
        None,
        description="Assessment of how this affects the task and related work"
    )
    suggested_approach: Optional[str] = Field(
        None,
        description="Worker's suggestion for resolving the challenge"
    )
    affected_tasks: Optional[List[str]] = Field(
        None,
        description="Other task IDs that may be affected by this challenge"
    )


# Tool Outputs
class TaskAssignment(BaseModel):
    """Task assignment returned to compute instance."""
    task_id: str
    title: str
    description: str
    skill_ids: List[str] = Field(description="Selected skill IDs for this task")
    branch_name: str
    context: Optional[Dict[str, Any]] = None
    dependencies: Optional[List[str]] = None

    # Repository details for linked repos
    git_project_name: Optional[str] = Field(
        None,
        description="Composite bare repo name for git operations (e.g. proj_abc_repo_def)"
    )
    clone_url: Optional[str] = Field(
        None,
        description="Full HTTP clone URL for the repository"
    )
    default_branch: Optional[str] = Field(
        None,
        description="Repository's configured default branch name"
    )


class ProgressAck(BaseModel):
    """Acknowledgment of progress report."""
    acknowledged: bool
    task_id: str
    updated_at: datetime


class ReviewResponse(BaseModel):
    """Response to review request."""
    pr_id: str
    branch: str
    status: str
    queue_position: Optional[int] = None


class ContextResponse(BaseModel):
    """Context information for a task."""
    task: Optional[Dict[str, Any]] = None
    relevant_files: Optional[List[Dict[str, Any]]] = None
    related_tasks: Optional[List[Dict[str, Any]]] = None
    recent_commits: Optional[List[Dict[str, Any]]] = None


class BlockerResponse(BaseModel):
    """Response to blocker signal."""
    acknowledged: bool
    blocker_id: str
    resolution_task_id: Optional[str] = None
    status: str


class CompleteResponse(BaseModel):
    """Response to task completion."""
    task_id: str
    status: str
    merge_status: MergeStatus
    next_task: Optional[TaskAssignment] = None


class RequirementResponse(BaseModel):
    """Response to add_requirement request."""
    acknowledged: bool
    new_task_id: str
    status: str = Field(description="Status of the new requirement (e.g., 'added_to_backlog')")


class ChallengeResponse(BaseModel):
    """Response to report_challenge request."""
    acknowledged: bool
    signal_id: str = Field(description="Feedback signal ID for tracking")
    profile_updated: bool = Field(
        default=False,
        description="Whether the planner profile was updated"
    )
    pattern_detected: bool = Field(
        default=False,
        description="Whether this signal contributed to a detected pattern"
    )
    status: str = Field(description="Status of the challenge (e.g., 'challenge_recorded')")


class SkillResponse(BaseModel):
    """Skill definition."""
    skill_id: str
    name: str
    instructions: str = Field(description="CLAUDE.md fragment for this skill")
    capabilities: List[str]
    specialized_tools: Optional[List[str]] = Field(None, description="Tools this skill grants access to")


class ConflictNotification(BaseModel):
    """Response to conflict notification.

    Provides the compute instance with acknowledgment and
    detailed guidance on how to resolve the merge conflict.
    """
    acknowledged: bool
    task_id: str
    branch: str
    action_required: str = Field(
        default="rebase_and_push",
        description="Action the compute instance should take"
    )
    conflicting_files: List[str]
    guidance: str = Field(
        description="Detailed steps for resolving the conflict"
    )


# MCP Protocol wrapper
class MCPToolCall(BaseModel):
    """MCP tool call request."""
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")


class MCPResponse(BaseModel):
    """MCP tool response."""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class MCPError(BaseModel):
    """MCP error details."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Re-export SubmitCharacterizationInput from tool module for server registry
from .tools.characterization import SubmitCharacterizationInput  # noqa: E402, F401
