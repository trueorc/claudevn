"""Unit tests for pre-merge upstream sync in PRService.

Tests the _sync_upstream helper and its integration with merge() and dry_run_merge().
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from git.pr_service import PRService, PRStatus, PullRequest


@pytest.fixture
def mock_repo_manager():
    manager = MagicMock()
    manager.get_default_branch.return_value = "main"
    manager.get_branch_head.return_value = "abc123"
    manager.pull_from_origin.return_value = {
        "success": True,
        "project": "test-project",
        "output": "",
    }
    return manager


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set_branch_status = AsyncMock()
    redis.remove_from_pr_queue = AsyncMock()
    redis.untrack_compute_branch = AsyncMock()
    redis.publish_git_event = AsyncMock()
    return redis


@pytest.fixture
def mock_ssh_key_service():
    service = MagicMock()
    private_key = MagicMock()
    private_key.exists.return_value = True
    private_key.__str__ = lambda self: "/keys/sshk_abc123"
    service._private_key_path.return_value = private_key
    return service


@pytest.fixture
def pr_service(mock_repo_manager, mock_redis, mock_ssh_key_service):
    with patch("git.pr_service.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/repos"
        mock_config.return_value.redis.host = "localhost"
        mock_config.return_value.redis.port = 6379
        mock_config.return_value.redis.key_prefix = "cvn:"
        service = PRService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager,
            ssh_key_service=mock_ssh_key_service,
        )
    return service


class TestSyncUpstream:
    """Tests for _sync_upstream helper method."""

    def test_skips_internal_repos(self, pr_service, mock_repo_manager):
        """Internal repos (not linked) should skip upstream fetch."""
        with patch.object(pr_service, "_read_git_config", return_value=None):
            pr_service._sync_upstream("test-project", Path("/repos/test-project.git"))

        mock_repo_manager.pull_from_origin.assert_not_called()

    def test_skips_when_is_linked_false(self, pr_service, mock_repo_manager):
        """Repos with claudevn.isLinked=false should skip upstream fetch."""
        with patch.object(pr_service, "_read_git_config", return_value="false"):
            pr_service._sync_upstream("test-project", Path("/repos/test-project.git"))

        mock_repo_manager.pull_from_origin.assert_not_called()

    def test_fetches_upstream_for_linked_repo(self, pr_service, mock_repo_manager):
        """Linked repos should fetch from upstream before merge."""
        def config_side_effect(repo_path, key):
            return {"claudevn.isLinked": "true", "claudevn.sshKeyId": "sshk_abc123"}.get(key)

        with patch.object(pr_service, "_read_git_config", side_effect=config_side_effect):
            with patch.object(pr_service, "_resolve_ssh_key_path", return_value="/keys/sshk_abc123"):
                pr_service._sync_upstream("test-project", Path("/repos/test-project.git"))

        mock_repo_manager.pull_from_origin.assert_called_once_with(
            "test-project", ssh_key_path="/keys/sshk_abc123"
        )

    def test_fetches_without_ssh_key_when_not_configured(self, pr_service, mock_repo_manager):
        """Linked repos without SSH key should still attempt fetch."""
        def config_side_effect(repo_path, key):
            return {"claudevn.isLinked": "true", "claudevn.sshKeyId": None}.get(key)

        with patch.object(pr_service, "_read_git_config", side_effect=config_side_effect):
            pr_service._sync_upstream("test-project", Path("/repos/test-project.git"))

        mock_repo_manager.pull_from_origin.assert_called_once_with(
            "test-project", ssh_key_path=None
        )

    def test_raises_on_fetch_failure(self, pr_service, mock_repo_manager):
        """Failed upstream fetch should raise ValueError to abort merge."""
        def config_side_effect(repo_path, key):
            return {"claudevn.isLinked": "true", "claudevn.sshKeyId": None}.get(key)

        mock_repo_manager.pull_from_origin.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "fetch"],
            output="",
            stderr="fatal: Could not read from remote repository",
        )

        with patch.object(pr_service, "_read_git_config", side_effect=config_side_effect):
            with pytest.raises(ValueError, match="Pre-merge upstream sync failed"):
                pr_service._sync_upstream("test-project", Path("/repos/test-project.git"))


class TestDryRunMergeUpstreamSync:
    """Tests for upstream sync integration in dry_run_merge()."""

    async def test_dry_run_syncs_upstream_for_linked_repo(self, pr_service, mock_repo_manager):
        """dry_run_merge should call _sync_upstream before conflict detection."""
        with patch.object(pr_service, "_sync_upstream") as mock_sync:
            # Make the clone fail early so we don't need full merge setup
            with patch("git.pr_service.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
                result = await pr_service.dry_run_merge("test-project", "feature-branch")

        mock_sync.assert_called_once_with("test-project", Path("/repos/test-project.git"))

    async def test_dry_run_returns_error_on_sync_failure(self, pr_service):
        """dry_run_merge should return error dict if upstream sync fails."""
        with patch.object(
            pr_service,
            "_sync_upstream",
            side_effect=ValueError("Pre-merge upstream sync failed for test-project: connection refused"),
        ):
            result = await pr_service.dry_run_merge("test-project", "feature-branch")

        assert result["can_merge"] is False
        assert "upstream sync failed" in result["error"]


class TestMergeUpstreamSync:
    """Tests for upstream sync integration in merge()."""

    async def test_merge_syncs_upstream_for_linked_repo(self, pr_service, mock_redis):
        """merge() should call _sync_upstream before proceeding."""
        mock_pr = PullRequest(
            project="test-project",
            branch="feature-branch",
            status=PRStatus.APPROVED,
            compute_id="compute-001",
        )

        with patch.object(pr_service, "_sync_upstream") as mock_sync:
            with patch.object(pr_service, "get_pr", return_value=mock_pr):
                with patch.object(pr_service, "check_mergeable", return_value={"mergeable": True}):
                    with patch("git.pr_service.subprocess.run") as mock_run:
                        # Set up successful subprocess calls
                        mock_run.return_value = MagicMock(
                            returncode=0,
                            stdout="abc123def456\n",
                            stderr="",
                        )
                        with patch.object(pr_service, "_push_upstream", return_value=None):
                            await pr_service.merge("test-project", "feature-branch")

        mock_sync.assert_called_once_with("test-project", Path("/repos/test-project.git"))

    async def test_merge_aborts_on_sync_failure(self, pr_service):
        """merge() should raise ValueError if upstream sync fails."""
        with patch.object(
            pr_service,
            "_sync_upstream",
            side_effect=ValueError("Pre-merge upstream sync failed"),
        ):
            with pytest.raises(ValueError, match="Pre-merge upstream sync failed"):
                await pr_service.merge("test-project", "feature-branch")
