"""Conversation message models."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    """A single message in a project conversation."""
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    user_id: str = "system"
    display_name: str = "System"
    type: str = "user"  # user, assistant, system, thinking, goal_created, goal_processing, goal_complete, directive_preview, directive_applied, directive_rejected, error
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SendMessageRequest(BaseModel):
    """Request body for posting a message."""
    type: str = "user"
    content: str
    metadata: dict = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    """Response for conversation endpoint."""
    messages: list[ConversationMessage]
    total: int
    has_more: bool = False
