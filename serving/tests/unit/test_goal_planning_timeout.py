"""Tests for goal planning timeout and recovery (Issue #435).

Tests cover:
- GoalStatus.FAILED enum value
- planning_started_at and planning_error fields on Goal
- GoalService timeout detection methods
- GoalService retry_goal_planning method
- Admin API endpoints (stale-planning, cleanup-stale, retry-planning)
- Redis persistence of new fields
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.goal_service import GoalService, get_goal_service, set_goal_service
from models.work_map import (
    Goal, GoalStatus, GoalCreateRequest, GoalListResponse
)


# ============================================================================
# Fixtures
# ============================================================================


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
def service():
    """Create service without Redis for in-memory testing."""
    return GoalService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """Create service with mocked Redis."""
    return GoalService(redis_client=mock_redis)


@pytest.fixture
def sample_goal_request():
    """Create a sample goal creation request."""
    return GoalCreateRequest(
        title="Test Goal",
        description="Test goal description",
        priority="P1",
        project_id="project_123"
    )


# ============================================================================
# GoalStatus.FAILED Tests
# ============================================================================


class TestGoalStatusFailed:
    """Test FAILED status in GoalStatus enum."""

    def test_failed_status_exists(self):
        """Test that FAILED status is a valid GoalStatus."""
        assert GoalStatus.FAILED == "failed"
        assert GoalStatus.FAILED.value == "failed"

    def test_failed_status_in_enum_values(self):
        """Test that FAILED is included in all GoalStatus values."""
        values = [s.value for s in GoalStatus]
        assert "failed" in values

    def test_goal_can_be_created_with_failed_status(self):
        """Test that a Goal can have FAILED status."""
        goal = Goal(
            goal_id="goal_test123",
            title="Failed Goal",
            description="A failed goal",
            status=GoalStatus.FAILED,
            planning_error="Decomposition timed out"
        )
        assert goal.status == GoalStatus.FAILED
        assert goal.planning_error == "Decomposition timed out"


# ============================================================================
# Goal Model New Fields Tests
# ============================================================================


class TestGoalPlanningFields:
    """Test planning_started_at and planning_error fields on Goal."""

    def test_goal_default_planning_started_at_is_none(self):
        """Test that planning_started_at defaults to None."""
        goal = Goal(
            goal_id="goal_test123",
            title="Test",
            description="Test"
        )
        assert goal.planning_started_at is None

    def test_goal_default_planning_error_is_none(self):
        """Test that planning_error defaults to None."""
        goal = Goal(
            goal_id="goal_test123",
            title="Test",
            description="Test"
        )
        assert goal.planning_error is None

    def test_goal_with_planning_started_at(self):
        """Test setting planning_started_at on a Goal."""
        now = datetime.now(timezone.utc)
        goal = Goal(
            goal_id="goal_test123",
            title="Test",
            description="Test",
            planning_started_at=now
        )
        assert goal.planning_started_at == now

    def test_goal_with_planning_error(self):
        """Test setting planning_error on a Goal."""
        goal = Goal(
            goal_id="goal_test123",
            title="Test",
            description="Test",
            status=GoalStatus.FAILED,
            planning_error="Timeout after 300s"
        )
        assert goal.planning_error == "Timeout after 300s"


# ============================================================================
# GoalService.mark_planning_started Tests
# ============================================================================


class TestMarkPlanningStarted:
    """Test GoalService.mark_planning_started method."""

    @pytest.mark.asyncio
    async def test_mark_planning_started(self, service, sample_goal_request):
        """Test marking planning as started."""
        goal = await service.create_goal(sample_goal_request)

        updated = await service.mark_planning_started(goal.goal_id)

        assert updated is not None
        assert updated.planning_started_at is not None
        assert updated.planning_error is None

    @pytest.mark.asyncio
    async def test_mark_planning_started_clears_error(self, service, sample_goal_request):
        """Test that mark_planning_started clears any previous error."""
        goal = await service.create_goal(sample_goal_request)

        # Set a previous error
        await service.mark_planning_failed(goal.goal_id, "Previous error")

        # Reset to planning and mark started
        service._goals[goal.goal_id].status = GoalStatus.PLANNING
        updated = await service.mark_planning_started(goal.goal_id)

        assert updated.planning_error is None
        assert updated.planning_started_at is not None

    @pytest.mark.asyncio
    async def test_mark_planning_started_nonexistent(self, service):
        """Test marking nonexistent goal returns None."""
        result = await service.mark_planning_started("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_planning_started_persists_to_redis(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test that planning_started_at is saved to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_started(goal.goal_id)

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('planning_started_at') != ''
        assert mapping.get('planning_error') == ''


# ============================================================================
# GoalService.mark_planning_failed Tests
# ============================================================================


class TestMarkPlanningFailed:
    """Test GoalService.mark_planning_failed method."""

    @pytest.mark.asyncio
    async def test_mark_planning_failed(self, service, sample_goal_request):
        """Test marking planning as failed."""
        goal = await service.create_goal(sample_goal_request)

        updated = await service.mark_planning_failed(goal.goal_id, "Timeout")

        assert updated is not None
        assert updated.status == GoalStatus.FAILED
        assert updated.planning_error == "Timeout"

    @pytest.mark.asyncio
    async def test_mark_planning_failed_nonexistent(self, service):
        """Test marking nonexistent goal returns None."""
        result = await service.mark_planning_failed("nonexistent", "Error")
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_planning_failed_persists_to_redis(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test that FAILED status and error are saved to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_failed(goal.goal_id, "Test error")

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('status') == 'failed'
        assert mapping.get('planning_error') == 'Test error'


# ============================================================================
# GoalService.get_stale_planning_goals Tests
# ============================================================================


class TestGetStalePlanningGoals:
    """Test GoalService.get_stale_planning_goals method."""

    @pytest.mark.asyncio
    async def test_no_stale_goals(self, service, sample_goal_request):
        """Test returns empty list when no goals are stale."""
        goal = await service.create_goal(sample_goal_request)
        await service.mark_planning_started(goal.goal_id)

        stale = await service.get_stale_planning_goals(timeout_seconds=300)
        assert stale == []

    @pytest.mark.asyncio
    async def test_detects_stale_goal_by_planning_started_at(self, service, sample_goal_request):
        """Test detection of stale goal via planning_started_at."""
        goal = await service.create_goal(sample_goal_request)

        # Set planning_started_at to 10 minutes ago
        service._goals[goal.goal_id].planning_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )

        stale = await service.get_stale_planning_goals(timeout_seconds=300)
        assert len(stale) == 1
        assert stale[0].goal_id == goal.goal_id

    @pytest.mark.asyncio
    async def test_detects_stale_goal_by_created_at_fallback(self, service, sample_goal_request):
        """Test detection of stale goal using created_at when planning_started_at is None."""
        goal = await service.create_goal(sample_goal_request)

        # Set created_at to 10 minutes ago, no planning_started_at
        service._goals[goal.goal_id].created_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        service._goals[goal.goal_id].planning_started_at = None

        stale = await service.get_stale_planning_goals(timeout_seconds=300)
        assert len(stale) == 1
        assert stale[0].goal_id == goal.goal_id

    @pytest.mark.asyncio
    async def test_excludes_non_planning_goals(self, service, sample_goal_request):
        """Test that goals not in PLANNING status are excluded."""
        goal = await service.create_goal(sample_goal_request)

        # Set old created_at but transition to IN_PROGRESS
        service._goals[goal.goal_id].created_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        await service.update_goal_status(goal.goal_id, GoalStatus.IN_PROGRESS)

        stale = await service.get_stale_planning_goals(timeout_seconds=300)
        assert stale == []

    @pytest.mark.asyncio
    async def test_excludes_deleted_goals(self, service, sample_goal_request):
        """Test that soft-deleted goals are excluded."""
        goal = await service.create_goal(sample_goal_request)

        # Set old created_at and soft delete
        service._goals[goal.goal_id].created_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        await service.delete_goal(goal.goal_id)

        stale = await service.get_stale_planning_goals(timeout_seconds=300)
        assert stale == []

    @pytest.mark.asyncio
    async def test_respects_timeout_parameter(self, service, sample_goal_request):
        """Test that timeout parameter is respected."""
        goal = await service.create_goal(sample_goal_request)

        # Set planning_started_at to 3 minutes ago
        service._goals[goal.goal_id].planning_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=3)
        )

        # With 5 minute timeout, should NOT be stale
        stale = await service.get_stale_planning_goals(timeout_seconds=300)
        assert stale == []

        # With 2 minute timeout, SHOULD be stale
        stale = await service.get_stale_planning_goals(timeout_seconds=120)
        assert len(stale) == 1


# ============================================================================
# GoalService.fail_stale_planning_goals Tests
# ============================================================================


class TestFailStalePlanningGoals:
    """Test GoalService.fail_stale_planning_goals method."""

    @pytest.mark.asyncio
    async def test_transitions_stale_goals_to_failed(self, service, sample_goal_request):
        """Test that stale goals are transitioned to FAILED."""
        goal = await service.create_goal(sample_goal_request)

        # Make goal stale
        service._goals[goal.goal_id].planning_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )

        failed = await service.fail_stale_planning_goals(timeout_seconds=300)

        assert len(failed) == 1
        assert failed[0].status == GoalStatus.FAILED
        assert "timed out" in failed[0].planning_error

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_stale_goals(self, service, sample_goal_request):
        """Test returns empty list when no goals are stale."""
        await service.create_goal(sample_goal_request)

        failed = await service.fail_stale_planning_goals(timeout_seconds=300)
        assert failed == []

    @pytest.mark.asyncio
    async def test_transitions_multiple_stale_goals(self, service):
        """Test that multiple stale goals are all transitioned."""
        for i in range(3):
            goal = await service.create_goal(GoalCreateRequest(
                title=f"Goal {i}",
                description=f"Stale planning goal {i}",
                project_id="project_123"
            ))
            service._goals[goal.goal_id].planning_started_at = (
                datetime.now(timezone.utc) - timedelta(minutes=10)
            )

        failed = await service.fail_stale_planning_goals(timeout_seconds=300)
        assert len(failed) == 3
        assert all(g.status == GoalStatus.FAILED for g in failed)


# ============================================================================
# GoalService.retry_goal_planning Tests
# ============================================================================


class TestRetryGoalPlanning:
    """Test GoalService.retry_goal_planning method."""

    @pytest.mark.asyncio
    async def test_retry_resets_failed_goal(self, service, sample_goal_request):
        """Test that retry resets a FAILED goal to PLANNING."""
        goal = await service.create_goal(sample_goal_request)
        await service.mark_planning_failed(goal.goal_id, "Timeout")

        retried = await service.retry_goal_planning(goal.goal_id)

        assert retried is not None
        assert retried.status == GoalStatus.PLANNING
        assert retried.planning_started_at is None
        assert retried.planning_error is None
        assert retried.decomposition_id is None
        assert retried.issue_ids == []

    @pytest.mark.asyncio
    async def test_retry_nonexistent_goal(self, service):
        """Test retry on nonexistent goal returns None."""
        result = await service.retry_goal_planning("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_retry_non_failed_goal_returns_none(self, service, sample_goal_request):
        """Test retry on a non-FAILED goal returns None."""
        goal = await service.create_goal(sample_goal_request)
        # Goal is in PLANNING, not FAILED
        result = await service.retry_goal_planning(goal.goal_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_retry_clears_decomposition_id(self, service, sample_goal_request):
        """Test that retry clears decomposition_id."""
        goal = await service.create_goal(sample_goal_request)
        await service.update_goal_decomposition_id(goal.goal_id, "decomp-old")
        await service.mark_planning_failed(goal.goal_id, "Error")

        retried = await service.retry_goal_planning(goal.goal_id)
        assert retried.decomposition_id is None

    @pytest.mark.asyncio
    async def test_retry_persists_to_redis(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test that retry state is persisted to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_failed(goal.goal_id, "Error")
        await service_with_redis.retry_goal_planning(goal.goal_id)

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('status') == 'planning'
        assert mapping.get('planning_error') == ''
        assert mapping.get('planning_started_at') == ''
        assert mapping.get('decomposition_id') == ''


# ============================================================================
# Admin API Endpoint Tests
# ============================================================================


class TestStalePlanningEndpoint:
    """Test GET /goals/stale-planning endpoint."""

    @pytest.fixture
    def app(self):
        """Create test FastAPI app with goals router."""
        from api.work_map import goals_router
        app = FastAPI()
        app.include_router(goals_router)
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Set up service mocks for API tests."""
        mock_service = GoalService(redis_client=None)
        set_goal_service(mock_service)
        yield mock_service

    @pytest.mark.asyncio
    async def test_get_stale_planning_empty(self, client, setup_mocks):
        """Test getting stale planning goals when none exist."""
        response = client.get("/goals/stale-planning")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_stale_planning_with_stale_goal(self, client, setup_mocks):
        """Test getting stale planning goals."""
        service = setup_mocks
        goal = await service.create_goal(GoalCreateRequest(
            title="Stale Goal",
            description="Test",
            project_id="project_123"
        ))
        service._goals[goal.goal_id].planning_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )

        response = client.get("/goals/stale-planning?timeout=300")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["goal_id"] == goal.goal_id

    @pytest.mark.asyncio
    async def test_get_stale_planning_custom_timeout(self, client, setup_mocks):
        """Test custom timeout parameter."""
        service = setup_mocks
        goal = await service.create_goal(GoalCreateRequest(
            title="Goal",
            description="Test",
            project_id="project_123"
        ))
        service._goals[goal.goal_id].planning_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=2)
        )

        # 5 minute timeout - not stale
        response = client.get("/goals/stale-planning?timeout=300")
        assert response.status_code == 200
        assert len(response.json()) == 0

        # 1 minute timeout - stale
        response = client.get("/goals/stale-planning?timeout=60")
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestCleanupStaleEndpoint:
    """Test POST /goals/cleanup-stale endpoint."""

    @pytest.fixture
    def app(self):
        from api.work_map import goals_router
        app = FastAPI()
        app.include_router(goals_router)
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        mock_service = GoalService(redis_client=None)
        set_goal_service(mock_service)
        yield mock_service

    @pytest.mark.asyncio
    async def test_cleanup_stale_no_goals(self, client, setup_mocks):
        """Test cleanup when no stale goals exist."""
        response = client.post("/goals/cleanup-stale?timeout=300")
        assert response.status_code == 200
        data = response.json()
        assert data["transitioned_count"] == 0
        assert data["failed_goal_ids"] == []

    @pytest.mark.asyncio
    async def test_cleanup_stale_transitions_goals(self, client, setup_mocks):
        """Test cleanup transitions stale goals to FAILED."""
        service = setup_mocks
        goal = await service.create_goal(GoalCreateRequest(
            title="Stale Goal",
            description="Test",
            project_id="project_123"
        ))
        service._goals[goal.goal_id].planning_started_at = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )

        response = client.post("/goals/cleanup-stale?timeout=300")
        assert response.status_code == 200
        data = response.json()
        assert data["transitioned_count"] == 1
        assert goal.goal_id in data["failed_goal_ids"]

        # Verify goal is now FAILED
        updated = await service.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.FAILED


