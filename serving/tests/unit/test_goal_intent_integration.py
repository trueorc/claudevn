"""Tests for goal intent integration with GoalService and API endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.goal_service import GoalService
from services.goal_intent_service import GoalIntentService
from models.work_map import (
    Goal, GoalIntentType, GoalStatus, GoalAdjustIntentRequest,
    GoalCreateRequest, IntentSignal, IssuePriority,
)


# =============================================================================
# GoalService Intent Tests
# =============================================================================


@pytest.fixture
def service():
    """Create GoalService without Redis."""
    return GoalService(redis_client=None)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.hset = AsyncMock()
    redis._redis.hgetall = AsyncMock(return_value={})
    redis._redis.delete = AsyncMock()
    redis._redis.sadd = AsyncMock()
    redis._redis.srem = AsyncMock()
    redis._redis.scan = AsyncMock(return_value=(0, []))
    redis._prefix = "claudevn:"
    return redis


@pytest.fixture
def service_with_redis(mock_redis):
    """Create GoalService with mocked Redis."""
    return GoalService(redis_client=mock_redis)


class TestGoalServiceAdjustIntent:
    """Test GoalService.adjust_goal_intent."""

    @pytest.mark.asyncio
    async def test_adjust_primary_intent(self, service):
        """Test adjusting primary intent."""
        request = GoalCreateRequest(
            title="Test", description="Test", project_id="proj_1"
        )
        goal = await service.create_goal(request)

        adjust = GoalAdjustIntentRequest(
            primary_intent=GoalIntentType.CONSOLIDATION,
            intent_strength=0.8,
        )
        result = await service.adjust_goal_intent(goal.goal_id, adjust)

        assert result is not None
        assert result.primary_intent == GoalIntentType.CONSOLIDATION
        assert result.intent_strength == 0.8

    @pytest.mark.asyncio
    async def test_adjust_title_and_description(self, service):
        """Test adjusting goal title and description."""
        request = GoalCreateRequest(
            title="Old Title", description="Old desc", project_id="proj_1"
        )
        goal = await service.create_goal(request)

        adjust = GoalAdjustIntentRequest(
            title="New Title",
            description="New description",
        )
        result = await service.adjust_goal_intent(goal.goal_id, adjust)

        assert result.title == "New Title"
        assert result.description == "New description"

    @pytest.mark.asyncio
    async def test_adjust_with_reparse(self, service):
        """Test that reparse_intent re-analyzes goal text."""
        request = GoalCreateRequest(
            title="Build new feature",
            description="Create and implement authentication",
            project_id="proj_1"
        )
        goal = await service.create_goal(request)
        assert goal.primary_intent is None  # Not yet classified

        adjust = GoalAdjustIntentRequest(reparse_intent=True)
        result = await service.adjust_goal_intent(goal.goal_id, adjust)

        assert result.primary_intent is not None
        assert len(result.intent_signals) > 0

    @pytest.mark.asyncio
    async def test_adjust_nonexistent_goal(self, service):
        """Test adjusting a goal that doesn't exist."""
        adjust = GoalAdjustIntentRequest(
            primary_intent=GoalIntentType.EXPANSION
        )
        result = await service.adjust_goal_intent("nonexistent", adjust)
        assert result is None

    @pytest.mark.asyncio
    async def test_adjust_deleted_goal(self, service):
        """Test that deleted goals cannot be adjusted."""
        request = GoalCreateRequest(
            title="Test", description="Test", project_id="proj_1"
        )
        goal = await service.create_goal(request)
        await service.delete_goal(goal.goal_id)

        adjust = GoalAdjustIntentRequest(
            primary_intent=GoalIntentType.EXPANSION
        )
        result = await service.adjust_goal_intent(goal.goal_id, adjust)
        assert result is None


