"""Tests for compute task rejection and re-dispatch logic (#862).

When a compute instance rejects a task (e.g., at capacity), the serving side
should reset the SSE connection to idle and attempt to re-dispatch the task
to another available compute.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.compute import router, _handle_rejection_redispatch, _track_rejection_for_orchestrator
from services.registry_service import get_compute_registry
from models.compute import (
    ComputeEventType,
    ComputeEventRequest,
    ComputeInstance,
    InstanceCapabilities,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_registry():
    """Create a mock compute registry."""
    registry = MagicMock()
    instance = ComputeInstance(
        instance_id="compute-001",
        name="Test Compute",
        endpoint="sse",
        capabilities=InstanceCapabilities(agents=[]),
    )
    registry.get_instance = AsyncMock(return_value=instance)
    registry.update_instance = AsyncMock(return_value=instance)
    return registry


@pytest.fixture
def app(mock_registry):
    """Create a FastAPI test app with dependency overrides."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_compute_registry] = lambda: mock_registry
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_work_data():
    """Sample work_assigned event data for re-dispatch testing."""
    return {
        "task_id": "work_abc123",
        "title": "Implement feature",
        "description": "Do the work",
        "branch_name": "work/compute-001/work_abc123",
        "skills": {"ids": ["coder"], "merged_instructions": "Write code"},
        "context": {"project_id": "proj-1", "repository": "git@host:repo.git"},
        "mcp_config": {"server_url": "http://serving:8002", "api_key": "key-123"},
    }


def _make_rejection_event(task_id="work_abc123", compute_id="compute-001"):
    """Create a rejection event."""
    return ComputeEventRequest(
        event=ComputeEventType.CLAUDE_CODE_REJECTED,
        compute_id=compute_id,
        task_id=task_id,
        error="At capacity (1 instance(s))",
    )


def _make_mock_connection(compute_id, status="idle", work_data=None):
    """Create a mock SSE connection."""
    conn = MagicMock()
    conn.compute_id = compute_id
    conn.status = status
    conn.current_task_id = None
    conn.last_work_assigned_data = work_data
    return conn


# =============================================================================
# API Endpoint Tests — Rejected Event
# =============================================================================


