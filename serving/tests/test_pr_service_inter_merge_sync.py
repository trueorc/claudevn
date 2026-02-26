"""Unit tests for inter-merge upstream sync in PRService.process_merge_queue().

Tests that after each successful merge, _sync_upstream is called so the
next merge starts from the latest state.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from git.pr_service import PRService


@pytest.fixture
def mock_repo_manager():
    manager = MagicMock()
    manager.get_default_branch.return_value = "main"
    manager.get_branch_head.return_value = "abc123"
    return manager


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def pr_service(mock_repo_manager, mock_redis):
    with patch("git.pr_service.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/repos"
        mock_config.return_value.redis.host = "localhost"
        mock_config.return_value.redis.port = 6379
        mock_config.return_value.redis.key_prefix = "cvn:"
        service = PRService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager,
        )
    return service


class TestProcessMergeQueueSync:
    """Tests for inter-merge upstream sync in process_merge_queue."""

    @pytest.mark.asyncio
    async def test_syncs_after_successful_merge(self, pr_service, mock_redis):
        """After a successful merge, _sync_upstream should be called."""
        mock_redis.pop_merge_queue = AsyncMock(
            side_effect=["feature-a", None]
        )

        with patch.object(
            pr_service, "merge", return_value={"success": True, "branch": "feature-a"}
        ):
            with patch.object(pr_service, "_sync_upstream") as mock_sync:
                results = await pr_service.process_merge_queue("test-project")

        assert len(results) == 1
        assert results[0]["success"] is True
        mock_sync.assert_called_once_with(
            "test-project", Path("/repos/test-project.git")
        )

    @pytest.mark.asyncio
    async def test_no_sync_after_failed_merge(self, pr_service, mock_redis):
        """Failed merges should not trigger inter-merge sync."""
        mock_redis.pop_merge_queue = AsyncMock(
            side_effect=["feature-a", None]
        )
        mock_redis.add_to_merge_queue = AsyncMock()

        with patch.object(
            pr_service, "merge", side_effect=ValueError("conflict")
        ):
            with patch.object(pr_service, "_sync_upstream") as mock_sync:
                results = await pr_service.process_merge_queue("test-project")

        assert len(results) == 1
        assert results[0]["success"] is False
        mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_syncs_between_sequential_merges(self, pr_service, mock_redis):
        """Multiple sequential merges should sync between each."""
        mock_redis.pop_merge_queue = AsyncMock(
            side_effect=["feature-a", "feature-b", None]
        )

        with patch.object(pr_service, "merge") as mock_merge:
            mock_merge.side_effect = [
                {"success": True, "branch": "feature-a"},
                {"success": True, "branch": "feature-b"},
            ]
            with patch.object(pr_service, "_sync_upstream") as mock_sync:
                results = await pr_service.process_merge_queue("test-project")

        assert len(results) == 2
        repo_path = Path("/repos/test-project.git")
        assert mock_sync.call_count == 2
        mock_sync.assert_has_calls([
            call("test-project", repo_path),
            call("test-project", repo_path),
        ])

    @pytest.mark.asyncio
    async def test_sync_failure_does_not_stop_queue(self, pr_service, mock_redis):
        """Inter-merge sync failure should not block the next merge."""
        mock_redis.pop_merge_queue = AsyncMock(
            side_effect=["feature-a", "feature-b", None]
        )

        with patch.object(pr_service, "merge") as mock_merge:
            mock_merge.side_effect = [
                {"success": True, "branch": "feature-a"},
                {"success": True, "branch": "feature-b"},
            ]
            with patch.object(
                pr_service,
                "_sync_upstream",
                side_effect=[ValueError("sync failed"), None],
            ) as mock_sync:
                results = await pr_service.process_merge_queue("test-project")

        # Both merges should complete despite first sync failing
        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert mock_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_queue_no_sync(self, pr_service, mock_redis):
        """Empty merge queue should return empty results and no sync."""
        mock_redis.pop_merge_queue = AsyncMock(return_value=None)

        with patch.object(pr_service, "_sync_upstream") as mock_sync:
            results = await pr_service.process_merge_queue("test-project")

        assert results == []
        mock_sync.assert_not_called()
