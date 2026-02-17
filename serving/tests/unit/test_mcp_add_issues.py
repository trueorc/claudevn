"""Unit tests for claudevn_add_issues MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.issues import AddIssuesInput, AddIssuesResponse, add_issues
from mcp.models import MCPError
from models.work_map import (
    Goal, GoalStatus, IssuePriority,
    IssueBatchCreateResponse, IssueType, IssueArea
)


class TestAddIssuesTool:
    """Test cases for the add_issues tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_goal = AsyncMock()
        service.create_issues_batch = AsyncMock()
        return service

    @pytest.fixture
    def sample_goal(self):
        """Create a sample goal."""
        return Goal(
            goal_id="goal-001",
            title="Test Goal",
            description="Test goal description",
            priority=IssuePriority.P1,
            status=GoalStatus.PLANNING,
            project_id="proj_test123"
        )

    @pytest.fixture
    def simple_issues_input(self):
        """Create simple issues input without dependencies."""
        return AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Design schema",
                    "description": "Design database schema",
                    "type": "feature",
                    "area": "database",
                    "priority": "P1"
                },
                {
                    "title": "Implement API",
                    "description": "Create REST API endpoints",
                    "type": "feature",
                    "area": "api",
                    "priority": "P2"
                }
            ]
        )

    @pytest.fixture
    def issues_with_dependencies_input(self):
        """Create issues input with internal dependencies."""
        return AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Design schema",
                    "description": "Design database schema",
                    "type": "feature"
                },
                {
                    "title": "Implement model",
                    "description": "Create data models",
                    "type": "feature",
                    "depends_on": [0]  # Depends on first issue (array index)
                },
                {
                    "title": "Add tests",
                    "description": "Add unit tests",
                    "type": "test",
                    "depends_on": [1]  # Depends on second issue
                }
            ]
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_successful_batch_creation(self, mock_get_service, mock_work_map_service, sample_goal, simple_issues_input):
        """Test successful batch issue creation."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[
                {"index": 0, "id": "issue-001"},
                {"index": 1, "id": "issue-002"}
            ],
            ready_count=2,
            backlog_count=0
        )

        result, error = await add_issues(simple_issues_input)

        assert error is None
        assert result is not None
        assert isinstance(result, AddIssuesResponse)
        assert result.success is True
        assert result.goal_id == "goal-001"
        assert len(result.created_issues) == 2
        assert result.ready_count == 2
        assert result.backlog_count == 0

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_successful_batch_with_dependencies(self, mock_get_service, mock_work_map_service, sample_goal, issues_with_dependencies_input):
        """Test batch creation with dependencies creates backlog items."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[
                {"index": 0, "id": "issue-001"},
                {"index": 1, "id": "issue-002"},
                {"index": 2, "id": "issue-003"}
            ],
            ready_count=1,  # Only first issue ready
            backlog_count=2  # Two dependent issues in backlog
        )

        result, error = await add_issues(issues_with_dependencies_input)

        assert error is None
        assert result is not None
        assert result.success is True
        assert result.ready_count == 1
        assert result.backlog_count == 2
        assert len(result.created_issues) == 3

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_goal_not_found(self, mock_get_service, mock_work_map_service, simple_issues_input):
        """Test error when goal doesn't exist."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = None

        result, error = await add_issues(simple_issues_input)

        assert result is None
        assert error is not None
        assert isinstance(error, MCPError)
        assert error.code == "GOAL_NOT_FOUND"
        assert "goal-001" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_invalid_issue_data(self, mock_get_service, mock_work_map_service, sample_goal):
        """Test error when issue data is invalid."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal

        # Create input with invalid issue (missing required fields)
        invalid_input = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {"title": "Valid issue", "description": "Valid description"},
                {"title": "Invalid issue"},  # Missing description
            ]
        )

        result, error = await add_issues(invalid_input)

        assert result is None
        assert error is not None
        assert error.code == "INVALID_ISSUE"
        assert "index 1" in error.message
        assert error.details["index"] == 1

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_invalid_enum_value(self, mock_get_service, mock_work_map_service, sample_goal):
        """Test error when enum value is invalid."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal

        # Create input with invalid enum
        invalid_input = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Test issue",
                    "description": "Test description",
                    "type": "invalid_type"  # Invalid IssueType
                }
            ]
        )

        result, error = await add_issues(invalid_input)

        assert result is None
        assert error is not None
        assert error.code == "INVALID_ISSUE"
        assert "index 0" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, simple_issues_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await add_issues(simple_issues_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"
        assert "not initialized" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_internal_error(self, mock_get_service, mock_work_map_service, sample_goal, simple_issues_input):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.side_effect = Exception("Unexpected error")

        result, error = await add_issues(simple_issues_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_enum_conversion_type(self, mock_get_service, mock_work_map_service, sample_goal):
        """Test that type string is correctly converted to IssueType enum."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[{"index": 0, "id": "issue-001"}],
            ready_count=1,
            backlog_count=0
        )

        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Test",
                    "description": "Test",
                    "type": "feature"  # String value
                }
            ]
        )

        result, error = await add_issues(input_data)

        assert error is None
        assert result is not None

        # Verify the service was called with correct enum
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        assert batch_request.issues[0].issue_type == IssueType.FEATURE

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_enum_conversion_area(self, mock_get_service, mock_work_map_service, sample_goal):
        """Test that area string is correctly converted to IssueArea enum."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[{"index": 0, "id": "issue-001"}],
            ready_count=1,
            backlog_count=0
        )

        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Test",
                    "description": "Test",
                    "area": "api"  # String value
                }
            ]
        )

        result, error = await add_issues(input_data)

        assert error is None
        assert result is not None

        # Verify the service was called with correct enum
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        assert batch_request.issues[0].area == IssueArea.API

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_enum_conversion_priority(self, mock_get_service, mock_work_map_service, sample_goal):
        """Test that priority string is correctly converted to IssuePriority enum."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[{"index": 0, "id": "issue-001"}],
            ready_count=1,
            backlog_count=0
        )

        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Test",
                    "description": "Test",
                    "priority": "P0"  # String value
                }
            ]
        )

        result, error = await add_issues(input_data)

        assert error is None
        assert result is not None

        # Verify the service was called with correct enum
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        assert batch_request.issues[0].priority == IssuePriority.P0

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_handles_array_index_dependencies(self, mock_get_service, mock_work_map_service, sample_goal, issues_with_dependencies_input):
        """Test that array index dependencies are passed through correctly."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[
                {"index": 0, "id": "issue-001"},
                {"index": 1, "id": "issue-002"},
                {"index": 2, "id": "issue-003"}
            ],
            ready_count=1,
            backlog_count=2
        )

        result, error = await add_issues(issues_with_dependencies_input)

        assert error is None
        assert result is not None

        # Verify the service was called with correct dependencies
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        assert batch_request.issues[0].depends_on == []
        assert batch_request.issues[1].depends_on == [0]
        assert batch_request.issues[2].depends_on == [1]

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_project_id_inherited_from_goal(self, mock_get_service, mock_work_map_service, sample_goal, simple_issues_input):
        """Test that issues inherit project_id from their parent goal."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[
                {"index": 0, "id": "issue-001"},
                {"index": 1, "id": "issue-002"}
            ],
            ready_count=2,
            backlog_count=0
        )

        result, error = await add_issues(simple_issues_input)

        assert error is None
        assert result is not None

        # Verify every issue in the batch has the goal's project_id
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        for issue_req in batch_request.issues:
            assert issue_req.project_id == "proj_test123"

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_project_id_none_when_goal_has_no_project(self, mock_get_service, mock_work_map_service):
        """Test that project_id is None when goal has no project_id."""
        mock_get_service.return_value = mock_work_map_service
        goal_without_project = Goal(
            goal_id="goal-002",
            title="No Project Goal",
            description="Goal without project",
            priority=IssuePriority.P2,
            status=GoalStatus.PLANNING,
            project_id=None
        )
        mock_work_map_service.get_goal.return_value = goal_without_project
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-002",
            created_issues=[{"index": 0, "id": "issue-001"}],
            ready_count=1,
            backlog_count=0
        )

        input_data = AddIssuesInput(
            goal_id="goal-002",
            issues=[{"title": "Test", "description": "Test desc"}]
        )

        result, error = await add_issues(input_data)

        assert error is None
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        assert batch_request.issues[0].project_id is None

    @pytest.mark.asyncio
    @patch("mcp.tools.issues.get_work_map_service")
    async def test_required_skills_preserved(self, mock_get_service, mock_work_map_service, sample_goal):
        """Test that required_skills are passed through correctly."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.create_issues_batch.return_value = IssueBatchCreateResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[{"index": 0, "id": "issue-001"}],
            ready_count=1,
            backlog_count=0
        )

        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Test",
                    "description": "Test",
                    "required_skills": ["python", "fastapi"]
                }
            ]
        )

        result, error = await add_issues(input_data)

        assert error is None
        assert result is not None

        # Verify the service was called with correct skills
        batch_request = mock_work_map_service.create_issues_batch.call_args[0][0]
        assert batch_request.issues[0].required_skills == ["python", "fastapi"]


class TestAddIssuesInputModel:
    """Test cases for the AddIssuesInput model."""

    def test_required_fields(self):
        """Test that required fields are enforced."""
        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {"title": "Test", "description": "Test description"}
            ]
        )

        assert input_data.goal_id == "goal-001"
        assert len(input_data.issues) == 1
        assert input_data.issues[0]["title"] == "Test"

    def test_empty_issues_list(self):
        """Test input with empty issues list."""
        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[]
        )

        assert input_data.goal_id == "goal-001"
        assert len(input_data.issues) == 0

    def test_issues_with_all_fields(self):
        """Test input with all optional fields populated."""
        input_data = AddIssuesInput(
            goal_id="goal-001",
            issues=[
                {
                    "title": "Test",
                    "description": "Test description",
                    "type": "feature",
                    "area": "api",
                    "priority": "P1",
                    "required_skills": ["python"],
                    "depends_on": [0, 1]
                }
            ]
        )

        assert len(input_data.issues) == 1
        issue = input_data.issues[0]
        assert issue["type"] == "feature"
        assert issue["area"] == "api"
        assert issue["priority"] == "P1"
        assert issue["required_skills"] == ["python"]
        assert issue["depends_on"] == [0, 1]


class TestAddIssuesResponseModel:
    """Test cases for the AddIssuesResponse model."""

    def test_model_creation(self):
        """Test creating an add issues response."""
        response = AddIssuesResponse(
            success=True,
            goal_id="goal-001",
            created_issues=[
                {"index": 0, "id": "issue-001"},
                {"index": 1, "id": "issue-002"}
            ],
            ready_count=1,
            backlog_count=1
        )

        assert response.success is True
        assert response.goal_id == "goal-001"
        assert len(response.created_issues) == 2
        assert response.ready_count == 1
        assert response.backlog_count == 1

    def test_empty_created_issues(self):
        """Test response with no created issues."""
        response = AddIssuesResponse(
            success=False,
            goal_id="goal-001",
            created_issues=[],
            ready_count=0,
            backlog_count=0
        )

        assert response.success is False
        assert len(response.created_issues) == 0
        assert response.ready_count == 0
        assert response.backlog_count == 0
