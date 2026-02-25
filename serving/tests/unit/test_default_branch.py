"""Tests for dynamic default branch support.

Unit tests for:
- RepoManager.get_default_branch() reading from symbolic-ref HEAD
- PRService._get_default_branch() delegation
- PR lifecycle with non-main default branches (e.g., "develop")
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from git.repo_manager import RepoManager
from git.pr_service import PRService, PRStatus


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """Create mock GitConfig."""
    config = MagicMock()
    config.repos_path = "/home/git/repos"
    return config


@pytest.fixture
def repo_manager(mock_config):
    """Create RepoManager with mocked config."""
    return RepoManager(config=mock_config)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.get_branch_status = AsyncMock(return_value=None)
    redis.set_branch_status = AsyncMock()
    redis.add_to_pr_queue = AsyncMock(return_value=1)
    redis.track_compute_branch = AsyncMock()
    redis.publish_git_event = AsyncMock(return_value=1)
    redis.get_pr_queue_position = AsyncMock(return_value=1)
    redis.remove_from_pr_queue = AsyncMock(return_value=True)
    redis.add_to_merge_queue = AsyncMock(return_value=1)
    redis.untrack_compute_branch = AsyncMock()
    return redis


@pytest.fixture
def mock_repo_manager():
    """Create mock RepoManager with configurable default branch."""
    manager = MagicMock()
    manager.get_branch_head = MagicMock(return_value="abc123def456")
    manager.get_default_branch = MagicMock(return_value="main")
    manager.get_repo_url = MagicMock(return_value="http://serving:8002/git/test.git")
    return manager


@pytest.fixture
def mock_sse_manager():
    """Create mock SSE connection manager."""
    sse = AsyncMock()
    sse.send_merge_conflict = AsyncMock(return_value=True)
    sse.send_work_completed = AsyncMock(return_value=True)
    return sse


@pytest.fixture
def pr_service(mock_redis, mock_repo_manager, mock_sse_manager):
    """Create PRService with all mocked dependencies."""
    with patch("git.pr_service.get_config") as mock_config:
        mock_config.return_value.git.repos_path = "/home/git/repos"
        service = PRService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager,
            sse_manager=mock_sse_manager
        )
    return service


# =============================================================================
# Test: RepoManager.get_default_branch()
# =============================================================================

class TestRepoManagerGetDefaultBranch:
    """Tests for RepoManager.get_default_branch()."""

    @patch("git.repo_manager.subprocess.run")
    def test_returns_main_from_symbolic_ref(self, mock_run, repo_manager):
        """Test reading 'main' from symbolic-ref HEAD."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="refs/heads/main\n"
        )

        result = repo_manager.get_default_branch("test-project")

        assert result == "main"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "symbolic-ref" in args
        assert "HEAD" in args

    @patch("git.repo_manager.subprocess.run")
    def test_returns_develop_from_symbolic_ref(self, mock_run, repo_manager):
        """Test reading 'develop' from symbolic-ref HEAD."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="refs/heads/develop\n"
        )

        result = repo_manager.get_default_branch("test-project")

        assert result == "develop"

    @patch("git.repo_manager.subprocess.run")
    def test_returns_master_from_symbolic_ref(self, mock_run, repo_manager):
        """Test reading 'master' from symbolic-ref HEAD."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="refs/heads/master\n"
        )

        result = repo_manager.get_default_branch("test-project")

        assert result == "master"

    @patch("git.repo_manager.subprocess.run")
    def test_fallback_to_main_on_failure(self, mock_run, repo_manager):
        """Test fallback to 'main' when symbolic-ref fails."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=""
        )

        result = repo_manager.get_default_branch("test-project")

        assert result == "main"


# =============================================================================
# Test: PRService._get_default_branch()
# =============================================================================

class TestPRServiceGetDefaultBranch:
    """Tests for PRService._get_default_branch() delegation."""

    def test_delegates_to_repo_manager(self, pr_service, mock_repo_manager):
        """Test that _get_default_branch delegates to RepoManager."""
        mock_repo_manager.get_default_branch.return_value = "develop"

        result = pr_service._get_default_branch("test-project")

        assert result == "develop"
        mock_repo_manager.get_default_branch.assert_called_once_with("test-project")


# =============================================================================
# Test: PR Lifecycle with non-main default branch
# =============================================================================

class TestCreatePRWithDevelopBranch:
    """Tests for create_pr() using dynamic default branch."""

    @pytest.mark.asyncio
    async def test_create_pr_uses_dynamic_base_branch(
        self, pr_service, mock_redis, mock_repo_manager
    ):
        """Test that create_pr sets base_branch from get_default_branch."""
        mock_repo_manager.get_default_branch.return_value = "develop"

        # Mock dry_run_merge to return success
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry:
            mock_dry.return_value = {"can_merge": True, "conflicting_files": []}

            pr = await pr_service.create_pr(
                project="test-project",
                branch="f/issue_1/compute-001",
                compute_id="compute-001"
            )

        # Verify base_branch was set to "develop" (not hardcoded "main")
        call_kwargs = mock_redis.set_branch_status.call_args_list[0].kwargs
        assert call_kwargs["base_branch"] == "develop"

    @pytest.mark.asyncio
    async def test_create_pr_conflict_message_uses_default_branch(
        self, pr_service, mock_redis, mock_repo_manager, mock_sse_manager
    ):
        """Test conflict messages reference the actual default branch name."""
        mock_repo_manager.get_default_branch.return_value = "develop"

        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry:
            mock_dry.return_value = {
                "can_merge": False,
                "conflicting_files": ["file.py"],
                "main_head": "abc123"
            }

            await pr_service.create_pr(
                project="test-project",
                branch="f/issue_1/compute-001",
                compute_id="compute-001",
                task_id="task-1"
            )

        # Check that conflict message references "develop" not "main"
        sse_call = mock_sse_manager.send_merge_conflict.call_args
        assert "develop" in sse_call.kwargs["message"]
        assert "main" not in sse_call.kwargs["message"]


class TestCheckMergeableWithDevelopBranch:
    """Tests for check_mergeable() using dynamic default branch."""

    @pytest.mark.asyncio
    async def test_check_mergeable_uses_default_branch(
        self, pr_service, mock_repo_manager
    ):
        """Test check_mergeable uses dynamic default branch for merge-base."""
        mock_repo_manager.get_default_branch.return_value = "develop"
        mock_repo_manager.get_branch_head.side_effect = lambda proj, branch: {
            "f/issue_1/compute-001": "branch_head_123",
            "develop": "develop_head_456"
        }.get(branch)

        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(pr_service, "_git_cmd") as mock_git:
                # merge-base returns the merge base
                mock_git.return_value = MagicMock(
                    returncode=0,
                    stdout="develop_head_456\n"
                )

                result = await pr_service.check_mergeable("test-project", "f/issue_1/compute-001")

        # Verify merge-base was called with "develop" not "main"
        mock_git.assert_called_once()
        args = mock_git.call_args[0]
        assert "develop" in args
        assert "main" not in args

    @pytest.mark.asyncio
    async def test_check_mergeable_error_message_uses_default_branch(
        self, pr_service, mock_repo_manager
    ):
        """Test error messages reference the actual default branch name."""
        mock_repo_manager.get_default_branch.return_value = "develop"

        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(pr_service, "_git_cmd") as mock_git:
                mock_git.return_value = MagicMock(returncode=1, stdout="")

                result = await pr_service.check_mergeable("test-project", "f/issue_1/compute-001")

        assert "develop" in result["error"]
        assert "main" not in result["error"]


class TestMergeWithDevelopBranch:
    """Tests for merge() using dynamic default branch."""

    @pytest.mark.asyncio
    async def test_merge_uses_default_branch(
        self, pr_service, mock_redis, mock_repo_manager, mock_sse_manager
    ):
        """Test merge() checks out and pushes the actual default branch."""
        mock_repo_manager.get_default_branch.return_value = "develop"

        # Set up approved PR in Redis
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": "compute-001",
            "task_id": "task-1",
            "title": "Test PR",
            "base_branch": "develop",
            "head_commit": "abc123"
        }

        # Mock check_mergeable
        with patch.object(pr_service, "check_mergeable", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {"mergeable": True, "merge_type": "merge"}

            with patch("git.pr_service.subprocess.run") as mock_run:
                # All subprocess calls succeed
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="abc123def456\n",
                    stderr=""
                )

                result = await pr_service.merge("test-project", "f/issue_1/compute-001")

        assert result["success"] is True

        # Verify checkout was called with "develop" not "main"
        checkout_calls = [
            call for call in mock_run.call_args_list
            if "checkout" in call[0][0]
        ]
        assert len(checkout_calls) >= 1
        assert "develop" in checkout_calls[0][0][0]

        # Verify push was called with "develop" not "main"
        push_calls = [
            call for call in mock_run.call_args_list
            if "push" in call[0][0]
        ]
        assert len(push_calls) >= 1
        assert "develop" in push_calls[0][0][0]

        # Verify merge message references "develop"
        merge_calls = [
            call for call in mock_run.call_args_list
            if "merge" in call[0][0] and "--no-ff" in call[0][0]
        ]
        assert len(merge_calls) >= 1
        merge_cmd = merge_calls[0][0][0]
        msg_idx = merge_cmd.index("-m") + 1
        assert "develop" in merge_cmd[msg_idx]
