"""Tests for Slim Claude Code API endpoints.

Unit tests for the API endpoints that provide decompose, plan, and execute
operations for the Slim Claude Code feature. Tests use mocked services
to avoid real API calls or database operations.
"""

import json
import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.slim_claude_code import router
from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
    GoalDecompositionResult,
)
from models.work_map import (
    Goal,
    GoalStatus,
    Issue,
    IssueBatchCreateResponse,
    IssueStatus,
)
from models.work_planner import (
    ExecutionPhase,
    PlanRisk,
    RiskSeverity,
    WorkPlan,
)
from services.work_planner import CyclicDependencyError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_goal():
    """Create a sample goal for testing."""
    return Goal(
        goal_id="goal-123",
        title="Implement user management",
        description="Build a complete user management system with CRUD operations and authentication",
        project_id="project-test",
        priority="P1",
        status=GoalStatus.PLANNING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_decomposition_result():
    """Create a sample decomposition result for testing."""
    return GoalDecompositionResult(
        goal_id="goal-123",
        decomposition_id="decomp-abc123",
        issues=[
            DecomposedIssue(
                temp_id="issue-1",
                title="Set up database schema",
                description="Create the initial database schema",
                issue_type="feature",
                priority="P1",
                area="database",
                required_skills=["sql"],
                estimated_complexity=EstimatedComplexity.M,
                blocked_by=[],
                acceptance_criteria=["Schema created"],
            ),
            DecomposedIssue(
                temp_id="issue-2",
                title="Implement API endpoints",
                description="Create REST API endpoints",
                issue_type="feature",
                priority="P1",
                area="api",
                required_skills=["python", "fastapi"],
                estimated_complexity=EstimatedComplexity.L,
                blocked_by=["issue-1"],
                acceptance_criteria=["Endpoints work"],
            ),
        ],
        dependency_graph={"issue-2": ["issue-1"]},
        execution_phases=[["issue-1"], ["issue-2"]],
        confidence=0.85,
        reasoning="Logical dependency chain",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_work_plan():
    """Create a sample work plan for testing."""
    return WorkPlan(
        plan_id="plan-xyz789",
        goal_id="goal-123",
        decomposition_id="decomp-abc123",
        phases=[
            ExecutionPhase(
                phase_number=1,
                issues=["issue-1"],
                parallel=False,
                gate=None,
                description="Set up database schema",
            ),
            ExecutionPhase(
                phase_number=2,
                issues=["issue-2"],
                parallel=False,
                gate=None,
                description="Implement API endpoints",
            ),
        ],
        estimated_duration="2.5 days",
        critical_path=["issue-1", "issue-2"],
        risks=[
            PlanRisk(
                risk_id="risk-001",
                description="Database blocking",
                severity=RiskSeverity.MEDIUM,
                mitigation="Prioritize database work",
                affected_issues=["issue-1"],
            )
        ],
        recommendations=["Plan looks well-balanced"],
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_issue():
    """Create a sample issue for testing."""
    return Issue(
        issue_id="issue-real-001",
        title="Set up database schema",
        description="Create the initial database schema",
        issue_type="feature",
        priority="P1",
        area="database",
        status=IssueStatus.READY,
        required_skills=["sql"],
        depends_on=[],
        goal_id="goal-123",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_work_map_service():
    """Create a mock WorkMapService."""
    service = MagicMock()
    service.get_goal = AsyncMock()
    service.get_goal_issues = AsyncMock(return_value=[])
    service.create_issue = AsyncMock()
    service.update_goal_issues = AsyncMock()
    service.update_goal_decomposition_id = AsyncMock()
    return service


@pytest.fixture
def mock_goal_decomposer():
    """Create a mock GoalDecomposerService."""
    service = MagicMock()
    service.decompose_goal = AsyncMock()
    service.decompose_and_characterize = AsyncMock()
    service.map_to_issue_models = MagicMock()
    return service


@pytest.fixture
def mock_characterization_service():
    """Create a mock CharacterizationService."""
    service = MagicMock()
    service.characterize_items = AsyncMock()
    return service


@pytest.fixture
def mock_work_planner():
    """Create a mock WorkPlannerService."""
    service = MagicMock()
    service.create_plan_from_decomposition = AsyncMock()
    return service


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


@pytest.fixture
def mock_goal_service():
    """Create a mock GoalService."""
    service = MagicMock()
    service.mark_planning_started = AsyncMock()
    service.mark_planning_failed = AsyncMock()
    return service


@pytest.fixture
def app(
    mock_work_map_service,
    mock_goal_decomposer,
    mock_work_planner,
    mock_redis,
    mock_goal_service,
):
    """Create a FastAPI app with the slim_claude_code router for testing."""
    app = FastAPI()
    app.include_router(router)

    # Apply patches
    with patch(
        "api.slim_claude_code.get_work_map_service",
        return_value=mock_work_map_service,
    ), patch(
        "api.slim_claude_code.get_goal_decomposer_service",
        return_value=mock_goal_decomposer,
    ), patch(
        "api.slim_claude_code.get_work_planner_service",
        return_value=mock_work_planner,
    ), patch(
        "api.slim_claude_code.get_redis",
        return_value=mock_redis,
    ), patch(
        "api.slim_claude_code.get_goal_service",
        return_value=mock_goal_service,
    ):
        yield app


@pytest.fixture
def client(
    mock_work_map_service,
    mock_goal_decomposer,
    mock_work_planner,
    mock_redis,
    mock_goal_service,
):
    """Create a test client with properly patched services."""
    app = FastAPI()
    app.include_router(router)

    with patch(
        "api.slim_claude_code.get_work_map_service",
        return_value=mock_work_map_service,
    ), patch(
        "api.slim_claude_code.get_goal_decomposer_service",
        return_value=mock_goal_decomposer,
    ), patch(
        "api.slim_claude_code.get_work_planner_service",
        return_value=mock_work_planner,
    ), patch(
        "api.slim_claude_code.get_redis",
        return_value=mock_redis,
    ), patch(
        "api.slim_claude_code.get_goal_service",
        return_value=mock_goal_service,
    ):
        yield TestClient(app)


# =============================================================================
# Test: Decompose Goal Endpoint (POST /goals/{goal_id}/decompose)
# =============================================================================


class TestDecomposeGoalEndpoint:
    """Test POST /goals/{goal_id}/decompose endpoint."""

    def test_decompose_goal_success(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test successful goal decomposition."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result

        app = FastAPI()
        app.include_router(router)

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=MagicMock(mark_planning_started=AsyncMock(), mark_planning_failed=AsyncMock()),
        ):
            client = TestClient(app)

            # Act
            response = client.post("/goals/goal-123/decompose")

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["goal_id"] == "goal-123"
            assert data["decomposition_id"] == "decomp-abc123"
            assert len(data["issues"]) == 2
            assert data["confidence"] == 0.85

    def test_decompose_goal_with_constraints(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test goal decomposition with constraints."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result

        app = FastAPI()
        app.include_router(router)

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=MagicMock(mark_planning_started=AsyncMock(), mark_planning_failed=AsyncMock()),
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/decompose",
                json={"constraints": {"max_issues": 5, "focus_areas": ["api"]}},
            )

            # Assert
            assert response.status_code == 201
            mock_goal_decomposer.decompose_goal.assert_called_once()
            call_kwargs = mock_goal_decomposer.decompose_goal.call_args.kwargs
            assert call_kwargs["constraints"] == {"max_issues": 5, "focus_areas": ["api"]}

    def test_decompose_uses_project_metadata(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test decomposition uses actual project metadata instead of hardcoded defaults."""
        from models.project import Project, RepoConfig

        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result

        project = Project(
            project_id="project-test",
            name="My Project",
            description="A real project",
            repos=[
                RepoConfig(repo_id="r1", name="backend", url="git@example.com:backend.git"),
                RepoConfig(repo_id="r2", name="frontend", url="git@example.com:frontend.git"),
            ],
            metadata={"tech_stack": "Go, gRPC", "conventions": "Google style", "language": "go"},
        )

        app = FastAPI()
        app.include_router(router)

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=project)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=MagicMock(mark_planning_started=AsyncMock(), mark_planning_failed=AsyncMock()),
        ):
            client = TestClient(app)
            response = client.post("/goals/goal-123/decompose")

            assert response.status_code == 201
            call_kwargs = mock_goal_decomposer.decompose_goal.call_args.kwargs
            ctx = call_kwargs["project_context"]
            assert ctx["project_name"] == "My Project"
            assert ctx["project_description"] == "A real project"
            assert ctx["tech_stack"] == "Go, gRPC"
            assert ctx["conventions"] == "Google style"
            assert ctx["language"] == "go"
            assert ctx["repos"] == ["backend", "frontend"]

    def test_decompose_falls_back_when_project_not_found(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test decomposition falls back gracefully when project is not found."""
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result

        app = FastAPI()
        app.include_router(router)

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=MagicMock(mark_planning_started=AsyncMock(), mark_planning_failed=AsyncMock()),
        ):
            client = TestClient(app)
            response = client.post("/goals/goal-123/decompose")

            assert response.status_code == 201
            call_kwargs = mock_goal_decomposer.decompose_goal.call_args.kwargs
            ctx = call_kwargs["project_context"]
            assert ctx["tech_stack"] == "Not specified"
            assert ctx["conventions"] == "Not specified"
            assert "project_name" not in ctx

    def test_decompose_with_empty_metadata(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test decomposition with project that has no metadata fields."""
        from models.project import Project

        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result

        project = Project(
            project_id="project-test",
            name="Bare Project",
            description="",
            metadata={},
        )

        app = FastAPI()
        app.include_router(router)

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=project)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=MagicMock(mark_planning_started=AsyncMock(), mark_planning_failed=AsyncMock()),
        ):
            client = TestClient(app)
            response = client.post("/goals/goal-123/decompose")

            assert response.status_code == 201
            call_kwargs = mock_goal_decomposer.decompose_goal.call_args.kwargs
            ctx = call_kwargs["project_context"]
            assert ctx["project_name"] == "Bare Project"
            assert ctx["project_description"] == ""
            assert ctx["tech_stack"] == "Not specified"
            assert ctx["conventions"] == "Not specified"
            assert ctx["repos"] == []

    def test_decompose_goal_not_found(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
    ):
        """Test decomposition when goal doesn't exist."""
        # Arrange
        mock_work_map_service.get_goal.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post("/goals/nonexistent/decompose")

            # Assert
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


# =============================================================================
# Test: Get Decomposition Endpoint (GET /goals/{goal_id}/decompositions/{decomposition_id})
# =============================================================================


class TestGetDecompositionEndpoint:
    """Test GET /goals/{goal_id}/decompositions/{decomposition_id} endpoint."""

    def test_get_decomposition_success(
        self,
        mock_redis,
        sample_decomposition_result,
    ):
        """Test successful retrieval of decomposition."""
        # Arrange
        mock_redis.get.return_value = sample_decomposition_result.model_dump_json()

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.get("/goals/goal-123/decompositions/decomp-abc123")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["decomposition_id"] == "decomp-abc123"
            assert data["goal_id"] == "goal-123"

    def test_get_decomposition_not_found(
        self,
        mock_redis,
    ):
        """Test retrieval of non-existent decomposition."""
        # Arrange
        mock_redis.get.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.get("/goals/goal-123/decompositions/nonexistent")

            # Assert
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_decomposition_wrong_goal(
        self,
        mock_redis,
        sample_decomposition_result,
    ):
        """Test retrieval when decomposition belongs to different goal."""
        # Arrange - decomposition is for goal-123, but request is for goal-456
        mock_redis.get.return_value = sample_decomposition_result.model_dump_json()

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.get("/goals/goal-456/decompositions/decomp-abc123")

            # Assert
            assert response.status_code == 404
            assert "does not belong to goal" in response.json()["detail"]


# =============================================================================
# Test: Create Plan Endpoint (POST /goals/{goal_id}/plan)
# =============================================================================


class TestCreatePlanEndpoint:
    """Test POST /goals/{goal_id}/plan endpoint."""

    def test_create_plan_success(
        self,
        mock_work_map_service,
        mock_work_planner,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
        sample_work_plan,
    ):
        """Test successful plan creation."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_redis.get.return_value = sample_decomposition_result.model_dump_json()
        mock_work_planner.create_plan_from_decomposition.return_value = sample_work_plan

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_work_planner_service",
            return_value=mock_work_planner,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/plan",
                json={"decomposition_id": "decomp-abc123"},
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["plan_id"] == "plan-xyz789"
            assert len(data["phases"]) == 2
            assert data["estimated_duration"] == "2.5 days"

    def test_create_plan_with_constraints(
        self,
        mock_work_map_service,
        mock_work_planner,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
        sample_work_plan,
    ):
        """Test plan creation with constraints."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_redis.get.return_value = sample_decomposition_result.model_dump_json()
        mock_work_planner.create_plan_from_decomposition.return_value = sample_work_plan

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_work_planner_service",
            return_value=mock_work_planner,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/plan",
                json={
                    "decomposition_id": "decomp-abc123",
                    "constraints": {"max_parallel": 3},
                },
            )

            # Assert
            assert response.status_code == 201
            mock_work_planner.create_plan_from_decomposition.assert_called_once()

    def test_create_plan_goal_not_found(
        self,
        mock_work_map_service,
        mock_redis,
    ):
        """Test plan creation when goal doesn't exist."""
        # Arrange
        mock_work_map_service.get_goal.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/nonexistent/plan",
                json={"decomposition_id": "decomp-abc123"},
            )

            # Assert
            assert response.status_code == 404
            assert "Goal" in response.json()["detail"]

    def test_create_plan_decomposition_not_found(
        self,
        mock_work_map_service,
        mock_redis,
        sample_goal,
    ):
        """Test plan creation when decomposition doesn't exist."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_redis.get.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/plan",
                json={"decomposition_id": "nonexistent"},
            )

            # Assert
            assert response.status_code == 404
            assert "Decomposition" in response.json()["detail"]

    def test_create_plan_cyclic_dependency(
        self,
        mock_work_map_service,
        mock_work_planner,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test plan creation with cyclic dependency."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_redis.get.return_value = sample_decomposition_result.model_dump_json()
        mock_work_planner.create_plan_from_decomposition.side_effect = (
            CyclicDependencyError(["issue-1", "issue-2", "issue-1"])
        )

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_work_planner_service",
            return_value=mock_work_planner,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/plan",
                json={"decomposition_id": "decomp-abc123"},
            )

            # Assert
            assert response.status_code == 400
            assert "cyclic" in response.json()["detail"].lower()


# =============================================================================
# Test: Get Plan Endpoint (GET /goals/{goal_id}/plans/{plan_id})
# =============================================================================


class TestGetPlanEndpoint:
    """Test GET /goals/{goal_id}/plans/{plan_id} endpoint."""

    def test_get_plan_success(
        self,
        mock_redis,
        sample_work_plan,
    ):
        """Test successful retrieval of plan."""
        # Arrange
        mock_redis.get.return_value = sample_work_plan.model_dump_json()

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.get("/goals/goal-123/plans/plan-xyz789")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["plan_id"] == "plan-xyz789"
            assert data["goal_id"] == "goal-123"

    def test_get_plan_not_found(
        self,
        mock_redis,
    ):
        """Test retrieval of non-existent plan."""
        # Arrange
        mock_redis.get.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.get("/goals/goal-123/plans/nonexistent")

            # Assert
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


# =============================================================================
# Test: Execute Plan Endpoint (POST /goals/{goal_id}/execute)
# =============================================================================


class TestExecutePlanEndpoint:
    """Test POST /goals/{goal_id}/execute endpoint."""

    def test_execute_plan_success(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
        sample_work_plan,
        sample_issue,
    ):
        """Test successful plan execution."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []  # No existing issues
        mock_work_map_service.create_issue.return_value = sample_issue
        mock_work_map_service.update_goal_issues.return_value = sample_goal

        # Setup Redis to return plan then decomposition
        def redis_get_side_effect(key):
            if "plan:" in key:
                return sample_work_plan.model_dump_json()
            elif "decomposition:" in key:
                return sample_decomposition_result.model_dump_json()
            return None

        mock_redis.get.side_effect = redis_get_side_effect

        # Setup decomposer to map issues
        mock_goal_decomposer.map_to_issue_models.return_value = [
            {
                "temp_id": "issue-1",
                "title": "Set up database schema",
                "description": "Create the initial database schema",
                "type": "feature",
                "area": "database",
                "priority": "P1",
                "required_skills": ["sql"],
                "blocked_by_temp_ids": [],
            },
            {
                "temp_id": "issue-2",
                "title": "Implement API endpoints",
                "description": "Create REST API endpoints",
                "type": "feature",
                "area": "api",
                "priority": "P1",
                "required_skills": ["python", "fastapi"],
                "blocked_by_temp_ids": ["issue-1"],
            },
        ]

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/execute",
                json={"plan_id": "plan-xyz789"},
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            assert data["goal_id"] == "goal-123"
            assert len(data["created_issues"]) == 2

    def test_execute_plan_goal_not_found(
        self,
        mock_work_map_service,
        mock_redis,
    ):
        """Test plan execution when goal doesn't exist."""
        # Arrange
        mock_work_map_service.get_goal.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/nonexistent/execute",
                json={"plan_id": "plan-xyz789"},
            )

            # Assert
            assert response.status_code == 404
            assert "Goal" in response.json()["detail"]

    def test_execute_plan_already_has_issues(
        self,
        mock_work_map_service,
        mock_redis,
        sample_goal,
        sample_issue,
    ):
        """Test plan execution when goal already has issues."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = [sample_issue]

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/execute",
                json={"plan_id": "plan-xyz789"},
            )

            # Assert
            assert response.status_code == 400
            assert "already has" in response.json()["detail"]

    def test_execute_plan_not_found(
        self,
        mock_work_map_service,
        mock_redis,
        sample_goal,
    ):
        """Test plan execution when plan doesn't exist."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_redis.get.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/execute",
                json={"plan_id": "nonexistent"},
            )

            # Assert
            assert response.status_code == 404
            assert "Plan" in response.json()["detail"]

    def test_execute_plan_with_approver(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
        sample_work_plan,
        sample_issue,
    ):
        """Test plan execution with approver specified."""
        # Arrange
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []
        mock_work_map_service.create_issue.return_value = sample_issue
        mock_work_map_service.update_goal_issues.return_value = sample_goal

        def redis_get_side_effect(key):
            if "plan:" in key:
                return sample_work_plan.model_dump_json()
            elif "decomposition:" in key:
                return sample_decomposition_result.model_dump_json()
            return None

        mock_redis.get.side_effect = redis_get_side_effect

        mock_goal_decomposer.map_to_issue_models.return_value = [
            {
                "temp_id": "issue-1",
                "title": "Set up database schema",
                "description": "Create the initial database schema",
                "type": "feature",
                "area": "database",
                "priority": "P1",
                "required_skills": ["sql"],
                "blocked_by_temp_ids": [],
            },
        ]

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            # Act
            response = client.post(
                "/goals/goal-123/execute",
                json={
                    "plan_id": "plan-xyz789",
                    "approved_by": "user@example.com",
                },
            )

            # Assert
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True


# =============================================================================
# Test: Auto-Process Goal Endpoint (POST /goals/{goal_id}/auto-process)
# Now returns 202 Accepted and runs background task.
# =============================================================================


class TestAutoProcessGoalEndpoint:
    """Test POST /goals/{goal_id}/auto-process endpoint (async 202 pattern)."""

    def test_auto_process_returns_202_accepted(
        self,
        mock_work_map_service,
        mock_redis,
        sample_goal,
    ):
        """Test auto-process returns 202 Accepted with goal_id and status."""
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.post("/goals/goal-123/auto-process")

            assert response.status_code == 202
            data = response.json()
            assert data["goal_id"] == "goal-123"
            assert data["status"] == "accepted"
            assert data["stage"] == "queued"

    def test_auto_process_goal_not_found(
        self,
        mock_work_map_service,
        mock_redis,
    ):
        """Test auto-process when goal doesn't exist."""
        mock_work_map_service.get_goal.return_value = None

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.post("/goals/nonexistent/auto-process")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_auto_process_missing_project_id(
        self,
        mock_work_map_service,
        mock_redis,
    ):
        """Test auto-process returns 400 when goal has no project_id."""
        goal_no_project = Goal(
            goal_id="goal-no-project",
            title="Goal without project",
            description="Test goal",
            project_id=None,
            priority="P1",
            status=GoalStatus.PLANNING,
        )
        mock_work_map_service.get_goal.return_value = goal_no_project

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.post("/goals/goal-no-project/auto-process")

            assert response.status_code == 400
            assert "project_id" in response.json()["detail"].lower()

    def test_auto_process_goal_already_has_issues(
        self,
        mock_work_map_service,
        mock_redis,
        sample_goal,
        sample_issue,
    ):
        """Test auto-process returns 400 when goal already has issues."""
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = [sample_issue]

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.post("/goals/goal-123/auto-process")

            assert response.status_code == 400
            assert "already has" in response.json()["detail"].lower()

    def test_auto_process_rejects_when_planning_already_started(
        self,
        mock_work_map_service,
        mock_redis,
    ):
        """Test auto-process returns 400 when planning_started_at is already set."""
        goal_already_planning = Goal(
            goal_id="goal-planning",
            title="Already planning goal",
            description="Test goal",
            project_id="project-test",
            priority="P1",
            status=GoalStatus.PLANNING,
            planning_started_at=datetime(2026, 1, 30, 10, 0, 0, tzinfo=timezone.utc),
        )
        mock_work_map_service.get_goal.return_value = goal_already_planning

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.post("/goals/goal-planning/auto-process")

            assert response.status_code == 400
            assert "already has decomposition in progress" in response.json()["detail"]

    def test_auto_process_sets_initial_processing_status(
        self,
        mock_work_map_service,
        mock_redis,
        sample_goal,
    ):
        """Test that auto-process sets initial 'queued' status in Redis."""
        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.get_goal_issues.return_value = []

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.post("/goals/goal-123/auto-process")

            assert response.status_code == 202

            # Verify Redis was called to store processing status
            mock_redis.setex.assert_called()
            # Find the call that stores processing status
            for call in mock_redis.setex.call_args_list:
                key = call[0][0]
                if "processing:" in key:
                    data = json.loads(call[0][2])
                    assert data["stage"] == "queued"
                    assert data["goal_id"] == "goal-123"
                    break


# =============================================================================
# Test: Processing Status Endpoint (GET /goals/{goal_id}/processing-status)
# =============================================================================


class TestProcessingStatusEndpoint:
    """Test GET /goals/{goal_id}/processing-status endpoint."""

    def test_get_processing_status_found(
        self,
        mock_redis,
    ):
        """Test retrieving existing processing status."""
        status_data = json.dumps({
            "goal_id": "goal-123",
            "stage": "decomposing",
            "started_at": "2026-01-30T10:00:00+00:00",
        })

        def redis_get_side_effect(key):
            if "processing:" in key:
                return status_data
            return None

        mock_redis.get = AsyncMock(side_effect=redis_get_side_effect)

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.get("/goals/goal-123/processing-status")

            assert response.status_code == 200
            data = response.json()
            assert data["goal_id"] == "goal-123"
            assert data["stage"] == "decomposing"
            assert data["started_at"] is not None

    def test_get_processing_status_complete_includes_result(
        self,
        mock_redis,
    ):
        """Test that completed status includes the result payload."""
        status_data = json.dumps({
            "goal_id": "goal-123",
            "stage": "complete",
            "started_at": "2026-01-30T10:00:00+00:00",
            "completed_at": "2026-01-30T10:01:03+00:00",
            "result": {
                "success": True,
                "goal_id": "goal-123",
                "decomposition_id": "decomp-abc",
                "created_issues": [{"temp_id": "t1", "issue_id": "i1", "title": "Test", "status": "ready"}],
                "ready_count": 1,
                "backlog_count": 0,
                "confidence": 0.9,
                "reasoning": "Simple goal",
            },
        })

        def redis_get_side_effect(key):
            if "processing:" in key:
                return status_data
            return None

        mock_redis.get = AsyncMock(side_effect=redis_get_side_effect)

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.get("/goals/goal-123/processing-status")

            assert response.status_code == 200
            data = response.json()
            assert data["stage"] == "complete"
            assert data["result"]["success"] is True
            assert data["result"]["confidence"] == 0.9

    def test_get_processing_status_not_found_returns_404(
        self,
        mock_redis,
        mock_goal_service,
    ):
        """Test that missing processing status returns 404."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_goal_service.get_goal = AsyncMock(return_value=None)

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=mock_goal_service,
        ):
            client = TestClient(app)

            response = client.get("/goals/goal-999/processing-status")

            assert response.status_code == 404

    def test_get_processing_status_fallback_to_goal_planning(
        self,
        mock_redis,
        mock_goal_service,
    ):
        """Test fallback: returns decomposing if goal is in PLANNING state."""
        mock_redis.get = AsyncMock(return_value=None)

        # Goal is in PLANNING with planning_started_at set
        planning_goal = Goal(
            goal_id="goal-123",
            title="Test goal",
            description="Test",
            project_id="proj-1",
            status=GoalStatus.PLANNING,
            planning_started_at=datetime(2026, 1, 30, 10, 0, 0, tzinfo=timezone.utc),
        )
        mock_goal_service.get_goal = AsyncMock(return_value=planning_goal)

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=mock_goal_service,
        ):
            client = TestClient(app)

            response = client.get("/goals/goal-123/processing-status")

            assert response.status_code == 200
            data = response.json()
            assert data["stage"] == "decomposing"
            assert data["started_at"] is not None

    def test_get_processing_status_failed(
        self,
        mock_redis,
    ):
        """Test that failed status includes error."""
        status_data = json.dumps({
            "goal_id": "goal-123",
            "stage": "failed",
            "started_at": "2026-01-30T10:00:00+00:00",
            "completed_at": "2026-01-30T10:05:00+00:00",
            "error": "Decomposition timed out after 300s",
        })

        def redis_get_side_effect(key):
            if "processing:" in key:
                return status_data
            return None

        mock_redis.get = AsyncMock(side_effect=redis_get_side_effect)

        app = FastAPI()
        app.include_router(router)

        with patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ):
            client = TestClient(app)

            response = client.get("/goals/goal-123/processing-status")

            assert response.status_code == 200
            data = response.json()
            assert data["stage"] == "failed"
            assert "timed out" in data["error"]


# =============================================================================
# Test: Background Auto-Process Function (unit test of _auto_process_background)
# =============================================================================


class TestAutoProcessBackground:
    """Test the background processing function directly."""

    @pytest.mark.asyncio
    async def test_background_skips_when_already_active(
        self,
        mock_work_map_service,
        mock_redis,
    ):
        """Test that concurrent calls for the same goal_id are skipped."""
        from api.slim_claude_code import _active_decompositions, _auto_process_background

        # Simulate another decomposition already running for this goal
        _active_decompositions.add("goal-123")
        try:
            await _auto_process_background("goal-123", None)

            # Should have returned early — no service calls made
            mock_work_map_service.get_goal.assert_not_called()
        finally:
            _active_decompositions.discard("goal-123")

    @pytest.mark.asyncio
    async def test_background_cleans_up_active_set_on_success(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_characterization_service,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test that goal_id is removed from _active_decompositions after success."""
        from api.slim_claude_code import _active_decompositions, _auto_process_background
        from models.characterization import BatchCharacterizationResponse

        # Ensure clean state
        _active_decompositions.discard("goal-123")

        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.update_goal_issues = AsyncMock()
        mock_work_map_service.update_goal_decomposition_id = AsyncMock()
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result
        mock_characterization_service.characterize_items.return_value = BatchCharacterizationResponse(
            project_id="project-test",
            results=[],
            total=0,
            completed=0,
            failed=0,
        )
        mock_goal_decomposer.map_to_issue_models.return_value = []

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        mock_goal_svc = MagicMock()
        mock_goal_svc.mark_planning_started = AsyncMock()
        mock_goal_svc.record_decomposition_pass = AsyncMock(return_value=sample_goal)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_characterization_service",
            return_value=mock_characterization_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=mock_goal_svc,
        ):
            await _auto_process_background("goal-123", None)

        # goal_id should be cleaned up from the active set
        assert "goal-123" not in _active_decompositions

    @pytest.mark.asyncio
    async def test_background_cleans_up_active_set_on_failure(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_redis,
        mock_goal_service,
        sample_goal,
    ):
        """Test that goal_id is removed from _active_decompositions after failure."""
        from api.slim_claude_code import _active_decompositions, _auto_process_background

        # Ensure clean state
        _active_decompositions.discard("goal-123")

        mock_work_map_service.get_goal.return_value = sample_goal
        mock_goal_decomposer.decompose_goal.side_effect = RuntimeError("LLM failed")

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        mock_goal_svc = MagicMock()
        mock_goal_svc.mark_planning_started = AsyncMock()
        mock_goal_svc.mark_planning_failed = AsyncMock()

        mock_comment_service = MagicMock()
        mock_comment_service.list_comments = AsyncMock(return_value=MagicMock(items=[]))

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=mock_goal_svc,
        ), patch(
            "api.slim_claude_code.get_goal_comment_service",
            return_value=mock_comment_service,
        ):
            await _auto_process_background("goal-123", None)

        # goal_id should be cleaned up even after failure
        assert "goal-123" not in _active_decompositions

    @pytest.mark.asyncio
    async def test_background_updates_status_stages(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_characterization_service,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test that the background function transitions through stages including characterizing."""
        from api.slim_claude_code import _auto_process_background
        from models.characterization import BatchCharacterizationResponse

        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.update_goal_issues = AsyncMock()
        mock_work_map_service.update_goal_decomposition_id = AsyncMock()
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result
        mock_characterization_service.characterize_items.return_value = BatchCharacterizationResponse(
            project_id="project-test",
            results=[],
            total=2,
            completed=2,
            failed=0,
        )
        mock_goal_decomposer.map_to_issue_models.return_value = []

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        mock_goal_svc = MagicMock()
        mock_goal_svc.mark_planning_started = AsyncMock()
        mock_goal_svc.record_decomposition_pass = AsyncMock(return_value=sample_goal)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_characterization_service",
            return_value=mock_characterization_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=mock_goal_svc,
        ):
            await _auto_process_background("goal-123", None)

        # Verify status was updated through all stages: decomposing, characterizing, creating_issues, complete
        setex_calls = mock_redis.setex.call_args_list
        processing_stages = []
        for call in setex_calls:
            key = call[0][0]
            if "processing:" in key:
                data = json.loads(call[0][2])
                processing_stages.append(data["stage"])

        # The fix: verify that characterizing stage is now visible
        assert "decomposing" in processing_stages
        assert "characterizing" in processing_stages
        assert "creating_issues" in processing_stages
        assert "complete" in processing_stages

    @pytest.mark.asyncio
    async def test_background_passes_project_id_to_created_issues(
        self,
        mock_work_map_service,
        mock_goal_decomposer,
        mock_characterization_service,
        mock_redis,
        sample_goal,
        sample_decomposition_result,
    ):
        """Test that created issues inherit project_id from the goal."""
        from api.slim_claude_code import _auto_process_background
        from models.characterization import BatchCharacterizationResponse

        mock_work_map_service.get_goal.return_value = sample_goal
        mock_work_map_service.update_goal_issues = AsyncMock()
        mock_work_map_service.update_goal_decomposition_id = AsyncMock()
        mock_goal_decomposer.decompose_goal.return_value = sample_decomposition_result
        mock_characterization_service.characterize_items.return_value = BatchCharacterizationResponse(
            project_id="project-test",
            results=[],
            total=1,
            completed=1,
            failed=0,
        )

        # Return issue data that will be created (single issue, no deps)
        mock_goal_decomposer.map_to_issue_models.return_value = [
            {
                "temp_id": "issue-1",
                "title": "Set up database schema",
                "description": "Create the initial database schema",
                "type": "feature",
                "area": "database",
                "priority": "P1",
                "required_skills": ["sql"],
                "blocked_by_temp_ids": [],
            }
        ]

        # create_issue returns a mock Issue
        mock_issue = MagicMock()
        mock_issue.issue_id = "issue_abc123"
        mock_issue.title = "Set up database schema"
        mock_issue.status.value = "ready"
        mock_work_map_service.create_issue = AsyncMock(return_value=mock_issue)

        mock_project_service = MagicMock()
        mock_project_service.get_project = AsyncMock(return_value=None)

        mock_goal_svc = MagicMock()
        mock_goal_svc.mark_planning_started = AsyncMock()
        mock_goal_svc.record_decomposition_pass = AsyncMock(return_value=sample_goal)

        with patch(
            "api.slim_claude_code.get_work_map_service",
            return_value=mock_work_map_service,
        ), patch(
            "api.slim_claude_code.get_goal_decomposer_service",
            return_value=mock_goal_decomposer,
        ), patch(
            "api.slim_claude_code.get_characterization_service",
            return_value=mock_characterization_service,
        ), patch(
            "api.slim_claude_code.get_redis",
            return_value=mock_redis,
        ), patch(
            "api.slim_claude_code.get_project_service",
            return_value=mock_project_service,
        ), patch(
            "api.slim_claude_code.get_goal_service",
            return_value=mock_goal_svc,
        ):
            await _auto_process_background("goal-123", None)

        # Verify create_issue was called with project_id from the goal
        mock_work_map_service.create_issue.assert_awaited_once()
        issue_request = mock_work_map_service.create_issue.call_args[0][0]
        assert issue_request.project_id == "project-test"
