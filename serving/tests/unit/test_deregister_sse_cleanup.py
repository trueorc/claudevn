"""Tests for SSE connection cleanup on compute deregistration (#787).

Verifies that deregistering a compute instance via DELETE /api/v1/compute/{id}
also disconnects the SSE connection, preventing work from being assigned to
deregistered instances.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.compute import router
from services.registry_service import get_compute_registry


@pytest.fixture
def mock_registry():
    registry = MagicMock()
    registry.remove_instance = AsyncMock(return_value=True)
    return registry


@pytest.fixture
def mock_sse_manager():
    manager = MagicMock()
    manager.unregister_connection = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def client(mock_registry, mock_sse_manager):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_compute_registry] = lambda: mock_registry

    with patch(
        "api.compute.get_sse_connection_manager", return_value=mock_sse_manager
    ):
        yield TestClient(app)


class TestDeregisterSSECleanup:
    """Tests that deregistration disconnects SSE connections."""

    def test_deregister_disconnects_sse(self, client, mock_registry, mock_sse_manager):
        """Deregistering a compute should unregister its SSE connection."""
        response = client.delete("/api/v1/compute/compute-001")

        assert response.status_code == 200
        mock_sse_manager.unregister_connection.assert_awaited_once_with("compute-001")
        mock_registry.remove_instance.assert_awaited_once_with("compute-001")

    def test_deregister_disconnects_sse_before_registry_removal(
        self, client, mock_registry, mock_sse_manager
    ):
        """SSE should be disconnected before registry removal to prevent race conditions."""
        call_order = []
        mock_sse_manager.unregister_connection = AsyncMock(
            side_effect=lambda *a: call_order.append("sse_unregister")
        )
        mock_registry.remove_instance = AsyncMock(
            side_effect=lambda *a: call_order.append("registry_remove") or True
        )

        response = client.delete("/api/v1/compute/compute-002")

        assert response.status_code == 200
        assert call_order == ["sse_unregister", "registry_remove"]

    def test_deregister_not_found_still_cleans_sse(
        self, client, mock_registry, mock_sse_manager
    ):
        """Even if instance not in registry, SSE should still be cleaned up."""
        mock_registry.remove_instance = AsyncMock(return_value=False)

        response = client.delete("/api/v1/compute/compute-ghost")

        assert response.status_code == 404
        # SSE cleanup should still happen (defensive)
        mock_sse_manager.unregister_connection.assert_awaited_once_with("compute-ghost")

    def test_deregister_sse_no_connection_is_noop(
        self, client, mock_registry, mock_sse_manager
    ):
        """If no SSE connection exists, unregister should still succeed."""
        mock_sse_manager.unregister_connection = AsyncMock(return_value=False)

        response = client.delete("/api/v1/compute/compute-001")

        assert response.status_code == 200
        assert response.json()["status"] == "deregistered"
