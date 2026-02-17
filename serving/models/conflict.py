"""Conflict identification taxonomy and surfacing protocol models.

Defines the conflict type taxonomy, surfacing protocol schema, authority
boundary rules, and user response mechanisms for planner-level conflict
detection and surfacing.

Conflict types:
1. Goal-to-goal: Competing goals demand same resources or push profile
   in opposing directions
2. Goal-to-reality: Goal intent undermined by ground-truth conditions
3. Dependency: Circular, contradictory, or unresolvable dependency chains
4. Resource: Plan requires capabilities exceeding availability

Reference: docs/work_management_framework.md — Sections 10.1, 12
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Conflict Type Taxonomy
# =============================================================================


class ConflictType(str, Enum):
    """Classification of planner-level conflicts.

    Each type represents a distinct category of tension that the planner
    may detect during planning and execution.
    """
    GOAL_TO_GOAL = "goal_to_goal"
    GOAL_TO_REALITY = "goal_to_reality"
    DEPENDENCY = "dependency"
    RESOURCE = "resource"


class ConflictSeverity(str, Enum):
    """How severe a conflict is, determining surfacing behavior.

    LOW: Planner handles autonomously, logged for traceability
    MEDIUM: Planner handles autonomously, included in status updates
    HIGH: Surfaced to user with planner's current handling approach
    CRITICAL: Surfaced to user immediately, planner pauses affected work
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictStatus(str, Enum):
    """Lifecycle status of a conflict."""
    ACTIVE = "active"
    AUTONOMOUSLY_RESOLVED = "autonomously_resolved"
    SURFACED = "surfaced"
    USER_RESOLVED = "user_resolved"
    SUPERSEDED = "superseded"


# =============================================================================
# User Response Mechanisms
# =============================================================================


class UserResponseType(str, Enum):
    """How a user can respond to a surfaced conflict."""
    ADJUST_GOAL = "adjust_goal"
    ACCEPT_TRADEOFF = "accept_tradeoff"
    CLARIFY_INTENT = "clarify_intent"
    SET_PRIORITY = "set_priority"


