"""Tests for RepoManager initial commit seeding.

Verifies that create_repo() seeds an initial commit so that
refs/heads/main exists and `git clone --branch main` succeeds.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from git.repo_manager import RepoManager


@pytest.fixture
def repo_manager(tmp_path):
    """Create a RepoManager instance with a real temp repos directory."""
    with patch("git.repo_manager.get_config") as mock_config:
        mock_config.return_value.git.repos_path = str(tmp_path / "repos")
        mock_config.return_value.git.git_user = "nonexistent_user"
        mock_config.return_value.redis.host = "localhost"
        mock_config.return_value.redis.port = 6379
        mock_config.return_value.redis.key_prefix = "claudevn:"
        manager = RepoManager()
    return manager


class TestSeedInitialCommit:
    """Test that create_repo seeds an initial commit on main."""

    def test_create_repo_has_main_branch(self, repo_manager):
        """After create_repo, refs/heads/main should exist."""
        repo_path = repo_manager.create_repo("test-project")

        # Verify refs/heads/main exists
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "refs/heads/main"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) == 40  # Full SHA

    def test_create_repo_clone_with_branch_main(self, repo_manager):
        """git clone --branch main should succeed after create_repo."""
        repo_path = repo_manager.create_repo("test-project")

        with tempfile.TemporaryDirectory() as clone_dir:
            result = subprocess.run(
                ["git", "clone", "--branch", "main", str(repo_path), clone_dir],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0

    def test_create_repo_initial_commit_message(self, repo_manager):
        """The initial commit should have the expected message."""
        repo_path = repo_manager.create_repo("test-project")

        result = subprocess.run(
            ["git", "-C", str(repo_path), "log", "--format=%s", "refs/heads/main"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "Initial commit"

    def test_create_repo_single_commit(self, repo_manager):
        """There should be exactly one commit after create_repo."""
        repo_path = repo_manager.create_repo("test-project")

        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--count", "refs/heads/main"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"


class TestSeedInitialCommitMethod:
    """Test _seed_initial_commit directly."""

    def test_seed_into_bare_repo(self, tmp_path):
        """_seed_initial_commit creates a commit in an empty bare repo."""
        bare_path = tmp_path / "test.git"
        subprocess.run(
            ["git", "init", "--bare", str(bare_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(bare_path), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
            capture_output=True,
        )

        with patch("git.repo_manager.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(tmp_path)
            mock_config.return_value.git.git_user = "nonexistent_user"
            manager = RepoManager()

        manager._seed_initial_commit(bare_path)

        # Verify main branch now exists
        result = subprocess.run(
            ["git", "-C", str(bare_path), "rev-parse", "refs/heads/main"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_seed_with_non_main_branch(self, tmp_path):
        """_seed_initial_commit creates a commit on a custom branch name."""
        bare_path = tmp_path / "test.git"
        subprocess.run(
            ["git", "init", "--bare", str(bare_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(bare_path), "symbolic-ref", "HEAD", "refs/heads/develop"],
            check=True,
            capture_output=True,
        )

        with patch("git.repo_manager.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(tmp_path)
            mock_config.return_value.git.git_user = "nonexistent_user"
            manager = RepoManager()

        manager._seed_initial_commit(bare_path, branch="develop")

        # Verify develop branch exists
        result = subprocess.run(
            ["git", "-C", str(bare_path), "rev-parse", "refs/heads/develop"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Verify main does NOT exist (only develop was seeded)
        result_main = subprocess.run(
            ["git", "-C", str(bare_path), "rev-parse", "refs/heads/main"],
            capture_output=True,
            text=True,
        )
        assert result_main.returncode != 0
