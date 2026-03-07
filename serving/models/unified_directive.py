"""Unified directive models for the merged goal/directive system.

A unified directive accepts any user intent — new work requests, priority
shifts, or combined instructions — classifies it, and routes to the
appropriate handler.

Reference: Issue #613 - Unified Directives Backend
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from models.directive import DirectiveInterpretation


class DirectiveIntent(str, Enum):
    """Classified intent of a user directive."""
    NEW_WORK = "new_work"
    PRIORITY_SHIFT = "priority_shift"
    COMBINED = "combined"
    CLARIFICATION = "clarification"
    CONVERSATION = "conversation"


class DirectiveLifecycleStatus(str, Enum):
    """Lifecycle status of a unified directive."""
    RECEIVED = "received"
    CLASSIFYING = "classifying"
    CLASSIFIED = "classified"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"


class DirectiveComment(BaseModel):
    """A comment on a unified directive (conversation thread)."""
    comment_id: str
    directive_id: str
    content: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_by: str = "user"
    created_by_name: Optional[str] = None


class DirectiveOutcome(BaseModel):
    """What happened as a result of processing this directive."""
    issue_ids_created: List[str] = Field(default_factory=list)
    goal_id_created: Optional[str] = None
    profile_changes_applied: bool = False
    profile_version_before: Optional[int] = None
    profile_version_after: Optional[int] = None
    clarification_question: Optional[str] = None


class UnifiedDirective(BaseModel):
    """A unified user directive — any user intent.

    Replaces the separate Goal and Directive concepts with a single
    entry point that accepts natural language, classifies intent, and
    routes to the appropriate handler.
    """
    directive_id: str = Field(..., description="Unique directive identifier")
    project_id: str = Field(..., description="Project this directive targets")
    text: str = Field(..., min_length=1, description="Natural language input")
    intent: Optional[DirectiveIntent] = Field(
        default=None,
        description="Classified intent (set after classification)",
    )
    lifecycle_status: DirectiveLifecycleStatus = Field(
        default=DirectiveLifecycleStatus.RECEIVED,
    )
    outcome: Optional[DirectiveOutcome] = Field(
        default=None,
        description="Outcome after processing completes",
    )
    comments: List[DirectiveComment] = Field(default_factory=list)
    interpretation: Optional[DirectiveInterpretation] = Field(
        default=None,
        description="Profile adjustment interpretation (for priority_shift intents)",
    )
    parent_directive_id: Optional[str] = Field(
        default=None,
        description="Parent directive ID for conversation follow-ups",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_by: Optional[str] = Field(
        default=None,
        description="User ID of the creator",
    )
    created_by_name: Optional[str] = Field(
        default=None,
        description="Display name of the creator at time of creation",
    )


class UnifiedDirectiveCreateRequest(BaseModel):
    """Request to submit a new unified directive."""
    text: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language directive text",
    )
    project_id: str = Field(..., description="Project this directive targets")
    parent_directive_id: Optional[str] = Field(
        default=None,
        description="Parent directive ID for follow-up conversation",
    )


class DirectiveCommentCreateRequest(BaseModel):
    """Request to add a comment to a directive."""
    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Comment text",
    )


class UnifiedDirectiveListResponse(BaseModel):
    """Response for listing unified directives."""
    items: List[UnifiedDirective]
    total: int
