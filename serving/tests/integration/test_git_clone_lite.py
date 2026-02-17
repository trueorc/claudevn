#!/usr/bin/env python3
"""
Lightweight Git Clone Integration Tests
========================================

Tier-2 integration tests for git clone capability that run against a minimal
Serving instance without requiring full Docker Compose setup.

These tests focus specifically on:
1. Repository creation with proper branch setup
2. Git clone operations from bare repositories
3. Main branch configuration and HEAD setup

Prerequisites (minimal):
- Python test environment with pytest
- Git CLI installed
- Temporary directory for test repos

No Docker, no Redis, no full system required - just fast git infrastructure tests.

Run with:
    pytest serving/tests/integration/test_git_clone_lite.py -v

Or use the integration test script:
    ./scripts/run_integration_tests.sh -s serving/tests/integration/test_git_clone_lite.py
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from git.repo_manager import RepoManager


class TestGitRepositoryCreation:
    """Test repository creation with proper initialization."""

    @pytest.fixture
    def temp_repos_dir(self):
        """Create temporary directory for test repositories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo_manager(self, temp_repos_dir):
        """Create RepoManager with temporary repos path."""
        from config import GitConfig

        config = GitConfig(
            repos_path=str(temp_repos_dir / "repos"),
            ssh_keys_path=str(temp_repos_dir / "keys"),
            git_user="git",
            enable_ssh=False  # Disable SSH for lite tests
        )
        return RepoManager(config=config)

    def test_create_bare_repository(self, repo_manager):
        """Test creating a bare Git repository."""
        project = "test-project"

        # Create repository
        repo_path = repo_manager.create_repo(project, install_hooks=False)

        # Verify repository exists and is valid
        assert repo_path.exists()
        assert (repo_path / "HEAD").exists()
        assert (repo_path / "config").exists()
        assert (repo_path / "objects").exists()
        assert (repo_path / "refs").exists()

    def test_repository_has_correct_default_branch(self, repo_manager):
        """Test that new repositories have main as default branch."""
        project = "test-default-branch"

        # Create repository
        repo_path = repo_manager.create_repo(project, install_hooks=False)

        # Check HEAD points to main
        result = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )

        assert result.stdout.strip() == "refs/heads/main"

    def test_repository_list_operations(self, repo_manager):
        """Test listing repositories."""
        # Create multiple repositories
        projects = ["project-a", "project-b", "project-c"]
        for project in projects:
            repo_manager.create_repo(project, install_hooks=False)

        # List repositories
        repos = repo_manager.list_repos()

        # Verify all created repos are listed
        assert len(repos) >= len(projects)
        for project in projects:
            assert project in repos

    def test_repository_status(self, repo_manager):
        """Test getting repository status."""
        project = "test-status"
        repo_path = repo_manager.create_repo(project, install_hooks=False)

        # Get status
        status = repo_manager.get_repo_status(project)

        # Verify status contains expected fields
        assert status is not None
        assert status["project"] == project
        assert status["path"] == str(repo_path)
        assert status["exists"] is True
        assert status["default_branch"] == "main"
        # After recent fixes (#806), bare repos are created with an initial commit,
        # so main branch exists immediately
        assert "main" in status["branches"]


