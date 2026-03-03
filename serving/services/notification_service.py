"""Notification Service for system event alerts.

Lightweight in-memory notification feed. Notifications are ephemeral
and do not survive restarts — this is intentional for a v1 that
just surfaces alerts in the UI.

Reference: Issue #547
"""

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional

from models.notification import (
    Notification,
    NotificationCategory,
    NotificationLevel,
    NotificationListResponse,
)

logger = logging.getLogger(__name__)

MAX_NOTIFICATIONS = 200


class NotificationService:
    """In-memory notification service.

    Stores a bounded deque of recent notifications. No persistence —
    notifications are cleared on restart.
    """

    def __init__(self):
        self._notifications: deque[Notification] = deque(maxlen=MAX_NOTIFICATIONS)

    def emit(
        self,
        title: str,
        message: str = "",
        level: NotificationLevel = NotificationLevel.INFO,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        project_id: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> Notification:
        """Emit a new notification.

        Args:
            title: Short notification title
            message: Detailed message
            level: Severity level
            category: Event category
            project_id: Optional project scope
            entity_id: Optional related entity ID

        Returns:
            The created Notification
        """
        notification = Notification(
            notification_id=f"notif_{uuid.uuid4().hex[:12]}",
            level=level,
            category=category,
            title=title,
            message=message,
            project_id=project_id,
            entity_id=entity_id,
        )
        self._notifications.appendleft(notification)
        logger.debug(f"Notification emitted: [{level.value}] {title}")
        return notification

    def list_notifications(
        self,
        project_id: Optional[str] = None,
        category: Optional[NotificationCategory] = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> NotificationListResponse:
        """List recent notifications with optional filters.

        Args:
            project_id: Filter by project (None = all projects)
            category: Filter by category
            unread_only: Only return unread notifications
            limit: Maximum items to return

        Returns:
            NotificationListResponse
        """
        items = list(self._notifications)

        if project_id:
            items = [n for n in items if n.project_id == project_id or n.project_id is None]
        if category:
            items = [n for n in items if n.category == category]
        if unread_only:
            items = [n for n in items if not n.read]

        total = len(items)
        unread_count = sum(1 for n in items if not n.read)
        items = items[:limit]

        return NotificationListResponse(
            items=items,
            total=total,
            unread_count=unread_count,
        )

    def mark_read(self, notification_id: str) -> bool:
        """Mark a notification as read.

        Returns:
            True if found and marked, False if not found
        """
        for n in self._notifications:
            if n.notification_id == notification_id:
                n.read = True
                return True
        return False

    def mark_all_read(self, project_id: Optional[str] = None) -> int:
        """Mark all notifications as read.

        Args:
            project_id: Only mark notifications for this project

        Returns:
            Number of notifications marked
        """
        count = 0
        for n in self._notifications:
            if not n.read and (project_id is None or n.project_id == project_id or n.project_id is None):
                n.read = True
                count += 1
        return count

    def dismiss(self, notification_id: str) -> bool:
        """Dismiss (remove) a notification.

        Returns:
            True if found and removed, False if not found
        """
        for n in self._notifications:
            if n.notification_id == notification_id:
                self._notifications.remove(n)
                return True
        return False

    def dismiss_all(self, project_id: Optional[str] = None) -> int:
        """Dismiss all read notifications.

        Args:
            project_id: Only dismiss notifications for this project

        Returns:
            Number of notifications dismissed
        """
        to_remove = [
            n for n in self._notifications
            if n.read
            and (project_id is None or n.project_id == project_id or n.project_id is None)
        ]
        for n in to_remove:
            self._notifications.remove(n)
        return len(to_remove)

    def get_unread_count(self, project_id: Optional[str] = None) -> int:
        """Get count of unread notifications."""
        return sum(
            1 for n in self._notifications
            if not n.read
            and (project_id is None or n.project_id == project_id or n.project_id is None)
        )


# =============================================================================
# Global Instance
# =============================================================================

_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get the global notification service instance."""
    if _notification_service is None:
        raise RuntimeError("Notification service not initialized")
    return _notification_service


def set_notification_service(service: Optional[NotificationService]) -> None:
    """Set the global notification service instance."""
    global _notification_service
    _notification_service = service
