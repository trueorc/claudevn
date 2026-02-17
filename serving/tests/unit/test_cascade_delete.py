"""Tests for cascade delete functionality in WorkMapService."""

import pytest
from unittest.mock import AsyncMock, patch

from services.work_map_service import WorkMapService
from models.work_map import (
    GoalCreateRequest, IssueCreateRequest, WorkCreateRequest,
    WorkPriority, IssuePriority,
)


@pytest.fixture
def service():
    """Create service without Redis for in-memory testing."""
    return WorkMapService(redis_client=None)


_goal_counter = 0


async def _create_goal(service, project_id="proj-001", title="Test Goal"):
    """Helper to create a goal with unique description to avoid dedup."""
    global _goal_counter
    _goal_counter += 1
    req = GoalCreateRequest(
        title=title,
        description=f"Test goal description #{_goal_counter}",
        priority=IssuePriority.P1,
        project_id=project_id,
    )
    return await service.create_goal(req)


async def _create_issue(service, goal_id=None, parent_issue_id=None, project_id="proj-001"):
    """Helper to create an issue."""
    req = IssueCreateRequest(
        title="Test Issue",
        description="Test issue description",
        goal_id=goal_id,
        parent_issue_id=parent_issue_id,
        project_id=project_id,
    )
    return await service.create_issue(req)


async def _create_work(service, issue_id=None, project_id="proj-001"):
    """Helper to create a work item."""
    req = WorkCreateRequest(
        title="Test Work",
        description="Test work description",
        project_id=project_id,
        issue_id=issue_id,
    )
    return await service.create_work(req)


# ============ Issue Cascade Delete ============


class TestIssueCascadeDelete:
    """Test cascade delete for issues."""

    @pytest.mark.asyncio
    async def test_delete_issue_no_cascade(self, service):
        """Non-cascade delete only removes the issue, not children."""
        issue = await _create_issue(service)
        child = await _create_issue(service, parent_issue_id=issue.issue_id)
        work = await _create_work(service, issue_id=issue.issue_id)

        result = await service.delete_issue(issue.issue_id, cascade=False)

        assert result["deleted"] is True
        assert result["child_issue_count"] == 0
        assert result["work_item_count"] == 0
        # Child issue and work item still exist
        assert await service.get_issue(child.issue_id) is not None
        assert work.work_id in service._work_items

    @pytest.mark.asyncio
    async def test_delete_issue_cascade_removes_work_items(self, service):
        """Cascade delete removes work items linked to the issue."""
        issue = await _create_issue(service)
        w1 = await _create_work(service, issue_id=issue.issue_id)
        w2 = await _create_work(service, issue_id=issue.issue_id)
        # Unrelated work item should not be deleted
        w3 = await _create_work(service)

        result = await service.delete_issue(issue.issue_id, cascade=True)

        assert result["deleted"] is True
        assert result["work_item_count"] == 2
        assert w1.work_id not in service._work_items
        assert w2.work_id not in service._work_items
        assert w3.work_id in service._work_items

    @pytest.mark.asyncio
    async def test_delete_issue_cascade_removes_child_issues(self, service):
        """Cascade delete removes child issues recursively."""
        parent = await _create_issue(service)
        child = await _create_issue(service, parent_issue_id=parent.issue_id)
        grandchild = await _create_issue(service, parent_issue_id=child.issue_id)

        result = await service.delete_issue(parent.issue_id, cascade=True)

        assert result["deleted"] is True
        assert result["child_issue_count"] == 2  # child + grandchild
        assert await service.get_issue(child.issue_id) is None
        assert await service.get_issue(grandchild.issue_id) is None

    @pytest.mark.asyncio
    async def test_delete_issue_cascade_deep_hierarchy(self, service):
        """Cascade counts work items from all levels of the hierarchy."""
        parent = await _create_issue(service)
        child = await _create_issue(service, parent_issue_id=parent.issue_id)
        w_parent = await _create_work(service, issue_id=parent.issue_id)
        w_child = await _create_work(service, issue_id=child.issue_id)

        result = await service.delete_issue(parent.issue_id, cascade=True)

        assert result["deleted"] is True
        assert result["child_issue_count"] == 1
        assert result["work_item_count"] == 2  # parent's + child's work items
        assert w_parent.work_id not in service._work_items
        assert w_child.work_id not in service._work_items

    @pytest.mark.asyncio
    async def test_delete_nonexistent_issue(self, service):
        """Deleting a non-existent issue returns deleted=False."""
        result = await service.delete_issue("nonexistent", cascade=True)

        assert result["deleted"] is False
        assert result["child_issue_count"] == 0
        assert result["work_item_count"] == 0


# ============ Goal Cascade Delete ============


