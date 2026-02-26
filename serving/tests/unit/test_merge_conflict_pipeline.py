"""Tests for merge conflict resolution pipeline improvements (#48).

Covers:
- (a) process_merge_queue skips conflicts and continues
- (b) Queue re-processing after each merge (inherent in skip-and-continue)
- (c) Post-resolution queue trigger in _auto_create_and_merge_pr
- (d) No dual SSE notification from merge()
- (e) Conflict resolution dispatch fallback to idle compute
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from git.pr_service import PRService, PRStatus, PullRequest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    redis = AsyncMock()
    redis.get_branch_status = AsyncMock(return_value={
        "status": "approved",
        "compute_id": "compute-001",
        "task_id": "task-100",
        "title": "Test PR",
        "base_branch": "main",
        "head_commit": "abc123",
    })
    redis.set_branch_status = AsyncMock()
    redis.add_to_pr_queue = AsyncMock(return_value=1)
    redis.remove_from_pr_queue = AsyncMock()
    redis.pop_merge_queue = AsyncMock()
    redis.add_to_merge_queue = AsyncMock()
    redis.publish_git_event = AsyncMock()
    redis.untrack_compute_branch = AsyncMock()
    return redis


@pytest.fixture
def mock_repo_manager():
    """Create mock RepoManager."""
    manager = MagicMock()
    manager.get_branch_head = MagicMock(return_value="main123")
    manager.get_default_branch = MagicMock(return_value="main")
    manager.get_repo_url = MagicMock(return_value="http://serving:8002/git/test-project.git")
    return manager


@pytest.fixture
def mock_sse_manager():
    """Create mock SSE manager."""
    sse = AsyncMock()
    sse.send_merge_conflict = AsyncMock(return_value=True)
    sse.send_work_completed = AsyncMock(return_value=True)
    sse.send_work_assigned = AsyncMock(return_value=True)
    sse.get_connection = MagicMock(return_value=None)
    sse.get_idle_connections = MagicMock(return_value=[])
    return sse


@pytest.fixture
def pr_service(mock_redis, mock_repo_manager, mock_sse_manager):
    """Create PRService with mocked dependencies."""
    with patch("git.pr_service.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/home/git/repos"
        service = PRService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager,
            sse_manager=mock_sse_manager,
        )
    return service


# =============================================================================
# (a) process_merge_queue: skip-and-continue
# =============================================================================


class TestProcessMergeQueueSkipAndContinue:
    """Test that process_merge_queue skips conflicts and continues."""

    @pytest.mark.asyncio
    async def test_continues_past_conflict_to_merge_clean_prs(
        self, pr_service, mock_redis
    ):
        """When a PR conflicts, the queue should continue processing remaining PRs."""
        # Queue has 3 branches: first conflicts, second and third are clean
        branches = ["feature/conflict", "feature/clean-1", "feature/clean-2", None]
        mock_redis.pop_merge_queue = AsyncMock(side_effect=branches)

        merge_results = [
            {"success": False, "reason": "conflict", "branch": "feature/conflict"},
            {"success": True, "merged_commit": "aaa", "branch": "feature/clean-1"},
            {"success": True, "merged_commit": "bbb", "branch": "feature/clean-2"},
        ]

        with patch.object(pr_service, "merge", AsyncMock(side_effect=merge_results)):
            results = await pr_service.process_merge_queue("test-project")

        # All three were processed
        assert len(results) == 3
        assert results[0]["success"] is False
        assert results[1]["success"] is True
        assert results[2]["success"] is True

    @pytest.mark.asyncio
    async def test_continues_past_valueerror(self, pr_service, mock_redis):
        """ValueError (not approved, etc.) should skip, not break."""
        branches = ["feature/bad", "feature/good", None]
        mock_redis.pop_merge_queue = AsyncMock(side_effect=branches)

        async def mock_merge(project, branch):
            if branch == "feature/bad":
                raise ValueError("PR not approved")
            return {"success": True, "merged_commit": "abc", "branch": branch}

        with patch.object(pr_service, "merge", AsyncMock(side_effect=mock_merge)):
            results = await pr_service.process_merge_queue("test-project")

        assert len(results) == 2
        assert results[0]["success"] is False
        assert "not approved" in results[0]["error"]
        assert results[1]["success"] is True

    @pytest.mark.asyncio
    async def test_does_not_readd_failed_prs_to_queue(self, pr_service, mock_redis):
        """Failed PRs should NOT be re-added to the merge queue."""
        branches = ["feature/bad", None]
        mock_redis.pop_merge_queue = AsyncMock(side_effect=branches)

        with patch.object(
            pr_service, "merge", AsyncMock(side_effect=ValueError("PR not found"))
        ):
            await pr_service.process_merge_queue("test-project")

        mock_redis.add_to_merge_queue.assert_not_called()


# =============================================================================
# (d) No dual SSE notification from merge()
# =============================================================================


class TestNoDualNotification:
    """Test that merge() does NOT send direct SSE merge_conflict events."""

    @pytest.mark.asyncio
    async def test_merge_conflict_does_not_send_sse_merge_conflict(
        self, pr_service, mock_redis, mock_repo_manager, mock_sse_manager
    ):
        """merge() should not call send_merge_conflict — only work_assigned via caller."""
        mock_repo_manager.get_branch_head.return_value = "main123"

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            if "merge" in cmd and "--no-ff" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT (content): Merge conflict in src/api.py\n"

            if "rev-parse" in cmd:
                result.stdout = "abc123\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service.merge(
                            "test-project", "feature/test"
                        )

        assert result["success"] is False
        assert result["reason"] == "conflict"
        # SSE merge_conflict should NOT be called (deduplicated)
        mock_sse_manager.send_merge_conflict.assert_not_called()


# =============================================================================
# (c) Post-resolution queue trigger
# =============================================================================


class TestPostResolutionQueueTrigger:
    """Test _auto_create_and_merge_pr handles post-conflict-resolution re-entry."""

    @pytest.mark.asyncio
    async def test_reentry_after_conflict_resolution(self):
        """After conflict resolution, re-approves PR and re-processes queue."""
        from api.compute import _auto_create_and_merge_pr

        mock_work = MagicMock()
        mock_work.work_id = "work-1"
        mock_work.project_id = "proj-1"
        mock_work.title = "Test work"

        existing_pr = MagicMock()
        existing_pr.status = PRStatus.CONFLICT
        existing_pr.compute_id = "compute-001"

        mock_pr_service = AsyncMock()
        mock_pr_service.create_pr = AsyncMock(
            side_effect=ValueError("PR already exists")
        )
        mock_pr_service.get_pr = AsyncMock(return_value=existing_pr)
        mock_pr_service.dry_run_merge = AsyncMock(
            return_value={"can_merge": True}
        )
        mock_pr_service.update_status = AsyncMock()
        mock_pr_service.process_merge_queue = AsyncMock(return_value=[])
        mock_pr_service._get_redis = AsyncMock(
            return_value=AsyncMock(add_to_merge_queue=AsyncMock())
        )

        with patch("git.pr_service.PRService", return_value=mock_pr_service):
            with patch("git.pr_service.PRService", return_value=mock_pr_service):
                with patch("api.compute._resolve_git_project_name", return_value="proj-1"):
                    await _auto_create_and_merge_pr(mock_work, "feature/test", "compute-001")

        # PR should be re-approved
        mock_pr_service.update_status.assert_called_once_with(
            project="proj-1",
            branch="feature/test",
            status=PRStatus.APPROVED,
            reviewed_by="auto-approved",
        )
        # Merge queue should be re-processed
        mock_pr_service.process_merge_queue.assert_called_once_with("proj-1")

    @pytest.mark.asyncio
    async def test_reentry_still_conflicting_dispatches_resolution(self):
        """If PR is still conflicting after resolution attempt, re-dispatch."""
        from api.compute import _auto_create_and_merge_pr

        mock_work = MagicMock()
        mock_work.work_id = "work-1"
        mock_work.project_id = "proj-1"
        mock_work.title = "Test work"

        existing_pr = MagicMock()
        existing_pr.status = PRStatus.CONFLICT
        existing_pr.compute_id = "compute-001"
        existing_pr.conflicting_files = ["src/api.py"]

        mock_pr_service = AsyncMock()
        mock_pr_service.create_pr = AsyncMock(
            side_effect=ValueError("PR already exists")
        )
        mock_pr_service.get_pr = AsyncMock(return_value=existing_pr)
        mock_pr_service.dry_run_merge = AsyncMock(
            return_value={"can_merge": False, "conflicting_files": ["src/api.py"]}
        )

        with patch("git.pr_service.PRService", return_value=mock_pr_service):
            with patch("api.compute._resolve_git_project_name", return_value="proj-1"):
                with patch(
                    "api.compute._dispatch_conflict_resolution_work", new_callable=AsyncMock
                ) as mock_dispatch:
                    await _auto_create_and_merge_pr(
                        mock_work, "feature/test", "compute-001"
                    )

        mock_dispatch.assert_called_once()


# =============================================================================
# (e) Conflict resolution dispatch: fallback to idle compute
# =============================================================================


class TestConflictResolutionDispatchFallback:
    """Test _dispatch_conflict_resolution_work tries original, falls back to idle."""

    @pytest.mark.asyncio
    async def test_dispatches_to_original_compute_when_connected(self):
        """Uses original compute when it's still connected."""
        from api.compute import _dispatch_conflict_resolution_work

        mock_work = MagicMock()
        mock_work.work_id = "work-1"
        mock_work.project_id = "proj-1"

        mock_pr = MagicMock()
        mock_pr.conflicting_files = ["file.py"]

        mock_conn = MagicMock()
        mock_conn.compute_id = "compute-001"

        mock_sse = MagicMock()
        mock_sse.get_connection = MagicMock(return_value=mock_conn)
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_repo_url.return_value = "http://repo"
        mock_repo_mgr.get_branch_head.return_value = "main123"

        with patch("api.compute._resolve_git_project_name", return_value="proj-1"):
            with patch("api.compute.get_sse_connection_manager", return_value=mock_sse):
                with patch("git.repo_manager.RepoManager", return_value=mock_repo_mgr):
                    with patch("mcp.auth.generate_api_key", return_value="key-1"):
                        with patch("mcp.auth.register_compute_key", new_callable=AsyncMock):
                            await _dispatch_conflict_resolution_work(
                                mock_work, "feature/test", "compute-001", mock_pr
                            )

        # Should send to the original compute
        call_kwargs = mock_sse.send_work_assigned.call_args[1]
        assert call_kwargs["compute_id"] == "compute-001"

    @pytest.mark.asyncio
    async def test_falls_back_to_idle_compute_when_original_disconnected(self):
        """Falls back to any idle compute when original is disconnected."""
        from api.compute import _dispatch_conflict_resolution_work

        mock_work = MagicMock()
        mock_work.work_id = "work-1"
        mock_work.project_id = "proj-1"

        mock_pr = MagicMock()
        mock_pr.conflicting_files = ["file.py"]

        idle_conn = MagicMock()
        idle_conn.compute_id = "compute-002"

        mock_sse = MagicMock()
        mock_sse.get_connection = MagicMock(return_value=None)  # original disconnected
        mock_sse.get_idle_connections = MagicMock(return_value=[idle_conn])
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        mock_repo_mgr = MagicMock()
        mock_repo_mgr.get_repo_url.return_value = "http://repo"
        mock_repo_mgr.get_branch_head.return_value = "main123"

        with patch("api.compute._resolve_git_project_name", return_value="proj-1"):
            with patch("api.compute.get_sse_connection_manager", return_value=mock_sse):
                with patch("git.repo_manager.RepoManager", return_value=mock_repo_mgr):
                    with patch("mcp.auth.generate_api_key", return_value="key-1"):
                        with patch("mcp.auth.register_compute_key", new_callable=AsyncMock):
                            await _dispatch_conflict_resolution_work(
                                mock_work, "feature/test", "compute-001", mock_pr
                            )

        # Should send to idle compute, not the original
        call_kwargs = mock_sse.send_work_assigned.call_args[1]
        assert call_kwargs["compute_id"] == "compute-002"

    @pytest.mark.asyncio
    async def test_no_dispatch_when_no_compute_available(self):
        """Logs warning and returns when no compute is available."""
        from api.compute import _dispatch_conflict_resolution_work

        mock_work = MagicMock()
        mock_work.work_id = "work-1"
        mock_work.project_id = "proj-1"

        mock_pr = MagicMock()
        mock_pr.conflicting_files = ["file.py"]

        mock_sse = MagicMock()
        mock_sse.get_connection = MagicMock(return_value=None)
        mock_sse.get_idle_connections = MagicMock(return_value=[])
        mock_sse.send_work_assigned = AsyncMock(return_value=True)

        with patch("api.compute._resolve_git_project_name", return_value="proj-1"):
            with patch("api.compute.get_sse_connection_manager", return_value=mock_sse):
                await _dispatch_conflict_resolution_work(
                    mock_work, "feature/test", "compute-001", mock_pr
                )

        # Should NOT attempt to send
        mock_sse.send_work_assigned.assert_not_called()
