"""
Linked Repository Round-Trip Integration Tests
================================================

Tier-2 integration tests that validate the complete linked repository workflow:
  clone external repo → compute works on branch → PR → merge → upstream push

These tests exercise real Git operations using local bare repos as simulated
upstreams (no real GitHub dependency). PR service uses mocked Redis.

Test Scenarios:
1. Full round-trip: clone → compute branch → PR → merge → upstream push verified
2. Non-main default branch (e.g., "develop")
3. Merge conflict with upstream changes detected
4. Upstream push failure doesn't corrupt local merge state
5. Multiple compute instances on different branches
6. Compute branches survive upstream fetch
7. Pre-merge sync picks up upstream changes

Prerequisites:
- Python test environment with pytest
- Git CLI installed
- No Docker, Redis, or SSH required

Run with:
    pytest serving/tests/integration/test_linked_repo_workflow.py -v

Or use the integration test script:
    ./scripts/run_integration_tests.sh -s serving/tests/integration/test_linked_repo_workflow.py
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
# Helpers
# =============================================================================


def _git(work_dir: str, *args, env_extra: dict = None, check: bool = True):
    """Run a git command in the given directory."""
    cmd = ["git"]
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
    _git(work_dir, "config", "user.name", "Linked Repo Test")


def _create_upstream_bare_repo(path: Path, default_branch: str = "main") -> Path:
    """Create a bare repo that simulates an upstream GitHub repository.

    Seeds it with an initial commit on the given default branch.
    Returns the path to the bare repo.
    """
    bare_path = path / "upstream.git"
    work_path = path / "upstream-work"

    # Init bare
    subprocess.run(["git", "init", "--bare", str(bare_path)],
                    capture_output=True, check=True)

    # Set default branch
    subprocess.run(
        ["git", "-C", str(bare_path), "symbolic-ref", "HEAD",
         f"refs/heads/{default_branch}"],
        capture_output=True, check=True
    )

    # Clone, seed, push
    subprocess.run(["git", "clone", str(bare_path), str(work_path)],
                    capture_output=True, check=True)
    _git_config(str(work_path))

    # Create initial commit on the default branch
    _git(str(work_path), "checkout", "-b", default_branch)
    (work_path / "README.md").write_text("# Upstream Project\nInitial content.\n")
    _git(str(work_path), "add", "README.md")
    _git(str(work_path), "commit", "-m", "Initial upstream commit")
    _git(str(work_path), "push", "origin", default_branch)

    return bare_path


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def workspace():
    """Create a temporary workspace with all required directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        dirs = {
            "base": base,
            "repos": base / "repos",           # Serving's bare repos
            "clones": base / "clones",          # Compute clones
            "keys": base / "keys",              # SSH keys
            "upstream": base / "upstream",       # Simulated upstream repos
        }
        for d in dirs.values():
            d.mkdir(exist_ok=True)
        yield dirs


@pytest.fixture
def repo_manager(workspace):
    """Create RepoManager with temporary paths."""
    config = GitConfig(
        repos_path=str(workspace["repos"]),
        ssh_keys_path=str(workspace["keys"]),
        git_user="git",
        enable_ssh=False,
    )
    return RepoManager(config=config)


@pytest.fixture
def upstream_repo(workspace):
    """Create a simulated upstream bare repo with initial content on 'main'."""
    return _create_upstream_bare_repo(workspace["upstream"], default_branch="main")


@pytest.fixture
def upstream_repo_develop(workspace):
    """Create a simulated upstream with 'develop' as default branch."""
    return _create_upstream_bare_repo(workspace["upstream"], default_branch="develop")


@pytest.fixture
def linked_repo(repo_manager, upstream_repo):
    """Clone the upstream into Serving via clone_from_url.

    Returns (project, serving_repo_path, upstream_path).
    """
    project = "linked-test-project"
    repo_path = repo_manager.clone_from_url(
        project=project,
        url=str(upstream_repo),
        default_branch="main",
    )
    return project, repo_path, upstream_repo


