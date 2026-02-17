"""Unit tests for goal project context enforcement.

Tests that goals require project_id and properly filter by project.
Verifies issue #411 acceptance criteria (backend).
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.work_map import (
    Goal, GoalStatus, GoalCreateRequest, GoalListResponse,
    IssuePriority, ConversationStatus
)
from services.goal_service import GoalService


@pytest.fixture
def goal_service():
    """Create a GoalService without Redis for testing."""
    service = GoalService(redis_client=None)
    service._initialized = True
    # Mock Redis save to avoid actual Redis calls
    service._save_goal_to_redis = AsyncMock()
    return service


@pytest.fixture
def sample_goals(goal_service):
    """Create sample goals across different projects."""
    goals = [
        Goal(
            goal_id="goal_001",
            title="Build authentication",
            description="Implement user authentication",
            project_id="project_a",
            priority=IssuePriority.P1,
            status=GoalStatus.PLANNING,
            conversation_status=ConversationStatus.NO_COMMENTS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        Goal(
            goal_id="goal_002",
            title="Add dashboard",
            description="Create main dashboard page",
            project_id="project_a",
            priority=IssuePriority.P2,
            status=GoalStatus.IN_PROGRESS,
            conversation_status=ConversationStatus.NO_COMMENTS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        Goal(
            goal_id="goal_003",
            title="Setup CI/CD",
            description="Configure CI/CD pipeline",
            project_id="project_b",
            priority=IssuePriority.P1,
            status=GoalStatus.PLANNING,
            conversation_status=ConversationStatus.NO_COMMENTS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        Goal(
            goal_id="goal_004",
            title="Legacy goal without project",
            description="A goal from before project enforcement",
            project_id=None,
            priority=IssuePriority.P3,
            status=GoalStatus.PLANNING,
            conversation_status=ConversationStatus.NO_COMMENTS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]

    for goal in goals:
        goal_service._goals[goal.goal_id] = goal

    return goals


class TestGoalCreateWithProject:
    """Tests for goal creation with project_id."""

    @pytest.mark.asyncio
    async def test_create_goal_with_project_id(self, goal_service):
        """Goal creation succeeds when project_id is provided."""
        request = GoalCreateRequest(
            title="New feature",
            description="Build new feature",
            project_id="project_a",
        )
        goal = await goal_service.create_goal(request)

        assert goal.project_id == "project_a"
        assert goal.title == "New feature"
        assert goal.status == GoalStatus.PLANNING

    @pytest.mark.asyncio
    async def test_create_goal_without_project_id(self, goal_service):
        """Goal creation still works at service level without project_id.

        Validation happens at API layer, not service layer, for backward
        compatibility during migration.
        """
        request = GoalCreateRequest(
            title="Orphan goal",
            description="Goal without project",
        )
        goal = await goal_service.create_goal(request)

        assert goal.project_id is None
        assert goal.title == "Orphan goal"

    @pytest.mark.asyncio
    async def test_create_goal_preserves_priority(self, goal_service):
        """Goal creation preserves custom priority."""
        request = GoalCreateRequest(
            title="Urgent feature",
            description="Must do now",
            project_id="project_a",
            priority=IssuePriority.P0,
        )
        goal = await goal_service.create_goal(request)

        assert goal.priority == IssuePriority.P0
        assert goal.project_id == "project_a"


class TestGoalListByProject:
    """Tests for filtering goals by project_id."""

    @pytest.mark.asyncio
    async def test_list_goals_no_filter(self, goal_service, sample_goals):
        """List all goals when no project filter is applied."""
        result = await goal_service.list_goals()
        assert result.total == 4

    @pytest.mark.asyncio
    async def test_list_goals_filter_project_a(self, goal_service, sample_goals):
        """List goals filtered to project A."""
        result = await goal_service.list_goals(project_id="project_a")
        assert result.total == 2
        assert all(g.project_id == "project_a" for g in result.items)

    @pytest.mark.asyncio
    async def test_list_goals_filter_project_b(self, goal_service, sample_goals):
        """List goals filtered to project B."""
        result = await goal_service.list_goals(project_id="project_b")
        assert result.total == 1
        assert result.items[0].project_id == "project_b"
        assert result.items[0].goal_id == "goal_003"

    @pytest.mark.asyncio
    async def test_list_goals_filter_nonexistent_project(self, goal_service, sample_goals):
        """List goals for a project with no goals returns empty."""
        result = await goal_service.list_goals(project_id="project_x")
        assert result.total == 0
        assert len(result.items) == 0


class TestGoalAPIProjectValidation:
    """Tests for API-level project_id validation."""

    @pytest.mark.asyncio
    async def test_api_rejects_goal_without_project_id(self):
        """API endpoint rejects goal creation without project_id."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        # Import the router
        from api.work_map import goals_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(goals_router)

        client = TestClient(app)

        response = client.post("/goals", json={
            "title": "Test goal",
            "description": "Missing project_id"
        })

        assert response.status_code == 400
        assert "project_id is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_api_accepts_goal_with_project_id(self):
        """API endpoint accepts goal creation with project_id."""
        from fastapi.testclient import TestClient

        from api.work_map import goals_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(goals_router)

        # Mock the work map service
        mock_goal = Goal(
            goal_id="goal_test",
            title="Test goal",
            description="Has project_id",
            project_id="project_a",
            priority=IssuePriority.P1,
            status=GoalStatus.PLANNING,
            conversation_status=ConversationStatus.NO_COMMENTS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("api.work_map.get_work_map_service") as mock_service:
            mock_svc = MagicMock()
            mock_svc.create_goal = AsyncMock(return_value=mock_goal)
            mock_service.return_value = mock_svc

            client = TestClient(app)
            response = client.post("/goals", json={
                "title": "Test goal",
                "description": "Has project_id",
                "project_id": "project_a"
            })

            assert response.status_code == 201
            assert response.json()["project_id"] == "project_a"