class TestGoalServiceRetire:
    """Test GoalService.retire_goal."""

    @pytest.mark.asyncio
    async def test_retire_active_goal(self, service):
        """Test retiring an active goal."""
        request = GoalCreateRequest(
            title="Test", description="Test", project_id="proj_1"
        )
        goal = await service.create_goal(request)

        result = await service.retire_goal(goal.goal_id)
        assert result is not None
        assert result.status == GoalStatus.RETIRED

    @pytest.mark.asyncio
    async def test_retire_already_retired(self, service):
        """Test retiring an already retired goal returns it."""
        request = GoalCreateRequest(
            title="Test", description="Test", project_id="proj_1"
        )
        goal = await service.create_goal(request)
        await service.retire_goal(goal.goal_id)

        result = await service.retire_goal(goal.goal_id)
        assert result is not None
        assert result.status == GoalStatus.RETIRED

    @pytest.mark.asyncio
    async def test_retire_nonexistent(self, service):
        """Test retiring a nonexistent goal."""
        result = await service.retire_goal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_retire_deleted_goal(self, service):
        """Test that deleted goals cannot be retired."""
        request = GoalCreateRequest(
            title="Test", description="Test", project_id="proj_1"
        )
        goal = await service.create_goal(request)
        await service.delete_goal(goal.goal_id)

        result = await service.retire_goal(goal.goal_id)
        assert result is None


class TestListActiveGoals:
    """Test GoalService.list_active_goals."""

    @pytest.mark.asyncio
    async def test_returns_active_goals(self, service):
        """Test that only active goals are returned."""
        # Create goals in different states
        g1 = await service.create_goal(GoalCreateRequest(
            title="Active", description="Active goal", project_id="proj_1"
        ))
        g2 = await service.create_goal(GoalCreateRequest(
            title="Also active", description="Active goal 2", project_id="proj_1"
        ))
        g3 = await service.create_goal(GoalCreateRequest(
            title="Different project", description="Other", project_id="proj_2"
        ))

        active = await service.list_active_goals("proj_1")
        goal_ids = [g.goal_id for g in active]

        assert g1.goal_id in goal_ids
        assert g2.goal_id in goal_ids
        assert g3.goal_id not in goal_ids  # Different project

    @pytest.mark.asyncio
    async def test_excludes_retired(self, service):
        """Test that retired goals are excluded."""
        g1 = await service.create_goal(GoalCreateRequest(
            title="Active", description="Active", project_id="proj_1"
        ))
        g2 = await service.create_goal(GoalCreateRequest(
            title="To retire", description="Will retire", project_id="proj_1"
        ))
        await service.retire_goal(g2.goal_id)

        active = await service.list_active_goals("proj_1")
        goal_ids = [g.goal_id for g in active]

        assert g1.goal_id in goal_ids
        assert g2.goal_id not in goal_ids

    @pytest.mark.asyncio
    async def test_excludes_deleted(self, service):
        """Test that deleted goals are excluded."""
        g1 = await service.create_goal(GoalCreateRequest(
            title="Active", description="Active", project_id="proj_1"
        ))
        g2 = await service.create_goal(GoalCreateRequest(
            title="Deleted", description="Will delete", project_id="proj_1"
        ))
        await service.delete_goal(g2.goal_id)

        active = await service.list_active_goals("proj_1")
        goal_ids = [g.goal_id for g in active]

        assert g1.goal_id in goal_ids
        assert g2.goal_id not in goal_ids


class TestGoalServiceRedisIntentPersistence:
    """Test that intent fields are persisted to Redis."""

    @pytest.mark.asyncio
    async def test_save_includes_intent_fields(self, service_with_redis, mock_redis):
        """Test that _save_goal_to_redis includes intent fields."""
        request = GoalCreateRequest(
            title="Build feature", description="Create new API",
            project_id="proj_1"
        )
        goal = await service_with_redis.create_goal(request)

        # Manually set intent
        goal.primary_intent = GoalIntentType.EXPANSION
        goal.intent_strength = 0.75
        goal.intent_signals = [IntentSignal(
            intent_type=GoalIntentType.EXPANSION,
            strength=0.75,
            detected_from="goal_text",
            keywords_matched=["build", "create"],
        )]
        await service_with_redis._save_goal_to_redis(goal)

        # Verify hset was called with intent fields
        call_args = mock_redis._redis.hset.call_args
        mapping = call_args.kwargs.get('mapping') or call_args[1].get('mapping')
        assert mapping['primary_intent'] == 'expansion'
        assert mapping['intent_strength'] == '0.75'
        assert 'intent_signals' in mapping
        assert '"expansion"' in mapping['intent_signals']


