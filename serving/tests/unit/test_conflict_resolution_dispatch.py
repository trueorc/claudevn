"""Tests for conflict resolution dispatch logic.

Covers:
- Bug 1: send_merge_conflict includes task_id + repository in payload
- Bug 3: _auto_create_and_merge_pr skips approval for CONFLICT PRs
- Part 2: _dispatch_conflict_resolution_work sends work_assigned SSE
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from models.work_map import WorkItem, WorkStatus, WorkPriority


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_work_item():
    """A minimal work item that has completed."""
    return WorkItem(
        work_id="work_abc123",
        title="Implement feature",
        description="Test work item",
        work_type="feature",
        priority=WorkPriority.NORMAL,
        status=WorkStatus.COMPLETED,
        issue_id="issue_def456",
        project_id="proj-1",
        assigned_to="compute-001",
        context={},
    )


def _make_pr(status_value, conflicting_files=None, task_id="work_abc123"):
    """Build a mock PullRequest with specified status."""
    from git.pr_service import PRStatus
    pr = MagicMock()
    pr.status = PRStatus(status_value)
    pr.conflicting_files = conflicting_files or ["CLAUDE.md", "docs/guide.md"]
    pr.task_id = task_id
    pr.compute_id = "compute-001"
    return pr


# =============================================================================
# Bug 1: send_merge_conflict payload includes task_id and repository
# =============================================================================


class TestSendMergeConflictPayload:
    """Verify send_merge_conflict includes task_id and repository in event data."""

    @pytest.mark.asyncio
    async def test_send_merge_conflict_includes_task_id_and_repository(self):
        """task_id and repository fields are present in the queued event."""
        from services.sse_connection_manager import SSEConnectionManager

        manager = SSEConnectionManager()
        # Pre-register a connection so send_event queues successfully
        conn = MagicMock()
        conn.event_queue = AsyncMock()
        conn.event_queue.put = AsyncMock(return_value=None)
        manager._connections["compute-001"] = conn

        with patch.object(manager, "send_event", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await manager.send_merge_conflict(
                compute_id="compute-001",
                issue_id="issue-1",
                branch="feat/my-branch",
                conflicting_files=["CLAUDE.md"],
                main_head="abc123",
                task_id="work_abc123",
                repository="git@serving:repos/proj-1.git",
            )

        mock_send.assert_awaited_once()
        _event_type, data = mock_send.call_args[0][1], mock_send.call_args[0][2]
        assert data["task_id"] == "work_abc123"
        assert data["repository"] == "git@serving:repos/proj-1.git"
        assert data["issue_id"] == "issue-1"
        assert data["branch"] == "feat/my-branch"

    @pytest.mark.asyncio
    async def test_send_merge_conflict_task_id_defaults_to_none(self):
        """task_id and repository are None when not supplied (backwards compat)."""
        from services.sse_connection_manager import SSEConnectionManager

        manager = SSEConnectionManager()
        with patch.object(manager, "send_event", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await manager.send_merge_conflict(
                compute_id="compute-001",
                issue_id="issue-1",
                branch="feat/my-branch",
                conflicting_files=[],
                main_head="abc123",
            )

        _, data = mock_send.call_args[0][1], mock_send.call_args[0][2]
        assert data["task_id"] is None
        assert data["repository"] is None


# =============================================================================
# Bug 3: _auto_create_and_merge_pr does NOT approve CONFLICT PRs
# =============================================================================


class TestAutoCreateAndMergePr:
    """Verify _auto_create_and_merge_pr handles CONFLICT status correctly."""

    @pytest.mark.asyncio
    async def test_conflict_pr_skips_approval_dispatches_resolution(self, mock_work_item):
        """When create_pr returns CONFLICT status, skip approval and dispatch resolution."""
        from api.compute import _auto_create_and_merge_pr
        from git.pr_service import PRStatus

        conflict_pr = _make_pr("conflict")

        mock_pr_service = MagicMock()
        mock_pr_service.create_pr = AsyncMock(return_value=conflict_pr)
        mock_pr_service.update_status = AsyncMock()
        mock_pr_service.process_merge_queue = AsyncMock(return_value=[])

        with patch("api.compute._resolve_git_project_name", return_value="proj-1_repo-abc"), \
             patch("git.pr_service.PRService", return_value=mock_pr_service), \
             patch("api.compute._dispatch_conflict_resolution_work", new_callable=AsyncMock) as mock_dispatch:
            await _auto_create_and_merge_pr(mock_work_item, "feat/my-branch", "compute-001")

        # update_status must NOT be called (PR is in conflict)
        mock_pr_service.update_status.assert_not_called()
        # process_merge_queue must NOT be called either
        mock_pr_service.process_merge_queue.assert_not_called()
        # conflict resolution dispatch must be called
        mock_dispatch.assert_awaited_once_with(
            mock_work_item, "feat/my-branch", "compute-001", conflict_pr
        )

    @pytest.mark.asyncio
    async def test_clean_pr_gets_approved_and_merged(self, mock_work_item):
        """When create_pr returns PENDING status, proceed with approval and merge."""
        from api.compute import _auto_create_and_merge_pr

        clean_pr = _make_pr("pending", conflicting_files=[])

        mock_pr_service = MagicMock()
        mock_pr_service.create_pr = AsyncMock(return_value=clean_pr)
        mock_pr_service.update_status = AsyncMock()
        mock_pr_service.process_merge_queue = AsyncMock(return_value=[{"success": True, "branch": "feat/my-branch"}])
        mock_pr_service._get_redis = AsyncMock(
            return_value=AsyncMock(add_to_merge_queue=AsyncMock())
        )

        with patch("api.compute._resolve_git_project_name", return_value="proj-1_repo-abc"), \
             patch("git.pr_service.PRService", return_value=mock_pr_service), \
             patch("api.compute._dispatch_conflict_resolution_work", new_callable=AsyncMock) as mock_dispatch:
            await _auto_create_and_merge_pr(mock_work_item, "feat/my-branch", "compute-001")

        mock_pr_service.update_status.assert_awaited_once()
        mock_pr_service.process_merge_queue.assert_awaited_once()
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_merge_conflict_race_dispatches_resolution(self, mock_work_item):
        """When merge queue reports a conflict (race condition), dispatch resolution."""
        from api.compute import _auto_create_and_merge_pr

        clean_pr = _make_pr("pending", conflicting_files=[])

        mock_pr_service = MagicMock()
        mock_pr_service.create_pr = AsyncMock(return_value=clean_pr)
        mock_pr_service.update_status = AsyncMock()
        mock_pr_service.process_merge_queue = AsyncMock(
            return_value=[{"success": False, "reason": "conflict", "branch": "feat/my-branch"}]
        )
        mock_pr_service._get_redis = AsyncMock(
            return_value=AsyncMock(add_to_merge_queue=AsyncMock())
        )
        # get_pr is needed for conflict dispatch lookup
        conflict_pr_after_merge = _make_pr("conflict", conflicting_files=["file.py"])
        mock_pr_service.get_pr = AsyncMock(return_value=conflict_pr_after_merge)

        with patch("api.compute._resolve_git_project_name", return_value="proj-1_repo-abc"), \
             patch("git.pr_service.PRService", return_value=mock_pr_service), \
             patch("api.compute._dispatch_conflict_resolution_work", new_callable=AsyncMock) as mock_dispatch:
            await _auto_create_and_merge_pr(mock_work_item, "feat/my-branch", "compute-001")

        # Should still have approved, but then detected conflict during merge
        mock_pr_service.update_status.assert_awaited_once()
        mock_dispatch.assert_awaited_once()


# =============================================================================
# Part 2: _dispatch_conflict_resolution_work sends correct work_assigned event
# =============================================================================


class TestDispatchConflictResolutionWork:
    """Verify _dispatch_conflict_resolution_work sends work_assigned SSE correctly."""

    @pytest.mark.asyncio
    async def test_dispatches_work_assigned_with_correct_fields(self, mock_work_item):
        """work_assigned event has is_conflict_resolution=True and correct branch."""
        from api.compute import _dispatch_conflict_resolution_work

        pr = _make_pr("conflict", conflicting_files=["CLAUDE.md"])
        mock_sse = MagicMock()
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_repo_url.return_value = "git@serving:repos/proj-1.git"
        mock_repo_mgr.get_branch_head.return_value = "deadbeef"

        with patch("api.compute._resolve_git_project_name", return_value="proj-1_repo-abc"), \
             patch("api.compute.get_sse_connection_manager", return_value=mock_sse), \
             patch("mcp.auth.generate_api_key", return_value="troc_testkey"), \
             patch("mcp.auth.register_compute_key", new_callable=AsyncMock), \
             patch("git.repo_manager.RepoManager", return_value=mock_repo_mgr):
            await _dispatch_conflict_resolution_work(
                mock_work_item, "feat/my-branch", "compute-001", pr
            )

        mock_sse.send_work_assigned.assert_awaited_once()
        kwargs = mock_sse.send_work_assigned.call_args.kwargs
        assert kwargs["compute_id"] == "compute-001"
        assert kwargs["branch_name"] == "feat/my-branch"
        assert kwargs["context"]["is_conflict_resolution"] is True
        assert kwargs["context"]["original_branch"] == "feat/my-branch"
        assert "CLAUDE.md" in kwargs["context"]["conflicting_files"]
        assert kwargs["context"]["repository"] == "git@serving:repos/proj-1.git"
        assert kwargs["mcp_config"]["api_key"] == "troc_testkey"

    @pytest.mark.asyncio
    async def test_task_id_has_conflict_prefix(self, mock_work_item):
        """The dispatched task_id is prefixed with 'conflict-' for easy identification."""
        from api.compute import _dispatch_conflict_resolution_work

        pr = _make_pr("conflict")
        mock_sse = MagicMock()
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_repo_url.return_value = "git@serving:repos/proj-1.git"
        mock_repo_mgr.get_branch_head.return_value = ""

        with patch("api.compute._resolve_git_project_name", return_value="proj-1_repo-abc"), \
             patch("api.compute.get_sse_connection_manager", return_value=mock_sse), \
             patch("mcp.auth.generate_api_key", return_value="troc_testkey"), \
             patch("mcp.auth.register_compute_key", new_callable=AsyncMock), \
             patch("git.repo_manager.RepoManager", return_value=mock_repo_mgr):
            await _dispatch_conflict_resolution_work(
                mock_work_item, "feat/my-branch", "compute-001", pr
            )

        kwargs = mock_sse.send_work_assigned.call_args.kwargs
        assert kwargs["task_id"].startswith("conflict-work_abc123-")

    @pytest.mark.asyncio
    async def test_dispatch_error_is_swallowed(self, mock_work_item):
        """Errors in dispatch are caught and logged, not re-raised."""
        from api.compute import _dispatch_conflict_resolution_work

        pr = _make_pr("conflict")

        with patch("api.compute._resolve_git_project_name", side_effect=RuntimeError("boom")):
            # Should not raise
            await _dispatch_conflict_resolution_work(
                mock_work_item, "feat/my-branch", "compute-001", pr
            )


