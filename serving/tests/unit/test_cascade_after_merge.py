"""Tests for merge-before-cascade fix (#832).

Verifies that dependency cascade is deferred until after PR merge,
so dependent work items clone main with the merged code.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.work_map import (
    WorkItem, WorkStatus, WorkPriority,
    Issue, IssueStatus, IssueResult, IssueType, IssuePriority,
)
from services.work_map_service import WorkMapService


@pytest.fixture
def service():
    """Create WorkMapService without Redis for in-memory testing."""
    return WorkMapService(redis_client=None)


@pytest.fixture
def sample_work(service):
    """Create a completed work item linked to an issue."""
    work = WorkItem(
        work_id="work-1",
        title="Implement feature X",
        description="Build feature X",
        work_type="task",
        priority=WorkPriority.NORMAL,
        status=WorkStatus.IN_PROGRESS,
        issue_id="issue-1",
        assigned_to="compute-1",
        project_id="proj-1",
        branch_name="feat/x/compute-1",
    )
    service._work_items[work.work_id] = work
    return work


@pytest.fixture
def parent_issue(service):
    """Create a parent issue in IN_PROGRESS state."""
    issue = Issue(
        issue_id="issue-1",
        title="Feature X",
        description="Implement feature X",
        issue_type=IssueType.FEATURE,
        priority=IssuePriority.P1,
        status=IssueStatus.IN_PROGRESS,
    )
    service._issue_service._issues[issue.issue_id] = issue
    return issue


@pytest.fixture
def dependent_issue(service, parent_issue):
    """Create an issue that depends on parent_issue."""
    dep = Issue(
        issue_id="issue-2",
        title="Feature Y (depends on X)",
        description="Depends on feature X",
        issue_type=IssueType.FEATURE,
        priority=IssuePriority.P1,
        status=IssueStatus.BACKLOG,
        depends_on=["issue-1"],
    )
    service._issue_service._issues[dep.issue_id] = dep
    # Wire up the blocks relationship
    parent_issue.blocks.append("issue-2")
    return dep


class TestCompleteWorkCascadeFlag:
    """Test that trigger_cascade=False suppresses dependency cascade."""

    @pytest.mark.asyncio
    async def test_complete_work_default_cascades(
        self, service, sample_work, parent_issue, dependent_issue
    ):
        """Default complete_work triggers cascade — dependent moves to READY."""
        work = await service.complete_work(
            work_id="work-1",
            result={"summary": "Done"},
            compute_id="compute-1",
        )
        assert work is not None
        assert work.status == WorkStatus.COMPLETED
        assert parent_issue.status == IssueStatus.DONE
        assert dependent_issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_complete_work_no_cascade(
        self, service, sample_work, parent_issue, dependent_issue
    ):
        """complete_work(trigger_cascade=False) does NOT unblock dependents."""
        work = await service.complete_work(
            work_id="work-1",
            result={"summary": "Done"},
            compute_id="compute-1",
            trigger_cascade=False,
        )
        assert work is not None
        assert work.status == WorkStatus.COMPLETED
        assert parent_issue.status == IssueStatus.DONE
        # Dependent should still be BACKLOG — cascade was suppressed
        assert dependent_issue.status == IssueStatus.BACKLOG


class TestCascadeDependents:
    """Test the explicit cascade_dependents() method."""

    @pytest.mark.asyncio
    async def test_cascade_after_complete(
        self, service, sample_work, parent_issue, dependent_issue
    ):
        """cascade_dependents() unblocks dependents when parent is DONE."""
        # Complete without cascade
        await service.complete_work(
            work_id="work-1",
            result={"summary": "Done"},
            compute_id="compute-1",
            trigger_cascade=False,
        )
        assert dependent_issue.status == IssueStatus.BACKLOG

        # Now trigger cascade explicitly
        unblocked = await service.cascade_dependents("work-1")
        assert "issue-2" in unblocked
        assert dependent_issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_cascade_idempotent(
        self, service, sample_work, parent_issue, dependent_issue
    ):
        """Calling cascade_dependents() twice is safe (idempotent)."""
        await service.complete_work(
            work_id="work-1",
            result={"summary": "Done"},
            compute_id="compute-1",
            trigger_cascade=False,
        )

        unblocked1 = await service.cascade_dependents("work-1")
        assert "issue-2" in unblocked1
        assert dependent_issue.status == IssueStatus.READY

        # Second call — already READY, nothing new to unblock
        unblocked2 = await service.cascade_dependents("work-1")
        assert unblocked2 == []

    @pytest.mark.asyncio
    async def test_cascade_noop_when_parent_not_done(self, service, sample_work, parent_issue):
        """cascade_dependents() is a no-op when parent issue isn't DONE."""
        # Work is still IN_PROGRESS, parent is IN_PROGRESS
        unblocked = await service.cascade_dependents("work-1")
        assert unblocked == []

    @pytest.mark.asyncio
    async def test_cascade_noop_for_unknown_work(self, service):
        """cascade_dependents() returns empty for unknown work IDs."""
        unblocked = await service.cascade_dependents("nonexistent")
        assert unblocked == []

    @pytest.mark.asyncio
    async def test_cascade_noop_for_work_without_issue(self, service):
        """cascade_dependents() returns empty for work without parent issue."""
        work = WorkItem(
            work_id="work-orphan",
            title="Orphan work",
            description="No parent issue",
            work_type="task",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.COMPLETED,
            project_id="proj-1",
        )
        service._work_items[work.work_id] = work
        unblocked = await service.cascade_dependents("work-orphan")
        assert unblocked == []


class TestHandleWorkStatusUpdateOrder:
    """Test that _handle_work_status_update merges PR before cascade."""

    @pytest.mark.asyncio
    async def test_merge_before_cascade_order(self):
        """Verify the order: complete_work → merge PR → cascade_dependents."""
        call_order = []

        mock_work = MagicMock(
            work_id="work-1",
            status=WorkStatus.IN_PROGRESS,
            branch_name="feat/x/compute-1",
            project_id="proj-1",
            tags=[],
        )
        mock_work_map = MagicMock()
        mock_work_map.get_work = AsyncMock(return_value=mock_work)
        mock_work_map.update_status = AsyncMock()
        mock_work_map.complete_work = AsyncMock(
            side_effect=lambda **kw: call_order.append("complete_work")
        )
        mock_work_map.cascade_dependents = AsyncMock(
            side_effect=lambda *a: call_order.append("cascade_dependents")
        )

        mock_auto_merge = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("auto_merge")
        )

        # Mock RepoManager for branch verification
        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_branches = MagicMock(return_value=["feat/x/compute-1", "main"])

        with patch("services.work_map_service.get_work_map_service", return_value=mock_work_map), \
             patch("api.compute._auto_create_and_merge_pr", mock_auto_merge), \
             patch("api.compute._resolve_git_project_name", return_value="proj-1"), \
             patch("git.repo_manager.RepoManager", return_value=mock_repo_mgr):

            from api.compute import _handle_work_status_update
            from models.compute import ComputeEventRequest, ComputeEventType

            event = ComputeEventRequest(
                event=ComputeEventType.CLAUDE_CODE_COMPLETED,
                compute_id="compute-1",
                task_id="work-1",
                exit_code=0,
                branch_name="feat/x/compute-1",
            )

            await _handle_work_status_update(event)

        assert call_order == ["complete_work", "auto_merge", "cascade_dependents"]
