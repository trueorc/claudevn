"""Tests for CommentRollupService."""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.comment_rollup_service import (
    CommentRollupService,
    get_comment_rollup_service,
    set_comment_rollup_service
)
from models.work_map import (
    GoalComment,
    RollupBatch,
    RollupConfig,
    RollupStatus,
    EvaluationStatus,
    IssuePriority,
    IssueArea
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.get = AsyncMock(return_value=None)
    redis._redis.set = AsyncMock()
    redis._redis.delete = AsyncMock()
    redis._redis.expire = AsyncMock()
    redis._redis.scan = AsyncMock(return_value=(0, []))
    redis._prefix = "claudevn:"
    return redis


@pytest.fixture
def default_config():
    """Create default rollup configuration."""
    return RollupConfig(
        rollup_window_seconds=30,
        quiet_period_seconds=10,
        enabled=True
    )


@pytest.fixture
def service(default_config):
    """Create service without Redis for in-memory testing."""
    return CommentRollupService(redis_client=None, config=default_config)


@pytest.fixture
def service_with_redis(mock_redis, default_config):
    """Create service with mocked Redis."""
    return CommentRollupService(redis_client=mock_redis, config=default_config)


@pytest.fixture
def sample_comment():
    """Create a sample comment."""
    return GoalComment(
        comment_id="comment_test123",
        goal_id="goal_test123",
        content="Test comment content",
        priority=IssuePriority.P1,
        area=IssueArea.API,
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
        created_by="test_user"
    )


@pytest.fixture
def sample_comment_2():
    """Create a second sample comment."""
    return GoalComment(
        comment_id="comment_test456",
        goal_id="goal_test123",
        content="Second test comment",
        priority=IssuePriority.P2,
        area=IssueArea.FRONTEND,
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
        created_by="test_user"
    )


class TestCommentRollupServiceInit:
    """Test CommentRollupService initialization."""

    def test_init_without_redis(self, default_config):
        """Test initialization without Redis client."""
        service = CommentRollupService(config=default_config)
        assert service._redis is None
        assert service._active_batches == {}
        assert service._default_config == default_config
        assert service._initialized is False

    def test_init_with_redis(self, mock_redis, default_config):
        """Test initialization with Redis client."""
        service = CommentRollupService(redis_client=mock_redis, config=default_config)
        assert service._redis is mock_redis

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization."""
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self, service_with_redis, mock_redis):
        """Test service initialization loads from Redis."""
        await service_with_redis.initialize()
        assert service_with_redis._initialized is True
        mock_redis._redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_shutdown_cancels_timers(self, service):
        """Test shutdown cancels all timers."""
        await service.initialize()
        # Create a dummy timer
        service._timers["test_goal"] = asyncio.create_task(asyncio.sleep(100))
        await service.shutdown()
        assert len(service._timers) == 0


class TestRollupConfiguration:
    """Test rollup configuration management."""

    def test_get_default_config(self, service, default_config):
        """Test getting default configuration."""
        config = service.get_config()
        assert config.rollup_window_seconds == default_config.rollup_window_seconds
        assert config.quiet_period_seconds == default_config.quiet_period_seconds
        assert config.enabled == default_config.enabled

    def test_set_default_config(self, service):
        """Test setting default configuration."""
        new_config = RollupConfig(
            rollup_window_seconds=60,
            quiet_period_seconds=20,
            enabled=True
        )
        service.set_config(new_config)
        config = service.get_config()
        assert config.rollup_window_seconds == 60
        assert config.quiet_period_seconds == 20

    def test_set_goal_specific_config(self, service):
        """Test setting goal-specific configuration."""
        goal_config = RollupConfig(
            rollup_window_seconds=45,
            quiet_period_seconds=15,
            enabled=True
        )
        service.set_config(goal_config, goal_id="goal_123")

        # Goal-specific config
        config = service.get_config("goal_123")
        assert config.rollup_window_seconds == 45

        # Other goals get default
        default = service.get_config("other_goal")
        assert default.rollup_window_seconds == 30

    def test_disabled_config(self, service):
        """Test disabled configuration."""
        disabled_config = RollupConfig(enabled=False)
        service.set_config(disabled_config)
        config = service.get_config()
        assert config.enabled is False


class TestAddComment:
    """Test adding comments to rollup."""

    @pytest.mark.asyncio
    async def test_add_first_comment_creates_batch(self, service, sample_comment):
        """Test adding first comment creates a new batch."""
        await service.initialize()

        batch = await service.add_comment(sample_comment.goal_id, sample_comment)

        assert batch is not None
        assert batch.goal_id == sample_comment.goal_id
        assert sample_comment.comment_id in batch.comment_ids
        assert batch.status == RollupStatus.COLLECTING
        assert len(batch.comment_ids) == 1

    @pytest.mark.asyncio
    async def test_add_second_comment_extends_batch(self, service, sample_comment, sample_comment_2):
        """Test adding second comment extends existing batch."""
        await service.initialize()

        batch1 = await service.add_comment(sample_comment.goal_id, sample_comment)
        batch2 = await service.add_comment(sample_comment_2.goal_id, sample_comment_2)

        assert batch2.batch_id == batch1.batch_id
        assert len(batch2.comment_ids) == 2
        assert sample_comment.comment_id in batch2.comment_ids
        assert sample_comment_2.comment_id in batch2.comment_ids

    @pytest.mark.asyncio
    async def test_force_evaluate_bypasses_rollup(self, service, sample_comment):
        """Test force_evaluate=True bypasses rollup."""
        await service.initialize()

        callback_called = False
        callback_args = None

        async def mock_callback(goal_id, comment_ids):
            nonlocal callback_called, callback_args
            callback_called = True
            callback_args = (goal_id, comment_ids)

        service.set_evaluation_callback(mock_callback)

        batch = await service.add_comment(
            sample_comment.goal_id,
            sample_comment,
            force_evaluate=True
        )

        assert batch is None  # No batch created
        assert callback_called is True
        assert callback_args == (sample_comment.goal_id, [sample_comment.comment_id])

    @pytest.mark.asyncio
    async def test_disabled_rollup_bypasses_rollup(self, sample_comment):
        """Test disabled rollup evaluates immediately."""
        disabled_config = RollupConfig(enabled=False)
        service = CommentRollupService(config=disabled_config)
        await service.initialize()

        callback_called = False

        async def mock_callback(goal_id, comment_ids):
            nonlocal callback_called
            callback_called = True

        service.set_evaluation_callback(mock_callback)

        batch = await service.add_comment(sample_comment.goal_id, sample_comment)

        assert batch is None
        assert callback_called is True

    @pytest.mark.asyncio
    async def test_duplicate_comment_not_added_twice(self, service, sample_comment):
        """Test same comment ID not added twice to batch."""
        await service.initialize()

        batch1 = await service.add_comment(sample_comment.goal_id, sample_comment)
        batch2 = await service.add_comment(sample_comment.goal_id, sample_comment)

        assert len(batch2.comment_ids) == 1

    @pytest.mark.asyncio
    async def test_different_goals_get_separate_batches(self, service, sample_comment):
        """Test different goals get separate batches."""
        await service.initialize()

        comment_goal_2 = GoalComment(
            comment_id="comment_other",
            goal_id="goal_other",
            content="Other goal comment",
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
            created_by="user"
        )

        batch1 = await service.add_comment(sample_comment.goal_id, sample_comment)
        batch2 = await service.add_comment(comment_goal_2.goal_id, comment_goal_2)

        assert batch1.batch_id != batch2.batch_id
        assert batch1.goal_id == "goal_test123"
        assert batch2.goal_id == "goal_other"


class TestRollupStatus:
    """Test rollup status tracking."""

    @pytest.mark.asyncio
    async def test_get_status_no_batch(self, service, sample_comment):
        """Test getting status with no active batch."""
        await service.initialize()

        status = await service.get_status(sample_comment.goal_id)

        assert status.goal_id == sample_comment.goal_id
        assert status.has_active_batch is False
        assert status.batch is None
        assert status.pending_comment_count == 0

    @pytest.mark.asyncio
    async def test_get_status_with_batch(self, service, sample_comment, sample_comment_2):
        """Test getting status with active batch."""
        await service.initialize()

        await service.add_comment(sample_comment.goal_id, sample_comment)
        await service.add_comment(sample_comment_2.goal_id, sample_comment_2)

        status = await service.get_status(sample_comment.goal_id)

        assert status.has_active_batch is True
        assert status.batch is not None
        assert status.pending_comment_count == 2
        assert status.batch.status == RollupStatus.COLLECTING

    @pytest.mark.asyncio
    async def test_get_pending_goals(self, service, sample_comment):
        """Test getting list of pending goals."""
        await service.initialize()

        # Initially empty
        assert await service.get_pending_goals() == []

        # Add a comment
        await service.add_comment(sample_comment.goal_id, sample_comment)

        goals = await service.get_pending_goals()
        assert sample_comment.goal_id in goals


class TestForceEvaluate:
    """Test force evaluation functionality."""

    @pytest.mark.asyncio
    async def test_force_evaluate_triggers_callback(self, service, sample_comment):
        """Test force_evaluate triggers evaluation callback."""
        await service.initialize()

        callback_called = False
        callback_args = None

        async def mock_callback(goal_id, comment_ids):
            nonlocal callback_called, callback_args
            callback_called = True
            callback_args = (goal_id, comment_ids)

        service.set_evaluation_callback(mock_callback)

        await service.add_comment(sample_comment.goal_id, sample_comment)
        result = await service.force_evaluate(sample_comment.goal_id)

        assert result is True
        assert callback_called is True
        assert callback_args[0] == sample_comment.goal_id
        assert sample_comment.comment_id in callback_args[1]

    @pytest.mark.asyncio
    async def test_force_evaluate_no_batch(self, service, sample_comment):
        """Test force_evaluate with no active batch returns False."""
        await service.initialize()

        result = await service.force_evaluate(sample_comment.goal_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_force_evaluate_clears_batch(self, service, sample_comment):
        """Test force_evaluate clears the batch after completion."""
        await service.initialize()

        async def mock_callback(goal_id, comment_ids):
            pass

        service.set_evaluation_callback(mock_callback)

        await service.add_comment(sample_comment.goal_id, sample_comment)
        await service.force_evaluate(sample_comment.goal_id)

        status = await service.get_status(sample_comment.goal_id)
        assert status.has_active_batch is False


class TestEvaluationTimer:
    """Test automatic evaluation timing."""

    @pytest.mark.asyncio
    async def test_evaluation_scheduled_after_add(self, service, sample_comment):
        """Test evaluation is scheduled after adding comment."""
        await service.initialize()

        await service.add_comment(sample_comment.goal_id, sample_comment)

        assert sample_comment.goal_id in service._timers

    @pytest.mark.asyncio
    async def test_timer_cancelled_on_force_evaluate(self, service, sample_comment):
        """Test timer is cancelled when force evaluate is called."""
        await service.initialize()

        async def mock_callback(goal_id, comment_ids):
            pass

        service.set_evaluation_callback(mock_callback)

        await service.add_comment(sample_comment.goal_id, sample_comment)
        assert sample_comment.goal_id in service._timers

        await service.force_evaluate(sample_comment.goal_id)
        assert sample_comment.goal_id not in service._timers


class TestRollupBatchModel:
    """Test RollupBatch model."""

    def test_batch_creation(self):
        """Test creating a rollup batch."""
        batch = RollupBatch(
            batch_id="batch_test123",
            goal_id="goal_test123",
            comment_ids=["comment_1", "comment_2"],
            status=RollupStatus.COLLECTING
        )

        assert batch.batch_id == "batch_test123"
        assert batch.goal_id == "goal_test123"
        assert len(batch.comment_ids) == 2
        assert batch.status == RollupStatus.COLLECTING

    def test_batch_status_transitions(self):
        """Test batch status values."""
        assert RollupStatus.COLLECTING.value == "collecting"
        assert RollupStatus.WAITING.value == "waiting"
        assert RollupStatus.PROCESSING.value == "processing"
        assert RollupStatus.COMPLETED.value == "completed"


class TestRollupConfigModel:
    """Test RollupConfig model."""

    def test_config_defaults(self):
        """Test configuration defaults."""
        config = RollupConfig()

        assert config.rollup_window_seconds == 30
        assert config.quiet_period_seconds == 10
        assert config.enabled is True

    def test_config_custom_values(self):
        """Test configuration with custom values."""
        config = RollupConfig(
            rollup_window_seconds=60,
            quiet_period_seconds=20,
            enabled=False
        )

        assert config.rollup_window_seconds == 60
        assert config.quiet_period_seconds == 20
        assert config.enabled is False

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid ranges
        config = RollupConfig(rollup_window_seconds=1, quiet_period_seconds=1)
        assert config.rollup_window_seconds == 1

        config = RollupConfig(rollup_window_seconds=300, quiet_period_seconds=60)
        assert config.rollup_window_seconds == 300


class TestGlobalInstance:
    """Test global instance management."""

    def test_set_get_service(self, service):
        """Test setting and getting global service."""
        set_comment_rollup_service(service)

        retrieved = get_comment_rollup_service()
        assert retrieved is service

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_comment_rollup_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_comment_rollup_service()


class TestRedisIntegration:
    """Test Redis persistence integration."""

    @pytest.mark.asyncio
    async def test_save_batch_to_redis(self, service_with_redis, mock_redis, sample_comment):
        """Test batch is saved to Redis."""
        await service_with_redis.initialize()

        await service_with_redis.add_comment(sample_comment.goal_id, sample_comment)

        mock_redis._redis.set.assert_called()
        mock_redis._redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_delete_batch_from_redis(self, service_with_redis, mock_redis, sample_comment):
        """Test batch is deleted from Redis on completion."""
        await service_with_redis.initialize()

        async def mock_callback(goal_id, comment_ids):
            pass

        service_with_redis.set_evaluation_callback(mock_callback)

        await service_with_redis.add_comment(sample_comment.goal_id, sample_comment)
        await service_with_redis.force_evaluate(sample_comment.goal_id)

        mock_redis._redis.delete.assert_called()