class TestRetryPlanningEndpoint:
    """Test POST /goals/{goal_id}/retry-planning endpoint."""

    @pytest.fixture
    def app(self):
        from api.work_map import goals_router
        app = FastAPI()
        app.include_router(goals_router)
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        mock_service = GoalService(redis_client=None)
        set_goal_service(mock_service)
        yield mock_service

    @pytest.mark.asyncio
    async def test_retry_planning_success(self, client, setup_mocks):
        """Test retrying planning for a FAILED goal."""
        service = setup_mocks
        goal = await service.create_goal(GoalCreateRequest(
            title="Failed Goal",
            description="Test",
            project_id="project_123"
        ))
        await service.mark_planning_failed(goal.goal_id, "Timeout")

        response = client.post(f"/goals/{goal.goal_id}/retry-planning")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "planning"
        assert data["planning_error"] is None

    @pytest.mark.asyncio
    async def test_retry_planning_not_found(self, client, setup_mocks):
        """Test retrying planning for nonexistent goal."""
        response = client.post("/goals/nonexistent/retry-planning")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_planning_not_failed(self, client, setup_mocks):
        """Test retrying planning for a goal that isn't FAILED."""
        service = setup_mocks
        goal = await service.create_goal(GoalCreateRequest(
            title="Planning Goal",
            description="Test",
            project_id="project_123"
        ))

        response = client.post(f"/goals/{goal.goal_id}/retry-planning")
        assert response.status_code == 400
        assert "not in FAILED status" in response.json()["detail"]


