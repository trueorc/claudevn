"""Work Map models for task allocation and tracking.

The WorkMap manages three core concepts:
- Goal: High-level objective, input to Planner (persistent)
- Issue: Unit of work with history (persistent, Git-backed)
- WorkItem: Active assignment to a Compute (ephemeral, Redis)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator

from models.ontology import OntologyTags


# =============================================================================
# Enums
# =============================================================================


class GoalStatus(str, Enum):
    """Status of a goal."""
    PLANNING = "planning"       # Being broken into issues by Planner
    IN_PROGRESS = "in_progress"  # Issues being worked
    DONE = "done"               # All issues completed
    FAILED = "failed"           # Planning/decomposition failed or timed out
    RETIRED = "retired"         # Retired: no longer active but work preserved


class GoalIntentType(str, Enum):
    """Strategic intent classification for a goal."""
    EXPANSION = "expansion"                  # Building new features/capabilities
    CONSOLIDATION = "consolidation"          # Quality, stability, testing focus
    TARGETED_INVESTMENT = "targeted_investment"  # Focused capability investment
    QUALITY_FOCUSED = "quality_focused"      # Deep quality improvement


class IssueStatus(str, Enum):
    """Status of an issue per the WorkMap spec."""
    BACKLOG = "backlog"         # Has unmet dependencies, not ready
    READY = "ready"             # All dependencies met, waiting for assignment
    IN_PROGRESS = "in_progress"  # Assigned to a Compute, being worked
    BLOCKED = "blocked"         # Compute reported a blocker
    DONE = "done"               # Completed successfully
    FAILED = "failed"           # Failed after retries exhausted


class IssueType(str, Enum):
    """Types of issues."""
    FEATURE = "feature"
    BUG = "bug"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"


class IssueArea(str, Enum):
    """Areas of the codebase an issue affects."""
    API = "api"
    DATABASE = "database"
    FRONTEND = "frontend"
    INFRA = "infra"
    OTHER = "other"


class ReleaseStatus(str, Enum):
    """Status of a release."""
    PLANNED = "planned"     # Future release, not yet started
    ACTIVE = "active"       # Currently being worked on
    RELEASED = "released"   # Released/shipped


class IssuePriority(str, Enum):
    """Priority levels for issues (P0-P3)."""
    P0 = "P0"  # Critical - highest priority
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low - lowest priority

    @property
    def score_weight(self) -> int:
        """Return score weight for priority queue (lower = higher priority)."""
        return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}[self.value]


class WorkStatus(str, Enum):
    """Status of a work item (ephemeral assignment)."""
    PENDING = "pending"           # Created, waiting for assignment
    ASSIGNED = "assigned"         # Assigned to compute, not yet started
    IN_PROGRESS = "in_progress"   # Compute actively working
    BLOCKED = "blocked"           # Waiting on dependency or external
    REVIEW = "review"             # Work done, awaiting review
    COMPLETED = "completed"       # Successfully completed
    FAILED = "failed"             # Failed, needs intervention


class WorkPriority(str, Enum):
    """Priority levels for work items."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class BlockerType(str, Enum):
    """Types of blockers that can impede work."""
    DEPENDENCY = "dependency"      # Waiting on another work item
    EXTERNAL = "external"          # Waiting on external input
    RESOURCE = "resource"          # Waiting on resource availability
    CLARIFICATION = "clarification"  # Needs human clarification
    TECHNICAL = "technical"        # Technical issue


class EvaluationStatus(str, Enum):
    """Status of AI evaluation for a goal comment."""
    NOT_EVALUATED = "not_evaluated"  # Comment has not been evaluated
    EVALUATING = "evaluating"        # Evaluation in progress
    EVALUATED = "evaluated"          # Evaluation complete
    FAILED = "failed"                # Evaluation failed after retries


class CommentType(str, Enum):
    """Type of content identified in a goal comment during evaluation."""
    SUGGESTION = "suggestion"          # User suggesting a feature or approach
    BUG = "bug"                        # User reporting a bug or issue
    ENHANCEMENT = "enhancement"        # Request to enhance existing functionality
    PRIORITY_INFLUENCE = "priority_influence"  # Comment affecting priority
    INFO = "info"                      # General information or context


