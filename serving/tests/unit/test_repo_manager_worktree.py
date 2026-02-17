"""Tests for RepoManager worktree operations.

Unit tests for the worktree-related methods in RepoManager:
- clone_regular: Clone repository as non-bare (regular) clone
- add_worktree: Add a Git worktree
- list_worktrees: List all worktrees
- remove_worktree: Remove a worktree
- prune_worktrees: Clean up stale worktree references
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from git.repo_manager import RepoManager


@pytest.fixture
def repo_manager():
    """Create a RepoManager instance with mocked config."""
    with patch("git.repo_manager.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/tmp/repos"
        mock_config.return_value.git.git_user = "git"
        manager = RepoManager()
    return manager


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a temporary directory structure for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return repo_path


# =============================================================================
# Test: clone_regular
# =============================================================================

class TestCloneRegular:
    """Test regular (non-bare) clone operation."""

    @patch("subprocess.run")
    def test_clone_regular_success(self, mock_run, repo_manager, tmp_path):
        """Test successful regular clone."""
        dest_path = tmp_path / "cloned_repo"
        url = "git@github.com:test/repo.git"
        mock_run.return_value = MagicMock(returncode=0)

        result = repo_manager.clone_regular(url, dest_path)

        assert result == dest_path
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "git" in call_args
        assert "clone" in call_args
        assert url in call_args
        assert str(dest_path) in call_args

    @patch("subprocess.run")
    def test_clone_regular_with_branch(self, mock_run, repo_manager, tmp_path):
        """Test clone with specific branch."""
        dest_path = tmp_path / "cloned_repo"
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_regular(
            url="git@github.com:test/repo.git",
            dest_path=dest_path,
            branch="develop"
        )

        call_args = mock_run.call_args[0][0]
        assert "--branch" in call_args
        assert "develop" in call_args

    @patch("subprocess.run")
    def test_clone_regular_with_ssh_key(self, mock_run, repo_manager, tmp_path):
        """Test clone with SSH key authentication."""
        dest_path = tmp_path / "cloned_repo"
        ssh_key = "/path/to/key"
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.clone_regular(
            url="git@github.com:test/repo.git",
            dest_path=dest_path,
            ssh_key_path=ssh_key
        )

        call_kwargs = mock_run.call_args[1]
        env = call_kwargs.get("env", {})
        assert "GIT_SSH_COMMAND" in env
        assert ssh_key in env["GIT_SSH_COMMAND"]

    def test_clone_regular_destination_exists_raises(self, repo_manager, tmp_path):
        """Test that clone raises when destination exists."""
        dest_path = tmp_path / "existing"
        dest_path.mkdir()

        with pytest.raises(FileExistsError):
            repo_manager.clone_regular(
                url="git@github.com:test/repo.git",
                dest_path=dest_path
            )

    @patch("subprocess.run")
    def test_clone_regular_failure_raises(self, mock_run, repo_manager, tmp_path):
        """Test that clone raises on git failure."""
        dest_path = tmp_path / "cloned_repo"
        mock_run.side_effect = subprocess.CalledProcessError(1, "git clone")

        with pytest.raises(subprocess.CalledProcessError):
            repo_manager.clone_regular(
                url="git@github.com:test/repo.git",
                dest_path=dest_path
            )


# =============================================================================
# Test: add_worktree
# =============================================================================

class TestAddWorktree:
    """Test Git worktree add operation."""

    @patch("subprocess.run")
    def test_add_worktree_existing_branch(self, mock_run, repo_manager, tmp_repo, tmp_path):
        """Test adding worktree for existing branch."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = MagicMock(returncode=0)

        result = repo_manager.add_worktree(
            repo_path=tmp_repo,
            worktree_path=worktree_path,
            branch="main"
        )

        assert result == worktree_path
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "worktree" in call_args
        assert "add" in call_args
        assert str(worktree_path) in call_args
        assert "main" in call_args

    @patch("subprocess.run")
    def test_add_worktree_new_branch(self, mock_run, repo_manager, tmp_repo, tmp_path):
        """Test adding worktree with new branch creation."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.add_worktree(
            repo_path=tmp_repo,
            worktree_path=worktree_path,
            branch="feature/new",
            create_branch=True
        )

        call_args = mock_run.call_args[0][0]
        assert "-b" in call_args
        assert "feature/new" in call_args

    @patch("subprocess.run")
    def test_add_worktree_with_track_remote(self, mock_run, repo_manager, tmp_repo, tmp_path):
        """Test adding worktree that tracks a remote branch."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.add_worktree(
            repo_path=tmp_repo,
            worktree_path=worktree_path,
            branch="feature/new",
            create_branch=True,
            track_remote="origin/main"
        )

        call_args = mock_run.call_args[0][0]
        assert "origin/main" in call_args

    def test_add_worktree_repo_not_found_raises(self, repo_manager, tmp_path):
        """Test that add_worktree raises when repo doesn't exist."""
        repo_path = tmp_path / "nonexistent"
        worktree_path = tmp_path / "worktree"

        with pytest.raises(FileNotFoundError):
            repo_manager.add_worktree(
                repo_path=repo_path,
                worktree_path=worktree_path,
                branch="main"
            )

    def test_add_worktree_path_exists_raises(self, repo_manager, tmp_repo, tmp_path):
        """Test that add_worktree raises when worktree path exists."""
        worktree_path = tmp_path / "existing"
        worktree_path.mkdir()

        with pytest.raises(FileExistsError):
            repo_manager.add_worktree(
                repo_path=tmp_repo,
                worktree_path=worktree_path,
                branch="main"
            )


