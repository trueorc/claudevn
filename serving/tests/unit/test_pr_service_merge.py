"""Tests for PRService merge operations.

Unit tests for the worktree-based merge with conflict detection:
- _parse_conflict_files: Parse conflict file names from git merge output
- merge: Worktree-based merge with proper conflict detection
- dry_run_merge: Conflict detection without committing
- SSE event integration: merge_conflict and work_completed events
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from git.pr_service import PRService, PRStatus, PullRequest, _parse_conflict_files


# =============================================================================
# Test: _parse_conflict_files
# =============================================================================

class TestParseConflictFiles:
    """Test conflict file parsing from git merge output."""

    def test_parse_content_conflict(self):
        """Test parsing standard content merge conflicts."""
        merge_output = """Auto-merging src/utils.py
CONFLICT (content): Merge conflict in src/utils.py
Auto-merging src/main.py
CONFLICT (content): Merge conflict in src/main.py
Automatic merge failed; fix conflicts and then commit the result.
"""
        conflicts = _parse_conflict_files(merge_output)
        assert conflicts == ["src/utils.py", "src/main.py"]

    def test_parse_modify_delete_conflict(self):
        """Test parsing modify/delete conflicts."""
        merge_output = """CONFLICT (modify/delete): config.json deleted in HEAD and modified in feature/branch.
"""
        conflicts = _parse_conflict_files(merge_output)
        assert "config.json" in conflicts

    def test_parse_add_add_conflict(self):
        """Test parsing add/add conflicts."""
        merge_output = """CONFLICT (add/add): Merge conflict in new_file.txt
"""
        conflicts = _parse_conflict_files(merge_output)
        assert conflicts == ["new_file.txt"]

    def test_parse_no_conflicts(self):
        """Test parsing output with no conflicts."""
        merge_output = """Auto-merging src/utils.py
Merge made by the 'ort' strategy.
 src/utils.py | 2 ++
 1 file changed, 2 insertions(+)
"""
        conflicts = _parse_conflict_files(merge_output)
        assert conflicts == []

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        conflicts = _parse_conflict_files("")
        assert conflicts == []

    def test_parse_multiple_conflict_types(self):
        """Test parsing output with multiple conflict types."""
        merge_output = """CONFLICT (content): Merge conflict in src/api.py
