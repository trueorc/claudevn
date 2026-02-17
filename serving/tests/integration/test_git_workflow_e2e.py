"""
End-to-End Git Workflow Integration Tests
==========================================

Tier-2 integration tests that validate the complete compute git workflow:
  clone → branch → work → push → PR → merge → cleanup

These tests exercise real Git operations against local bare repositories
with hooks installed, validating the full lifecycle without requiring
Docker, SSH, or Redis. PR service operations use mocked Redis.

Test Scenarios:
1. Happy path: Full clone→branch→push→merge cycle
2. Pre-receive hook rejects push to main
3. Pre-receive hook rejects invalid branch names
4. Pre-receive hook rejects wrong compute pushing to another's branch
5. Merge conflict detection and reporting
6. Branch cleanup after successful merge

Known Gaps (#830 — these require Docker-level tests):
- All git ops run as the same OS user (no root→compute ownership transition)
- Uses local file paths, not SSH transport (ssh://git@serving:2222/...)
- No 'su' shell boundary or env var propagation testing
- See compute/tests/unit/test_claude_code_spawner.py::TestGitOpsRunAsCurrentUser
  for unit-level coverage of user context and SSH transport.

Prerequisites:
- Python test environment with pytest
- Git CLI installed
- No Docker, Redis, or SSH required

Run with:
    pytest serving/tests/integration/test_git_workflow_e2e.py -v

Or use the integration test script:
    ./scripts/run_integration_tests.sh -s serving/tests/integration/test_git_workflow_e2e.py
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from config import GitConfig
from git.pr_service import PRService, PRStatus
from git.repo_manager import RepoManager


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def workspace():
    """Create a temporary workspace with repos and clones directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        dirs = {
            "base": base,
            "repos": base / "repos",
            "clones": base / "clones",
            "keys": base / "keys",
        }
        for d in dirs.values():
            d.mkdir(exist_ok=True)
        yield dirs


@pytest.fixture
def repo_manager(workspace):
    """Create RepoManager with temporary repos path and hooks enabled."""
    config = GitConfig(
        repos_path=str(workspace["repos"]),
        ssh_keys_path=str(workspace["keys"]),
        git_user="git",
        enable_ssh=False,
    )
    return RepoManager(config=config)


@pytest.fixture
def seeded_repo(repo_manager, workspace):
    """Create a bare repo with hooks installed and an initial content commit.

    Returns (project_name, bare_repo_path).
    """
    project = "test-e2e-project"
    repo_path = repo_manager.create_repo(project, install_hooks=True)

    # Add a real content file beyond the empty initial commit
    with tempfile.TemporaryDirectory() as work_dir:
        _git(work_dir, "clone", str(repo_path), work_dir)
        _git_config(work_dir)
        (Path(work_dir) / "README.md").write_text("# E2E Test Project\n")
        _git(work_dir, "add", "README.md")
        _git(work_dir, "commit", "-m", "Add README")
        # Push with CLAUDEVN_ALLOW_MAIN_PUSH=true since hooks are installed
        _git(work_dir, "push", "origin", "main",
             env_extra={"CLAUDEVN_ALLOW_MAIN_PUSH": "true"})

    return project, repo_path


@pytest.fixture
def compute_clone(seeded_repo, workspace):
    """Clone the seeded repo as a compute instance would.

    Returns (clone_path, project, bare_repo_path, compute_id).
    """
    project, repo_path = seeded_repo
    compute_id = "compute-001"
    clone_path = workspace["clones"] / compute_id

    _git(str(clone_path), "clone", str(repo_path), str(clone_path))
    _git_config(str(clone_path))

    return clone_path, project, repo_path, compute_id


