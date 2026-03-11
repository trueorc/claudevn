"""Work Map Service for task allocation and tracking.

Manages goals, issues, and work items per the WorkMap specification:
- Goal: High-level objective, input to Planner (persistent)
- Issue: Unit of work with history (persistent)
- WorkItem: Active assignment to a Compute (ephemeral, Redis)

Uses Redis for work items and indexes, with in-memory caching.

This service acts as a facade coordinating:
- GoalService: Goal CRUD and lifecycle
- IssueOpsService: Issue CRUD and status management
- AssignmentService: Work assignment and status operations
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.work_map import (
    # Core models
    Goal, GoalStatus, GoalProgressMetrics, GoalCreateRequest, GoalListResponse, GoalDeleteResponse,
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueBatchCreateRequest, IssueBatchCreateResponse,
    IssueUpdateRequest, IssueListResponse, IssueStats, IssueResult,
    IssueHistory, IssueHistoryEntry,
    # Work item models (ephemeral)
    WorkItem, WorkStatus, WorkPriority, WorkCreateRequest,
    WorkUpdateRequest, WorkAssignment, ProgressReport, Blocker,
    BlockerType, WorkStats, WorkListResponse
)
from services.goal_service import GoalService
from services.issue_ops_service import IssueOpsService
from services.assignment_service import AssignmentService
from services.skill_selection_service import get_skill_selection_service
from services.goal_comment_service import (
    GoalCommentService,
    set_goal_comment_service
)
from services.goal_evaluation_service import (
    GoalEvaluationService,
    set_goal_evaluation_service
)

logger = logging.getLogger(__name__)


class WorkMapService:
    """Service for managing the work map.

    Provides:
    - Goal CRUD and lifecycle management (via GoalService)
    - Issue CRUD with status flow (via IssueOpsService)
    - Work item CRUD operations (ephemeral assignments)
    - Assignment algorithm matching issues to compute capabilities (via AssignmentService)
    - Dependency tracking and resolution
    - Blocker management
    """

    def __init__(self, redis_client=None):
        """Initialize work map service.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._work_items: Dict[str, WorkItem] = {}
        self._initialized = False

        # Initialize sub-services
        self._goal_service = GoalService(redis_client)
        self._issue_service = IssueOpsService(redis_client, self._goal_service)
        self._assignment_service = AssignmentService(redis_client)
        self._comment_service = GoalCommentService(redis_client)
        self._evaluation_service = GoalEvaluationService(self._comment_service)

        # Set cross-references
        self._goal_service.set_issues_reference(self._issue_service.issues)
        self._issue_service.set_goal_service(self._goal_service)
        self._assignment_service.set_work_items_reference(self._work_items)
        self._comment_service.set_goals_reference(self._goal_service.goals)

    async def initialize(self) -> None:
        """Initialize the service, loading data from Redis if available."""
        if self._initialized:
            return

        await self._goal_service.initialize()
        await self._issue_service.initialize()
        await self._assignment_service.initialize()
        await self._comment_service.initialize()
        set_goal_comment_service(self._comment_service)
        await self._evaluation_service.start()
        set_goal_evaluation_service(self._evaluation_service)
        await self._load_from_redis()
        self._initialized = True
        logger.info("Work map service initialized")

    async def _load_from_redis(self) -> None:
        """Load work items from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("work:*"),
                    count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    # Skip index keys
                    if any(x in key_str for x in [":status:", ":skill:", ":assignee:", ":depends_on:", ":blocks:", ":pending:"]):
                        continue
                    try:
                        data = await self._redis._redis.hgetall(key)
                        if data:
                            work_data = {
                                (k.decode() if isinstance(k, bytes) else k):
                                (v.decode() if isinstance(v, bytes) else v)
                                for k, v in data.items()
                            }
                            def _parse_dt(val: str) -> Optional[datetime]:
                                """Parse an ISO datetime string, returning None for empty/invalid."""
                                if not val:
                                    return None
                                try:
                                    return datetime.fromisoformat(val)
                                except (ValueError, TypeError):
                                    return None

                            work = WorkItem(
                                work_id=work_data.get('work_id', ''),
                                title=work_data.get('title', ''),
                                description=work_data.get('description', ''),
                                work_type=work_data.get('work_type', 'task'),
                                priority=WorkPriority(work_data.get('priority', 'normal')),
                                status=WorkStatus(work_data.get('status', 'pending')),
                                tags=json.loads(work_data.get('tags', '[]')),
                                required_skills=json.loads(work_data.get('required_skills', '[]')),
                                required_capabilities=json.loads(work_data.get('required_capabilities', '[]')),
                                required_labels=json.loads(work_data.get('required_labels', '[]')),
                                required_tools=json.loads(work_data.get('required_tools', '[]')),
                                skill_ids=json.loads(work_data.get('skill_ids', '[]')),
                                context=json.loads(work_data.get('context', '{}')),
                                depends_on=json.loads(work_data.get('depends_on', '[]')),
                                blocks=json.loads(work_data.get('blocks', '[]')),
                                issue_id=work_data.get('issue_id') or None,
                                project_id=work_data.get('project_id', ''),
                                base_branch=work_data.get('base_branch', 'main'),
                                branch_name=work_data.get('branch_name', ''),
                                assigned_to=work_data.get('assigned_to') or None,
                                assigned_skills=json.loads(work_data.get('assigned_skills', '[]')),
                                retry_count=int(work_data.get('retry_count', 0)),
                                progress_percent=int(work_data.get('progress_percent', 0)),
                                progress_notes=json.loads(work_data.get('progress_notes', '[]')),
                                error=work_data.get('error') or None,
                                assigned_at=_parse_dt(work_data.get('assigned_at', '')),
                                started_at=_parse_dt(work_data.get('started_at', '')),
                                completed_at=_parse_dt(work_data.get('completed_at', '')),
                                last_activity_at=_parse_dt(work_data.get('last_activity_at', '')),
                            )
                            # Restore persisted timestamps (override model defaults)
                            raw_created = _parse_dt(work_data.get('created_at', ''))
                            if raw_created:
                                work.created_at = raw_created
                            raw_updated = _parse_dt(work_data.get('updated_at', ''))
                            if raw_updated:
                                work.updated_at = raw_updated
                            self._work_items[work.work_id] = work
                    except Exception as e:
                        logger.error(f"Error loading work from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._work_items)} work items from Redis")
        except Exception as e:
            logger.error(f"Error loading work items from Redis: {e}")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}workmap:{key}"

    async def _save_to_redis(self, work: WorkItem) -> None:
        """Save work item to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"work:{work.work_id}")
            await self._redis._redis.hset(key, mapping={
                'work_id': work.work_id,
                'title': work.title,
                'description': work.description,
                'work_type': work.work_type,
                'priority': work.priority.value,
                'status': work.status.value,
                'tags': json.dumps(work.tags),
                'required_skills': json.dumps(work.required_skills),
                'required_capabilities': json.dumps(work.required_capabilities),
                'required_labels': json.dumps(work.required_labels),
                'required_tools': json.dumps(work.required_tools),
                'skill_ids': json.dumps(work.skill_ids),
                'context': json.dumps(work.context),
                'depends_on': json.dumps(work.depends_on),
                'blocks': json.dumps(work.blocks),
                'issue_id': work.issue_id or '',
                'project_id': work.project_id,
                'base_branch': work.base_branch,
                'branch_name': work.branch_name,
                'assigned_to': work.assigned_to or '',
                'assigned_skills': json.dumps(work.assigned_skills),
                'progress_percent': str(work.progress_percent),
                'progress_notes': json.dumps(work.progress_notes),
                'result': json.dumps(work.result) if work.result else '',
                'error': work.error or '',
                'blockers': json.dumps([b.model_dump(mode='json') for b in work.blockers]),
                'retry_count': str(work.retry_count),
                'created_at': work.created_at.isoformat(),
                'updated_at': work.updated_at.isoformat(),
                'assigned_at': work.assigned_at.isoformat() if work.assigned_at else '',
                'started_at': work.started_at.isoformat() if work.started_at else '',
                'completed_at': work.completed_at.isoformat() if work.completed_at else '',
                'last_activity_at': work.last_activity_at.isoformat() if work.last_activity_at else ''
            })

            # Update status index
            await self._redis._redis.sadd(
                self._key(f"work:status:{work.status.value}"),
                work.work_id
            )

            # Update skill indexes
            for skill in work.required_skills:
                await self._redis._redis.sadd(
                    self._key(f"workmap:work:skill:{skill}"),
                    work.work_id
                )

            # Update assignee index
            if work.assigned_to:
                await self._redis._redis.sadd(
                    self._key(f"work:assignee:{work.assigned_to}"),
                    work.work_id
                )
                await self._redis._redis.set(
                    self._key(f"workmap:compute:{work.assigned_to}:current"),
                    work.work_id
                )

            # Update dependency indexes
            for dep_id in work.depends_on:
                await self._redis._redis.sadd(
                    self._key(f"workmap:work:depends_on:{work.work_id}"),
                    dep_id
                )

            for blocked_id in work.blocks:
                await self._redis._redis.sadd(
                    self._key(f"workmap:work:blocks:{work.work_id}"),
                    blocked_id
                )

            # Update pending queue
            if work.status == WorkStatus.PENDING:
                priority_score = {
                    WorkPriority.CRITICAL: 0,
                    WorkPriority.HIGH: 1,
                    WorkPriority.NORMAL: 2,
                    WorkPriority.LOW: 3
                }.get(work.priority, 2)
                await self._redis._redis.zadd(
                    self._key("workmap:work:pending:queue"),
                    {work.work_id: priority_score}
                )
            else:
                await self._redis._redis.zrem(
                    self._key("workmap:work:pending:queue"),
                    work.work_id
                )

        except Exception as e:
            logger.error(f"Error saving work to Redis: {e}")

    async def _delete_from_redis(self, work_id: str) -> None:
        """Delete work item from Redis."""
        if not self._redis:
            return

        try:
            work = self._work_items.get(work_id)
            if work:
                # Remove from status index
                await self._redis._redis.srem(
                    self._key(f"work:status:{work.status.value}"),
                    work_id
                )
                # Remove from skill indexes
                for skill in work.required_skills:
                    await self._redis._redis.srem(
                        self._key(f"workmap:work:skill:{skill}"),
                        work_id
                    )
                # Remove from assignee index
                if work.assigned_to:
                    await self._redis._redis.srem(
                        self._key(f"work:assignee:{work.assigned_to}"),
                        work_id
                    )
                    await self._redis._redis.delete(
                        self._key(f"workmap:compute:{work.assigned_to}:current")
                    )
                # Remove from pending queue
                await self._redis._redis.zrem(
                    self._key("workmap:work:pending:queue"),
                    work_id
                )
                # Remove dependency indexes
                await self._redis._redis.delete(self._key(f"workmap:work:depends_on:{work_id}"))
                await self._redis._redis.delete(self._key(f"workmap:work:blocks:{work_id}"))

            await self._redis._redis.delete(self._key(f"work:{work_id}"))
        except Exception as e:
            logger.error(f"Error deleting work from Redis: {e}")

    # ============ Goal Operations (delegated to GoalService) ============

    @property
    def _goals(self) -> Dict[str, Goal]:
        """Access goals dictionary for backwards compatibility."""
        return self._goal_service.goals

    @property
    def _issues(self) -> Dict[str, Issue]:
        """Access issues dictionary for backwards compatibility."""
        return self._issue_service.issues

    async def create_goal(self, request: GoalCreateRequest) -> Goal:
        """Create a new goal."""
        return await self._goal_service.create_goal(request)

    async def get_goal(
        self,
        goal_id: str,
        include_deleted: bool = False
    ) -> Optional[Goal]:
        """Get a goal by ID."""
        return await self._goal_service.get_goal(goal_id, include_deleted)

    async def list_goals(
        self,
        status: Optional[GoalStatus] = None,
        project_id: Optional[str] = None,
        include_deleted: bool = False,
        include_archived: bool = False,
        limit: int = 100
    ) -> GoalListResponse:
        """List goals with optional filtering."""
        return await self._goal_service.list_goals(
            status=status,
            project_id=project_id,
            include_deleted=include_deleted,
            include_archived=include_archived,
            limit=limit
        )

    async def update_goal_status(
        self,
        goal_id: str,
        status: GoalStatus
    ) -> Optional[Goal]:
        """Update goal status."""
        return await self._goal_service.update_goal_status(goal_id, status)

    async def delete_goal(
        self,
        goal_id: str,
        hard: bool = False,
        cascade: bool = False
    ) -> Optional[GoalDeleteResponse]:
        """Delete a goal (soft delete by default), optionally cascading.

        Args:
            goal_id: Goal to delete
            hard: If True, permanently delete
            cascade: If True and hard=True, also delete child issues and work items
        """
        goal = await self._goal_service.get_goal(goal_id, include_deleted=True)
        if not goal:
            return None

        issue_count = 0
        work_item_count = 0

        if cascade and hard:
            # Delete all issues belonging to this goal (cascade to work items)
            issue_ids = list(goal.issue_ids) if goal.issue_ids else []
            # Also find issues referencing this goal that aren't in issue_ids
            for issue in list(self._issue_service._issues.values()):
                if issue.goal_id == goal_id and issue.issue_id not in issue_ids:
                    issue_ids.append(issue.issue_id)

            for iid in issue_ids:
                result = await self.delete_issue(iid, cascade=True)
                if result.get("deleted"):
                    issue_count += 1
                    issue_count += result.get("child_issue_count", 0)
                    work_item_count += result.get("work_item_count", 0)

        response = await self._goal_service.delete_goal(goal_id, hard)
        if response:
            response.issue_count = issue_count
            response.work_item_count = work_item_count
        return response

    async def restore_goal(self, goal_id: str) -> Optional[Goal]:
        """Restore a soft-deleted goal."""
        return await self._goal_service.restore_goal(goal_id)

    async def archive_goal(self, goal_id: str) -> Optional[Goal]:
        """Archive a goal."""
        return await self._goal_service.archive_goal(goal_id)

    async def unarchive_goal(self, goal_id: str) -> Optional[Goal]:
        """Unarchive a goal."""
        return await self._goal_service.unarchive_goal(goal_id)

    async def get_goal_issues(self, goal_id: str) -> List[Issue]:
        """Get all issues for a goal."""
        return await self._goal_service.get_goal_issues(goal_id)

    async def update_goal_issues(
        self,
        goal_id: str,
        issue_ids: List[str],
    ) -> Optional[Goal]:
        """Update the issue_ids list for a goal."""
        return await self._goal_service.update_goal_issues(goal_id, issue_ids)

    async def update_goal_decomposition_id(
        self,
        goal_id: str,
        decomposition_id: str,
    ) -> Optional[Goal]:
        """Update the decomposition_id for a goal."""
        return await self._goal_service.update_goal_decomposition_id(goal_id, decomposition_id)

    async def get_goal_progress(self, goal_id: str) -> Optional[GoalProgressMetrics]:
        """Get multi-dimensional progress metrics for a goal."""
        return await self._goal_service.get_goal_progress(goal_id)

    async def _check_goal_completion(self, goal_id: str) -> None:
        """Check if all issues for a goal are complete."""
        await self._goal_service.check_goal_completion(goal_id)

    # ============ Issue Operations (delegated to IssueOpsService) ============

    async def create_issue(self, request: IssueCreateRequest) -> Issue:
        """Create a new issue."""
        return await self._issue_service.create_issue(request)

    async def create_issues_batch(
        self,
        request: IssueBatchCreateRequest
    ) -> IssueBatchCreateResponse:
        """Create multiple issues at once."""
        return await self._issue_service.create_issues_batch(request)

    async def get_issue(self, issue_id: str) -> Optional[Issue]:
        """Get an issue by ID."""
        return await self._issue_service.get_issue(issue_id)

    async def update_issue(
        self,
        issue_id: str,
        request: IssueUpdateRequest
    ) -> Optional[Issue]:
        """Update an issue."""
        return await self._issue_service.update_issue(issue_id, request)

    async def update_issue_status(
        self,
        issue_id: str,
        status: IssueStatus,
        compute_id: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Optional[Issue]:
        """Update issue status with validation."""
        issue = await self._issue_service.update_issue_status(
            issue_id, status, compute_id, reason=reason
        )

        # When an issue resets to BACKLOG (or auto-promotes to READY),
        # mark any non-terminal work items as FAILED so a fresh work item
        # can be created, and clear orchestrator retry state.
        actual_status = issue.status if issue else status
        if issue and (status in (IssueStatus.BACKLOG, IssueStatus.READY)
                      or actual_status in (IssueStatus.BACKLOG, IssueStatus.READY)):
            from models.work_map import WorkStatus
            for work in list(self._work_items.values()):
                if work.issue_id == issue_id and work.status not in (
                    WorkStatus.COMPLETED, WorkStatus.FAILED
                ):
                    old_status = work.status
                    work.status = WorkStatus.FAILED
                    work.error = f"Reset: issue moved to {status.value}"
                    logger.info(
                        f"Marked work {work.work_id} as FAILED "
                        f"(was {old_status.value}) due to issue reset"
                    )
            try:
                from services.work_orchestrator import get_work_orchestrator
                orchestrator = get_work_orchestrator()
                if orchestrator:
                    for work in self._work_items.values():
                        if work.issue_id == issue_id:
                            orchestrator.clear_retry_state(work.work_id)
            except Exception:
                pass  # Orchestrator may not be initialized yet

        return issue

    async def complete_issue(
        self,
        issue_id: str,
        result: IssueResult,
        compute_id: Optional[str] = None
    ) -> Optional[Issue]:
        """Mark an issue as done with result."""
        return await self._issue_service.complete_issue(issue_id, result, compute_id)

    async def delete_issue(self, issue_id: str, cascade: bool = False) -> dict:
        """Delete an issue, optionally cascading to children.

        Args:
            issue_id: Issue to delete
            cascade: If True, also delete child issues and work items

        Returns:
            Dict with deletion counts: {"deleted": bool, "child_issue_count": int, "work_item_count": int}
        """
        if issue_id not in self._issue_service._issues:
            return {"deleted": False, "child_issue_count": 0, "work_item_count": 0}

        child_issue_count = 0
        work_item_count = 0

        if cascade:
            # Delete work items linked to this issue
            work_ids_to_delete = [
                w.work_id for w in self._work_items.values()
                if w.issue_id == issue_id
            ]
            for work_id in work_ids_to_delete:
                await self.delete_work(work_id)
                work_item_count += 1

            # Delete child issues (and their work items recursively)
            child_ids = [
                i.issue_id for i in self._issue_service._issues.values()
                if i.parent_issue_id == issue_id
            ]
            for child_id in child_ids:
                child_result = await self.delete_issue(child_id, cascade=True)
                child_issue_count += 1
                child_issue_count += child_result.get("child_issue_count", 0)
                work_item_count += child_result.get("work_item_count", 0)

        deleted = await self._issue_service.delete_issue(issue_id)
        return {
            "deleted": deleted,
            "child_issue_count": child_issue_count,
            "work_item_count": work_item_count,
        }

    async def list_issues(
        self,
        status: Optional[IssueStatus] = None,
        priority: Optional[IssuePriority] = None,
        area: Optional[IssueArea] = None,
        goal_id: Optional[str] = None,
        skill: Optional[str] = None,
        release_id: Optional[str] = None,
        project_id: Optional[str] = None,
        work_type: Optional[str] = None,
        lifecycle_stage: Optional[str] = None,
        technical_domain: Optional[str] = None,
        limit: int = 100
    ) -> IssueListResponse:
        """List issues with optional filtering."""
        return await self._issue_service.list_issues(
            status, priority, area, goal_id, skill, release_id, project_id,
            work_type, lifecycle_stage, technical_domain, limit
        )

    async def get_ready_queue(self, limit: int = 50) -> List[Issue]:
        """Get the ready queue sorted by priority score."""
        return await self._issue_service.get_ready_queue(limit)

    async def get_issue_stats(self) -> IssueStats:
        """Get issue statistics."""
        return await self._issue_service.get_issue_stats()

    async def get_issue_history(self, issue_id: str) -> IssueHistory:
        """Get history of changes for an issue."""
        return await self._issue_service.get_issue_history(issue_id)

    async def assign_issue_to_compute(
        self,
        issue_id: str,
        compute_id: str,
        skills: List[str]
    ) -> Optional[Issue]:
        """Assign a ready issue to a compute instance."""
        return await self._issue_service.assign_issue_to_compute(issue_id, compute_id, skills)

    async def get_next_issue_assignment(
        self,
        compute_id: str,
        compute_skills: List[str],
        compute_labels: Optional[List[str]] = None,
        compute_tools_available: Optional[List[str]] = None
    ) -> Optional[Issue]:
        """Get the next issue assignment for a compute instance."""
        return await self._issue_service.get_next_issue_assignment(
            compute_id, compute_skills, compute_labels, compute_tools_available
        )

    async def set_issue_compute_id(
        self, issue_id: str, compute_id: str
    ) -> Optional[Issue]:
        """Set assigned_compute_id on an Issue without changing status.

        Args:
            issue_id: Issue ID to update
            compute_id: Compute instance ID to assign

        Returns:
            Updated Issue, or None if not found
        """
        issue = await self._issue_service.get_issue(issue_id)
        if not issue:
            return None

        issue.assigned_compute_id = compute_id
        await self._issue_service._save_issue_to_redis(issue)
        logger.info(f"Set assigned_compute_id={compute_id} on issue {issue_id}")
        return issue

    # ============ Issue-to-Work Bridge ============

    async def create_work_from_issue(self, issue_id: str) -> Optional[WorkItem]:
        """Convert a ready Issue into a pending WorkItem.

        This bridges the backlog (Issues) to execution (WorkItems) by:
        1. Validating the issue exists and is in READY status
        2. Looking up the project's git repo info via ProjectService
        3. Creating a WorkItem with issue context

        The issue status remains READY until the work item is actually
        dispatched to a compute instance (see work_orchestrator.py).

        Args:
            issue_id: ID of the issue to convert

        Returns:
            Created WorkItem, or None if conversion failed
        """
        from services.project_service import get_project_service

        issue = await self._issue_service.get_issue(issue_id)
        if not issue:
            logger.warning(f"Cannot create work from issue {issue_id}: issue not found")
            return None

        if issue.status != IssueStatus.READY:
            logger.warning(
                f"Cannot create work from issue {issue_id}: "
                f"status is {issue.status}, expected READY"
            )
            return None

        # Check if a WorkItem already exists for this issue
        for work in self._work_items.values():
            if work.context.get("issue_id") == issue_id and work.status not in [
                WorkStatus.COMPLETED, WorkStatus.FAILED
            ]:
                logger.warning(
                    f"WorkItem {work.work_id} already exists for issue {issue_id}"
                )
                return None

        # Get project git info — always resolve through resolve_repo_details()
        # so compute gets the internal serving URL, never an external origin.
        repo_url = None
        base_branch = "main"
        if issue.project_id:
            try:
                project_service = get_project_service()
                repo_details = await project_service.resolve_repo_details(issue.project_id)
                if repo_details:
                    repo_url = repo_details["clone_url"]
                    base_branch = repo_details["default_branch"]
                else:
                    # Fallback: try project-level default
                    project = await project_service.get_project(issue.project_id)
                    if project:
                        base_branch = project.default_base_branch
            except Exception as e:
                logger.warning(f"Error getting project info for issue {issue_id}: {e}")

        # Map IssuePriority to WorkPriority
        priority_map = {
            IssuePriority.P0: WorkPriority.CRITICAL,
            IssuePriority.P1: WorkPriority.HIGH,
            IssuePriority.P2: WorkPriority.NORMAL,
            IssuePriority.P3: WorkPriority.LOW,
        }
        work_priority = priority_map.get(issue.priority, WorkPriority.NORMAL)

        # Map IssueType to work_type
        type_map = {
            IssueType.FEATURE: "feature",
            IssueType.BUG: "bug",
            IssueType.REFACTOR: "refactor",
            IssueType.DOCS: "docs",
            IssueType.TEST: "test",
        }
        work_type = type_map.get(issue.issue_type, "task")

        # Build context linking back to the issue
        context = {
            "issue_id": issue_id,
            "goal_id": issue.goal_id,
        }
        if repo_url:
            context["repo_url"] = repo_url
            context["repository"] = repo_url

        # Create the WorkItem via existing create_work method
        request = WorkCreateRequest(
            title=issue.title,
            description=issue.description,
            work_type=work_type,
            priority=work_priority,
            required_skills=issue.required_skills,
            required_labels=issue.required_labels,
            required_tools=issue.required_tools,
            context=context,
            issue_id=issue_id,
            project_id=issue.project_id or "default",
            base_branch=base_branch,
        )

        work = await self.create_work(request)

        logger.info(
            f"Created work {work.work_id} from issue {issue_id}: {issue.title}"
        )
        return work

    async def fail_work_and_update_issue(
        self,
        work_id: str,
        error: str,
        compute_id: Optional[str] = None
    ) -> Optional[WorkItem]:
        """Fail a WorkItem and update its parent Issue.

        Args:
            work_id: WorkItem ID that failed
            error: Error description
            compute_id: Compute instance that reported the failure

        Returns:
            Failed WorkItem, or None if update failed
        """
        work = self._work_items.get(work_id)
        if not work:
            return None

        work.error = error
        updated = await self._assignment_service.update_status(
            work_id, WorkStatus.FAILED, compute_id,
            save_callback=self._save_to_redis
        )
        if not updated:
            return None

        # Update the parent issue if linked
        issue_id = work.context.get("issue_id")
        if issue_id:
            await self._issue_service.update_issue_status(
                issue_id, IssueStatus.FAILED, compute_id
            )
            logger.info(
                f"Work {work_id} failed, issue {issue_id} marked as failed"
            )

        # Emit failure notification
        try:
            from services.notification_service import get_notification_service
            from models.notification import NotificationLevel, NotificationCategory
            svc = get_notification_service()
            svc.emit(
                title=f"Work failed: {work.title}",
                message=error,
                level=NotificationLevel.ERROR,
                category=NotificationCategory.WORK,
                project_id=work.project_id,
                entity_id=work_id,
            )
        except Exception:
            pass

        return work

    # ============ Work Item CRUD Operations ============

    async def create_work(self, request: WorkCreateRequest) -> WorkItem:
        """Create a new work item."""
        work_id = f"work_{uuid.uuid4().hex[:12]}"

        # Build hook-compliant branch name: {type}/{issue_or_work_id}
        # Full branch ({type}/{id}/{compute_id}) set at assignment time by orchestrator
        _type_prefix_map = {
            "feature": "f", "bug": "b", "refactor": "r",
            "docs": "d", "test": "t",
        }
        type_prefix = _type_prefix_map.get(request.work_type, "f")
        issue_or_work_id = request.issue_id or work_id
        branch_name = f"{type_prefix}/{issue_or_work_id}"

        skill_ids = request.skill_ids if hasattr(request, 'skill_ids') and request.skill_ids else []
        if not skill_ids and request.required_capabilities:
            try:
                skill_service = get_skill_selection_service()
                temp_work = WorkItem(
                    work_id=work_id,
                    title=request.title,
                    description=request.description,
                    work_type=request.work_type,
                    priority=request.priority,
                    tags=request.tags,
                    required_skills=request.required_skills,
                    required_capabilities=request.required_capabilities,
                    required_labels=request.required_labels,
                    required_tools=request.required_tools,
                    context=request.context,
                    depends_on=request.depends_on,
                    project_id=request.project_id,
                    base_branch=request.base_branch,
                    branch_name=branch_name,
                )
                skill_ids = await skill_service.select_skills(temp_work)
                logger.info(f"Auto-selected skills {skill_ids} for work {work_id}")
            except Exception as e:
                logger.error(f"Error auto-selecting skills for work {work_id}: {e}")
                skill_ids = []

        work = WorkItem(
            work_id=work_id,
            title=request.title,
            description=request.description,
            work_type=request.work_type,
            priority=request.priority,
            tags=request.tags,
            required_skills=request.required_skills,
            required_capabilities=request.required_capabilities,
            required_labels=request.required_labels,
            required_tools=request.required_tools,
            skill_ids=skill_ids,
            context=request.context,
            depends_on=request.depends_on,
            issue_id=request.issue_id,
            project_id=request.project_id,
            base_branch=request.base_branch,
            branch_name=branch_name,
            status=WorkStatus.PENDING
        )

        # Update dependency graph
        for dep_id in request.depends_on:
            if dep_id in self._work_items:
                dep_work = self._work_items[dep_id]
                if work_id not in dep_work.blocks:
                    dep_work.blocks.append(work_id)
                    await self._save_to_redis(dep_work)

        self._work_items[work_id] = work
        await self._save_to_redis(work)

        logger.info(f"Created work item {work_id}: {work.title}")
        return work

    async def get_work(self, work_id: str) -> Optional[WorkItem]:
        """Get a work item by ID."""
        return self._work_items.get(work_id)

    async def update_work(self, work_id: str, request: WorkUpdateRequest) -> Optional[WorkItem]:
        """Update a work item."""
        work = self._work_items.get(work_id)
        if not work:
            return None

        if request.title is not None:
            work.title = request.title
        if request.description is not None:
            work.description = request.description
        if request.priority is not None:
            work.priority = request.priority
        if request.tags is not None:
            work.tags = request.tags
        if request.context is not None:
            work.context.update(request.context)

        work.updated_at = datetime.now(timezone.utc)
        await self._save_to_redis(work)

        logger.info(f"Updated work item {work_id}")
        return work

    async def delete_work(self, work_id: str) -> bool:
        """Delete a work item."""
        if work_id not in self._work_items:
            return False

        work = self._work_items[work_id]

        # Remove from dependency graph
        for dep_id in work.depends_on:
            if dep_id in self._work_items:
                dep_work = self._work_items[dep_id]
                if work_id in dep_work.blocks:
                    dep_work.blocks.remove(work_id)
                    await self._save_to_redis(dep_work)

        await self._delete_from_redis(work_id)
        del self._work_items[work_id]

        logger.info(f"Deleted work item {work_id}")
        return True

    async def cascade_delete_project(self, project_id: str) -> dict:
        """Cascade-delete a project and all its children.

        Deletes goals → issues → work items belonging to the project.

        Args:
            project_id: Project to cascade-delete

        Returns:
            Dict with deletion counts
        """
        goal_count = 0
        issue_count = 0
        work_item_count = 0
        comment_count = 0

        # Find all goals belonging to this project
        goal_ids = [
            g.goal_id for g in self._goal_service._goals.values()
            if g.project_id == project_id
        ]

        for gid in goal_ids:
            # Count comments before deleting
            try:
                comments = await self._comment_service.list_comments(gid, limit=1000)
                if comments:
                    comment_count += comments.total
                    for comment in comments.items:
                        await self._comment_service.delete_comment(comment.comment_id)
            except Exception:
                pass

            result = await self.delete_goal(gid, hard=True, cascade=True)
            if result:
                goal_count += 1
                issue_count += result.issue_count
                work_item_count += result.work_item_count
                comment_count += result.comment_count

        # Delete orphaned work items for this project (not linked via goals/issues)
        orphan_work_ids = [
            w.work_id for w in self._work_items.values()
            if w.project_id == project_id
        ]
        for wid in orphan_work_ids:
            await self.delete_work(wid)
            work_item_count += 1

        return {
            "goal_count": goal_count,
            "issue_count": issue_count,
            "work_item_count": work_item_count,
            "comment_count": comment_count,
        }

    # ============ Assignment Operations (delegated to AssignmentService) ============

    async def assign_work(
        self,
        work_id: str,
        compute_id: str,
        skills: List[str],
        branch_name: Optional[str] = None
    ) -> Optional[WorkAssignment]:
        """Assign work to a compute instance."""
        return await self._assignment_service.assign_work(
            work_id, compute_id, skills,
            save_callback=self._save_to_redis,
            branch_name=branch_name
        )

    async def unassign_work(self, work_id: str) -> bool:
        """Unassign work from a compute instance."""
        return await self._assignment_service.unassign_work(
            work_id, save_callback=self._save_to_redis
        )

    async def get_compute_current_work(self, compute_id: str) -> Optional[str]:
        """Get the current work assignment for a compute instance."""
        return await self._assignment_service.get_compute_current_work(compute_id)

    async def get_work_by_skill(self, skill: str) -> List[WorkItem]:
        """Get all work items requiring a specific skill."""
        return await self._assignment_service.get_work_by_skill(skill)

    async def get_work_blockers(self, work_id: str) -> List[str]:
        """Get IDs of work items that block a given work item."""
        return await self._assignment_service.get_work_blockers(work_id)

    async def get_blocked_by_work(self, work_id: str) -> List[str]:
        """Get IDs of work items that are blocked by a given work item."""
        return await self._assignment_service.get_blocked_by_work(work_id)

    async def get_pending_queue(self, limit: int = 50) -> List[WorkItem]:
        """Get the pending work queue sorted by priority score."""
        return await self._assignment_service.get_pending_queue(limit)

    async def get_next_assignment(
        self,
        compute_id: str,
        capabilities: List[str],
        labels: Optional[List[str]] = None,
        tools_available: Optional[List[str]] = None
    ) -> Optional[WorkAssignment]:
        """Get the next work assignment for a compute instance."""
        return await self._assignment_service.get_next_assignment(
            compute_id, capabilities, labels, tools_available,
            save_callback=self._save_to_redis
        )

    # ============ Status Operations (delegated to AssignmentService) ============

    async def update_status(
        self,
        work_id: str,
        status: WorkStatus,
        compute_id: Optional[str] = None
    ) -> Optional[WorkItem]:
        """Update work status with validation."""
        return await self._assignment_service.update_status(
            work_id, status, compute_id, save_callback=self._save_to_redis
        )

    async def report_progress(
        self,
        work_id: str,
        report: ProgressReport
    ) -> Optional[WorkItem]:
        """Report progress on work."""
        return await self._assignment_service.report_progress(
            work_id, report, save_callback=self._save_to_redis
        )

    async def complete_work(
        self,
        work_id: str,
        result: Dict[str, Any],
        compute_id: Optional[str] = None,
        trigger_cascade: bool = True
    ) -> Optional[WorkItem]:
        """Mark work as completed with result.

        After completing the work item, if it has a parent issue_id,
        auto-complete the parent Issue which triggers the dependency
        cascade (unblocking dependent Issues from backlog → ready).

        Set trigger_cascade=False to suppress the dependency cascade,
        allowing the caller to merge PRs before triggering it via
        cascade_dependents().
        """
        work = await self._assignment_service.complete_work(
            work_id, result, compute_id, save_callback=self._save_to_redis
        )
        if not work:
            return None

        if work.issue_id:
            await self._complete_parent_issue(work, trigger_cascade=trigger_cascade)

        return work

    async def cascade_dependents(self, work_id: str) -> List[str]:
        """Trigger dependency cascade for a completed work item's parent issue.

        Looks up the parent issue for the work item and, if it's DONE,
        triggers _check_unblock_issue_dependents to move dependent issues
        from BACKLOG → READY.

        This is idempotent — already-READY issues stay READY.

        Returns:
            List of issue IDs that were unblocked.
        """
        work = self._work_items.get(work_id)
        if not work or not work.issue_id:
            return []

        issue = await self._issue_service.get_issue(work.issue_id)
        if not issue or issue.status != IssueStatus.DONE:
            return []

        return await self._issue_service._check_unblock_issue_dependents(work.issue_id)

    async def revert_completed_work(self, work_id: str) -> bool:
        """Revert a completed work item and its parent issue back to IN_PROGRESS.

        Called when the PR merge fails after work was already marked COMPLETED.
        This prevents dependent work from being dispatched against unmerged code.

        Returns:
            True if revert succeeded, False if work not found or not completed.
        """
        work = self._work_items.get(work_id)
        if not work or work.status != WorkStatus.COMPLETED:
            return False

        # Revert work item to IN_PROGRESS
        work.status = WorkStatus.IN_PROGRESS
        work.result = None
        await self._save_to_redis(work)
        logger.info(f"Reverted work {work_id} from COMPLETED to IN_PROGRESS")

        # Revert parent issue: DONE → BACKLOG → READY → IN_PROGRESS
        # (following valid transition rules)
        if work.issue_id:
            issue = await self._issue_service.get_issue(work.issue_id)
            if issue and issue.status == IssueStatus.DONE:
                reason = "PR merge or quality gates failed — reverting to retry"
                await self._issue_service.update_issue_status(
                    work.issue_id, IssueStatus.BACKLOG, reason=reason, trigger_cascade=False
                )
                await self._issue_service.update_issue_status(
                    work.issue_id, IssueStatus.READY, trigger_cascade=False
                )
                await self._issue_service.update_issue_status(
                    work.issue_id, IssueStatus.IN_PROGRESS, trigger_cascade=False
                )
                logger.info(
                    f"Reverted issue {work.issue_id} from DONE to IN_PROGRESS "
                    f"(work {work_id} merge failed)"
                )

        return True

    async def _complete_parent_issue(self, work: WorkItem, trigger_cascade: bool = True) -> None:
        """Complete the parent Issue when its WorkItem finishes.

        Marks the parent Issue as DONE with the work result. When
        trigger_cascade=True (default), also triggers
        _check_unblock_issue_dependents to cascade and move dependent
        Issues from backlog → ready.
        """
        issue = await self._issue_service.get_issue(work.issue_id)
        if not issue:
            logger.warning(f"Parent issue {work.issue_id} not found for work {work.work_id}")
            return

        if issue.status == IssueStatus.DONE:
            return

        issue_result = IssueResult(
            summary=work.result.get("summary", "") if work.result else "",
            branch=work.branch_name,
        )

        completed = await self._issue_service.complete_issue(
            work.issue_id, issue_result, work.assigned_to, trigger_cascade=trigger_cascade
        )
        if completed:
            logger.info(
                f"Auto-completed issue {work.issue_id} from work {work.work_id} "
                f"(cascade will unblock dependents)"
            )

    # ============ Blocker Operations (delegated to AssignmentService) ============

    async def add_blocker(
        self,
        work_id: str,
        blocker_type: BlockerType,
        description: str,
        blocking_work_id: Optional[str] = None
    ) -> Optional[Blocker]:
        """Add a blocker to work."""
        return await self._assignment_service.add_blocker(
            work_id, blocker_type, description, blocking_work_id,
            save_callback=self._save_to_redis
        )

    async def resolve_blocker(
        self,
        work_id: str,
        blocker_id: str,
        resolution_note: Optional[str] = None,
        resolved_by: Optional[str] = None
    ) -> bool:
        """Resolve a blocker."""
        return await self._assignment_service.resolve_blocker(
            work_id, blocker_id, resolution_note, resolved_by,
            save_callback=self._save_to_redis
        )

    # ============ Query Operations ============

    async def list_work(
        self,
        status: Optional[WorkStatus] = None,
        project_id: Optional[str] = None,
        assigned_to: Optional[str] = None,
        priority: Optional[WorkPriority] = None,
        limit: int = 100
    ) -> WorkListResponse:
        """List work items with optional filters."""
        items = list(self._work_items.values())

        if status:
            items = [w for w in items if w.status == status]
        if project_id:
            items = [w for w in items if w.project_id == project_id]
        if assigned_to:
            items = [w for w in items if w.assigned_to == assigned_to]
        if priority:
            items = [w for w in items if w.priority == priority]

        items.sort(key=lambda w: (
            -[WorkPriority.CRITICAL, WorkPriority.HIGH,
              WorkPriority.NORMAL, WorkPriority.LOW].index(w.priority),
            w.created_at
        ))

        items = items[:limit]

        all_items = list(self._work_items.values())
        by_status = {}
        by_priority = {}

        for w in all_items:
            by_status[w.status.value] = by_status.get(w.status.value, 0) + 1
            by_priority[w.priority.value] = by_priority.get(w.priority.value, 0) + 1

        return WorkListResponse(
            items=items,
            total=len(all_items),
            by_status=by_status,
            by_priority=by_priority
        )

    async def get_stats(self) -> WorkStats:
        """Get work map statistics."""
        all_items = list(self._work_items.values())

        by_status = {}
        by_priority = {}
        by_project = {}
        blocked_count = 0
        assigned_count = 0
        unassigned_count = 0

        for w in all_items:
            by_status[w.status.value] = by_status.get(w.status.value, 0) + 1
            by_priority[w.priority.value] = by_priority.get(w.priority.value, 0) + 1
            by_project[w.project_id] = by_project.get(w.project_id, 0) + 1

            if w.is_blocked:
                blocked_count += 1
            if w.assigned_to:
                assigned_count += 1
            else:
                unassigned_count += 1

        return WorkStats(
            total=len(all_items),
            by_status=by_status,
            by_priority=by_priority,
            by_project=by_project,
            blocked_count=blocked_count,
            assigned_count=assigned_count,
            unassigned_count=unassigned_count
        )

    async def get_dependencies(self, work_id: str) -> Dict[str, Any]:
        """Get dependency information for work."""
        work = self._work_items.get(work_id)
        if not work:
            return {}

        depends_on = []
        for dep_id in work.depends_on:
            dep = self._work_items.get(dep_id)
            if dep:
                depends_on.append({
                    'work_id': dep.work_id,
                    'title': dep.title,
                    'status': dep.status.value,
                    'completed': dep.status == WorkStatus.COMPLETED
                })

        blocks = []
        for blocked_id in work.blocks:
            blocked = self._work_items.get(blocked_id)
            if blocked:
                blocks.append({
                    'work_id': blocked.work_id,
                    'title': blocked.title,
                    'status': blocked.status.value
                })

        return {
            'work_id': work_id,
            'depends_on': depends_on,
            'blocks': blocks,
            'all_dependencies_met': all(d['completed'] for d in depends_on)
        }

    async def get_dependencies_bulk(self, work_ids: List[str]) -> Dict[str, bool]:
        """Check dependency status for multiple work items in one call.

        Returns a mapping of work_id -> all_dependencies_met (bool).
        This avoids N individual get_dependencies() calls in the
        orchestrator poll loop.

        Args:
            work_ids: List of work IDs to check

        Returns:
            Dict mapping work_id to whether all dependencies are met
        """
        result: Dict[str, bool] = {}

        for work_id in work_ids:
            work = self._work_items.get(work_id)
            if not work:
                result[work_id] = True  # Unknown work — don't block
                continue

            if not work.depends_on:
                result[work_id] = True
                continue

            all_met = True
            for dep_id in work.depends_on:
                dep = self._work_items.get(dep_id)
                if dep and dep.status != WorkStatus.COMPLETED:
                    all_met = False
                    break

            result[work_id] = all_met

        return result

    # ============ Timeout Operations (delegated to AssignmentService) ============

    async def get_stale_work(self, timeout_minutes: int) -> List[WorkItem]:
        """Get work items that have been IN_PROGRESS for too long without activity."""
        return await self._assignment_service.get_stale_work(timeout_minutes)

    async def get_stale_assigned_work(self, assigned_timeout_minutes: int) -> List[WorkItem]:
        """Get ASSIGNED work items that were never started by a compute."""
        return await self._assignment_service.get_stale_assigned_work(assigned_timeout_minutes)

    async def reset_assigned_to_pending(self, work_id: str) -> Optional[WorkItem]:
        """Reset a stale ASSIGNED work item back to PENDING for re-dispatch."""
        return await self._assignment_service.reset_assigned_to_pending(
            work_id, save_callback=self._save_to_redis
        )

    async def mark_work_timed_out(
        self,
        work_id: str,
        max_retries: int
    ) -> Optional[WorkItem]:
        """Handle work that has timed out."""
        return await self._assignment_service.mark_work_timed_out(
            work_id, max_retries, save_callback=self._save_to_redis
        )

    async def get_failed_work(self, max_retries: int) -> List[WorkItem]:
        """Get FAILED work items eligible for retry."""
        return await self._assignment_service.get_failed_work(max_retries)

    async def mark_work_for_retry(
        self,
        work_id: str,
        max_retries: int
    ) -> Optional[WorkItem]:
        """Return a FAILED work item to PENDING for retry.

        Also resets the parent issue status to IN_PROGRESS so that
        subsequent failure doesn't trigger invalid FAILED→FAILED transition.
        """
        work = self._work_items.get(work_id)
        result = await self._assignment_service.mark_work_for_retry(
            work_id, max_retries, save_callback=self._save_to_redis
        )

        # Reset parent issue status when work successfully returns to PENDING
        if result and result.status == WorkStatus.PENDING and work:
            issue_id = work.context.get("issue_id") if work.context else None
            if issue_id:
                await self._issue_service.update_issue_status(
                    issue_id, IssueStatus.IN_PROGRESS
                )
                logger.info(
                    f"Reset issue {issue_id} to IN_PROGRESS for work retry"
                )

        return result


# Global instance
_work_map_service: Optional[WorkMapService] = None


def get_work_map_service() -> WorkMapService:
    """Get the global work map service instance."""
    if _work_map_service is None:
        raise RuntimeError("Work map service not initialized")
    return _work_map_service


def set_work_map_service(service: WorkMapService) -> None:
    """Set the global work map service instance."""
    global _work_map_service
    _work_map_service = service
