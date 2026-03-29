"""v2.0 Decomposition API — work units, approval, and coherence analysis.

Layer 1 endpoints for the decomposition review workflow.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.work_unit.compute_environment import EnvironmentStatus
from services.events.event_bus import get_event_bus
from services.events.event_types import DecompositionApproved

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decomposition", tags=["decomposition"])


# -- Response models --

class WorkUnitResponse(BaseModel):
    id: str
    project_id: str
    goal_ref: str
    description: str
    status: str
    formal_spec: dict = Field(default_factory=dict)
    verification_criteria: dict = Field(default_factory=dict)
    context_package: dict = Field(default_factory=dict)
    independence: dict = Field(default_factory=dict)


class WorkUnitsListResponse(BaseModel):
    work_units: List[WorkUnitResponse] = Field(default_factory=list)
    count: int = 0


class RuntimeRequirementResponse(BaseModel):
    name: str
    version: Optional[str] = None
    reason: str = ""
    install_cmd: Optional[str] = None


class ComputeEnvironmentResponse(BaseModel):
    id: str
    project_id: str
    status: str = "proposed"
    requirements: List[RuntimeRequirementResponse] = Field(default_factory=list)
    base_image: str = ""
    dockerfile_content: str = ""
    work_unit_ids: List[str] = Field(default_factory=list)
    image_tag: Optional[str] = None


class CoherenceInsightResponse(BaseModel):
    id: str
    type: str
    severity: str
    title: str
    description: str
    sources: list = Field(default_factory=list)
    suggestion: str = ""
    affected_units: list = Field(default_factory=list)


class CoherenceResponse(BaseModel):
    insights: List[CoherenceInsightResponse] = Field(default_factory=list)
    goals_analyzed: int = 0


# -- Endpoints --

@router.get("/{goal_id}/work-units", response_model=WorkUnitsListResponse)
async def get_work_units(goal_id: str):
    """Get all work units for a goal's decomposition.

    Returns the formally specified work units with target files,
    interface contracts, verification criteria, and independence
    assertions.
    """
    # TODO: wire to persistent storage (Redis or Git-backed)
    # For now, return empty — the frontend handles this gracefully
    return WorkUnitsListResponse(work_units=[], count=0)


@router.post("/{goal_id}/approve")
async def approve_decomposition(goal_id: str):
    """Approve a decomposition — transition work units from draft to ready.

    This is the human approval gate. Once approved, work units enter
    the dispatch queue for execution.
    """
    bus = get_event_bus()

    # TODO: load work units, validate all are in draft, transition to ready
    # For now, emit the event
    await bus.publish(DecompositionApproved(
        project_id="",  # Will be resolved from goal lookup
        goal_id=goal_id,
        work_unit_ids=[],
    ))

    return {"approved": True, "goal_id": goal_id}


@router.get("/{goal_id}/environment", response_model=ComputeEnvironmentResponse)
async def get_compute_environment(goal_id: str):
    """Get the compute environment spec for a goal's work units.

    Shows detected runtime requirements, generated Dockerfile, and
    approval status. This is a first-class artifact of planning —
    review and approve before execution.
    """
    # TODO: wire to environment analyzer + storage
    return ComputeEnvironmentResponse(
        id=f"env-{goal_id}",
        project_id="",
        status="proposed",
        requirements=[],
        dockerfile_content="",
    )


@router.post("/{goal_id}/environment/approve")
async def approve_environment(goal_id: str):
    """Approve a compute environment spec for building.

    Human gate — nothing gets built until explicitly approved.
    """
    # TODO: wire to environment status update + build trigger
    return {"approved": True, "goal_id": goal_id}


@router.get("/coherence/{project_id}", response_model=CoherenceResponse)
async def get_coherence_insights(project_id: str):
    """Get goal coherence analysis for a project.

    Detects inconsistencies, implicit requirements, scope drift,
    and gaps across all goals and steering input.
    """
    # TODO: wire to coherence analyzer service
    return CoherenceResponse(insights=[], goals_analyzed=0)
