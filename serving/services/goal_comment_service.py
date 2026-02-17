"""Goal Comment Service for managing goal conversation threads.

Provides CRUD operations for goal comments with evaluation status tracking.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.work_map import (
    GoalComment,
    GoalCommentCreateRequest,
    GoalCommentUpdateRequest,
    GoalCommentListResponse,
    EvaluationStatus,
    EvaluationResult,
    ConversationStatus,
    Goal
)

logger = logging.getLogger(__name__)


class GoalCommentService:
    """Service for managing goal comments.

    Provides:
    - Comment CRUD operations
    - Evaluation status transitions
    - Conversation status aggregation
    """

    def __init__(self, redis_client=None):
        """Initialize goal comment service.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._comments: Dict[str, GoalComment] = {}
        self._goal_comments_index: Dict[str, List[str]] = {}  # goal_id -> [comment_ids]
        self._goals: Dict[str, Goal] = {}  # Reference to goals (set externally)
        self._initialized = False

    def set_goals_reference(self, goals: Dict[str, Goal]) -> None:
        """Set reference to goals dictionary for conversation status updates.

        Args:
            goals: Reference to goals dictionary from GoalService
        """
        self._goals = goals

    async def initialize(self) -> None:
        """Initialize the service, loading data from Redis if available."""
        if self._initialized:
            return

        await self._load_comments_from_redis()
        self._initialized = True
        logger.info("Goal comment service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}workmap:{key}"

    # ============ Redis Persistence ============

    async def _load_comments_from_redis(self) -> None:
        """Load comments from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("comment:*"),
                    count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    # Skip index keys
                    if ":goal:" in key_str or ":status:" in key_str:
                        continue
                    try:
                        data = await self._redis._redis.hgetall(key)
                        if data:
                            comment_data = {
                                (k.decode() if isinstance(k, bytes) else k):
                                (v.decode() if isinstance(v, bytes) else v)
                                for k, v in data.items()
                            }
                            # Parse evaluation result if present
                            eval_result_raw = comment_data.get('evaluation_result', '')
                            eval_result = None
                            if eval_result_raw and eval_result_raw != 'null':
                                try:
                                    eval_result_dict = json.loads(eval_result_raw)
                                    if eval_result_dict:
                                        eval_result = EvaluationResult(**eval_result_dict)
                                except (json.JSONDecodeError, TypeError):
                                    pass

                            comment = GoalComment(
                                comment_id=comment_data.get('comment_id', ''),
                                goal_id=comment_data.get('goal_id', ''),
                                content=comment_data.get('content', ''),
                                priority=comment_data.get('priority') or None,
                                area=comment_data.get('area') or None,
                                evaluation_status=EvaluationStatus(
                                    comment_data.get('evaluation_status', 'not_evaluated')
                                ),
                                evaluation_result=eval_result,
                                evaluation_error=comment_data.get('evaluation_error') or None,
                                evaluation_retry_count=int(
                                    comment_data.get('evaluation_retry_count', '0')
                                ),
                                created_at=datetime.fromisoformat(
                                    comment_data.get('created_at', datetime.now(timezone.utc).isoformat())
                                ),
                                created_by=comment_data.get('created_by', 'user')
                            )
                            self._comments[comment.comment_id] = comment
                            # Update goal index
                            if comment.goal_id not in self._goal_comments_index:
                                self._goal_comments_index[comment.goal_id] = []
                            if comment.comment_id not in self._goal_comments_index[comment.goal_id]:
                                self._goal_comments_index[comment.goal_id].append(comment.comment_id)
                    except Exception as e:
                        logger.error(f"Error loading comment from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._comments)} comments from Redis")
        except Exception as e:
            logger.error(f"Error loading comments from Redis: {e}")

    async def _save_comment_to_redis(self, comment: GoalComment) -> None:
        """Save comment to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"comment:{comment.comment_id}")
            # Serialize evaluation_result properly
            eval_result_json = None
            if comment.evaluation_result:
                eval_result_json = json.dumps(comment.evaluation_result.model_dump())
            await self._redis._redis.hset(key, mapping={
                'comment_id': comment.comment_id,
                'goal_id': comment.goal_id,
                'content': comment.content,
                'priority': comment.priority.value if comment.priority else '',
                'area': comment.area.value if comment.area else '',
                'evaluation_status': comment.evaluation_status.value,
                'evaluation_result': eval_result_json or '',
                'evaluation_error': comment.evaluation_error or '',
                'evaluation_retry_count': str(comment.evaluation_retry_count),
                'created_at': comment.created_at.isoformat(),
                'created_by': comment.created_by
            })

            # Update goal index
            await self._redis._redis.sadd(
                self._key(f"comment:goal:{comment.goal_id}"),
                comment.comment_id
            )

            # Update evaluation status index
            await self._redis._redis.sadd(
                self._key(f"comment:status:{comment.evaluation_status.value}"),
                comment.comment_id
            )
        except Exception as e:
            logger.error(f"Error saving comment to Redis: {e}")

    async def _delete_comment_from_redis(self, comment_id: str) -> None:
        """Delete comment from Redis."""
        if not self._redis:
            return

        try:
            comment = self._comments.get(comment_id)
            if comment:
                # Remove from goal index
                await self._redis._redis.srem(
                    self._key(f"comment:goal:{comment.goal_id}"),
                    comment_id
                )
                # Remove from status index
                await self._redis._redis.srem(
                    self._key(f"comment:status:{comment.evaluation_status.value}"),
                    comment_id
                )
            await self._redis._redis.delete(self._key(f"comment:{comment_id}"))
        except Exception as e:
            logger.error(f"Error deleting comment from Redis: {e}")

    # ============ Comment CRUD Operations ============

    async def create_comment(
        self,
        goal_id: str,
        request: GoalCommentCreateRequest
    ) -> GoalComment:
        """Create a new comment for a goal.

        Args:
            goal_id: ID of the parent goal
            request: Comment creation request

        Returns:
            Created comment
        """
        comment_id = f"comment_{uuid.uuid4().hex[:12]}"

        comment = GoalComment(
            comment_id=comment_id,
            goal_id=goal_id,
            content=request.content,
            priority=request.priority,
            area=request.area,
            evaluation_status=EvaluationStatus.NOT_EVALUATED,
            created_by=request.created_by
        )

        self._comments[comment_id] = comment

        # Update goal index
        if goal_id not in self._goal_comments_index:
            self._goal_comments_index[goal_id] = []
        self._goal_comments_index[goal_id].append(comment_id)

        await self._save_comment_to_redis(comment)

        # Update goal conversation status
        await self._update_goal_conversation_status(goal_id)

        logger.info(f"Created comment {comment_id} for goal {goal_id}")
        return comment

    async def get_comment(self, comment_id: str) -> Optional[GoalComment]:
        """Get a comment by ID."""
        return self._comments.get(comment_id)

    async def list_comments(
        self,
        goal_id: str,
        limit: int = 100
    ) -> GoalCommentListResponse:
        """List comments for a goal.

        Args:
            goal_id: ID of the parent goal
            limit: Maximum number of comments to return

        Returns:
            List of comments with conversation status
        """
        comment_ids = self._goal_comments_index.get(goal_id, [])
        items = [self._comments[cid] for cid in comment_ids if cid in self._comments]

        # Sort by created_at (oldest first for conversation flow)
        items.sort(key=lambda c: c.created_at)
        items = items[:limit]

        conversation_status = self._calculate_conversation_status(goal_id)

        return GoalCommentListResponse(
            items=items,
            total=len(comment_ids),
            goal_id=goal_id,
            conversation_status=conversation_status
        )

    async def update_comment(
        self,
        comment_id: str,
        request: GoalCommentUpdateRequest
    ) -> Optional[GoalComment]:
        """Update a comment.

        Args:
            comment_id: ID of the comment to update
            request: Update request

        Returns:
            Updated comment or None if not found
        """
        comment = self._comments.get(comment_id)
        if not comment:
            return None

        old_status = comment.evaluation_status

        if request.content is not None:
            comment.content = request.content
        if request.priority is not None:
            comment.priority = request.priority
        if request.area is not None:
            comment.area = request.area
        if request.evaluation_status is not None:
            comment.evaluation_status = request.evaluation_status
        if request.evaluation_result is not None:
            comment.evaluation_result = request.evaluation_result
        if request.evaluation_error is not None:
            comment.evaluation_error = request.evaluation_error
        if request.evaluation_retry_count is not None:
            comment.evaluation_retry_count = request.evaluation_retry_count

        # Update Redis status index if status changed
        if self._redis and old_status != comment.evaluation_status:
            await self._redis._redis.srem(
                self._key(f"comment:status:{old_status.value}"),
                comment_id
            )

        await self._save_comment_to_redis(comment)

        # Update goal conversation status if evaluation status changed
        if old_status != comment.evaluation_status:
            await self._update_goal_conversation_status(comment.goal_id)

        logger.info(f"Updated comment {comment_id}")
        return comment

    async def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment.

        Args:
            comment_id: ID of the comment to delete

        Returns:
            True if deleted, False if not found
        """
        if comment_id not in self._comments:
            return False

        comment = self._comments[comment_id]
        goal_id = comment.goal_id

        await self._delete_comment_from_redis(comment_id)

        # Remove from goal index
        if goal_id in self._goal_comments_index:
            if comment_id in self._goal_comments_index[goal_id]:
                self._goal_comments_index[goal_id].remove(comment_id)

        del self._comments[comment_id]

        # Update goal conversation status
        await self._update_goal_conversation_status(goal_id)

        logger.info(f"Deleted comment {comment_id}")
        return True

    # ============ Conversation Status Operations ============

    def _calculate_conversation_status(self, goal_id: str) -> ConversationStatus:
        """Calculate the conversation status for a goal based on its comments
        and goal text evaluation status.

        Factors in:
        - Whether the initial goal text has been evaluated (decomposed)
        - Evaluation status of each comment

        Args:
            goal_id: ID of the goal

        Returns:
            Aggregated conversation status
        """
        goal = self._goals.get(goal_id)
        comment_ids = self._goal_comments_index.get(goal_id, [])

        # Check goal text evaluation status
        goal_text_evaluated = goal.goal_text_evaluated if goal else False

        if not comment_ids and goal_text_evaluated:
            return ConversationStatus.COMPLETE
        if not comment_ids and not goal_text_evaluated:
            return ConversationStatus.NO_COMMENTS

        has_not_evaluated = not goal_text_evaluated
        has_evaluating = False
        all_evaluated = goal_text_evaluated

        for cid in comment_ids:
            comment = self._comments.get(cid)
            if not comment:
                continue

            if comment.evaluation_status == EvaluationStatus.NOT_EVALUATED:
                has_not_evaluated = True
                all_evaluated = False
            elif comment.evaluation_status == EvaluationStatus.EVALUATING:
                has_evaluating = True
                all_evaluated = False
            elif comment.evaluation_status == EvaluationStatus.FAILED:
                # Failed evaluations count as pending (can be retried)
                has_not_evaluated = True
                all_evaluated = False
            # EVALUATED doesn't change all_evaluated

        if has_evaluating:
            return ConversationStatus.EVALUATING
        if all_evaluated:
            return ConversationStatus.COMPLETE
        if has_not_evaluated:
            return ConversationStatus.PENDING

        return ConversationStatus.NO_COMMENTS

    async def _update_goal_conversation_status(self, goal_id: str) -> None:
        """Update the conversation status on a goal.

        Args:
            goal_id: ID of the goal to update
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return

        new_status = self._calculate_conversation_status(goal_id)
        if goal.conversation_status != new_status:
            goal.conversation_status = new_status
            goal.updated_at = datetime.now(timezone.utc)
            logger.info(f"Updated goal {goal_id} conversation status to {new_status.value}")

    async def get_comments_by_status(
        self,
        evaluation_status: EvaluationStatus,
        limit: int = 100
    ) -> List[GoalComment]:
        """Get comments by evaluation status.

        Args:
            evaluation_status: Status to filter by
            limit: Maximum number of comments to return

        Returns:
            List of comments with the given status
        """
        items = [
            c for c in self._comments.values()
            if c.evaluation_status == evaluation_status
        ]
        items.sort(key=lambda c: c.created_at)
        return items[:limit]

    # ============ Direct Access ============

    @property
    def comments(self) -> Dict[str, GoalComment]:
        """Direct access to comments dictionary."""
        return self._comments


# Global instance
_goal_comment_service: Optional[GoalCommentService] = None


def get_goal_comment_service() -> GoalCommentService:
    """Get the global goal comment service instance."""
    if _goal_comment_service is None:
        raise RuntimeError("Goal comment service not initialized")
    return _goal_comment_service


def set_goal_comment_service(service: GoalCommentService) -> None:
    """Set the global goal comment service instance."""
    global _goal_comment_service
    _goal_comment_service = service