class ConversationStatus(str, Enum):
    """Overall status of a goal conversation derived from comments."""
    NO_COMMENTS = "no_comments"      # No comments yet
    PENDING = "pending"              # Has comments awaiting evaluation
    EVALUATING = "evaluating"        # At least one comment being evaluated
    COMPLETE = "complete"            # All comments evaluated


# =============================================================================
# Evaluation Result Model (AI evaluation output for comments)
# =============================================================================


class SuggestedAction(BaseModel):
    """A suggested action from comment evaluation."""
    action_type: str = Field(..., description="Type of action: create_issue, update_priority, add_context")
    description: str = Field(..., description="Description of the suggested action")
    target: Optional[str] = Field(None, description="Target entity (issue_id, goal_id, etc.)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional action metadata")


class EvaluationResult(BaseModel):
    """Result of AI evaluation for a goal comment.

    Contains extracted information and suggested actions from the comment.
    """
    comment_type: CommentType = Field(..., description="Type of content identified")
    entities: List[str] = Field(default_factory=list, description="Features, components mentioned")
    suggested_actions: List[SuggestedAction] = Field(
        default_factory=list,
        description="Proposed actions based on the comment"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for the evaluation (0.0 - 1.0)"
    )
    summary: str = Field(..., description="Brief AI-generated summary of the comment")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluator_version: str = Field(default="1.0", description="Version of the evaluation pipeline")


# =============================================================================
# Goal Comment Model (Persistent - Conversational thread entries)
# =============================================================================


class GoalComment(BaseModel):
    """A comment in a goal conversation thread.

    Each comment represents a message in the goal conversation and has
    independent evaluation status for the AI evaluation pipeline.
    """
    comment_id: str = Field(..., description="Unique comment identifier")
    goal_id: str = Field(..., description="Parent goal reference")
    content: str = Field(..., description="Text content of the comment")

    # Optional classification (can be null)
    priority: Optional[IssuePriority] = Field(None, description="Optional P0-P3 priority")
    area: Optional[IssueArea] = Field(None, description="Optional area tag")

    # Evaluation pipeline
    evaluation_status: EvaluationStatus = Field(
        default=EvaluationStatus.NOT_EVALUATED,
        description="Status of AI evaluation for this comment"
    )
    evaluation_result: Optional[EvaluationResult] = Field(
        None,
        description="Structured AI evaluation output"
    )
    evaluation_error: Optional[str] = Field(
        None,
        description="Error message if evaluation failed"
    )
    evaluation_retry_count: int = Field(
        default=0,
        description="Number of evaluation retry attempts"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="user", description="User identifier who created this comment")


class GoalCommentCreateRequest(BaseModel):
    """Request to create a new goal comment."""
    content: str
    priority: Optional[IssuePriority] = None
    area: Optional[IssueArea] = None
    created_by: str = "user"


class GoalCommentUpdateRequest(BaseModel):
    """Request to update a goal comment."""
    content: Optional[str] = None
    priority: Optional[IssuePriority] = None
    area: Optional[IssueArea] = None
    evaluation_status: Optional[EvaluationStatus] = None
    evaluation_result: Optional[EvaluationResult] = None
    evaluation_error: Optional[str] = None
    evaluation_retry_count: Optional[int] = None


class GoalCommentListResponse(BaseModel):
    """Response for listing goal comments."""
    items: List["GoalComment"]
    total: int
    goal_id: str
    conversation_status: ConversationStatus


class GoalCommentCreateRequestWithRollup(BaseModel):
    """Request to create a new goal comment with rollup options."""
    content: str
    priority: Optional[IssuePriority] = None
    area: Optional[IssueArea] = None
    created_by: str = "user"
    force_evaluate: bool = Field(
        default=False,
        description="Skip rollup and immediately evaluate this comment"
    )


# =============================================================================
# Rollup Models (For batch comment processing)
# =============================================================================


class RollupStatus(str, Enum):
    """Status of a rollup batch."""
    COLLECTING = "collecting"    # Still within rollup window, collecting comments
    WAITING = "waiting"          # Rollup window closed, waiting for quiet period
    PROCESSING = "processing"    # Quiet period passed, evaluation in progress
    COMPLETED = "completed"      # Batch evaluation complete


class RollupConfig(BaseModel):
    """Configuration for comment rollup behavior."""
    rollup_window_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Time window to group comments (default 30 seconds)"
    )
    quiet_period_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Quiet period before triggering evaluation (default 10 seconds)"
    )
    enabled: bool = Field(
        default=True,
        description="Whether rollup is enabled"
    )