class TestRejectedEventEndpoint:
    """Tests for the /events endpoint handling claude_code_rejected."""

    def test_rejected_event_returns_acknowledged(self, client):
        """Rejected event should be accepted and acknowledged."""
        with patch("api.compute.get_sse_connection_manager") as mock_sse:
            mock_sse.return_value.get_connection.return_value = _make_mock_connection(
                "compute-001"
            )
            with patch("api.compute._handle_rejection_redispatch", new_callable=AsyncMock):
                response = client.post(
                    "/compute/events",
                    json={
                        "event": "claude_code_rejected",
                        "compute_id": "compute-001",
                        "task_id": "work_abc123",
                        "error": "At capacity (1 instance(s))",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "acknowledged"
        assert data["event"] == "claude_code_rejected"

    def test_rejected_event_resets_sse_connection_to_idle(self, client):
        """Rejected event should reset the SSE connection to idle."""
        mock_conn = _make_mock_connection("compute-001", status="busy")

        with patch("api.compute.get_sse_connection_manager") as mock_sse:
            mock_sse.return_value.get_connection.return_value = mock_conn
            with patch("api.compute._handle_rejection_redispatch", new_callable=AsyncMock):
                client.post(
                    "/compute/events",
                    json={
                        "event": "claude_code_rejected",
                        "compute_id": "compute-001",
                        "task_id": "work_abc123",
                        "error": "At capacity",
                    },
                )

        assert mock_conn.status == "idle"
        assert mock_conn.current_task_id is None

    def test_rejected_event_updates_metadata(self, client, mock_registry):
        """Rejected event should update instance metadata with error."""
        with patch("api.compute.get_sse_connection_manager") as mock_sse:
            mock_sse.return_value.get_connection.return_value = _make_mock_connection(
                "compute-001"
            )
            with patch("api.compute._handle_rejection_redispatch", new_callable=AsyncMock):
                client.post(
                    "/compute/events",
                    json={
                        "event": "claude_code_rejected",
                        "compute_id": "compute-001",
                        "task_id": "work_abc123",
                        "error": "At capacity (1 instance(s))",
                    },
                )

        # Check metadata was updated
        mock_registry.update_instance.assert_awaited_once()
        call_kwargs = mock_registry.update_instance.call_args[1]
        assert call_kwargs["metadata"]["current_task_id"] is None
        assert call_kwargs["metadata"]["last_error"] == "At capacity (1 instance(s))"


# =============================================================================
# _handle_rejection_redispatch Unit Tests
# =============================================================================


class TestHandleRejectionRedispatch:
    """Tests for the re-dispatch logic when a task is rejected."""

    @pytest.mark.asyncio
    async def test_redispatch_to_alternative_compute(self, sample_work_data):
        """Should re-dispatch rejected task to another idle compute."""
        rejecting_conn = _make_mock_connection(
            "compute-001", work_data=sample_work_data
        )
        alt_conn = _make_mock_connection("compute-002")

        mock_sse = MagicMock()
        mock_sse.get_connection.return_value = rejecting_conn
        mock_sse.find_matching_connection.return_value = alt_conn
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        event = _make_rejection_event()

        with patch(
            "api.compute.get_sse_connection_manager", return_value=mock_sse
        ):
            await _handle_rejection_redispatch(event)

        # Should have searched for alt compute excluding rejector
        mock_sse.find_matching_connection.assert_called_once_with(
            idle_only=True,
            exclude_compute_ids={"compute-001"},
        )

        # Should have sent work to alt compute
        mock_sse.send_work_assigned.assert_awaited_once_with(
            compute_id="compute-002",
            task_id="work_abc123",
            title="Implement feature",
            description="Do the work",
            branch_name="work/compute-001/work_abc123",
            skills=sample_work_data["skills"],
            context=sample_work_data["context"],
            mcp_config=sample_work_data["mcp_config"],
        )

    @pytest.mark.asyncio
    async def test_redispatch_clears_stored_data(self, sample_work_data):
        """Should clear last_work_assigned_data on the rejecting connection."""
        rejecting_conn = _make_mock_connection(
            "compute-001", work_data=sample_work_data
        )
        alt_conn = _make_mock_connection("compute-002")

        mock_sse = MagicMock()
        mock_sse.get_connection.return_value = rejecting_conn
        mock_sse.find_matching_connection.return_value = alt_conn
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        event = _make_rejection_event()

        with patch(
            "api.compute.get_sse_connection_manager", return_value=mock_sse
        ):
            await _handle_rejection_redispatch(event)

        assert rejecting_conn.last_work_assigned_data is None

    @pytest.mark.asyncio
    async def test_no_redispatch_without_stored_data(self):
        """Should not re-dispatch if no work_assigned data is stored."""
        rejecting_conn = _make_mock_connection("compute-001", work_data=None)

        mock_sse = MagicMock()
        mock_sse.get_connection.return_value = rejecting_conn

        event = _make_rejection_event()

        with patch(
            "api.compute.get_sse_connection_manager", return_value=mock_sse
        ):
            await _handle_rejection_redispatch(event)

        # Should not attempt to find alt compute or send work
        mock_sse.find_matching_connection.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_alt_compute_tracks_orchestrator_failure(self, sample_work_data):
        """When no alt compute available, should track in orchestrator failed_nodes."""
        rejecting_conn = _make_mock_connection(
            "compute-001", work_data=sample_work_data
        )

        mock_sse = MagicMock()
        mock_sse.get_connection.return_value = rejecting_conn
        mock_sse.find_matching_connection.return_value = None

        event = _make_rejection_event()

        with patch(
            "api.compute.get_sse_connection_manager", return_value=mock_sse
        ):
            with patch(
                "api.compute._track_rejection_for_orchestrator"
            ) as mock_track:
                await _handle_rejection_redispatch(event)

        mock_track.assert_called_once_with("work_abc123", "compute-001")

    @pytest.mark.asyncio
    async def test_mismatched_task_id_skips_redispatch(self, sample_work_data):
        """Should skip redispatch if stored data has a different task_id."""
        rejecting_conn = _make_mock_connection(
            "compute-001", work_data={**sample_work_data, "task_id": "other_task"}
        )

        mock_sse = MagicMock()
        mock_sse.get_connection.return_value = rejecting_conn

        event = _make_rejection_event()

        with patch(
            "api.compute.get_sse_connection_manager", return_value=mock_sse
        ):
            await _handle_rejection_redispatch(event)

        mock_sse.find_matching_connection.assert_not_called()


# =============================================================================
# _track_rejection_for_orchestrator Unit Tests
# =============================================================================


class TestTrackRejectionForOrchestrator:
    """Tests for tracking rejections in orchestrator's failed_nodes."""

    def test_tracks_work_item_rejection(self):
        """Should add compute to orchestrator's failed_nodes for work items."""
        mock_orchestrator = MagicMock()
        mock_orchestrator._failed_nodes = {}

        with patch(
            "services.work_orchestrator.get_work_orchestrator",
            return_value=mock_orchestrator,
        ):
            _track_rejection_for_orchestrator("work_abc123", "compute-001")

        assert "work_abc123" in mock_orchestrator._failed_nodes
        assert "compute-001" in mock_orchestrator._failed_nodes["work_abc123"]

    def test_skips_characterization_tasks(self):
        """Should not track char-* tasks in orchestrator (not work items)."""
        with patch(
            "services.work_orchestrator.get_work_orchestrator"
        ) as mock_get:
            _track_rejection_for_orchestrator("char-abc123", "compute-001")

        mock_get.assert_not_called()

    def test_skips_decomposition_tasks(self):
        """Should not track decomp-* tasks in orchestrator (not work items)."""
        with patch(
            "services.work_orchestrator.get_work_orchestrator"
        ) as mock_get:
            _track_rejection_for_orchestrator("decomp-abc123", "compute-001")

        mock_get.assert_not_called()

    def test_appends_to_existing_failed_nodes(self):
        """Should append to existing failed_nodes set for the work item."""
        mock_orchestrator = MagicMock()
        mock_orchestrator._failed_nodes = {
            "work_abc123": {"compute-003"}
        }

        with patch(
            "services.work_orchestrator.get_work_orchestrator",
            return_value=mock_orchestrator,
        ):
            _track_rejection_for_orchestrator("work_abc123", "compute-001")

        assert mock_orchestrator._failed_nodes["work_abc123"] == {
            "compute-003", "compute-001"
        }

    def test_gracefully_handles_missing_orchestrator(self):
        """Should not raise if orchestrator is not available."""
        with patch(
            "services.work_orchestrator.get_work_orchestrator",
            side_effect=RuntimeError("Not initialized"),
        ):
            # Should not raise
            _track_rejection_for_orchestrator("work_abc123", "compute-001")


# =============================================================================
# SSE Connection Manager — work_assigned data storage
# =============================================================================


class TestSSEConnectionWorkDataStorage:
    """Tests for storing work_assigned data on SSE connections."""

    @pytest.mark.asyncio
    async def test_send_work_assigned_stores_data(self):
        """send_work_assigned should store data on the connection for replay."""
        from services.sse_connection_manager import SSEConnectionManager, SSEConnection

        manager = SSEConnectionManager()
        conn = SSEConnection(
            compute_id="compute-001",
            capabilities=["general"],
            resources={"cpu": 4},
        )
        manager._connections["compute-001"] = conn

        await manager.send_work_assigned(
            compute_id="compute-001",
            task_id="work_abc123",
            title="Test Task",
            description="Do stuff",
            branch_name="work/compute-001/work_abc123",
            skills={"ids": ["coder"]},
            context={"project_id": "proj-1"},
            mcp_config={"server_url": "http://serving:8002"},
        )

        assert conn.last_work_assigned_data is not None
        assert conn.last_work_assigned_data["task_id"] == "work_abc123"
        assert conn.last_work_assigned_data["title"] == "Test Task"


# =============================================================================
# ComputeEventType Enum
# =============================================================================


class TestComputeEventTypeEnum:
    """Tests for the CLAUDE_CODE_REJECTED event type."""

    def test_rejected_event_type_exists(self):
        """CLAUDE_CODE_REJECTED should be a valid event type."""
        assert ComputeEventType.CLAUDE_CODE_REJECTED.value == "claude_code_rejected"

    def test_rejected_event_request_validates(self):
        """ComputeEventRequest should accept claude_code_rejected."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_REJECTED,
            compute_id="compute-001",
            task_id="work_abc123",
            error="At capacity",
        )
        assert event.event == ComputeEventType.CLAUDE_CODE_REJECTED
        assert event.error == "At capacity"
