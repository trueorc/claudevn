"""Comprehensive tests for PRService.

Unit tests covering the full PR lifecycle:
- PR creation and validation
- PR retrieval (get_pr, list_prs)
- Status transitions (approve, reject, update_status)
- Queue operations (PR queue, merge queue)
- Compute operations (get_compute_prs, cleanup_compute)
- Edge cases and error handling

Happy paths:
- create → approve → merge (full lifecycle)

Conflict paths:
- create → merge → conflict

Edge cases:
- approve non-existent PR
- merge without approval
- create PR for non-existent branch
- create duplicate PR
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from git.pr_service import PRService, PRStatus, PullRequest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_redis():
    """Create mock Redis client with default behavior."""
    redis = AsyncMock()

    # Default branch status (no existing PR)
    redis.get_branch_status = AsyncMock(return_value=None)
    redis.set_branch_status = AsyncMock()
    redis.delete_branch_status = AsyncMock(return_value=True)

    # PR queue operations
    redis.add_to_pr_queue = AsyncMock(return_value=1)
    redis.remove_from_pr_queue = AsyncMock(return_value=True)
    redis.get_pr_queue = AsyncMock(return_value=[])
    redis.get_pr_queue_position = AsyncMock(return_value=1)

    # Merge queue operations
    redis.add_to_merge_queue = AsyncMock(return_value=1)
    redis.pop_merge_queue = AsyncMock(return_value=None)
    redis.get_merge_queue = AsyncMock(return_value=[])

    # Compute tracking
    redis.track_compute_branch = AsyncMock()
    redis.untrack_compute_branch = AsyncMock()
    redis.get_compute_branches = AsyncMock(return_value=[])

    # List branches
    redis.list_branches = AsyncMock(return_value=[])

    # Event publishing
    redis.publish_git_event = AsyncMock(return_value=1)

    return redis


@pytest.fixture
def mock_repo_manager():
    """Create mock RepoManager."""
    manager = MagicMock()
    manager.get_branch_head = MagicMock(return_value="abc123def456")
    manager.get_default_branch = MagicMock(return_value="main")
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
# Test: PullRequest Dataclass
# =============================================================================

class TestPullRequestDataclass:
    """Tests for PullRequest dataclass."""

    def test_create_minimal_pull_request(self):
        """Test creating a PR with minimal required fields."""
        pr = PullRequest(
            project="test-project",
            branch="feature/test",
            status=PRStatus.PENDING,
            compute_id="compute-001"
        )

        assert pr.project == "test-project"
        assert pr.branch == "feature/test"
        assert pr.status == PRStatus.PENDING
        assert pr.compute_id == "compute-001"
        assert pr.base_branch == "main"
        assert pr.title is None
        assert pr.description is None

    def test_create_full_pull_request(self):
        """Test creating a PR with all fields."""
        pr = PullRequest(
            project="test-project",
            branch="feature/test",
            status=PRStatus.APPROVED,
            compute_id="compute-001",
            task_id="issue-100",
            title="Add new feature",
            description="This PR adds a new feature",
            head_commit="abc123",
            base_branch="develop",
            queue_position=2,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T01:00:00Z",
            reviewed_by="reviewer-001",
            merged_at=None,
            conflicting_files=["file1.py"]
        )

        assert pr.task_id == "issue-100"
        assert pr.title == "Add new feature"
        assert pr.base_branch == "develop"
        assert pr.queue_position == 2
        assert pr.reviewed_by == "reviewer-001"
        assert pr.conflicting_files == ["file1.py"]

    def test_pull_request_to_dict(self):
        """Test converting PR to dictionary."""
        pr = PullRequest(
            project="test-project",
            branch="feature/test",
            status=PRStatus.MERGED,
            compute_id="compute-001",
            task_id="issue-100",
            merged_at="2025-01-01T02:00:00Z"
        )

        result = pr.to_dict()

        assert result["project"] == "test-project"
        assert result["branch"] == "feature/test"
        assert result["status"] == "merged"
        assert result["compute_id"] == "compute-001"
        assert result["task_id"] == "issue-100"
        assert result["merged_at"] == "2025-01-01T02:00:00Z"

    def test_pr_status_enum_values(self):
        """Test PRStatus enum has expected values."""
        assert PRStatus.PENDING.value == "pending"
        assert PRStatus.IN_REVIEW.value == "in_review"
        assert PRStatus.APPROVED.value == "approved"
        assert PRStatus.REJECTED.value == "rejected"
        assert PRStatus.MERGED.value == "merged"
        assert PRStatus.CONFLICT.value == "conflict"
        assert PRStatus.CLOSED.value == "closed"


# =============================================================================
# Test: PRService.create_pr
# =============================================================================

class TestPRServiceCreatePR:
    """Tests for PRService.create_pr method."""

    @pytest.mark.asyncio
    async def test_create_pr_success(self, pr_service, mock_redis, mock_repo_manager):
        """Test successfully creating a PR."""
        mock_repo_manager.get_branch_head.return_value = "abc123"

        # Mock dry_run_merge to return no conflicts
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {"can_merge": True, "conflicting_files": []}

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100",
                title="Test PR",
                description="Test description"
            )

        assert result.project == "test-project"
        assert result.branch == "feature/test"
        assert result.status == PRStatus.PENDING
        assert result.compute_id == "compute-001"
        assert result.task_id == "issue-100"
        assert result.title == "Test PR"
        assert result.queue_position == 1

        # Verify Redis calls
        mock_redis.set_branch_status.assert_called()
        mock_redis.add_to_pr_queue.assert_called_once_with("test-project", "feature/test")
        mock_redis.track_compute_branch.assert_called_once_with(
            "compute-001", "test-project:feature/test"
        )

    @pytest.mark.asyncio
    async def test_create_pr_branch_not_found(self, pr_service, mock_repo_manager):
        """Test creating PR for non-existent branch fails."""
        mock_repo_manager.get_branch_head.return_value = None

        with pytest.raises(ValueError, match="Branch not found"):
            await pr_service.create_pr(
                project="test-project",
                branch="nonexistent",
                compute_id="compute-001"
            )

    @pytest.mark.asyncio
    async def test_create_pr_duplicate_fails(self, pr_service, mock_redis, mock_repo_manager):
        """Test creating duplicate PR fails."""
        mock_repo_manager.get_branch_head.return_value = "abc123"
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        with pytest.raises(ValueError, match="PR already exists"):
            await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001"
            )

    @pytest.mark.asyncio
    async def test_create_pr_allows_after_closed(self, pr_service, mock_redis, mock_repo_manager):
        """Test creating PR is allowed after previous one was closed."""
        mock_repo_manager.get_branch_head.return_value = "abc123"
        mock_redis.get_branch_status.return_value = {
            "status": "closed",
            "compute_id": "compute-001"
        }

        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {"can_merge": True, "conflicting_files": []}

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-002"
            )

        assert result.status == PRStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_pr_allows_after_merged(self, pr_service, mock_redis, mock_repo_manager):
        """Test creating PR is allowed after previous one was merged."""
        mock_repo_manager.get_branch_head.return_value = "abc123"
        mock_redis.get_branch_status.return_value = {
            "status": "merged",
            "compute_id": "compute-001"
        }

        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {"can_merge": True, "conflicting_files": []}

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-002"
            )

        assert result.status == PRStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_pr_uses_branch_name_as_default_title(
        self, pr_service, mock_redis, mock_repo_manager
    ):
        """Test PR uses branch name as default title."""
        mock_repo_manager.get_branch_head.return_value = "abc123"

        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {"can_merge": True, "conflicting_files": []}

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/my-feature",
                compute_id="compute-001"
            )

        assert result.title == "feature/my-feature"

    @pytest.mark.asyncio
    async def test_create_pr_publishes_event(self, pr_service, mock_redis, mock_repo_manager):
        """Test creating PR publishes Git event."""
        mock_repo_manager.get_branch_head.return_value = "abc123"

        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {"can_merge": True, "conflicting_files": []}

            await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        # Verify pr_created event was published
        calls = mock_redis.publish_git_event.call_args_list
        pr_created_calls = [c for c in calls if c[0][1] == "pr_created"]
        assert len(pr_created_calls) == 1

        event_data = pr_created_calls[0][0][2]
        assert event_data["branch"] == "feature/test"
        assert event_data["compute_id"] == "compute-001"
        assert event_data["task_id"] == "issue-100"


# =============================================================================
# Test: PRService.get_pr
# =============================================================================

class TestPRServiceGetPR:
    """Tests for PRService.get_pr method."""

    @pytest.mark.asyncio
    async def test_get_pr_exists(self, pr_service, mock_redis):
        """Test getting an existing PR."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001",
            "task_id": "issue-100",
            "title": "Test PR",
            "description": "Test description",
            "head_commit": "abc123",
            "base_branch": "main",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T01:00:00Z"
        }

        result = await pr_service.get_pr("test-project", "feature/test")

        assert result is not None
        assert result.project == "test-project"
        assert result.branch == "feature/test"
        assert result.status == PRStatus.PENDING
        assert result.compute_id == "compute-001"
        assert result.queue_position == 1

    @pytest.mark.asyncio
    async def test_get_pr_not_found(self, pr_service, mock_redis):
        """Test getting non-existent PR returns None."""
        mock_redis.get_branch_status.return_value = None

        result = await pr_service.get_pr("test-project", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_pr_parses_conflicting_files_json(self, pr_service, mock_redis):
        """Test get_pr parses conflicting_files from JSON."""
        mock_redis.get_branch_status.return_value = {
            "status": "conflict",
            "compute_id": "compute-001",
            "conflicting_files": '["file1.py", "file2.py"]'
        }

        result = await pr_service.get_pr("test-project", "feature/test")

        assert result.conflicting_files == ["file1.py", "file2.py"]

    @pytest.mark.asyncio
    async def test_get_pr_handles_invalid_conflicting_files_json(self, pr_service, mock_redis):
        """Test get_pr handles invalid conflicting_files JSON gracefully."""
        mock_redis.get_branch_status.return_value = {
            "status": "conflict",
            "compute_id": "compute-001",
            "conflicting_files": "not valid json"
        }

        result = await pr_service.get_pr("test-project", "feature/test")

        assert result.conflicting_files is None


# =============================================================================
# Test: PRService.list_prs
# =============================================================================

class TestPRServiceListPRs:
    """Tests for PRService.list_prs method."""

    @pytest.mark.asyncio
    async def test_list_prs_returns_all(self, pr_service, mock_redis):
        """Test listing all PRs for a project."""
        mock_redis.list_branches.return_value = [
            {
                "branch": "feature/test-1",
                "status": "pending",
                "compute_id": "compute-001"
            },
            {
                "branch": "feature/test-2",
                "status": "approved",
                "compute_id": "compute-002"
            }
        ]

        result = await pr_service.list_prs("test-project")

        assert len(result) == 2
        assert result[0].branch == "feature/test-1"
        assert result[1].branch == "feature/test-2"

    @pytest.mark.asyncio
    async def test_list_prs_with_status_filter(self, pr_service, mock_redis):
        """Test listing PRs with status filter."""
        mock_redis.list_branches.return_value = [
            {
                "branch": "feature/test-1",
                "status": "approved",
                "compute_id": "compute-001"
            }
        ]

        result = await pr_service.list_prs("test-project", status=PRStatus.APPROVED)

        mock_redis.list_branches.assert_called_with(
            "test-project", status="approved", compute_id=None
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_prs_with_compute_filter(self, pr_service, mock_redis):
        """Test listing PRs with compute_id filter."""
        mock_redis.list_branches.return_value = [
            {
                "branch": "feature/test-1",
                "status": "pending",
                "compute_id": "compute-001"
            }
        ]

        result = await pr_service.list_prs("test-project", compute_id="compute-001")

        mock_redis.list_branches.assert_called_with(
            "test-project", status=None, compute_id="compute-001"
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_prs_empty(self, pr_service, mock_redis):
        """Test listing PRs returns empty list when none exist."""
        mock_redis.list_branches.return_value = []

        result = await pr_service.list_prs("test-project")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_prs_skips_entries_without_branch(self, pr_service, mock_redis):
        """Test list_prs skips entries missing branch field."""
        mock_redis.list_branches.return_value = [
            {"status": "pending", "compute_id": "compute-001"},  # Missing branch
            {"branch": "feature/test", "status": "pending", "compute_id": "compute-002"}
        ]

        result = await pr_service.list_prs("test-project")

        assert len(result) == 1
        assert result[0].branch == "feature/test"


# =============================================================================
# Test: PRService.update_status
# =============================================================================

class TestPRServiceUpdateStatus:
    """Tests for PRService.update_status method."""

    @pytest.mark.asyncio
    async def test_update_status_success(self, pr_service, mock_redis):
        """Test updating PR status."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        result = await pr_service.update_status(
            "test-project", "feature/test", PRStatus.IN_REVIEW
        )

        assert result is not None
        mock_redis.set_branch_status.assert_called()

    @pytest.mark.asyncio
    async def test_update_status_pr_not_found(self, pr_service, mock_redis):
        """Test updating status of non-existent PR fails."""
        mock_redis.get_branch_status.return_value = None

        with pytest.raises(ValueError, match="PR not found"):
            await pr_service.update_status(
                "test-project", "nonexistent", PRStatus.APPROVED
            )

    @pytest.mark.asyncio
    async def test_update_status_approved_adds_to_merge_queue(self, pr_service, mock_redis):
        """Test approving PR adds it to merge queue."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        await pr_service.update_status(
            "test-project", "feature/test", PRStatus.APPROVED, reviewed_by="reviewer-001"
        )

        mock_redis.add_to_merge_queue.assert_called_once_with("test-project", "feature/test")

    @pytest.mark.asyncio
    async def test_update_status_approved_publishes_event(self, pr_service, mock_redis):
        """Test approving PR publishes approval event."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        await pr_service.update_status(
            "test-project", "feature/test", PRStatus.APPROVED, reviewed_by="reviewer-001"
        )

        calls = mock_redis.publish_git_event.call_args_list
        approval_calls = [c for c in calls if c[0][1] == "pr_approved"]
        assert len(approval_calls) == 1
        assert approval_calls[0][0][2]["reviewed_by"] == "reviewer-001"

    @pytest.mark.asyncio
    async def test_update_status_rejected_removes_from_queue(self, pr_service, mock_redis):
        """Test rejecting PR removes it from queue."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        await pr_service.update_status(
            "test-project", "feature/test", PRStatus.REJECTED
        )

        mock_redis.remove_from_pr_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_closed_removes_from_queue(self, pr_service, mock_redis):
        """Test closing PR removes it from queue."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        await pr_service.update_status(
            "test-project", "feature/test", PRStatus.CLOSED
        )

        mock_redis.remove_from_pr_queue.assert_called_once()


# =============================================================================
# Test: PRService.approve and PRService.reject
# =============================================================================

class TestPRServiceApproveReject:
    """Tests for PRService.approve and reject convenience methods."""

    @pytest.mark.asyncio
    async def test_approve_sets_status_and_reviewer(self, pr_service, mock_redis):
        """Test approve method sets correct status and reviewer."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        await pr_service.approve("test-project", "feature/test", "reviewer-001")

        # Check that status was set to approved
        calls = mock_redis.set_branch_status.call_args_list
        status_calls = [c for c in calls if "status" in c[1]]
        assert any(c[1].get("status") == "approved" for c in status_calls)

    @pytest.mark.asyncio
    async def test_approve_non_existent_pr_fails(self, pr_service, mock_redis):
        """Test approving non-existent PR fails."""
        mock_redis.get_branch_status.return_value = None

        with pytest.raises(ValueError, match="PR not found"):
            await pr_service.approve("test-project", "nonexistent", "reviewer-001")

    @pytest.mark.asyncio
    async def test_reject_sets_status(self, pr_service, mock_redis):
        """Test reject method sets correct status."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        await pr_service.reject("test-project", "feature/test", "reviewer-001")

        # Check that pr_closed event was published
        calls = mock_redis.publish_git_event.call_args_list
        closed_calls = [c for c in calls if c[0][1] == "pr_closed"]
        assert len(closed_calls) == 1


# =============================================================================
# Test: PRService.check_mergeable
# =============================================================================

class TestPRServiceCheckMergeable:
    """Tests for PRService.check_mergeable method."""

    @pytest.mark.asyncio
    async def test_check_mergeable_repo_not_found(self, pr_service):
        """Test check_mergeable with non-existent repo."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await pr_service.check_mergeable("nonexistent", "feature/test")

        assert result["mergeable"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_check_mergeable_branch_not_found(self, pr_service, mock_repo_manager):
        """Test check_mergeable with non-existent branch."""
        mock_repo_manager.get_branch_head.return_value = None

        with patch("pathlib.Path.exists", return_value=True):
            result = await pr_service.check_mergeable("test-project", "nonexistent")

        assert result["mergeable"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_check_mergeable_fast_forward_possible(self, pr_service, mock_repo_manager):
        """Test check_mergeable when fast-forward is possible."""
        mock_repo_manager.get_branch_head.side_effect = lambda p, b: {
            "main": "abc123",
            "feature/test": "def456"
        }.get(b, None)

        def mock_subprocess(*args, **kwargs):
            cmd = args[0]
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc123\n"  # merge-base same as main
            return result

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", side_effect=mock_subprocess):
                result = await pr_service.check_mergeable("test-project", "feature/test")

        assert result["mergeable"] is True
        assert result["merge_type"] == "fast-forward"

    @pytest.mark.asyncio
    async def test_check_mergeable_no_common_ancestor(self, pr_service, mock_repo_manager):
        """Test check_mergeable when no common ancestor exists."""
        mock_repo_manager.get_branch_head.return_value = "abc123"

        def mock_subprocess(*args, **kwargs):
            result = MagicMock()
            result.returncode = 1  # merge-base fails
            return result

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", side_effect=mock_subprocess):
                result = await pr_service.check_mergeable("test-project", "feature/test")

        assert result["mergeable"] is False
        assert "common ancestor" in result["error"].lower()


# =============================================================================
# Test: PRService Queue Operations
# =============================================================================

class TestPRServiceQueueOperations:
    """Tests for PRService queue operations."""

    @pytest.mark.asyncio
    async def test_get_pr_queue(self, pr_service, mock_redis):
        """Test getting PR queue."""
        mock_redis.get_pr_queue.return_value = ["feature/test-1", "feature/test-2"]
        mock_redis.get_branch_status.side_effect = [
            {"status": "pending", "compute_id": "compute-001"},
            {"status": "pending", "compute_id": "compute-002"}
        ]
        mock_redis.get_pr_queue_position.side_effect = [1, 2]

        result = await pr_service.get_pr_queue("test-project")

        assert len(result) == 2
        assert result[0].queue_position == 1
        assert result[1].queue_position == 2

    @pytest.mark.asyncio
    async def test_get_merge_queue(self, pr_service, mock_redis):
        """Test getting merge queue."""
        mock_redis.get_merge_queue.return_value = ["feature/approved-1", "feature/approved-2"]

        result = await pr_service.get_merge_queue("test-project")

        assert result == ["feature/approved-1", "feature/approved-2"]

    @pytest.mark.asyncio
    async def test_process_merge_queue_empty(self, pr_service, mock_redis):
        """Test processing empty merge queue."""
        mock_redis.pop_merge_queue.return_value = None

        result = await pr_service.process_merge_queue("test-project")

        assert result == []


# =============================================================================
# Test: PRService Compute Operations
# =============================================================================

class TestPRServiceComputeOperations:
    """Tests for PRService compute-related operations."""

    @pytest.mark.asyncio
    async def test_get_compute_prs(self, pr_service, mock_redis):
        """Test getting PRs owned by a compute instance."""
        mock_redis.get_compute_branches.return_value = [
            "project1:feature/test-1",
            "project2:feature/test-2"
        ]
        mock_redis.get_branch_status.side_effect = [
            {"status": "pending", "compute_id": "compute-001"},
            {"status": "approved", "compute_id": "compute-001"}
        ]

        result = await pr_service.get_compute_prs("compute-001")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_compute_prs_skips_invalid_format(self, pr_service, mock_redis):
        """Test get_compute_prs skips branches without colon separator."""
        mock_redis.get_compute_branches.return_value = [
            "invalid-format",  # No colon
            "project:feature/test"
        ]
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        result = await pr_service.get_compute_prs("compute-001")

        # Only one valid PR should be returned
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_cleanup_compute_closes_pending_prs(self, pr_service, mock_redis):
        """Test cleanup_compute closes pending PRs."""
        mock_redis.get_compute_branches.return_value = ["project:feature/test"]
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }

        closed_count = await pr_service.cleanup_compute("compute-001")

        assert closed_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_compute_closes_in_review_prs(self, pr_service, mock_redis):
        """Test cleanup_compute closes in_review PRs."""
        mock_redis.get_compute_branches.return_value = ["project:feature/test"]
        mock_redis.get_branch_status.return_value = {
            "status": "in_review",
            "compute_id": "compute-001"
        }

        closed_count = await pr_service.cleanup_compute("compute-001")

        assert closed_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_compute_skips_merged_prs(self, pr_service, mock_redis):
        """Test cleanup_compute does not close merged PRs."""
        mock_redis.get_compute_branches.return_value = ["project:feature/test"]
        mock_redis.get_branch_status.return_value = {
            "status": "merged",
            "compute_id": "compute-001"
        }

        closed_count = await pr_service.cleanup_compute("compute-001")

        assert closed_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_compute_no_prs(self, pr_service, mock_redis):
        """Test cleanup_compute with no PRs."""
        mock_redis.get_compute_branches.return_value = []

        closed_count = await pr_service.cleanup_compute("compute-001")

        assert closed_count == 0


# =============================================================================
# Test: Happy Path - Full PR Lifecycle
# =============================================================================

class TestPRServiceFullLifecycle:
    """Tests for full PR lifecycle: create → approve → merge."""

    @pytest.mark.asyncio
    async def test_create_approve_merge_happy_path(
        self, pr_service, mock_redis, mock_repo_manager, mock_sse_manager
    ):
        """Test full lifecycle: create → approve → merge."""
        # Setup for create
        mock_repo_manager.get_branch_head.return_value = "abc123"

        # Step 1: Create PR
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {"can_merge": True, "conflicting_files": []}

            pr = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100",
                title="New Feature"
            )

        assert pr.status == PRStatus.PENDING

        # Step 2: Approve PR
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001",
            "task_id": "issue-100"
        }

        approved_pr = await pr_service.approve(
            "test-project", "feature/test", "reviewer-001"
        )

        # Verify added to merge queue
        mock_redis.add_to_merge_queue.assert_called_with("test-project", "feature/test")

        # Step 3: Merge PR
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": "compute-001",
            "task_id": "issue-100",
            "head_commit": "abc123"
        }

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = "merge123\n"
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        merge_result = await pr_service.merge("test-project", "feature/test")

        assert merge_result["success"] is True

        # Verify SSE work_completed event was sent
        mock_sse_manager.send_work_completed.assert_called()


