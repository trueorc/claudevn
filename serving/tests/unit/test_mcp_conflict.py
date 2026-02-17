"""Unit tests for claudevn_notify_conflict MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.models import NotifyConflictInput, ConflictNotification, MCPError
from mcp.tools.conflict import notify_conflict, _generate_rebase_guidance


class TestGenerateRebaseGuidance:
    """Test cases for the rebase guidance generator."""

    def test_generates_guidance_with_single_file(self):
        """Test guidance generation with a single conflicting file."""
        guidance = _generate_rebase_guidance(
            branch="feat/my-feature",
            base_branch="main",
            conflicting_files=["src/app.py"]
        )

        assert "feat/my-feature" in guidance
        assert "main" in guidance
        assert "src/app.py" in guidance
        assert "git fetch origin" in guidance
        assert "git rebase origin/main" in guidance
        assert "git push --force-with-lease" in guidance

    def test_generates_guidance_with_multiple_files(self):
        """Test guidance generation with multiple conflicting files."""
        guidance = _generate_rebase_guidance(
            branch="fix/bug-123",
            base_branch="main",
            conflicting_files=["src/app.py", "src/utils.py", "tests/test_app.py"]
        )

        assert "src/app.py" in guidance
        assert "src/utils.py" in guidance
        assert "tests/test_app.py" in guidance
        assert "fix/bug-123" in guidance

    def test_includes_conflict_markers_help(self):
        """Test that guidance includes conflict marker explanation."""
        guidance = _generate_rebase_guidance(
            branch="feat/test",
            base_branch="main",
            conflicting_files=["file.py"]
        )

        assert "<<<<<<<" in guidance
        assert "=======" in guidance
        assert ">>>>>>>" in guidance

    def test_includes_abort_option(self):
        """Test that guidance includes abort instructions."""
        guidance = _generate_rebase_guidance(
            branch="feat/test",
            base_branch="main",
            conflicting_files=["file.py"]
        )

        assert "git rebase --abort" in guidance


class TestNotifyConflict:
    """Test cases for the notify_conflict tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_work = AsyncMock()
        service.update_status = AsyncMock()
        return service

    @pytest.fixture
    def conflict_input(self):
        """Create a sample conflict input."""
        return NotifyConflictInput(
            task_id="task-123",
            branch="feat/my-feature",
            conflicting_files=["src/app.py", "src/models.py"],
            base_branch="main"
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.conflict.get_work_map_service")
    async def test_successful_notification(self, mock_get_service, mock_work_map_service, conflict_input):
        """Test successful conflict notification."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = MagicMock(task_id="task-123")

        result, error = await notify_conflict(conflict_input)

        assert error is None
        assert result is not None
        assert isinstance(result, ConflictNotification)
        assert result.acknowledged is True
        assert result.task_id == "task-123"
        assert result.branch == "feat/my-feature"
        assert result.action_required == "rebase_and_push"
        assert "src/app.py" in result.conflicting_files
        assert "git rebase" in result.guidance

    @pytest.mark.asyncio
    @patch("mcp.tools.conflict.get_work_map_service")
    async def test_task_not_found(self, mock_get_service, mock_work_map_service, conflict_input):
        """Test notification when task doesn't exist."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = None

        result, error = await notify_conflict(conflict_input)

        assert result is None
        assert error is not None
        assert error.code == "TASK_NOT_FOUND"
        assert "task-123" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.conflict.get_work_map_service")
    async def test_updates_work_status(self, mock_get_service, mock_work_map_service, conflict_input):
        """Test that notification updates work status to BLOCKED."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = MagicMock(task_id="task-123")

        await notify_conflict(conflict_input)

        mock_work_map_service.update_status.assert_called_once()
        call_kwargs = mock_work_map_service.update_status.call_args.kwargs
        assert call_kwargs["work_id"] == "task-123"
        assert "conflict" in call_kwargs["message"].lower()

    @pytest.mark.asyncio
    @patch("mcp.tools.conflict.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, conflict_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await notify_conflict(conflict_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    @patch("mcp.tools.conflict.get_work_map_service")
    async def test_internal_error(self, mock_get_service, mock_work_map_service, conflict_input):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.side_effect = Exception("Unexpected error")

        result, error = await notify_conflict(conflict_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"


class TestConflictInputModel:
    """Test cases for the NotifyConflictInput model."""

    def test_required_fields(self):
        """Test that required fields are enforced."""
        input_data = NotifyConflictInput(
            task_id="task-123",
            branch="feat/test",
            conflicting_files=["file.py"]
        )

        assert input_data.task_id == "task-123"
        assert input_data.branch == "feat/test"
        assert input_data.conflicting_files == ["file.py"]
        assert input_data.base_branch == "main"  # default

    def test_custom_base_branch(self):
        """Test custom base branch."""
        input_data = NotifyConflictInput(
            task_id="task-123",
            branch="feat/test",
            conflicting_files=["file.py"],
            base_branch="develop"
        )

        assert input_data.base_branch == "develop"


class TestConflictNotificationModel:
    """Test cases for the ConflictNotification response model."""

    def test_model_creation(self):
        """Test creating a conflict notification response."""
        notification = ConflictNotification(
            acknowledged=True,
            task_id="task-123",
            branch="feat/test",
            action_required="rebase_and_push",
            conflicting_files=["file.py"],
            guidance="Test guidance"
        )

        assert notification.acknowledged is True
        assert notification.task_id == "task-123"
        assert notification.branch == "feat/test"
        assert notification.action_required == "rebase_and_push"
        assert notification.conflicting_files == ["file.py"]
        assert notification.guidance == "Test guidance"
