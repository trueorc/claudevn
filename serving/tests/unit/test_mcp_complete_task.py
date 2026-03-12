"""Tests for claudevn_complete_task MCP tool with conflict detection."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.tools.complete import complete_task
from mcp.models import CompleteTaskInput, MergeStatus


class MockWork:
    """Mock work item."""
    def __init__(self, **kwargs):
        self.work_id = kwargs.get("work_id", "work-123")
        self.title = kwargs.get("title", "Test Task")
        self.description = kwargs.get("description", "Test Description")
        self.assigned_to = kwargs.get("assigned_to", "compute-001")
        self.project_id = kwargs.get("project_id", "test-project")
        self.base_branch = kwargs.get("base_branch", "main")
        self.required_capabilities = kwargs.get("required_capabilities", [])


@pytest.fixture
def complete_input():
    """Standard complete task input."""
    return CompleteTaskInput(
        task_id="work-123",
        branch="feat/test-feature",
        summary="Implemented the feature",
        deliverables=["src/feature.py"],
        test_results={"passed": 10, "failed": 0}
    )


@pytest.fixture
def mock_work():
    """Mock work item."""
    return MockWork()


class TestCompleteTaskConflictDetection:
    """Tests for conflict detection in complete_task."""

    @pytest.mark.asyncio
    async def test_complete_task_no_conflicts(self, complete_input, mock_work):
        """Test complete_task when no merge conflicts exist."""
        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            with patch("git.pr_service.PRService") as MockPRService:
                # Setup mocks
                mock_service = AsyncMock()
                mock_service.get_work = AsyncMock(return_value=mock_work)
                mock_service.complete_work = AsyncMock(return_value=mock_work)
                mock_service.get_next_assignment = AsyncMock(return_value=None)
                mock_get_service.return_value = mock_service

                mock_pr_service = AsyncMock()
                mock_pr_service.dry_run_merge = AsyncMock(return_value={
                    "can_merge": True,
                    "conflicting_files": [],
                    "main_head": "abc123",
                    "branch_head": "def456"
                })
                MockPRService.return_value = mock_pr_service

                # Execute
                result, error = await complete_task(complete_input)

                # Verify
                assert error is None
                assert result is not None
                assert result.merge_status == MergeStatus.QUEUED
                assert result.task_id == "work-123"
                assert result.status == "implemented"

                # Verify dry-run merge was called
                mock_pr_service.dry_run_merge.assert_called_once_with(
                    "test-project", "feat/test-feature"
                )

    @pytest.mark.asyncio
    async def test_complete_task_with_conflicts(self, complete_input, mock_work):
        """Test complete_task when merge conflicts are detected."""
        conflicting_files = ["src/main.py", "src/config.py"]

        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            with patch("git.pr_service.PRService") as MockPRService:
                with patch("mcp.tools.conflict.notify_conflict") as mock_notify:
                    # Setup mocks
                    mock_service = AsyncMock()
                    mock_service.get_work = AsyncMock(return_value=mock_work)
                    mock_service.complete_work = AsyncMock(return_value=mock_work)
                    mock_service.get_next_assignment = AsyncMock(return_value=None)
                    mock_get_service.return_value = mock_service

                    mock_pr_service = AsyncMock()
                    mock_pr_service.dry_run_merge = AsyncMock(return_value={
                        "can_merge": False,
                        "conflicting_files": conflicting_files,
                        "main_head": "abc123",
                        "branch_head": "def456"
                    })
                    MockPRService.return_value = mock_pr_service

                    mock_notify.return_value = (MagicMock(), None)

                    # Execute
                    result, error = await complete_task(complete_input)

                    # Verify
                    assert error is None
                    assert result is not None
                    assert result.merge_status == MergeStatus.CONFLICT
                    assert result.task_id == "work-123"

                    # Verify notify_conflict was called
                    mock_notify.assert_called_once()
                    call_args = mock_notify.call_args[0][0]
                    assert call_args.task_id == "work-123"
                    assert call_args.branch == "feat/test-feature"
                    assert call_args.conflicting_files == conflicting_files

    @pytest.mark.asyncio
    async def test_complete_task_conflict_notification_fails(self, complete_input, mock_work):
        """Test complete_task continues even if conflict notification fails."""
        from mcp.models import MCPError

        conflicting_files = ["src/main.py"]

        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            with patch("git.pr_service.PRService") as MockPRService:
                with patch("mcp.tools.conflict.notify_conflict") as mock_notify:
                    # Setup mocks
                    mock_service = AsyncMock()
                    mock_service.get_work = AsyncMock(return_value=mock_work)
                    mock_service.complete_work = AsyncMock(return_value=mock_work)
                    mock_service.get_next_assignment = AsyncMock(return_value=None)
                    mock_get_service.return_value = mock_service

                    mock_pr_service = AsyncMock()
                    mock_pr_service.dry_run_merge = AsyncMock(return_value={
                        "can_merge": False,
                        "conflicting_files": conflicting_files
                    })
                    MockPRService.return_value = mock_pr_service

                    # Notification fails
                    mock_notify.return_value = (
                        None,
                        MCPError(code="NOTIFICATION_FAILED", message="Failed")
                    )

                    # Execute - should still complete
                    result, error = await complete_task(complete_input)

                    # Verify completion still succeeds
                    assert error is None
                    assert result is not None
                    assert result.merge_status == MergeStatus.CONFLICT

    @pytest.mark.asyncio
    async def test_complete_task_task_not_found(self, complete_input):
        """Test complete_task when task is not found."""
        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            mock_service = AsyncMock()
            mock_service.get_work = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            # Execute
            result, error = await complete_task(complete_input)

            # Verify
            assert result is None
            assert error is not None
            assert error.code == "TASK_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_complete_task_service_unavailable(self, complete_input):
        """Test complete_task when service is not available."""
        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            mock_get_service.side_effect = RuntimeError("Service not initialized")

            # Execute
            result, error = await complete_task(complete_input)

            # Verify
            assert result is None
            assert error is not None
            assert error.code == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_complete_task_dry_run_error(self, complete_input, mock_work):
        """Test complete_task when dry-run merge returns error."""
        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            with patch("git.pr_service.PRService") as MockPRService:
                # Setup mocks
                mock_service = AsyncMock()
                mock_service.get_work = AsyncMock(return_value=mock_work)
                mock_service.complete_work = AsyncMock(return_value=mock_work)
                mock_service.get_next_assignment = AsyncMock(return_value=None)
                mock_get_service.return_value = mock_service

                # dry_run_merge returns error instead of can_merge
                mock_pr_service = AsyncMock()
                mock_pr_service.dry_run_merge = AsyncMock(return_value={
                    "can_merge": False,
                    "conflicting_files": [],
                    "error": "Git error: Branch not found"
                })
                MockPRService.return_value = mock_pr_service

                with patch("mcp.tools.conflict.notify_conflict") as mock_notify:
                    mock_notify.return_value = (MagicMock(), None)

                    # Execute
                    result, error = await complete_task(complete_input)

                    # Verify - empty conflicting_files means branch not pushed yet,
                    # not a real conflict. Should proceed as QUEUED, not CONFLICT.
                    assert error is None
                    assert result is not None
                    assert result.merge_status == MergeStatus.QUEUED
                    # notify_conflict should NOT be called when no actual files conflict
                    mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_task_assigns_next_work(self, complete_input, mock_work):
        """Test complete_task returns next assignment when available."""
        class MockNextAssignment:
            work_id = "work-456"
            title = "Next Task"
            description = "Next task description"
            skills = ["python"]
            branch_name = "feat/next-task"
            context = {}
            base_branch = "main"
            dependency_outputs = {}
            dependencies = []

        with patch("mcp.tools.complete.get_work_map_service") as mock_get_service:
            with patch("git.pr_service.PRService") as MockPRService:
                # Setup mocks
                mock_service = AsyncMock()
                mock_service.get_work = AsyncMock(return_value=mock_work)
                mock_service.complete_work = AsyncMock(return_value=mock_work)
                mock_service.get_next_assignment = AsyncMock(
                    return_value=MockNextAssignment()
                )
                mock_get_service.return_value = mock_service

                mock_pr_service = AsyncMock()
                mock_pr_service.dry_run_merge = AsyncMock(return_value={
                    "can_merge": True,
                    "conflicting_files": []
                })
                MockPRService.return_value = mock_pr_service

                # Execute
                result, error = await complete_task(complete_input)

                # Verify
                assert error is None
                assert result is not None
                assert result.next_task is not None
                assert result.next_task.task_id == "work-456"
                assert result.next_task.title == "Next Task"
