"""Tests for graceful compute deregistration via drain (issue #452).

Tests cover:
- Model: DRAINING status, drain_started_at, DrainRequest, DrainStatusResponse
- Registry: drain_instance, cancel_drain
- API: POST /{id}/drain, GET /{id}/drain, DELETE /{id}/drain
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.compute import (
    ComputeInstance,
    InstanceCapabilities,
    InstanceStatus,
    DrainRequest,
    DrainStatusResponse,
)
from services.registry_service import ComputeRegistry


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry():
    """Create a registry for testing."""
    return ComputeRegistry()


@pytest.fixture
def make_instance():
    """Factory for creating test compute instances."""
    def _make(instance_id="compute-001", project_ids=None, status=InstanceStatus.ONLINE):
        return ComputeInstance(
            instance_id=instance_id,
            name=f"Compute {instance_id}",
            endpoint="sse",
            capabilities=InstanceCapabilities(agents=["agent-a"]),
            project_ids=project_ids if project_ids is not None else ["*"],
            status=status,
        )
    return _make


# =============================================================================
# Model Tests
# =============================================================================


class TestDrainingStatus:
    """Test DRAINING status in InstanceStatus enum."""

    def test_draining_status_exists(self):
        """DRAINING is a valid InstanceStatus value."""
        assert InstanceStatus.DRAINING == "draining"
        assert InstanceStatus.DRAINING.value == "draining"

    def test_instance_can_have_draining_status(self, make_instance):
        """ComputeInstance can be set to DRAINING status."""
        instance = make_instance()
        instance.status = InstanceStatus.DRAINING
        assert instance.status == InstanceStatus.DRAINING

    def test_drain_started_at_default_none(self, make_instance):
        """drain_started_at defaults to None."""
        instance = make_instance()
        assert instance.drain_started_at is None

    def test_drain_started_at_serialization(self, make_instance):
        """drain_started_at survives serialization round-trip."""
        instance = make_instance()
        now = datetime.now(timezone.utc)
        instance.drain_started_at = now
        data = instance.model_dump()
        restored = ComputeInstance(**data)
        assert restored.drain_started_at == now

    def test_heartbeat_doesnt_reset_draining(self, make_instance):
        """update_heartbeat does not reset DRAINING to ONLINE."""
        instance = make_instance()
        instance.status = InstanceStatus.DRAINING
        instance.update_heartbeat()
        assert instance.status == InstanceStatus.DRAINING


class TestDrainRequestModel:
    """Test DrainRequest model."""

    def test_default_auto_deregister_false(self):
        """auto_deregister defaults to False."""
        req = DrainRequest()
        assert req.auto_deregister is False

    def test_with_auto_deregister(self):
        """Can create request with auto_deregister=True."""
        req = DrainRequest(auto_deregister=True)
        assert req.auto_deregister is True


class TestDrainStatusResponseModel:
    """Test DrainStatusResponse model."""

    def test_basic_response(self):
        """Can create a basic drain status response."""
        resp = DrainStatusResponse(
            instance_id="compute-001",
            is_draining=True,
            drain_started_at="2026-02-06T10:00:00+00:00",
            in_flight_work_ids=["work-001"],
            in_flight_count=1,
            drain_complete=False,
        )
        assert resp.instance_id == "compute-001"
        assert resp.is_draining is True
        assert resp.in_flight_count == 1
        assert resp.drain_complete is False

    def test_drain_complete_response(self):
        """Can create a drain complete response."""
        resp = DrainStatusResponse(
            instance_id="compute-001",
            is_draining=True,
            drain_complete=True,
            in_flight_count=0,
        )
        assert resp.drain_complete is True


# =============================================================================
# Registry Service Tests
# =============================================================================


class TestDrainInstance:
    """Test drain_instance method in ComputeRegistry."""

    @pytest.mark.asyncio
    async def test_drain_sets_status_and_clears_projects(self, registry, make_instance):
        """drain_instance sets DRAINING status and removes project tags."""
        instance = make_instance(project_ids=["proj-1", "proj-2"])
        await registry.add_instance(instance)

        result = await registry.drain_instance("compute-001")

        assert result is not None
        assert result.status == InstanceStatus.DRAINING
        assert result.project_ids == []
        assert result.drain_started_at is not None

    @pytest.mark.asyncio
    async def test_drain_removes_from_project_index(self, registry, make_instance):
        """drain_instance removes the instance from the project index."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        assert "compute-001" in registry._project_index.get("proj-1", [])

        await registry.drain_instance("compute-001")

        assert "compute-001" not in registry._project_index.get("proj-1", [])

    @pytest.mark.asyncio
    async def test_drain_with_auto_deregister(self, registry, make_instance):
        """drain_instance stores auto_deregister preference in metadata."""
        instance = make_instance(project_ids=["*"])
        await registry.add_instance(instance)

        result = await registry.drain_instance("compute-001", auto_deregister=True)

        assert result.metadata.get("auto_deregister_on_drain") is True

    @pytest.mark.asyncio
    async def test_drain_without_auto_deregister(self, registry, make_instance):
        """drain_instance does not set auto_deregister flag by default."""
        instance = make_instance(project_ids=["*"])
        await registry.add_instance(instance)

        result = await registry.drain_instance("compute-001")

        assert "auto_deregister_on_drain" not in result.metadata

    @pytest.mark.asyncio
    async def test_drain_already_draining_returns_instance(self, registry, make_instance):
        """drain_instance on already draining instance returns instance unchanged."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        await registry.drain_instance("compute-001")

        result = await registry.drain_instance("compute-001")

        assert result is not None
        assert result.status == InstanceStatus.DRAINING

    @pytest.mark.asyncio
    async def test_drain_nonexistent_returns_none(self, registry):
        """drain_instance on nonexistent instance returns None."""
        result = await registry.drain_instance("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_drain_excludes_from_online_queries(self, registry, make_instance):
        """Draining instances are excluded from online-only queries."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        await registry.drain_instance("compute-001")

        online = await registry.list_instances(status=InstanceStatus.ONLINE)
        draining = await registry.list_instances(status=InstanceStatus.DRAINING)

        assert len(online) == 0
        assert len(draining) == 1