# ============================================================================
# Redis Persistence Tests
# ============================================================================


class TestRedisPersistence:
    """Test Redis persistence of new fields."""

    @pytest.mark.asyncio
    async def test_planning_started_at_persists(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test planning_started_at is saved and can be read from Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_started(goal.goal_id)

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        # Verify it's a non-empty ISO format string
        assert mapping['planning_started_at'] != ''
        datetime.fromisoformat(mapping['planning_started_at'])  # Should not raise

    @pytest.mark.asyncio
    async def test_planning_error_persists(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test planning_error is saved to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_failed(goal.goal_id, "Test error msg")

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping['planning_error'] == 'Test error msg'

    @pytest.mark.asyncio
    async def test_none_fields_persist_as_empty_string(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test None values for new fields are persisted as empty strings."""
        await service_with_redis.create_goal(sample_goal_request)

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('planning_started_at') == ''
        assert mapping.get('planning_error') == ''

    @pytest.mark.asyncio
    async def test_failed_status_persists(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test that FAILED status value is saved correctly to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_failed(goal.goal_id, "Error")

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping['status'] == 'failed'

    @pytest.mark.asyncio
    async def test_status_index_updated_on_fail(
        self, service_with_redis, mock_redis, sample_goal_request
    ):
        """Test that Redis status index is updated when goal transitions to FAILED."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.mark_planning_failed(goal.goal_id, "Error")

        # Verify srem was called to remove from planning index
        srem_calls = mock_redis._redis.srem.call_args_list
        assert any(
            "goal:status:planning" in str(call)
            for call in srem_calls
        )

        # Verify sadd was called to add to failed index
        sadd_calls = mock_redis._redis.sadd.call_args_list
        assert any(
            "goal:status:failed" in str(call)
            for call in sadd_calls
        )