class TestGitCloneOperations:
    """Test git clone operations against created repositories."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for repos and clones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            repos_dir = base / "repos"
            clones_dir = base / "clones"
            repos_dir.mkdir()
            clones_dir.mkdir()
            yield {
                "base": base,
                "repos": repos_dir,
                "clones": clones_dir
            }

    @pytest.fixture
    def repo_manager_with_seed(self, temp_dirs):
        """Create RepoManager and seed a test repository with initial commit."""
        from config import GitConfig

        config = GitConfig(
            repos_path=str(temp_dirs["repos"]),
            ssh_keys_path=str(temp_dirs["base"] / "keys"),
            git_user="git",
            enable_ssh=False
        )
        manager = RepoManager(config=config)

        # Create a repository with an initial commit
        project = "test-clone-repo"
        repo_path = manager.create_repo(project, install_hooks=False)

        # Seed the repository with an initial commit
        # This is required for cloning to work properly
        with tempfile.TemporaryDirectory() as work_dir:
            work_path = Path(work_dir)

            # Clone the bare repo to a working directory
            subprocess.run(
                ["git", "clone", str(repo_path), str(work_path)],
                check=True,
                capture_output=True
            )

            # Configure git user
            subprocess.run(
                ["git", "-C", str(work_path), "config", "user.email", "test@test.com"],
                check=True
            )
            subprocess.run(
                ["git", "-C", str(work_path), "config", "user.name", "Test User"],
                check=True
            )

            # Create initial commit
            readme = work_path / "README.md"
            readme.write_text(f"# {project}\n\nTest repository")

            subprocess.run(
                ["git", "-C", str(work_path), "add", "README.md"],
                check=True
            )
            subprocess.run(
                ["git", "-C", str(work_path), "commit", "-m", "Initial commit"],
                check=True
            )
            subprocess.run(
                ["git", "-C", str(work_path), "push", "origin", "main"],
                check=True
            )

        yield manager

    def test_clone_repository_with_initial_commit(self, repo_manager_with_seed, temp_dirs):
        """Test cloning a repository with an initial commit."""
        project = "test-clone-repo"
        repo_path = temp_dirs["repos"] / f"{project}.git"
        clone_path = temp_dirs["clones"] / "clone-1"

        # Clone the repository
        result = subprocess.run(
            ["git", "clone", str(repo_path), str(clone_path)],
            capture_output=True,
            text=True
        )

        # Verify clone succeeded
        assert result.returncode == 0, f"Clone failed: {result.stderr}"
        assert clone_path.exists()
        assert (clone_path / ".git").exists()
        assert (clone_path / "README.md").exists()

        # Verify we're on main branch
        result = subprocess.run(
            ["git", "-C", str(clone_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True
        )
        assert result.stdout.strip() == "main"

    def test_clone_and_verify_commit_history(self, repo_manager_with_seed, temp_dirs):
        """Test that cloned repository has correct commit history."""
        project = "test-clone-repo"
        repo_path = temp_dirs["repos"] / f"{project}.git"
        clone_path = temp_dirs["clones"] / "clone-2"

        # Clone the repository
        subprocess.run(
            ["git", "clone", str(repo_path), str(clone_path)],
            check=True,
            capture_output=True
        )

        # Get commit log
        result = subprocess.run(
            ["git", "-C", str(clone_path), "log", "--oneline"],
            capture_output=True,
            text=True,
            check=True
        )

        # Verify initial commit exists
        assert "Initial commit" in result.stdout

    def test_multiple_clones_from_same_repo(self, repo_manager_with_seed, temp_dirs):
        """Test creating multiple clones from the same repository."""
        project = "test-clone-repo"
        repo_path = temp_dirs["repos"] / f"{project}.git"

        # Create multiple clones
        clone_paths = []
        for i in range(3):
            clone_path = temp_dirs["clones"] / f"clone-{i}"
            result = subprocess.run(
                ["git", "clone", str(repo_path), str(clone_path)],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0
            clone_paths.append(clone_path)

        # Verify all clones exist and are valid
        for clone_path in clone_paths:
            assert clone_path.exists()
            assert (clone_path / ".git").exists()
            assert (clone_path / "README.md").exists()


class TestRepositoryBranchSetup:
    """Test branch setup and configuration."""

    @pytest.fixture
    def repo_with_branches(self):
        """Create a repository with multiple branches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            repos_dir = base / "repos"
            repos_dir.mkdir()

            from config import GitConfig
            config = GitConfig(
                repos_path=str(repos_dir),
                ssh_keys_path=str(base / "keys"),
                git_user="git",
                enable_ssh=False
            )
            manager = RepoManager(config=config)

            # Create and seed repository
            project = "test-branches"
            repo_path = manager.create_repo(project, install_hooks=False)

            # Create initial commit and branches
            with tempfile.TemporaryDirectory() as work_dir:
                work_path = Path(work_dir)

                subprocess.run(
                    ["git", "clone", str(repo_path), str(work_path)],
                    check=True,
                    capture_output=True
                )

                subprocess.run(
                    ["git", "-C", str(work_path), "config", "user.email", "test@test.com"],
                    check=True
                )
                subprocess.run(
                    ["git", "-C", str(work_path), "config", "user.name", "Test User"],
                    check=True
                )

                # Initial commit
                (work_path / "file.txt").write_text("initial")
                subprocess.run(
                    ["git", "-C", str(work_path), "add", "."],
                    check=True
                )
                subprocess.run(
                    ["git", "-C", str(work_path), "commit", "-m", "Initial"],
                    check=True
                )
                subprocess.run(
                    ["git", "-C", str(work_path), "push", "origin", "main"],
                    check=True
                )

                # Create feature branches
                for branch in ["feature-1", "feature-2"]:
                    subprocess.run(
                        ["git", "-C", str(work_path), "checkout", "-b", branch],
                        check=True,
                        capture_output=True
                    )
                    (work_path / f"{branch}.txt").write_text(branch)
                    subprocess.run(
                        ["git", "-C", str(work_path), "add", "."],
                        check=True
                    )
                    subprocess.run(
                        ["git", "-C", str(work_path), "commit", "-m", f"Add {branch}"],
                        check=True
                    )
                    subprocess.run(
                        ["git", "-C", str(work_path), "push", "origin", branch],
                        check=True
                    )

            yield manager, project

    def test_list_branches(self, repo_with_branches):
        """Test listing branches in a repository."""
        manager, project = repo_with_branches

        branches = manager.get_branches(project)

        # Should have main and feature branches
        assert "main" in branches
        assert "feature-1" in branches
        assert "feature-2" in branches
        assert len(branches) == 3

    def test_get_branch_head(self, repo_with_branches):
        """Test getting HEAD commit of branches."""
        manager, project = repo_with_branches

        # Get HEAD of main branch
        main_head = manager.get_branch_head(project, "main")
        assert main_head is not None
        assert len(main_head) == 40  # SHA-1 hash length

        # Get HEAD of feature branch
        feature_head = manager.get_branch_head(project, "feature-1")
        assert feature_head is not None
        assert len(feature_head) == 40

    def test_clone_specific_branch(self, repo_with_branches):
        """Test cloning a specific branch."""
        manager, project = repo_with_branches

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "clone"
            repos_dir = Path(manager._config.repos_path)
            repo_path = repos_dir / f"{project}.git"

            # Clone feature-1 branch
            result = subprocess.run(
                ["git", "clone", "--branch", "feature-1", str(repo_path), str(clone_path)],
                capture_output=True,
                text=True
            )

            assert result.returncode == 0

            # Verify we're on feature-1 branch
            result = subprocess.run(
                ["git", "-C", str(clone_path), "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True
            )
            assert result.stdout.strip() == "feature-1"

            # Verify feature-1 specific file exists
            assert (clone_path / "feature-1.txt").exists()


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
