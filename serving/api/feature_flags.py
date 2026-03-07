"""Feature flags API router.

Provides REST endpoints for feature flag management:
- GET    /feature-flags          - List all flags
- GET    /feature-flags/{name}   - Get a single flag
- POST   /feature-flags          - Create a new flag
- PUT    /feature-flags/{name}   - Toggle a flag
- DELETE /feature-flags/{name}   - Delete a flag
"""

from fastapi import APIRouter, HTTPException
from models.feature_flag import (
    CreateFeatureFlagRequest,
    FeatureFlagListResponse,
    FeatureFlagResponse,
    ToggleFeatureFlagRequest,
)
from services.feature_flag_service import get_feature_flag_service

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])


def _get_service():
    """Get the feature flag service or raise 503."""
    service = get_feature_flag_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Feature flag service not available")
    return service


@router.get("", response_model=FeatureFlagListResponse)
async def list_flags():
    """List all feature flags."""
    service = _get_service()
    flags = await service.list_flags()
    return {"flags": flags}


@router.get("/{name}", response_model=FeatureFlagResponse)
async def get_flag(name: str):
    """Get a single feature flag by name."""
    service = _get_service()
    flag = await service.get_flag(name)
    if flag is None:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found")
    return flag


@router.post("", response_model=FeatureFlagResponse, status_code=201)
async def create_flag(body: CreateFeatureFlagRequest):
    """Create a new feature flag."""
    service = _get_service()
    try:
        flag = await service.create_flag(
            name=body.name,
            description=body.description,
            enabled=body.enabled,
            category=body.category,
        )
        return flag
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/{name}", response_model=FeatureFlagResponse)
async def toggle_flag(name: str, body: ToggleFeatureFlagRequest):
    """Toggle a feature flag on or off."""
    service = _get_service()
    flag = await service.toggle_flag(name, body.enabled)
    if flag is None:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found")
    return flag


@router.delete("/{name}", status_code=204)
async def delete_flag(name: str):
    """Delete a feature flag."""
    service = _get_service()
    deleted = await service.delete_flag(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Feature flag '{name}' not found")
