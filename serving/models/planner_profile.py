"""Planner dynamic profile schema for work management.

The planner profile is a dynamic lens constructed from three influence sources:
user goals (top-down intent), worker feedback (bottom-up signals), and resource
opportunities (environmental conditions). It determines how the planner evaluates
and sequences all work.

The profile consists of three components:
  A. Ontology weights — preferences across both ontology layers
  B. Policy rules — conditional logic that overrides weights
  C. Confidence bands — how firmly the profile holds its positions

Reference: docs/work_management_framework.md — Sections 7.1, 7.2
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Confidence Bands
# =============================================================================


class ConfidenceLevel(str, Enum):
    """How firmly the planner holds a weight or policy position.

    High confidence: the planner deviates only for strong countervailing signals.
    Medium confidence: the planner may adjust for moderate signals.
    Low confidence: the planner is willing to be opportunistic or flexible.
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceBand(BaseModel):
    """Confidence metadata attached to a weight or policy.

    Influenced by the strength of the user's directive language
    and the consistency of other signals.
    """
    level: ConfidenceLevel = Field(
        default=ConfidenceLevel.MEDIUM,
        description="Confidence level for this weight or policy"
    )
    rationale: str = Field(
        default="",
        description="Why this confidence level was assigned"
    )


# =============================================================================
# Weighted Ontology Values (weights + confidence)
# =============================================================================


class WeightedValue(BaseModel):
    """A weight value paired with its confidence band.

    Represents a single ontology category weight (0.0-1.0) along with
    how firmly the planner should hold that position.
    """
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Priority weight from 0.0 (deprioritized) to 1.0 (highest)"
    )
    confidence: ConfidenceBand = Field(
        default_factory=ConfidenceBand,
        description="How firmly the planner holds this weight"
    )


class ProfileWeights(BaseModel):
    """Ontology weights with confidence bands for both layers.

    Layer 1 (universal): weights for work type, lifecycle stage, technical domain.
    Layer 2 (project-specific): weights for domain clusters.

    Each weight carries a confidence band indicating how firmly the planner
    should hold that position.
    """
    # Layer 1 weights — keyed by enum value strings
    work_type_weights: Dict[str, WeightedValue] = Field(
        default_factory=dict,
        description="Weight per WorkType value (e.g., 'feature': 0.3, 'test': 0.9)"
    )
    lifecycle_stage_weights: Dict[str, WeightedValue] = Field(
        default_factory=dict,
        description="Weight per LifecycleStage value"
    )
    technical_domain_weights: Dict[str, WeightedValue] = Field(
        default_factory=dict,
        description="Weight per TechnicalDomain value"
    )

    # Layer 2 weights — keyed by cluster_id
    cluster_weights: Dict[str, WeightedValue] = Field(
        default_factory=dict,
        description="Weight per project-specific cluster_id"
    )

    def get_weight(self, category: str, key: str) -> float:
        """Get a weight value, defaulting to 0.5 if not set.

        Args:
            category: One of 'work_type', 'lifecycle_stage',
                      'technical_domain', 'cluster'
            key: The specific category key (e.g., 'feature', 'build')

        Returns:
            Weight value between 0.0 and 1.0
        """
        weights_map = {
            "work_type": self.work_type_weights,
            "lifecycle_stage": self.lifecycle_stage_weights,
            "technical_domain": self.technical_domain_weights,
            "cluster": self.cluster_weights,
        }
        weights = weights_map.get(category, {})
        entry = weights.get(key)
        return entry.weight if entry else 0.5

    def get_confidence(self, category: str, key: str) -> ConfidenceLevel:
        """Get the confidence level for a weight, defaulting to MEDIUM.

        Args:
            category: One of 'work_type', 'lifecycle_stage',
                      'technical_domain', 'cluster'
            key: The specific category key

        Returns:
            ConfidenceLevel for the weight
        """
        weights_map = {
            "work_type": self.work_type_weights,
            "lifecycle_stage": self.lifecycle_stage_weights,
            "technical_domain": self.technical_domain_weights,
            "cluster": self.cluster_weights,
        }
        weights = weights_map.get(category, {})
        entry = weights.get(key)
        return entry.confidence.level if entry else ConfidenceLevel.MEDIUM


# =============================================================================
# Policy Rules
# =============================================================================


class PolicyConditionType(str, Enum):
    """Types of conditions that can trigger policy rules."""
    BLOCKS_HIGH_PRIORITY = "blocks_high_priority"
    COMPLETION_ABOVE_THRESHOLD = "completion_above_threshold"
    IN_ONTOLOGY_CATEGORY = "in_ontology_category"
    BLOCKED_BY_COUNT_ABOVE = "blocked_by_count_above"
    BLOCKING_COUNT_ABOVE = "blocking_count_above"
    IN_CLUSTER = "in_cluster"
    CUSTOM = "custom"


class PolicyActionType(str, Enum):
    """Types of actions a policy rule can take."""
    ELEVATE_PRIORITY = "elevate_priority"
    PRESERVE_PRIORITY = "preserve_priority"
    DEPRIORITIZE = "deprioritize"
    FORCE_BUCKET = "force_bucket"
    SKIP = "skip"


