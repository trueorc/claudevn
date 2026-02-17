"""Tests for specialization integration with SSEConnectionManager and API."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from services.sse_connection_manager import SSEConnectionManager, SSEConnection
from services.specialization_service import (
    SpecializationService,
    set_specialization_service,
)
from api.specialization import router


class TestSSEConnectionManagerSpecialization:
    """Test find_matching_connection with specialization_scores."""

    @pytest.fixture
    def manager(self):
        return SSEConnectionManager()

    @pytest.fixture
    async def two_connections(self, manager):
        """Register two idle connections."""
        await manager.register_connection(
            compute_id="compute-a",
            capabilities=["coding"],
            resources={},
        )
        await manager.register_connection(
            compute_id="compute-b",
            capabilities=["coding"],
            resources={},
        )
        return manager

    @pytest.mark.asyncio
    async def test_without_scores_returns_first_match(self, two_connections):
        """Without scores, returns first matching connection (existing behavior)."""
        manager = two_connections
        conn = manager.find_matching_connection()
        assert conn is not None
        # Should return one of the two (deterministic order is dict insertion order)
        assert conn.compute_id in ("compute-a", "compute-b")

    @pytest.mark.asyncio
    async def test_with_scores_returns_highest(self, two_connections):
        """With scores, returns the highest-scored connection."""
        manager = two_connections
        conn = manager.find_matching_connection(
            specialization_scores={"compute-a": 0.3, "compute-b": 0.9}
        )
        assert conn is not None
        assert conn.compute_id == "compute-b"

    @pytest.mark.asyncio
    async def test_with_scores_a_higher(self, two_connections):
        """With reversed scores, returns compute-a."""
        manager = two_connections
        conn = manager.find_matching_connection(
            specialization_scores={"compute-a": 0.8, "compute-b": 0.2}
        )
        assert conn is not None
        assert conn.compute_id == "compute-a"

    @pytest.mark.asyncio
    async def test_scores_with_no_candidates(self, manager):
        """No candidates with scores still returns None."""
        conn = manager.find_matching_connection(
            specialization_scores={"compute-a": 0.9}
        )
        assert conn is None

    @pytest.mark.asyncio
    async def test_scores_with_capability_filter(self, manager):
        """Scores apply after capability filtering."""
        await manager.register_connection(
            compute_id="compute-a",
            capabilities=["coding"],
            resources={},
        )
        await manager.register_connection(
            compute_id="compute-b",
            capabilities=["testing"],
            resources={},
        )

        # compute-b scores higher but doesn't have "coding" capability
        conn = manager.find_matching_connection(
            required_capabilities=["coding"],
            specialization_scores={"compute-a": 0.3, "compute-b": 0.9},
        )
        assert conn is not None
        assert conn.compute_id == "compute-a"

    @pytest.mark.asyncio
    async def test_scores_only_idle_considered(self, two_connections):
        """Busy connections are filtered out before scoring."""
        manager = two_connections
        # Make compute-b busy
        conn_b = manager.get_connection("compute-b")
        conn_b.status = "busy"

        conn = manager.find_matching_connection(
            specialization_scores={"compute-a": 0.1, "compute-b": 0.9}
        )
        assert conn is not None
        assert conn.compute_id == "compute-a"


class TestSpecializationAPI:
    """Test specialization REST API endpoints."""

    @pytest.fixture
    def service(self):
        svc = SpecializationService(redis_client=None)
        set_specialization_service(svc)
        return svc

    @pytest.fixture
    def client(self, service):
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_list_profiles_empty(self, client):
        resp = client.get("/specialization/proj-001/profiles")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_set_and_get_profile(self, client):
        # Create profile
        resp = client.put(
            "/specialization/proj-001/profiles/compute-a",
            json={"cluster_ids": ["cluster-frontend", "cluster-api"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compute_id"] == "compute-a"
        assert data["cluster_ids"] == ["cluster-frontend", "cluster-api"]

        # Get it back
        resp = client.get("/specialization/proj-001/profiles/compute-a")
        assert resp.status_code == 200
        assert resp.json()["cluster_ids"] == ["cluster-frontend", "cluster-api"]

    def test_get_profile_not_found(self, client):
        resp = client.get("/specialization/proj-001/profiles/nonexistent")
        assert resp.status_code == 404

    def test_delete_profile(self, client):
        client.put(
            "/specialization/proj-001/profiles/compute-a",
            json={"cluster_ids": ["cluster-frontend"]},
        )
        resp = client.delete("/specialization/proj-001/profiles/compute-a")
        assert resp.status_code == 200

        resp = client.get("/specialization/proj-001/profiles/compute-a")
        assert resp.status_code == 404

    def test_delete_profile_not_found(self, client):
        resp = client.delete("/specialization/proj-001/profiles/nonexistent")
        assert resp.status_code == 404

    def test_list_profiles(self, client):
        client.put(
            "/specialization/proj-001/profiles/compute-a",
            json={"cluster_ids": ["cluster-frontend"]},
        )
        client.put(
            "/specialization/proj-001/profiles/compute-b",
            json={"cluster_ids": ["cluster-backend"]},
        )

        resp = client.get("/specialization/proj-001/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_utilization_endpoint(self, client, service):
        service.set_profile("compute-a", "proj-001", ["cluster-frontend"])
        service.record_completion("compute-a", ["cluster-frontend"])

        resp = client.get("/specialization/proj-001/utilization")
        assert resp.status_code == 200
        data = resp.json()
        assert "compute-a" in data

    def test_imbalances_endpoint(self, client, service):
        service.set_profile("compute-a", "proj-001", ["cluster-frontend"])
        service.set_profile("compute-b", "proj-001", ["cluster-frontend"])

        resp = client.get("/specialization/proj-001/imbalances")
        assert resp.status_code == 200
        # No imbalances expected since both cover same cluster

    def test_summary_endpoint(self, client, service):
        service.set_profile("compute-a", "proj-001", ["cluster-frontend"])

        resp = client.get("/specialization/proj-001/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "proj-001"
        assert data["total_workers"] == 1
        assert data["total_clusters_covered"] == 1