CONFLICT (modify/delete): old_module.py deleted in HEAD and modified in feature.
CONFLICT (add/add): Merge conflict in tests/test_new.py
"""
        conflicts = _parse_conflict_files(merge_output)
        assert "src/api.py" in conflicts
        assert "old_module.py" in conflicts
        assert "tests/test_new.py" in conflicts


# =============================================================================
# Test: PRService.merge
# =============================================================================

class TestPRServiceMerge:
    """Test PRService merge operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get_branch_status = AsyncMock(return_value={
            "status": "approved",
            "compute_id": "compute-1",
            "task_id": "task-1",
            "title": "Test PR",
            "head_commit": "abc123"
        })
        redis.set_branch_status = AsyncMock()
        redis.remove_from_pr_queue = AsyncMock()
        redis.publish_git_event = AsyncMock()
        redis.untrack_compute_branch = AsyncMock()
        redis.get_pr_queue_position = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def mock_repo_manager(self):
        """Create mock RepoManager."""
        manager = MagicMock()
        manager.get_branch_head = MagicMock(return_value="abc123")
        manager.get_default_branch = MagicMock(return_value="main")
        return manager

    @pytest.fixture
    def pr_service(self, mock_redis, mock_repo_manager):
        """Create PRService with mocked dependencies."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            service = PRService(
                redis_client=mock_redis,
                repo_manager=mock_repo_manager
            )
        return service

    @pytest.mark.asyncio
    async def test_merge_requires_approved_status(self, pr_service, mock_redis):
        """Test merge fails if PR not approved."""
        mock_redis.get_branch_status.return_value = {
            "status": "pending",
            "compute_id": "compute-1"
        }

        with pytest.raises(ValueError, match="not approved"):
            await pr_service.merge("test-project", "feature/test")

    @pytest.mark.asyncio
    async def test_merge_requires_existing_pr(self, pr_service, mock_redis):
        """Test merge fails if PR doesn't exist."""
        mock_redis.get_branch_status.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await pr_service.merge("test-project", "feature/test")

    @pytest.mark.asyncio
    async def test_merge_success_updates_redis(self, pr_service, mock_redis, mock_repo_manager):
        """Test successful merge updates Redis status."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        with patch("subprocess.run") as mock_run:
            # Mock all subprocess calls to succeed
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="def456\n",
                stderr=""
            )

            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service.merge("test-project", "feature/test")

        assert result["success"] is True
        mock_redis.set_branch_status.assert_called()
        mock_redis.publish_git_event.assert_called()

    @pytest.mark.asyncio
    async def test_merge_conflict_returns_file_list(self, pr_service, mock_redis, mock_repo_manager):
        """Test merge conflict returns list of conflicting files."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            # Check for merge command
            if "merge" in cmd and "--no-ff" in cmd:
                result.returncode = 1
                result.stdout = "Auto-merging src/file.py\n"
                result.stderr = "CONFLICT (content): Merge conflict in src/file.py\n"

            # rev-parse for HEAD
            if "rev-parse" in cmd:
                result.stdout = "abc123\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service.merge("test-project", "feature/test")

        assert result["success"] is False
        assert result["reason"] == "conflict"
        assert "src/file.py" in result["conflicts"]

    @pytest.mark.asyncio
    async def test_merge_conflict_publishes_event(self, pr_service, mock_redis, mock_repo_manager):
        """Test merge conflict publishes event with file list."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            if "merge" in cmd and "--no-ff" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT (content): Merge conflict in src/api.py\n"

            if "rev-parse" in cmd:
                result.stdout = "abc123\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service.merge("test-project", "feature/test")

        # Verify event was published with conflict info
        calls = mock_redis.publish_git_event.call_args_list
        status_call = [c for c in calls if c[0][1] == "status"]
        assert len(status_call) > 0
        event_data = status_call[0][0][2]
        assert event_data["status"] == "conflict"
        assert "conflicting_files" in event_data
        assert "src/api.py" in event_data["conflicting_files"]

    @pytest.mark.asyncio
    async def test_merge_conflict_updates_redis_status(self, pr_service, mock_redis, mock_repo_manager):
        """Test merge conflict updates Redis with conflict status and reason."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            if "merge" in cmd and "--no-ff" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT (content): Merge conflict in config.py\n"

            if "rev-parse" in cmd:
                result.stdout = "abc123\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service.merge("test-project", "feature/test")

        # Check that set_branch_status was called with conflict status
        calls = mock_redis.set_branch_status.call_args_list
        conflict_call = [c for c in calls if c[1].get("status") == PRStatus.CONFLICT.value]
        assert len(conflict_call) > 0
        assert "rejection_reason" in conflict_call[0][1]
        assert "config.py" in conflict_call[0][1]["rejection_reason"]

    @pytest.mark.asyncio
    async def test_merge_cleanup_on_success(self, pr_service, mock_redis, mock_repo_manager):
        """Test temp directory is cleaned up after successful merge."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="def456\n",
                stderr=""
            )

            with patch("shutil.rmtree") as mock_rmtree:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service.merge("test-project", "feature/test")

                mock_rmtree.assert_called_once()

    @pytest.mark.asyncio
    async def test_merge_cleanup_on_conflict(self, pr_service, mock_redis, mock_repo_manager):
        """Test temp directory is cleaned up after conflict."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            if "merge" in cmd and "--no-ff" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT (content): Merge conflict in file.py\n"

            if "rev-parse" in cmd:
                result.stdout = "abc123\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree") as mock_rmtree:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service.merge("test-project", "feature/test")

                mock_rmtree.assert_called_once()


# =============================================================================
# Test: PRService.dry_run_merge
# =============================================================================