class PolicyRule(BaseModel):
    """A conditional rule that overrides ontology weights.

    Policy rules express dependency-aware and situational reasoning.
    They fire when their condition is met and apply an action that
    overrides the normal weight-based prioritization.

    Examples:
    - "Tasks blocking high-priority testing inherit elevated priority"
    - "Tasks >80% complete should be finished regardless of deprioritization"
    """
    rule_id: str = Field(..., description="Unique rule identifier")
    name: str = Field(..., description="Human-readable rule name")
    description: str = Field(
        default="",
        description="Detailed explanation of what this rule does"
    )

    # Condition
    condition_type: PolicyConditionType = Field(
        ...,
        description="Type of condition that triggers this rule"
    )
    condition_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the condition (e.g., {'threshold': 0.8})"
    )

    # Action
    action_type: PolicyActionType = Field(
        ...,
        description="Action to take when condition is met"
    )
    action_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the action (e.g., {'target_bucket': 1})"
    )

    # Metadata
    confidence: ConfidenceBand = Field(
        default_factory=ConfidenceBand,
        description="How firmly the planner holds this policy"
    )
    enabled: bool = Field(
        default=True,
        description="Whether this rule is currently active"
    )
    source_goal_id: Optional[str] = Field(
        default=None,
        description="Goal that introduced this rule (if any)"
    )

    def matches_condition_type(self, condition_type: PolicyConditionType) -> bool:
        """Check if this rule matches the given condition type."""
        return self.enabled and self.condition_type == condition_type


# =============================================================================
# Profile Triggers and Lifecycle
# =============================================================================


class ProfileTriggerType(str, Enum):
    """Events that cause the planner profile to be rebuilt or adjusted."""
    NEW_GOAL = "new_goal"
    GOAL_UPDATED = "goal_updated"
    GOAL_REMOVED = "goal_removed"
    WORKER_FEEDBACK = "worker_feedback"
    RESOURCE_CHANGE = "resource_change"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class ProfileTrigger(BaseModel):
    """Record of an event that caused a profile update.

    Maintains traceability for why the profile changed.
    """
    trigger_type: ProfileTriggerType = Field(
        ...,
        description="What caused this profile update"
    )
    source_id: str = Field(
        ...,
        description="ID of the goal, worker, or resource that triggered the update"
    )
    description: str = Field(
        default="",
        description="Human-readable description of what changed"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =============================================================================
# Planner Profile (top-level)
# =============================================================================


class PlannerProfile(BaseModel):
    """The planner's dynamic operating profile.

    Constructed from three influence sources: user goals (top-down intent),
    worker feedback (bottom-up signals), and resource conditions.
    Determines how the planner evaluates and sequences all work.

    The profile is rebuilt or adjusted when:
    - A new goal arrives (primary trigger)
    - Worker feedback surfaces new information (secondary trigger)
    - Resource conditions change (tertiary trigger)

    When multiple goals coexist, the profile reconciles potentially
    competing intents by evaluating relative strength and recency.
    """
    profile_id: str = Field(..., description="Unique profile identifier")
    project_id: str = Field(..., description="Project this profile belongs to")

    # The three core components
    weights: ProfileWeights = Field(
        default_factory=ProfileWeights,
        description="Ontology weights with confidence bands"
    )
    policy_rules: List[PolicyRule] = Field(
        default_factory=list,
        description="Conditional rules that override weights"
    )

    # Active preset (base layer)
    active_preset: Optional[str] = Field(
        default=None,
        description="Name of the active work profile preset (e.g., 'build', 'harden')"
    )

    # Goal tracking for multi-goal reconciliation
    active_goal_ids: List[str] = Field(
        default_factory=list,
        description="Goal IDs currently influencing this profile"
    )

    # Lifecycle tracking
    triggers: List[ProfileTrigger] = Field(
        default_factory=list,
        description="History of events that caused profile updates"
    )
    version: int = Field(
        default=1,
        description="Profile version, incremented on each update"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def get_enabled_rules(self) -> List[PolicyRule]:
        """Get all currently enabled policy rules."""
        return [r for r in self.policy_rules if r.enabled]

    def get_rules_by_condition(
        self, condition_type: PolicyConditionType
    ) -> List[PolicyRule]:
        """Get enabled rules matching a specific condition type."""
        return [
            r for r in self.policy_rules
            if r.matches_condition_type(condition_type)
        ]

    def get_rules_for_goal(self, goal_id: str) -> List[PolicyRule]:
        """Get all rules introduced by a specific goal."""
        return [
            r for r in self.policy_rules
            if r.source_goal_id == goal_id
        ]

    @model_validator(mode="after")
    def validate_rule_ids_unique(self) -> "PlannerProfile":
        """Ensure all policy rule IDs are unique within the profile."""
        rule_ids = [r.rule_id for r in self.policy_rules]
        if len(rule_ids) != len(set(rule_ids)):
            duplicates = [
                rid for rid in rule_ids if rule_ids.count(rid) > 1
            ]
            raise ValueError(
                f"Duplicate policy rule IDs: {set(duplicates)}"
            )
        return self
