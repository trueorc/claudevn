"""Reconciliation models for the unified project plan.

Tracks how directives reshape the project plan — which units
get superseded, which conflicts arise, and how they're resolved.
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class SupersessionRecord(BaseModel):
    """One unit superseding another during plan reconciliation."""
    old_unit_id: str
    new_unit_id: str
    reason: str = Field(description="file_overlap | llm_determined | user_action")
    overlapping_files: List[str] = Field(default_factory=list)


class ConflictRecord(BaseModel):
    """A detected conflict between work units requiring user review."""
    conflict_id: str
    unit_ids: List[str] = Field(description="The conflicting unit IDs")
    description: str
    severity: str = Field(default="medium", description="high | medium | low")
    resolution_hint: Optional[str] = None
    resolved: bool = False
    resolved_by: Optional[str] = None
    resolution: Optional[str] = Field(
        default=None,
        description="supersede | keep_both | merge — set when resolved"
    )


class ReconciliationResult(BaseModel):
    """Result of reconciling a new directive against the existing project plan."""
    project_id: str
    directive_id: str
    supersessions: List[SupersessionRecord] = Field(default_factory=list)
    conflicts: List[ConflictRecord] = Field(default_factory=list)
    new_unit_ids: List[str] = Field(default_factory=list)
    retained_unit_ids: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def superseded_count(self) -> int:
        return len(self.supersessions)

    @property
    def conflict_count(self) -> int:
        return len([c for c in self.conflicts if not c.resolved])

    @property
    def has_unresolved_conflicts(self) -> bool:
        return any(not c.resolved for c in self.conflicts)
