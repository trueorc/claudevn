"""Comment Rollup Service for batch comment processing.

Implements rollup capability to efficiently process multiple comments
submitted in quick succession as a single evaluation batch.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from models.work_map import (
    GoalComment,
    RollupBatch,
    RollupConfig,
    RollupStatus,
    RollupStatusResponse,
    EvaluationStatus,
)

logger = logging.getLogger(__name__)


class CommentRollupService:
    """Service for managing comment rollup and batch evaluation.

    Tracks comment submission timestamps and groups comments within
    configurable time windows. Triggers batch evaluation after a quiet
    period with no new comments.

    Flow:
    1. Comment submitted -> Start/extend rollup window
    2. More comments within window -> Add to batch
    3. Rollup window expires OR quiet period passes -> Trigger evaluation
    4. Evaluation completes -> Mark all comments evaluated
    """

    def __init__(
        self,
        redis_client=None,
        config: Optional[RollupConfig] = None,
        evaluation_callback: Optional[Callable] = None
    ):
        """Initialize rollup service.

        Args:
            redis_client: Optional Redis client for persistence
            config: Default rollup configuration
            evaluation_callback: Async callback to trigger evaluation
        """
        self._redis = redis_client
        self._default_config = config or RollupConfig()
        self._evaluation_callback = evaluation_callback

        # In-memory state
        self._active_batches: Dict[str, RollupBatch] = {}  # goal_id -> batch
        self._goal_configs: Dict[str, RollupConfig] = {}  # goal_id -> custom config
        self._timers: Dict[str, asyncio.Task] = {}  # goal_id -> timer task
        self._initialized = False

    def set_evaluation_callback(
        self,
        callback: Callable[[str, List[str]], None]
    ) -> None:
        """Set callback for triggering evaluation.

        Args:
            callback: Async function(goal_id, comment_ids) to trigger evaluation
        """
        self._evaluation_callback = callback

    async def initialize(self) -> None:
        """Initialize the service, loading state from Redis if available."""
        if self._initialized:
            return

        await self._load_batches_from_redis()
        self._initialized = True
        logger.info("Comment rollup service initialized")

    async def shutdown(self) -> None:
        """Shutdown the service, cancelling timers."""
        for goal_id, timer in list(self._timers.items()):
            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass
        self._timers.clear()
        logger.info("Comment rollup service shutdown")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}rollup:{key}"

    # ============ Redis Persistence ============

    async def _load_batches_from_redis(self) -> None:
        """Load active batches from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("batch:*"),
                    count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    try:
                        data = await self._redis._redis.get(key)
                        if data:
                            data_str = data.decode() if isinstance(data, bytes) else data
                            batch_data = json.loads(data_str)
                            batch = RollupBatch(**batch_data)
                            # Only restore non-completed batches
                            if batch.status != RollupStatus.COMPLETED:
                                self._active_batches[batch.goal_id] = batch
                                # Restart timer if needed
                                await self._schedule_evaluation(batch.goal_id)
                    except Exception as e:
                        logger.error(f"Error loading batch from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._active_batches)} active rollup batches from Redis")
        except Exception as e:
            logger.error(f"Error loading batches from Redis: {e}")

    async def _save_batch_to_redis(self, batch: RollupBatch) -> None:
        """Save batch to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"batch:{batch.goal_id}")
            # Convert datetime fields to ISO format for JSON serialization
            batch_dict = batch.model_dump()
            for field in ['first_comment_at', 'last_comment_at', 'window_expires_at',
                         'quiet_period_ends_at', 'completed_at']:
                if batch_dict.get(field):
                    batch_dict[field] = batch_dict[field].isoformat()
            # Serialize config
            if batch_dict.get('config'):
                batch_dict['config'] = batch.config.model_dump()

            await self._redis._redis.set(key, json.dumps(batch_dict))

            # Set TTL for auto-cleanup (2x the max window time)
            max_ttl = max(
                batch.config.rollup_window_seconds,
                batch.config.quiet_period_seconds
            ) * 2 + 60
            await self._redis._redis.expire(key, max_ttl)
        except Exception as e:
            logger.error(f"Error saving batch to Redis: {e}")

    async def _delete_batch_from_redis(self, goal_id: str) -> None:
        """Delete batch from Redis."""
        if not self._redis:
            return

        try:
            await self._redis._redis.delete(self._key(f"batch:{goal_id}"))
        except Exception as e:
            logger.error(f"Error deleting batch from Redis: {e}")

    # ============ Configuration ============

    def get_config(self, goal_id: Optional[str] = None) -> RollupConfig:
        """Get rollup configuration for a goal.

        Args:
            goal_id: Optional goal ID for goal-specific config

        Returns:
            Configuration (goal-specific or default)
        """
        if goal_id and goal_id in self._goal_configs:
            return self._goal_configs[goal_id]
        return self._default_config

    def set_config(
        self,
        config: RollupConfig,
        goal_id: Optional[str] = None
    ) -> None:
        """Set rollup configuration.

        Args:
            config: Configuration to set
            goal_id: Optional goal ID for goal-specific config (None = default)
        """
        if goal_id:
            self._goal_configs[goal_id] = config
        else:
            self._default_config = config
        logger.info(f"Rollup config updated: goal={goal_id or 'default'}, window={config.rollup_window_seconds}s, quiet={config.quiet_period_seconds}s")

    # ============ Rollup Operations ============

    async def add_comment(
        self,
        goal_id: str,
        comment: GoalComment,
        force_evaluate: bool = False
    ) -> Optional[RollupBatch]:
        """Add a comment to rollup tracking.

        Args:
            goal_id: Goal ID the comment belongs to
            comment: Comment to add
            force_evaluate: If True, skip rollup and evaluate immediately

        Returns:
            The rollup batch (if not force_evaluate)
        """
        config = self.get_config(goal_id)

        # If rollup disabled or force evaluate, trigger immediate evaluation
        if not config.enabled or force_evaluate:
            logger.info(f"Immediate evaluation for comment {comment.comment_id} (force={force_evaluate}, enabled={config.enabled})")
            if self._evaluation_callback:
                await self._evaluation_callback(goal_id, [comment.comment_id])
            return None

        now = datetime.now(timezone.utc)
        batch = self._active_batches.get(goal_id)

        if batch is None:
            # Start new batch
            batch = RollupBatch(
                batch_id=f"batch_{uuid.uuid4().hex[:12]}",
                goal_id=goal_id,
                comment_ids=[comment.comment_id],
                status=RollupStatus.COLLECTING,
                first_comment_at=now,
                last_comment_at=now,
                window_expires_at=now + timedelta(seconds=config.rollup_window_seconds),
                config=config
            )
            self._active_batches[goal_id] = batch
            logger.info(f"Started new rollup batch {batch.batch_id} for goal {goal_id}")
        else:
            # Add to existing batch
            if comment.comment_id not in batch.comment_ids:
                batch.comment_ids.append(comment.comment_id)
            batch.last_comment_at = now

            # If we're still collecting and window hasn't expired, extend quiet period
            if batch.status == RollupStatus.COLLECTING:
                # Check if window has expired
                if batch.window_expires_at and now >= batch.window_expires_at:
                    batch.status = RollupStatus.WAITING
                    batch.quiet_period_ends_at = now + timedelta(
                        seconds=config.quiet_period_seconds
                    )
            elif batch.status == RollupStatus.WAITING:
                # New comment resets quiet period
                batch.quiet_period_ends_at = now + timedelta(
                    seconds=config.quiet_period_seconds
                )

            logger.info(f"Added comment {comment.comment_id} to batch {batch.batch_id} (now {len(batch.comment_ids)} comments)")

        await self._save_batch_to_redis(batch)
        await self._schedule_evaluation(goal_id)

        return batch

    async def _schedule_evaluation(self, goal_id: str) -> None:
        """Schedule evaluation timer for a goal's batch.

        Args:
            goal_id: Goal ID to schedule evaluation for
        """
        # Cancel existing timer
        if goal_id in self._timers:
            self._timers[goal_id].cancel()
            try:
                await self._timers[goal_id]
            except asyncio.CancelledError:
                pass

        batch = self._active_batches.get(goal_id)
        if not batch or batch.status in [RollupStatus.PROCESSING, RollupStatus.COMPLETED]:
            return

        now = datetime.now(timezone.utc)
        delay_seconds = 0.0

        if batch.status == RollupStatus.COLLECTING:
            # Wait for window to expire, then add quiet period
            if batch.window_expires_at:
                window_remaining = (batch.window_expires_at - now).total_seconds()
                delay_seconds = max(0, window_remaining) + batch.config.quiet_period_seconds
        elif batch.status == RollupStatus.WAITING:
            # Wait for quiet period to end
            if batch.quiet_period_ends_at:
                delay_seconds = max(0, (batch.quiet_period_ends_at - now).total_seconds())

        # Create timer task
        async def evaluation_timer():
            try:
                await asyncio.sleep(delay_seconds)
                await self._trigger_evaluation(goal_id)
            except asyncio.CancelledError:
                pass

        self._timers[goal_id] = asyncio.create_task(evaluation_timer())
        logger.debug(f"Scheduled evaluation for goal {goal_id} in {delay_seconds:.1f}s")

    async def _trigger_evaluation(self, goal_id: str) -> None:
        """Trigger batch evaluation for a goal.

        Args:
            goal_id: Goal ID to evaluate
        """
        batch = self._active_batches.get(goal_id)
        if not batch:
            return

        # Update status
        batch.status = RollupStatus.PROCESSING
        await self._save_batch_to_redis(batch)

        logger.info(f"Triggering batch evaluation for goal {goal_id}: {len(batch.comment_ids)} comments")

        if self._evaluation_callback:
            try:
                await self._evaluation_callback(goal_id, batch.comment_ids)
                # Mark complete
                batch.status = RollupStatus.COMPLETED
                batch.completed_at = datetime.now(timezone.utc)
                await self._save_batch_to_redis(batch)
            except Exception as e:
                logger.error(f"Evaluation callback failed for goal {goal_id}: {e}")
                # Revert to waiting for retry
                batch.status = RollupStatus.WAITING
                batch.quiet_period_ends_at = datetime.now(timezone.utc) + timedelta(
                    seconds=batch.config.quiet_period_seconds
                )
                await self._save_batch_to_redis(batch)
                await self._schedule_evaluation(goal_id)
                return

        # Clean up completed batch
        del self._active_batches[goal_id]
        if goal_id in self._timers:
            del self._timers[goal_id]
        await self._delete_batch_from_redis(goal_id)

    async def force_evaluate(self, goal_id: str) -> bool:
        """Force immediate evaluation of pending comments for a goal.

        Args:
            goal_id: Goal ID to force evaluation for

        Returns:
            True if there was a batch to evaluate
        """
        batch = self._active_batches.get(goal_id)
        if not batch or batch.status == RollupStatus.PROCESSING:
            return False

        # Cancel timer
        if goal_id in self._timers:
            self._timers[goal_id].cancel()
            try:
                await self._timers[goal_id]
            except asyncio.CancelledError:
                pass

        # Trigger immediately
        await self._trigger_evaluation(goal_id)
        return True

    async def get_status(self, goal_id: str) -> RollupStatusResponse:
        """Get rollup status for a goal.

        Args:
            goal_id: Goal ID to get status for

        Returns:
            Rollup status response
        """
        batch = self._active_batches.get(goal_id)
        config = self.get_config(goal_id)

        return RollupStatusResponse(
            goal_id=goal_id,
            has_active_batch=batch is not None,
            batch=batch,
            pending_comment_count=len(batch.comment_ids) if batch else 0,
            config=config
        )

    async def get_pending_goals(self) -> List[str]:
        """Get list of goal IDs with active rollup batches.

        Returns:
            List of goal IDs with pending batches
        """
        return list(self._active_batches.keys())

    # ============ Direct Access ============

    @property
    def active_batches(self) -> Dict[str, RollupBatch]:
        """Direct access to active batches."""
        return self._active_batches


# Global instance
_comment_rollup_service: Optional[CommentRollupService] = None


def get_comment_rollup_service() -> CommentRollupService:
    """Get the global comment rollup service instance."""
    if _comment_rollup_service is None:
        raise RuntimeError("Comment rollup service not initialized")
    return _comment_rollup_service


def set_comment_rollup_service(service: CommentRollupService) -> None:
    """Set the global comment rollup service instance."""
    global _comment_rollup_service
    _comment_rollup_service = service
