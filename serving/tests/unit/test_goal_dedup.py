"""Tests for goal creation deduplication (#682).

Verifies that GoalService.create_goal() deduplicates rapid identical
submissions: same description + project_id within 60 seconds returns
the existing goal instead of creating a duplicate.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.goal_service import GoalService
from models.work_map import (
    Goal, GoalStatus, GoalCreateRequest, IssuePriority
)


@pytest.fixture
def service():
    """Create GoalService without Redis for in-memory testing."""
    return GoalService(redis_client=None)


def _make_request(
    description="Build auth system",
    project_id="proj_abc",
    title="Test Goal",
    priority=IssuePriority.P1,
):
    return GoalCreateRequest(
        title=title,
        description=description,
        project_id=project_id,
        priority=priority,
    )


class TestGoalDeduplication:
    """Test deduplication of rapid identical goal submissions."""

    @pytest.mark.asyncio
    async def test_same_description_same_project_returns_existing(self, service):
        """Same description + project_id within 60s returns existing goal."""
        request = _make_request()

        goal1 = await service.create_goal(request)
        goal2 = await service.create_goal(request)

        assert goal1.goal_id == goal2.goal_id
        assert goal2 is goal1

    @pytest.mark.asyncio
    async def test_different_description_creates_new(self, service):
        """Different descriptions always create new goals."""
        goal1 = await service.create_goal(
            _make_request(description="Build auth system")
        )
        goal2 = await service.create_goal(
            _make_request(description="Build payment system")
        )

        assert goal1.goal_id != goal2.goal_id

    @pytest.mark.asyncio
    async def test_different_project_creates_new(self, service):
        """Different project_ids always create new goals."""
        goal1 = await service.create_goal(
            _make_request(project_id="proj_abc")
        )
        goal2 = await service.create_goal(
            _make_request(project_id="proj_xyz")
        )

        assert goal1.goal_id != goal2.goal_id

    @pytest.mark.asyncio
    async def test_outside_window_creates_new(self, service):
        """Same description + project_id outside 60s window creates new goal."""
        request = _make_request()

        goal1 = await service.create_goal(request)

        # Backdate the existing goal to 61 seconds ago
        goal1.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)

        goal2 = await service.create_goal(request)

        assert goal1.goal_id != goal2.goal_id

    @pytest.mark.asyncio
    async def test_at_window_boundary_creates_new(self, service):
        """Exactly at the 60s boundary creates a new goal."""
        request = _make_request()

        goal1 = await service.create_goal(request)

        # Backdate to exactly 60 seconds ago
        goal1.created_at = datetime.now(timezone.utc) - timedelta(seconds=60)

        goal2 = await service.create_goal(request)

        assert goal1.goal_id != goal2.goal_id

    @pytest.mark.asyncio
    async def test_empty_description_skips_dedup(self, service):
        """Empty string description skips deduplication."""
        request1 = GoalCreateRequest(
            title="Goal A",
            description="",
            project_id="proj_abc",
        )
        request2 = GoalCreateRequest(
            title="Goal B",
            description="",
            project_id="proj_abc",
        )

        goal1 = await service.create_goal(request1)
        goal2 = await service.create_goal(request2)

        assert goal1.goal_id != goal2.goal_id

    @pytest.mark.asyncio
    async def test_none_project_id_skips_dedup(self, service):
        """Goals without project_id should not be deduplicated."""
        request1 = GoalCreateRequest(
            title="Goal A",
            description="Build auth system",
            project_id=None,
        )
        request2 = GoalCreateRequest(
            title="Goal B",
            description="Build auth system",
            project_id=None,
        )

        goal1 = await service.create_goal(request1)
        goal2 = await service.create_goal(request2)

        assert goal1.goal_id != goal2.goal_id


class TestGoalDeduplicationEdgeCases:
    """Edge cases for goal deduplication."""

    @pytest.mark.asyncio
    async def test_deleted_goal_does_not_block_new_creation(self, service):
        """Soft-deleted goal with same description should not prevent new goal."""
        request = _make_request()

        goal1 = await service.create_goal(request)
        await service.delete_goal(goal1.goal_id)  # soft delete

        goal2 = await service.create_goal(request)

        assert goal1.goal_id != goal2.goal_id

    @pytest.mark.asyncio
    async def test_dedup_returns_same_object(self, service):
        """Deduplicated call returns the exact same goal instance."""
        request = _make_request()

        goal1 = await service.create_goal(request)
        goal2 = await service.create_goal(request)

        # Should be the same object, not a copy
        assert goal1 is goal2

    @pytest.mark.asyncio
    async def test_dedup_does_not_create_extra_entries(self, service):
        """Deduplication should not increase the goal count."""
        request = _make_request()

        await service.create_goal(request)
        await service.create_goal(request)
        await service.create_goal(request)

        result = await service.list_goals()
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_within_window_returns_existing(self, service):
        """Goal created 30s ago with same params is still deduplicated."""
        request = _make_request()

        goal1 = await service.create_goal(request)

        # Backdate to 30 seconds ago (within window)
        goal1.created_at = datetime.now(timezone.utc) - timedelta(seconds=30)

        goal2 = await service.create_goal(request)

        assert goal1.goal_id == goal2.goal_id

    @pytest.mark.asyncio
    async def test_different_title_same_description_deduplicates(self, service):
        """Dedup is based on description, not title — different titles still dedup."""
        goal1 = await service.create_goal(
            _make_request(title="Title A", description="Same desc")
        )
        goal2 = await service.create_goal(
            _make_request(title="Title B", description="Same desc")
        )

        assert goal1.goal_id == goal2.goal_id

    @pytest.mark.asyncio
    async def test_different_priority_same_description_deduplicates(self, service):
        """Dedup is based on description + project_id, not priority."""
        goal1 = await service.create_goal(
            _make_request(priority=IssuePriority.P0)
        )
        goal2 = await service.create_goal(
            _make_request(priority=IssuePriority.P3)
        )

        assert goal1.goal_id == goal2.goal_id
