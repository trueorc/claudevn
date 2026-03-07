"""Presence API — user online status and activity awareness."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.users import get_current_user_id, get_optional_user_id
from models.presence import HeartbeatRequest, PresenceResponse
from services.presence_service import get_presence_service

router = APIRouter(prefix="/projects/{project_id}/presence", tags=["presence"])


@router.post("/heartbeat", status_code=204)
async def heartbeat(
    project_id: str,
    body: HeartbeatRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Record or refresh a user's presence heartbeat for a project."""
    service = get_presence_service()
    if not service:
        # Presence is optional — return 204 silently rather than 503
        return

    # Resolve display name from user service
    display_name = user_id
    try:
        from services.user_service import get_user_service
        user_svc = get_user_service()
        if user_svc:
            user = await user_svc.get_user(user_id)
            if user:
                display_name = user.username
    except Exception:
        pass

    await service.heartbeat(
        project_id=project_id,
        user_id=user_id,
        display_name=display_name,
        current_view=body.current_view,
    )


@router.get("", response_model=PresenceResponse)
async def get_presence(
    project_id: str,
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Get all active users for a project."""
    service = get_presence_service()
    if not service:
        return PresenceResponse(users=[])

    users = await service.get_active_users(project_id)
    return PresenceResponse(users=users)
