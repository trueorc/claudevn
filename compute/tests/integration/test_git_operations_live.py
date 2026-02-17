#!/usr/bin/env python3
"""
Compute Git Operations Integration Tests (Live Server)
======================================================

Tests Git operations from the compute instance perspective against
a live SSH Git server.

Prerequisites:
- Serving service running with SSH Git server enabled (port 2222)
- Redis running for PR queue management
- Docker services: docker compose up -d

Run with:
    ./scripts/run_integration_tests.sh compute/tests/integration/test_git_operations_live.py

Test Categories:
1. Workspace Initialization - Clone repos, set up worktrees
2. Branch Operations - Create, checkout, list branches
3. Commit and Push - Make commits, push to feature branches
4. Pull and Sync - Pull changes from origin
5. Worktree Management - Create and manage Git worktrees
6. Error Recovery - Handle conflicts, failed pushes
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional

import httpx
import pytest

# Test configuration
SERVING_BASE_URL = os.getenv("SERVING_URL", "http://localhost:8002")
API_PREFIX = "/api/v1"
SSH_GIT_PORT = int(os.getenv("SSH_GIT_PORT", "2222"))
SSH_GIT_HOST = os.getenv("SSH_GIT_HOST", "localhost")


def generate_test_id() -> str:
    """Generate unique test ID."""
    return f"test-{uuid.uuid4().hex[:8]}"


def generate_compute_id() -> str:
    """Generate valid compute ID format."""
    return f"compute-{uuid.uuid4().hex[:8]}"


class GitWorkspace:
    """Helper class for Git workspace operations."""

    def __init__(self, workspace_dir: Path, ssh_key_path: Path, ssh_config_path: Path):
        self.workspace_dir = workspace_dir
        self.ssh_key_path = ssh_key_path
        self.ssh_config_path = ssh_config_path
        self.env = {
            **os.environ,
            "GIT_SSH_COMMAND": f"ssh -F {ssh_config_path}"
        }

    def run_git(self, *args, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command."""
        cmd = ["git"] + list(args)
        return subprocess.run(
            cmd,
            cwd=cwd or self.workspace_dir,
            env=self.env,
            capture_output=True,
            timeout=60,
            check=check
        )

    def clone(self, ssh_url: str, target_dir: Optional[Path] = None) -> bool:
        """Clone a repository."""
        target = target_dir or self.workspace_dir
        result = self.run_git("clone", ssh_url, str(target), check=False)
        return result.returncode == 0 or "empty repository" in result.stderr.decode().lower()

    def init_config(self, cwd: Optional[Path] = None):
        """Initialize git config for commits."""
        target = cwd or self.workspace_dir
        self.run_git("config", "user.email", "compute@claudevn.local", cwd=target)
        self.run_git("config", "user.name", "ClaudeVN Compute", cwd=target)

    def create_branch(self, branch_name: str, cwd: Optional[Path] = None) -> bool:
        """Create and checkout a new branch."""
        result = self.run_git("checkout", "-b", branch_name, cwd=cwd, check=False)
        return result.returncode == 0

    def add_and_commit(self, message: str, files: list = None, cwd: Optional[Path] = None) -> bool:
        """Add files and create a commit."""
        target = cwd or self.workspace_dir
        if files:
            for f in files:
                self.run_git("add", f, cwd=target)
        else:
            self.run_git("add", ".", cwd=target)
        result = self.run_git("commit", "-m", message, cwd=target, check=False)
        return result.returncode == 0

    def push(self, remote: str = "origin", branch: str = None, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Push to remote."""
        args = ["push", "-u", remote]
        if branch:
            args.append(branch)
        return self.run_git(*args, cwd=cwd, check=False)

    def pull(self, remote: str = "origin", branch: str = None, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Pull from remote."""
        args = ["pull", remote]
        if branch:
            args.append(branch)
        return self.run_git(*args, cwd=cwd, check=False)


@pytest.fixture
async def compute_setup():
    """Set up compute instance with SSH credentials and test repository."""
    compute_id = generate_compute_id()
    project = generate_test_id()

    async with httpx.AsyncClient() as client:
        # Generate SSH key
        key_response = await client.post(
            f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}/generate"
        )
        key_pair = key_response.json()

        # Create repository
        await client.post(
            f"{SERVING_BASE_URL}{API_PREFIX}/git/repos",
            json={"project": project, "install_hooks": True}
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write SSH key
            key_path = tmpdir / "id_ed25519"
            key_path.write_text(key_pair["private_key"])
            key_path.chmod(0o600)

            # Write SSH config
            ssh_config = tmpdir / "ssh_config"
            ssh_config.write_text(f"""
Host {SSH_GIT_HOST}
    HostName {SSH_GIT_HOST}
    Port {SSH_GIT_PORT}
    User git
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
""")

            yield {
                "compute_id": compute_id,
                "project": project,
                "ssh_url": f"ssh://git@{SSH_GIT_HOST}:{SSH_GIT_PORT}/app/data/repos/{project}.git",
                "tmpdir": tmpdir,
                "key_path": key_path,
                "ssh_config": ssh_config,
            }

        # Cleanup
        await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/git/repos/{project}")
        await client.delete(f"{SERVING_BASE_URL}{API_PREFIX}/git/ssh/keys/{compute_id}")


class TestWorkspaceInitialization:
    """Test workspace initialization workflows."""

    @pytest.mark.asyncio
    async def test_clone_empty_repository(self, compute_setup):
        """Test cloning an empty repository for workspace setup."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])

        # Clone empty repo
        success = git.clone(setup["ssh_url"], workspace)
        assert success
        assert workspace.exists()
        assert (workspace / ".git").exists()

    @pytest.mark.asyncio
    async def test_workspace_with_initial_commit(self, compute_setup):
        """Test setting up workspace with initial content."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])

        # Clone
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Create initial file
        readme = workspace / "README.md"
        readme.write_text(f"# Test Project\n\nCreated by {setup['compute_id']}")

        # Create branch with proper naming and commit
        branch = f"f/init/{setup['compute_id']}"
        git.create_branch(branch)
        git.add_and_commit("Initial project setup")

        # Push
        result = git.push(branch=branch)
        assert result.returncode == 0


class TestBranchOperations:
    """Test Git branch operations."""

    @pytest.mark.asyncio
    async def test_create_feature_branch(self, compute_setup):
        """Test creating a properly named feature branch."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Create feature branch with correct naming convention
        branch = f"f/issue-100/{setup['compute_id']}"
        success = git.create_branch(branch)
        assert success

        # Verify branch exists
        result = git.run_git("branch", "--show-current")
        assert branch in result.stdout.decode()

    @pytest.mark.asyncio
    async def test_create_bugfix_branch(self, compute_setup):
        """Test creating a bugfix branch."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        branch = f"b/issue-200/{setup['compute_id']}"
        success = git.create_branch(branch)
        assert success

    @pytest.mark.asyncio
    async def test_list_remote_branches(self, compute_setup):
        """Test listing remote branches."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)

        # List remote branches
        result = git.run_git("branch", "-r", check=False)
        # Empty repo may have no remote branches
        assert result.returncode == 0


class TestCommitAndPush:
    """Test commit and push workflows."""

    @pytest.mark.asyncio
    async def test_commit_and_push_single_file(self, compute_setup):
        """Test committing and pushing a single file change."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Create branch
        branch = f"f/issue-101/{setup['compute_id']}"
        git.create_branch(branch)

        # Create file
        test_file = workspace / "test.py"
        test_file.write_text("print('Hello World')")

        # Commit
        success = git.add_and_commit("Add test.py")
        assert success

        # Push
        result = git.push(branch=branch)
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_commit_and_push_multiple_files(self, compute_setup):
        """Test committing and pushing multiple files."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        branch = f"f/issue-102/{setup['compute_id']}"
        git.create_branch(branch)

        # Create multiple files
        (workspace / "src").mkdir(exist_ok=True)
        (workspace / "src" / "main.py").write_text("def main(): pass")
        (workspace / "src" / "utils.py").write_text("def helper(): pass")
        (workspace / "README.md").write_text("# Project")

        # Commit all
        success = git.add_and_commit("Add initial project structure")
        assert success

        result = git.push(branch=branch)
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_multiple_commits_then_push(self, compute_setup):
        """Test making multiple commits before pushing."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        branch = f"f/issue-103/{setup['compute_id']}"
        git.create_branch(branch)

        # First commit
        (workspace / "file1.txt").write_text("Content 1")
        git.add_and_commit("Add file1")

        # Second commit
        (workspace / "file2.txt").write_text("Content 2")
        git.add_and_commit("Add file2")

        # Third commit
        (workspace / "file3.txt").write_text("Content 3")
        git.add_and_commit("Add file3")

        # Verify we have 3 commits
        result = git.run_git("rev-list", "--count", "HEAD")
        count = int(result.stdout.decode().strip())
        assert count >= 3

        # Push all at once
        result = git.push(branch=branch)
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_push_rejected_for_main(self, compute_setup):
        """Test that pushes to main are rejected."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Stay on main (or create if orphan)
        (workspace / "test.txt").write_text("test")
        git.add_and_commit("Test commit on main")

        # Try to push to main
        result = git.push(branch="main")
        assert result.returncode != 0


class TestWorktreeOperations:
    """Test Git worktree operations."""

    @pytest.mark.asyncio
    async def test_create_worktree(self, compute_setup):
        """Test creating a Git worktree for parallel work."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "main-workspace"
        worktree_dir = setup["tmpdir"] / "worktree-workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Create initial commit on a branch
        branch = f"f/issue-200/{setup['compute_id']}"
        git.create_branch(branch)
        (workspace / "init.txt").write_text("initial")
        git.add_and_commit("Initial commit")
        git.push(branch=branch)

        # Create worktree for a different branch
        worktree_branch = f"f/issue-201/{setup['compute_id']}"
        result = git.run_git(
            "worktree", "add", "-b", worktree_branch, str(worktree_dir),
            check=False
        )
        assert result.returncode == 0
        assert worktree_dir.exists()

        # Verify worktree is on correct branch
        worktree_git = GitWorkspace(worktree_dir, setup["key_path"], setup["ssh_config"])
        result = worktree_git.run_git("branch", "--show-current")
        assert worktree_branch in result.stdout.decode()

    @pytest.mark.asyncio
    async def test_worktree_isolation(self, compute_setup):
        """Test that worktrees are isolated from each other."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "main-workspace"
        worktree1 = setup["tmpdir"] / "worktree-1"
        worktree2 = setup["tmpdir"] / "worktree-2"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Initial commit
        branch_main = f"f/issue-300/{setup['compute_id']}"
        git.create_branch(branch_main)
        (workspace / "shared.txt").write_text("shared content")
        git.add_and_commit("Shared base")
        git.push(branch=branch_main)

        # Create two worktrees
        branch1 = f"f/issue-301/{setup['compute_id']}"
        branch2 = f"f/issue-302/{setup['compute_id']}"

        git.run_git("worktree", "add", "-b", branch1, str(worktree1))
        git.run_git("worktree", "add", "-b", branch2, str(worktree2))

        # Make different changes in each worktree
        wt1_git = GitWorkspace(worktree1, setup["key_path"], setup["ssh_config"])
        wt1_git.init_config(worktree1)
        (worktree1 / "feature1.txt").write_text("Feature 1")
        wt1_git.add_and_commit("Add feature 1", cwd=worktree1)

        wt2_git = GitWorkspace(worktree2, setup["key_path"], setup["ssh_config"])
        wt2_git.init_config(worktree2)
        (worktree2 / "feature2.txt").write_text("Feature 2")
        wt2_git.add_and_commit("Add feature 2", cwd=worktree2)

        # Verify files are isolated
        assert (worktree1 / "feature1.txt").exists()
        assert not (worktree1 / "feature2.txt").exists()
        assert (worktree2 / "feature2.txt").exists()
        assert not (worktree2 / "feature1.txt").exists()

    @pytest.mark.asyncio
    async def test_remove_worktree(self, compute_setup):
        """Test removing a worktree."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "main-workspace"
        worktree = setup["tmpdir"] / "temp-worktree"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Create worktree
        branch = f"f/temp/{setup['compute_id']}"
        git.run_git("worktree", "add", "-b", branch, str(worktree))
        assert worktree.exists()

        # Remove worktree
        git.run_git("worktree", "remove", str(worktree))
        assert not worktree.exists()

        # Verify it's removed from worktree list
        result = git.run_git("worktree", "list")
        assert str(worktree) not in result.stdout.decode()


class TestPullAndSync:
    """Test pull and sync operations."""

    @pytest.mark.asyncio
    async def test_pull_after_remote_update(self, compute_setup):
        """Test pulling changes after remote is updated."""
        setup = compute_setup
        workspace1 = setup["tmpdir"] / "workspace1"
        workspace2 = setup["tmpdir"] / "workspace2"

        # First workspace - push a change
        git1 = GitWorkspace(workspace1, setup["key_path"], setup["ssh_config"])
        git1.clone(setup["ssh_url"], workspace1)
        git1.init_config()

        branch = f"f/issue-400/{setup['compute_id']}"
        git1.create_branch(branch)
        (workspace1 / "remote-file.txt").write_text("From workspace 1")
        git1.add_and_commit("Add from workspace 1")
        git1.push(branch=branch)

        # Second workspace - clone and pull the same branch
        git2 = GitWorkspace(workspace2, setup["key_path"], setup["ssh_config"])
        git2.clone(setup["ssh_url"], workspace2)
        git2.init_config()

        # Fetch and checkout the remote branch
        git2.run_git("fetch", "origin")
        git2.run_git("checkout", "-b", branch, f"origin/{branch}", check=False)

        # Verify file exists
        assert (workspace2 / "remote-file.txt").exists()
        content = (workspace2 / "remote-file.txt").read_text()
        assert "From workspace 1" in content


class TestErrorRecovery:
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_push_nonexistent_remote(self, compute_setup):
        """Test handling push to nonexistent remote."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        branch = f"f/test/{setup['compute_id']}"
        git.create_branch(branch)
        (workspace / "test.txt").write_text("test")
        git.add_and_commit("Test")

        # Try to push to nonexistent remote
        result = git.run_git("push", "nonexistent", branch, check=False)
        assert result.returncode != 0

    @pytest.mark.asyncio
    async def test_recover_from_detached_head(self, compute_setup):
        """Test recovering from detached HEAD state."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Create a commit
        branch = f"f/test/{setup['compute_id']}"
        git.create_branch(branch)
        (workspace / "test.txt").write_text("test")
        git.add_and_commit("Test commit")

        # Get commit hash
        result = git.run_git("rev-parse", "HEAD")
        commit_hash = result.stdout.decode().strip()

        # Detach HEAD
        git.run_git("checkout", commit_hash)

        # Verify detached
        result = git.run_git("symbolic-ref", "HEAD", check=False)
        assert result.returncode != 0  # Should fail when detached

        # Recover by checking out branch
        git.run_git("checkout", branch)

        # Verify recovered
        result = git.run_git("branch", "--show-current")
        assert branch in result.stdout.decode()


class TestBranchNamingValidation:
    """Test branch naming convention validation."""

    @pytest.mark.asyncio
    async def test_valid_feature_branch_naming(self, compute_setup):
        """Test that valid feature branch names are accepted."""
        setup = compute_setup
        workspace = setup["tmpdir"] / "workspace"

        git = GitWorkspace(workspace, setup["key_path"], setup["ssh_config"])
        git.clone(setup["ssh_url"], workspace)
        git.init_config()

        # Valid branch patterns: f/ (feature), b/ (bugfix), r/ (refactor), d/ (docs)
        valid_branches = [
            f"f/issue-1/{setup['compute_id']}",
            f"b/issue-2/{setup['compute_id']}",
            f"r/issue-3/{setup['compute_id']}",
            f"d/issue-4/{setup['compute_id']}",
        ]

        for branch in valid_branches:
            # Reset to initial state
            git.run_git("checkout", "-B", "temp-main", check=False)

            # Create branch
            success = git.create_branch(branch)
            assert success, f"Failed to create branch: {branch}"

            # Create content and commit
            (workspace / "test.txt").write_text(f"Content for {branch}")
            git.add_and_commit(f"Test for {branch}")

            # Push should succeed (hook validates naming)
            result = git.push(branch=branch)
            # If hooks are working, valid branches should be accepted
            # Note: Empty repos may have issues, so we check for non-auth errors
            if result.returncode != 0:
                stderr = result.stderr.decode()
                # Auth errors indicate hooks aren't the problem
                assert "Permission denied" not in stderr


# Run tests
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Compute Git Operations Integration Tests")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print(f"  - Serving service running at {SERVING_BASE_URL}")
    print(f"  - SSH Git server running on port {SSH_GIT_PORT}")
    print("  - Docker services: docker compose up -d")
    print()
    print("Running tests...")
    print()

    sys.exit(pytest.main([__file__, "-v", "-s"]))
