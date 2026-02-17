"""Unit tests for claudevn_get_context MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.context import get_context
from mcp.models import GetContextInput, ContextResponse, ContextType, MCPError
from models.work_map import WorkStatus, WorkPriority, BlockerType, Blocker


class MockWorkItem:
    """Mock work item."""

    def __init__(self, **kwargs):
        self.work_id = kwargs.get("work_id", "work-123")
        self.title = kwargs.get("title", "Test Task")
        self.description = kwargs.get("description", "Test Description")
        self.work_type = kwargs.get("work_type", "feature")
        self.priority = kwargs.get("priority", WorkPriority.NORMAL)
        self.status = kwargs.get("status", WorkStatus.IN_PROGRESS)
        self.branch_name = kwargs.get("branch_name", "feat/test")
        self.base_branch = kwargs.get("base_branch", "main")
        self.project_id = kwargs.get("project_id", "test-project")
        self.context = kwargs.get("context", {})
        self.required_skills = kwargs.get("required_skills", ["python"])
        self.assigned_skills = kwargs.get("assigned_skills", ["python", "fastapi"])
        self.progress_percent = kwargs.get("progress_percent", 50)
        self.progress_notes = kwargs.get("progress_notes", ["Started work"])
        self.depends_on = kwargs.get("depends_on", [])
        self.result = kwargs.get("result", None)
        self._active_blockers = kwargs.get("active_blockers", [])
        self._is_blocked = kwargs.get("is_blocked", False)

    @property
    def active_blockers(self):
        return self._active_blockers

    @property
    def is_blocked(self):
        return self._is_blocked


class TestGetContextTool:
    """Test cases for the get_context tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_work = AsyncMock()
        service.get_dependencies = AsyncMock()
        return service

    @pytest.fixture
    def mock_work(self):
        """Create a basic mock work item."""
        return MockWorkItem()

    @pytest.fixture
    def basic_input(self):
        """Create basic context input."""
        return GetContextInput(task_id="work-123")

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_successful_context_retrieval(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test successful context retrieval."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [],
            "blocks": [],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result is not None
        assert isinstance(result, ContextResponse)
        assert result.task["task_id"] == "work-123"
        assert result.task["title"] == "Test Task"
        assert result.task["description"] == "Test Description"
        assert result.task["status"] == "in_progress"

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_task_not_found(self, mock_get_service, mock_work_map_service, basic_input):
        """Test error when task doesn't exist."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = None

        result, error = await get_context(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "TASK_NOT_FOUND"
        assert "work-123" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_context_includes_dependencies(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test that dependencies are included in related tasks."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [
                {
                    "work_id": "work-100",
                    "title": "Dependency Task",
                    "status": "completed",
                    "completed": True
                }
            ],
            "blocks": [],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result is not None
        assert len(result.related_tasks) == 1
        assert result.related_tasks[0]["task_id"] == "work-100"
        assert result.related_tasks[0]["relationship"] == "depends_on"
        assert result.related_tasks[0]["completed"] is True

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_context_includes_blocked_tasks(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test that blocked tasks are included in related tasks."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [],
            "blocks": [
                {
                    "work_id": "work-200",
                    "title": "Waiting Task",
                    "status": "pending"
                }
            ],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result is not None
        assert len(result.related_tasks) == 1
        assert result.related_tasks[0]["task_id"] == "work-200"
        assert result.related_tasks[0]["relationship"] == "blocks"

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_context_includes_blockers(
        self, mock_get_service, mock_work_map_service, basic_input
    ):
        """Test that active blockers are included in context."""
        blocker = MagicMock()
        blocker.blocker_id = "blocker-001"
        blocker.blocker_type = BlockerType.TECHNICAL
        blocker.description = "Build failing"
        blocker.blocking_work_id = None

        mock_work = MockWorkItem(
            active_blockers=[blocker],
            is_blocked=True
        )

        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [],
            "blocks": [],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result is not None
        assert result.task["is_blocked"] is True
        assert len(result.task["blockers"]) == 1
        assert result.task["blockers"][0]["blocker_id"] == "blocker-001"
        assert result.task["blockers"][0]["type"] == "technical"

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_context_includes_dependency_outputs(
        self, mock_get_service, mock_work_map_service, basic_input
    ):
        """Test that dependency outputs are included when available."""
        mock_work = MockWorkItem(
            depends_on=["work-100"]
        )
        dep_work = MockWorkItem(
            work_id="work-100",
            result={"summary": "API implemented", "files": ["api.py"]}
        )

        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.side_effect = [mock_work, dep_work]
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [],
            "blocks": [],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result is not None
        assert "dependency_outputs" in result.task
        assert "work-100" in result.task["dependency_outputs"]
        assert result.task["dependency_outputs"]["work-100"]["summary"] == "API implemented"

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_context_all_dependencies_met(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test all_dependencies_met flag is included."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [
                {"work_id": "work-100", "title": "Dep", "status": "pending", "completed": False}
            ],
            "blocks": [],
            "all_dependencies_met": False
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result is not None
        assert result.task["all_dependencies_met"] is False

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, basic_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await get_context(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"
        assert "not initialized" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_internal_error(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.side_effect = Exception("Database error")

        result, error = await get_context(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Database error" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_context_includes_all_task_fields(
        self, mock_get_service, mock_work_map_service, basic_input
    ):
        """Test that all task fields are included in context."""
        mock_work = MockWorkItem(
            priority=WorkPriority.HIGH,
            progress_percent=75,
            progress_notes=["Step 1 done", "Step 2 in progress"]
        )

        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [],
            "blocks": [],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        task = result.task
        assert task["work_type"] == "feature"
        assert task["priority"] == "high"
        assert task["branch_name"] == "feat/test"
        assert task["base_branch"] == "main"
        assert task["project_id"] == "test-project"
        assert task["required_skills"] == ["python"]
        assert task["assigned_skills"] == ["python", "fastapi"]
        assert task["progress_percent"] == 75
        assert task["progress_notes"] == ["Step 1 done", "Step 2 in progress"]

    @pytest.mark.asyncio
    @patch("mcp.tools.context.get_work_map_service")
    async def test_empty_relevant_files_and_commits(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test that relevant_files and recent_commits are empty lists (TODO items)."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.get_dependencies.return_value = {
            "depends_on": [],
            "blocks": [],
            "all_dependencies_met": True
        }

        result, error = await get_context(basic_input)

        assert error is None
        assert result.relevant_files == []
        assert result.recent_commits == []


class TestGetContextInputModel:
    """Test cases for the GetContextInput model."""

    def test_required_fields(self):
        """Test that task_id is required."""
        input_data = GetContextInput(task_id="work-123")
        assert input_data.task_id == "work-123"
        assert input_data.context_types is None
        assert input_data.file_patterns is None

    def test_optional_context_types(self):
        """Test optional context_types field."""
        input_data = GetContextInput(
            task_id="work-123",
            context_types=[ContextType.FILES, ContextType.DEPENDENCIES]
        )
        assert input_data.context_types == [ContextType.FILES, ContextType.DEPENDENCIES]

    def test_optional_file_patterns(self):
        """Test optional file_patterns field."""
        input_data = GetContextInput(
            task_id="work-123",
            file_patterns=["*.py", "*.ts"]
        )
        assert input_data.file_patterns == ["*.py", "*.ts"]


class TestContextResponseModel:
    """Test cases for the ContextResponse model."""

    def test_model_creation(self):
        """Test creating a context response."""
        response = ContextResponse(
            task={"task_id": "work-123", "title": "Test"},
            relevant_files=[{"path": "src/app.py"}],
            related_tasks=[{"task_id": "work-100", "relationship": "depends_on"}],
            recent_commits=[{"sha": "abc123", "message": "Initial commit"}]
        )

        assert response.task["task_id"] == "work-123"
        assert len(response.relevant_files) == 1
        assert len(response.related_tasks) == 1
        assert len(response.recent_commits) == 1

    def test_empty_lists(self):
        """Test response with empty lists."""
        response = ContextResponse(
            task={"task_id": "work-123"},
            relevant_files=[],
            related_tasks=[],
            recent_commits=[]
        )

        assert response.relevant_files == []
        assert response.related_tasks == []
        assert response.recent_commits == []