# =============================================================================
# Test: list_worktrees
# =============================================================================

class TestListWorktrees:
    """Test Git worktree list operation."""

    @patch("subprocess.run")
    def test_list_worktrees_success(self, mock_run, repo_manager, tmp_repo):
        """Test listing worktrees."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""worktree /path/to/repo
HEAD abc1234
branch refs/heads/main

worktree /path/to/worktree
HEAD def5678
branch refs/heads/feature
"""
        )

        result = repo_manager.list_worktrees(tmp_repo)

        assert len(result) == 2
        assert result[0]["path"] == "/path/to/repo"
        assert result[0]["branch"] == "main"
        assert result[1]["path"] == "/path/to/worktree"
        assert result[1]["branch"] == "feature"

    @patch("subprocess.run")
    def test_list_worktrees_detached(self, mock_run, repo_manager, tmp_repo):
        """Test listing worktrees with detached HEAD."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="""worktree /path/to/worktree
HEAD abc1234
detached
"""
        )

        result = repo_manager.list_worktrees(tmp_repo)

        assert len(result) == 1
        assert result[0].get("detached") is True

    def test_list_worktrees_repo_not_found(self, repo_manager, tmp_path):
        """Test list returns empty when repo doesn't exist."""
        repo_path = tmp_path / "nonexistent"

        result = repo_manager.list_worktrees(repo_path)

        assert result == []

    @patch("subprocess.run")
    def test_list_worktrees_failure(self, mock_run, repo_manager, tmp_repo):
        """Test list returns empty on git failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = repo_manager.list_worktrees(tmp_repo)

        assert result == []


# =============================================================================
# Test: remove_worktree
# =============================================================================

class TestRemoveWorktree:
    """Test Git worktree remove operation."""

    @patch("subprocess.run")
    def test_remove_worktree_success(self, mock_run, repo_manager, tmp_repo, tmp_path):
        """Test removing a worktree."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = MagicMock(returncode=0)

        result = repo_manager.remove_worktree(tmp_repo, worktree_path)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "worktree" in call_args
        assert "remove" in call_args
        assert str(worktree_path) in call_args

    @patch("subprocess.run")
    def test_remove_worktree_force(self, mock_run, repo_manager, tmp_repo, tmp_path):
        """Test force removing a worktree."""
        worktree_path = tmp_path / "worktree"
        mock_run.return_value = MagicMock(returncode=0)

        repo_manager.remove_worktree(tmp_repo, worktree_path, force=True)

        call_args = mock_run.call_args[0][0]
        assert "--force" in call_args

    def test_remove_worktree_repo_not_found_raises(self, repo_manager, tmp_path):
        """Test that remove raises when repo doesn't exist."""
        repo_path = tmp_path / "nonexistent"
        worktree_path = tmp_path / "worktree"

        with pytest.raises(FileNotFoundError):
            repo_manager.remove_worktree(repo_path, worktree_path)


# =============================================================================
# Test: prune_worktrees
# =============================================================================

class TestPruneWorktrees:
    """Test Git worktree prune operation."""

    @patch("subprocess.run")
    def test_prune_worktrees_success(self, mock_run, repo_manager, tmp_repo):
        """Test pruning stale worktrees."""
        mock_run.return_value = MagicMock(returncode=0)

        result = repo_manager.prune_worktrees(tmp_repo)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "worktree" in call_args
        assert "prune" in call_args

    def test_prune_worktrees_repo_not_found(self, repo_manager, tmp_path):
        """Test prune returns False when repo doesn't exist."""
        repo_path = tmp_path / "nonexistent"

        result = repo_manager.prune_worktrees(repo_path)

        assert result is False