@pytest.fixture
def linked_repo_develop(repo_manager, upstream_repo_develop):
    """Clone upstream with develop default branch.

    Returns (project, serving_repo_path, upstream_path).
    """
    project = "linked-develop-project"
    repo_path = repo_manager.clone_from_url(
        project=project,
        url=str(upstream_repo_develop),
        default_branch="develop",
    )
    return project, repo_path, upstream_repo_develop


@pytest.fixture
def compute_clone(linked_repo, workspace):
    """Clone from Serving as a compute instance would.

    Returns (clone_path, project, serving_repo_path, upstream_path, compute_id).
    """
    project, repo_path, upstream_path = linked_repo
    compute_id = "compute-001"
    clone_path = workspace["clones"] / compute_id

    _git(str(clone_path), "clone", str(repo_path), str(clone_path))
    _git_config(str(clone_path))

    return clone_path, project, repo_path, upstream_path, compute_id


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


@pytest.fixture
def allow_main_push():
    """Set CLAUDEVN_ALLOW_MAIN_PUSH=true for merge operations."""
    os.environ["CLAUDEVN_ALLOW_MAIN_PUSH"] = "true"
    yield
    os.environ.pop("CLAUDEVN_ALLOW_MAIN_PUSH", None)


def _make_pr_service(repo_manager, mock_redis):
    """Build a PRService with mocked config and Redis."""
    with patch("git.pr_service.get_config") as mock_config:
        mock_config.return_value.git.repos_path = str(repo_manager._repos_path)
        pr_service = PRService(
            redis_client=mock_redis,
            repo_manager=repo_manager,
            sse_manager=AsyncMock(),
        )
    return pr_service


# =============================================================================
# Test: Clone Verification
# =============================================================================


class TestLinkedRepoClone:
    """Verify clone_from_url produces correct linked repo configuration."""

    def test_clone_sets_is_linked_flag(self, linked_repo, repo_manager):
        """claudevn.isLinked=true is set in git config."""
        project, repo_path, _ = linked_repo
        status = repo_manager.get_repo_status(project)
        assert status["is_linked"] is True

    def test_clone_is_bare_not_mirror(self, linked_repo):
        """Repo is bare clone, not mirror."""
        _, repo_path, _ = linked_repo
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "remote.origin.mirror"],
            capture_output=True, text=True
        )
        # Mirror config should NOT exist
        assert result.returncode != 0 or result.stdout.strip() != "true"

    def test_clone_has_restricted_fetch_refspec(self, linked_repo):
        """Fetch refspec only includes default branch and tags."""
        _, repo_path, _ = linked_repo
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get-all", "remote.origin.fetch"],
            capture_output=True, text=True, check=True
        )
        refspecs = result.stdout.strip().split("\n")
        assert "+refs/heads/main:refs/heads/main" in refspecs
        assert "+refs/tags/*:refs/tags/*" in refspecs
        # Should NOT have catch-all
        assert "+refs/*:refs/*" not in refspecs

    def test_clone_has_correct_default_branch(self, linked_repo, repo_manager):
        """Symbolic HEAD points to the correct default branch."""
        project, _, _ = linked_repo
        assert repo_manager.get_default_branch(project) == "main"

    def test_clone_has_initial_content(self, linked_repo):
        """Cloned repo contains the upstream's initial content."""
        _, repo_path, _ = linked_repo
        with tempfile.TemporaryDirectory() as work_dir:
            _git(work_dir, "clone", str(repo_path), work_dir)
            readme = Path(work_dir) / "README.md"
            assert readme.exists()
            assert "Upstream Project" in readme.read_text()

    def test_clone_has_hooks_installed(self, linked_repo, repo_manager):
        """Hooks are installed on the cloned repo."""
        project, _, _ = linked_repo
        status = repo_manager.verify_hooks(project)
        assert status["hooks_installed"] is True
        assert status["pre_receive"]["exists"] is True
        assert status["pre_receive"]["executable"] is True

    def test_clone_stores_ssh_key_id(self, repo_manager, workspace):
        """SSH key ID is stored in git config when provided."""
        upstream = _create_upstream_bare_repo(
            workspace["upstream"] / "ssh-test", default_branch="main"
        )
        project = "ssh-linked-project"
        repo_path = repo_manager.clone_from_url(
            project=project,
            url=str(upstream),
            ssh_key_id="key-abc-123",
            default_branch="main",
        )
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "claudevn.sshKeyId"],
            capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == "key-abc-123"

    def test_clone_with_develop_default_branch(self, linked_repo_develop, repo_manager):
        """Clone with non-main default branch sets correct symbolic ref."""
        project, repo_path, _ = linked_repo_develop
        assert repo_manager.get_default_branch(project) == "develop"

        # Verify restricted refspec uses develop, not main
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get-all", "remote.origin.fetch"],
            capture_output=True, text=True, check=True
        )
        refspecs = result.stdout.strip().split("\n")
        assert "+refs/heads/develop:refs/heads/develop" in refspecs