class RollupBatch(BaseModel):
    """A batch of comments being rolled up for evaluation."""
    batch_id: str = Field(..., description="Unique batch identifier")
    goal_id: str = Field(..., description="Goal this batch belongs to")
    comment_ids: List[str] = Field(default_factory=list, description="Comment IDs in this batch")
    status: RollupStatus = Field(default=RollupStatus.COLLECTING)

    # Timing
    first_comment_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of first comment in batch"
    )
    last_comment_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of most recent comment in batch"
    )
    window_expires_at: Optional[datetime] = Field(
        None,
        description="When the rollup window expires"
    )
    quiet_period_ends_at: Optional[datetime] = Field(
        None,
        description="When the quiet period ends and evaluation triggers"
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="When batch evaluation completed"
    )

    # Configuration snapshot (in case config changes mid-batch)
    config: RollupConfig = Field(default_factory=RollupConfig)


class RollupStatusResponse(BaseModel):
    """Response for rollup status query."""
    goal_id: str
    has_active_batch: bool
    batch: Optional[RollupBatch] = None
    pending_comment_count: int = 0
    config: RollupConfig


# =============================================================================
# Goal Intent Models (Strategic intent classification)
# =============================================================================


class IntentSignal(BaseModel):
    """A parsed intent signal from goal text or conversation.

    Represents a detected strategic intent with its strength and source.
    Multiple signals can coexist on a single goal, with the strongest
    being the primary intent.
    """
    intent_type: GoalIntentType = Field(..., description="Classification of the intent")
    strength: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Strength of the intent signal (0.0-1.0)"
    )
    detected_from: str = Field(
        default="goal_text",
        description="Source of signal: 'goal_text', 'comment', 'manual'"
    )
    source_id: Optional[str] = Field(
        None,
        description="ID of the source (comment_id if from comment, None for goal text)"
    )
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    keywords_matched: List[str] = Field(
        default_factory=list,
        description="Keywords that contributed to this signal"
    )


class GoalConflict(BaseModel):
    """A detected tension or conflict between two goals.

    Surfaced when goals pull the planner profile in opposing directions.
    Conflicts with severity >= 0.7 are considered irreconcilable and
    require explicit user intervention (priority/weight overrides).
    """
    conflict_id: str = Field(..., description="Unique conflict identifier")
    goal_id_a: str = Field(..., description="First goal in the conflict")
    goal_id_b: str = Field(..., description="Second goal in the conflict")
    description: str = Field(..., description="Human-readable description of the tension")
    severity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Severity of the conflict (0.0 minor, 1.0 severe)"
    )
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_irreconcilable: bool = Field(
        default=False,
        description="True when severity >= 0.7 and automatic reconciliation may produce poor results"
    )
    resolution_hint: Optional[str] = Field(
        None,
        description="Suggested action to resolve (e.g., set reconciliation_weight on one goal)"
    )


# =============================================================================
# Decomposition Pass Model (Tracks each decomposition invocation)
# =============================================================================


class DecompositionTrigger(str, Enum):
    """What triggered a decomposition pass."""
    INITIAL = "initial"              # First decomposition at goal creation
    PLANNER_GAP = "planner_gap"      # Planner detected missing work
    WORKER_FEEDBACK = "worker_feedback"  # Worker identified gaps during execution
    MANUAL = "manual"                # User manually requested re-decomposition