class TestCancelDrain:
    """Test cancel_drain method in ComputeRegistry."""

    @pytest.mark.asyncio
    async def test_cancel_restores_online(self, registry, make_instance):
        """cancel_drain restores ONLINE status."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        await registry.drain_instance("compute-001")

        result = await registry.cancel_drain("compute-001")

        assert result is not None
        assert result.status == InstanceStatus.ONLINE
        assert result.drain_started_at is None

    @pytest.mark.asyncio
    async def test_cancel_clears_auto_deregister(self, registry, make_instance):
        """cancel_drain removes auto_deregister metadata."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        await registry.drain_instance("compute-001", auto_deregister=True)

        result = await registry.cancel_drain("compute-001")

        assert "auto_deregister_on_drain" not in result.metadata

    @pytest.mark.asyncio
    async def test_cancel_keeps_projects_empty(self, registry, make_instance):
        """cancel_drain does not restore project tags (must be re-assigned manually)."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        await registry.drain_instance("compute-001")

        result = await registry.cancel_drain("compute-001")

        assert result.project_ids == []

    @pytest.mark.asyncio
    async def test_cancel_on_non_draining_returns_instance(self, registry, make_instance):
        """cancel_drain on a non-draining instance returns it unchanged."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)

        result = await registry.cancel_drain("compute-001")

        assert result is not None
        assert result.status == InstanceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_none(self, registry):
        """cancel_drain on nonexistent instance returns None."""
        result = await registry.cancel_drain("nonexistent")
        assert result is None


# =============================================================================
# API Tests
# =============================================================================


