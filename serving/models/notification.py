"""Models for system notifications and alerts.

Lightweight in-memory notification feed for surfacing system events
(goal completions, status changes, etc.) in the serving UI.

Reference: Issue #547
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class NotificationLevel(str, Enum):
    """Severity level for notifications."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationCategory(str, Enum):
    """Category of system event that generated the notification."""
    GOAL = "goal"
    ISSUE = "issue"
    WORK = "work"
    COMPUTE = "compute"
    SYSTEM = "system"


class Notification(BaseModel):
    """A single system notification."""
    notification_id: str = Field(..., description="Unique notification ID")
    level: NotificationLevel = Field(default=NotificationLevel.INFO)
    category: NotificationCategory = Field(default=NotificationCategory.SYSTEM)
    title: str = Field(..., description="Short notification title")
    message: str = Field(default="", description="Detailed message")
    project_id: Optional[str] = Field(default=None)
    entity_id: Optional[str] = Field(
        default=None, description="ID of the related entity (goal, issue, etc.)"
    )
    read: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class NotificationListResponse(BaseModel):
    """Response for listing notifications."""
    items: List[Notification] = Field(default_factory=list)
    total: int = Field(default=0)
    unread_count: int = Field(default=0)
