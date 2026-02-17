"""Unit tests for work map filtering functionality.

Tests that the list_work method properly filters work items by:
- status
- priority
- project_id
- assigned_to

These tests verify issue #374 is fixed.
"""

import pytest
from datetime import datetime, timezone

from models.work_map import (
    WorkItem, WorkStatus, WorkPriority, WorkCreateRequest, WorkListResponse
)
from services.work_map_service import WorkMapService


@pytest.fixture
def work_map_service():
    """Create a WorkMapService without Redis for testing."""
    service = WorkMapService(redis_client=None)
    service._initialized = True
    return service


@pytest.fixture
def sample_work_items(work_map_service):
    """Create sample work items for filter testing."""
    items = [
        WorkItem(
            work_id="work_001",
            title="Critical task in project A",
            description="Test item 1",
            work_type="task",
            priority=WorkPriority.CRITICAL,
            status=WorkStatus.PENDING,
            project_id="project_a",
            assigned_to=None
        ),
        WorkItem(
            work_id="work_002",
            title="High priority task in project A",
            description="Test item 2",
            work_type="task",
            priority=WorkPriority.HIGH,
            status=WorkStatus.IN_PROGRESS,
            project_id="project_a",
            assigned_to="compute_001"
        ),
        WorkItem(
            work_id="work_003",
            title="Normal task in project B",
            description="Test item 3",
            work_type="task",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.PENDING,
            project_id="project_b",
            assigned_to=None
        ),
        WorkItem(
            work_id="work_004",
            title="Low priority completed task",
            description="Test item 4",
            work_type="task",
            priority=WorkPriority.LOW,
            status=WorkStatus.COMPLETED,
            project_id="project_b",
            assigned_to="compute_002"
        ),
    ]

    for item in items:
        work_map_service._work_items[item.work_id] = item

    return items


class TestWorkMapFilters:
    """Test work item filtering functionality."""

    @pytest.mark.asyncio
    async def test_list_work_no_filters(self, work_map_service, sample_work_items):
        """Test listing all work items without filters."""
        result = await work_map_service.list_work()

        assert isinstance(result, WorkListResponse)
        assert result.total == 4
        assert len(result.items) == 4

    @pytest.mark.asyncio
    async def test_filter_by_status_pending(self, work_map_service, sample_work_items):
        """Test filtering by pending status."""
        result = await work_map_service.list_work(status=WorkStatus.PENDING)

        assert len(result.items) == 2
        assert all(item.status == WorkStatus.PENDING for item in result.items)
        work_ids = [item.work_id for item in result.items]
        assert "work_001" in work_ids
        assert "work_003" in work_ids

    @pytest.mark.asyncio
    async def test_filter_by_status_in_progress(self, work_map_service, sample_work_items):
        """Test filtering by in_progress status."""
        result = await work_map_service.list_work(status=WorkStatus.IN_PROGRESS)

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_002"
        assert result.items[0].status == WorkStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_filter_by_status_completed(self, work_map_service, sample_work_items):
        """Test filtering by completed status."""
        result = await work_map_service.list_work(status=WorkStatus.COMPLETED)

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_004"
        assert result.items[0].status == WorkStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_filter_by_priority_critical(self, work_map_service, sample_work_items):
        """Test filtering by critical priority."""
        result = await work_map_service.list_work(priority=WorkPriority.CRITICAL)

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_001"
        assert result.items[0].priority == WorkPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_filter_by_priority_high(self, work_map_service, sample_work_items):
        """Test filtering by high priority."""
        result = await work_map_service.list_work(priority=WorkPriority.HIGH)

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_002"

    @pytest.mark.asyncio
    async def test_filter_by_project_id(self, work_map_service, sample_work_items):
        """Test filtering by project ID."""
        result = await work_map_service.list_work(project_id="project_a")

        assert len(result.items) == 2
        assert all(item.project_id == "project_a" for item in result.items)
        work_ids = [item.work_id for item in result.items]
        assert "work_001" in work_ids
        assert "work_002" in work_ids

    @pytest.mark.asyncio
    async def test_filter_by_assigned_to(self, work_map_service, sample_work_items):
        """Test filtering by assignee."""
        result = await work_map_service.list_work(assigned_to="compute_001")

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_002"
        assert result.items[0].assigned_to == "compute_001"

    @pytest.mark.asyncio
    async def test_combined_filters_status_and_project(self, work_map_service, sample_work_items):
        """Test combining status and project filters."""
        result = await work_map_service.list_work(
            status=WorkStatus.PENDING,
            project_id="project_a"
        )

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_001"
        assert result.items[0].status == WorkStatus.PENDING
        assert result.items[0].project_id == "project_a"

    @pytest.mark.asyncio
    async def test_combined_filters_priority_and_status(self, work_map_service, sample_work_items):
        """Test combining priority and status filters."""
        result = await work_map_service.list_work(
            priority=WorkPriority.LOW,
            status=WorkStatus.COMPLETED
        )

        assert len(result.items) == 1
        assert result.items[0].work_id == "work_004"

    @pytest.mark.asyncio
    async def test_filter_no_matches(self, work_map_service, sample_work_items):
        """Test filter that returns no matches."""
        result = await work_map_service.list_work(
            status=WorkStatus.BLOCKED
        )

        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_filter_preserves_stats(self, work_map_service, sample_work_items):
        """Test that filtering still returns correct total stats."""
        result = await work_map_service.list_work(status=WorkStatus.PENDING)

        # Filtered items should only be pending
        assert len(result.items) == 2
        # But total should reflect all items
        assert result.total == 4
        # by_status should show all statuses
        assert result.by_status.get("pending", 0) == 2
        assert result.by_status.get("in_progress", 0) == 1
        assert result.by_status.get("completed", 0) == 1
