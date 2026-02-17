"""API endpoints for conflict surfacing and resolution.

Provides endpoints for:
- Listing conflicts for a project (with filters)
- Getting a specific conflict by ID
- Resolving a conflict with user response
- Getting conflict count (for notification badge)
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from models.conflict import (
    ConflictReport,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    UserResponse,
    UserResponseType,
)
from services.conflict_detection_service import (
    get_conflict_detection_service,
    ConflictDetectionService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


class ConflictListResponse(BaseModel):
    """Response for listing conflicts."""
    project_id: str
    conflicts: List[ConflictReport]
    total: int
    surfaceable_count: int = 0
    by_severity: dict = Field(default_factory=dict)
    by_type: dict = Field(default_factory=dict)


class ConflictCountResponse(BaseModel):
    """Lightweight response for notification badge."""
    project_id: str
    total: int
    surfaceable: int
    critical: int
    high: int


class ResolveConflictRequest(BaseModel):
    """Request body for resolving a conflict."""
    response_type: UserResponseType
    description: str = ""
    affected_goal_ids: List[str] = Field(default_factory=list)


def _get_service() -> ConflictDetectionService:
    """Get the conflict detection service, raising 503 if unavailable."""
    try:
        return get_conflict_detection_service()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conflict detection service not available",
        )


@router.get("/{project_id}", response_model=ConflictListResponse)
async def list_conflicts(
    project_id: str,
    conflict_type: Optional[str] = Query(None, description="Filter by conflict type"),
    conflict_status: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    surfaceable_only: bool = Query(
        False, description="Only return conflicts that should be surfaced"
    ),
    severity: Optional[str] = Query(None, description="Filter by severity"),
):
    """List conflicts for a project with optional filters.

    Returns conflicts with summary statistics for building the UI.
    """
    service = _get_service()

    ct = None
    if conflict_type:
        try:
            ct = ConflictType(conflict_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid conflict type: {conflict_type}",
            )

    cs = None
    if conflict_status:
        try:
            cs = ConflictStatus(conflict_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid conflict status: {conflict_status}",
            )

    conflicts = await service.get_conflicts(
        project_id=project_id,
        conflict_type=ct,
        status=cs,
        surfaceable_only=surfaceable_only,
    )

    # Apply severity filter (not supported natively by service)
    if severity:
        try:
            sev = ConflictSeverity(severity)
            conflicts = [c for c in conflicts if c.severity == sev]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity: {severity}",
            )

    # Build summary stats
    by_severity = {}
    by_type = {}
    surfaceable_count = 0
    for c in conflicts:
        by_severity[c.severity.value] = by_severity.get(c.severity.value, 0) + 1
        by_type[c.conflict_type.value] = by_type.get(c.conflict_type.value, 0) + 1
        if c.should_surface():
            surfaceable_count += 1

    return ConflictListResponse(
        project_id=project_id,
        conflicts=conflicts,
        total=len(conflicts),
        surfaceable_count=surfaceable_count,
        by_severity=by_severity,
        by_type=by_type,
    )


@router.get("/{project_id}/count", response_model=ConflictCountResponse)
async def get_conflict_count(project_id: str):
    """Get conflict counts for notification badge.

    Lightweight endpoint that returns only counts, not full conflict data.
    """
    service = _get_service()

    conflicts = await service.get_conflicts(project_id=project_id)

    surfaceable = sum(1 for c in conflicts if c.should_surface())
    critical = sum(1 for c in conflicts if c.severity == ConflictSeverity.CRITICAL)
    high = sum(1 for c in conflicts if c.severity == ConflictSeverity.HIGH)

    return ConflictCountResponse(
        project_id=project_id,
        total=len(conflicts),
        surfaceable=surfaceable,
        critical=critical,
        high=high,
    )


@router.get("/{project_id}/{conflict_id}", response_model=ConflictReport)
async def get_conflict(project_id: str, conflict_id: str):
    """Get a specific conflict by ID."""
    service = _get_service()

    conflicts = await service.get_conflicts(project_id=project_id)
    for conflict in conflicts:
        if conflict.conflict_id == conflict_id:
            return conflict

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Conflict '{conflict_id}' not found",
    )


@router.post(
    "/{project_id}/{conflict_id}/resolve",
    response_model=ConflictReport,
)
async def resolve_conflict(
    project_id: str,
    conflict_id: str,
    request: ResolveConflictRequest,
):
    """Resolve a conflict with a user response.

    Records the user's chosen resolution approach for the conflict.
    """
    service = _get_service()

    user_response = UserResponse(
        response_type=request.response_type,
        description=request.description,
        affected_goal_ids=request.affected_goal_ids,
    )

    result = await service.resolve_conflict(
        project_id=project_id,
        conflict_id=conflict_id,
        response=user_response,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict '{conflict_id}' not found",
        )

    return result
