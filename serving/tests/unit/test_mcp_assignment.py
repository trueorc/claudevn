"""Unit tests for claudevn_get_assignment MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.assignment import get_assignment
from mcp.models import GetAssignmentInput, TaskAssignment, MCPError


class MockWorkAssignment:
    """Mock work assignment from service."""

    def __init__(self, **kwargs):
        self.work_id = kwargs.get("work_id", "work-123")
        self.title = kwargs.get("title", "Test Task")
        self.description = kwargs.get("description", "Test Description")
        self.skills = kwargs.get("skills", ["python", "fastapi"])
        self.skill_ids = kwargs.get("skill_ids", ["python", "fastapi"])
        self.branch_name = kwargs.get("branch_name", "feat/test-task")
        self.base_branch = kwargs.get("base_branch", "main")
        self.context = kwargs.get("context", {"project": "test"})
        self.dependencies = kwargs.get("dependencies", [])
        self.dependency_outputs = kwargs.get("dependency_outputs", {})
        self.git_project_name = kwargs.get("git_project_name", None)
        self.clone_url = kwargs.get("clone_url", None)
        self.default_branch = kwargs.get("default_branch", None)


class TestGetAssignmentTool:
    """Test cases for the get_assignment tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_next_assignment = AsyncMock()
        return service

    @pytest.fixture
    def basic_input(self):
        """Create basic input for get_assignment."""
        return GetAssignmentInput(
            compute_id="compute-001"
        )

    @pytest.fixture
    def input_with_capabilities(self):
        """Create input with capabilities filter."""
        return GetAssignmentInput(
            compute_id="compute-001",
            capabilities=["python", "react", "database"]
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_successful_assignment(self, mock_get_service, mock_work_map_service, basic_input):
        """Test successful task assignment."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment()

        result, error = await get_assignment(basic_input)

        assert error is None
        assert result is not None
        assert isinstance(result, TaskAssignment)
        assert result.task_id == "work-123"
        assert result.title == "Test Task"
        assert result.description == "Test Description"
        assert result.branch_name == "feat/test-task"
        assert "skills" in result.context
        assert result.context["skills"] == ["python", "fastapi"]
        assert result.context["base_branch"] == "main"

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_no_work_available(self, mock_get_service, mock_work_map_service, basic_input):
        """Test when no work is available for compute."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = None

        result, error = await get_assignment(basic_input)

        assert result is None
        assert error is not None
        assert isinstance(error, MCPError)
        assert error.code == "NO_WORK_AVAILABLE"
        assert "capabilities" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_capabilities_passed_to_service(self, mock_get_service, mock_work_map_service, input_with_capabilities):
        """Test that capabilities are passed to the service."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment()

        await get_assignment(input_with_capabilities)

        mock_work_map_service.get_next_assignment.assert_called_once_with(
            compute_id="compute-001",
            capabilities=["python", "react", "database"]
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_empty_capabilities_list(self, mock_get_service, mock_work_map_service, basic_input):
        """Test with no capabilities specified (should use empty list)."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment()

        await get_assignment(basic_input)

        mock_work_map_service.get_next_assignment.assert_called_once_with(
            compute_id="compute-001",
            capabilities=[]
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, basic_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await get_assignment(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"
        assert "not initialized" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_internal_error(self, mock_get_service, mock_work_map_service, basic_input):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.side_effect = Exception("Unexpected error")

        result, error = await get_assignment(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Unexpected error" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_skill_ids_defaults_to_skills(self, mock_get_service, mock_work_map_service, basic_input):
        """Test that skill_ids falls back to skills when skill_ids is empty."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment(
            skills=["python", "fastapi"],
            skill_ids=[]
        )

        result, error = await get_assignment(basic_input)

        assert error is None
        assert result is not None
        assert result.skill_ids == ["python", "fastapi"]

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_skill_ids_uses_skill_ids_when_present(self, mock_get_service, mock_work_map_service, basic_input):
        """Test that skill_ids uses skill_ids from assignment when present."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment(
            skills=["python", "fastapi"],
            skill_ids=["frontend", "react", "css"]
        )

        result, error = await get_assignment(basic_input)

        assert error is None
        assert result is not None
        assert result.skill_ids == ["frontend", "react", "css"]

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_dependency_outputs_in_context(self, mock_get_service, mock_work_map_service, basic_input):
        """Test that dependency outputs are included in context."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment(
            dependency_outputs={"work-100": {"result": "completed"}}
        )

        result, error = await get_assignment(basic_input)

        assert error is None
        assert result is not None
        assert "dependency_outputs" in result.context
        assert result.context["dependency_outputs"] == {"work-100": {"result": "completed"}}

    @pytest.mark.asyncio
    @patch("mcp.tools.assignment.get_work_map_service")
    async def test_dependencies_preserved(self, mock_get_service, mock_work_map_service, basic_input):
        """Test that dependencies are preserved in assignment."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_next_assignment.return_value = MockWorkAssignment(
            dependencies=["work-001", "work-002"]
        )

        result, error = await get_assignment(basic_input)

        assert error is None
        assert result is not None
        assert result.dependencies == ["work-001", "work-002"]


class TestGetAssignmentInputModel:
    """Test cases for the GetAssignmentInput model."""

    def test_required_compute_id(self):
        """Test that compute_id is required."""
        input_data = GetAssignmentInput(compute_id="compute-001")
        assert input_data.compute_id == "compute-001"
        assert input_data.capabilities is None

    def test_capabilities_optional(self):
        """Test that capabilities is optional."""
        input_data = GetAssignmentInput(
            compute_id="compute-001",
            capabilities=["python", "docker"]
        )
        assert input_data.capabilities == ["python", "docker"]

    def test_empty_capabilities_list(self):
        """Test input with empty capabilities list."""
        input_data = GetAssignmentInput(
            compute_id="compute-001",
            capabilities=[]
        )
        assert input_data.capabilities == []
