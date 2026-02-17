"""API endpoints for worker feedback patterns and signals.

Provides endpoints for:
- Listing detected feedback patterns for a project
- Listing raw feedback signals with optional type filter
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from models.feedback import FeedbackPattern, FeedbackSignal, FeedbackType
from services.feedback_aggregation_service import (
    get_feedback_aggregation_service,
    FeedbackAggregationService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackPatternsResponse(BaseModel):
    """Response for listing feedback patterns."""
    project_id: str
    patterns: List[FeedbackPattern]
    total: int
    by_type: dict = Field(default_factory=dict)


class FeedbackSignalsResponse(BaseModel):
    """Response for listing feedback signals."""
    project_id: str
    signals: List[FeedbackSignal]
    total: int


def _get_service() -> FeedbackAggregationService:
    """Get the feedback aggregation service, raising 503 if unavailable."""
    try:
        return get_feedback_aggregation_service()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feedback aggregation service not available",
        )


@router.get("/{project_id}/patterns", response_model=FeedbackPatternsResponse)
async def list_patterns(project_id: str):
    """List detected feedback patterns for a project.

    Returns patterns with summary statistics for building the UI.
    """
    service = _get_service()

    patterns = await service.get_patterns(project_id)

    by_type = {}
    for p in patterns:
        by_type[p.feedback_type.value] = by_type.get(p.feedback_type.value, 0) + 1

    return FeedbackPatternsResponse(
        project_id=project_id,
        patterns=patterns,
        total=len(patterns),
        by_type=by_type,
    )


@router.get("/{project_id}/signals", response_model=FeedbackSignalsResponse)
async def list_signals(
    project_id: str,
    feedback_type: Optional[str] = Query(None, description="Filter by feedback type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum signals to return"),
):
    """List feedback signals for a project with optional type filter."""
    service = _get_service()

    ft = None
    if feedback_type:
        try:
            ft = FeedbackType(feedback_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid feedback type: {feedback_type}",
            )

    signals = await service.get_signals(project_id, feedback_type=ft, limit=limit)

    return FeedbackSignalsResponse(
        project_id=project_id,
        signals=signals,
        total=len(signals),
    )