# =============================================================================
# API Endpoint Tests
# =============================================================================


@pytest.fixture
def app():
    """Create test FastAPI app with goals router."""
    from api.work_map import goals_router
    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestAdjustIntentAPI:
    """Test PATCH /goals/{goal_id}/intent endpoint."""

    def test_adjust_intent(self, client):
        """Test adjusting goal intent via API."""
        mock_goal = Goal(
            goal_id="goal_123",
            title="Test",
            description="Test",
            project_id="proj_1",
            primary_intent=GoalIntentType.EXPANSION,
            intent_strength=0.8,
            status=GoalStatus.IN_PROGRESS,
        )

        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=mock_goal)
        mock_service.adjust_goal_intent = AsyncMock(return_value=mock_goal)

        with patch("api.work_map.get_goal_service", return_value=mock_service):
            response = client.patch(
                "/api/v1/goals/goal_123/intent",
                json={
                    "primary_intent": "consolidation",
                    "intent_strength": 0.9,
                }
            )

        assert response.status_code == 200
        data = response.json()
        assert data["goal_id"] == "goal_123"

    def test_adjust_intent_not_found(self, client):
        """Test 404 when goal not found."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=None)

        with patch("api.work_map.get_goal_service", return_value=mock_service):
            response = client.patch(
                "/api/v1/goals/nonexistent/intent",
                json={"primary_intent": "expansion"}
            )

        assert response.status_code == 404


class TestRetireGoalAPI:
    """Test POST /goals/{goal_id}/retire endpoint."""

    def test_retire_goal(self, client):
        """Test retiring a goal via API."""
        mock_goal = Goal(
            goal_id="goal_123",
            title="Test",
            description="Test",
            project_id="proj_1",
            status=GoalStatus.RETIRED,
        )

        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=mock_goal)
        mock_service.retire_goal = AsyncMock(return_value=mock_goal)

        with patch("api.work_map.get_goal_service", return_value=mock_service):
            response = client.post("/api/v1/goals/goal_123/retire")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "retired"

    def test_retire_not_found(self, client):
        """Test 404 when goal not found."""
        mock_service = MagicMock()
        mock_service.get_goal = AsyncMock(return_value=None)

        with patch("api.work_map.get_goal_service", return_value=mock_service):
            response = client.post("/api/v1/goals/nonexistent/retire")

        assert response.status_code == 404


class TestGoalConflictsAPI:
    """Test GET /goals/project/{project_id}/conflicts endpoint."""

    def test_get_conflicts(self, client):
        """Test getting conflicts between goals."""
        mock_goal_service = MagicMock()
        mock_goal_service.list_active_goals = AsyncMock(return_value=[])

        mock_intent_service = GoalIntentService()

        with patch("api.work_map.get_goal_service", return_value=mock_goal_service), \
             patch("api.work_map.get_goal_intent_service", return_value=mock_intent_service):
            response = client.get("/api/v1/goals/project/proj_1/conflicts")

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "proj_1"
        assert data["conflicts"] == []
        assert data["total"] == 0

    def test_get_conflicts_with_tension(self, client):
        """Test getting conflicts when goals have opposing intents."""
        expansion_goal = Goal(
            goal_id="goal_a", title="Build", description="Create",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.EXPANSION, intent_strength=0.8,
        )
        consolidation_goal = Goal(
            goal_id="goal_b", title="Stabilize", description="Fix",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.CONSOLIDATION, intent_strength=0.7,
        )

        mock_goal_service = MagicMock()
        mock_goal_service.list_active_goals = AsyncMock(
            return_value=[expansion_goal, consolidation_goal]
        )

        mock_intent_service = GoalIntentService()

        with patch("api.work_map.get_goal_service", return_value=mock_goal_service), \
             patch("api.work_map.get_goal_intent_service", return_value=mock_intent_service):
            response = client.get("/api/v1/goals/project/proj_1/conflicts")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        assert len(data["conflicts"]) > 0