class DecompositionPass(BaseModel):
    """Record of a single decomposition invocation.

    Tracks each time decomposition is run for a goal, including
    what triggered it and what issues were created.
    """
    decomposition_id: str = Field(..., description="ID of the decomposition result")
    pass_number: int = Field(..., description="Sequential pass number (1-based)")
    trigger: DecompositionTrigger = Field(
        default=DecompositionTrigger.INITIAL,
        description="What triggered this decomposition pass"
    )
    triggered_by: Optional[str] = Field(
        None,
        description="ID of the entity that triggered decomposition (compute_id, user_id)"
    )
    trigger_context: Optional[str] = Field(
        None,
        description="Additional context about why re-decomposition was needed"
    )
    issue_ids_created: List[str] = Field(
        default_factory=list,
        description="Issue IDs created during this pass"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Goal Model (Persistent - High-level objectives)
# =============================================================================


class Goal(BaseModel):
    """High-level objective submitted by user.

    Goals are broken into Issues by the Planner Compute.
    Stored persistently in Git.
    """
    goal_id: str = Field(..., description="Unique goal identifier")
    title: str = Field(..., description="Brief title of the goal")
    description: str = Field(..., description="Detailed description of what to achieve")

    # Project association
    project_id: Optional[str] = Field(
        None,
        description="Project this goal belongs to (optional for backwards compatibility)"
    )

    priority: IssuePriority = Field(default=IssuePriority.P1)
    status: GoalStatus = Field(default=GoalStatus.PLANNING)

    # Populated after planning
    issue_ids: List[str] = Field(default_factory=list, description="Issue IDs created for this goal")

    # Intent classification
    intent_signals: List[IntentSignal] = Field(
        default_factory=list,
        description="Parsed intent signals from goal text and conversation"
    )
    primary_intent: Optional[GoalIntentType] = Field(
        None,
        description="Primary intent classification (strongest signal)"
    )
    intent_strength: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall intent strength for profile reconciliation"
    )

    # User-set reconciliation weight override
    reconciliation_weight: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="User-set weight for multi-goal reconciliation (None = auto from priority/recency)"
    )

    # Conversation support
    conversation_status: ConversationStatus = Field(
        default=ConversationStatus.NO_COMMENTS,
        description="Overall status derived from comment evaluations"
    )

    # Goal text evaluation tracking
    goal_text_evaluated: bool = Field(
        default=False,
        description="Whether the initial goal text has been evaluated (decomposed)"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="user", description="Who created this goal")

    # Decomposition tracking
    decomposition_id: Optional[str] = Field(
        default=None,
        description="ID of the most recent decomposition result"
    )
    decomposition_passes: List[DecompositionPass] = Field(
        default_factory=list,
        description="History of all decomposition passes for this goal"
    )
    planning_started_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when planning/decomposition was last started"
    )
    planning_error: Optional[str] = Field(
        default=None,
        description="Error message if planning/decomposition failed"
    )

    # Soft delete support
    deleted_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when goal was soft-deleted, None if not deleted"
    )

    # Archive support
    archived: bool = Field(
        default=False,
        description="Whether the goal is archived (hidden by default but not deleted)"
    )
    archived_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when goal was archived, None if not archived"
    )


class GoalCreateRequest(BaseModel):
    """Request to create a new goal."""
    title: str
    description: str
    priority: IssuePriority = IssuePriority.P1
    project_id: Optional[str] = Field(None, description="Project this goal belongs to")


class GoalDeleteResponse(BaseModel):
    """Response for goal deletion."""
    goal_id: str
    deleted: bool
    deleted_at: Optional[datetime] = None
    comment_count: int = Field(default=0, description="Number of comments deleted with goal")
    issue_count: int = Field(default=0, description="Number of issues cascade-deleted (cascade only)")
    work_item_count: int = Field(default=0, description="Number of work items cascade-deleted (cascade only)")


class ProjectDeleteResponse(BaseModel):
    """Response for project deletion."""
    project_id: str
    deleted: bool
    goal_count: int = Field(default=0, description="Number of goals cascade-deleted")
    issue_count: int = Field(default=0, description="Number of issues cascade-deleted")
    work_item_count: int = Field(default=0, description="Number of work items cascade-deleted")
    comment_count: int = Field(default=0, description="Number of comments cascade-deleted")
    repo_count: int = Field(default=0, description="Number of internal Git repos deleted")


class IssueDeleteResponse(BaseModel):
    """Response for issue deletion."""
    issue_id: str
    deleted: bool
    child_issue_count: int = Field(default=0, description="Number of child issues cascade-deleted")
    work_item_count: int = Field(default=0, description="Number of work items cascade-deleted")


