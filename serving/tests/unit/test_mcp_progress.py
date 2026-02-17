"""Unit tests for claudevn_report_progress MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.progress import report_progress, STATUS_MAP
from mcp.models import ReportProgressInput, ProgressAck, TaskStatus, MCPError
from models.work_map import WorkStatus


class MockWorkItem:
    """Mock work item."""

    def __init__(self, **kwargs):
        self.work_id = kwargs.get("work_id", "work-123")
        self.title = kwargs.get("title", "Test Task")
        self.status = kwargs.get("status", WorkStatus.IN_PROGRESS)
        self.progress_percent = kwargs.get("progress_percent", 50)


class TestReportProgressTool:
    """Test cases for the report_progress tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.report_progress = AsyncMock()
        return service

    @pytest.fixture
    def mock_work(self):
        """Create a mock work item."""
        return MockWorkItem()

    @pytest.fixture
    def basic_input(self):
        """Create basic progress input."""
        return ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.IN_PROGRESS,
            progress_percent=50,
            message="Working on implementation"
        )

    @pytest.fixture
    def started_input(self):
        """Create progress input with STARTED status."""
        return ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.STARTED,
            progress_percent=0
        )

    @pytest.fixture
    def completed_input(self):
        """Create progress input with COMPLETED status."""
        return ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.COMPLETED,
            progress_percent=100,
            message="Task completed successfully"
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_successful_progress_report(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test successful progress report."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        result, error = await report_progress(basic_input)

        assert error is None
        assert result is not None
        assert isinstance(result, ProgressAck)
        assert result.acknowledged is True
        assert result.task_id == "work-123"
        assert result.updated_at is not None

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_task_not_found(self, mock_get_service, mock_work_map_service, basic_input):
        """Test error when task doesn't exist."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = None

        result, error = await report_progress(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "TASK_NOT_FOUND"
        assert "work-123" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_status_mapping_started(
        self, mock_get_service, mock_work_map_service, mock_work, started_input
    ):
        """Test STARTED status maps to IN_PROGRESS."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        await report_progress(started_input)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.status == WorkStatus.IN_PROGRESS

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_status_mapping_in_progress(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test IN_PROGRESS status mapping."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        await report_progress(basic_input)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.status == WorkStatus.IN_PROGRESS

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_status_mapping_blocked(
        self, mock_get_service, mock_work_map_service, mock_work
    ):
        """Test BLOCKED status mapping."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        input_data = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.BLOCKED,
            message="Waiting for dependency"
        )

        await report_progress(input_data)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.status == WorkStatus.BLOCKED

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_status_mapping_review_requested(
        self, mock_get_service, mock_work_map_service, mock_work
    ):
        """Test REVIEW_REQUESTED status maps to REVIEW."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        input_data = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.REVIEW_REQUESTED,
            progress_percent=100
        )

        await report_progress(input_data)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.status == WorkStatus.REVIEW

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_status_mapping_completed(
        self, mock_get_service, mock_work_map_service, mock_work, completed_input
    ):
        """Test COMPLETED status mapping."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        await report_progress(completed_input)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.status == WorkStatus.COMPLETED

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_progress_percent_passed(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test that progress percent is passed to service."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        await report_progress(basic_input)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.progress_percent == 50

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_progress_percent_defaults_to_zero(
        self, mock_get_service, mock_work_map_service, mock_work
    ):
        """Test that progress percent defaults to 0 when not provided."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        input_data = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.STARTED
        )

        await report_progress(input_data)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.progress_percent == 0

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_message_passed_as_note(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test that message is passed as note in progress report."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        await report_progress(basic_input)

        call_args = mock_work_map_service.report_progress.call_args[0]
        report = call_args[1]
        assert report.note == "Working on implementation"

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, basic_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await report_progress(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"
        assert "not initialized" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_internal_error(
        self, mock_get_service, mock_work_map_service, basic_input
    ):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.side_effect = Exception("Database error")

        result, error = await report_progress(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Database error" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.progress.get_work_map_service")
    async def test_updated_at_is_utc(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test that updated_at timestamp is in UTC."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.report_progress.return_value = mock_work

        result, error = await report_progress(basic_input)

        assert error is None
        assert result.updated_at.tzinfo == timezone.utc


class TestStatusMapping:
    """Test cases for status mapping."""

    def test_all_task_statuses_mapped(self):
        """Test that all TaskStatus values are mapped."""
        for status in TaskStatus:
            assert status in STATUS_MAP

    def test_started_maps_to_in_progress(self):
        """Test STARTED maps to IN_PROGRESS."""
        assert STATUS_MAP[TaskStatus.STARTED] == WorkStatus.IN_PROGRESS

    def test_in_progress_maps_to_in_progress(self):
        """Test IN_PROGRESS maps to IN_PROGRESS."""
        assert STATUS_MAP[TaskStatus.IN_PROGRESS] == WorkStatus.IN_PROGRESS

    def test_blocked_maps_to_blocked(self):
        """Test BLOCKED maps to BLOCKED."""
        assert STATUS_MAP[TaskStatus.BLOCKED] == WorkStatus.BLOCKED

    def test_review_requested_maps_to_review(self):
        """Test REVIEW_REQUESTED maps to REVIEW."""
        assert STATUS_MAP[TaskStatus.REVIEW_REQUESTED] == WorkStatus.REVIEW

    def test_completed_maps_to_completed(self):
        """Test COMPLETED maps to COMPLETED."""
        assert STATUS_MAP[TaskStatus.COMPLETED] == WorkStatus.COMPLETED


class TestReportProgressInputModel:
    """Test cases for the ReportProgressInput model."""

    def test_required_fields(self):
        """Test required fields."""
        input_data = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.IN_PROGRESS
        )
        assert input_data.task_id == "work-123"
        assert input_data.status == TaskStatus.IN_PROGRESS
        assert input_data.progress_percent is None
        assert input_data.message is None

    def test_all_fields(self):
        """Test all fields."""
        input_data = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.IN_PROGRESS,
            progress_percent=75,
            message="Almost done",
            commits=["abc123", "def456"]
        )
        assert input_data.progress_percent == 75
        assert input_data.message == "Almost done"
        assert input_data.commits == ["abc123", "def456"]

    def test_progress_percent_bounds(self):
        """Test that progress_percent has valid bounds (0-100)."""
        # Valid bounds
        input_0 = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.STARTED,
            progress_percent=0
        )
        assert input_0.progress_percent == 0

        input_100 = ReportProgressInput(
            task_id="work-123",
            status=TaskStatus.COMPLETED,
            progress_percent=100
        )
        assert input_100.progress_percent == 100


class TestProgressAckModel:
    """Test cases for the ProgressAck model."""

    def test_model_creation(self):
        """Test creating a progress acknowledgment."""
        now = datetime.now(timezone.utc)
        ack = ProgressAck(
            acknowledged=True,
            task_id="work-123",
            updated_at=now
        )

        assert ack.acknowledged is True
        assert ack.task_id == "work-123"
        assert ack.updated_at == now
