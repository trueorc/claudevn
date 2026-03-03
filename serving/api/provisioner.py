"""API endpoints for compute provisioner management."""

import logging
from typing import List

from fastapi import APIRouter

from services.compute_provisioner import (
    get_provisioner_registry,
    ProviderInfo,
    ComputeImage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/provisioner", tags=["provisioner"])


@router.get("/providers", response_model=List[ProviderInfo])
async def list_providers():
    """List all registered compute provisioners and their status."""
    registry = get_provisioner_registry()
    return registry.list_providers()


@router.get("/images", response_model=List[ComputeImage])
async def list_images():
    """List available compute images from all enabled providers."""
    registry = get_provisioner_registry()
    return await registry.list_all_images()


@router.post("/providers/{name}/enable")
async def enable_provider(name: str):
    """Enable a provisioner by name."""
    registry = get_provisioner_registry()
    if registry.enable(name):
        return {"status": "enabled", "provider": name}
    return {"status": "not_found", "provider": name}


@router.post("/providers/{name}/disable")
async def disable_provider(name: str):
    """Disable a provisioner by name."""
    registry = get_provisioner_registry()
    if registry.disable(name):
        return {"status": "disabled", "provider": name}
    return {"status": "not_found", "provider": name}
