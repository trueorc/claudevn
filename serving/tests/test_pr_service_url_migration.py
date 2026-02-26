"""Unit tests for HTTPS→SSH URL migration in PRService.

Tests _ensure_ssh_remote_urls and its integration with _push_upstream
and _sync_upstream.
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

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


class TestEnsureSshRemoteUrls:
    """Test _ensure_ssh_remote_urls migration helper."""

    def test_converts_https_fetch_url(self, pr_service):
        """HTTPS fetch URL should be converted to SSH."""
        repo_path = Path("/repos/test.git")

        # Simulate: fetch URL is HTTPS, push URL is already SSH
        def mock_git_cmd(path, *args):
            result = MagicMock()
            cmd = list(args)
            if cmd == ["remote", "get-url", "origin"]:
                result.returncode = 0
                result.stdout = "https://github.com/org/repo.git\n"
            elif cmd == ["remote", "get-url", "--push", "origin"]:
                result.returncode = 0
                result.stdout = "git@github.com:org/repo.git\n"
            elif cmd[:2] == ["remote", "set-url"]:
                result.returncode = 0
                result.stdout = ""
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        pr_service._git_cmd = mock_git_cmd
        calls = []
        original_git_cmd = pr_service._git_cmd

        def tracking_git_cmd(path, *args):
            calls.append(list(args))
            return original_git_cmd(path, *args)

        pr_service._git_cmd = tracking_git_cmd
        pr_service._ensure_ssh_remote_urls(repo_path)

        # Should have called set-url for fetch (HTTPS→SSH) but not push (already SSH)
        set_url_calls = [c for c in calls if c[:2] == ["remote", "set-url"]]
        assert len(set_url_calls) == 1
        assert set_url_calls[0] == ["remote", "set-url", "origin", "git@github.com:org/repo.git"]

    def test_converts_both_urls(self, pr_service):
        """Both HTTPS fetch and push URLs should be converted."""
        repo_path = Path("/repos/test.git")

        def mock_git_cmd(path, *args):
            result = MagicMock()
            cmd = list(args)
            if "get-url" in cmd:
                result.returncode = 0
                result.stdout = "https://github.com/org/repo.git\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        calls = []

        def tracking_git_cmd(path, *args):
            calls.append(list(args))
            return mock_git_cmd(path, *args)

        pr_service._git_cmd = tracking_git_cmd
        pr_service._ensure_ssh_remote_urls(repo_path)

        set_url_calls = [c for c in calls if c[:2] == ["remote", "set-url"]]
        assert len(set_url_calls) == 2

    def test_noop_when_already_ssh(self, pr_service):
        """No changes needed when URLs are already SSH."""
        repo_path = Path("/repos/test.git")

        def mock_git_cmd(path, *args):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "git@github.com:org/repo.git\n"
            return result

        calls = []

        def tracking_git_cmd(path, *args):
            calls.append(list(args))
            return mock_git_cmd(path, *args)

        pr_service._git_cmd = tracking_git_cmd
        pr_service._ensure_ssh_remote_urls(repo_path)

        set_url_calls = [c for c in calls if c[:2] == ["remote", "set-url"]]
        assert len(set_url_calls) == 0


class TestPushUpstreamUrlMigration:
    """Test _push_upstream triggers URL migration when SSH key is present."""

    @pytest.mark.asyncio
    async def test_push_upstream_calls_ensure_ssh(self, pr_service, mock_redis):
        """_push_upstream should call _ensure_ssh_remote_urls when SSH key exists."""
        repo_path = Path("/repos/test.git")
        pr = PullRequest(
            project="test",
            branch="feat/test",
            compute_id="c1",
            status=PRStatus.PENDING,
        )

        # Mock git config reads
        def mock_read_config(path, key):
            return {"claudevn.isLinked": "true", "claudevn.sshKeyId": "sshk_abc"}.get(key)

        pr_service._read_git_config = mock_read_config
        pr_service._get_redis = AsyncMock(return_value=mock_redis)

        # Track migration call
        migration_called = False

        def mock_ensure_ssh(path):
            nonlocal migration_called
            migration_called = True

        pr_service._ensure_ssh_remote_urls = mock_ensure_ssh

        # Mock subprocess for the push itself
        push_result = MagicMock()
        push_result.returncode = 0
        push_result.stdout = ""
        push_result.stderr = ""

        with patch("git.pr_service.subprocess.run", return_value=push_result):
            await pr_service._push_upstream(
                project="test",
                repo_path=repo_path,
                default_branch="main",
                pr=pr,
                merge_commit="abc123",
            )

        assert migration_called is True

    @pytest.mark.asyncio
    async def test_push_upstream_skips_migration_without_ssh_key(self, pr_service, mock_redis):
        """_push_upstream should NOT call migration when no SSH key."""
        repo_path = Path("/repos/test.git")
        pr = PullRequest(
            project="test",
            branch="feat/test",
            compute_id="c1",
            status=PRStatus.PENDING,
        )

        def mock_read_config(path, key):
            configs = {"claudevn.isLinked": "true", "claudevn.sshKeyId": None}
            return configs.get(key)

        pr_service._read_git_config = mock_read_config
        pr_service._get_redis = AsyncMock(return_value=mock_redis)

        migration_called = False

        def mock_ensure_ssh(path):
            nonlocal migration_called
            migration_called = True

        pr_service._ensure_ssh_remote_urls = mock_ensure_ssh

        push_result = MagicMock()
        push_result.returncode = 0

        with patch("git.pr_service.subprocess.run", return_value=push_result):
            await pr_service._push_upstream(
                project="test",
                repo_path=repo_path,
                default_branch="main",
                pr=pr,
                merge_commit="abc123",
            )

        assert migration_called is False


class TestSyncUpstreamUrlMigration:
    """Test _sync_upstream triggers URL migration when SSH key is present."""

    def test_sync_upstream_calls_ensure_ssh(self, pr_service, mock_repo_manager):
        """_sync_upstream should call _ensure_ssh_remote_urls when SSH key exists."""
        repo_path = Path("/repos/test.git")

        def mock_read_config(path, key):
            return {"claudevn.isLinked": "true", "claudevn.sshKeyId": "sshk_abc"}.get(key)

        pr_service._read_git_config = mock_read_config

        migration_called = False

        def mock_ensure_ssh(path):
            nonlocal migration_called
            migration_called = True

        pr_service._ensure_ssh_remote_urls = mock_ensure_ssh

        pr_service._sync_upstream(project="test", repo_path=repo_path)

        assert migration_called is True
