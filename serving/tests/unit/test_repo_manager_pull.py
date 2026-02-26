"""Tests for RepoManager.pull_from_origin safe fetch behavior."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from git.repo_manager import RepoManager


@pytest.fixture
def repo_manager(tmp_path):
    """Create a RepoManager with a temp repos directory."""
    config = MagicMock()
    config.repos_path = str(tmp_path / "repos")
    return RepoManager(config=config)


class TestPullFromOriginLinkedRepo:
    """Test pull_from_origin preserves compute branches for linked repos."""

    @patch("git.repo_manager.subprocess.run")
    def test_linked_repo_fetches_origin_only(self, mock_run, repo_manager, tmp_path):
        """Linked repos should fetch from origin only, not --all."""
        repo_path = tmp_path / "repos" / "test-project.git"
        repo_path.mkdir(parents=True)

        # _git_cmd for claudevn.isLinked check returns "true"
        linked_check = MagicMock(returncode=0, stdout="true\n")
        with patch.object(repo_manager, "_git_cmd", return_value=linked_check):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = repo_manager.pull_from_origin("test-project")

        fetch_call = mock_run.call_args
        fetch_cmd = fetch_call[0][0] if fetch_call[0] else fetch_call[1].get("args", [])

        assert "origin" in fetch_cmd
        assert "--all" not in fetch_cmd
        assert "--prune" not in fetch_cmd
        assert "--tags" in fetch_cmd
        assert result["success"] is True

    @patch("git.repo_manager.subprocess.run")
    def test_linked_repo_omits_prune(self, mock_run, repo_manager, tmp_path):
        """Linked repos must not use --prune to preserve compute branches."""
        repo_path = tmp_path / "repos" / "test-project.git"
        repo_path.mkdir(parents=True)

        linked_check = MagicMock(returncode=0, stdout="true\n")
        with patch.object(repo_manager, "_git_cmd", return_value=linked_check):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            repo_manager.pull_from_origin("test-project")

        fetch_cmd = mock_run.call_args[0][0]
        assert "--prune" not in fetch_cmd


class TestPullFromOriginInternalRepo:
    """Test pull_from_origin retains existing behavior for internal repos."""

    @patch("git.repo_manager.subprocess.run")
    def test_internal_repo_fetches_all_with_prune(self, mock_run, repo_manager, tmp_path):
        """Internal repos should use --all --prune --tags (original behavior)."""
        repo_path = tmp_path / "repos" / "test-project.git"
        repo_path.mkdir(parents=True)

        # _git_cmd returns non-zero (no claudevn.isLinked config)
        not_linked = MagicMock(returncode=1, stdout="")
        with patch.object(repo_manager, "_git_cmd", return_value=not_linked):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = repo_manager.pull_from_origin("test-project")

        fetch_cmd = mock_run.call_args[0][0]
        assert "--all" in fetch_cmd
        assert "--prune" in fetch_cmd
        assert "--tags" in fetch_cmd
        assert result["success"] is True

    @patch("git.repo_manager.subprocess.run")
    def test_internal_repo_when_linked_config_missing(self, mock_run, repo_manager, tmp_path):
        """Repos without claudevn.isLinked should use internal fetch behavior."""
        repo_path = tmp_path / "repos" / "test-project.git"
        repo_path.mkdir(parents=True)

        # Config key doesn't exist → returncode 1
        no_config = MagicMock(returncode=1, stdout="")
        with patch.object(repo_manager, "_git_cmd", return_value=no_config):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            repo_manager.pull_from_origin("test-project")

        fetch_cmd = mock_run.call_args[0][0]
        assert "--all" in fetch_cmd
        assert "--prune" in fetch_cmd


class TestPullFromOriginSshKey:
    """Test SSH key is passed through for both repo types."""

    @patch("git.repo_manager.subprocess.run")
    def test_ssh_key_set_in_env_for_linked_repo(self, mock_run, repo_manager, tmp_path):
        """SSH key should be passed via GIT_SSH_COMMAND for linked repos."""
        repo_path = tmp_path / "repos" / "test-project.git"
        repo_path.mkdir(parents=True)

        linked_check = MagicMock(returncode=0, stdout="true\n")
        with patch.object(repo_manager, "_git_cmd", return_value=linked_check):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            repo_manager.pull_from_origin("test-project", ssh_key_path="/tmp/key")

        fetch_call = mock_run.call_args
        env = fetch_call[1].get("env") or fetch_call.kwargs.get("env")
        assert env is not None
        assert "/tmp/key" in env.get("GIT_SSH_COMMAND", "")


class TestPullFromOriginErrors:
    """Test error handling in pull_from_origin."""

    def test_raises_file_not_found_for_missing_repo(self, repo_manager):
        """Should raise FileNotFoundError if repo doesn't exist."""
        with pytest.raises(FileNotFoundError):
            repo_manager.pull_from_origin("nonexistent-project")

    @patch("git.repo_manager.subprocess.run")
    def test_raises_on_fetch_failure(self, mock_run, repo_manager, tmp_path):
        """Should raise CalledProcessError when git fetch fails."""
        repo_path = tmp_path / "repos" / "test-project.git"
        repo_path.mkdir(parents=True)

        not_linked = MagicMock(returncode=1, stdout="")
        with patch.object(repo_manager, "_git_cmd", return_value=not_linked):
            mock_run.return_value = MagicMock(
                returncode=128, stdout="", stderr="fatal: error", args=["git", "fetch"]
            )

            import subprocess
            with pytest.raises(subprocess.CalledProcessError):
                repo_manager.pull_from_origin("test-project")