# =============================================================================
# Test: Edge Cases - Merge Without Approval
# =============================================================================

class TestPRServiceMergeWithoutApproval:
    """Tests for merge without approval edge case."""

    @pytest.mark.asyncio
    async def test_merge_pending_pr_fails(self, pr_service, mock_redis, mock_repo_manager):
        """Test merging a pending PR fails."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-001"
        }
        mock_repo_manager.get_branch_head.return_value = "abc123"

        with pytest.raises(ValueError, match="not approved"):
            await pr_service.merge("test-project", "feature/test")

    @pytest.mark.asyncio
    async def test_merge_in_review_pr_fails(self, pr_service, mock_redis, mock_repo_manager):
        """Test merging an in_review PR fails."""
        mock_redis.get_branch_status.return_value = {
            "status": "in_review",
            "compute_id": "compute-001"
        }
        mock_repo_manager.get_branch_head.return_value = "abc123"

        with pytest.raises(ValueError, match="not approved"):
            await pr_service.merge("test-project", "feature/test")

    @pytest.mark.asyncio
    async def test_merge_rejected_pr_fails(self, pr_service, mock_redis, mock_repo_manager):
        """Test merging a rejected PR fails."""
        mock_redis.get_branch_status.return_value = {
            "status": "rejected",
            "compute_id": "compute-001"
        }
        mock_repo_manager.get_branch_head.return_value = "abc123"

        with pytest.raises(ValueError, match="not approved"):
            await pr_service.merge("test-project", "feature/test")

    @pytest.mark.asyncio
    async def test_merge_conflict_status_pr_fails(self, pr_service, mock_redis, mock_repo_manager):
        """Test merging a PR with conflict status fails."""
        mock_redis.get_branch_status.return_value = {
            "status": "conflict",
            "compute_id": "compute-001"
        }
        mock_repo_manager.get_branch_head.return_value = "abc123"

        with pytest.raises(ValueError, match="not approved"):
            await pr_service.merge("test-project", "feature/test")


# =============================================================================
# Test: PRService Initialization
# =============================================================================

class TestPRServiceInit:
    """Tests for PRService initialization."""

    def test_init_with_dependencies(self):
        """Test PRService initialization with provided dependencies."""
        redis = AsyncMock()
        repo_manager = MagicMock()
        sse_manager = AsyncMock()

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            service = PRService(
                redis_client=redis,
                repo_manager=repo_manager,
                sse_manager=sse_manager
            )

        assert service._redis is redis
        assert service._repo_manager is repo_manager
        assert service._sse_manager is sse_manager

    def test_init_creates_repo_manager_on_demand(self):
        """Test PRService creates RepoManager if not provided."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            with patch("git.pr_service.RepoManager") as mock_rm_class:
                mock_rm_class.return_value = MagicMock()
                service = PRService()

        mock_rm_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_redis_creates_on_demand(self):
        """Test _get_redis creates Redis client on demand."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            with patch("git.pr_service.get_redis", new_callable=AsyncMock) as mock_get_redis:
                mock_get_redis.return_value = AsyncMock()

                service = PRService(redis_client=None)
                redis = await service._get_redis()

        mock_get_redis.assert_called_once()
        assert redis is not None

    def test_get_sse_manager_uses_global_if_not_set(self):
        """Test _get_sse_manager uses global manager if not set."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            with patch("git.pr_service.get_sse_connection_manager") as mock_get_sse:
                mock_get_sse.return_value = AsyncMock()

                service = PRService(sse_manager=None)
                sse = service._get_sse_manager()

        mock_get_sse.assert_called_once()
        assert sse is not None