class GoalProgressMetrics(BaseModel):
    """Multi-dimensional progress metrics for a goal.

    Provides richer progress indicators beyond simple issue completion:
    - Issue status breakdown (completion, blocked, failed)
    - Characterization pipeline progress
    - Execution velocity (recent completion rate)
    """
    goal_id: str
    goal_status: GoalStatus

    # Issue completion
    total_issues: int = Field(default=0, description="Total issues for this goal")
    done_count: int = Field(default=0, description="Issues completed successfully")
    in_progress_count: int = Field(default=0, description="Issues currently being worked")
    blocked_count: int = Field(default=0, description="Issues blocked by dependencies or errors")
    failed_count: int = Field(default=0, description="Issues that failed")
    ready_count: int = Field(default=0, description="Issues ready for assignment")
    backlog_count: int = Field(default=0, description="Issues with unmet dependencies")

    # Completion percentage
    completion_percent: float = Field(
        default=0.0,
        description="Percentage of issues completed (0.0-100.0)"
    )

    # Characterization progress
    characterized_count: int = Field(
        default=0,
        description="Issues with completed characterization (ontology_tags populated)"
    )
    characterization_percent: float = Field(
        default=0.0,
        description="Percentage of issues characterized (0.0-100.0)"
    )

    # Execution velocity (items completed in last 7 days)
    velocity_7d: int = Field(
        default=0,
        description="Issues completed in the last 7 days"
    )
    velocity_trend: str = Field(
        default="steady",
        description="Velocity trend: accelerating, steady, or stalling"
    )

    # Timestamps
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GoalListResponse(BaseModel):
    """Response for listing goals."""
    items: List[Goal]
    total: int
    by_status: Dict[str, int]


class GoalAdjustIntentRequest(BaseModel):
    """Request to adjust a goal's intent without recreating."""
    primary_intent: Optional[GoalIntentType] = Field(
        None, description="Override primary intent classification"
    )
    intent_strength: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Override intent strength"
    )
    title: Optional[str] = Field(None, description="Update goal title")
    description: Optional[str] = Field(None, description="Update goal description")
    priority: Optional[IssuePriority] = Field(None, description="Update priority")
    reparse_intent: bool = Field(
        default=False,
        description="Re-analyze goal text for intent signals after update"
    )


class GoalSetReconciliationWeightRequest(BaseModel):
    """Request to set a goal's reconciliation weight for multi-goal balancing."""
    reconciliation_weight: Optional[float] = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weight for reconciliation (0.0-1.0), or null to reset to automatic"
    )


class SupplementalDecomposeRequest(BaseModel):
    """Request to trigger supplemental decomposition for an existing goal."""
    trigger: DecompositionTrigger = Field(
        default=DecompositionTrigger.MANUAL,
        description="What triggered this supplemental decomposition"
    )
    triggered_by: Optional[str] = Field(
        None,
        description="ID of the entity requesting decomposition (compute_id, user_id)"
    )
    gap_description: Optional[str] = Field(
        None,
        description="Description of what work is missing or what gaps were detected"
    )
    context: Optional[str] = Field(
        None,
        description="Additional context for the decomposer (e.g., worker observations)"
    )
    constraints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional constraints (max_issues, focus_areas, etc.)"
    )


class GoalConflictListResponse(BaseModel):
    """Response for listing conflicts between active goals."""
    project_id: str
    conflicts: List[GoalConflict]
    total: int
    has_irreconcilable: bool = Field(
        default=False,
        description="True if any conflicts have severity >= 0.7"
    )


class EvaluationItemStatus(BaseModel):
    """Evaluation status for a single item (goal text or comment)."""
    item_type: str = Field(..., description="'goal_text' or 'comment'")
    item_id: Optional[str] = Field(None, description="Comment ID (null for goal_text)")
    content_preview: str = Field(..., description="First 200 chars of content")
    evaluation_status: str = Field(..., description="Evaluation status value")
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class GoalEvaluationSummary(BaseModel):
    """Summary of evaluation status for a goal and all its items."""
    goal_id: str
    all_evaluated: bool = Field(..., description="True if goal text and all comments are evaluated")
    goal_text_evaluated: bool
    has_decomposition: bool
    decomposition_id: Optional[str] = None
    items: List[EvaluationItemStatus] = Field(default_factory=list)
    total_items: int = 0
    evaluated_count: int = 0
    pending_count: int = 0


# =============================================================================
# Release Model (Persistent - Grouping for planning/milestones)
# =============================================================================


