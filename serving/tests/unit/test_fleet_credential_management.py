"""Tests for fleet credential management endpoints (issue #538).

Tests cover:
- Model: CredentialsRefreshEvent, DrainEvent, RefreshCredentialsRequest/Response
- API: POST /compute/refresh-credentials, POST /compute/{id}/drain-for-restart
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.compute import (
    SSEEventType,
    CredentialsRefreshEvent,
    DrainEvent,
    RefreshCredentialsRequest,
    RefreshCredentialsResponse,
)
from api.compute import router


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_registry():
    """Create a mock compute registry."""
    registry = AsyncMock()
    registry.drain_instance = AsyncMock(return_value=MagicMock())
    return registry


@pytest.fixture
def mock_sse_manager():
    """Create a mock SSE connection manager with test connections."""
    manager = MagicMock()
    conn_001 = MagicMock()
    conn_001.send_event = AsyncMock()
    conn_002 = MagicMock()
    conn_002.send_event = AsyncMock()

    connections = {
        "compute-001": conn_001,
        "compute-002": conn_002,
    }
    manager._connections = connections
    manager.get_connection = MagicMock(side_effect=lambda cid: connections.get(cid))
    return manager


@pytest.fixture
def client(mock_registry, mock_sse_manager):
    """Create test client with mocked dependencies."""
    from services.registry_service import get_compute_registry
    from services.sse_connection_manager import get_sse_connection_manager as get_sse_mgr

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override FastAPI dependencies
    app.dependency_overrides[get_compute_registry] = lambda: mock_registry
    app.dependency_overrides[get_sse_mgr] = lambda: mock_sse_manager

    with patch(
        "api.compute.get_sse_connection_manager", return_value=mock_sse_manager
    ):
        yield TestClient(app)


# =============================================================================
# Model Tests
# =============================================================================


class TestSSEEventTypes:
    """Test new SSE event types."""

    def test_credentials_refresh_event_type(self):
        """CREDENTIALS_REFRESH should be a valid SSE event type."""
        assert SSEEventType.CREDENTIALS_REFRESH == "credentials_refresh"

    def test_drain_event_type(self):
        """DRAIN should be a valid SSE event type."""
        assert SSEEventType.DRAIN == "drain"


class TestCredentialsRefreshEvent:
    """Test CredentialsRefreshEvent model."""

    def test_default_values(self):
        """Default values should be set."""
        event = CredentialsRefreshEvent()
        assert event.reason == "Credentials refreshed"
        assert event.timestamp is not None

    def test_custom_values(self):
        """Custom values should be accepted."""
        event = CredentialsRefreshEvent(reason="Host login refreshed")
        assert event.reason == "Host login refreshed"

    def test_serialization(self):
        """Should serialize to dict."""
        event = CredentialsRefreshEvent(reason="test")
        data = event.model_dump()
        assert data["reason"] == "test"
        assert "timestamp" in data


class TestDrainEvent:
    """Test DrainEvent model."""

    def test_default_values(self):
        """Default grace period should be 300 seconds."""
        event = DrainEvent()
        assert event.grace_period_seconds == 300
        assert event.reason == ""

    def test_custom_values(self):
        """Custom values should be accepted."""
        event = DrainEvent(reason="cred failure", grace_period_seconds=120)
        assert event.reason == "cred failure"
        assert event.grace_period_seconds == 120


class TestRefreshCredentialsRequest:
    """Test RefreshCredentialsRequest model."""

    def test_default_all_instances(self):
        """None instance_ids means all instances."""
        req = RefreshCredentialsRequest()
        assert req.instance_ids is None
        assert req.reason == "Credentials refreshed"

    def test_specific_instances(self):
        """Can target specific instances."""
        req = RefreshCredentialsRequest(
            instance_ids=["compute-001"],
            reason="manual refresh"
        )
        assert req.instance_ids == ["compute-001"]


class TestRefreshCredentialsResponse:
    """Test RefreshCredentialsResponse model."""

    def test_construction(self):
        """Response fields should match."""
        resp = RefreshCredentialsResponse(
            status="sent",
            instances_notified=["compute-001"],
            instances_failed=[],
            total_notified=1,
        )
        assert resp.status == "sent"
        assert resp.total_notified == 1


# =============================================================================
# API Tests: POST /compute/refresh-credentials
# =============================================================================


class TestRefreshCredentialsEndpoint:
    """Tests for POST /compute/refresh-credentials."""

    def test_refresh_all_instances(self, client, mock_sse_manager):
        """Should send refresh to all connected instances."""
        response = client.post("/api/v1/compute/refresh-credentials", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "sent"
        assert set(data["instances_notified"]) == {"compute-001", "compute-002"}
        assert data["instances_failed"] == []
        assert data["total_notified"] == 2

        # Verify events were sent
        conn_001 = mock_sse_manager.get_connection("compute-001")
        conn_001.send_event.assert_called_once()
        args = conn_001.send_event.call_args
        assert args[0][0] == "credentials_refresh"

    def test_refresh_specific_instances(self, client, mock_sse_manager):
        """Should only refresh specified instances."""
        response = client.post(
            "/api/v1/compute/refresh-credentials",
            json={"instance_ids": ["compute-001"], "reason": "test refresh"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["instances_notified"] == ["compute-001"]
        assert data["total_notified"] == 1

        # compute-002 should NOT have been refreshed
        conn_002 = mock_sse_manager.get_connection("compute-002")
        conn_002.send_event.assert_not_called()

    def test_refresh_unknown_instance(self, client, mock_sse_manager):
        """Should report failure for unknown instances."""
        response = client.post(
            "/api/v1/compute/refresh-credentials",
            json={"instance_ids": ["unknown-001"]},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "failed"
        assert data["instances_failed"] == ["unknown-001"]
        assert data["total_notified"] == 0

    def test_refresh_partial_failure(self, client, mock_sse_manager):
        """Should report partial when some succeed and some fail."""
        response = client.post(
            "/api/v1/compute/refresh-credentials",
            json={"instance_ids": ["compute-001", "unknown-001"]},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "partial"
        assert data["instances_notified"] == ["compute-001"]
        assert data["instances_failed"] == ["unknown-001"]

    def test_refresh_no_instances_connected(self, client, mock_sse_manager):
        """Should return no_instances when no connections exist."""
        mock_sse_manager._connections = {}
        response = client.post("/api/v1/compute/refresh-credentials", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "no_instances"
        assert data["total_notified"] == 0


# =============================================================================
# API Tests: POST /compute/{id}/drain-for-restart
# =============================================================================


class TestDrainForRestartEndpoint:
    """Tests for POST /compute/{id}/drain-for-restart."""

    def test_drain_for_restart_success(self, client, mock_sse_manager, mock_registry):
        """Should send drain event and update registry."""
        response = client.post("/api/v1/compute/compute-001/drain-for-restart")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "drain_sent"
        assert data["instance_id"] == "compute-001"
        assert data["grace_period_seconds"] == 300

        # Verify drain event was sent
        conn = mock_sse_manager.get_connection("compute-001")
        conn.send_event.assert_called_once()
        args = conn.send_event.call_args
        assert args[0][0] == "drain"

        # Verify registry was updated
        mock_registry.drain_instance.assert_called_once_with(
            instance_id="compute-001", auto_deregister=False
        )

    def test_drain_unknown_instance(self, client, mock_sse_manager):
        """Should return 404 for unknown instance."""
        response = client.post("/api/v1/compute/unknown-001/drain-for-restart")
        assert response.status_code == 404

    def test_drain_custom_grace_period(self, client, mock_sse_manager):
        """Should accept custom grace period."""
        response = client.post(
            "/api/v1/compute/compute-001/drain-for-restart",
            params={"grace_period": 120, "reason": "custom drain"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["grace_period_seconds"] == 120
        assert data["reason"] == "custom drain"
