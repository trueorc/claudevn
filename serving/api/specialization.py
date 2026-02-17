"""Worker specialization API endpoints."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from models.specialization import (
    SpecializationImbalance,
    SpecializationProfile,
    SpecializationProfileRequest,
    SpecializationSummary,
    UtilizationRecord,
)
from services.specialization_service import get_specialization_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/specialization", tags=["specialization"])


@router.get("/{project_id}/profiles", response_model=List[SpecializationProfile])
async def list_profiles(project_id: str):
    """List all specialization profiles for a project.

    Args:
        project_id: Project ID

    Returns:
        List of specialization profiles
    """
    service = get_specialization_service()
    return service.list_profiles(project_id)


@router.get(
    "/{project_id}/profiles/{compute_id}",
    response_model=SpecializationProfile,
)
async def get_profile(project_id: str, compute_id: str):
    """Get a specialization profile for a specific worker.

    Args:
        project_id: Project ID
        compute_id: Compute instance ID

    Returns:
        Specialization profile

    Raises:
        HTTPException: If profile not found
    """
    service = get_specialization_service()
    profile = service.get_profile(compute_id, project_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No specialization profile for {compute_id} in project {project_id}",
        )
    return profile


@router.put(
    "/{project_id}/profiles/{compute_id}",
    response_model=SpecializationProfile,
)
async def set_profile(
    project_id: str,
    compute_id: str,
    request: SpecializationProfileRequest,
):
    """Set or update a specialization profile for a worker.

    Args:
        project_id: Project ID
        compute_id: Compute instance ID
        request: Profile configuration

    Returns:
        Created or updated profile
    """
    service = get_specialization_service()
    profile = service.set_profile(
        compute_id=compute_id,
        project_id=project_id,
        cluster_ids=request.cluster_ids,
        preferred_work_types=request.preferred_work_types,
    )
    logger.info(f"Set specialization profile for {compute_id}: clusters={request.cluster_ids}")
    return profile


@router.delete("/{project_id}/profiles/{compute_id}")
async def remove_profile(project_id: str, compute_id: str):
    """Remove a specialization profile.

    Args:
        project_id: Project ID
        compute_id: Compute instance ID

    Returns:
        Success message

    Raises:
        HTTPException: If profile not found
    """
    service = get_specialization_service()
    removed = service.remove_profile(compute_id, project_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No specialization profile for {compute_id} in project {project_id}",
        )
    return {"status": "removed", "compute_id": compute_id, "project_id": project_id}


@router.get("/{project_id}/utilization")
async def get_utilization(project_id: str):
    """Get utilization summary per worker for a project.

    Args:
        project_id: Project ID

    Returns:
        Dict of compute_id -> utilization records
    """
    service = get_specialization_service()
    return service.get_utilization(project_id)


@router.get(
    "/{project_id}/imbalances",
    response_model=List[SpecializationImbalance],
)
async def get_imbalances(project_id: str):
    """Detect and return specialization imbalances.

    Args:
        project_id: Project ID

    Returns:
        List of detected imbalances
    """
    service = get_specialization_service()
    return service.detect_imbalances(project_id)


@router.get("/{project_id}/summary", response_model=SpecializationSummary)
async def get_summary(project_id: str):
    """Get full specialization summary for a project.

    Args:
        project_id: Project ID

    Returns:
        Summary with profiles, utilization, and imbalances
    """
    service = get_specialization_service()
    return service.get_summary(project_id)
