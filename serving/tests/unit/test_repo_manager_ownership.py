"""Tests for RepoManager repository ownership (chown to git user).

Verifies that bare repositories are chowned to the git user after creation
to prevent 'dubious ownership' errors when compute instances clone via SSH.

See: https://github.com/Guarrdon/trueorc/issues/796
"""

import os
import pwd
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from git.repo_manager import RepoManager


@pytest.fixture
def repo_manager():
    """Create a RepoManager instance with mocked config."""
    with patch("git.repo_manager.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/tmp/repos"
        mock_config.return_value.git.git_user = "git"
        mock_config.return_value.redis.host = "localhost"
        mock_config.return_value.redis.port = 6379
        mock_config.return_value.redis.key_prefix = "claudevn:"
        manager = RepoManager()
    return manager


# =============================================================================
# Test: _chown_to_git_user
# =============================================================================

class TestChownToGitUser:
    """Test _chown_to_git_user helper method."""

    def test_chown_applies_to_all_files(self, repo_manager, tmp_path):
        """Test that chown is applied recursively to all files and dirs."""
        # Create a fake repo structure
        repo_dir = tmp_path / "test.git"
        repo_dir.mkdir()
        (repo_dir / "HEAD").write_text("ref: refs/heads/main\n")
        objects_dir = repo_dir / "objects"
        objects_dir.mkdir()
        (objects_dir / "pack").mkdir()

        mock_pw = MagicMock()
        mock_pw.pw_uid = 1001
        mock_pw.pw_gid = 1001

        with patch("git.repo_manager.pwd.getpwnam", return_value=mock_pw) as mock_getpw, \
             patch("git.repo_manager.os.chown") as mock_chown:
            repo_manager._chown_to_git_user(repo_dir)

        mock_getpw.assert_called_once_with("git")
        # Should have chowned directories and files
        assert mock_chown.call_count > 0
        # Verify all calls use the correct uid/gid
        for c in mock_chown.call_args_list:
            assert c[0][1] == 1001  # uid
            assert c[0][2] == 1001  # gid

    def test_chown_skipped_when_user_not_found(self, repo_manager, tmp_path):
        """Test graceful handling when git user doesn't exist."""
        repo_dir = tmp_path / "test.git"
        repo_dir.mkdir()

        with patch("git.repo_manager.pwd.getpwnam", side_effect=KeyError("git")), \
             patch("git.repo_manager.os.chown") as mock_chown:
            # Should not raise
            repo_manager._chown_to_git_user(repo_dir)

        mock_chown.assert_not_called()

    def test_chown_handles_os_error(self, repo_manager, tmp_path):
        """Test graceful handling of OS permission errors."""
        repo_dir = tmp_path / "test.git"
        repo_dir.mkdir()

        mock_pw = MagicMock()
        mock_pw.pw_uid = 1001
        mock_pw.pw_gid = 1001

        with patch("git.repo_manager.pwd.getpwnam", return_value=mock_pw), \
             patch("git.repo_manager.os.chown", side_effect=OSError("Permission denied")):
            # Should not raise
            repo_manager._chown_to_git_user(repo_dir)


# =============================================================================
# Test: create_repo calls _chown_to_git_user
# =============================================================================

class TestCreateRepoOwnership:
    """Test that create_repo chowns the repo to git user."""

    @patch("git.repo_manager.subprocess.run")
    def test_create_repo_calls_chown(self, mock_run, repo_manager, tmp_path):
        """Test that create_repo chowns the new bare repo."""
        repo_manager._repos_path = tmp_path

        with patch.object(repo_manager, "install_hooks"), \
             patch.object(repo_manager, "_chown_to_git_user") as mock_chown:
            repo_manager.create_repo("test_project")

        mock_chown.assert_called_once()
        chown_path = mock_chown.call_args[0][0]
        assert str(chown_path).endswith("test_project.git")


# =============================================================================
# Test: clone_from_url calls _chown_to_git_user
# =============================================================================

class TestCloneFromUrlOwnership:
    """Test that clone_from_url chowns the repo to git user."""

    @patch("git.repo_manager.subprocess.run")
    def test_clone_from_url_calls_chown(self, mock_run, repo_manager, tmp_path):
        """Test that clone_from_url chowns the cloned bare repo."""
        repo_manager._repos_path = tmp_path

        with patch.object(repo_manager, "install_hooks"), \
             patch.object(repo_manager, "_chown_to_git_user") as mock_chown:
            repo_manager.clone_from_url("test_project", "https://github.com/test/repo.git")

        mock_chown.assert_called_once()
        chown_path = mock_chown.call_args[0][0]
        assert str(chown_path).endswith("test_project.git")
