"""Decision traceability API endpoints for querying planning decisions.

Provides REST endpoints for querying decision traces by project,
decision type, or specific work item. Supports the "why is this task
here?" query pattern.

Reference: docs/work_management_framework.md — Section 11
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from models.decision_trace import DecisionPointType, DecisionTrace
from services.decision_trace_service import (
    DecisionTraceService,
    get_decision_trace_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/decision-traces", tags=["decision-traces"])


class DecisionTraceListResponse(BaseModel):
    """Response containing a list of decision traces."""
    traces: List[DecisionTrace] = Field(default_factory=list)
    count: int = Field(default=0)


class DecisionTraceChainResponse(BaseModel):
    """Response containing a chain of related decision traces."""
    chain: List[DecisionTrace] = Field(default_factory=list)
    depth: int = Field(default=0)


@router.get(
    "/projects/{project_id}",
    response_model=DecisionTraceListResponse,
)
async def get_project_traces(
    project_id: str,
    decision_type: Optional[DecisionPointType] = Query(
        default=None,
        description="Filter by decision type"
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Max traces to return"),
    service: DecisionTraceService = Depends(get_decision_trace_service),
):
    """Get decision traces for a project.

    Returns traces ordered by most recent first. Optionally filter
    by decision type.
    """
    traces = await service.get_traces(
        project_id=project_id,
        decision_type=decision_type,
        limit=limit,
    )
    return DecisionTraceListResponse(traces=traces, count=len(traces))


@router.get(
    "/projects/{project_id}/items/{item_id}",
    response_model=DecisionTraceListResponse,
)
async def get_item_traces(
    project_id: str,
    item_id: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max traces to return"),
    service: DecisionTraceService = Depends(get_decision_trace_service),
):
    """Get decision traces affecting a specific work item.

    Answers the question: "Why is this task here?"
    """
    traces = await service.get_traces_for_item(
        project_id=project_id,
        item_id=item_id,
        limit=limit,
    )
    return DecisionTraceListResponse(traces=traces, count=len(traces))


@router.get(
    "/projects/{project_id}/traces/{trace_id}",
    response_model=DecisionTrace,
)
async def get_trace(
    project_id: str,
    trace_id: str,
    service: DecisionTraceService = Depends(get_decision_trace_service),
):
    """Get a specific decision trace by ID."""
    trace = await service.get_trace_by_id(
        project_id=project_id,
        trace_id=trace_id,
    )
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return trace


@router.get(
    "/projects/{project_id}/traces/{trace_id}/chain",
    response_model=DecisionTraceChainResponse,
)
async def get_trace_chain(
    project_id: str,
    trace_id: str,
    max_depth: int = Query(default=10, ge=1, le=50, description="Max chain depth"),
    service: DecisionTraceService = Depends(get_decision_trace_service),
):
    """Follow the chain of related traces from a starting trace.

    Useful for understanding the full decision path.
    """
    chain = await service.get_trace_chain(
        project_id=project_id,
        trace_id=trace_id,
        max_depth=max_depth,
    )
    if not chain:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return DecisionTraceChainResponse(chain=chain, depth=len(chain))
