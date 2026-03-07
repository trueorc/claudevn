"""User models for registration and authentication."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User role in the network."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(BaseModel):
    """A registered user in the ClaudeVN network."""
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique user ID")
    username: str = Field(..., description="Unique display name")
    email: Optional[str] = Field(None, description="Optional contact email")
    role: UserRole = Field(default=UserRole.MEMBER, description="User role")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")


class RegisterRequest(BaseModel):
    """Request to register a new user."""
    username: str = Field(..., min_length=2, max_length=50, description="Display name")
    email: Optional[str] = Field(None, description="Optional contact email")


class RegisterResponse(BaseModel):
    """Response for user registration."""
    user_id: str
    username: str
    role: UserRole
    token: str = Field(..., description="Session JWT token")


class LoginRequest(BaseModel):
    """Request to log in."""
    username: str
    password: Optional[str] = Field(None, description="Password (required in local auth mode)")


class LoginResponse(BaseModel):
    """Response for login."""
    user_id: str
    username: str
    role: UserRole
    token: str = Field(..., description="Session JWT token")


class UserProfileResponse(BaseModel):
    """Response for user profile."""
    user_id: str
    username: str
    email: Optional[str] = None
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None


class UpdateProfileRequest(BaseModel):
    """Request to update user profile."""
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[str] = None
