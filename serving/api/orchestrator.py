"""API endpoints for Work Orchestrator management."""

import logging
from fastapi import APIRouter, HTTPException, status

from services.work_orchestrator import get_work_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/status")
async def get_orchestrator_status():
    """Get work orchestrator status and statistics.

    Returns:
        Orchestrator status and stats
    """
    orchestrator = get_work_orchestrator()

    if not orchestrator:
        return {
            "status": "not_initialized",
            "message": "Work orchestrator is not initialized"
        }

    stats = orchestrator.get_stats()

    return {
        "status": "running" if stats["running"] else "stopped",
        "paused": stats.get("paused", False),
        "stats": stats
    }


@router.post("/pause")
async def pause_orchestrator():
    """Pause the work orchestrator.

    Stops spawning new compute instances while keeping the service running.

    Returns:
        Confirmation of pause
    """
    orchestrator = get_work_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Work orchestrator is not initialized"
        )

    if not orchestrator.is_running():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Work orchestrator is not running"
        )

    await orchestrator.pause()

    return {
        "status": "paused",
        "message": "Work orchestrator paused"
    }


@router.post("/resume")
async def resume_orchestrator():
    """Resume the work orchestrator.

    Resumes spawning compute instances for pending work.

    Returns:
        Confirmation of resume
    """
    orchestrator = get_work_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Work orchestrator is not initialized"
        )

    if not orchestrator.is_running():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Work orchestrator is not running"
        )

    await orchestrator.resume()

    return {
        "status": "running",
        "message": "Work orchestrator resumed"
    }


@router.post("/trigger")
async def trigger_orchestration():
    """Trigger an immediate orchestration cycle.

    Forces the orchestrator to process pending work immediately
    without waiting for the next poll interval.

    Returns:
        Results of the orchestration cycle
    """
    orchestrator = get_work_orchestrator()

    if not orchestrator:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Work orchestrator is not initialized"
        )

    if not orchestrator.is_running():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Work orchestrator is not running"
        )

    result = await orchestrator.trigger_immediate()

    return result