class Release(BaseModel):
    """A release for grouping issues.

    Releases allow issues to be grouped by version or milestone for planning.
    """
    release_id: str = Field(..., description="Unique release identifier")
    name: str = Field(..., description="Release name (e.g., 'v1.0', 'Q1 2024')")
    description: Optional[str] = Field(None, description="Optional release description")
    target_date: Optional[datetime] = Field(None, description="Target release date")
    status: ReleaseStatus = Field(default=ReleaseStatus.PLANNED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReleaseCreateRequest(BaseModel):
    """Request to create a new release."""
    name: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    status: ReleaseStatus = ReleaseStatus.PLANNED


class ReleaseUpdateRequest(BaseModel):
    """Request to update a release."""
    name: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    status: Optional[ReleaseStatus] = None


class ReleaseListResponse(BaseModel):
    """Response for listing releases."""
    items: List[Release]
    total: int
    by_status: Dict[str, int]


# =============================================================================
# Issue Evaluation Models (Post-completion review)
# =============================================================================


class IssueEvaluationOutcome(str, Enum):
    """Outcome of post-completion issue evaluation."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class RootCauseCategory(str, Enum):
    """Category of root cause for partial/failed issue outcomes."""
    INCOMPLETE_REQUIREMENTS = "incomplete_requirements"
    TECHNICAL_LIMITATION = "technical_limitation"
    SCOPE_CREEP = "scope_creep"
    DEPENDENCY_ISSUE = "dependency_issue"
    OTHER = "other"


class IssueEvaluationResult(BaseModel):
    """Result of post-completion evaluation for an issue."""
    outcome: IssueEvaluationOutcome
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    accomplishments: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    root_cause_category: Optional[RootCauseCategory] = None
    root_cause_analysis: Optional[str] = None
    requires_followup: bool = False
    followup_issue_id: Optional[str] = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluator_version: str = "1.0"


# =============================================================================
# Issue Model (Persistent - Unit of work with history)
# =============================================================================


class IssueResult(BaseModel):
    """Result of a completed issue."""
    branch: Optional[str] = Field(None, description="Git branch with changes")
    summary: Optional[str] = Field(None, description="Summary of what was done")
    commits: List[str] = Field(default_factory=list, description="Commit SHAs")


class Issue(BaseModel):
    """Unit of work with full history.

    Issues are persistent and stored in Git for audit trail.
    Status flow: backlog → ready → in_progress → blocked → done → failed
    """
    issue_id: str = Field(..., description="Unique issue identifier")
    title: str = Field(..., description="Brief title of the issue")
    description: str = Field(..., description="Detailed description")

    # Classification (legacy — retained for backwards compatibility)
    issue_type: IssueType = Field(default=IssueType.FEATURE)
    area: IssueArea = Field(default=IssueArea.OTHER)
    priority: IssuePriority = Field(default=IssuePriority.P2)
    status: IssueStatus = Field(default=IssueStatus.BACKLOG)

    # Ontology tags (enriched classification from characterization pipeline)
    ontology_tags: Optional[OntologyTags] = Field(
        None,
        description="Ontology tags from characterization (None if not yet characterized)"
    )

    # Requirements
    required_skills: List[str] = Field(default_factory=list, description="Skill IDs needed")
    required_labels: List[str] = Field(default_factory=list, description="Compute labels required for routing (e.g., production-access)")
    required_tools: List[str] = Field(default_factory=list, description="Specialized tools required (e.g., deploy_prod)")

    # Dependencies
    depends_on: List[str] = Field(default_factory=list, description="Issue IDs this depends on")
    blocks: List[str] = Field(default_factory=list, description="Issue IDs waiting on this (computed)")

    # Project association
    project_id: Optional[str] = Field(
        None,
        description="Project this issue belongs to (optional for backwards compatibility)"
    )

    # Lineage
    goal_id: Optional[str] = Field(None, description="Parent goal")
    parent_issue_id: Optional[str] = Field(None, description="If subtask of another issue")

    # Release planning
    release_id: Optional[str] = Field(None, description="Target release for this issue")

    # Assignment
    assigned_compute_id: Optional[str] = Field(None, description="Compute instance ID if assigned")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Result (populated on completion)
    result: Optional[IssueResult] = None

    # Retry tracking
    retry_count: int = Field(default=0)

    # Post-completion evaluation
    evaluation_status: EvaluationStatus = Field(default=EvaluationStatus.NOT_EVALUATED)
    evaluation_result: Optional[IssueEvaluationResult] = None
    evaluation_retry_count: int = Field(default=0)

    def calculate_priority_score(self) -> float:
        """Calculate priority queue score: (Priority * 1000) + Age in hours.

        Lower score = higher priority.
        """
        age_hours = (datetime.now(timezone.utc) - self.created_at).total_seconds() / 3600
        return (self.priority.score_weight * 1000) + age_hours

    @property
    def all_dependencies_met(self) -> bool:
        """Check if all dependencies are completed (must be checked externally)."""
        # This is a marker property - actual check requires service context
        return len(self.depends_on) == 0


class IssueCreateRequest(BaseModel):
    """Request to create a new issue."""
    title: str
    description: str
    issue_type: IssueType = IssueType.FEATURE
    area: IssueArea = IssueArea.OTHER
    priority: IssuePriority = IssuePriority.P2
    required_skills: List[str] = Field(default_factory=list)
    required_labels: List[str] = Field(default_factory=list, description="Compute labels required for routing")
    required_tools: List[str] = Field(default_factory=list, description="Specialized tools required")
    depends_on: List[Union[str, int]] = Field(
        default_factory=list,
        description="Issue IDs or batch-internal indices this depends on"
    )
    project_id: Optional[str] = Field(None, description="Project this issue belongs to")
    goal_id: Optional[str] = None
    parent_issue_id: Optional[str] = None
    release_id: Optional[str] = None
    ontology_tags: Optional[OntologyTags] = Field(None, description="Ontology tags from characterization")


class IssueBatchCreateRequest(BaseModel):
    """Request to create multiple issues at once (from Planner)."""
    goal_id: str
    issues: List[IssueCreateRequest]


class IssueBatchCreateResponse(BaseModel):
    """Response for batch issue creation."""
    success: bool
    goal_id: str
    created_issues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {index, id} mappings"
    )
    ready_count: int = 0
    backlog_count: int = 0


class IssueUpdateRequest(BaseModel):
    """Request to update an issue."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[IssuePriority] = None
    area: Optional[IssueArea] = None
    required_skills: Optional[List[str]] = None
    release_id: Optional[str] = None
    ontology_tags: Optional[OntologyTags] = Field(None, description="Update ontology tags")


class IssueListResponse(BaseModel):
    """Response for listing issues."""
    items: List[Issue]
    total: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_release: Dict[str, int] = Field(default_factory=dict)


class IssueStats(BaseModel):
    """Statistics about issues."""
    total: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_area: Dict[str, int]
    by_release: Dict[str, int] = Field(default_factory=dict)
    ready_count: int
    in_progress_count: int
    blocked_count: int


class IssueHistoryEntry(BaseModel):
    """A single entry in issue history."""
    commit: str = Field(..., description="Git commit hash")
    author: str = Field(..., description="Commit author")
    timestamp: datetime = Field(..., description="Commit timestamp")
    message: str = Field(..., description="Commit message")


class IssueHistory(BaseModel):
    """History of changes to an issue."""
    issue_id: str = Field(..., description="Issue ID")
    entries: List[IssueHistoryEntry] = Field(default_factory=list, description="History entries")


# =============================================================================
# Blocker Model
# =============================================================================


class Blocker(BaseModel):
    """A blocker preventing work progress."""
    blocker_id: str = Field(..., description="Unique blocker identifier")
    blocker_type: BlockerType
    description: str
    blocking_work_id: Optional[str] = Field(None, description="Work ID if DEPENDENCY type")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


# =============================================================================
# WorkItem Model (Ephemeral - Active assignment to Compute)
# =============================================================================


class WorkItem(BaseModel):
    """Ephemeral assignment of work to a Compute instance.

    Work Items exist only while work is in progress (Redis).
    They link an Issue to a Compute instance during execution.
    """
    work_id: str = Field(..., description="Unique work identifier")
    title: str = Field(..., description="Brief title of the work")
    description: str = Field(..., description="Detailed description")

    # Classification
    work_type: str = Field(default="task", description="Type: task, bug, feature, review")
    priority: WorkPriority = Field(default=WorkPriority.NORMAL)
    tags: List[str] = Field(default_factory=list)

    # Requirements
    required_skills: List[str] = Field(default_factory=list, description="Skill IDs needed")
    required_capabilities: List[str] = Field(default_factory=list, description="Capability tags needed")
    required_labels: List[str] = Field(default_factory=list, description="Compute labels required for routing (e.g., production-access)")
    required_tools: List[str] = Field(default_factory=list, description="Specialized tools required (e.g., deploy_prod)")
    skill_ids: List[str] = Field(default_factory=list, description="Selected skill IDs for this work")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context for compute")

    # Lineage
    issue_id: Optional[str] = Field(None, description="Parent issue ID this work item was created from")

    # Dependencies
    depends_on: List[str] = Field(default_factory=list, description="Work IDs this depends on")
    blocks: List[str] = Field(default_factory=list, description="Work IDs blocked by this")

    # Git integration
    project_id: str = Field(..., min_length=1, description="Git project this work belongs to - required")
    branch_name: Optional[str] = Field(None, description="Git branch for this work")
    base_branch: str = Field(default="main", description="Branch to base work on")

    # Assignment
    status: WorkStatus = Field(default=WorkStatus.PENDING)
    assigned_to: Optional[str] = Field(None, description="Compute instance ID")
    assigned_skills: List[str] = Field(default_factory=list, description="Skills assigned to compute")

    # Blockers
    blockers: List[Blocker] = Field(default_factory=list)

    # Progress
    progress_percent: int = Field(default=0, ge=0, le=100)
    progress_notes: List[str] = Field(default_factory=list)

    # Timeout tracking
    retry_count: int = Field(default=0, description="Number of times work has been retried due to timeout")
    last_activity_at: Optional[datetime] = Field(None, description="Last activity timestamp for timeout detection")

    # Output
    result: Optional[Dict[str, Any]] = Field(None, description="Final result when completed")
    error: Optional[str] = Field(None, description="Error message if failed")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def active_blockers(self) -> List[Blocker]:
        """Get unresolved blockers."""
        return [b for b in self.blockers if not b.is_resolved]

    @property
    def is_blocked(self) -> bool:
        """Check if work has active blockers."""
        return len(self.active_blockers) > 0

    @property
    def can_start(self) -> bool:
        """Check if work can be started (no blockers, dependencies met)."""
        return not self.is_blocked and self.status in [WorkStatus.PENDING, WorkStatus.ASSIGNED]

    @field_validator('project_id')
    @classmethod
    def project_id_must_not_be_empty(cls, v: str) -> str:
        """Validate that project_id is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Work items must be attached to a project')
        return v.strip()


class WorkCreateRequest(BaseModel):
    """Request to create a new work item."""
    title: str
    description: str
    work_type: str = "task"
    priority: WorkPriority = WorkPriority.NORMAL
    tags: List[str] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)
    required_labels: List[str] = Field(default_factory=list, description="Compute labels required for routing")
    required_tools: List[str] = Field(default_factory=list, description="Specialized tools required")
    skill_ids: Optional[List[str]] = Field(None, description="Explicit skill IDs override")
    context: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    issue_id: Optional[str] = Field(None, description="Parent issue ID this work was created from")
    project_id: str = Field(..., min_length=1, description="Project ID - required for all work items")
    base_branch: str = "main"

    @field_validator('project_id')
    @classmethod
    def project_id_must_not_be_empty(cls, v: str) -> str:
        """Validate that project_id is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError('Work items must be attached to a project')
        return v.strip()


class WorkUpdateRequest(BaseModel):
    """Request to update a work item."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[WorkPriority] = None
    tags: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None


class WorkAssignment(BaseModel):
    """Work assignment details sent to compute."""
    work_id: str
    title: str
    description: str
    skills: List[str] = Field(description="Skill IDs to compose")
    skill_ids: List[str] = Field(default_factory=list, description="Selected skill IDs")
    branch_name: str
    base_branch: str
    context: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list, description="Completed dependency work IDs")
    dependency_outputs: Dict[str, Any] = Field(default_factory=dict, description="Outputs from dependencies")

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


class ProgressReport(BaseModel):
    """Progress report from compute."""
    work_id: str
    progress_percent: int = Field(ge=0, le=100)
    status: WorkStatus
    note: Optional[str] = None
    blockers: List[Dict[str, Any]] = Field(default_factory=list)


class WorkListResponse(BaseModel):
    """Response for listing work items."""
    items: List[WorkItem]
    total: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]


class WorkStats(BaseModel):
    """Statistics about work items."""
    total: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_project: Dict[str, int]
    blocked_count: int
    assigned_count: int
    unassigned_count: int
