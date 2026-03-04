"""API routes for compute lifecycle timing instrumentation."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from models.timing import (
    AggregateStats,
    TimingDashboardResponse,
    WorkItemTiming,
)
from services.timing_service import get_timing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/timing", tags=["timing"])


@router.get(
    "/dashboard",
    response_model=TimingDashboardResponse,
    summary="Get timing dashboard data",
)
async def get_dashboard(
    limit: int = Query(20, ge=1, le=100, description="Number of recent work items"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
):
    """Get combined dashboard with recent work item timings and aggregate stats."""
    service = get_timing_service()
    return await service.get_dashboard(limit, project_id=project_id)


@router.get(
    "/work/{work_id}/{instance_id}",
    response_model=Optional[WorkItemTiming],
    summary="Get timing for a specific work item",
)
async def get_work_item_timing(work_id: str, instance_id: str):
    """Get per-phase timing breakdown for a specific work item and instance."""
    service = get_timing_service()
    timing = await service.get_work_item_timing(work_id, instance_id)
    if timing is None:
        return None
    return timing


@router.get(
    "/aggregates",
    response_model=list[AggregateStats],
    summary="Get aggregate timing statistics",
)
async def get_aggregate_stats(
    limit: int = Query(100, ge=1, le=1000, description="Recent work items to aggregate over"),
):
    """Get aggregate stats (avg, p50, p95, p99) per phase across recent work items."""
    service = get_timing_service()
    return await service.get_aggregate_stats(limit)


@router.get(
    "/recent",
    response_model=list[WorkItemTiming],
    summary="Get recent work item timings",
)
async def get_recent_timings(
    limit: int = Query(50, ge=1, le=200, description="Number of items"),
):
    """Get timing data for recent work items, most recent first."""
    service = get_timing_service()
    return await service.get_recent_timings(limit)