@pytest.fixture
def allow_main_push():
    """Set CLAUDEVN_ALLOW_MAIN_PUSH=true to simulate serving merging to main.

    In production, the serving process sets this env var so the pre-receive
    hook allows its push to main after merge.
    """
    os.environ["CLAUDEVN_ALLOW_MAIN_PUSH"] = "true"
    yield
    os.environ.pop("CLAUDEVN_ALLOW_MAIN_PUSH", None)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for PR service tests."""
    redis = AsyncMock()
    redis.get_branch_status = AsyncMock(return_value=None)
    redis.set_branch_status = AsyncMock()
    redis.add_to_pr_queue = AsyncMock(return_value=1)
    redis.remove_from_pr_queue = AsyncMock()
    redis.track_compute_branch = AsyncMock()
    redis.untrack_compute_branch = AsyncMock()
    redis.publish_git_event = AsyncMock()
    redis.get_pr_queue_position = AsyncMock(return_value=1)
    redis.add_to_merge_queue = AsyncMock()
    redis.pop_merge_queue = AsyncMock(return_value=None)
    redis.get_compute_branches = AsyncMock(return_value=[])
    return redis


# =============================================================================
# Helper Functions
# =============================================================================


def _git(work_dir: str, *args, env_extra: dict = None, check: bool = True):
    """Run a git command in the given directory.

    Returns subprocess.CompletedProcess.
    """
    cmd = ["git"]
    # If the first arg is a subcommand (not a path), add -C
    if args and args[0] != "clone":
        cmd.extend(["-C", str(work_dir)])
    cmd.extend(args)

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)


def _git_config(work_dir: str):
    """Set up minimal git config for commits."""
    _git(work_dir, "config", "user.email", "test@claudevn.test")
    _git(work_dir, "config", "user.name", "E2E Test")


# =============================================================================
# Test: Happy Path - Full Workflow
# =============================================================================


class TestGitWorkflowHappyPath:
    """Test the full clone → branch → work → push → merge cycle."""

    def test_clone_has_initial_content(self, compute_clone):
        """Verify compute clone has the seeded content."""
        clone_path, project, repo_path, compute_id = compute_clone

        assert (clone_path / "README.md").exists()
        assert "E2E Test Project" in (clone_path / "README.md").read_text()

        # Verify on main branch
        result = _git(str(clone_path), "branch", "--show-current")
        assert result.stdout.strip() == "main"

    def test_create_feature_branch_with_valid_naming(self, compute_clone):
        """Compute creates a feature branch with valid naming convention."""
        clone_path, project, repo_path, compute_id = compute_clone
        branch = f"f/issue_abc123/{compute_id}"

        _git(str(clone_path), "checkout", "-b", branch)

        result = _git(str(clone_path), "branch", "--show-current")
        assert result.stdout.strip() == branch

    def test_push_feature_branch_accepted(self, compute_clone):
        """Push a feature branch with valid naming - hook accepts it."""
        clone_path, project, repo_path, compute_id = compute_clone
        branch = f"f/issue_abc123/{compute_id}"

        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "feature.py").write_text("# New feature\n")
        _git(str(clone_path), "add", "feature.py")
        _git(str(clone_path), "commit", "-m", "Add feature")
        _git(str(clone_path), "push", "origin", branch)

        # Verify branch exists in bare repo
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--list", "--format=%(refname:short)"],
            capture_output=True, text=True, check=True,
        )
        branches = result.stdout.strip().split("\n")
        assert branch in branches

    @pytest.mark.asyncio
    async def test_full_clone_branch_push_merge_cycle(self, compute_clone, repo_manager, mock_redis, allow_main_push):
        """Full e2e: clone → branch → commit → push → PR create → approve → merge → cleanup."""
        clone_path, project, repo_path, compute_id = compute_clone
        branch = f"f/issue_def456/{compute_id}"

        # 1. Create feature branch
        _git(str(clone_path), "checkout", "-b", branch)

        # 2. Do work
        (clone_path / "new_feature.py").write_text("def hello():\n    return 'world'\n")
        _git(str(clone_path), "add", "new_feature.py")
        _git(str(clone_path), "commit", "-m", "Add new feature")

        # 3. Push to bare repo
        _git(str(clone_path), "push", "origin", branch)

        # Verify branch HEAD in bare repo
        branch_head = repo_manager.get_branch_head(project, branch)
        assert branch_head is not None
        assert len(branch_head) == 40

        # 4. Create PR (mocked Redis, real repo)
        mock_redis.get_branch_status.return_value = None  # No existing PR

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(repo_manager._repos_path)
            pr_service = PRService(
                redis_client=mock_redis,
                repo_manager=repo_manager,
                sse_manager=AsyncMock(),
            )

        # Dry-run merge should succeed (no conflicts)
        dry_run = await pr_service.dry_run_merge(project, branch)
        assert dry_run["can_merge"] is True
        assert dry_run["conflicting_files"] == []

        # 5. Simulate approve + merge
        # Set up Redis mock for approved PR
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-456",
            "title": f"Merge {branch}",
            "head_commit": branch_head,
            "base_branch": "main",
        }

        merge_result = await pr_service.merge(project, branch, delete_branch=True)

        assert merge_result["success"] is True
        assert merge_result["merged_commit"] is not None
        assert len(merge_result["merged_commit"]) == 40
        assert merge_result["deleted"] is True

        # 6. Verify merge: main now contains the feature file
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "new_feature.py").exists()
            content = (Path(verify_dir) / "new_feature.py").read_text()
            assert "def hello():" in content

        # 7. Verify branch was deleted from bare repo
        remaining_branches = repo_manager.get_branches(project)
        assert branch not in remaining_branches
        assert "main" in remaining_branches

    @pytest.mark.asyncio
    async def test_multiple_sequential_merges(self, compute_clone, repo_manager, mock_redis, allow_main_push):
        """Two feature branches merged sequentially - both land on main."""
        clone_path, project, repo_path, compute_id = compute_clone

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(repo_manager._repos_path)
            pr_service = PRService(
                redis_client=mock_redis,
                repo_manager=repo_manager,
                sse_manager=AsyncMock(),
            )

        for i, filename in enumerate(["alpha.py", "beta.py"]):
            branch = f"f/issue_{i:06x}/{compute_id}"

            # Create branch from latest main
            _git(str(clone_path), "checkout", "main")
            _git(str(clone_path), "pull", "origin", "main")
            _git(str(clone_path), "checkout", "-b", branch)

            # Write, commit, push
            (clone_path / filename).write_text(f"# {filename}\n")
            _git(str(clone_path), "add", filename)
            _git(str(clone_path), "commit", "-m", f"Add {filename}")
            _git(str(clone_path), "push", "origin", branch)

            # Mock approved PR and merge
            head = repo_manager.get_branch_head(project, branch)
            mock_redis.get_branch_status.return_value = {
                "status": "approved",
                "compute_id": compute_id,
                "task_id": f"issue-{i}",
                "title": f"Merge {branch}",
                "head_commit": head,
                "base_branch": "main",
            }

            result = await pr_service.merge(project, branch, delete_branch=True)
            assert result["success"] is True

        # Verify both files on main
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "alpha.py").exists()
            assert (Path(verify_dir) / "beta.py").exists()


# =============================================================================
# Test: Pre-Receive Hook Rejections
# =============================================================================


class TestPreReceiveHookRejections:
    """Test that pre-receive hook rejects invalid pushes."""

    def test_push_to_main_rejected(self, compute_clone):
        """Direct push to main is rejected by pre-receive hook."""
        clone_path, project, repo_path, compute_id = compute_clone

        (clone_path / "unauthorized.py").write_text("# should not land\n")
        _git(str(clone_path), "add", "unauthorized.py")
        _git(str(clone_path), "commit", "-m", "Try to push to main")

        result = _git(str(clone_path), "push", "origin", "main", check=False)

        assert result.returncode != 0
        assert "FORBIDDEN" in result.stderr or "ERROR" in result.stderr

    def test_invalid_branch_name_rejected(self, compute_clone):
        """Push with invalid branch naming is rejected."""
        clone_path, project, repo_path, compute_id = compute_clone

        # Invalid: no compute ID suffix, wrong format
        bad_branch = "my-feature-branch"
        _git(str(clone_path), "checkout", "-b", bad_branch)
        (clone_path / "bad.py").write_text("# invalid branch name\n")
        _git(str(clone_path), "add", "bad.py")
        _git(str(clone_path), "commit", "-m", "Bad branch name")

        result = _git(str(clone_path), "push", "origin", bad_branch, check=False)

        assert result.returncode != 0
        assert "Invalid branch name" in result.stderr or "ERROR" in result.stderr

    def test_missing_type_prefix_rejected(self, compute_clone):
        """Branch without valid type prefix is rejected."""
        clone_path, project, repo_path, compute_id = compute_clone

        bad_branch = f"feature/issue_abc123/{compute_id}"  # 'feature' not in [f,b,r,d,t]
        _git(str(clone_path), "checkout", "-b", bad_branch)
        (clone_path / "bad2.py").write_text("# wrong prefix\n")
        _git(str(clone_path), "add", "bad2.py")
        _git(str(clone_path), "commit", "-m", "Wrong prefix")

        result = _git(str(clone_path), "push", "origin", bad_branch, check=False)

        assert result.returncode != 0
        assert "ERROR" in result.stderr

    def test_missing_compute_id_rejected(self, compute_clone):
        """Branch without compute ID suffix is rejected."""
        clone_path, project, repo_path, compute_id = compute_clone

        bad_branch = "f/issue_abc123"  # No compute ID
        _git(str(clone_path), "checkout", "-b", bad_branch)
        (clone_path / "bad3.py").write_text("# no compute id\n")
        _git(str(clone_path), "add", "bad3.py")
        _git(str(clone_path), "commit", "-m", "No compute ID")

        result = _git(str(clone_path), "push", "origin", bad_branch, check=False)

        assert result.returncode != 0
        assert "ERROR" in result.stderr

    def test_wrong_compute_id_rejected(self, compute_clone):
        """Compute instance cannot push to another compute's branch."""
        clone_path, project, repo_path, compute_id = compute_clone

        # Branch belongs to compute-999, but GIT_PUSH_COMPUTE_ID is compute-001
        other_branch = "f/issue_abc123/compute-999"
        _git(str(clone_path), "checkout", "-b", other_branch)
        (clone_path / "stolen.py").write_text("# impersonation\n")
        _git(str(clone_path), "add", "stolen.py")
        _git(str(clone_path), "commit", "-m", "Impersonate other compute")

        result = _git(
            str(clone_path), "push", "origin", other_branch,
            env_extra={"GIT_PUSH_COMPUTE_ID": compute_id},
            check=False,
        )

        assert result.returncode != 0
        assert "cannot push" in result.stderr or "ERROR" in result.stderr

    def test_all_valid_type_prefixes_accepted(self, compute_clone):
        """All valid type prefixes (f, b, r, d, t) are accepted."""
        clone_path, project, repo_path, compute_id = compute_clone

        for prefix, label in [("f", "feature"), ("b", "bugfix"), ("r", "refactor"),
                               ("d", "docs"), ("t", "test")]:
            branch = f"{prefix}/issue_{label}/{compute_id}"
            _git(str(clone_path), "checkout", "-b", branch, check=True)
            (clone_path / f"{label}.py").write_text(f"# {label}\n")
            _git(str(clone_path), "add", f"{label}.py")
            _git(str(clone_path), "commit", "-m", f"Add {label}")
            result = _git(str(clone_path), "push", "origin", branch, check=False)
            assert result.returncode == 0, (
                f"Type prefix '{prefix}' should be accepted but was rejected: {result.stderr}"
            )
            # Go back to main for next iteration
            _git(str(clone_path), "checkout", "main")


