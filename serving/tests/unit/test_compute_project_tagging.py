"""Tests for compute instance project tagging (issue #451).

Tests cover:
- Model: project_ids field on ComputeInstance
- Registry: project index, update_project_tags, get_by_project
- Assignment: project-scoped filtering in get_next_assignment
- API: PUT /{id}/projects, GET /search/by-project/{project_id}
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.compute import (
    ComputeInstance,
    InstanceCapabilities,
    InstanceStatus,
    UpdateProjectTagsRequest,
)
from services.registry_service import ComputeRegistry
from services.assignment_service import AssignmentService
from models.work_map import WorkItem, WorkStatus, WorkPriority


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
    def _make(instance_id="compute-001", project_ids=None):
        return ComputeInstance(
            instance_id=instance_id,
            name=f"Compute {instance_id}",
            endpoint="sse",
            capabilities=InstanceCapabilities(agents=["agent-a"]),
            project_ids=project_ids or [],
        )
    return _make


@pytest.fixture
def service():
    """Create assignment service without Redis."""
    return AssignmentService(redis_client=None)


@pytest.fixture
def make_work_item():
    """Factory for creating test work items."""
    def _make(work_id="work-001", project_id="proj-001", status=WorkStatus.PENDING):
        return WorkItem(
            work_id=work_id,
            title=f"Work {work_id}",
            description="Test work",
            project_id=project_id,
            status=status,
            branch_name=f"work/{work_id}",
            base_branch="main",
        )
    return _make


# =============================================================================
# Model Tests
# =============================================================================


class TestComputeInstanceProjectIds:
    """Test project_ids field on ComputeInstance model."""

    def test_default_all_projects(self):
        """New instances default to all projects (wildcard)."""
        instance = ComputeInstance(
            instance_id="test",
            name="Test",
            endpoint="sse",
        )
        assert instance.project_ids == ["*"]

    def test_with_specific_projects(self):
        """Instance can be created with specific project IDs."""
        instance = ComputeInstance(
            instance_id="test",
            name="Test",
            endpoint="sse",
            project_ids=["proj-1", "proj-2"],
        )
        assert instance.project_ids == ["proj-1", "proj-2"]

    def test_with_wildcard(self):
        """Instance can be created with wildcard."""
        instance = ComputeInstance(
            instance_id="test",
            name="Test",
            endpoint="sse",
            project_ids=["*"],
        )
        assert instance.project_ids == ["*"]

    def test_serialization(self):
        """project_ids survives serialization round-trip."""
        instance = ComputeInstance(
            instance_id="test",
            name="Test",
            endpoint="sse",
            project_ids=["proj-1"],
        )
        data = instance.model_dump()
        restored = ComputeInstance(**data)
        assert restored.project_ids == ["proj-1"]


class TestUpdateProjectTagsRequest:
    """Test UpdateProjectTagsRequest model."""

    def test_empty_projects(self):
        """Can create request with empty project_ids (bench)."""
        req = UpdateProjectTagsRequest(project_ids=[])
        assert req.project_ids == []

    def test_specific_projects(self):
        """Can create request with specific project IDs."""
        req = UpdateProjectTagsRequest(project_ids=["proj-1", "proj-2"])
        assert req.project_ids == ["proj-1", "proj-2"]

    def test_wildcard(self):
        """Can create request with wildcard."""
        req = UpdateProjectTagsRequest(project_ids=["*"])
        assert req.project_ids == ["*"]


# =============================================================================
# Registry Service Tests
# =============================================================================


class TestRegistryProjectIndex:
    """Test project index management in ComputeRegistry."""

    @pytest.mark.asyncio
    async def test_add_instance_indexes_projects(self, registry, make_instance):
        """Adding an instance with project_ids updates the project index."""
        instance = make_instance(project_ids=["proj-1", "proj-2"])
        await registry.add_instance(instance)

        assert "compute-001" in registry._project_index.get("proj-1", [])
        assert "compute-001" in registry._project_index.get("proj-2", [])

    @pytest.mark.asyncio
    async def test_add_benched_instance_no_index(self, registry, make_instance):
        """Adding a benched instance (empty project_ids) adds nothing to project index."""
        instance = make_instance(project_ids=[])
        await registry.add_instance(instance)

        assert len(registry._project_index) == 0

    @pytest.mark.asyncio
    async def test_remove_instance_cleans_project_index(self, registry, make_instance):
        """Removing an instance cleans up the project index."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)
        assert "compute-001" in registry._project_index.get("proj-1", [])

        await registry.remove_instance("compute-001")
        assert "compute-001" not in registry._project_index.get("proj-1", [])


