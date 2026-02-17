"""API endpoints for work profile presets.

Provides endpoints to list available presets and activate a preset
for a project's planner profile.

Reference: Issue #878
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models.work_profile_preset import (
    DEFAULT_PRESET,
    PresetName,
    WorkProfilePreset,
    get_preset,
    list_presets,
)
from models.planner_profile import (
    PlannerProfile,
    ProfileTrigger,
    ProfileTriggerType,
)
from services.planner_profile_service import get_planner_profile_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])


class PresetSummary(BaseModel):
    """Preset summary for listing."""
    name: str
    label: str
    description: str
    optimization_target: str
    intent: str
    color: str
    icon: str


class ActivatePresetResponse(BaseModel):
    """Response after activating a preset."""
    project_id: str
    preset_name: str
    preset_label: str
    profile_version: int
    message: str


class ActivePresetResponse(BaseModel):
    """Response for current active preset."""
    project_id: str
    active_preset: Optional[str] = None
    active_preset_label: Optional[str] = None


@router.get("/presets", response_model=List[PresetSummary])
async def list_available_presets():
    """List all available work profile presets."""
    presets = list_presets()
    return [
        PresetSummary(
            name=p.name.value,
            label=p.label,
            description=p.description,
            optimization_target=p.optimization_target,
            intent=p.intent,
            color=p.color,
            icon=p.icon,
        )
        for p in presets
    ]


@router.post("/presets/{preset_name}/activate", response_model=ActivatePresetResponse)
async def activate_preset(
    preset_name: str,
    project_id: str = Query(..., description="Project to activate preset for"),
):
    """Activate a work profile preset for a project.

    Creates or replaces the project's planner profile with the preset's
    weights and policy rules. Existing goal-derived weights will be
    re-layered on top during the next profile rebuild.
    """
    try:
        preset_enum = PresetName(preset_name)
    except ValueError:
        valid = [p.value for p in PresetName]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset name '{preset_name}'. Valid presets: {valid}",
        )

    preset = get_preset(preset_enum)
    profile_service = get_planner_profile_service()

    # Get existing profile or create new one
    existing = await profile_service.get_profile(project_id)

    if existing:
        # Update existing profile with preset weights
        existing.weights = preset.weights.model_copy(deep=True)
        existing.policy_rules = [r.model_copy(deep=True) for r in preset.policy_rules]
        existing.active_preset = preset_name
        existing.version += 1
        existing.updated_at = datetime.now(timezone.utc)
        existing.triggers.append(ProfileTrigger(
            trigger_type=ProfileTriggerType.MANUAL_ADJUSTMENT,
            source_id=f"preset:{preset_name}",
            description=f"Activated work profile preset: {preset.label}",
        ))
        await profile_service._save_profile_to_redis(existing)
        await profile_service._save_profile_history(existing)
        profile_version = existing.version
    else:
        # Create new profile from preset
        profile = PlannerProfile(
            profile_id=f"profile_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            weights=preset.weights.model_copy(deep=True),
            policy_rules=[r.model_copy(deep=True) for r in preset.policy_rules],
            active_preset=preset_name,
            triggers=[ProfileTrigger(
                trigger_type=ProfileTriggerType.MANUAL_ADJUSTMENT,
                source_id=f"preset:{preset_name}",
                description=f"Activated work profile preset: {preset.label}",
            )],
            version=1,
        )
        profile_service._profiles[project_id] = profile
        await profile_service._save_profile_to_redis(profile)
        await profile_service._save_profile_history(profile)
        profile_version = profile.version

    logger.info(f"Activated preset '{preset_name}' for project {project_id}")

    return ActivatePresetResponse(
        project_id=project_id,
        preset_name=preset_name,
        preset_label=preset.label,
        profile_version=profile_version,
        message=f"Work profile '{preset.label}' activated successfully.",
    )


@router.get("/presets/active", response_model=ActivePresetResponse)
async def get_active_preset(
    project_id: str = Query(..., description="Project to check active preset for"),
):
    """Get the currently active preset for a project."""
    profile_service = get_planner_profile_service()
    profile = await profile_service.get_profile(project_id)

    if not profile or not profile.active_preset:
        return ActivePresetResponse(project_id=project_id)

    try:
        preset = get_preset(PresetName(profile.active_preset))
        return ActivePresetResponse(
            project_id=project_id,
            active_preset=profile.active_preset,
            active_preset_label=preset.label,
        )
    except (ValueError, KeyError):
        return ActivePresetResponse(
            project_id=project_id,
            active_preset=profile.active_preset,
        )
