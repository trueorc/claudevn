"""Feature flag models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FlagCategory(str, Enum):
    """Feature flag category."""
    UI = "ui"
    BACKEND = "backend"
    EXPERIMENTAL = "experimental"


class FeatureFlag(BaseModel):
    """A feature flag definition."""
    name: str = Field(..., description="Unique flag identifier (kebab-case)")
    description: str = Field("", description="Human-readable description")
    enabled: bool = Field(False, description="Whether the flag is active")
    category: FlagCategory = Field(FlagCategory.EXPERIMENTAL, description="Flag category")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureFlagResponse(BaseModel):
    """Response for a single feature flag."""
    name: str
    description: str
    enabled: bool
    category: FlagCategory
    created_at: datetime
    updated_at: datetime


class FeatureFlagListResponse(BaseModel):
    """Response for listing feature flags."""
    flags: list[FeatureFlagResponse]


class CreateFeatureFlagRequest(BaseModel):
    """Request to create a feature flag."""
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str = Field("", max_length=500)
    enabled: bool = Field(False)
    category: FlagCategory = Field(FlagCategory.EXPERIMENTAL)


class ToggleFeatureFlagRequest(BaseModel):
    """Request to toggle a feature flag."""
    enabled: bool
