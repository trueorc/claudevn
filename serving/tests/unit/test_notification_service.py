"""Unit tests for NotificationService.

Tests cover emit, list, filter, mark-read, and unread-count operations
on the in-memory notification store.

Reference: Issue #547
"""

import pytest

from models.notification import NotificationCategory, NotificationLevel
from services.notification_service import NotificationService


@pytest.fixture
def service():
    return NotificationService()


# =============================================================================
# Emit
# =============================================================================


class TestEmit:
    def test_emit_returns_notification(self, service):
        n = service.emit(title="Test alert")
        assert n.title == "Test alert"
        assert n.notification_id.startswith("notif_")
        assert n.read is False
        assert n.level == NotificationLevel.INFO
        assert n.category == NotificationCategory.SYSTEM

    def test_emit_with_all_fields(self, service):
        n = service.emit(
            title="Goal done",
            message="Goal X finished",
            level=NotificationLevel.SUCCESS,
            category=NotificationCategory.GOAL,
            project_id="proj_1",
            entity_id="goal_1",
        )
        assert n.title == "Goal done"
        assert n.message == "Goal X finished"
        assert n.level == NotificationLevel.SUCCESS
        assert n.category == NotificationCategory.GOAL
        assert n.project_id == "proj_1"
        assert n.entity_id == "goal_1"

    def test_emit_newest_first(self, service):
        service.emit(title="First")
        service.emit(title="Second")
        result = service.list_notifications()
        assert result.items[0].title == "Second"
        assert result.items[1].title == "First"


# =============================================================================
# List & Filter
# =============================================================================


class TestListNotifications:
    def test_empty_list(self, service):
        result = service.list_notifications()
        assert result.items == []
        assert result.total == 0
        assert result.unread_count == 0

    def test_filter_by_project(self, service):
        service.emit(title="A", project_id="proj_1")
        service.emit(title="B", project_id="proj_2")
        service.emit(title="Global")  # no project_id → visible to all

        result = service.list_notifications(project_id="proj_1")
        titles = [n.title for n in result.items]
        assert "A" in titles
        assert "Global" in titles
        assert "B" not in titles

    def test_filter_by_category(self, service):
        service.emit(title="Goal event", category=NotificationCategory.GOAL)
        service.emit(title="System event", category=NotificationCategory.SYSTEM)

        result = service.list_notifications(category=NotificationCategory.GOAL)
        assert len(result.items) == 1
        assert result.items[0].title == "Goal event"

    def test_filter_unread_only(self, service):
        n = service.emit(title="Read me")
        service.emit(title="Unread")
        service.mark_read(n.notification_id)

        result = service.list_notifications(unread_only=True)
        assert len(result.items) == 1
        assert result.items[0].title == "Unread"

    def test_limit(self, service):
        for i in range(10):
            service.emit(title=f"N{i}")
        result = service.list_notifications(limit=3)
        assert len(result.items) == 3
        assert result.total == 10

    def test_unread_count_in_response(self, service):
        service.emit(title="A")
        n = service.emit(title="B")
        service.mark_read(n.notification_id)
        result = service.list_notifications()
        assert result.unread_count == 1


# =============================================================================
# Mark Read
# =============================================================================


class TestMarkRead:
    def test_mark_read(self, service):
        n = service.emit(title="Alert")
        assert service.mark_read(n.notification_id) is True
        result = service.list_notifications()
        assert result.items[0].read is True

    def test_mark_read_not_found(self, service):
        assert service.mark_read("nonexistent") is False

    def test_mark_all_read(self, service):
        service.emit(title="A")
        service.emit(title="B")
        count = service.mark_all_read()
        assert count == 2
        assert service.get_unread_count() == 0

    def test_mark_all_read_by_project(self, service):
        service.emit(title="P1", project_id="proj_1")
        service.emit(title="P2", project_id="proj_2")
        count = service.mark_all_read(project_id="proj_1")
        assert count == 1
        # proj_2 still unread
        assert service.get_unread_count(project_id="proj_2") == 1


# =============================================================================
# Unread Count
# =============================================================================


class TestUnreadCount:
    def test_unread_count(self, service):
        service.emit(title="A")
        service.emit(title="B")
        assert service.get_unread_count() == 2

    def test_unread_count_by_project(self, service):
        service.emit(title="A", project_id="proj_1")
        service.emit(title="B", project_id="proj_2")
        assert service.get_unread_count(project_id="proj_1") == 1

    def test_global_notifications_count_for_any_project(self, service):
        service.emit(title="Global")  # no project_id
        assert service.get_unread_count(project_id="proj_1") == 1


# =============================================================================
# Dismiss
# =============================================================================


class TestDismiss:
    def test_dismiss_removes_notification(self, service):
        n = service.emit(title="Bye")
        assert service.dismiss(n.notification_id) is True
        result = service.list_notifications()
        assert result.total == 0

    def test_dismiss_not_found(self, service):
        assert service.dismiss("nonexistent") is False

    def test_dismiss_updates_unread_count(self, service):
        n = service.emit(title="Unread")
        assert service.get_unread_count() == 1
        service.dismiss(n.notification_id)
        assert service.get_unread_count() == 0

    def test_dismiss_all_removes_read_only(self, service):
        n1 = service.emit(title="Read me")
        service.emit(title="Still unread")
        service.mark_read(n1.notification_id)
        count = service.dismiss_all()
        assert count == 1
        result = service.list_notifications()
        assert result.total == 1
        assert result.items[0].title == "Still unread"

    def test_dismiss_all_by_project(self, service):
        n1 = service.emit(title="P1", project_id="proj_1")
        n2 = service.emit(title="P2", project_id="proj_2")
        service.mark_read(n1.notification_id)
        service.mark_read(n2.notification_id)
        count = service.dismiss_all(project_id="proj_1")
        assert count == 1
        result = service.list_notifications()
        assert result.total == 1
        assert result.items[0].title == "P2"


# =============================================================================
# Bounded Deque
# =============================================================================


class TestBoundedStore:
    def test_max_notifications(self, service):
        for i in range(250):
            service.emit(title=f"N{i}")
        result = service.list_notifications(limit=250)
        assert result.total == 200