# =============================================================================
# Test: Full Round-Trip Workflow
# =============================================================================


class TestLinkedRepoRoundTrip:
    """Test the complete linked repo lifecycle: clone → compute → PR → merge → upstream push."""

    @pytest.mark.asyncio
    async def test_full_round_trip(
        self, compute_clone, repo_manager, mock_redis, allow_main_push
    ):
        """Full e2e: clone → compute branch → push → PR → merge → upstream push verified."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone
        branch = f"f/issue_linked1/{compute_id}"

        # 1. Compute creates feature branch and does work
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "linked_feature.py").write_text("def linked():\n    return True\n")
        _git(str(clone_path), "add", "linked_feature.py")
        _git(str(clone_path), "commit", "-m", "Add linked feature")

        # 2. Push to Serving
        _git(str(clone_path), "push", "origin", branch)

        # Verify branch exists in Serving's bare repo
        assert branch in repo_manager.get_branches(project)

        # 3. Create PR
        pr_service = _make_pr_service(repo_manager, mock_redis)

        # Dry-run merge should succeed
        dry_run = await pr_service.dry_run_merge(project, branch)
        assert dry_run["can_merge"] is True

        # 4. Approve + merge
        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-linked1",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "main",
        }

        merge_result = await pr_service.merge(project, branch, delete_branch=True)

        assert merge_result["success"] is True
        assert merge_result["merged_commit"] is not None
        assert len(merge_result["merged_commit"]) == 40
        assert merge_result["deleted"] is True

        # 5. Verify upstream push happened
        assert "upstream_push" in merge_result
        assert merge_result["upstream_push"]["success"] is True

        # 6. Verify upstream repo has the merge commit with the feature file
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(upstream_path), verify_dir)
            assert (Path(verify_dir) / "linked_feature.py").exists()
            content = (Path(verify_dir) / "linked_feature.py").read_text()
            assert "def linked():" in content

        # 7. Verify feature branch deleted from Serving
        assert branch not in repo_manager.get_branches(project)

    @pytest.mark.asyncio
    async def test_round_trip_with_develop_branch(
        self, linked_repo_develop, workspace, repo_manager, mock_redis, allow_main_push
    ):
        """Full round-trip with 'develop' as default branch."""
        project, repo_path, upstream_path = linked_repo_develop
        compute_id = "compute-dev-001"
        clone_path = workspace["clones"] / "dev-compute"

        # Clone from Serving
        _git(str(clone_path), "clone", str(repo_path), str(clone_path))
        _git_config(str(clone_path))

        # Create feature branch
        branch = f"f/issue_dev1/{compute_id}"
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "dev_feature.py").write_text("# develop branch feature\n")
        _git(str(clone_path), "add", "dev_feature.py")
        _git(str(clone_path), "commit", "-m", "Feature on develop")
        _git(str(clone_path), "push", "origin", branch)

        # PR + merge
        pr_service = _make_pr_service(repo_manager, mock_redis)

        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-dev1",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "develop",
        }

        merge_result = await pr_service.merge(project, branch, delete_branch=True)
        assert merge_result["success"] is True

        # Verify upstream 'develop' has the feature
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", "-b", "develop", str(upstream_path), verify_dir)
            assert (Path(verify_dir) / "dev_feature.py").exists()


# =============================================================================
# Test: Pre-Merge Upstream Sync
# =============================================================================


class TestPreMergeUpstreamSync:
    """Test that merge fetches latest upstream changes before merging."""

    @pytest.mark.asyncio
    async def test_merge_picks_up_upstream_changes(
        self, compute_clone, repo_manager, mock_redis, allow_main_push, workspace
    ):
        """Upstream changes committed after clone are fetched before merge."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone
        branch = f"f/issue_sync1/{compute_id}"

        # Compute creates feature branch
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "compute_work.py").write_text("# compute work\n")
        _git(str(clone_path), "add", "compute_work.py")
        _git(str(clone_path), "commit", "-m", "Compute work")
        _git(str(clone_path), "push", "origin", branch)

        # Meanwhile, push a change directly to upstream (simulating external contributor)
        upstream_work = workspace["base"] / "upstream-external"
        _git(str(upstream_work), "clone", str(upstream_path), str(upstream_work))
        _git_config(str(upstream_work))
        (upstream_work / "external_change.py").write_text("# external contributor\n")
        _git(str(upstream_work), "add", "external_change.py")
        _git(str(upstream_work), "commit", "-m", "External change to upstream")
        _git(str(upstream_work), "push", "origin", "main")

        # PR + merge (should sync upstream first)
        pr_service = _make_pr_service(repo_manager, mock_redis)

        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-sync1",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "main",
        }

        merge_result = await pr_service.merge(project, branch, delete_branch=True)
        assert merge_result["success"] is True

        # Verify: after merge, Serving's main has BOTH files
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "compute_work.py").exists()
            assert (Path(verify_dir) / "external_change.py").exists()

        # Verify: upstream also has both files after push
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(upstream_path), verify_dir)
            assert (Path(verify_dir) / "compute_work.py").exists()
            assert (Path(verify_dir) / "external_change.py").exists()