# =============================================================================
# Test: Merge Conflict Detection
# =============================================================================


class TestMergeConflictDetection:
    """Test conflict detection during PR merge workflow."""

    @pytest.mark.asyncio
    async def test_dry_run_detects_conflict(self, compute_clone, repo_manager, mock_redis, allow_main_push):
        """Dry-run merge detects conflicting changes to the same file."""
        clone_path, project, repo_path, compute_id = compute_clone

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(repo_manager._repos_path)
            pr_service = PRService(
                redis_client=mock_redis,
                repo_manager=repo_manager,
                sse_manager=AsyncMock(),
            )

        # Create feature branch with a change to README
        branch = f"f/issue_conflict1/{compute_id}"
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "README.md").write_text("# Changed by feature branch\n")
        _git(str(clone_path), "add", "README.md")
        _git(str(clone_path), "commit", "-m", "Feature changes README")
        _git(str(clone_path), "push", "origin", branch)

        # Meanwhile, create a conflicting change on main
        with tempfile.TemporaryDirectory() as other_dir:
            _git(other_dir, "clone", str(repo_path), other_dir)
            _git_config(other_dir)
            (Path(other_dir) / "README.md").write_text("# Changed by main\n")
            _git(other_dir, "add", "README.md")
            _git(other_dir, "commit", "-m", "Main changes README")
            _git(other_dir, "push", "origin", "main",
                 env_extra={"CLAUDEVN_ALLOW_MAIN_PUSH": "true"})

        # Dry-run merge should detect the conflict
        result = await pr_service.dry_run_merge(project, branch)

        assert result["can_merge"] is False
        assert len(result["conflicting_files"]) > 0
        assert "README.md" in result["conflicting_files"]

    @pytest.mark.asyncio
    async def test_merge_returns_conflict_result(self, compute_clone, repo_manager, mock_redis, allow_main_push):
        """Actual merge returns conflict details when conflicting."""
        clone_path, project, repo_path, compute_id = compute_clone

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(repo_manager._repos_path)
            pr_service = PRService(
                redis_client=mock_redis,
                repo_manager=repo_manager,
                sse_manager=AsyncMock(),
            )

        # Create conflicting branches
        branch = f"f/issue_conflict2/{compute_id}"
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "README.md").write_text("# Feature version\nLine 2\n")
        _git(str(clone_path), "add", "README.md")
        _git(str(clone_path), "commit", "-m", "Feature modifies README")
        _git(str(clone_path), "push", "origin", branch)

        # Conflicting main change
        with tempfile.TemporaryDirectory() as other_dir:
            _git(other_dir, "clone", str(repo_path), other_dir)
            _git_config(other_dir)
            (Path(other_dir) / "README.md").write_text("# Main version\nDifferent line 2\n")
            _git(other_dir, "add", "README.md")
            _git(other_dir, "commit", "-m", "Main modifies README differently")
            _git(other_dir, "push", "origin", "main",
                 env_extra={"CLAUDEVN_ALLOW_MAIN_PUSH": "true"})

        # Mock approved PR
        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-conflict",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "main",
        }

        result = await pr_service.merge(project, branch, delete_branch=False)

        assert result["success"] is False
        assert result["reason"] == "conflict"
        assert "README.md" in result["conflicts"]

        # Branch should still exist (not deleted on conflict)
        branches = repo_manager.get_branches(project)
        assert branch in branches

    @pytest.mark.asyncio
    async def test_non_conflicting_parallel_changes_merge_cleanly(
        self, compute_clone, repo_manager, mock_redis, allow_main_push
    ):
        """Non-overlapping changes to different files merge without conflict."""
        clone_path, project, repo_path, compute_id = compute_clone

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = str(repo_manager._repos_path)
            pr_service = PRService(
                redis_client=mock_redis,
                repo_manager=repo_manager,
                sse_manager=AsyncMock(),
            )

        # Feature branch adds a new file
        branch = f"f/issue_noconflict/{compute_id}"
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "new_module.py").write_text("# New module\n")
        _git(str(clone_path), "add", "new_module.py")
        _git(str(clone_path), "commit", "-m", "Add new module")
        _git(str(clone_path), "push", "origin", branch)

        # Main adds a different file
        with tempfile.TemporaryDirectory() as other_dir:
            _git(other_dir, "clone", str(repo_path), other_dir)
            _git_config(other_dir)
            (Path(other_dir) / "other_file.py").write_text("# Other file\n")
            _git(other_dir, "add", "other_file.py")
            _git(other_dir, "commit", "-m", "Add other file to main")
            _git(other_dir, "push", "origin", "main",
                 env_extra={"CLAUDEVN_ALLOW_MAIN_PUSH": "true"})

        # Dry-run should show no conflicts
        dry_run = await pr_service.dry_run_merge(project, branch)
        assert dry_run["can_merge"] is True

        # Actual merge should succeed
        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-noconflict",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "main",
        }

        result = await pr_service.merge(project, branch, delete_branch=True)

        assert result["success"] is True

        # Verify both files exist on main
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "new_module.py").exists()
            assert (Path(verify_dir) / "other_file.py").exists()


