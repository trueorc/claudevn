"""User directive models for topology-language communication.

Directives let users issue commands in the language of the work topology
rather than managing individual tasks. Examples:
- "Accelerate payment flow validation"
- "Deprioritize new feature development"
- "Focus on testing for the authentication domain"

Each directive is interpreted into concrete profile adjustments (weight
changes, policy rule additions/modifications) and previewed before applying.

Reference: docs/work_management_framework.md - Section 10
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DirectiveStatus(str, Enum):
    """Lifecycle status of a directive."""
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"


class WeightAdjustment(BaseModel):
    """A proposed change to a single ontology weight."""
    category: str = Field(
        ...,
        description="Ontology category: work_type, lifecycle_stage, technical_domain, cluster"
    )
    key: str = Field(
        ...,
        description="Specific key within the category (e.g., 'test', 'frontend')"
    )
    current_weight: Optional[float] = Field(
        default=None,
        description="Current weight value (None if not set)"
    )
    proposed_weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Proposed new weight value"
    )
    confidence: str = Field(
        default="medium",
        description="Proposed confidence level: high, medium, low"
    )
    rationale: str = Field(
        default="",
        description="Why this adjustment was proposed"
    )


class PolicyAdjustment(BaseModel):
    """A proposed policy rule addition or modification."""
    action: str = Field(
        ...,
        description="add, modify, or remove"
    )
    rule_id: Optional[str] = Field(
        default=None,
        description="Existing rule ID (for modify/remove)"
    )
    rule_name: str = Field(
        default="",
        description="Human-readable rule name"
    )
    rule_description: str = Field(
        default="",
        description="What this policy rule does"
    )
    condition_type: Optional[str] = Field(
        default=None,
        description="PolicyConditionType value"
    )
    condition_params: Dict[str, Any] = Field(
        default_factory=dict,
    )
    action_type: Optional[str] = Field(
        default=None,
        description="PolicyActionType value"
    )
    action_params: Dict[str, Any] = Field(
        default_factory=dict,
    )


class DirectiveInterpretation(BaseModel):
    """The AI-interpreted profile adjustments from a directive.

    Contains the parsed weight and policy changes that would result
    from applying the directive, along with a summary of the reasoning.
    """
    weight_adjustments: List[WeightAdjustment] = Field(
        default_factory=list,
        description="Proposed ontology weight changes"
    )
    policy_adjustments: List[PolicyAdjustment] = Field(
        default_factory=list,
        description="Proposed policy rule changes"
    )
    summary: str = Field(
        default="",
        description="Human-readable summary of what the directive will do"
    )
    detected_intent: Optional[str] = Field(
        default=None,
        description="Detected intent category (accelerate, deprioritize, focus, unblock)"
    )
    affected_areas: List[str] = Field(
        default_factory=list,
        description="Ontology areas affected by this directive"
    )


class Directive(BaseModel):
    """A user directive in topology language.

    Captures the user's natural language directive, its AI interpretation,
    and lifecycle status through preview -> approval -> application.
    """
    directive_id: str = Field(..., description="Unique directive identifier")
    project_id: str = Field(..., description="Project this directive targets")
    text: str = Field(
        ...,
        min_length=1,
        description="Natural language directive text"
    )
    status: DirectiveStatus = Field(
        default=DirectiveStatus.PENDING_REVIEW,
        description="Current lifecycle status"
    )
    interpretation: Optional[DirectiveInterpretation] = Field(
        default=None,
        description="AI-interpreted profile adjustments"
    )
    profile_version_before: Optional[int] = Field(
        default=None,
        description="Profile version before application"
    )
    profile_version_after: Optional[int] = Field(
        default=None,
        description="Profile version after application"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    applied_at: Optional[datetime] = Field(
        default=None,
        description="When the directive was applied"
    )
    rejected_at: Optional[datetime] = Field(
        default=None,
        description="When the directive was rejected"
    )
