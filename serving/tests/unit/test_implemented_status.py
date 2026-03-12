"""Tests for the IMPLEMENTED intermediate status (#267).

Verifies the two-phase completion flow:
  Phase 1: complete_work → IMPLEMENTED (code done, pending merge)
  Phase 2: finalize_work → COMPLETED + DONE (branch merged to main)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.work_map import (
    WorkItem, WorkStatus, WorkPriority, Issue, IssueStatus,
    IssuePriority, IssueResult
)
from services.assignment_service import AssignmentService
from services.issue_ops_service import IssueOpsService
from services.work_map_service import WorkMapService


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis._redis = AsyncMock()
    redis._redis.srem = AsyncMock()
    redis._redis.sadd = AsyncMock()
    redis._redis.delete = AsyncMock()
    redis._redis.set = AsyncMock()
    redis._redis.get = AsyncMock(return_value=None)
    return redis


@pytest.fixture
def assignment_service(mock_redis):
    service = AssignmentService()
    service._redis = mock_redis
    return service


@pytest.fixture
def issue_ops_service(mock_redis):
    service = IssueOpsService()
    service._redis = mock_redis
    return service


def _make_work(work_id, status=WorkStatus.IN_PROGRESS, issue_id=None):
    return WorkItem(
        work_id=work_id,
        title=f"Work {work_id}",
        description="Test work item",
        status=status,
        priority=WorkPriority.NORMAL,
        assigned_to="compute-001",
        branch_name=f"feat/{work_id}",
        issue_id=issue_id,
        project_id="test-project",
    )


def _make_issue(issue_id, status=IssueStatus.IN_PROGRESS, goal_id=None):
    return Issue(
        issue_id=issue_id,
        title=f"Issue {issue_id}",
        description="Test issue",
        status=status,
        priority=IssuePriority.P1,
        goal_id=goal_id,
    )


# =============================================================================
# WorkStatus.IMPLEMENTED Tests
# =============================================================================


class TestWorkStatusImplemented:
    """Test that complete_work sets IMPLEMENTED, not COMPLETED."""

    @pytest.mark.asyncio
    async def test_complete_work_sets_implemented(self, assignment_service):
        work = _make_work("w1")
        assignment_service.set_work_items_reference({"w1": work})

        result = await assignment_service.complete_work(
            "w1", {"summary": "done"}, "compute-001"
        )

        assert result.status == WorkStatus.IMPLEMENTED

    @pytest.mark.asyncio
    async def test_implemented_does_not_set_completed_at(self, assignment_service):
        work = _make_work("w1")
        assignment_service.set_work_items_reference({"w1": work})

        result = await assignment_service.complete_work(
            "w1", {"summary": "done"}, "compute-001"
        )

        assert result.completed_at is None

    @pytest.mark.asyncio
    async def test_implemented_to_completed_transition(self, assignment_service):
        work = _make_work("w1", status=WorkStatus.IMPLEMENTED)
        assignment_service.set_work_items_reference({"w1": work})

        result = await assignment_service.update_status("w1", WorkStatus.COMPLETED)

        assert result.status == WorkStatus.COMPLETED
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_implemented_to_in_progress_transition(self, assignment_service):
        """IMPLEMENTED can go back to IN_PROGRESS (e.g., merge conflict requires rework)."""
        work = _make_work("w1", status=WorkStatus.IMPLEMENTED)
        assignment_service.set_work_items_reference({"w1": work})

        result = await assignment_service.update_status("w1", WorkStatus.IN_PROGRESS)

        assert result.status == WorkStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_implemented_is_idempotent(self, assignment_service):
        work = _make_work("w1", status=WorkStatus.IMPLEMENTED)
        assignment_service.set_work_items_reference({"w1": work})

        result = await assignment_service.update_status("w1", WorkStatus.IMPLEMENTED)

        assert result.status == WorkStatus.IMPLEMENTED

    @pytest.mark.asyncio
    async def test_implemented_cannot_go_to_failed(self, assignment_service):
        """IMPLEMENTED cannot transition to FAILED (only IN_PROGRESS can)."""
        work = _make_work("w1", status=WorkStatus.IMPLEMENTED)
        assignment_service.set_work_items_reference({"w1": work})

        result = await assignment_service.update_status("w1", WorkStatus.FAILED)

        assert result is None  # invalid transition


# =============================================================================
# IssueStatus.IMPLEMENTED Tests
# =============================================================================


class TestIssueStatusImplemented:
    """Test that complete_issue sets IMPLEMENTED, not DONE."""

    @pytest.mark.asyncio
    async def test_complete_issue_sets_implemented(self, issue_ops_service):
        issue = _make_issue("i1")
        issue_ops_service._issues = {"i1": issue}

        result = await issue_ops_service.complete_issue(
            "i1", IssueResult(summary="done", branch="feat/i1"), "compute-001"
        )

        assert result.status == IssueStatus.IMPLEMENTED

    @pytest.mark.asyncio
    async def test_finalize_issue_sets_done(self, issue_ops_service):
        issue = _make_issue("i1", status=IssueStatus.IMPLEMENTED)
        issue.result = IssueResult(summary="done", branch="feat/i1")
        issue_ops_service._issues = {"i1": issue}

        result = await issue_ops_service.finalize_issue("i1", "compute-001")

        assert result.status == IssueStatus.DONE
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_finalize_requires_implemented_status(self, issue_ops_service):
        issue = _make_issue("i1", status=IssueStatus.IN_PROGRESS)
        issue_ops_service._issues = {"i1": issue}

        result = await issue_ops_service.finalize_issue("i1")

        assert result is None

    @pytest.mark.asyncio
    async def test_valid_transitions_include_implemented(self, issue_ops_service):
        transitions = issue_ops_service.VALID_TRANSITIONS

        # IN_PROGRESS → IMPLEMENTED
        assert IssueStatus.IMPLEMENTED in transitions[IssueStatus.IN_PROGRESS]
        # IMPLEMENTED → DONE
        assert IssueStatus.DONE in transitions[IssueStatus.IMPLEMENTED]
        # IMPLEMENTED → IN_PROGRESS (rework)
        assert IssueStatus.IN_PROGRESS in transitions[IssueStatus.IMPLEMENTED]
        # IN_PROGRESS should NOT go directly to DONE
        assert IssueStatus.DONE not in transitions[IssueStatus.IN_PROGRESS]

    @pytest.mark.asyncio
    async def test_cascade_only_triggers_on_done(self, issue_ops_service):
        """Dependency cascade should NOT trigger on IMPLEMENTED."""
        dep = _make_issue("dep1", status=IssueStatus.IN_PROGRESS)
        blocker = _make_issue("blocker1", status=IssueStatus.IN_PROGRESS)
        dep.depends_on = ["blocker1"]
        blocker.blocks = ["dep1"]
        issue_ops_service._issues = {"dep1": dep, "blocker1": blocker}

        # complete_issue → IMPLEMENTED: should NOT unblock dep1
        await issue_ops_service.complete_issue(
            "blocker1", IssueResult(summary="done", branch="b")
        )
        assert dep.status == IssueStatus.IN_PROGRESS  # not yet READY

        # finalize_issue → DONE: should unblock dep1
        # (need to set up for cascade by making dep1 BACKLOG)
        dep.status = IssueStatus.BACKLOG
        await issue_ops_service.finalize_issue("blocker1", trigger_cascade=True)
        assert dep.status == IssueStatus.READY


# =============================================================================
# Two-Phase Completion Flow Tests
# =============================================================================


class TestTwoPhaseCompletion:
    """Test the full complete_work → finalize_work flow."""

    @pytest.fixture
    def work_map_service(self, mock_redis):
        service = WorkMapService.__new__(WorkMapService)
        service._assignment_service = AssignmentService()
        service._assignment_service._redis = mock_redis
        service._issue_service = IssueOpsService()
        service._issue_service._redis = mock_redis
        service._redis = mock_redis
        # Share the same work_items dict between service and assignment_service
        work_items = {}
        service._work_items = work_items
        service._assignment_service._work_items = work_items
        return service

    @pytest.mark.asyncio
    async def test_complete_then_finalize(self, work_map_service):
        issue = _make_issue("i1")
        work = _make_work("w1", issue_id="i1")
        work_map_service._work_items["w1"] = work
        work_map_service._issue_service._issues = {"i1": issue}

        # Phase 1: complete_work
        result = await work_map_service.complete_work(
            "w1", {"summary": "done"}, "compute-001"
        )
        assert result.status == WorkStatus.IMPLEMENTED
        assert issue.status == IssueStatus.IMPLEMENTED

        # Phase 2: finalize_work (after merge)
        finalized = await work_map_service.finalize_work("w1")
        assert finalized.status == WorkStatus.COMPLETED
        assert issue.status == IssueStatus.DONE

    @pytest.mark.asyncio
    async def test_finalize_rejects_non_implemented(self, work_map_service):
        work = _make_work("w1", status=WorkStatus.IN_PROGRESS)
        work_map_service._work_items["w1"] = work

        result = await work_map_service.finalize_work("w1")
        assert result is None

    @pytest.mark.asyncio
    async def test_finalize_triggers_cascade(self, work_map_service):
        """finalize_work should trigger dependency cascade."""
        blocker_issue = _make_issue("blocker", status=IssueStatus.IN_PROGRESS)
        dependent_issue = _make_issue("dep", status=IssueStatus.BACKLOG)
        dependent_issue.depends_on = ["blocker"]
        blocker_issue.blocks = ["dep"]

        blocker_work = _make_work("w1", issue_id="blocker")

        work_map_service._work_items["w1"] = blocker_work
        work_map_service._issue_service._issues = {
            "blocker": blocker_issue,
            "dep": dependent_issue,
        }

        # Phase 1
        await work_map_service.complete_work("w1", {"summary": "done"}, "compute-001")
        assert dependent_issue.status == IssueStatus.BACKLOG  # NOT unblocked yet

        # Phase 2
        await work_map_service.finalize_work("w1")
        assert dependent_issue.status == IssueStatus.READY  # NOW unblocked


# =============================================================================
# MCP Status Mapping Tests
# =============================================================================


class TestMCPStatusMapping:
    def test_task_completed_maps_to_implemented(self):
        from mcp.models import TaskStatus
        from mcp.tools.progress import STATUS_MAP

        assert STATUS_MAP[TaskStatus.COMPLETED] == WorkStatus.IMPLEMENTED

    def test_task_implemented_maps_to_implemented(self):
        from mcp.models import TaskStatus
        from mcp.tools.progress import STATUS_MAP

        assert STATUS_MAP[TaskStatus.IMPLEMENTED] == WorkStatus.IMPLEMENTED
