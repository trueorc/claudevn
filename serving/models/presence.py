"""Presence models for user online status and activity awareness."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class UserPresence(BaseModel):
    user_id: str
    project_id: str = ""
    project_name: Optional[str] = None
    display_name: str = "Unknown"
    status: str = "online"  # online, idle, offline
    current_view: Optional[str] = None  # dashboard, backlog, plan, etc.
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HeartbeatRequest(BaseModel):
    current_view: Optional[str] = None
    project_name: Optional[str] = None


class PresenceResponse(BaseModel):
    users: list[UserPresence]
