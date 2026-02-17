"""Tests for RepoManager hook operations.

Unit tests for the hook-related methods in RepoManager:
- verify_hooks: Check if hooks are installed and executable
- install_hooks_all: Install hooks on all existing repositories
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from git.repo_manager import RepoManager


@pytest.fixture
def repo_manager():
    """Create a RepoManager instance with mocked config."""
    with patch("git.repo_manager.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/tmp/repos"
        mock_config.return_value.git.git_user = "git"
        manager = RepoManager()
    return manager


# =============================================================================
# Test: verify_hooks
# =============================================================================

class TestVerifyHooks:
    """Test Git hook verification."""

    def test_verify_hooks_all_installed(self, repo_manager, tmp_path):
        """Test verifying hooks when all are installed and executable."""
        # Set up repo path
        repo_path = tmp_path / "test_project.git"
        repo_path.mkdir()
        hooks_dir = repo_path / "hooks"
        hooks_dir.mkdir()

        # Create executable hooks
        pre_receive = hooks_dir / "pre-receive"
        post_receive = hooks_dir / "post-receive"
        pre_receive.write_text("#!/bin/bash\nexit 0")
        post_receive.write_text("#!/bin/bash\nexit 0")
        os.chmod(pre_receive, 0o755)
        os.chmod(post_receive, 0o755)

        # Patch the _repo_path method
        with patch.object(repo_manager, "_repo_path", return_value=repo_path):
            result = repo_manager.verify_hooks("test_project")

        assert result["hooks_installed"] is True
        assert result["pre_receive"]["exists"] is True
        assert result["pre_receive"]["executable"] is True
        assert result["post_receive"]["exists"] is True
        assert result["post_receive"]["executable"] is True

    def test_verify_hooks_none_installed(self, repo_manager, tmp_path):
        """Test verifying hooks when none are installed."""
        repo_path = tmp_path / "test_project.git"
        repo_path.mkdir()
        hooks_dir = repo_path / "hooks"
        hooks_dir.mkdir()

        with patch.object(repo_manager, "_repo_path", return_value=repo_path):
            result = repo_manager.verify_hooks("test_project")

        assert result["hooks_installed"] is False
        assert result["pre_receive"]["exists"] is False
        assert result["pre_receive"]["executable"] is False
        assert result["post_receive"]["exists"] is False
        assert result["post_receive"]["executable"] is False

    def test_verify_hooks_partial_installed(self, repo_manager, tmp_path):
        """Test verifying hooks when only some are installed."""
        repo_path = tmp_path / "test_project.git"
        repo_path.mkdir()
        hooks_dir = repo_path / "hooks"
        hooks_dir.mkdir()

        # Only create pre-receive
        pre_receive = hooks_dir / "pre-receive"
        pre_receive.write_text("#!/bin/bash\nexit 0")
        os.chmod(pre_receive, 0o755)

        with patch.object(repo_manager, "_repo_path", return_value=repo_path):
            result = repo_manager.verify_hooks("test_project")

        assert result["hooks_installed"] is False
        assert result["pre_receive"]["exists"] is True
        assert result["pre_receive"]["executable"] is True
        assert result["post_receive"]["exists"] is False

    def test_verify_hooks_not_executable(self, repo_manager, tmp_path):
        """Test verifying hooks when they exist but aren't executable."""
        repo_path = tmp_path / "test_project.git"
        repo_path.mkdir()
        hooks_dir = repo_path / "hooks"
        hooks_dir.mkdir()

        # Create non-executable hooks
        pre_receive = hooks_dir / "pre-receive"
        post_receive = hooks_dir / "post-receive"
        pre_receive.write_text("#!/bin/bash\nexit 0")
        post_receive.write_text("#!/bin/bash\nexit 0")
        os.chmod(pre_receive, 0o644)  # Not executable
        os.chmod(post_receive, 0o644)  # Not executable

        with patch.object(repo_manager, "_repo_path", return_value=repo_path):
            result = repo_manager.verify_hooks("test_project")

        assert result["hooks_installed"] is False
        assert result["pre_receive"]["exists"] is True
        assert result["pre_receive"]["executable"] is False
        assert result["post_receive"]["exists"] is True
        assert result["post_receive"]["executable"] is False

    def test_verify_hooks_repo_not_found(self, repo_manager, tmp_path):
        """Test verify_hooks raises when repository doesn't exist."""
        repo_path = tmp_path / "nonexistent.git"

        with patch.object(repo_manager, "_repo_path", return_value=repo_path):
            with pytest.raises(FileNotFoundError):
                repo_manager.verify_hooks("nonexistent")


# =============================================================================
# Test: install_hooks_all
# =============================================================================

class TestInstallHooksAll:
    """Test hook migration across all repositories."""

    def test_install_hooks_all_success(self, repo_manager):
        """Test installing hooks on all repos successfully."""
        with patch.object(repo_manager, "list_repos", return_value=["repo1", "repo2", "repo3"]):
            with patch.object(repo_manager, "install_hooks") as mock_install:
                result = repo_manager.install_hooks_all()

        assert result["total"] == 3
        assert result["success"] == 3
        assert result["failed"] == 0
        assert result["results"]["repo1"]["success"] is True
        assert result["results"]["repo2"]["success"] is True
        assert result["results"]["repo3"]["success"] is True
        assert mock_install.call_count == 3

    def test_install_hooks_all_partial_failure(self, repo_manager):
        """Test installing hooks with some failures."""
        def mock_install_hooks(project):
            if project == "repo2":
                raise Exception("Permission denied")

        with patch.object(repo_manager, "list_repos", return_value=["repo1", "repo2", "repo3"]):
            with patch.object(repo_manager, "install_hooks", side_effect=mock_install_hooks):
                result = repo_manager.install_hooks_all()

        assert result["total"] == 3
        assert result["success"] == 2
        assert result["failed"] == 1
        assert result["results"]["repo1"]["success"] is True
        assert result["results"]["repo2"]["success"] is False
        assert "Permission denied" in result["results"]["repo2"]["error"]
        assert result["results"]["repo3"]["success"] is True

    def test_install_hooks_all_empty_list(self, repo_manager):
        """Test installing hooks when no repos exist."""
        with patch.object(repo_manager, "list_repos", return_value=[]):
            result = repo_manager.install_hooks_all()

        assert result["total"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0
        assert result["results"] == {}

    def test_install_hooks_all_all_fail(self, repo_manager):
        """Test installing hooks when all fail."""
        with patch.object(repo_manager, "list_repos", return_value=["repo1", "repo2"]):
            with patch.object(
                repo_manager, "install_hooks", side_effect=Exception("Hook template not found")
            ):
                result = repo_manager.install_hooks_all()

        assert result["total"] == 2
        assert result["success"] == 0
        assert result["failed"] == 2
