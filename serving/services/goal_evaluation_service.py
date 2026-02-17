"""Goal Evaluation Service for processing goal comments.

Handles the evaluation pipeline for goal comments:
- Queues comments for async evaluation
- Processes evaluations with status transitions
- Stores evaluation results
- Broadcasts status change notifications via WebSocket
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from models.work_map import (
    GoalComment,
    GoalCommentUpdateRequest,
    EvaluationStatus,
    EvaluationResult,
    CommentType,
    SuggestedAction,
)
from models.observability import CommentEvaluationStatusEvent
from services.goal_comment_service import GoalCommentService, get_goal_comment_service

logger = logging.getLogger(__name__)


# Maximum retry attempts for failed evaluations
MAX_EVALUATION_RETRIES = 3
# Delay between retries (seconds)
RETRY_DELAY_SECONDS = 5


class GoalEvaluationService:
    """Service for evaluating goal comments.

    Provides:
    - Async evaluation queue processing
    - Status transition management
    - Retry logic for failed evaluations
    - Callback hooks for notifications
    """

    def __init__(
        self,
        comment_service: Optional[GoalCommentService] = None,
        max_retries: int = MAX_EVALUATION_RETRIES,
        retry_delay: float = RETRY_DELAY_SECONDS,
    ):
        """Initialize goal evaluation service.

        Args:
            comment_service: Optional comment service (uses global if not provided)
            max_retries: Maximum retry attempts for failed evaluations
            retry_delay: Delay between retries in seconds
        """
        self._comment_service = comment_service
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        # Evaluation queue
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._running = False

        # Status change callbacks
        self._on_status_change_callbacks: List[
            Callable[[str, EvaluationStatus, Optional[EvaluationResult]], None]
        ] = []

        # Custom evaluator (can be replaced for testing or different AI backends)
        self._evaluator: Optional[Callable[[GoalComment], EvaluationResult]] = None

        self._initialized = False

    @property
    def comment_service(self) -> GoalCommentService:
        """Get comment service, using global instance if not injected."""
        if self._comment_service:
            return self._comment_service
        return get_goal_comment_service()

    def set_evaluator(
        self,
        evaluator: Callable[[GoalComment], EvaluationResult]
    ) -> None:
        """Set custom evaluator function.

        Args:
            evaluator: Async function that takes a comment and returns evaluation result
        """
        self._evaluator = evaluator

    def on_status_change(
        self,
        callback: Callable[[str, EvaluationStatus, Optional[EvaluationResult]], None]
    ) -> None:
        """Register callback for status changes.

        Args:
            callback: Function called with (comment_id, new_status, result)
        """
        self._on_status_change_callbacks.append(callback)

    async def start(self) -> None:
        """Start the evaluation processing loop."""
        if self._running:
            return

        self._running = True
        self._processing_task = asyncio.create_task(self._process_queue())
        self._initialized = True
        logger.info("Goal evaluation service started")

    async def stop(self) -> None:
        """Stop the evaluation processing loop."""
        self._running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self._processing_task = None
        logger.info("Goal evaluation service stopped")

    async def queue_for_evaluation(self, comment_id: str) -> bool:
        """Queue a comment for evaluation.

        Args:
            comment_id: ID of the comment to evaluate

        Returns:
            True if queued successfully
        """
        comment = await self.comment_service.get_comment(comment_id)
        if not comment:
            logger.warning(f"Cannot queue unknown comment {comment_id}")
            return False

        if comment.evaluation_status != EvaluationStatus.NOT_EVALUATED:
            logger.debug(f"Comment {comment_id} already processed, skipping queue")
            return False

        await self._queue.put(comment_id)
        logger.debug(f"Queued comment {comment_id} for evaluation")
        return True

    async def queue_pending_comments(self, limit: int = 100) -> int:
        """Queue all pending comments for evaluation.

        Args:
            limit: Maximum number of comments to queue

        Returns:
            Number of comments queued
        """
        pending = await self.comment_service.get_comments_by_status(
            EvaluationStatus.NOT_EVALUATED,
            limit=limit
        )

        count = 0
        for comment in pending:
            if await self.queue_for_evaluation(comment.comment_id):
                count += 1

        logger.info(f"Queued {count} pending comments for evaluation")
        return count

    async def evaluate_comment(self, comment_id: str) -> Optional[EvaluationResult]:
        """Evaluate a single comment synchronously.

        This method handles the full evaluation lifecycle:
        1. Update status to EVALUATING
        2. Run evaluation
        3. Store result and update status to EVALUATED (or FAILED)

        Args:
            comment_id: ID of the comment to evaluate

        Returns:
            Evaluation result or None if evaluation failed
        """
        comment = await self.comment_service.get_comment(comment_id)
        if not comment:
            logger.warning(f"Comment {comment_id} not found for evaluation")
            return None

        # Update status to evaluating
        await self._update_status(
            comment_id,
            EvaluationStatus.EVALUATING
        )

        try:
            # Run evaluation
            result = await self._run_evaluation(comment)

            # Update with result
            await self._update_status(
                comment_id,
                EvaluationStatus.EVALUATED,
                result=result
            )

            logger.info(f"Evaluated comment {comment_id}: type={result.comment_type.value}")
            return result

        except Exception as e:
            logger.error(f"Evaluation failed for comment {comment_id}: {e}")

            # Check retry count
            if comment.evaluation_retry_count < self._max_retries:
                # Increment retry count and keep as NOT_EVALUATED for retry
                await self.comment_service.update_comment(
                    comment_id,
                    GoalCommentUpdateRequest(
                        evaluation_status=EvaluationStatus.NOT_EVALUATED,
                        evaluation_retry_count=comment.evaluation_retry_count + 1,
                        evaluation_error=str(e)
                    )
                )
                self._notify_status_change(
                    comment_id,
                    EvaluationStatus.NOT_EVALUATED,
                    None
                )
            else:
                # Mark as failed after max retries
                await self._update_status(
                    comment_id,
                    EvaluationStatus.FAILED,
                    error=str(e)
                )

            return None

    async def retry_failed_comments(self, limit: int = 100) -> int:
        """Retry evaluation of failed comments.

        Resets failed comments to NOT_EVALUATED and re-queues them.

        Args:
            limit: Maximum number of comments to retry

        Returns:
            Number of comments queued for retry
        """
        failed = await self.comment_service.get_comments_by_status(
            EvaluationStatus.FAILED,
            limit=limit
        )

        count = 0
        for comment in failed:
            # Reset retry count and status
            await self.comment_service.update_comment(
                comment.comment_id,
                GoalCommentUpdateRequest(
                    evaluation_status=EvaluationStatus.NOT_EVALUATED,
                    evaluation_retry_count=0,
                    evaluation_error=None
                )
            )
            if await self.queue_for_evaluation(comment.comment_id):
                count += 1

        logger.info(f"Queued {count} failed comments for retry")
        return count

    async def evaluate_batch(
        self,
        goal_id: str,
        limit: int = 100
    ) -> List[EvaluationResult]:
        """Evaluate all pending comments for a goal (rollup processing).

        Args:
            goal_id: Goal ID to evaluate comments for
            limit: Maximum number of comments to evaluate

        Returns:
            List of evaluation results
        """
        comments = await self.comment_service.list_comments(goal_id, limit=limit)
        results = []

        for comment in comments.items:
            if comment.evaluation_status == EvaluationStatus.NOT_EVALUATED:
                result = await self.evaluate_comment(comment.comment_id)
                if result:
                    results.append(result)

        logger.info(f"Batch evaluated {len(results)} comments for goal {goal_id}")
        return results

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._running

    # ============ Internal Methods ============

    async def _process_queue(self) -> None:
        """Background task that processes the evaluation queue."""
        while self._running:
            try:
                # Wait for next comment with timeout
                try:
                    comment_id = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Process the comment
                await self.evaluate_comment(comment_id)

                # Small delay between evaluations to prevent overload
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in evaluation queue processor: {e}")
                await asyncio.sleep(self._retry_delay)

    async def _run_evaluation(self, comment: GoalComment) -> EvaluationResult:
        """Run the actual evaluation logic.

        This method can be customized via set_evaluator() for testing
        or different AI backends.

        Args:
            comment: Comment to evaluate

        Returns:
            Evaluation result
        """
        if self._evaluator:
            return await self._evaluator(comment)

        # Default simple evaluation (placeholder for AI integration)
        return self._default_evaluation(comment)

    def _default_evaluation(self, comment: GoalComment) -> EvaluationResult:
        """Default evaluation logic based on simple heuristics.

        This is a placeholder for actual AI evaluation.

        Args:
            comment: Comment to evaluate

        Returns:
            Evaluation result based on simple heuristics
        """
        content_lower = comment.content.lower()

        # Determine comment type based on keywords
        if any(word in content_lower for word in ['bug', 'error', 'broken', 'crash', 'fix']):
            comment_type = CommentType.BUG
        elif any(word in content_lower for word in ['suggest', 'could', 'should', 'idea', 'add']):
            comment_type = CommentType.SUGGESTION
        elif any(word in content_lower for word in ['enhance', 'improve', 'better', 'upgrade']):
            comment_type = CommentType.ENHANCEMENT
        elif any(word in content_lower for word in ['priority', 'urgent', 'important', 'asap']):
            comment_type = CommentType.PRIORITY_INFLUENCE
        else:
            comment_type = CommentType.INFO

        # Extract basic entities (simple word extraction)
        entities = []
        # Look for capitalized words that might be feature names
        words = comment.content.split()
        for word in words:
            if word[0].isupper() and len(word) > 2 and word.isalpha():
                entities.append(word)

        # Generate suggested actions based on type
        suggested_actions = []
        if comment_type == CommentType.BUG:
            suggested_actions.append(SuggestedAction(
                action_type="create_issue",
                description="Create bug fix issue from this comment",
                metadata={"issue_type": "bug"}
            ))
        elif comment_type == CommentType.SUGGESTION:
            suggested_actions.append(SuggestedAction(
                action_type="create_issue",
                description="Create feature issue from suggestion",
                metadata={"issue_type": "feature"}
            ))
        elif comment_type == CommentType.PRIORITY_INFLUENCE:
            suggested_actions.append(SuggestedAction(
                action_type="update_priority",
                description="Consider adjusting goal priority",
                target=comment.goal_id
            ))

        # Calculate confidence (simple heuristic)
        confidence = 0.6  # Base confidence
        if comment.priority:
            confidence += 0.1
        if comment.area:
            confidence += 0.1
        if len(comment.content) > 100:
            confidence += 0.1

        return EvaluationResult(
            comment_type=comment_type,
            entities=entities[:10],  # Limit to 10 entities
            suggested_actions=suggested_actions,
            confidence=min(confidence, 1.0),
            summary=f"Comment classified as {comment_type.value}",
            evaluator_version="1.0-heuristic"
        )

    async def _update_status(
        self,
        comment_id: str,
        status: EvaluationStatus,
        result: Optional[EvaluationResult] = None,
        error: Optional[str] = None
    ) -> None:
        """Update comment status and notify callbacks.

        Args:
            comment_id: Comment ID
            status: New status
            result: Optional evaluation result
            error: Optional error message
        """
        # Get old status for event
        comment = await self.comment_service.get_comment(comment_id)
        old_status = comment.evaluation_status if comment else EvaluationStatus.NOT_EVALUATED

        update_request = GoalCommentUpdateRequest(
            evaluation_status=status,
            evaluation_result=result,
            evaluation_error=error
        )
        await self.comment_service.update_comment(comment_id, update_request)
        self._notify_status_change(comment_id, status, result)

        # Broadcast WebSocket event
        await self._broadcast_status_event(
            comment_id=comment_id,
            goal_id=comment.goal_id if comment else "",
            old_status=old_status,
            new_status=status,
            result=result,
            error=error
        )

    async def _broadcast_status_event(
        self,
        comment_id: str,
        goal_id: str,
        old_status: EvaluationStatus,
        new_status: EvaluationStatus,
        result: Optional[EvaluationResult] = None,
        error: Optional[str] = None
    ) -> None:
        """Broadcast evaluation status change via WebSocket.

        Args:
            comment_id: Comment ID
            goal_id: Parent goal ID
            old_status: Previous status
            new_status: New status
            result: Optional evaluation result
            error: Optional error message
        """
        try:
            from services.observability_event_bus import get_event_bus

            event = CommentEvaluationStatusEvent(
                event_id=f"eval_{uuid.uuid4().hex[:12]}",
                session_id=goal_id,  # Use goal_id for subscription
                comment_id=comment_id,
                old_status=old_status.value,
                new_status=new_status.value,
                comment_type=result.comment_type.value if result else None,
                confidence=result.confidence if result else None,
                summary=result.summary if result else None,
                error=error
            )

            event_bus = get_event_bus()
            await event_bus.emit_event(event)
            logger.debug(f"Broadcast evaluation status event for {comment_id}")

        except Exception as e:
            # Don't fail evaluation due to broadcast failure
            logger.warning(f"Failed to broadcast evaluation status event: {e}")

    def _notify_status_change(
        self,
        comment_id: str,
        status: EvaluationStatus,
        result: Optional[EvaluationResult]
    ) -> None:
        """Notify all registered callbacks of status change.

        Args:
            comment_id: Comment ID
            status: New status
            result: Optional evaluation result
        """
        for callback in self._on_status_change_callbacks:
            try:
                callback(comment_id, status, result)
            except Exception as e:
                logger.error(f"Error in status change callback: {e}")


# Global instance
_evaluation_service: Optional[GoalEvaluationService] = None


def get_goal_evaluation_service() -> GoalEvaluationService:
    """Get the global goal evaluation service instance."""
    if _evaluation_service is None:
        raise RuntimeError("Goal evaluation service not initialized")
    return _evaluation_service


def set_goal_evaluation_service(service: GoalEvaluationService) -> None:
    """Set the global goal evaluation service instance."""
    global _evaluation_service
    _evaluation_service = service
