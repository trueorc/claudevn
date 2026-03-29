"""v2.0 Dispatch API — queue visibility and active executions.

Layer 2 endpoints for execution observability.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


# -- Response models --

class QueueEntryResponse(BaseModel):
    work_unit_id: str
    goal_id: str
    project_id: str
    priority: int = 0
    description: str = ""


class ActiveExecutionResponse(BaseModel):
    work_unit_id: str
    goal_id: str
    project_id: str
    instance_id: str
    branch: str = ""
    description: str = ""


# -- Endpoints --

@router.get("/queue", response_model=List[QueueEntryResponse])
async def get_dispatch_queue():
    """Get the current dispatch queue.

    Returns work units waiting for execution, ordered by
    topological priority (dependency DAG order).
    """
    # TODO: wire to DispatchQueue
    return []


@router.get("/active", response_model=List[ActiveExecutionResponse])
async def get_active_executions():
    """Get currently executing work units.

    Shows which Claude Code instances are working on what.
    """
    # TODO: wire to Dispatcher.active_units
    return []