class TestDrainAPI:
    """Test drain API endpoints."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock registry."""
        registry = MagicMock(spec=ComputeRegistry)
        return registry

    @pytest.fixture
    def app(self, mock_registry):
        """Create test FastAPI app."""
        from fastapi import FastAPI
        from api.compute import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        from services.registry_service import get_compute_registry
        app.dependency_overrides[get_compute_registry] = lambda: mock_registry

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_drain_instance_success(self, client, mock_registry, make_instance):
        """POST /{id}/drain starts draining."""
        instance = make_instance()
        instance.status = InstanceStatus.DRAINING
        instance.project_ids = []
        instance.drain_started_at = datetime.now(timezone.utc)
        mock_registry.drain_instance = AsyncMock(return_value=instance)

        response = client.post(
            "/api/v1/compute/compute-001/drain",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draining"
        assert data["project_ids"] == []
        mock_registry.drain_instance.assert_called_once_with(
            instance_id="compute-001",
            auto_deregister=False,
        )

    def test_drain_instance_with_auto_deregister(self, client, mock_registry, make_instance):
        """POST /{id}/drain with auto_deregister=True passes the flag."""
        instance = make_instance()
        instance.status = InstanceStatus.DRAINING
        instance.project_ids = []
        mock_registry.drain_instance = AsyncMock(return_value=instance)

        response = client.post(
            "/api/v1/compute/compute-001/drain",
            json={"auto_deregister": True},
        )

        assert response.status_code == 200
        mock_registry.drain_instance.assert_called_once_with(
            instance_id="compute-001",
            auto_deregister=True,
        )

    def test_drain_instance_not_found(self, client, mock_registry):
        """POST /{id}/drain returns 404 for unknown instance."""
        mock_registry.drain_instance = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/compute/nonexistent/drain",
            json={},
        )

        assert response.status_code == 404

    def test_drain_status_draining(self, client, mock_registry, make_instance):
        """GET /{id}/drain returns drain status when draining."""
        instance = make_instance()
        instance.status = InstanceStatus.DRAINING
        instance.drain_started_at = datetime.now(timezone.utc)
        mock_registry.get_instance = AsyncMock(return_value=instance)

        with patch("services.work_map_service.get_work_map_service") as mock_wms:
            mock_service = MagicMock()
            mock_work_list = MagicMock()
            mock_work_list.items = []
            mock_service.list_work = AsyncMock(return_value=mock_work_list)
            mock_wms.return_value = mock_service

            response = client.get("/api/v1/compute/compute-001/drain")

        assert response.status_code == 200
        data = response.json()
        assert data["is_draining"] is True
        assert data["in_flight_count"] == 0
        assert data["drain_complete"] is True

    def test_drain_status_not_draining(self, client, mock_registry, make_instance):
        """GET /{id}/drain returns not draining when instance is online."""
        instance = make_instance()
        mock_registry.get_instance = AsyncMock(return_value=instance)

        response = client.get("/api/v1/compute/compute-001/drain")

        assert response.status_code == 200
        data = response.json()
        assert data["is_draining"] is False
        assert data["drain_complete"] is False

    def test_drain_status_not_found(self, client, mock_registry):
        """GET /{id}/drain returns 404 for unknown instance."""
        mock_registry.get_instance = AsyncMock(return_value=None)

        response = client.get("/api/v1/compute/nonexistent/drain")

        assert response.status_code == 404

    def test_cancel_drain_success(self, client, mock_registry, make_instance):
        """DELETE /{id}/drain cancels drain."""
        instance = make_instance()
        instance.status = InstanceStatus.ONLINE
        instance.drain_started_at = None
        mock_registry.cancel_drain = AsyncMock(return_value=instance)

        response = client.delete("/api/v1/compute/compute-001/drain")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        mock_registry.cancel_drain.assert_called_once_with("compute-001")

    def test_cancel_drain_not_found(self, client, mock_registry):
        """DELETE /{id}/drain returns 404 for unknown instance."""
        mock_registry.cancel_drain = AsyncMock(return_value=None)

        response = client.delete("/api/v1/compute/nonexistent/drain")

        assert response.status_code == 404
