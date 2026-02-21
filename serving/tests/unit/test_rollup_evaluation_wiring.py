"""Tests for comment rollup → evaluation callback wiring.

Verifies that CommentRollupService triggers GoalEvaluationService.evaluate_batch
when a rollup batch completes. This was broken (issue #16) because the callback
was never connected in app.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.comment_rollup_service import CommentRollupService
from models.work_map import RollupConfig, RollupBatch, RollupStatus, GoalComment, CommentType


@pytest.fixture
def rollup_config():
    return RollupConfig(
        rollup_window_seconds=5,
        quiet_period_seconds=2,
        enabled=True,
    )


@pytest.fixture
def rollup_service(rollup_config):
    svc = CommentRollupService(redis_client=None, config=rollup_config)
    svc._initialized = True
    return svc


class TestEvaluationCallbackWiring:
    """Test that rollup service correctly invokes the evaluation callback."""

    @pytest.mark.asyncio
    async def test_callback_set_via_set_evaluation_callback(self, rollup_service):
        """set_evaluation_callback stores the callback."""
        callback = AsyncMock()
        rollup_service.set_evaluation_callback(callback)
        assert rollup_service._evaluation_callback is callback

    @pytest.mark.asyncio
    async def test_trigger_evaluation_calls_callback(self, rollup_service):
        """_trigger_evaluation invokes the callback with goal_id and comment_ids."""
        callback = AsyncMock()
        rollup_service.set_evaluation_callback(callback)

        # Inject a batch directly
        batch = RollupBatch(
            batch_id="batch_test",
            goal_id="goal_abc",
            comment_ids=["c1", "c2"],
            status=RollupStatus.WAITING,
        )
        rollup_service._active_batches["goal_abc"] = batch

        await rollup_service._trigger_evaluation("goal_abc")

        callback.assert_awaited_once_with("goal_abc", ["c1", "c2"])

    @pytest.mark.asyncio
    async def test_trigger_evaluation_without_callback_cleans_up(self, rollup_service):
        """Without callback, _trigger_evaluation still cleans up the batch."""
        assert rollup_service._evaluation_callback is None

        batch = RollupBatch(
            batch_id="batch_noop",
            goal_id="goal_xyz",
            comment_ids=["c1"],
            status=RollupStatus.WAITING,
        )
        rollup_service._active_batches["goal_xyz"] = batch

        await rollup_service._trigger_evaluation("goal_xyz")

        # Batch should be cleaned up even without callback
        assert "goal_xyz" not in rollup_service._active_batches

    @pytest.mark.asyncio
    async def test_force_evaluate_triggers_callback(self, rollup_service):
        """force_evaluate should invoke the callback immediately."""
        callback = AsyncMock()
        rollup_service.set_evaluation_callback(callback)

        batch = RollupBatch(
            batch_id="batch_force",
            goal_id="goal_force",
            comment_ids=["c1", "c2", "c3"],
            status=RollupStatus.COLLECTING,
        )
        rollup_service._active_batches["goal_force"] = batch

        result = await rollup_service.force_evaluate("goal_force")

        assert result is True
        callback.assert_awaited_once_with("goal_force", ["c1", "c2", "c3"])

    @pytest.mark.asyncio
    async def test_add_comment_immediate_when_disabled(self, rollup_service):
        """With rollup disabled, add_comment triggers callback immediately."""
        rollup_service._default_config.enabled = False
        callback = AsyncMock()
        rollup_service.set_evaluation_callback(callback)

        comment = GoalComment(
            comment_id="c_imm",
            goal_id="goal_imm",
            content="Test",
            comment_type=CommentType.SUGGESTION,
        )
        result = await rollup_service.add_comment("goal_imm", comment)

        assert result is None  # No batch created
        callback.assert_awaited_once_with("goal_imm", ["c_imm"])

    @pytest.mark.asyncio
    async def test_callback_wiring_pattern_from_app(self):
        """Simulate the wiring pattern used in app.py lifespan."""
        # This mimics the actual wiring from app.py
        mock_eval_service = MagicMock()
        mock_eval_service.evaluate_batch = AsyncMock(return_value=[])

        rollup_service = CommentRollupService(redis_client=None)
        rollup_service._initialized = True

        # Wire the callback (same pattern as app.py)
        async def _rollup_evaluation_callback(goal_id: str, comment_ids: list) -> None:
            await mock_eval_service.evaluate_batch(goal_id)

        rollup_service.set_evaluation_callback(_rollup_evaluation_callback)

        # Inject a batch and trigger
        batch = RollupBatch(
            batch_id="batch_app",
            goal_id="goal_app",
            comment_ids=["c1"],
            status=RollupStatus.WAITING,
        )
        rollup_service._active_batches["goal_app"] = batch

        await rollup_service._trigger_evaluation("goal_app")

        mock_eval_service.evaluate_batch.assert_awaited_once_with("goal_app")
