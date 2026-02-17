"""API endpoints for characterization pipeline.

Provides endpoints for:
- Viewing characterization results for a project
- Getting a specific item's characterization
- Characterization statistics
- Manual characterization triggers
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from models.characterization import (
    BatchCharacterizationResponse,
    CharacterizationRequest,
    CharacterizationResult,
    CharacterizationStatus,
)
from services.characterization_service import get_characterization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/characterization", tags=["characterization"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CharacterizationTriggerItem(BaseModel):
    """Single item for manual characterization trigger."""
    item_id: str = Field(..., description="Work item ID (e.g., issue_id)")
    title: str = Field(..., description="Work item title")
    description: str = Field(default="", description="Work item description")
    issue_type_hint: Optional[str] = Field(None, description="Hint from decomposer")
    area_hint: Optional[str] = Field(None, description="Area hint from decomposer")


class CharacterizationTriggerRequest(BaseModel):
    """Request to manually trigger characterization for items."""
    project_id: str = Field(..., description="Project context")
    items: List[CharacterizationTriggerItem] = Field(
        ..., min_length=1, description="Items to characterize"
    )
    source_goal_id: Optional[str] = Field(None, description="Source goal if from decomposition")


class CharacterizationListResponse(BaseModel):
    """Response for listing characterization results."""
    project_id: str
    results: List[CharacterizationResult]
    total: int
    stats: Dict[str, int]


class CharacterizationStatsResponse(BaseModel):
    """Response for characterization statistics."""
    project_id: str
    stats: Dict[str, int]


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/{project_id}", response_model=CharacterizationListResponse)
async def list_characterizations(
    project_id: str,
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by status"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items"),
):
    """List characterization results for a project.

    Returns all characterization results, optionally filtered by status.
    """
    service = get_characterization_service()
    results = await service.get_results_for_project(project_id)

    if status_filter:
        try:
            target_status = CharacterizationStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: "
                       f"{[s.value for s in CharacterizationStatus]}",
            )
        results = [r for r in results if r.status == target_status]

    results = results[:limit]
    stats = await service.get_stats(project_id)

    return CharacterizationListResponse(
        project_id=project_id,
        results=results,
        total=len(results),
        stats=stats,
    )


@router.get("/{project_id}/stats", response_model=CharacterizationStatsResponse)
async def get_characterization_stats(project_id: str):
    """Get characterization pipeline statistics for a project."""
    service = get_characterization_service()
    stats = await service.get_stats(project_id)

    return CharacterizationStatsResponse(
        project_id=project_id,
        stats=stats,
    )


@router.get(
    "/{project_id}/{item_id}",
    response_model=CharacterizationResult,
)
async def get_characterization(project_id: str, item_id: str):
    """Get characterization result for a specific work item."""
    service = get_characterization_service()
    result = await service.get_result(project_id, item_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No characterization found for item '{item_id}' "
                   f"in project '{project_id}'",
        )

    return result


@router.post(
    "/trigger",
    response_model=BatchCharacterizationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_characterization(request: CharacterizationTriggerRequest):
    """Manually trigger characterization for work items.

    Creates pending characterization entries and spawns a compute instance
    to perform AI-powered characterization. Returns immediately with pending
    status; poll individual results for completion.
    """
    service = get_characterization_service()

    # Convert to CharacterizationRequest models
    char_items = [
        CharacterizationRequest(
            item_id=item.item_id,
            project_id=request.project_id,
            title=item.title,
            description=item.description,
            issue_type_hint=item.issue_type_hint,
            area_hint=item.area_hint,
        )
        for item in request.items
    ]

    try:
        response = await service.characterize_items(
            project_id=request.project_id,
            items=char_items,
            source_goal_id=request.source_goal_id,
        )
        return response
    except RuntimeError as e:
        # No compute available — return batch with pending entries
        logger.warning(f"Characterization compute unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
