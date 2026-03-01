"""Goal Service for goal CRUD and lifecycle management.

Extracted from work_map_service.py to reduce service size and improve maintainability.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from models.work_map import (
    Goal, GoalIntentType, GoalProgressMetrics, GoalStatus,
    GoalCreateRequest, GoalListResponse,
    GoalDeleteResponse, GoalAdjustIntentRequest, IntentSignal,
    Issue, IssueStatus, ConversationStatus,
    DecompositionPass, DecompositionTrigger,
)

logger = logging.getLogger(__name__)


class GoalService:
    """Service for managing goals.

    Provides:
    - Goal CRUD operations
    - Goal status transitions
    - Goal-issue relationship management
    """

    def __init__(self, redis_client=None):
        """Initialize goal service.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._goals: Dict[str, Goal] = {}
        self._issues: Dict[str, Issue] = {}  # Reference to issues (set externally)
        self._initialized = False

    def set_issues_reference(self, issues: Dict[str, Issue]) -> None:
        """Set reference to issues dictionary for goal completion checks.

        Args:
            issues: Reference to issues dictionary from WorkMapService
        """
        self._issues = issues

    async def initialize(self) -> None:
        """Initialize the service, loading data from Redis if available."""
        if self._initialized:
            return

        await self._load_goals_from_redis()
        self._initialized = True
        logger.info("Goal service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}workmap:{key}"

    # ============ Redis Persistence ============

    async def _load_goals_from_redis(self) -> None:
        """Load goals from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("goal:*"),
                    count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    # Skip status index keys
                    if ":status:" in key_str:
                        continue
                    try:
                        data = await self._redis._redis.hgetall(key)
                        if data:
                            goal_data = {
                                (k.decode() if isinstance(k, bytes) else k):
                                (v.decode() if isinstance(v, bytes) else v)
                                for k, v in data.items()
                            }
                            # Parse deleted_at timestamp
                            deleted_at_str = goal_data.get('deleted_at', '')
                            deleted_at = None
                            if deleted_at_str:
                                deleted_at = datetime.fromisoformat(deleted_at_str)

                            # Parse archived_at timestamp
                            archived_at_str = goal_data.get('archived_at', '')
                            archived_at = None
                            if archived_at_str:
                                archived_at = datetime.fromisoformat(archived_at_str)

                            # Parse project_id (empty string means None)
                            project_id = goal_data.get('project_id', '')
                            if not project_id:
                                project_id = None

                            # Parse decomposition_id (empty string means None)
                            decomposition_id = goal_data.get('decomposition_id', '')
                            if not decomposition_id:
                                decomposition_id = None

                            # Parse planning_started_at timestamp
                            planning_started_at_str = goal_data.get('planning_started_at', '')
                            planning_started_at = None
                            if planning_started_at_str:
                                planning_started_at = datetime.fromisoformat(planning_started_at_str)

                            # Parse planning_error (empty string means None)
                            planning_error = goal_data.get('planning_error', '')
                            if not planning_error:
                                planning_error = None

                            # Parse summary (empty string means None)
                            summary = goal_data.get('summary', '')
                            if not summary:
                                summary = None

                            # Parse intent fields
                            intent_signals_raw = goal_data.get('intent_signals', '[]')
                            intent_signals = []
                            try:
                                for sig_data in json.loads(intent_signals_raw):
                                    intent_signals.append(IntentSignal(**sig_data))
                            except (json.JSONDecodeError, Exception):
                                intent_signals = []

                            primary_intent_str = goal_data.get('primary_intent', '')
                            primary_intent = None
                            if primary_intent_str:
                                try:
                                    primary_intent = GoalIntentType(primary_intent_str)
                                except ValueError:
                                    primary_intent = None

                            intent_strength_str = goal_data.get('intent_strength', '0.0')
                            try:
                                intent_strength = float(intent_strength_str)
                            except (ValueError, TypeError):
                                intent_strength = 0.0

                            # Parse decomposition passes
                            decomposition_passes_raw = goal_data.get('decomposition_passes', '[]')
                            decomposition_passes = []
                            try:
                                for pass_data in json.loads(decomposition_passes_raw):
                                    decomposition_passes.append(DecompositionPass(**pass_data))
                            except (json.JSONDecodeError, Exception):
                                decomposition_passes = []

                            goal = Goal(
                                goal_id=goal_data.get('goal_id', ''),
                                title=goal_data.get('title', ''),
                                description=goal_data.get('description', ''),
                                summary=summary,
                                project_id=project_id,
                                decomposition_id=decomposition_id,
                                decomposition_passes=decomposition_passes,
                                priority=goal_data.get('priority', 'P2'),
                                status=GoalStatus(goal_data.get('status', 'planning')),
                                issue_ids=json.loads(goal_data.get('issue_ids', '[]')),
                                conversation_status=ConversationStatus(
                                    goal_data.get('conversation_status', 'no_comments')
                                ),
                                intent_signals=intent_signals,
                                primary_intent=primary_intent,
                                intent_strength=intent_strength,
                                created_at=datetime.fromisoformat(
                                    goal_data.get('created_at', datetime.now(timezone.utc).isoformat())
                                ),
                                updated_at=datetime.fromisoformat(
                                    goal_data.get('updated_at', datetime.now(timezone.utc).isoformat())
                                ),
                                deleted_at=deleted_at,
                                archived=goal_data.get('archived', 'false').lower() == 'true',
                                archived_at=archived_at,
                                planning_started_at=planning_started_at,
                                planning_error=planning_error
                            )
                            self._goals[goal.goal_id] = goal
                    except Exception as e:
                        logger.error(f"Error loading goal from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._goals)} goals from Redis")
        except Exception as e:
            logger.error(f"Error loading goals from Redis: {e}")

    async def _save_goal_to_redis(self, goal: Goal) -> None:
        """Save goal to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"goal:{goal.goal_id}")
            # Serialize intent signals as JSON
            intent_signals_json = json.dumps(
                [s.model_dump(mode='json') for s in goal.intent_signals]
            ) if goal.intent_signals else '[]'

            # Serialize decomposition passes as JSON
            decomposition_passes_json = json.dumps(
                [p.model_dump(mode='json') for p in goal.decomposition_passes]
            ) if goal.decomposition_passes else '[]'

            mapping = {
                'goal_id': goal.goal_id,
                'title': goal.title,
                'description': goal.description,
                'project_id': goal.project_id or '',
                'decomposition_id': goal.decomposition_id or '',
                'decomposition_passes': decomposition_passes_json,
                'priority': goal.priority.value if hasattr(goal.priority, 'value') else str(goal.priority),
                'status': goal.status.value,
                'issue_ids': json.dumps(goal.issue_ids),
                'conversation_status': goal.conversation_status.value,
                'intent_signals': intent_signals_json,
                'primary_intent': goal.primary_intent.value if goal.primary_intent else '',
                'intent_strength': str(goal.intent_strength),
                'created_at': goal.created_at.isoformat(),
                'updated_at': goal.updated_at.isoformat(),
                'deleted_at': goal.deleted_at.isoformat() if goal.deleted_at else '',
                'archived': str(goal.archived).lower(),
                'archived_at': goal.archived_at.isoformat() if goal.archived_at else '',
                'planning_started_at': goal.planning_started_at.isoformat() if goal.planning_started_at else '',
                'planning_error': goal.planning_error or '',
                'summary': goal.summary or ''
            }
            await self._redis._redis.hset(key, mapping=mapping)

            # Update status index
            await self._redis._redis.sadd(
                self._key(f"goal:status:{goal.status.value}"),
                goal.goal_id
            )
        except Exception as e:
            logger.error(f"Error saving goal to Redis: {e}")

    async def _delete_goal_from_redis(self, goal_id: str) -> None:
        """Delete goal from Redis."""
        if not self._redis:
            return

        try:
            goal = self._goals.get(goal_id)
            if goal:
                await self._redis._redis.srem(
                    self._key(f"goal:status:{goal.status.value}"),
                    goal_id
                )
            await self._redis._redis.delete(self._key(f"goal:{goal_id}"))
        except Exception as e:
            logger.error(f"Error deleting goal from Redis: {e}")

    # ============ Goal CRUD Operations ============

    async def create_goal(self, request: GoalCreateRequest) -> Goal:
        """Create a new goal.

        Includes deduplication: if a goal with matching description and
        project_id was created within the last 60 seconds, the existing
        goal is returned instead of creating a duplicate.

        Args:
            request: Goal creation request

        Returns:
            Created goal (or existing duplicate)
        """
        # Deduplication: reject rapid identical submissions
        if request.project_id and request.description:
            now = datetime.now(timezone.utc)
            dedup_window = timedelta(seconds=60)
            for existing in self._goals.values():
                if (
                    existing.deleted_at is None
                    and existing.project_id == request.project_id
                    and existing.description == request.description
                    and (now - existing.created_at) < dedup_window
                ):
                    logger.info(
                        f"Deduplicated goal creation — reusing {existing.goal_id}"
                    )
                    return existing

        goal_id = f"goal_{uuid.uuid4().hex[:12]}"

        goal = Goal(
            goal_id=goal_id,
            title=request.title,
            description=request.description,
            project_id=request.project_id,
            priority=request.priority,
            status=GoalStatus.PLANNING
        )

        self._goals[goal_id] = goal
        await self._save_goal_to_redis(goal)

        logger.info(f"Created goal {goal_id}: {goal.title}")
        return goal

    async def get_goal(
        self,
        goal_id: str,
        include_deleted: bool = False
    ) -> Optional[Goal]:
        """Get a goal by ID.

        Args:
            goal_id: Goal ID to retrieve
            include_deleted: If True, return even if soft-deleted

        Returns:
            Goal if found (and not deleted, unless include_deleted is True)
        """
        goal = self._goals.get(goal_id)
        if goal is None:
            return None
        if goal.deleted_at is not None and not include_deleted:
            return None
        return goal

    async def list_goals(
        self,
        status: Optional[GoalStatus] = None,
        project_id: Optional[str] = None,
        include_deleted: bool = False,
        include_archived: bool = False,
        limit: int = 100
    ) -> GoalListResponse:
        """List goals with optional filtering.

        Args:
            status: Filter by goal status
            project_id: Filter by project ID (None returns all goals)
            include_deleted: If True, include soft-deleted goals
            include_archived: If True, include archived goals
            limit: Maximum number of goals to return
        """
        items = list(self._goals.values())

        # Filter out soft-deleted goals unless explicitly requested
        if not include_deleted:
            items = [g for g in items if g.deleted_at is None]

        # Filter out archived goals unless explicitly requested
        if not include_archived:
            items = [g for g in items if not g.archived]

        if status:
            items = [g for g in items if g.status == status]

        # Filter by project if specified
        if project_id:
            items = [g for g in items if g.project_id == project_id]

        # Sort by priority and created time
        items.sort(key=lambda g: (g.priority.score_weight, g.created_at))
        items = items[:limit]

        # Calculate stats (excluding deleted and archived goals for default view)
        active_goals = [g for g in self._goals.values() if g.deleted_at is None and not g.archived]
        # If filtering by project, only count stats for that project
        if project_id:
            active_goals = [g for g in active_goals if g.project_id == project_id]

        by_status = {}
        for g in active_goals:
            by_status[g.status.value] = by_status.get(g.status.value, 0) + 1

        return GoalListResponse(
            items=items,
            total=len(active_goals),
            by_status=by_status
        )

    async def update_goal_status(
        self,
        goal_id: str,
        status: GoalStatus
    ) -> Optional[Goal]:
        """Update goal status."""
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        old_status = goal.status
        goal.status = status
        goal.updated_at = datetime.now(timezone.utc)

        # Update Redis indexes
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"goal:status:{old_status.value}"),
                goal_id
            )

        await self._save_goal_to_redis(goal)

        logger.info(f"Updated goal {goal_id} status: {old_status} -> {status}")
        return goal

    async def delete_goal(
        self,
        goal_id: str,
        hard: bool = False
    ) -> Optional[GoalDeleteResponse]:
        """Delete a goal (soft delete by default).

        Args:
            goal_id: Goal ID to delete
            hard: If True, permanently delete. If False (default), soft delete.

        Returns:
            GoalDeleteResponse with deletion details, or None if goal not found.
        """
        if goal_id not in self._goals:
            return None

        goal = self._goals[goal_id]
        deleted_at = datetime.now(timezone.utc)

        if hard:
            # Hard delete - remove completely
            await self._delete_goal_from_redis(goal_id)
            del self._goals[goal_id]
            logger.info(f"Hard deleted goal {goal_id}")
        else:
            # Soft delete - mark as deleted but retain data
            goal.deleted_at = deleted_at
            goal.updated_at = deleted_at
            await self._save_goal_to_redis(goal)
            logger.info(f"Soft deleted goal {goal_id}")

        return GoalDeleteResponse(
            goal_id=goal_id,
            deleted=True,
            deleted_at=deleted_at if not hard else None,
            comment_count=0  # Will be populated by API layer
        )

    async def restore_goal(self, goal_id: str) -> Optional[Goal]:
        """Restore a soft-deleted goal.

        Args:
            goal_id: Goal ID to restore

        Returns:
            Restored Goal, or None if not found or not deleted.
        """
        if goal_id not in self._goals:
            return None

        goal = self._goals[goal_id]
        if goal.deleted_at is None:
            return None  # Not deleted

        goal.deleted_at = None
        goal.updated_at = datetime.now(timezone.utc)
        await self._save_goal_to_redis(goal)

        logger.info(f"Restored goal {goal_id}")
        return goal

    async def archive_goal(self, goal_id: str) -> Optional[Goal]:
        """Archive a goal.

        Archives a goal so it's hidden by default but not deleted.
        Archived goals can be unarchived at any time.

        Args:
            goal_id: Goal ID to archive

        Returns:
            Archived Goal, or None if not found or already archived.
        """
        if goal_id not in self._goals:
            return None

        goal = self._goals[goal_id]

        # Don't archive deleted goals
        if goal.deleted_at is not None:
            return None

        # Already archived
        if goal.archived:
            return goal

        goal.archived = True
        goal.archived_at = datetime.now(timezone.utc)
        goal.updated_at = datetime.now(timezone.utc)
        await self._save_goal_to_redis(goal)

        logger.info(f"Archived goal {goal_id}")
        return goal

    async def unarchive_goal(self, goal_id: str) -> Optional[Goal]:
        """Unarchive a goal.

        Restores an archived goal to the default view.

        Args:
            goal_id: Goal ID to unarchive

        Returns:
            Unarchived Goal, or None if not found or not archived.
        """
        if goal_id not in self._goals:
            return None

        goal = self._goals[goal_id]

        # Not archived
        if not goal.archived:
            return goal

        goal.archived = False
        goal.archived_at = None
        goal.updated_at = datetime.now(timezone.utc)
        await self._save_goal_to_redis(goal)

        logger.info(f"Unarchived goal {goal_id}")
        return goal

    async def update_goal_decomposition_id(
        self,
        goal_id: str,
        decomposition_id: str,
    ) -> Optional[Goal]:
        """Update the decomposition_id for a goal.

        Args:
            goal_id: Goal ID to update
            decomposition_id: Decomposition ID to associate

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        goal.decomposition_id = decomposition_id
        goal.updated_at = datetime.now(timezone.utc)

        await self._save_goal_to_redis(goal)

        logger.info(f"Updated goal {goal_id} with decomposition_id={decomposition_id}")
        return goal

    async def get_goal_issues(self, goal_id: str) -> List[Issue]:
        """Get all issues for a goal."""
        return [i for i in self._issues.values() if i.goal_id == goal_id]

    async def update_goal_issues(
        self,
        goal_id: str,
        issue_ids: List[str],
    ) -> Optional[Goal]:
        """Update the issue_ids list for a goal.

        Sets the goal's issue_ids and updates status to IN_PROGRESS.

        Args:
            goal_id: Goal ID to update
            issue_ids: List of issue IDs created for this goal

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        goal.issue_ids = issue_ids
        goal.updated_at = datetime.now(timezone.utc)

        # Update status to in_progress since issues are now created
        if goal.status == GoalStatus.PLANNING:
            goal.status = GoalStatus.IN_PROGRESS

        await self._save_goal_to_redis(goal)

        logger.info(f"Updated goal {goal_id} with {len(issue_ids)} issues")
        return goal

    async def check_goal_completion(self, goal_id: str) -> None:
        """Check if all issues for a goal are complete."""
        goal = self._goals.get(goal_id)
        if not goal:
            return

        goal_issues = await self.get_goal_issues(goal_id)
        all_done = all(i.status == IssueStatus.DONE for i in goal_issues)

        if all_done and goal.status != GoalStatus.DONE:
            goal.status = GoalStatus.DONE
            goal.updated_at = datetime.now(timezone.utc)
            await self._save_goal_to_redis(goal)
            logger.info(f"Goal {goal_id} completed - all issues done")

    async def get_goal_progress(self, goal_id: str) -> Optional[GoalProgressMetrics]:
        """Compute multi-dimensional progress metrics for a goal.

        Returns metrics covering issue completion, characterization progress,
        and execution velocity.
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        issues = await self.get_goal_issues(goal_id)
        total = len(issues)

        if total == 0:
            return GoalProgressMetrics(
                goal_id=goal_id,
                goal_status=goal.status,
            )

        # Count by status
        status_counts = {}
        for s in IssueStatus:
            status_counts[s] = 0
        for issue in issues:
            status_counts[issue.status] = status_counts.get(issue.status, 0) + 1

        done = status_counts.get(IssueStatus.DONE, 0)
        in_progress = status_counts.get(IssueStatus.IN_PROGRESS, 0)
        blocked = status_counts.get(IssueStatus.BLOCKED, 0)
        failed = status_counts.get(IssueStatus.FAILED, 0)
        ready = status_counts.get(IssueStatus.READY, 0)
        backlog = status_counts.get(IssueStatus.BACKLOG, 0)

        completion_pct = round((done / total) * 100, 1)

        # Characterization: count issues with ontology_tags populated
        characterized = sum(1 for i in issues if i.ontology_tags is not None)
        char_pct = round((characterized / total) * 100, 1)

        # Velocity: issues completed in last 7 days
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        recent_done = sum(
            1 for i in issues
            if i.status == IssueStatus.DONE
            and i.completed_at is not None
            and i.completed_at >= week_ago
        )
        prior_done = sum(
            1 for i in issues
            if i.status == IssueStatus.DONE
            and i.completed_at is not None
            and two_weeks_ago <= i.completed_at < week_ago
        )

        if recent_done > prior_done:
            trend = "accelerating"
        elif recent_done < prior_done:
            trend = "stalling"
        else:
            trend = "steady"

        return GoalProgressMetrics(
            goal_id=goal_id,
            goal_status=goal.status,
            total_issues=total,
            done_count=done,
            in_progress_count=in_progress,
            blocked_count=blocked,
            failed_count=failed,
            ready_count=ready,
            backlog_count=backlog,
            completion_percent=completion_pct,
            characterized_count=characterized,
            characterization_percent=char_pct,
            velocity_7d=recent_done,
            velocity_trend=trend,
        )

    # ============ Planning Timeout & Recovery ============

    async def mark_planning_started(self, goal_id: str) -> Optional[Goal]:
        """Mark that planning/decomposition has started for a goal.

        Sets planning_started_at to current time and clears any previous error.

        Args:
            goal_id: Goal ID to mark

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        goal.planning_started_at = datetime.now(timezone.utc)
        goal.planning_error = None
        goal.updated_at = datetime.now(timezone.utc)

        await self._save_goal_to_redis(goal)

        logger.info(f"Marked planning started for goal {goal_id}")
        return goal

    async def mark_planning_failed(
        self,
        goal_id: str,
        error: str
    ) -> Optional[Goal]:
        """Mark a goal's planning as failed.

        Transitions goal to FAILED status with error message.

        Args:
            goal_id: Goal ID to mark as failed
            error: Error description

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        old_status = goal.status
        goal.status = GoalStatus.FAILED
        goal.planning_error = error
        goal.updated_at = datetime.now(timezone.utc)

        # Update Redis status index
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"goal:status:{old_status.value}"),
                goal_id
            )

        await self._save_goal_to_redis(goal)

        logger.info(f"Marked goal {goal_id} as failed: {error}")
        return goal

    async def get_stale_planning_goals(
        self,
        timeout_seconds: int = 300
    ) -> List[Goal]:
        """Find goals stuck in PLANNING state past the timeout.

        Args:
            timeout_seconds: How long a goal can be in PLANNING before
                it's considered stale (default: 300s / 5 minutes)

        Returns:
            List of goals stuck in PLANNING past the timeout
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)
        stale = []

        for goal in self._goals.values():
            if goal.deleted_at is not None:
                continue
            if goal.status != GoalStatus.PLANNING:
                continue

            # If planning_started_at is set and past cutoff, it's stale
            if goal.planning_started_at and goal.planning_started_at < cutoff:
                stale.append(goal)
            # If no planning_started_at but created_at is past cutoff,
            # also consider stale (legacy goals without the field)
            elif not goal.planning_started_at and goal.created_at < cutoff:
                stale.append(goal)

        return stale

    async def fail_stale_planning_goals(
        self,
        timeout_seconds: int = 300
    ) -> List[Goal]:
        """Transition stale PLANNING goals to FAILED status.

        Args:
            timeout_seconds: Timeout threshold in seconds

        Returns:
            List of goals that were transitioned to FAILED
        """
        stale_goals = await self.get_stale_planning_goals(timeout_seconds)
        failed_goals = []

        for goal in stale_goals:
            updated = await self.mark_planning_failed(
                goal.goal_id,
                f"Planning timed out after {timeout_seconds}s"
            )
            if updated:
                failed_goals.append(updated)

        if failed_goals:
            logger.info(
                f"Failed {len(failed_goals)} stale planning goals "
                f"(timeout={timeout_seconds}s)"
            )

        return failed_goals

    async def retry_goal_planning(self, goal_id: str) -> Optional[Goal]:
        """Reset a FAILED goal back to PLANNING for retry.

        Clears the error, resets planning_started_at, decomposition_id,
        and issue_ids so decomposition can be retried.

        Args:
            goal_id: Goal ID to retry

        Returns:
            Updated Goal or None if not found or not in FAILED status
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        if goal.status != GoalStatus.FAILED:
            return None

        old_status = goal.status
        goal.status = GoalStatus.PLANNING
        goal.planning_started_at = None
        goal.planning_error = None
        goal.decomposition_id = None
        goal.issue_ids = []
        goal.updated_at = datetime.now(timezone.utc)

        # Update Redis status index
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"goal:status:{old_status.value}"),
                goal_id
            )

        await self._save_goal_to_redis(goal)

        logger.info(f"Reset goal {goal_id} from FAILED to PLANNING for retry")
        return goal

    # ============ Supplemental Decomposition ============

    async def record_decomposition_pass(
        self,
        goal_id: str,
        decomposition_id: str,
        trigger: DecompositionTrigger,
        issue_ids_created: List[str],
        triggered_by: Optional[str] = None,
        trigger_context: Optional[str] = None,
    ) -> Optional[Goal]:
        """Record a decomposition pass for a goal.

        Appends a new DecompositionPass to the goal's history and
        updates the decomposition_id to the latest.

        Args:
            goal_id: Goal ID to update
            decomposition_id: ID of the decomposition result
            trigger: What triggered this decomposition
            issue_ids_created: Issue IDs created during this pass
            triggered_by: Entity that triggered decomposition
            trigger_context: Additional context

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return None

        pass_number = len(goal.decomposition_passes) + 1

        decomp_pass = DecompositionPass(
            decomposition_id=decomposition_id,
            pass_number=pass_number,
            trigger=trigger,
            triggered_by=triggered_by,
            trigger_context=trigger_context,
            issue_ids_created=issue_ids_created,
        )

        goal.decomposition_passes.append(decomp_pass)
        goal.decomposition_id = decomposition_id
        existing = set(goal.issue_ids)
        new_ids = [iid for iid in issue_ids_created if iid not in existing]
        goal.issue_ids.extend(new_ids)
        goal.updated_at = datetime.now(timezone.utc)

        await self._save_goal_to_redis(goal)

        logger.info(
            f"Recorded decomposition pass #{pass_number} for goal {goal_id}: "
            f"trigger={trigger.value}, {len(issue_ids_created)} issues created"
        )
        return goal

    # ============ Intent Adjustment ============

    async def adjust_goal_intent(
        self,
        goal_id: str,
        request: GoalAdjustIntentRequest,
    ) -> Optional[Goal]:
        """Adjust a goal's intent and/or properties without recreating.

        Allows modifying intent classification, strength, title, description,
        and priority in a single operation.

        Args:
            goal_id: Goal ID to adjust
            request: Adjustment request with optional fields

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal or goal.deleted_at is not None:
            return None

        if request.title is not None:
            goal.title = request.title
        if request.description is not None:
            goal.description = request.description
        if request.priority is not None:
            goal.priority = request.priority
        if request.primary_intent is not None:
            goal.primary_intent = request.primary_intent
        if request.intent_strength is not None:
            goal.intent_strength = request.intent_strength

        if request.reparse_intent:
            # Re-analyze goal text for intent signals
            from services.goal_intent_service import get_goal_intent_service
            intent_service = get_goal_intent_service()
            intent_service.update_goal_intent(goal)

        goal.updated_at = datetime.now(timezone.utc)
        await self._save_goal_to_redis(goal)

        logger.info(f"Adjusted goal {goal_id} intent: {goal.primary_intent}")
        return goal

    async def set_reconciliation_weight(
        self,
        goal_id: str,
        weight: Optional[float],
    ) -> Optional[Goal]:
        """Set or clear a goal's reconciliation weight for multi-goal balancing.

        When set, this weight overrides automatic priority/recency-based
        weighting during profile reconciliation. Higher weight means more
        influence on the reconciled profile.

        Args:
            goal_id: Goal ID to update
            weight: Reconciliation weight (0.0-1.0), or None to reset to auto

        Returns:
            Updated Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal or goal.deleted_at is not None:
            return None

        goal.reconciliation_weight = weight
        goal.updated_at = datetime.now(timezone.utc)
        await self._save_goal_to_redis(goal)

        logger.info(
            f"Set reconciliation weight for goal {goal_id}: "
            f"{weight if weight is not None else 'auto'}"
        )
        return goal

    async def retire_goal(self, goal_id: str) -> Optional[Goal]:
        """Retire a goal without deleting its associated work.

        Transitions goal to RETIRED status. Associated issues continue
        to exist and can be worked on, but the goal no longer influences
        the planner profile.

        Args:
            goal_id: Goal ID to retire

        Returns:
            Retired Goal or None if not found
        """
        goal = self._goals.get(goal_id)
        if not goal or goal.deleted_at is not None:
            return None

        if goal.status == GoalStatus.RETIRED:
            return goal  # Already retired

        old_status = goal.status
        goal.status = GoalStatus.RETIRED
        goal.updated_at = datetime.now(timezone.utc)

        # Update Redis status index
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"goal:status:{old_status.value}"),
                goal_id
            )

        await self._save_goal_to_redis(goal)

        logger.info(f"Retired goal {goal_id}")
        return goal

    async def list_active_goals(
        self,
        project_id: str,
    ) -> List[Goal]:
        """List all active (non-retired, non-deleted, non-archived) goals for a project.

        Used for multi-goal profile construction.

        Args:
            project_id: Project to get active goals for

        Returns:
            List of active goals sorted by priority
        """
        active = [
            g for g in self._goals.values()
            if g.project_id == project_id
            and g.deleted_at is None
            and not g.archived
            and g.status not in (GoalStatus.DONE, GoalStatus.FAILED, GoalStatus.RETIRED)
        ]
        active.sort(key=lambda g: (g.priority.score_weight, g.created_at))
        return active

    # ============ Direct Access ============

    @property
    def goals(self) -> Dict[str, Goal]:
        """Direct access to goals dictionary for WorkMapService integration."""
        return self._goals


# Global instance
_goal_service: Optional[GoalService] = None


def get_goal_service() -> GoalService:
    """Get the global goal service instance."""
    if _goal_service is None:
        raise RuntimeError("Goal service not initialized")
    return _goal_service


def set_goal_service(service: GoalService) -> None:
    """Set the global goal service instance."""
    global _goal_service
    _goal_service = service