# =============================================================================
# Test: Hook Installation and Verification
# =============================================================================


class TestHookInstallation:
    """Test that hooks are properly installed and executable."""

    def test_hooks_installed_on_repo_creation(self, seeded_repo, repo_manager):
        """Verify hooks are installed when repo is created with install_hooks=True."""
        project, repo_path = seeded_repo

        status = repo_manager.verify_hooks(project)

        assert status["hooks_installed"] is True
        assert status["pre_receive"]["exists"] is True
        assert status["pre_receive"]["executable"] is True
        assert status["post_receive"]["exists"] is True
        assert status["post_receive"]["executable"] is True

    def test_pre_receive_hook_is_bash_script(self, seeded_repo):
        """Verify pre-receive hook starts with bash shebang."""
        project, repo_path = seeded_repo
        hook_path = repo_path / "hooks" / "pre-receive"

        content = hook_path.read_text()
        assert content.startswith("#!/bin/bash")


# =============================================================================
# Test: Branch Lifecycle
# =============================================================================


class TestBranchLifecycle:
    """Test branch creation, listing, and deletion."""

    def test_feature_branch_appears_in_bare_repo(self, compute_clone, repo_manager):
        """After push, feature branch is visible in bare repo."""
        clone_path, project, repo_path, compute_id = compute_clone
        branch = f"f/issue_lifecycle/{compute_id}"

        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "lifecycle.py").write_text("# lifecycle test\n")
        _git(str(clone_path), "add", "lifecycle.py")
        _git(str(clone_path), "commit", "-m", "Lifecycle test")
        _git(str(clone_path), "push", "origin", branch)

        branches = repo_manager.get_branches(project)
        assert branch in branches
        assert "main" in branches

    def test_branch_deletion_after_merge(self, compute_clone, repo_manager):
        """Branch can be deleted after it's no longer needed."""
        clone_path, project, repo_path, compute_id = compute_clone
        branch = f"f/issue_delete/{compute_id}"

        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "deleteme.py").write_text("# will be deleted\n")
        _git(str(clone_path), "add", "deleteme.py")
        _git(str(clone_path), "commit", "-m", "Branch to delete")
        _git(str(clone_path), "push", "origin", branch)

        assert branch in repo_manager.get_branches(project)

        # Delete the branch
        deleted = repo_manager.delete_branch(project, branch)
        assert deleted is True
        assert branch not in repo_manager.get_branches(project)

    def test_cannot_delete_main_branch(self, seeded_repo, repo_manager):
        """Protected branch (main) cannot be deleted."""
        project, repo_path = seeded_repo

        with pytest.raises(ValueError, match="protected branch"):
            repo_manager.delete_branch(project, "main")

    def test_branch_head_matches_push(self, compute_clone, repo_manager):
        """Branch HEAD in bare repo matches the commit that was pushed."""
        clone_path, project, repo_path, compute_id = compute_clone
        branch = f"f/issue_head/{compute_id}"

        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "head_test.py").write_text("# head check\n")
        _git(str(clone_path), "add", "head_test.py")
        _git(str(clone_path), "commit", "-m", "Check HEAD")
        _git(str(clone_path), "push", "origin", branch)

        # Get the local commit SHA
        local_result = _git(str(clone_path), "rev-parse", "HEAD")
        local_sha = local_result.stdout.strip()

        # Compare with bare repo
        bare_sha = repo_manager.get_branch_head(project, branch)
        assert bare_sha == local_sha


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
