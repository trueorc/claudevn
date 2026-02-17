"""Tests for WorkMapService.get_dependencies_bulk method.

Validates the batch dependency check that replaces per-item
get_dependencies() calls in the orchestrator polling loop.
"""

import pytest
from unittest.mock import AsyncMock

from services.work_map_service import WorkMapService
from models.work_map import WorkItem, WorkStatus, WorkPriority


@pytest.fixture
def service():
    """Create a WorkMapService with no Redis."""
    svc = WorkMapService(redis_client=None)
    svc._save_to_redis = AsyncMock()
    return svc


def _make_work(work_id, depends_on=None, status=WorkStatus.PENDING):
    """Create a WorkItem for testing."""
    return WorkItem(
        work_id=work_id,
        title=f"Work {work_id}",
        description="Test",
        project_id="test-project",
        status=status,
        priority=WorkPriority.NORMAL,
        depends_on=depends_on or [],
    )


class TestGetDependenciesBulk:
    """Tests for batch dependency checking."""

    @pytest.mark.asyncio
    async def test_empty_list(self, service):
        """Empty input returns empty result."""
        result = await service.get_dependencies_bulk([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_dependencies(self, service):
        """Work with no dependencies reports all met."""
        work = _make_work("work-1")
        service._work_items["work-1"] = work

        result = await service.get_dependencies_bulk(["work-1"])
        assert result == {"work-1": True}

    @pytest.mark.asyncio
    async def test_all_dependencies_met(self, service):
        """Work whose dependency is COMPLETED reports all met."""
        dep = _make_work("dep-1", status=WorkStatus.COMPLETED)
        work = _make_work("work-1", depends_on=["dep-1"])
        service._work_items["dep-1"] = dep
        service._work_items["work-1"] = work

        result = await service.get_dependencies_bulk(["work-1"])
        assert result == {"work-1": True}

    @pytest.mark.asyncio
    async def test_unmet_dependencies(self, service):
        """Work whose dependency is not COMPLETED reports unmet."""
        dep = _make_work("dep-1", status=WorkStatus.IN_PROGRESS)
        work = _make_work("work-1", depends_on=["dep-1"])
        service._work_items["dep-1"] = dep
        service._work_items["work-1"] = work

        result = await service.get_dependencies_bulk(["work-1"])
        assert result == {"work-1": False}

    @pytest.mark.asyncio
    async def test_multiple_items_mixed(self, service):
        """Batch with mixed dependency status."""
        dep_done = _make_work("dep-done", status=WorkStatus.COMPLETED)
        dep_pending = _make_work("dep-pending", status=WorkStatus.PENDING)

        work_a = _make_work("work-a", depends_on=["dep-done"])
        work_b = _make_work("work-b", depends_on=["dep-pending"])
        work_c = _make_work("work-c")  # no deps

        service._work_items.update({
            "dep-done": dep_done,
            "dep-pending": dep_pending,
            "work-a": work_a,
            "work-b": work_b,
            "work-c": work_c,
        })

        result = await service.get_dependencies_bulk(["work-a", "work-b", "work-c"])
        assert result == {
            "work-a": True,
            "work-b": False,
            "work-c": True,
        }

    @pytest.mark.asyncio
    async def test_unknown_work_id(self, service):
        """Unknown work_id defaults to True (don't block)."""
        result = await service.get_dependencies_bulk(["nonexistent"])
        assert result == {"nonexistent": True}

    @pytest.mark.asyncio
    async def test_dependency_on_missing_item(self, service):
        """Work depending on a missing item reports all met (missing deps don't block)."""
        work = _make_work("work-1", depends_on=["missing-dep"])
        service._work_items["work-1"] = work

        result = await service.get_dependencies_bulk(["work-1"])
        # Missing dependency is not found in _work_items, so the inner loop
        # never sets all_met = False
        assert result == {"work-1": True}

    @pytest.mark.asyncio
    async def test_multiple_dependencies_all_must_be_met(self, service):
        """If one of multiple dependencies is unmet, the work is not ready."""
        dep_1 = _make_work("dep-1", status=WorkStatus.COMPLETED)
        dep_2 = _make_work("dep-2", status=WorkStatus.IN_PROGRESS)
        work = _make_work("work-1", depends_on=["dep-1", "dep-2"])

        service._work_items.update({
            "dep-1": dep_1,
            "dep-2": dep_2,
            "work-1": work,
        })

        result = await service.get_dependencies_bulk(["work-1"])
        assert result == {"work-1": False}

    @pytest.mark.asyncio
    async def test_short_circuits_on_first_unmet(self, service):
        """Should return False as soon as any dependency is unmet (optimization)."""
        # Create many deps, first one unmet
        deps = {}
        dep_ids = []
        for i in range(10):
            dep_id = f"dep-{i}"
            dep_ids.append(dep_id)
            status = WorkStatus.PENDING if i == 0 else WorkStatus.COMPLETED
            deps[dep_id] = _make_work(dep_id, status=status)

        work = _make_work("work-1", depends_on=dep_ids)
        service._work_items.update(deps)
        service._work_items["work-1"] = work

        result = await service.get_dependencies_bulk(["work-1"])
        assert result == {"work-1": False}