class TestPRServiceDryRunMerge:
    """Test PRService dry-run merge operations for conflict detection."""

    @pytest.fixture
    def mock_repo_manager(self):
        """Create mock RepoManager."""
        manager = MagicMock()
        manager.get_branch_head = MagicMock(side_effect=lambda p, b: "abc123" if b == "feature/test" else "def456")
        manager.get_default_branch = MagicMock(return_value="main")
        return manager

    @pytest.fixture
    def pr_service(self, mock_repo_manager):
        """Create PRService with mocked dependencies."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            service = PRService(
                redis_client=None,
                repo_manager=mock_repo_manager
            )
        return service

    @pytest.mark.asyncio
    async def test_dry_run_merge_no_conflicts(self, pr_service, mock_repo_manager):
        """Test dry-run merge with no conflicts returns can_merge=True."""
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service.dry_run_merge("test-project", "feature/test")

        assert result["can_merge"] is True
        assert result["conflicting_files"] == []
        assert "main_head" in result
        assert "branch_head" in result

    @pytest.mark.asyncio
    async def test_dry_run_merge_with_conflicts(self, pr_service, mock_repo_manager):
        """Test dry-run merge with conflicts returns can_merge=False and file list."""
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            # Merge command fails with conflicts
            if "merge" in cmd and "--no-commit" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT (content): Merge conflict in src/api.py\nCONFLICT (content): Merge conflict in src/utils.py\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service.dry_run_merge("test-project", "feature/test")

        assert result["can_merge"] is False
        assert "src/api.py" in result["conflicting_files"]
        assert "src/utils.py" in result["conflicting_files"]
        assert result["main_head"] == "def456"
        assert result["branch_head"] == "abc123"

    @pytest.mark.asyncio
    async def test_dry_run_merge_branch_not_found(self, pr_service, mock_repo_manager):
        """Test dry-run merge fails gracefully when branch doesn't exist."""
        mock_repo_manager.get_branch_head = MagicMock(return_value=None)

        result = await pr_service.dry_run_merge("test-project", "nonexistent")

        assert result["can_merge"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_dry_run_merge_cleanup(self, pr_service, mock_repo_manager):
        """Test dry-run merge cleans up temp directory after completion."""
        def mock_subprocess(*args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree") as mock_rmtree:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service.dry_run_merge("test-project", "feature/test")

                mock_rmtree.assert_called_once()

    @pytest.mark.asyncio
    async def test_dry_run_merge_cleanup_on_error(self, pr_service, mock_repo_manager):
        """Test dry-run merge cleans up temp directory even on error."""
        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "clone" in cmd:
                raise Exception("Clone failed")
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree") as mock_rmtree:
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service.dry_run_merge("test-project", "feature/test")

                mock_rmtree.assert_called_once()

        assert result["can_merge"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_dry_run_merge_aborts_uncommitted_merge(self, pr_service, mock_repo_manager):
        """Test dry-run merge aborts the uncommitted merge after checking."""
        abort_called = False

        def mock_subprocess(*args, **kwargs):
            nonlocal abort_called
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            # Merge succeeds but we need to abort
            if "merge" in cmd and "--abort" in cmd:
                abort_called = True

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service.dry_run_merge("test-project", "feature/test")

        assert abort_called, "Merge should have been aborted"


# =============================================================================
# Test: PRService.merge - SSE Event Integration
# =============================================================================

class TestPRServiceMergeSSE:
    """Test PRService merge SSE event sending."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get_branch_status = AsyncMock(return_value={
            "status": "approved",
            "compute_id": "compute-001",
            "task_id": "issue-100",
            "title": "Test PR",
            "head_commit": "abc123"
        })
        redis.set_branch_status = AsyncMock()
        redis.remove_from_pr_queue = AsyncMock()
        redis.publish_git_event = AsyncMock()
        redis.untrack_compute_branch = AsyncMock()
        redis.get_pr_queue_position = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def mock_repo_manager(self):
        """Create mock RepoManager."""
        manager = MagicMock()
        manager.get_branch_head = MagicMock(return_value="main123")
        manager.get_default_branch = MagicMock(return_value="main")
        return manager

    @pytest.fixture
    def mock_sse_manager(self):
        """Create mock SSE manager."""
        sse = AsyncMock()
        sse.send_merge_conflict = AsyncMock(return_value=True)
        sse.send_work_completed = AsyncMock(return_value=True)
        return sse

    @pytest.fixture
    def pr_service_with_sse(self, mock_redis, mock_repo_manager, mock_sse_manager):
        """Create PRService with mocked dependencies including SSE."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            service = PRService(
                redis_client=mock_redis,
                repo_manager=mock_repo_manager,
                sse_manager=mock_sse_manager
            )
        return service

    @pytest.mark.asyncio
    async def test_merge_conflict_sends_sse_event(
        self, pr_service_with_sse, mock_redis, mock_repo_manager, mock_sse_manager
    ):
        """Test merge conflict sends SSE merge_conflict event."""
        mock_repo_manager.get_branch_head.return_value = "main123"

        def mock_subprocess(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""

            if "merge" in cmd and "--no-ff" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT (content): Merge conflict in src/api.py\n"

            if "rev-parse" in cmd:
                result.stdout = "abc123\n"

            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await pr_service_with_sse.merge("test-project", "feature/test")

        # Verify SSE merge_conflict event was sent
        mock_sse_manager.send_merge_conflict.assert_called_once()
        call_kwargs = mock_sse_manager.send_merge_conflict.call_args[1]
        assert call_kwargs["compute_id"] == "compute-001"
        assert call_kwargs["issue_id"] == "issue-100"
        assert call_kwargs["branch"] == "feature/test"
        assert "src/api.py" in call_kwargs["conflicting_files"]
        assert call_kwargs["main_head"] == "main123"

    @pytest.mark.asyncio
    async def test_merge_success_sends_sse_event(
        self, pr_service_with_sse, mock_redis, mock_repo_manager, mock_sse_manager
    ):
        """Test successful merge sends SSE work_completed event."""
        mock_repo_manager.get_branch_head.return_value = "def456"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="merge789\n",
                stderr=""
            )

            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        result = await pr_service_with_sse.merge("test-project", "feature/test")

        assert result["success"] is True

        # Verify SSE work_completed event was sent
        mock_sse_manager.send_work_completed.assert_called_once()
        call_kwargs = mock_sse_manager.send_work_completed.call_args[1]
        assert call_kwargs["compute_id"] == "compute-001"
        assert call_kwargs["issue_id"] == "issue-100"
        assert call_kwargs["branch"] == "feature/test"
        assert "merge_commit" in call_kwargs

    @pytest.mark.asyncio
    async def test_merge_without_compute_id_skips_sse(self, mock_redis, mock_repo_manager):
        """Test merge without compute_id skips SSE events."""
        mock_redis.get_branch_status.return_value = {
            "status": "approved",
            "compute_id": None,  # No compute ID
            "title": "Test PR",
            "head_commit": "abc123"
        }

        mock_sse_manager = AsyncMock()

        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            service = PRService(
                redis_client=mock_redis,
                repo_manager=mock_repo_manager,
                sse_manager=mock_sse_manager
            )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="def456\n",
                stderr=""
            )

            with patch("shutil.rmtree"):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.mkdir"):
                        await service.merge("test-project", "feature/test")

        # SSE events should not be called when compute_id is None
        mock_sse_manager.send_merge_conflict.assert_not_called()
        mock_sse_manager.send_work_completed.assert_not_called()


# =============================================================================
# Test: PRService.create_pr - Early Conflict Detection
# =============================================================================

class TestPRServiceCreatePRConflictDetection:
    """Test PRService early conflict detection on PR creation."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get_branch_status = AsyncMock(return_value=None)  # No existing PR
        redis.set_branch_status = AsyncMock()
        redis.add_to_pr_queue = AsyncMock(return_value=1)
        redis.track_compute_branch = AsyncMock()
        redis.publish_git_event = AsyncMock()
        return redis

    @pytest.fixture
    def mock_repo_manager(self):
        """Create mock RepoManager."""
        manager = MagicMock()
        manager.get_branch_head = MagicMock(side_effect=lambda p, b: "abc123" if b == "feature/test" else "main456")
        manager.get_default_branch = MagicMock(return_value="main")
        return manager

    @pytest.fixture
    def mock_sse_manager(self):
        """Create mock SSE manager."""
        sse = AsyncMock()
        sse.send_merge_conflict = AsyncMock(return_value=True)
        return sse

    @pytest.fixture
    def pr_service(self, mock_redis, mock_repo_manager, mock_sse_manager):
        """Create PRService with mocked dependencies."""
        with patch("git.pr_service.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/home/git/repos"
            service = PRService(
                redis_client=mock_redis,
                repo_manager=mock_repo_manager,
                sse_manager=mock_sse_manager
            )
        return service

    @pytest.mark.asyncio
    async def test_create_pr_no_conflicts_returns_pending(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR with no conflicts returns pending status."""
        # Mock dry_run_merge to return no conflicts
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": True,
                "conflicting_files": [],
                "main_head": "main456",
                "branch_head": "abc123"
            }

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        assert result.status == PRStatus.PENDING
        assert result.conflicting_files is None
        mock_sse_manager.send_merge_conflict.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_pr_with_conflicts_returns_conflict_status(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR with conflicts returns conflict status."""
        # Mock dry_run_merge to return conflicts
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": False,
                "conflicting_files": ["src/api.py", "src/utils.py"],
                "main_head": "main456",
                "branch_head": "abc123"
            }

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        assert result.status == PRStatus.CONFLICT
        assert result.conflicting_files == ["src/api.py", "src/utils.py"]

    @pytest.mark.asyncio
    async def test_create_pr_with_conflicts_sends_sse_event(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR with conflicts sends SSE merge_conflict event."""
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": False,
                "conflicting_files": ["src/api.py"],
                "main_head": "main456",
                "branch_head": "abc123"
            }

            await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        # Verify SSE merge_conflict event was sent
        mock_sse_manager.send_merge_conflict.assert_called_once()
        call_kwargs = mock_sse_manager.send_merge_conflict.call_args[1]
        assert call_kwargs["compute_id"] == "compute-001"
        assert call_kwargs["issue_id"] == "issue-100"
        assert call_kwargs["branch"] == "feature/test"
        assert "src/api.py" in call_kwargs["conflicting_files"]
        assert call_kwargs["main_head"] == "main456"
        assert "Conflicts with main detected on PR submission" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_create_pr_with_conflicts_updates_redis_status(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR with conflicts updates Redis to conflict status."""
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": False,
                "conflicting_files": ["config.py"],
                "main_head": "main456",
                "branch_head": "abc123"
            }

            await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        # Check that set_branch_status was called with conflict status
        calls = mock_redis.set_branch_status.call_args_list
        conflict_call = [c for c in calls if c[1].get("status") == PRStatus.CONFLICT.value]
        assert len(conflict_call) > 0
        assert "rejection_reason" in conflict_call[0][1]
        assert "config.py" in conflict_call[0][1]["rejection_reason"]
        assert "conflicting_files" in conflict_call[0][1]

    @pytest.mark.asyncio
    async def test_create_pr_with_conflicts_publishes_redis_event(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR with conflicts publishes Redis status event."""
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": False,
                "conflicting_files": ["src/main.py"],
                "main_head": "main456",
                "branch_head": "abc123"
            }

            await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        # Check that publish_git_event was called with status event
        calls = mock_redis.publish_git_event.call_args_list
        status_call = [c for c in calls if c[0][1] == "status"]
        assert len(status_call) > 0
        event_data = status_call[0][0][2]
        assert event_data["status"] == "conflict"
        assert event_data["branch"] == "feature/test"
        assert "conflicting_files" in event_data
        assert "src/main.py" in event_data["conflicting_files"]

    @pytest.mark.asyncio
    async def test_create_pr_ignores_undetermined_conflicts(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR ignores 'Unable to determine' conflict placeholder."""
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": False,
                "conflicting_files": ["Unable to determine specific files"],
                "main_head": "main456",
                "branch_head": "abc123"
            }

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        # Should remain pending if conflicts can't be determined
        assert result.status == PRStatus.PENDING
        mock_sse_manager.send_merge_conflict.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_pr_handles_dry_run_error_gracefully(
        self, pr_service, mock_redis, mock_sse_manager
    ):
        """Test creating PR handles dry_run_merge errors gracefully."""
        with patch.object(pr_service, "dry_run_merge", new_callable=AsyncMock) as mock_dry_run:
            mock_dry_run.return_value = {
                "can_merge": False,
                "conflicting_files": [],
                "error": "Git clone failed"
            }

            result = await pr_service.create_pr(
                project="test-project",
                branch="feature/test",
                compute_id="compute-001",
                task_id="issue-100"
            )

        # Should remain pending on error
        assert result.status == PRStatus.PENDING
        mock_sse_manager.send_merge_conflict.assert_not_called()


# =============================================================================
# Test: PullRequest dataclass with conflicting_files
# =============================================================================

class TestPullRequestConflictingFiles:
    """Test PullRequest dataclass with conflicting_files field."""

    def test_pull_request_to_dict_includes_conflicting_files(self):
        """Test PullRequest.to_dict includes conflicting_files field."""
        pr = PullRequest(
            project="test-project",
            branch="feature/test",
            status=PRStatus.CONFLICT,
            compute_id="compute-001",
            conflicting_files=["src/api.py", "src/utils.py"]
        )

        pr_dict = pr.to_dict()

        assert "conflicting_files" in pr_dict
        assert pr_dict["conflicting_files"] == ["src/api.py", "src/utils.py"]

    def test_pull_request_to_dict_with_none_conflicting_files(self):
        """Test PullRequest.to_dict with None conflicting_files."""
        pr = PullRequest(
            project="test-project",
            branch="feature/test",
            status=PRStatus.PENDING,
            compute_id="compute-001",
            conflicting_files=None
        )

        pr_dict = pr.to_dict()

        assert "conflicting_files" in pr_dict
        assert pr_dict["conflicting_files"] is None