class TestGoalCascadeDelete:
    """Test cascade delete for goals."""

    @pytest.mark.asyncio
    async def test_delete_goal_hard_no_cascade(self, service):
        """Hard delete without cascade only removes the goal."""
        goal = await _create_goal(service)
        issue = await _create_issue(service, goal_id=goal.goal_id)

        result = await service.delete_goal(goal.goal_id, hard=True, cascade=False)

        assert result is not None
        assert result.deleted is True
        assert result.issue_count == 0
        assert result.work_item_count == 0
        # Issue still exists
        assert await service.get_issue(issue.issue_id) is not None

    @pytest.mark.asyncio
    async def test_delete_goal_soft_ignores_cascade(self, service):
        """Soft delete ignores cascade flag (cascade only applies with hard=True)."""
        goal = await _create_goal(service)
        issue = await _create_issue(service, goal_id=goal.goal_id)

        result = await service.delete_goal(goal.goal_id, hard=False, cascade=True)

        assert result is not None
        assert result.issue_count == 0
        assert result.work_item_count == 0
        # Issue still exists
        assert await service.get_issue(issue.issue_id) is not None

    @pytest.mark.asyncio
    async def test_delete_goal_hard_cascade_removes_issues(self, service):
        """Hard cascade delete removes all goal's issues and their work items."""
        goal = await _create_goal(service)
        issue1 = await _create_issue(service, goal_id=goal.goal_id)
        issue2 = await _create_issue(service, goal_id=goal.goal_id)
        w1 = await _create_work(service, issue_id=issue1.issue_id)

        result = await service.delete_goal(goal.goal_id, hard=True, cascade=True)

        assert result is not None
        assert result.deleted is True
        assert result.issue_count == 2
        assert result.work_item_count == 1
        assert await service.get_issue(issue1.issue_id) is None
        assert await service.get_issue(issue2.issue_id) is None
        assert w1.work_id not in service._work_items

    @pytest.mark.asyncio
    async def test_delete_goal_cascade_with_nested_issues(self, service):
        """Cascade properly handles issues with child issues."""
        goal = await _create_goal(service)
        parent_issue = await _create_issue(service, goal_id=goal.goal_id)
        child_issue = await _create_issue(
            service, parent_issue_id=parent_issue.issue_id
        )

        result = await service.delete_goal(goal.goal_id, hard=True, cascade=True)

        assert result is not None
        # parent_issue + child_issue
        assert result.issue_count == 2
        assert await service.get_issue(parent_issue.issue_id) is None
        assert await service.get_issue(child_issue.issue_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_goal(self, service):
        """Deleting a non-existent goal returns None."""
        result = await service.delete_goal("nonexistent", hard=True, cascade=True)
        assert result is None


# ============ Project Cascade Delete ============


class TestProjectCascadeDelete:
    """Test cascade delete for projects."""

    @pytest.mark.asyncio
    async def test_cascade_delete_project_empty(self, service):
        """Cascade delete on a project with no children returns zero counts."""
        result = await service.cascade_delete_project("proj-empty")

        assert result["goal_count"] == 0
        assert result["issue_count"] == 0
        assert result["work_item_count"] == 0
        assert result["comment_count"] == 0

    @pytest.mark.asyncio
    async def test_cascade_delete_project_removes_goals(self, service):
        """Cascade delete removes all goals belonging to the project."""
        goal1 = await _create_goal(service, project_id="proj-del")
        goal2 = await _create_goal(service, project_id="proj-del", title="Goal 2")
        # Goal in a different project should not be affected
        other_goal = await _create_goal(service, project_id="proj-other")

        result = await service.cascade_delete_project("proj-del")

        assert result["goal_count"] == 2
        assert await service.get_goal(goal1.goal_id) is None
        assert await service.get_goal(goal2.goal_id) is None
        # Other project's goal still exists
        assert await service.get_goal(other_goal.goal_id) is not None

    @pytest.mark.asyncio
    async def test_cascade_delete_project_full_hierarchy(self, service):
        """Cascade delete removes entire hierarchy: goals → issues → work items."""
        goal = await _create_goal(service, project_id="proj-full")
        issue = await _create_issue(service, goal_id=goal.goal_id, project_id="proj-full")
        work = await _create_work(service, issue_id=issue.issue_id, project_id="proj-full")

        result = await service.cascade_delete_project("proj-full")

        assert result["goal_count"] == 1
        assert result["issue_count"] == 1
        assert result["work_item_count"] == 1
        assert await service.get_issue(issue.issue_id) is None
        assert work.work_id not in service._work_items

    @pytest.mark.asyncio
    async def test_cascade_delete_project_orphaned_work_items(self, service):
        """Cascade delete also removes orphaned work items linked to the project."""
        # Work item not linked to any goal/issue, but belongs to the project
        orphan = await _create_work(service, project_id="proj-orphan")

        result = await service.cascade_delete_project("proj-orphan")

        assert result["work_item_count"] == 1
        assert orphan.work_id not in service._work_items

    @pytest.mark.asyncio
    async def test_cascade_delete_project_with_comments(self, service):
        """Cascade delete counts and removes goal comments."""
        goal = await _create_goal(service, project_id="proj-comments")

        # Mock the comment service to return comments
        mock_comment_list = AsyncMock()
        mock_comment_list.total = 2
        mock_comment_list.items = [
            type("Comment", (), {"comment_id": "c1"})(),
            type("Comment", (), {"comment_id": "c2"})(),
        ]
        service._comment_service.list_comments = AsyncMock(return_value=mock_comment_list)
        service._comment_service.delete_comment = AsyncMock()

        result = await service.cascade_delete_project("proj-comments")

        assert result["goal_count"] == 1
        assert result["comment_count"] >= 2
        assert service._comment_service.delete_comment.call_count == 2
