"""Network capacity management API endpoints."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config import get_config
from git.redis_client import get_redis_client
from services.registry_service import ComputeRegistry, get_compute_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["network"])

REDIS_KEY_MAX_COMPUTE = "settings:max_compute_instances"


class CapacityResponse(BaseModel):
    """Network capacity status response."""
    max_compute_instances: int = Field(description="Maximum allowed instances (0 = unlimited)")
    current_instances: int = Field(description="Current registered instance count")
    available_slots: int = Field(description="Remaining slots (-1 = unlimited)")


class UpdateCapacityRequest(BaseModel):
    """Request to update network capacity limit."""
    max_compute_instances: int = Field(ge=0, description="New maximum (0 = unlimited)")


@router.get("/capacity", response_model=CapacityResponse)
async def get_capacity(
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Get current network capacity status."""
    config = get_config()
    max_instances = config.network_capacity.max_compute_instances
    current = registry.get_instance_count()

    if max_instances == 0:
        available = -1  # unlimited
    else:
        available = max(0, max_instances - current)

    return CapacityResponse(
        max_compute_instances=max_instances,
        current_instances=current,
        available_slots=available,
    )


@router.put("/capacity", response_model=CapacityResponse)
async def update_capacity(
    body: UpdateCapacityRequest,
    registry: ComputeRegistry = Depends(get_compute_registry),
):
    """Update the network capacity limit at runtime.

    Persists the setting to Redis so it survives restarts.
    Falls back to the MAX_COMPUTE_INSTANCES env var if Redis is unavailable.
    """
    config = get_config()
    config.network_capacity.max_compute_instances = body.max_compute_instances

    # Persist to Redis
    redis_client = get_redis_client()
    if redis_client:
        try:
            await redis_client._redis.set(
                redis_client._key(REDIS_KEY_MAX_COMPUTE),
                str(body.max_compute_instances),
            )
        except Exception as e:
            logger.warning(f"Failed to persist max_compute_instances to Redis: {e}")

    logger.info(f"Updated max compute instances to {body.max_compute_instances}")

    current = registry.get_instance_count()
    max_instances = body.max_compute_instances

    if max_instances == 0:
        available = -1
    else:
        available = max(0, max_instances - current)

    return CapacityResponse(
        max_compute_instances=max_instances,
        current_instances=current,
        available_slots=available,
    )
