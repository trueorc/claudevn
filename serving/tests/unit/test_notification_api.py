"""Unit tests for notification API endpoints.

Tests use FastAPI TestClient with mocked NotificationService.

Reference: Issue #547
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.notifications import router
from models.notification import (
    Notification,
    NotificationCategory,
    NotificationLevel,
    NotificationListResponse,
)


@pytest.fixture
def mock_service():
    return MagicMock()


@pytest.fixture
def client(mock_service):
    app = FastAPI()
    app.include_router(router)
    with patch("api.notifications.get_notification_service", return_value=mock_service):
        yield TestClient(app)


# =============================================================================
# GET /notifications
# =============================================================================


class TestListNotifications:
    def test_list_returns_items(self, client, mock_service):
        mock_service.list_notifications.return_value = NotificationListResponse(
            items=[
                Notification(
                    notification_id="notif_abc123",
                    title="Test alert",
                    level=NotificationLevel.INFO,
                    category=NotificationCategory.SYSTEM,
                )
            ],
            total=1,
            unread_count=1,
        )
        resp = client.get("/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Test alert"

    def test_list_with_filters(self, client, mock_service):
        mock_service.list_notifications.return_value = NotificationListResponse()
        resp = client.get("/notifications?project_id=p1&unread_only=true&limit=10")
        assert resp.status_code == 200
        mock_service.list_notifications.assert_called_once_with(
            project_id="p1", category=None, unread_only=True, limit=10
        )

    def test_list_graceful_on_uninitialized(self, client):
        with patch("api.notifications.get_notification_service", side_effect=RuntimeError):
            resp = client.get("/notifications")
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# =============================================================================
# GET /notifications/unread-count
# =============================================================================


class TestUnreadCount:
    def test_unread_count(self, client, mock_service):
        mock_service.get_unread_count.return_value = 5
        resp = client.get("/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json() == {"unread_count": 5}

    def test_unread_count_graceful(self, client):
        with patch("api.notifications.get_notification_service", side_effect=RuntimeError):
            resp = client.get("/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json() == {"unread_count": 0}


# =============================================================================
# POST /notifications/{id}/read
# =============================================================================


class TestMarkRead:
    def test_mark_read(self, client, mock_service):
        mock_service.mark_read.return_value = True
        resp = client.post("/notifications/notif_abc/read")
        assert resp.status_code == 200
        assert resp.json() == {"marked": True}
        mock_service.mark_read.assert_called_once_with("notif_abc")

    def test_mark_read_not_found(self, client, mock_service):
        mock_service.mark_read.return_value = False
        resp = client.post("/notifications/notif_xxx/read")
        assert resp.json() == {"marked": False}


# =============================================================================
# POST /notifications/read-all
# =============================================================================


class TestMarkAllRead:
    def test_mark_all_read(self, client, mock_service):
        mock_service.mark_all_read.return_value = 3
        resp = client.post("/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json() == {"marked_count": 3}

    def test_mark_all_read_with_project(self, client, mock_service):
        mock_service.mark_all_read.return_value = 1
        resp = client.post("/notifications/read-all?project_id=p1")
        assert resp.status_code == 200
        mock_service.mark_all_read.assert_called_once_with("p1")


# =============================================================================
# POST /notifications/{id}/dismiss
# =============================================================================


class TestDismiss:
    def test_dismiss(self, client, mock_service):
        mock_service.dismiss.return_value = True
        resp = client.post("/notifications/notif_abc/dismiss")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed": True}
        mock_service.dismiss.assert_called_once_with("notif_abc")

    def test_dismiss_not_found(self, client, mock_service):
        mock_service.dismiss.return_value = False
        resp = client.post("/notifications/notif_xxx/dismiss")
        assert resp.json() == {"dismissed": False}

    def test_dismiss_graceful_on_uninitialized(self, client):
        with patch("api.notifications.get_notification_service", side_effect=RuntimeError):
            resp = client.post("/notifications/notif_abc/dismiss")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed": False}


# =============================================================================
# POST /notifications/dismiss-all
# =============================================================================


class TestDismissAll:
    def test_dismiss_all(self, client, mock_service):
        mock_service.dismiss_all.return_value = 5
        resp = client.post("/notifications/dismiss-all")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed_count": 5}

    def test_dismiss_all_with_project(self, client, mock_service):
        mock_service.dismiss_all.return_value = 2
        resp = client.post("/notifications/dismiss-all?project_id=p1")
        assert resp.status_code == 200
        mock_service.dismiss_all.assert_called_once_with("p1")

    def test_dismiss_all_graceful_on_uninitialized(self, client):
        with patch("api.notifications.get_notification_service", side_effect=RuntimeError):
            resp = client.post("/notifications/dismiss-all")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed_count": 0}
