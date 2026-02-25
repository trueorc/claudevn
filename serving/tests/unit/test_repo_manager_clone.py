"""Tests for RepoManager.clone_from_url safe bare clone behavior."""

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


class TestCloneFromUrl:
    """Test clone_from_url uses safe bare clone (not mirror)."""

    @patch.object(RepoManager, "install_hooks")
    @patch("git.repo_manager.subprocess.run")
    def test_clone_uses_bare_not_mirror(self, mock_run, mock_hooks, repo_manager):
        """Verify clone uses --bare without --mirror."""
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_from_url(
            project="test-project",
            url="git@github.com:test/repo.git",
        )

        # First subprocess call is the clone
        clone_call = mock_run.call_args_list[0]
        clone_cmd = clone_call[0][0]

        assert "--bare" in clone_cmd
        assert "--mirror" not in clone_cmd

    @patch.object(RepoManager, "install_hooks")
    @patch("git.repo_manager.subprocess.run")
    def test_clone_sets_restricted_fetch_refspec(self, mock_run, mock_hooks, repo_manager):
        """Verify fetch refspec is restricted to default branch + tags."""
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_from_url(
            project="test-project",
            url="git@github.com:test/repo.git",
            default_branch="main",
        )

        # Collect all git config calls
        config_calls = [
            c for c in mock_run.call_args_list
            if "config" in c[0][0]
        ]

        # Find the fetch refspec calls
        fetch_refspec_cmds = [
            c[0][0] for c in config_calls
            if "remote.origin.fetch" in c[0][0]
        ]

        assert len(fetch_refspec_cmds) == 2, (
            f"Expected 2 fetch refspec config calls, got {len(fetch_refspec_cmds)}"
        )

        # First: default branch only
        assert "+refs/heads/main:refs/heads/main" in fetch_refspec_cmds[0]

        # Second: tags (with --add)
        assert "--add" in fetch_refspec_cmds[1]
        assert "+refs/tags/*:refs/tags/*" in fetch_refspec_cmds[1]

    @patch.object(RepoManager, "install_hooks")
    @patch("git.repo_manager.subprocess.run")
    def test_clone_respects_custom_default_branch(self, mock_run, mock_hooks, repo_manager):
        """Verify refspec uses the provided default_branch, not hardcoded main."""
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_from_url(
            project="test-project",
            url="git@github.com:test/repo.git",
            default_branch="develop",
        )

        config_calls = [
            c[0][0] for c in mock_run.call_args_list
            if "remote.origin.fetch" in c[0][0]
        ]

        assert "+refs/heads/develop:refs/heads/develop" in config_calls[0]

    @patch.object(RepoManager, "install_hooks")
    @patch("git.repo_manager.subprocess.run")
    def test_clone_stores_linked_metadata(self, mock_run, mock_hooks, repo_manager):
        """Verify claudevn.isLinked is set in git config."""
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_from_url(
            project="test-project",
            url="git@github.com:test/repo.git",
        )

        config_calls = [
            c[0][0] for c in mock_run.call_args_list
            if "config" in c[0][0]
        ]

        is_linked_cmds = [
            c for c in config_calls
            if "claudevn.isLinked" in c
        ]

        assert len(is_linked_cmds) == 1
        assert "true" in is_linked_cmds[0]

    @patch.object(RepoManager, "install_hooks")
    @patch("git.repo_manager.subprocess.run")
    def test_clone_stores_ssh_key_id(self, mock_run, mock_hooks, repo_manager):
        """Verify claudevn.sshKeyId is stored when provided."""
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_from_url(
            project="test-project",
            url="git@github.com:test/repo.git",
            ssh_key_id="key-42",
        )

        config_calls = [
            c[0][0] for c in mock_run.call_args_list
            if "config" in c[0][0]
        ]

        ssh_key_cmds = [
            c for c in config_calls
            if "claudevn.sshKeyId" in c
        ]

        assert len(ssh_key_cmds) == 1
        assert "key-42" in ssh_key_cmds[0]

    @patch.object(RepoManager, "install_hooks")
    @patch("git.repo_manager.subprocess.run")
    def test_clone_omits_ssh_key_id_when_not_provided(self, mock_run, mock_hooks, repo_manager):
        """Verify claudevn.sshKeyId is NOT set when ssh_key_id is None."""
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_from_url(
            project="test-project",
            url="git@github.com:test/repo.git",
        )

        config_calls = [
            c[0][0] for c in mock_run.call_args_list
            if "config" in c[0][0]
        ]

        ssh_key_cmds = [
            c for c in config_calls
            if "claudevn.sshKeyId" in c
        ]

        assert len(ssh_key_cmds) == 0

    @patch("git.repo_manager.subprocess.run")
    def test_clone_raises_if_repo_exists(self, mock_run, repo_manager):
        """Verify FileExistsError when repo directory already exists."""
        # Create the repo directory to simulate existing repo
        repo_path = repo_manager._repo_path("test-project")
        repo_path.mkdir(parents=True)

        with pytest.raises(FileExistsError, match="already exists"):
            repo_manager.clone_from_url(
                project="test-project",
                url="git@github.com:test/repo.git",
            )


class TestGetRepoStatusLinked:
    """Test get_repo_status reports is_linked from git config."""

    @patch("git.repo_manager.subprocess.run")
    def test_status_reports_is_linked_true(self, mock_run, repo_manager):
        """Verify is_linked is True when claudevn.isLinked is set."""
        repo_path = repo_manager._repo_path("test-project")
        repo_path.mkdir(parents=True)
        (repo_path / "HEAD").write_text("ref: refs/heads/main\n")

        def side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0, stdout="", stderr="")
            cmd_str = " ".join(cmd)
            if "remote" in cmd and "get-url" in cmd:
                result.stdout = "git@github.com:test/repo.git\n"
            elif "branch" in cmd and "--list" in cmd:
                result.stdout = "main\n"
            elif "symbolic-ref" in cmd:
                result.stdout = "refs/heads/main\n"
            elif "remote.origin.mirror" in cmd:
                result.returncode = 1  # not a mirror
            elif "claudevn.isLinked" in cmd:
                result.stdout = "true\n"
            return result

        mock_run.side_effect = side_effect

        status = repo_manager.get_repo_status("test-project")

        assert status is not None
        assert status["is_linked"] is True
        assert status["is_mirror"] is False

    @patch("git.repo_manager.subprocess.run")
    def test_status_reports_is_linked_false_for_internal_repos(self, mock_run, repo_manager):
        """Verify is_linked is False for repos without claudevn.isLinked."""
        repo_path = repo_manager._repo_path("internal-project")
        repo_path.mkdir(parents=True)
        (repo_path / "HEAD").write_text("ref: refs/heads/main\n")

        def side_effect(cmd, **kwargs):
            result = MagicMock(returncode=0, stdout="", stderr="")
            if "remote" in cmd and "get-url" in cmd:
                result.stdout = "\n"
            elif "branch" in cmd and "--list" in cmd:
                result.stdout = "main\n"
            elif "symbolic-ref" in cmd:
                result.stdout = "refs/heads/main\n"
            elif "config" in cmd and "--get" in cmd:
                result.returncode = 1  # no config value
            return result

        mock_run.side_effect = side_effect

        status = repo_manager.get_repo_status("internal-project")

        assert status is not None
        assert status["is_linked"] is False
        assert status["is_mirror"] is False