class TestUpdateProjectTags:
    """Test update_project_tags method."""

    @pytest.mark.asyncio
    async def test_update_tags(self, registry, make_instance):
        """Can update project tags for an instance."""
        instance = make_instance(project_ids=[])
        await registry.add_instance(instance)

        updated = await registry.update_project_tags("compute-001", ["proj-1", "proj-2"])

        assert updated is not None
        assert updated.project_ids == ["proj-1", "proj-2"]
        assert "compute-001" in registry._project_index["proj-1"]
        assert "compute-001" in registry._project_index["proj-2"]

    @pytest.mark.asyncio
    async def test_update_tags_replaces_old(self, registry, make_instance):
        """Updating tags replaces old project index entries."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)

        await registry.update_project_tags("compute-001", ["proj-2"])

        assert "compute-001" not in registry._project_index.get("proj-1", [])
        assert "compute-001" in registry._project_index["proj-2"]

    @pytest.mark.asyncio
    async def test_bench_instance(self, registry, make_instance):
        """Setting empty project_ids benches the instance."""
        instance = make_instance(project_ids=["proj-1"])
        await registry.add_instance(instance)

        updated = await registry.update_project_tags("compute-001", [])

        assert updated.project_ids == []
        assert "compute-001" not in registry._project_index.get("proj-1", [])

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, registry):
        """Updating tags for nonexistent instance returns None."""
        result = await registry.update_project_tags("nonexistent", ["proj-1"])
        assert result is None


class TestGetByProject:
    """Test get_by_project method."""

    @pytest.mark.asyncio
    async def test_find_tagged_instances(self, registry, make_instance):
        """Finds instances tagged for a specific project."""
        inst1 = make_instance("compute-001", project_ids=["proj-1"])
        inst2 = make_instance("compute-002", project_ids=["proj-1", "proj-2"])
        inst3 = make_instance("compute-003", project_ids=["proj-2"])
        await registry.add_instance(inst1)
        await registry.add_instance(inst2)
        await registry.add_instance(inst3)

        result = await registry.get_by_project("proj-1")
        ids = [i.instance_id for i in result]

        assert "compute-001" in ids
        assert "compute-002" in ids
        assert "compute-003" not in ids

    @pytest.mark.asyncio
    async def test_wildcard_included(self, registry, make_instance):
        """Instances with '*' wildcard are included for any project."""
        inst1 = make_instance("compute-001", project_ids=["*"])
        inst2 = make_instance("compute-002", project_ids=["proj-1"])
        await registry.add_instance(inst1)
        await registry.add_instance(inst2)

        result = await registry.get_by_project("proj-999")
        ids = [i.instance_id for i in result]

        assert "compute-001" in ids  # wildcard
        assert "compute-002" not in ids  # not tagged for proj-999

    @pytest.mark.asyncio
    async def test_benched_excluded(self, registry, make_instance):
        """Benched instances (empty project_ids) are not returned."""
        inst = make_instance("compute-001", project_ids=[])
        await registry.add_instance(inst)

        result = await registry.get_by_project("proj-1")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_offline_filtered(self, registry, make_instance):
        """Offline instances are filtered when online_only=True."""
        inst = make_instance("compute-001", project_ids=["proj-1"])
        await registry.add_instance(inst)
        await registry.update_status("compute-001", InstanceStatus.OFFLINE)

        online_result = await registry.get_by_project("proj-1", online_only=True)
        all_result = await registry.get_by_project("proj-1", online_only=False)

        assert len(online_result) == 0
        assert len(all_result) == 1


# =============================================================================
# Assignment Service Tests
# =============================================================================


class TestAssignmentProjectFiltering:
    """Test project-scoped filtering in get_next_assignment."""

    @pytest.mark.asyncio
    async def test_benched_compute_gets_no_work(self, service, make_work_item):
        """Benched compute (empty project_ids) receives no work."""
        work = make_work_item()
        service.set_work_items_reference({work.work_id: work})

        result = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=[],  # benched
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_scoped_compute_gets_matching_work(self, service, make_work_item):
        """Scoped compute gets work from its project."""
        work = make_work_item(project_id="proj-001")
        service.set_work_items_reference({work.work_id: work})

        result = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=["proj-001"],
        )
        assert result is not None
        assert result.work_id == "work-001"

    @pytest.mark.asyncio
    async def test_scoped_compute_skips_other_projects(self, service, make_work_item):
        """Scoped compute does not get work from untagged projects."""
        work = make_work_item(project_id="proj-002")
        service.set_work_items_reference({work.work_id: work})

        result = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=["proj-001"],  # not tagged for proj-002
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_wildcard_gets_any_work(self, service, make_work_item):
        """Compute with '*' wildcard gets work from any project."""
        work = make_work_item(project_id="proj-999")
        service.set_work_items_reference({work.work_id: work})

        result = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=["*"],
        )
        assert result is not None
        assert result.work_id == "work-001"

    @pytest.mark.asyncio
    async def test_multi_project_compute(self, service, make_work_item):
        """Compute tagged for multiple projects gets work from any of them."""
        work1 = make_work_item("work-001", project_id="proj-001")
        work2 = make_work_item("work-002", project_id="proj-002")
        service.set_work_items_reference({
            work1.work_id: work1,
            work2.work_id: work2,
        })

        result = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=["proj-001", "proj-002"],
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_project_ids_none_skips_filter(self, service, make_work_item):
        """If project_ids is not passed (None), project filter is skipped (legacy compat)."""
        work = make_work_item()
        service.set_work_items_reference({work.work_id: work})

        result = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            # project_ids not passed, defaults to None -> no filtering
        )
        assert result is not None


# =============================================================================
# API Tests
# =============================================================================


class TestComputeProjectTagsAPI:
    """Test API endpoints for project tagging."""

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

        # Override registry dependency
        from services.registry_service import get_compute_registry
        app.dependency_overrides[get_compute_registry] = lambda: mock_registry

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_update_project_tags_success(self, client, mock_registry, make_instance):
        """PUT /{instance_id}/projects updates project tags."""
        instance = make_instance(project_ids=["proj-1"])
        mock_registry.update_project_tags = AsyncMock(return_value=instance)

        response = client.put(
            "/api/v1/compute/compute-001/projects",
            json={"project_ids": ["proj-1"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["project_ids"] == ["proj-1"]
        mock_registry.update_project_tags.assert_called_once_with(
            instance_id="compute-001",
            project_ids=["proj-1"],
        )

    def test_update_project_tags_not_found(self, client, mock_registry):
        """PUT /{instance_id}/projects returns 404 for unknown instance."""
        mock_registry.update_project_tags = AsyncMock(return_value=None)

        response = client.put(
            "/api/v1/compute/nonexistent/projects",
            json={"project_ids": ["proj-1"]},
        )

        assert response.status_code == 404

    def test_update_project_tags_bench(self, client, mock_registry, make_instance):
        """PUT /{instance_id}/projects with empty list benches instance."""
        instance = make_instance(project_ids=[])
        mock_registry.update_project_tags = AsyncMock(return_value=instance)

        response = client.put(
            "/api/v1/compute/compute-001/projects",
            json={"project_ids": []},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["project_ids"] == []

    def test_search_by_project(self, client, mock_registry, make_instance):
        """GET /search/by-project/{project_id} returns tagged instances."""
        inst = make_instance(project_ids=["proj-1"])
        mock_registry.get_by_project = AsyncMock(return_value=[inst])

        response = client.get("/api/v1/compute/search/by-project/proj-1")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["instance_id"] == "compute-001"

    def test_search_by_project_empty(self, client, mock_registry):
        """GET /search/by-project/{project_id} returns empty for no matches."""
        mock_registry.get_by_project = AsyncMock(return_value=[])

        response = client.get("/api/v1/compute/search/by-project/proj-999")

        assert response.status_code == 200
        assert response.json() == []
