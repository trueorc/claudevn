"""Unit tests for claudevn_request_review MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.review import request_review
from mcp.models import RequestReviewInput, ReviewResponse, MCPError


class MockPR:
    """Mock PR object."""

    def __init__(self, **kwargs):
        self.project = kwargs.get("project", "test-project")
        self.branch = kwargs.get("branch", "feat/test-feature")
        self.status = MagicMock()
        self.status.value = kwargs.get("status", "pending")
        self.queue_position = kwargs.get("queue_position", 1)


class MockWorkItem:
    """Mock work item."""

    def __init__(self, **kwargs):
        self.work_id = kwargs.get("work_id", "work-123")
        self.project_id = kwargs.get("project_id", "test-project")
        self.assigned_to = kwargs.get("assigned_to", "compute-001")


class TestRequestReviewTool:
    """Test cases for the request_review tool function."""

    @pytest.fixture
    def basic_input(self):
        """Create basic review input."""
        return RequestReviewInput(
            branch="feat/test-feature",
            task_id="work-123"
        )

    @pytest.fixture
    def full_input(self):
        """Create review input with all fields."""
        return RequestReviewInput(
            branch="feat/test-feature",
            task_id="work-123",
            title="Add new feature",
            description="This PR adds a new feature",
            test_results={"passed": 10, "failed": 0}
        )

    @pytest.mark.asyncio
    async def test_successful_pr_creation(self, basic_input):
        """Test successful PR creation."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR()
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem()
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                result, error = await request_review(basic_input)

                assert error is None
                assert result is not None
                assert isinstance(result, ReviewResponse)
                assert result.branch == "feat/test-feature"
                assert result.status == "pending"
                assert result.queue_position == 1

    @pytest.mark.asyncio
    async def test_pr_id_format(self, basic_input):
        """Test that PR ID is formatted correctly."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR(project="my-project", branch="feat/my-branch")
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem(project_id="my-project")
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                result, error = await request_review(basic_input)

                assert error is None
                assert result.pr_id == "pr-my-project-feat/my-branch"

    @pytest.mark.asyncio
    async def test_pr_creation_with_work_context(self, basic_input):
        """Test PR creation uses work context for project and compute ID."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR()
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem(
                    project_id="actual-project",
                    assigned_to="compute-001"
                )
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                await request_review(basic_input)

                mock_pr_service.create_pr.assert_called_once_with(
                    project="actual-project",
                    branch="feat/test-feature",
                    compute_id="compute-001",
                    task_id="work-123",
                    title=None,
                    description=None
                )

    @pytest.mark.asyncio
    async def test_pr_creation_without_work_context(self, basic_input):
        """Test PR creation falls back to defaults when work not found."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR()
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=None)
                mock_get_service.return_value = mock_work_map

                await request_review(basic_input)

                mock_pr_service.create_pr.assert_called_once_with(
                    project="default",
                    branch="feat/test-feature",
                    compute_id="unknown",
                    task_id="work-123",
                    title=None,
                    description=None
                )

    @pytest.mark.asyncio
    async def test_pr_creation_with_title_and_description(self, full_input):
        """Test PR creation passes title and description."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR()
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem()
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                await request_review(full_input)

                call_kwargs = mock_pr_service.create_pr.call_args.kwargs
                assert call_kwargs["title"] == "Add new feature"
                assert call_kwargs["description"] == "This PR adds a new feature"

    @pytest.mark.asyncio
    async def test_pr_create_failed_value_error(self, basic_input):
        """Test graceful response when branch not yet pushed (timing issue).

        When the agent calls claudevn_request_review before the branch is pushed,
        create_pr raises ValueError('Branch not found'). The tool now returns a
        pending ReviewResponse instead of an error — the real PR is auto-created
        on the claude_code_completed event.
        """
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(
                    side_effect=ValueError("Branch not found")
                )
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem()
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                result, error = await request_review(basic_input)

                # Branch not found = timing issue, not an error — return pending response
                assert error is None
                assert result is not None
                assert result.status == "pending"
                assert result.branch == basic_input.branch

    @pytest.mark.asyncio
    async def test_pr_already_exists(self, basic_input):
        """Test graceful response when PR already exists for the branch."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(
                    side_effect=ValueError("PR already exists for branch")
                )
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem()
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                result, error = await request_review(basic_input)

                # PR already exists — return pending response, not an error
                assert error is None
                assert result is not None
                assert result.status == "pending"
                assert result.branch == basic_input.branch

    @pytest.mark.asyncio
    async def test_internal_error(self, basic_input):
        """Test error handling for unexpected exceptions."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(
                    side_effect=Exception("Network error")
                )
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem()
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                result, error = await request_review(basic_input)

                assert result is None
                assert error is not None
                assert error.code == "INTERNAL_ERROR"
                assert "Network error" in error.message

    @pytest.mark.asyncio
    async def test_work_context_exception_handled(self, basic_input):
        """Test that exception getting work context is handled gracefully."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR()
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                # Work map service throws exception
                mock_get_service.side_effect = RuntimeError("Service not initialized")

                result, error = await request_review(basic_input)

                # Should still succeed with defaults
                assert error is None
                assert result is not None

                # Should use defaults for project and compute_id
                mock_pr_service.create_pr.assert_called_once_with(
                    project="default",
                    branch="feat/test-feature",
                    compute_id="unknown",
                    task_id="work-123",
                    title=None,
                    description=None
                )

    @pytest.mark.asyncio
    async def test_queue_position_in_response(self, basic_input):
        """Test that queue position is included in response."""
        with patch("git.pr_service.PRService") as MockPRService:
            with patch("services.work_map_service.get_work_map_service") as mock_get_service:
                mock_pr = MockPR(queue_position=5)
                mock_pr_service = AsyncMock()
                mock_pr_service.create_pr = AsyncMock(return_value=mock_pr)
                MockPRService.return_value = mock_pr_service

                mock_work = MockWorkItem()
                mock_work_map = AsyncMock()
                mock_work_map.get_work = AsyncMock(return_value=mock_work)
                mock_get_service.return_value = mock_work_map

                result, error = await request_review(basic_input)

                assert error is None
                assert result.queue_position == 5


class TestRequestReviewInputModel:
    """Test cases for the RequestReviewInput model."""

    def test_required_fields(self):
        """Test required fields."""
        input_data = RequestReviewInput(
            branch="feat/test",
            task_id="work-123"
        )
        assert input_data.branch == "feat/test"
        assert input_data.task_id == "work-123"
        assert input_data.title is None
        assert input_data.description is None
        assert input_data.test_results is None

    def test_all_fields(self):
        """Test all fields."""
        input_data = RequestReviewInput(
            branch="feat/test",
            task_id="work-123",
            title="Test PR",
            description="Test description",
            test_results={"passed": 5, "failed": 0}
        )
        assert input_data.title == "Test PR"
        assert input_data.description == "Test description"
        assert input_data.test_results == {"passed": 5, "failed": 0}


class TestReviewResponseModel:
    """Test cases for the ReviewResponse model."""

    def test_model_creation(self):
        """Test creating a review response."""
        response = ReviewResponse(
            pr_id="pr-project-feat/test",
            branch="feat/test",
            status="pending",
            queue_position=1
        )

        assert response.pr_id == "pr-project-feat/test"
        assert response.branch == "feat/test"
        assert response.status == "pending"
        assert response.queue_position == 1

    def test_optional_queue_position(self):
        """Test response without queue position."""
        response = ReviewResponse(
            pr_id="pr-project-feat/test",
            branch="feat/test",
            status="merged"
        )

        assert response.queue_position is None