# =============================================================================
# Test: Upstream Fetch Preserves Compute Branches
# =============================================================================


class TestUpstreamFetchPreservation:
    """Test that fetching from upstream doesn't destroy compute feature branches."""

    def test_fetch_preserves_compute_branches(
        self, compute_clone, repo_manager, workspace
    ):
        """Compute feature branches survive an upstream fetch."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone

        # Compute pushes a feature branch to Serving
        branch = f"f/issue_preserve/{compute_id}"
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "preserve_me.py").write_text("# must survive fetch\n")
        _git(str(clone_path), "add", "preserve_me.py")
        _git(str(clone_path), "commit", "-m", "Branch to preserve")
        _git(str(clone_path), "push", "origin", branch)

        # Verify branch exists before fetch
        assert branch in repo_manager.get_branches(project)

        # Push a change to upstream
        upstream_work = workspace["base"] / "upstream-fetch-test"
        _git(str(upstream_work), "clone", str(upstream_path), str(upstream_work))
        _git_config(str(upstream_work))
        (upstream_work / "upstream_new.py").write_text("# new upstream\n")
        _git(str(upstream_work), "add", "upstream_new.py")
        _git(str(upstream_work), "commit", "-m", "Upstream change")
        _git(str(upstream_work), "push", "origin", "main")

        # Fetch from upstream into Serving
        repo_manager.pull_from_origin(project)

        # Verify: compute branch still exists
        branches = repo_manager.get_branches(project)
        assert branch in branches
        assert "main" in branches

        # Verify: main was updated with upstream content
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "upstream_new.py").exists()


# =============================================================================
# Test: Merge Conflict With Upstream Changes
# =============================================================================


class TestUpstreamConflictDetection:
    """Test that upstream conflicts are properly detected."""

    @pytest.mark.asyncio
    async def test_conflict_with_upstream_change(
        self, compute_clone, repo_manager, mock_redis, allow_main_push, workspace
    ):
        """Merge detects conflict when upstream changed same file as compute."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone
        branch = f"f/issue_conflict/{compute_id}"

        # Compute modifies README
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "README.md").write_text("# Modified by compute\n")
        _git(str(clone_path), "add", "README.md")
        _git(str(clone_path), "commit", "-m", "Compute modifies README")
        _git(str(clone_path), "push", "origin", branch)

        # Upstream also modifies README (conflicting change)
        upstream_work = workspace["base"] / "upstream-conflict"
        _git(str(upstream_work), "clone", str(upstream_path), str(upstream_work))
        _git_config(str(upstream_work))
        (upstream_work / "README.md").write_text("# Modified by upstream contributor\n")
        _git(str(upstream_work), "add", "README.md")
        _git(str(upstream_work), "commit", "-m", "Upstream modifies README")
        _git(str(upstream_work), "push", "origin", "main")

        # PR + attempt merge
        pr_service = _make_pr_service(repo_manager, mock_redis)

        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-conflict",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "main",
        }

        merge_result = await pr_service.merge(project, branch, delete_branch=False)

        assert merge_result["success"] is False
        assert merge_result["reason"] == "conflict"
        assert "README.md" in merge_result["conflicts"]

        # Branch should still exist (not deleted on conflict)
        assert branch in repo_manager.get_branches(project)