class UserResponse(BaseModel):
    """A user's response to a surfaced conflict."""
    response_type: UserResponseType = Field(
        ...,
        description="How the user chose to respond"
    )
    description: str = Field(
        default="",
        description="User's explanation or clarification"
    )
    affected_goal_ids: List[str] = Field(
        default_factory=list,
        description="Goal IDs the user modified in response"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =============================================================================
# Conflict Tension (what is in tension)
# =============================================================================


class TensionElement(BaseModel):
    """A specific element involved in a conflict tension.

    Represents a goal, task, resource, or dependency that is part
    of the conflict.
    """
    element_type: str = Field(
        ...,
        description="Type of element: 'goal', 'task', 'resource', 'dependency'"
    )
    element_id: str = Field(
        ...,
        description="ID of the specific element (goal_id, task_id, etc.)"
    )
    label: str = Field(
        ...,
        description="Human-readable label for the element"
    )
    detail: str = Field(
        default="",
        description="Additional context about this element's role in the conflict"
    )


# =============================================================================
# Authority Boundary Rules
# =============================================================================


class ResolutionAuthority(str, Enum):
    """Who has authority to resolve a conflict."""
    AUTONOMOUS = "autonomous"
    USER_REQUIRED = "user_required"


class AuthorityRule(BaseModel):
    """A rule defining when the planner can resolve autonomously vs. surface.

    Authority boundaries are determined by conflict type, severity,
    and specific conditions.
    """
    conflict_type: ConflictType = Field(
        ...,
        description="Which conflict type this rule applies to"
    )
    severity_threshold: ConflictSeverity = Field(
        ...,
        description="Minimum severity at which user intervention is required"
    )
    authority: ResolutionAuthority = Field(
        ...,
        description="Who resolves conflicts below the threshold"
    )
    condition: str = Field(
        default="",
        description="Additional condition for this rule"
    )
    description: str = Field(
        default="",
        description="Human-readable description of the rule"
    )


# Default authority boundary rules
DEFAULT_AUTHORITY_RULES: List[AuthorityRule] = [
    AuthorityRule(
        conflict_type=ConflictType.GOAL_TO_GOAL,
        severity_threshold=ConflictSeverity.HIGH,
        authority=ResolutionAuthority.USER_REQUIRED,
        condition="severity >= 0.7 or is_irreconcilable",
        description=(
            "Goal-to-goal conflicts with high severity require user "
            "intervention. Lower severity conflicts are reconciled "
            "automatically using priority and recency signals."
        ),
    ),
    AuthorityRule(
        conflict_type=ConflictType.GOAL_TO_REALITY,
        severity_threshold=ConflictSeverity.MEDIUM,
        authority=ResolutionAuthority.USER_REQUIRED,
        condition="goal_intent_significantly_undermined",
        description=(
            "Goal-to-reality conflicts are surfaced at medium severity "
            "because the user's stated intent is being undermined by "
            "ground-truth conditions they may not be aware of."
        ),
    ),
    AuthorityRule(
        conflict_type=ConflictType.DEPENDENCY,
        severity_threshold=ConflictSeverity.HIGH,
        authority=ResolutionAuthority.AUTONOMOUS,
        condition="not circular",
        description=(
            "Dependency conflicts are resolved autonomously unless "
            "circular or contradictory. Circular dependencies require "
            "user intervention to break the cycle."
        ),
    ),
    AuthorityRule(
        conflict_type=ConflictType.RESOURCE,
        severity_threshold=ConflictSeverity.MEDIUM,
        authority=ResolutionAuthority.AUTONOMOUS,
        condition="alternative_available",
        description=(
            "Resource conflicts are resolved autonomously when "
            "alternatives exist (resequencing, worker substitution). "
            "Surfaced when no alternative exists."
        ),
    ),
]


# =============================================================================
# ConflictReport (Surfacing Protocol Schema)
# =============================================================================


class PlannerHandling(BaseModel):
    """How the planner is currently handling a conflict.

    Documents what the planner decided and its reasoning.
    """
    approach: str = Field(
        ...,
        description="What the planner is doing about this conflict"
    )
    favored_side: Optional[str] = Field(
        None,
        description="Which side the planner favored (if applicable)"
    )
    reasoning: str = Field(
        default="",
        description="Why the planner chose this approach"
    )
    profile_impact: Dict[str, Any] = Field(
        default_factory=dict,
        description="How this handling affected the planner profile"
    )


class SuggestedResolution(BaseModel):
    """A suggested action the user can take to resolve a conflict."""
    response_type: UserResponseType = Field(
        ...,
        description="Type of response this suggestion represents"
    )
    description: str = Field(
        ...,
        description="Human-readable description of what the user could do"
    )
    expected_impact: str = Field(
        default="",
        description="What would change if the user takes this action"
    )


class ConflictReport(BaseModel):
    """A complete conflict report for surfacing to the user.

    This is the primary surfacing protocol schema. Each conflict is
    presented with:
    - What is in tension (specific goals, tasks, resources)
    - How the planner is currently handling it
    - What the user could do to resolve it
    - Decision trace reference

    Reference: docs/work_management_framework.md — Section 10.1
    """
    conflict_id: str = Field(
        ...,
        description="Unique conflict identifier"
    )
    project_id: str = Field(
        ...,
        description="Project this conflict belongs to"
    )

    # Classification
    conflict_type: ConflictType = Field(
        ...,
        description="Category of conflict"
    )
    severity: ConflictSeverity = Field(
        ...,
        description="How severe this conflict is"
    )
    severity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Numeric severity score (0.0 minor, 1.0 severe)"
    )
    status: ConflictStatus = Field(
        default=ConflictStatus.ACTIVE,
        description="Current lifecycle status"
    )

    # What is in tension
    title: str = Field(
        ...,
        description="Brief human-readable title of the conflict"
    )
    description: str = Field(
        ...,
        description="Detailed description of the tension"
    )
    tension_elements: List[TensionElement] = Field(
        default_factory=list,
        description="Specific elements involved in the tension"
    )

    # How the planner is handling it
    planner_handling: PlannerHandling = Field(
        ...,
        description="How the planner is currently handling this conflict"
    )

    # What the user could do
    suggested_resolutions: List[SuggestedResolution] = Field(
        default_factory=list,
        description="Actions the user could take to resolve the conflict"
    )

    # Decision trace reference
    decision_trace_ids: List[str] = Field(
        default_factory=list,
        description="IDs of decision trace entries related to this conflict"
    )

    # Authority
    resolution_authority: ResolutionAuthority = Field(
        ...,
        description="Whether this conflict requires user intervention"
    )

    # Resolution tracking
    user_response: Optional[UserResponse] = Field(
        None,
        description="User's response if they've addressed this conflict"
    )
    autonomous_resolution: Optional[str] = Field(
        None,
        description="Description of autonomous resolution if applicable"
    )

    # Timestamps
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    surfaced_at: Optional[datetime] = Field(
        None,
        description="When this conflict was surfaced to the user"
    )
    resolved_at: Optional[datetime] = Field(
        None,
        description="When this conflict was resolved"
    )

    def should_surface(self) -> bool:
        """Determine if this conflict should be surfaced to the user.

        Returns True if the conflict requires user intervention based
        on severity and authority rules.
        """
        return (
            self.resolution_authority == ResolutionAuthority.USER_REQUIRED
            or self.severity in (ConflictSeverity.HIGH, ConflictSeverity.CRITICAL)
        )

    def mark_surfaced(self) -> None:
        """Mark the conflict as surfaced to the user."""
        self.status = ConflictStatus.SURFACED
        self.surfaced_at = datetime.now(timezone.utc)

    def resolve_autonomously(self, resolution: str) -> None:
        """Mark the conflict as autonomously resolved."""
        self.status = ConflictStatus.AUTONOMOUSLY_RESOLVED
        self.autonomous_resolution = resolution
        self.resolved_at = datetime.now(timezone.utc)

    def resolve_by_user(self, response: UserResponse) -> None:
        """Mark the conflict as resolved by user response."""
        self.status = ConflictStatus.USER_RESOLVED
        self.user_response = response
        self.resolved_at = datetime.now(timezone.utc)


