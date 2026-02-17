"""Unit tests for claudevn_add_requirement MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.requirement import add_requirement, PRIORITY_MAP
from mcp.models import AddRequirementInput, RequirementResponse, MCPError
from models.work_map import IssuePriority, IssueStatus


class TestAddRequirementTool:
    """Test cases for the add_requirement tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_work = AsyncMock()
        service.get_issue = AsyncMock()
        service.create_issue = AsyncMock()
        return service

    @pytest.fixture
    def mock_parent_work(self):
        """Create a mock parent work item."""
        work = MagicMock()
        work.work_id = "work-123"
        work.title = "Parent Work"
        return work

    @pytest.fixture
    def mock_parent_issue(self):
        """Create a mock parent issue."""
        issue = MagicMock()
        issue.issue_id = "issue-123"
        issue.title = "Parent Issue"
        issue.goal_id = "goal-001"
        return issue

    @pytest.fixture
    def mock_created_issue(self):
        """Create a mock created issue."""
        issue = MagicMock()
        issue.issue_id = "issue-456"
        issue.title = "Add password reset endpoint"
        issue.status = IssueStatus.BACKLOG
        return issue

    @pytest.fixture
    def basic_input(self):
        """Create basic requirement input."""
        return AddRequirementInput(
            title="Add password reset endpoint",
            description="During auth implementation, identified need for password reset flow.",
            parent_task_id="work-123"
        )

    @pytest.fixture
    def full_input(self):
        """Create requirement input with all optional fields."""
        return AddRequirementInput(
            title="Add password reset endpoint",
            description="During auth implementation, identified need for password reset flow.",
            parent_task_id="work-123",
            suggested_skills=["code-writer", "email-integration"],
            dependencies=["work-100"],
            priority="high"
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_successful_requirement_from_work(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue, basic_input
    ):
        """Test successful requirement creation when parent is a work item."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        result, error = await add_requirement(basic_input)

        assert error is None
        assert result is not None
        assert isinstance(result, RequirementResponse)
        assert result.acknowledged is True
        assert result.new_task_id == "issue-456"
        assert result.status == "added_to_backlog"

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_successful_requirement_from_issue(
        self, mock_get_service, mock_work_map_service, mock_parent_issue,
        mock_created_issue, basic_input
    ):
        """Test successful requirement creation when parent is an issue (no work item)."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = None  # No work item
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        result, error = await add_requirement(basic_input)

        assert error is None
        assert result is not None
        assert result.acknowledged is True
        assert result.new_task_id == "issue-456"

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_parent_task_not_found(
        self, mock_get_service, mock_work_map_service, basic_input
    ):
        """Test error when parent task doesn't exist."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = None
        mock_work_map_service.get_issue.return_value = None

        result, error = await add_requirement(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "PARENT_TASK_NOT_FOUND"
        assert "work-123" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_parent_automatically_added_as_dependency(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue, basic_input
    ):
        """Test that parent task is automatically added as a dependency."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        await add_requirement(basic_input)

        # Check that create_issue was called with parent in depends_on
        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]  # First positional argument
        assert "work-123" in request.depends_on

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_parent_not_duplicated_in_dependencies(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue
    ):
        """Test that parent is not duplicated if already in dependencies."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        input_data = AddRequirementInput(
            title="Test",
            description="Test",
            parent_task_id="work-123",
            dependencies=["work-123", "work-100"]  # Parent already in list
        )

        await add_requirement(input_data)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        # Parent should appear only once
        assert request.depends_on.count("work-123") == 1

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_priority_mapping_critical(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue
    ):
        """Test critical priority is mapped to P0."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        input_data = AddRequirementInput(
            title="Critical issue",
            description="Test",
            parent_task_id="work-123",
            priority="critical"
        )

        await add_requirement(input_data)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.priority == IssuePriority.P0

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_priority_mapping_high(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue
    ):
        """Test high priority is mapped to P1."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        input_data = AddRequirementInput(
            title="High priority",
            description="Test",
            parent_task_id="work-123",
            priority="high"
        )

        await add_requirement(input_data)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.priority == IssuePriority.P1

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_priority_mapping_normal(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue
    ):
        """Test normal priority is mapped to P2."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        input_data = AddRequirementInput(
            title="Normal priority",
            description="Test",
            parent_task_id="work-123",
            priority="normal"
        )

        await add_requirement(input_data)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.priority == IssuePriority.P2

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_priority_mapping_low(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue
    ):
        """Test low priority is mapped to P3."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        input_data = AddRequirementInput(
            title="Low priority",
            description="Test",
            parent_task_id="work-123",
            priority="low"
        )

        await add_requirement(input_data)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.priority == IssuePriority.P3

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_priority_default_when_not_specified(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue, basic_input
    ):
        """Test default priority is P2 when not specified."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        await add_requirement(basic_input)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.priority == IssuePriority.P2

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_priority_case_insensitive(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue
    ):
        """Test priority mapping is case insensitive."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        input_data = AddRequirementInput(
            title="Test",
            description="Test",
            parent_task_id="work-123",
            priority="HIGH"  # Uppercase
        )

        await add_requirement(input_data)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.priority == IssuePriority.P1

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_suggested_skills_passed_through(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue, full_input
    ):
        """Test that suggested_skills are passed as required_skills."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        await add_requirement(full_input)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert "code-writer" in request.required_skills
        assert "email-integration" in request.required_skills

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_goal_id_inherited_from_parent(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue, basic_input
    ):
        """Test that goal_id is inherited from parent issue."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        await add_requirement(basic_input)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.goal_id == "goal-001"

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_parent_issue_id_set(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, mock_created_issue, basic_input
    ):
        """Test that parent_issue_id is set correctly."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.return_value = mock_created_issue

        await add_requirement(basic_input)

        call_args = mock_work_map_service.create_issue.call_args
        request = call_args[0][0]
        assert request.parent_issue_id == "work-123"

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, basic_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await add_requirement(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"
        assert "not initialized" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.requirement.get_work_map_service")
    async def test_internal_error(
        self, mock_get_service, mock_work_map_service, mock_parent_work,
        mock_parent_issue, basic_input
    ):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_parent_work
        mock_work_map_service.get_issue.return_value = mock_parent_issue
        mock_work_map_service.create_issue.side_effect = Exception("Database error")

        result, error = await add_requirement(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Database error" in error.message


class TestPriorityMapping:
    """Test cases for priority mapping."""

    def test_all_priorities_mapped(self):
        """Test that all expected priority strings are mapped."""
        expected_priorities = ["critical", "high", "normal", "low"]
        for priority in expected_priorities:
            assert priority in PRIORITY_MAP

    def test_priority_values(self):
        """Test correct priority enum values."""
        assert PRIORITY_MAP["critical"] == IssuePriority.P0
        assert PRIORITY_MAP["high"] == IssuePriority.P1
        assert PRIORITY_MAP["normal"] == IssuePriority.P2
        assert PRIORITY_MAP["low"] == IssuePriority.P3


class TestAddRequirementInputModel:
    """Test cases for the AddRequirementInput model."""

    def test_required_fields(self):
        """Test that required fields are enforced."""
        input_data = AddRequirementInput(
            title="Test requirement",
            description="Test description",
            parent_task_id="work-123"
        )

        assert input_data.title == "Test requirement"
        assert input_data.description == "Test description"
        assert input_data.parent_task_id == "work-123"
        assert input_data.suggested_skills is None
        assert input_data.dependencies is None
        assert input_data.priority is None

    def test_optional_fields(self):
        """Test optional fields."""
        input_data = AddRequirementInput(
            title="Test requirement",
            description="Test description",
            parent_task_id="work-123",
            suggested_skills=["skill-1", "skill-2"],
            dependencies=["work-100", "work-101"],
            priority="high"
        )

        assert input_data.suggested_skills == ["skill-1", "skill-2"]
        assert input_data.dependencies == ["work-100", "work-101"]
        assert input_data.priority == "high"

    def test_missing_required_field_raises(self):
        """Test that missing required fields raise validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            AddRequirementInput(
                title="Test",
                description="Test"
                # Missing parent_task_id
            )


class TestRequirementResponseModel:
    """Test cases for the RequirementResponse model."""

    def test_model_creation(self):
        """Test creating a requirement response."""
        response = RequirementResponse(
            acknowledged=True,
            new_task_id="issue-456",
            status="added_to_backlog"
        )

        assert response.acknowledged is True
        assert response.new_task_id == "issue-456"
        assert response.status == "added_to_backlog"

    def test_different_status(self):
        """Test response with different status."""
        response = RequirementResponse(
            acknowledged=True,
            new_task_id="issue-789",
            status="ready"
        )

        assert response.status == "ready"
