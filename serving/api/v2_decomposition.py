"""v2.0 Decomposition API — work units, pipeline status, approval, coherence.

Layer 1 endpoints backed by Redis storage from the decomposition pipeline.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.events.event_bus import get_event_bus
from services.events.event_types import DecompositionApproved

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decomposition", tags=["decomposition"])


async def _resolve_project_id(goal_id: str) -> str:
    """Look up project_id from a goal."""
    try:
        from services.work_map_service import get_work_map_service
        wm = get_work_map_service()
        goal = await wm.get_goal(goal_id)
        return goal.project_id if goal else ""
    except Exception:
        return ""


@router.get("/{goal_id}/work-units")
async def get_work_units(goal_id: str):
    """Get all work units for a goal's decomposition."""
    from services.decomposition.storage import get_work_units as fetch_units
    project_id = await _resolve_project_id(goal_id)
    units = await fetch_units(project_id, goal_id)
    return {"work_units": units, "count": len(units)}


@router.get("/{goal_id}/pipeline")
async def get_pipeline_status(goal_id: str):
    """Get the full pipeline result — steps with status, work units, environment.

    This is what the Plan page uses to show pipeline step progress.
    """
    from services.decomposition.storage import get_pipeline_result
    project_id = await _resolve_project_id(goal_id)
    result = await get_pipeline_result(project_id, goal_id)
    if not result:
        return {"steps": [], "work_units": [], "success": False, "error": "No pipeline result"}
    return result


@router.post("/{goal_id}/approve")
async def approve_decomposition(goal_id: str):
    """Approve a decomposition — transition work units from draft to ready."""
    project_id = await _resolve_project_id(goal_id)
    bus = get_event_bus()
    await bus.publish(DecompositionApproved(
        project_id=project_id,
        goal_id=goal_id,
        work_unit_ids=[],
    ))
    return {"approved": True, "goal_id": goal_id}


@router.get("/{goal_id}/environment")
async def get_compute_environment(goal_id: str):
    """Get the compute environment spec for a goal's work units."""
    from services.decomposition.storage import get_environment, get_project_environment
    project_id = await _resolve_project_id(goal_id)

    env = await get_environment(project_id, goal_id)
    if env:
        return env

    # Fall back to project-level environment
    env = await get_project_environment(project_id or goal_id)
    if env:
        return env

    return {
        "id": f"env-{goal_id}", "project_id": project_id,
        "status": "proposed", "requirements": [],
        "base_image": "", "dockerfile_content": "", "work_unit_ids": [],
    }


@router.post("/{goal_id}/environment/approve")
async def approve_environment(goal_id: str):
    """Approve a compute environment — writes Dockerfile + metadata to disk.

    After approval, run ./compute-envs/start.sh <project_name> on the host
    to build and start the compute container.
    """
    from services.decomposition.storage import get_environment
    from services.decomposition.provisioner import write_environment

    project_id = await _resolve_project_id(goal_id)

    # Get the environment spec
    env = await get_environment(project_id, goal_id)
    if not env:
        raise HTTPException(status_code=404, detail="No environment spec found for this goal")

    # Get project name for the directory
    try:
        from services.work_map_service import get_work_map_service
        wm = get_work_map_service()
        goal = await wm.get_goal(goal_id)
        from services.project_service import get_project_service
        ps = get_project_service()
        project = await ps.get_project(goal.project_id) if goal else None
        project_name = project.name if project else project_id
    except Exception:
        project_name = project_id

    # Determine a description from requirements
    runtimes = [r["name"] for r in env.get("requirements", []) if r["name"] not in ("python-packages", "node-packages")]
    desc = "_".join(runtimes[:3]) if runtimes else "default"

    # Write to mounted volume
    env_dir = await write_environment(
        project_name=project_name,
        project_id=project_id,
        goal_id=goal_id,
        dockerfile_content=env.get("dockerfile_content", ""),
        requirements=env.get("requirements", []),
        description=desc,
    )

    return {
        "approved": True,
        "goal_id": goal_id,
        "environment_dir": env_dir,
        "instructions": f"Run: ./compute-envs/start.sh {project_name.lower().replace(' ', '_')}",
    }


@router.get("/coherence/{project_id}")
async def get_coherence_insights(project_id: str):
    """Get goal coherence analysis for a project."""
    return {"insights": [], "goals_analyzed": 0}