# =============================================================================
# Test: Upstream Push Failure Preserves Local Merge
# =============================================================================


class TestUpstreamPushFailure:
    """Test that push failure to upstream doesn't corrupt local state."""

    @pytest.mark.asyncio
    async def test_push_failure_preserves_local_merge(
        self, compute_clone, repo_manager, mock_redis, allow_main_push
    ):
        """If upstream push fails, local merge is still intact."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone
        branch = f"f/issue_pushfail/{compute_id}"

        # Compute creates feature
        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "push_fail_feature.py").write_text("# survives push failure\n")
        _git(str(clone_path), "add", "push_fail_feature.py")
        _git(str(clone_path), "commit", "-m", "Feature that survives push fail")
        _git(str(clone_path), "push", "origin", branch)

        pr_service = _make_pr_service(repo_manager, mock_redis)

        head = repo_manager.get_branch_head(project, branch)
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": compute_id,
            "task_id": "issue-pushfail",
            "title": f"Merge {branch}",
            "head_commit": head,
            "base_branch": "main",
        }

        # Make upstream repo read-only to simulate push failure
        # Remove the origin push URL to make push fail
        subprocess.run(
            ["git", "-C", str(repo_path), "remote", "set-url", "--push",
             "origin", "/nonexistent/path.git"],
            capture_output=True, check=True
        )

        merge_result = await pr_service.merge(project, branch, delete_branch=True)

        # Local merge succeeded
        assert merge_result["success"] is True
        assert merge_result["merged_commit"] is not None

        # Upstream push failed
        assert "upstream_push" in merge_result
        assert merge_result["upstream_push"]["success"] is False

        # Local Serving repo has the feature file (merge preserved)
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "push_fail_feature.py").exists()


# =============================================================================
# Test: Multiple Compute Instances
# =============================================================================


class TestMultipleComputeInstances:
    """Test that multiple compute instances can work on different branches."""

    @pytest.mark.asyncio
    async def test_two_compute_instances_sequential_merge(
        self, linked_repo, workspace, repo_manager, mock_redis, allow_main_push
    ):
        """Two compute instances merge sequentially, both land on main and upstream."""
        project, repo_path, upstream_path = linked_repo
        pr_service = _make_pr_service(repo_manager, mock_redis)

        for i, (compute_id, filename) in enumerate([
            ("compute-001", "alpha.py"),
            ("compute-002", "beta.py"),
        ]):
            clone_path = workspace["clones"] / compute_id
            _git(str(clone_path), "clone", str(repo_path), str(clone_path))
            _git_config(str(clone_path))

            branch = f"f/issue_multi{i}/{compute_id}"
            _git(str(clone_path), "checkout", "-b", branch)
            (clone_path / filename).write_text(f"# {filename} by {compute_id}\n")
            _git(str(clone_path), "add", filename)
            _git(str(clone_path), "commit", "-m", f"Add {filename}")
            _git(str(clone_path), "push", "origin", branch)

            head = repo_manager.get_branch_head(project, branch)
            mock_redis.get_branch_status.return_value = {
                "status": "approved",
                "compute_id": compute_id,
                "task_id": f"issue-multi{i}",
                "title": f"Merge {branch}",
                "head_commit": head,
                "base_branch": "main",
            }

            result = await pr_service.merge(project, branch, delete_branch=True)
            assert result["success"] is True

        # Both files exist in Serving
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(repo_path), verify_dir)
            assert (Path(verify_dir) / "alpha.py").exists()
            assert (Path(verify_dir) / "beta.py").exists()

        # Both files pushed to upstream
        with tempfile.TemporaryDirectory() as verify_dir:
            _git(verify_dir, "clone", str(upstream_path), verify_dir)
            assert (Path(verify_dir) / "alpha.py").exists()
            assert (Path(verify_dir) / "beta.py").exists()


# =============================================================================
# Test: Hook Behavior on Linked Repos
# =============================================================================


class TestLinkedRepoHooks:
    """Verify hooks work correctly on linked repos."""

    def test_pre_receive_rejects_push_to_default_branch(self, compute_clone):
        """Pre-receive hook rejects direct push to default branch on linked repo."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone

        (clone_path / "unauthorized.py").write_text("# should not land\n")
        _git(str(clone_path), "add", "unauthorized.py")
        _git(str(clone_path), "commit", "-m", "Direct push to main")

        result = _git(str(clone_path), "push", "origin", "main", check=False)
        assert result.returncode != 0

    def test_pre_receive_accepts_valid_compute_branch(self, compute_clone):
        """Pre-receive hook accepts valid compute branch on linked repo."""
        clone_path, project, repo_path, upstream_path, compute_id = compute_clone
        branch = f"f/issue_hooktest/{compute_id}"

        _git(str(clone_path), "checkout", "-b", branch)
        (clone_path / "hook_test.py").write_text("# hook test\n")
        _git(str(clone_path), "add", "hook_test.py")
        _git(str(clone_path), "commit", "-m", "Hook test")

        result = _git(str(clone_path), "push", "origin", branch, check=False)
        assert result.returncode == 0


# =============================================================================
# Test: Repo Status Reporting
# =============================================================================


class TestLinkedRepoStatus:
    """Verify get_repo_status accurately reports linked repo state."""

    def test_status_reports_is_linked(self, linked_repo, repo_manager):
        """get_repo_status reports is_linked=True for linked repos."""
        project, _, _ = linked_repo
        status = repo_manager.get_repo_status(project)
        assert status is not None
        assert status["is_linked"] is True
        assert status["is_mirror"] is False
        assert status["default_branch"] == "main"

    def test_status_shows_origin_url(self, linked_repo, repo_manager):
        """get_repo_status includes the upstream origin URL."""
        project, _, upstream_path = linked_repo
        status = repo_manager.get_repo_status(project)
        assert status["origin_url"] is not None
        assert str(upstream_path) in status["origin_url"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
