"""API endpoints for system notifications.

Provides endpoints to list, read, and manage notifications
surfaced in the serving UI.

Reference: Issue #547
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from models.notification import NotificationCategory, NotificationListResponse
from services.notification_service import get_notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    project_id: Optional[str] = Query(None),
    category: Optional[NotificationCategory] = Query(None),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    """List recent notifications."""
    try:
        service = get_notification_service()
        return service.list_notifications(
            project_id=project_id,
            category=category,
            unread_only=unread_only,
            limit=limit,
        )
    except RuntimeError:
        return NotificationListResponse()


@router.get("/unread-count")
async def get_unread_count(
    project_id: Optional[str] = Query(None),
):
    """Get count of unread notifications."""
    try:
        service = get_notification_service()
        return {"unread_count": service.get_unread_count(project_id)}
    except RuntimeError:
        return {"unread_count": 0}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str):
    """Mark a single notification as read."""
    try:
        service = get_notification_service()
        found = service.mark_read(notification_id)
        return {"marked": found}
    except RuntimeError:
        return {"marked": False}


@router.post("/read-all")
async def mark_all_read(
    project_id: Optional[str] = Query(None),
):
    """Mark all notifications as read."""
    try:
        service = get_notification_service()
        count = service.mark_all_read(project_id)
        return {"marked_count": count}
    except RuntimeError:
        return {"marked_count": 0}
