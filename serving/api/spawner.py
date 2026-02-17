"""API endpoints for Compute Spawner."""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from models.compute_spawner import (
    SpawnRequest, SpawnResponse, SpawnedCompute, ComputeState,
    ComputeListResponse, StopRequest, ComputeMetrics
)
from services.compute_spawner import get_compute_spawner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spawner", tags=["spawner"])


# ============ Stats Endpoint (must be before /{compute_id}) ============

@router.get("/stats")
async def get_stats():
    """Get spawner statistics.

    Returns:
        Statistics about spawned compute instances
    """
    spawner = get_compute_spawner()
    result = await spawner.list_instances()

    return {
        "total_instances": result.total,
        "by_state": result.by_state,
        "running": result.by_state.get("running", 0),
        "idle": result.by_state.get("idle", 0),
        "stopped": result.by_state.get("stopped", 0)
    }


# ============ Spawn Endpoints ============

@router.post("/spawn", response_model=SpawnResponse, status_code=status.HTTP_201_CREATED)
async def spawn_compute(request: SpawnRequest):
    """Spawn a new compute instance.

    Creates a new Claude Code instance with the specified skills
    and capabilities. The instance will connect to Serving via MCP
    and can be assigned work immediately.

    Args:
        request: Spawn configuration

    Returns:
        Spawn response with instance details and API key

    Raises:
        HTTPException: If spawn fails
    """
    spawner = get_compute_spawner()

    try:
        response = await spawner.spawn(request)
        logger.info(f"Spawned compute instance: {response.compute_id}")
        return response
    except Exception as e:
        logger.error(f"Failed to spawn compute: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to spawn compute instance: {str(e)}"
        )


@router.get("", response_model=ComputeListResponse)
async def list_instances(
    state: Optional[str] = Query(None, description="Filter by state")
):
    """List all compute instances.

    Args:
        state: Optional state filter

    Returns:
        List of compute instances with statistics
    """
    spawner = get_compute_spawner()

    compute_state = None
    if state:
        try:
            compute_state = ComputeState(state)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state: {state}. Must be one of: {[s.value for s in ComputeState]}"
            )

    return await spawner.list_instances(state=compute_state)


@router.get("/{compute_id}", response_model=SpawnedCompute)
async def get_instance(compute_id: str):
    """Get a specific compute instance.

    Args:
        compute_id: Compute instance ID

    Returns:
        Compute instance details

    Raises:
        HTTPException: If instance not found
    """
    spawner = get_compute_spawner()
    instance = await spawner.get_instance(compute_id)

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compute instance '{compute_id}' not found"
        )

    return instance


@router.get("/{compute_id}/metrics", response_model=ComputeMetrics)
async def get_metrics(compute_id: str):
    """Get metrics for a compute instance.

    Args:
        compute_id: Compute instance ID

    Returns:
        Instance metrics

    Raises:
        HTTPException: If instance not found
    """
    spawner = get_compute_spawner()
    metrics = await spawner.get_metrics(compute_id)

    if not metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Compute instance '{compute_id}' not found"
        )

    return metrics


@router.post("/{compute_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_instance(
    compute_id: str,
    force: bool = Query(False, description="Force kill if graceful stop fails"),
    timeout: int = Query(30, ge=1, le=300, description="Seconds to wait for graceful stop")
):
    """Stop a compute instance.

    Args:
        compute_id: Compute instance ID
        force: Force kill if graceful stop fails
        timeout: Seconds to wait for graceful stop

    Raises:
        HTTPException: If stop fails
    """
    spawner = get_compute_spawner()

    request = StopRequest(
        compute_id=compute_id,
        force=force,
        timeout=timeout
    )

    stopped = await spawner.stop(request)

    if not stopped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to stop compute instance '{compute_id}'"
        )


@router.post("/stop-all", status_code=status.HTTP_204_NO_CONTENT)
async def stop_all():
    """Stop all compute instances.

    Gracefully shuts down all running compute instances.
    """
    spawner = get_compute_spawner()
    await spawner.shutdown()