# =============================================================================
# Detection Criteria
# =============================================================================


class DetectionCriteria(BaseModel):
    """Criteria for detecting a specific type of conflict.

    Used by the conflict detection service to know what to look for.
    """
    conflict_type: ConflictType = Field(
        ...,
        description="Which conflict type these criteria detect"
    )
    name: str = Field(
        ...,
        description="Human-readable name for these criteria"
    )
    description: str = Field(
        ...,
        description="What this criteria checks for"
    )
    required_data: List[str] = Field(
        default_factory=list,
        description="Data sources needed for detection (e.g., 'goals', 'feedback_signals')"
    )


# Default detection criteria for each conflict type
DEFAULT_DETECTION_CRITERIA: List[DetectionCriteria] = [
    DetectionCriteria(
        conflict_type=ConflictType.GOAL_TO_GOAL,
        name="Intent conflict detection",
        description=(
            "Detect when two active goals have conflicting primary intents "
            "(e.g., expansion vs. consolidation). Uses GoalConflict model "
            "from goal_intent_service."
        ),
        required_data=["goals", "planner_profile"],
    ),
    DetectionCriteria(
        conflict_type=ConflictType.GOAL_TO_GOAL,
        name="Resource competition detection",
        description=(
            "Detect when two goals compete for the same domain clusters "
            "or worker capabilities."
        ),
        required_data=["goals", "planner_profile", "bucket_tree"],
    ),
    DetectionCriteria(
        conflict_type=ConflictType.GOAL_TO_REALITY,
        name="Intent vs. feedback detection",
        description=(
            "Detect when worker feedback patterns contradict the dominant "
            "goal intent. E.g., goal says 'focus on testing' but workers "
            "report systemic blockers requiring bug fixes."
        ),
        required_data=["goals", "feedback_patterns", "planner_profile"],
    ),
    DetectionCriteria(
        conflict_type=ConflictType.DEPENDENCY,
        name="Circular dependency detection",
        description=(
            "Detect circular or contradictory dependency chains in "
            "work items."
        ),
        required_data=["work_items", "dependencies"],
    ),
    DetectionCriteria(
        conflict_type=ConflictType.DEPENDENCY,
        name="Unresolvable dependency detection",
        description=(
            "Detect dependencies that reference non-existent items "
            "or items in terminal states."
        ),
        required_data=["work_items", "dependencies"],
    ),
    DetectionCriteria(
        conflict_type=ConflictType.RESOURCE,
        name="Worker contention detection",
        description=(
            "Detect when multiple high-priority tasks require the same "
            "specialized worker or capability."
        ),
        required_data=["bucket_tree", "worker_registry"],
    ),
    DetectionCriteria(
        conflict_type=ConflictType.RESOURCE,
        name="Capability gap detection",
        description=(
            "Detect when planned work requires capabilities that no "
            "available worker can provide."
        ),
        required_data=["work_items", "worker_registry"],
    ),
]
