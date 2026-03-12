"""Issue Operations Service for issue CRUD and status management.

Extracted from work_map_service.py to reduce service size and improve maintainability.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from models.work_map import (
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueBatchCreateRequest, IssueBatchCreateResponse,
    IssueUpdateRequest, IssueListResponse, IssueStats, IssueResult,
    IssueHistory, IssueHistoryEntry, GoalStatus,
    EvaluationStatus, IssueEvaluationResult,
)

if TYPE_CHECKING:
    from services.goal_service import GoalService

logger = logging.getLogger(__name__)


class IssueOpsService:
    """Service for managing issues.

    Provides:
    - Issue CRUD operations
    - Status transitions with validation
    - Dependency tracking and cycle detection
    - Issue assignment to compute instances
    """

    def __init__(self, redis_client=None, goal_service: Optional["GoalService"] = None):
        """Initialize issue operations service.

        Args:
            redis_client: Optional Redis client for persistence
            goal_service: Optional goal service for goal-issue coordination
        """
        self._redis = redis_client
        self._goal_service = goal_service
        self._issues: Dict[str, Issue] = {}
        self._initialized = False

    def set_goal_service(self, goal_service: "GoalService") -> None:
        """Set goal service reference for goal-issue coordination."""
        self._goal_service = goal_service

    async def initialize(self) -> None:
        """Initialize the service, loading data from Redis if available."""
        if self._initialized:
            return

        await self._load_issues_from_redis()
        self._initialized = True
        logger.info("Issue operations service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}workmap:{key}"

    # ============ Redis Persistence ============

    async def _load_issues_from_redis(self) -> None:
        """Load issues from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("issue:data:*"),
                    count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    try:
                        data = await self._redis._redis.hgetall(key)
                        if data:
                            issue_data = {
                                (k.decode() if isinstance(k, bytes) else k):
                                (v.decode() if isinstance(v, bytes) else v)
                                for k, v in data.items()
                            }
                            # Parse optional ontology_tags
                            ontology_tags = None
                            ontology_tags_json = issue_data.get('ontology_tags', '')
                            if ontology_tags_json:
                                try:
                                    from models.ontology import OntologyTags
                                    ontology_tags = OntologyTags.model_validate_json(ontology_tags_json)
                                except Exception:
                                    pass

                            # Parse evaluation fields
                            eval_status_str = issue_data.get('evaluation_status', 'not_evaluated')
                            eval_result = None
                            eval_result_json = issue_data.get('evaluation_result', '')
                            if eval_result_json:
                                try:
                                    eval_result = IssueEvaluationResult.model_validate_json(eval_result_json)
                                except Exception:
                                    pass

                            issue = Issue(
                                issue_id=issue_data.get('issue_id', ''),
                                title=issue_data.get('title', ''),
                                description=issue_data.get('description', ''),
                                issue_type=IssueType(issue_data.get('issue_type', 'task')),
                                area=IssueArea(issue_data.get('area', 'backend')),
                                priority=IssuePriority(issue_data.get('priority', 'P2')),
                                status=IssueStatus(issue_data.get('status', 'backlog')),
                                required_skills=json.loads(issue_data.get('required_skills', '[]')),
                                required_labels=json.loads(issue_data.get('required_labels', '[]')),
                                required_tools=json.loads(issue_data.get('required_tools', '[]')),
                                depends_on=json.loads(issue_data.get('depends_on', '[]')),
                                blocks=json.loads(issue_data.get('blocks', '[]')),
                                project_id=issue_data.get('project_id') or None,
                                goal_id=issue_data.get('goal_id') or None,
                                parent_issue_id=issue_data.get('parent_issue_id') or None,
                                assigned_compute_id=issue_data.get('assigned_compute_id') or None,
                                release_id=issue_data.get('release_id') or None,
                                ontology_tags=ontology_tags,
                                evaluation_status=EvaluationStatus(eval_status_str),
                                evaluation_result=eval_result,
                                evaluation_retry_count=int(issue_data.get('evaluation_retry_count', '0')),
                            )
                            self._issues[issue.issue_id] = issue
                    except Exception as e:
                        logger.error(f"Error loading issue from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._issues)} issues from Redis")
        except Exception as e:
            logger.error(f"Error loading issues from Redis: {e}")

    async def _save_issue_to_redis(self, issue: Issue) -> None:
        """Save issue to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"issue:data:{issue.issue_id}")
            mapping = {
                'issue_id': issue.issue_id,
                'title': issue.title,
                'description': issue.description,
                'issue_type': issue.issue_type.value,
                'area': issue.area.value,
                'priority': issue.priority.value,
                'status': issue.status.value,
                'required_skills': json.dumps(issue.required_skills),
                'required_labels': json.dumps(issue.required_labels),
                'required_tools': json.dumps(issue.required_tools),
                'depends_on': json.dumps(issue.depends_on),
                'blocks': json.dumps(issue.blocks),
                'project_id': issue.project_id or '',
                'goal_id': issue.goal_id or '',
                'parent_issue_id': issue.parent_issue_id or '',
                'assigned_compute_id': issue.assigned_compute_id or '',
                'release_id': issue.release_id or '',
                'created_at': issue.created_at.isoformat(),
                'updated_at': issue.updated_at.isoformat(),
                'started_at': issue.started_at.isoformat() if issue.started_at else '',
                'completed_at': issue.completed_at.isoformat() if issue.completed_at else '',
                'ontology_tags': issue.ontology_tags.model_dump_json() if issue.ontology_tags else '',
                'evaluation_status': issue.evaluation_status.value,
                'evaluation_result': issue.evaluation_result.model_dump_json() if issue.evaluation_result else '',
                'evaluation_retry_count': str(issue.evaluation_retry_count),
            }
            await self._redis._redis.hset(key, mapping=mapping)

            # Update release index
            if issue.release_id:
                await self._redis._redis.sadd(
                    self._key(f"issue:release:{issue.release_id}"),
                    issue.issue_id
                )

            # Update status index
            await self._redis._redis.sadd(
                self._key(f"issue:status:{issue.status.value}"),
                issue.issue_id
            )

            # Update skill indexes
            for skill in issue.required_skills:
                await self._redis._redis.sadd(
                    self._key(f"issue:skill:{skill}"),
                    issue.issue_id
                )

            # Update dependency indexes
            for dep_id in issue.depends_on:
                await self._redis._redis.sadd(
                    self._key(f"issue:depends_on:{issue.issue_id}"),
                    dep_id
                )

            for blocked_id in issue.blocks:
                await self._redis._redis.sadd(
                    self._key(f"issue:blocks:{issue.issue_id}"),
                    blocked_id
                )
        except Exception as e:
            logger.error(f"Error saving issue to Redis: {e}")

    async def _delete_issue_from_redis(self, issue_id: str) -> None:
        """Delete issue from Redis."""
        if not self._redis:
            return

        try:
            issue = self._issues.get(issue_id)
            if issue:
                # Remove from status index
                await self._redis._redis.srem(
                    self._key(f"issue:status:{issue.status.value}"),
                    issue_id
                )
                # Remove from skill indexes
                for skill in issue.required_skills:
                    await self._redis._redis.srem(
                        self._key(f"issue:skill:{skill}"),
                        issue_id
                    )
                # Remove dependency indexes
                await self._redis._redis.delete(self._key(f"issue:depends_on:{issue_id}"))
                await self._redis._redis.delete(self._key(f"issue:blocks:{issue_id}"))

            await self._redis._redis.delete(self._key(f"issue:data:{issue_id}"))
        except Exception as e:
            logger.error(f"Error deleting issue from Redis: {e}")

    async def _save_issue_history_entry(
        self,
        issue_id: str,
        action: str,
        details: Optional[str] = None
    ) -> None:
        """Save a history entry for an issue."""
        if not self._redis:
            return

        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "details": details or ""
            }
            key = self._key(f"issue:history:{issue_id}")
            await self._redis._redis.lpush(key, json.dumps(entry))
            # Keep last 100 entries
            await self._redis._redis.ltrim(key, 0, 99)
        except Exception as e:
            logger.error(f"Error saving issue history: {e}")

    async def get_issue_history(self, issue_id: str) -> IssueHistory:
        """Get history of changes for an issue."""
        entries = []

        if self._redis:
            try:
                key = self._key(f"issue:history:{issue_id}")
                raw_entries = await self._redis._redis.lrange(key, 0, -1)
                for raw in raw_entries:
                    try:
                        data = json.loads(raw)
                        entries.append(IssueHistoryEntry(
                            commit=data.get("action", "unknown"),
                            author="system",
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            message=data.get("details", data.get("action", ""))
                        ))
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Error parsing history entry: {e}")
            except Exception as e:
                logger.error(f"Error loading issue history: {e}")

        return IssueHistory(issue_id=issue_id, entries=entries)

    # ============ Dependency Validation ============

    def _detect_circular_dependency(
        self,
        new_issue_id: str,
        depends_on: List[str],
        existing_issues: Optional[Dict[str, Issue]] = None
    ) -> Optional[List[str]]:
        """Detect circular dependencies before creating an issue."""
        issues = existing_issues if existing_issues is not None else self._issues

        def detect_cycle_in_deps(start_deps: List[str]) -> Optional[List[str]]:
            """Detect cycles starting from given dependencies."""
            visited = set()
            rec_stack = set()
            path = []

            def dfs(node_id: str) -> Optional[List[str]]:
                visited.add(node_id)
                rec_stack.add(node_id)
                path.append(node_id)

                node = issues.get(node_id)
                if node:
                    for dep in node.depends_on:
                        if dep not in visited:
                            result = dfs(dep)
                            if result:
                                return result
                        elif dep in rec_stack:
                            # Found cycle
                            cycle_start = path.index(dep)
                            return path[cycle_start:] + [dep]

                path.pop()
                rec_stack.remove(node_id)
                return None

            for dep in start_deps:
                if dep not in visited:
                    result = dfs(dep)
                    if result:
                        return result

            return None

        return detect_cycle_in_deps(depends_on)

    def _validate_dependencies(
        self,
        depends_on: List[str],
        existing_issues: Optional[Dict[str, Issue]] = None
    ) -> List[str]:
        """Validate that all dependencies exist."""
        issues = existing_issues if existing_issues is not None else self._issues
        missing = []
        for dep_id in depends_on:
            if dep_id not in issues:
                missing.append(dep_id)
        return missing

    # ============ Issue CRUD Operations ============

    async def create_issue(self, request: IssueCreateRequest) -> Issue:
        """Create a new issue."""
        # Validate dependencies exist
        if request.depends_on:
            # Filter out integer indices (batch references) - only validate string IDs
            string_deps = [d for d in request.depends_on if isinstance(d, str)]
            missing = self._validate_dependencies(string_deps)
            if missing:
                raise ValueError(f"Dependencies not found: {missing}")

            # Check for circular dependencies
            cycle = self._detect_circular_dependency("new_issue", string_deps)
            if cycle:
                raise ValueError(f"Circular dependency detected: {' -> '.join(cycle)}")

        issue_id = f"issue_{uuid.uuid4().hex[:12]}"

        # Determine initial status based on dependencies
        initial_status = IssueStatus.BACKLOG
        if not request.depends_on:
            initial_status = IssueStatus.READY
        else:
            # Check if all dependencies are done
            all_done = all(
                self._issues.get(dep_id) and
                self._issues[dep_id].status == IssueStatus.DONE
                for dep_id in request.depends_on
            )
            if all_done:
                initial_status = IssueStatus.READY

        issue = Issue(
            issue_id=issue_id,
            title=request.title,
            description=request.description,
            issue_type=request.issue_type,
            area=request.area,
            priority=request.priority,
            status=initial_status,
            required_skills=request.required_skills,
            required_labels=request.required_labels,
            required_tools=request.required_tools,
            depends_on=request.depends_on,
            project_id=request.project_id,
            goal_id=request.goal_id,
            parent_issue_id=request.parent_issue_id,
            release_id=request.release_id,
            ontology_tags=request.ontology_tags,
        )

        # Update blocks list on dependencies
        for dep_id in request.depends_on:
            if dep_id in self._issues:
                dep = self._issues[dep_id]
                if issue_id not in dep.blocks:
                    dep.blocks.append(issue_id)
                    await self._save_issue_to_redis(dep)

        # Update goal's issue list
        if request.goal_id and self._goal_service:
            goal = await self._goal_service.get_goal(request.goal_id)
            if goal and issue_id not in goal.issue_ids:
                goal.issue_ids.append(issue_id)
                await self._goal_service._save_goal_to_redis(goal)

        self._issues[issue_id] = issue
        await self._save_issue_to_redis(issue)
        await self._save_issue_history_entry(
            issue_id, "create", f"Created: {issue.title}"
        )

        logger.info(f"Created issue {issue_id}: {issue.title} (status: {initial_status})")
        return issue

    async def create_issues_batch(
        self,
        request: IssueBatchCreateRequest
    ) -> IssueBatchCreateResponse:
        """Create multiple issues at once (from Planner)."""
        created = []
        ready_count = 0
        backlog_count = 0

        # Inherit project_id from parent goal if available
        batch_project_id = None
        if request.goal_id and self._goal_service:
            goal = await self._goal_service.get_goal(request.goal_id)
            if goal:
                batch_project_id = goal.project_id

        # First pass: create all issues with placeholder IDs
        issue_id_map: Dict[int, str] = {}

        for idx, issue_req in enumerate(request.issues):
            issue_id = f"issue_{uuid.uuid4().hex[:12]}"
            issue_id_map[idx] = issue_id

        # Validate external dependencies and detect cycles
        batch_deps_graph: Dict[str, List[str]] = {}

        for idx, issue_req in enumerate(request.issues):
            issue_id = issue_id_map[idx]
            resolved_deps = []
            for dep in issue_req.depends_on:
                if isinstance(dep, int):
                    if dep < 0 or dep >= len(request.issues):
                        raise ValueError(f"Invalid batch index dependency: {dep}")
                    resolved_deps.append(issue_id_map[dep])
                else:
                    if dep not in self._issues:
                        raise ValueError(f"External dependency not found: {dep}")
                    resolved_deps.append(dep)
            batch_deps_graph[issue_id] = resolved_deps

        # Detect cycles
        def detect_batch_cycle() -> Optional[List[str]]:
            visited = set()
            rec_stack = set()
            cycle_path: List[str] = []

            def dfs(node_id: str) -> Optional[List[str]]:
                visited.add(node_id)
                rec_stack.add(node_id)
                cycle_path.append(node_id)

                deps = batch_deps_graph.get(node_id)
                if deps is None:
                    issue = self._issues.get(node_id)
                    deps = issue.depends_on if issue else []

                for dep in deps:
                    if dep not in visited:
                        result = dfs(dep)
                        if result:
                            return result
                    elif dep in rec_stack:
                        cycle_start = cycle_path.index(dep)
                        return cycle_path[cycle_start:] + [dep]

                cycle_path.pop()
                rec_stack.remove(node_id)
                return None

            for batch_issue_id in batch_deps_graph.keys():
                if batch_issue_id not in visited:
                    result = dfs(batch_issue_id)
                    if result:
                        return result

            return None

        cycle = detect_batch_cycle()
        if cycle:
            raise ValueError(f"Circular dependency detected: {' -> '.join(cycle)}")

        # Second pass: create issues
        for idx, issue_req in enumerate(request.issues):
            issue_id = issue_id_map[idx]

            resolved_deps = []
            for dep in issue_req.depends_on:
                if isinstance(dep, int):
                    resolved_deps.append(issue_id_map[dep])
                else:
                    resolved_deps.append(dep)

            initial_status = IssueStatus.BACKLOG
            if not resolved_deps:
                initial_status = IssueStatus.READY
                ready_count += 1
            else:
                all_done = all(
                    self._issues.get(dep_id) and
                    self._issues[dep_id].status == IssueStatus.DONE
                    for dep_id in resolved_deps
                    if dep_id not in issue_id_map.values()
                )
                if all_done and all(
                    dep_id in issue_id_map.values()
                    for dep_id in resolved_deps
                ):
                    backlog_count += 1
                elif all_done:
                    initial_status = IssueStatus.READY
                    ready_count += 1
                else:
                    backlog_count += 1

            issue = Issue(
                issue_id=issue_id,
                title=issue_req.title,
                description=issue_req.description,
                issue_type=issue_req.issue_type,
                area=issue_req.area,
                priority=issue_req.priority,
                status=initial_status,
                required_skills=issue_req.required_skills,
                depends_on=resolved_deps,
                project_id=issue_req.project_id or batch_project_id,
                goal_id=request.goal_id,
                parent_issue_id=issue_req.parent_issue_id
            )

            self._issues[issue_id] = issue
            await self._save_issue_to_redis(issue)

            created.append({"index": idx, "id": issue_id})

        # Update blocks lists
        for issue in self._issues.values():
            for dep_id in issue.depends_on:
                if dep_id in self._issues:
                    dep = self._issues[dep_id]
                    if issue.issue_id not in dep.blocks:
                        dep.blocks.append(issue.issue_id)
                        await self._save_issue_to_redis(dep)

        # Update goal
        if request.goal_id and self._goal_service:
            goal = await self._goal_service.get_goal(request.goal_id)
            if goal:
                for item in created:
                    if item["id"] not in goal.issue_ids:
                        goal.issue_ids.append(item["id"])
                goal.status = GoalStatus.IN_PROGRESS
                await self._goal_service._save_goal_to_redis(goal)

        logger.info(f"Created {len(created)} issues for goal {request.goal_id}")

        return IssueBatchCreateResponse(
            success=True,
            goal_id=request.goal_id,
            created_issues=created,
            ready_count=ready_count,
            backlog_count=backlog_count
        )

    async def get_issue(self, issue_id: str) -> Optional[Issue]:
        """Get an issue by ID."""
        return self._issues.get(issue_id)

    async def update_issue(
        self,
        issue_id: str,
        request: IssueUpdateRequest
    ) -> Optional[Issue]:
        """Update an issue."""
        issue = self._issues.get(issue_id)
        if not issue:
            return None

        if request.title is not None:
            issue.title = request.title
        if request.description is not None:
            issue.description = request.description
        if request.priority is not None:
            issue.priority = request.priority
        if request.area is not None:
            issue.area = request.area
        if request.required_skills is not None:
            issue.required_skills = request.required_skills
        if request.release_id is not None:
            # Handle release index updates
            old_release_id = issue.release_id
            issue.release_id = request.release_id if request.release_id else None
            if self._redis and old_release_id != issue.release_id:
                if old_release_id:
                    await self._redis._redis.srem(
                        self._key(f"issue:release:{old_release_id}"),
                        issue_id
                    )
        if request.ontology_tags is not None:
            issue.ontology_tags = request.ontology_tags

        issue.updated_at = datetime.now(timezone.utc)
        await self._save_issue_to_redis(issue)
        await self._save_issue_history_entry(issue_id, "update", "Issue updated")

        logger.info(f"Updated issue {issue_id}")
        return issue

    # Transitions that require a reason from the caller
    REASON_REQUIRED_TRANSITIONS = {
        (IssueStatus.DONE, IssueStatus.BACKLOG),
        (IssueStatus.FAILED, IssueStatus.BACKLOG),
    }

    # Valid status transitions — exported for frontend consumption
    VALID_TRANSITIONS = {
        IssueStatus.BACKLOG: [IssueStatus.READY],
        IssueStatus.READY: [IssueStatus.IN_PROGRESS, IssueStatus.BACKLOG],
        IssueStatus.IN_PROGRESS: [IssueStatus.BLOCKED, IssueStatus.IMPLEMENTED, IssueStatus.FAILED],
        IssueStatus.BLOCKED: [IssueStatus.IN_PROGRESS, IssueStatus.READY],
        IssueStatus.IMPLEMENTED: [IssueStatus.DONE, IssueStatus.IN_PROGRESS],
        IssueStatus.DONE: [IssueStatus.BACKLOG],
        IssueStatus.FAILED: [IssueStatus.READY, IssueStatus.IN_PROGRESS, IssueStatus.BACKLOG],
    }

    async def update_issue_status(
        self,
        issue_id: str,
        status: IssueStatus,
        compute_id: Optional[str] = None,
        trigger_cascade: bool = True,
        reason: Optional[str] = None
    ) -> Optional[Issue]:
        """Update issue status with validation.

        Args:
            issue_id: Issue to update
            status: New status
            compute_id: Compute instance performing the transition
            trigger_cascade: Whether to check/unblock dependents on DONE
            reason: Required for DONE/FAILED → BACKLOG transitions
        """
        issue = self._issues.get(issue_id)
        if not issue:
            return None

        # Validate status transitions
        if status not in self.VALID_TRANSITIONS.get(issue.status, []):
            logger.warning(f"Invalid issue status transition: {issue.status} -> {status}")
            return None

        # Require reason for certain transitions
        if (issue.status, status) in self.REASON_REQUIRED_TRANSITIONS:
            if not reason or not reason.strip():
                logger.warning(
                    f"Reason required for {issue.status} -> {status} on issue {issue_id}"
                )
                return None

        old_status = issue.status
        issue.status = status
        issue.updated_at = datetime.now(timezone.utc)

        if status == IssueStatus.IN_PROGRESS:
            if not issue.started_at:
                issue.started_at = datetime.now(timezone.utc)
            if compute_id:
                issue.assigned_compute_id = compute_id
        elif status in [IssueStatus.DONE, IssueStatus.FAILED]:
            issue.completed_at = datetime.now(timezone.utc)
        elif status == IssueStatus.BACKLOG and old_status in [IssueStatus.DONE, IssueStatus.FAILED]:
            # Reset completion state when moving back to backlog
            issue.completed_at = None
            issue.assigned_compute_id = None

            # Auto-promote to READY if all dependencies are met
            if not issue.depends_on:
                status = IssueStatus.READY
                issue.status = status
                logger.info(f"Auto-promoted issue {issue_id} to READY (no dependencies)")
            else:
                all_done = all(
                    self._issues.get(dep_id) and
                    self._issues[dep_id].status == IssueStatus.DONE
                    for dep_id in issue.depends_on
                )
                if all_done:
                    status = IssueStatus.READY
                    issue.status = status
                    logger.info(f"Auto-promoted issue {issue_id} to READY (all deps done)")

        if self._redis:
            await self._redis._redis.srem(
                self._key(f"issue:status:{old_status.value}"),
                issue_id
            )

        await self._save_issue_to_redis(issue)

        details = f"Status: {old_status.value} -> {status.value}"
        if reason:
            details += f" | Reason: {reason}"
        await self._save_issue_history_entry(issue_id, "status_change", details)

        if status == IssueStatus.DONE and trigger_cascade:
            await self._check_unblock_issue_dependents(issue_id)

        logger.info(f"Updated issue {issue_id} status: {old_status} -> {status}")
        return issue

    async def _check_unblock_issue_dependents(self, issue_id: str) -> List[str]:
        """Check if completing this issue unblocks dependents.

        When an issue completes, iterates through issues it blocks and
        moves them from BACKLOG → READY if all their dependencies are done.

        Args:
            issue_id: ID of the completed issue

        Returns:
            List of issue IDs that were unblocked
        """
        issue = self._issues.get(issue_id)
        if not issue:
            return []

        unblocked = []
        for blocked_id in issue.blocks:
            blocked = self._issues.get(blocked_id)
            if not blocked or blocked.status != IssueStatus.BACKLOG:
                continue

            all_done = all(
                self._issues.get(dep_id) and
                self._issues[dep_id].status == IssueStatus.DONE
                for dep_id in blocked.depends_on
            )

            if all_done:
                blocked.status = IssueStatus.READY
                blocked.updated_at = datetime.now(timezone.utc)
                await self._save_issue_to_redis(blocked)
                await self._save_issue_history_entry(
                    blocked_id, "cascade_unblock",
                    f"Unblocked: all dependencies satisfied (triggered by {issue_id})"
                )
                unblocked.append(blocked_id)
                logger.info(f"Issue {blocked_id} moved to READY (deps satisfied by {issue_id})")

        return unblocked

    async def complete_issue(
        self,
        issue_id: str,
        result: IssueResult,
        compute_id: Optional[str] = None,
        trigger_cascade: bool = True
    ) -> Optional[Issue]:
        """Mark an issue as implemented (code done, pending merge).

        Sets IMPLEMENTED status. The issue transitions to DONE only after
        the branch is merged to main via finalize_issue().
        """
        issue = self._issues.get(issue_id)
        if not issue:
            return None

        issue.result = result
        await self.update_issue_status(issue_id, IssueStatus.IMPLEMENTED, compute_id, trigger_cascade=False)

        return issue

    async def finalize_issue(
        self,
        issue_id: str,
        compute_id: Optional[str] = None,
        trigger_cascade: bool = True
    ) -> Optional[Issue]:
        """Mark an issue as done after merge to main.

        Transitions IMPLEMENTED → DONE, triggers dependency cascade,
        checks goal completion, and queues evaluation.
        """
        issue = self._issues.get(issue_id)
        if not issue:
            return None

        if issue.status != IssueStatus.IMPLEMENTED:
            logger.warning(
                f"Cannot finalize issue {issue_id}: status is {issue.status.value}, expected implemented"
            )
            return None

        await self.update_issue_status(issue_id, IssueStatus.DONE, compute_id, trigger_cascade=trigger_cascade)

        if issue.goal_id and self._goal_service:
            await self._goal_service.check_goal_completion(issue.goal_id)

        # Queue for post-completion evaluation (best-effort)
        try:
            from services.issue_evaluation_service import get_issue_evaluation_service
            eval_service = get_issue_evaluation_service()
            await eval_service.queue_for_evaluation(issue_id)
        except Exception as e:
            logger.debug(f"Issue evaluation service not available (optional): {e}")

        return issue

    async def delete_issue(self, issue_id: str) -> bool:
        """Delete an issue."""
        if issue_id not in self._issues:
            return False

        issue = self._issues[issue_id]

        # Remove from dependency graph
        for dep_id in issue.depends_on:
            if dep_id in self._issues:
                dep = self._issues[dep_id]
                if issue_id in dep.blocks:
                    dep.blocks.remove(issue_id)
                    await self._save_issue_to_redis(dep)

        # Remove from goal
        if issue.goal_id and self._goal_service:
            goal = await self._goal_service.get_goal(issue.goal_id)
            if goal and issue_id in goal.issue_ids:
                goal.issue_ids.remove(issue_id)
                await self._goal_service._save_goal_to_redis(goal)

        await self._delete_issue_from_redis(issue_id)
        del self._issues[issue_id]

        logger.info(f"Deleted issue {issue_id}")
        return True

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
        """List issues with optional filtering.

        Supports both legacy filters (area, priority) and ontology-based filters
        (work_type, lifecycle_stage, technical_domain) on characterized issues.
        """
        items = list(self._issues.values())

        if project_id:
            items = [i for i in items if i.project_id == project_id]
        if status:
            items = [i for i in items if i.status == status]
        if priority:
            items = [i for i in items if i.priority == priority]
        if area:
            items = [i for i in items if i.area == area]
        if goal_id:
            items = [i for i in items if i.goal_id == goal_id]
        if skill:
            items = [i for i in items if skill in i.required_skills]
        if release_id:
            # Special case: 'unscheduled' filters for issues without a release
            if release_id == 'unscheduled':
                items = [i for i in items if not i.release_id]
            else:
                items = [i for i in items if i.release_id == release_id]

        # Ontology-based filters (only apply to characterized issues)
        if work_type:
            items = [
                i for i in items
                if i.ontology_tags and i.ontology_tags.universal.work_type.value == work_type
            ]
        if lifecycle_stage:
            items = [
                i for i in items
                if i.ontology_tags and i.ontology_tags.universal.lifecycle_stage.value == lifecycle_stage
            ]
        if technical_domain:
            items = [
                i for i in items
                if i.ontology_tags and any(
                    d.value == technical_domain
                    for d in i.ontology_tags.universal.technical_domains
                )
            ]

        # Compute stats from filtered items (before pagination) so stats
        # respect project_id and other filters instead of showing global counts.
        filtered_total = len(items)
        by_status = {}
        by_priority = {}
        by_release = {}

        for i in items:
            by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
            by_priority[i.priority.value] = by_priority.get(i.priority.value, 0) + 1
            release_key = i.release_id or 'unscheduled'
            by_release[release_key] = by_release.get(release_key, 0) + 1

        items.sort(key=lambda i: i.calculate_priority_score())
        items = items[:limit]

        return IssueListResponse(
            items=items,
            total=filtered_total,
            by_status=by_status,
            by_priority=by_priority,
            by_release=by_release
        )

    async def get_ready_queue(self, limit: int = 50) -> List[Issue]:
        """Get the ready queue sorted by priority score."""
        ready_issues = [
            i for i in self._issues.values()
            if i.status == IssueStatus.READY
        ]
        ready_issues.sort(key=lambda i: i.calculate_priority_score())
        return ready_issues[:limit]

    async def get_issue_stats(self) -> IssueStats:
        """Get issue statistics."""
        all_issues = list(self._issues.values())

        by_status = {}
        by_priority = {}
        by_area = {}
        by_release = {}
        ready_count = 0
        in_progress_count = 0
        blocked_count = 0

        for i in all_issues:
            by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
            by_priority[i.priority.value] = by_priority.get(i.priority.value, 0) + 1
            by_area[i.area.value] = by_area.get(i.area.value, 0) + 1
            release_key = i.release_id or 'unscheduled'
            by_release[release_key] = by_release.get(release_key, 0) + 1

            if i.status == IssueStatus.READY:
                ready_count += 1
            elif i.status == IssueStatus.IN_PROGRESS:
                in_progress_count += 1
            elif i.status == IssueStatus.BLOCKED:
                blocked_count += 1

        return IssueStats(
            total=len(all_issues),
            by_status=by_status,
            by_priority=by_priority,
            by_area=by_area,
            by_release=by_release,
            ready_count=ready_count,
            in_progress_count=in_progress_count,
            blocked_count=blocked_count
        )

    async def assign_issue_to_compute(
        self,
        issue_id: str,
        compute_id: str,
        skills: List[str]
    ) -> Optional[Issue]:
        """Assign a ready issue to a compute instance."""
        issue = self._issues.get(issue_id)
        if not issue:
            return None

        if issue.status != IssueStatus.READY:
            logger.warning(f"Cannot assign issue {issue_id} - status is {issue.status}")
            return None

        issue.assigned_compute_id = compute_id
        await self.update_issue_status(issue_id, IssueStatus.IN_PROGRESS, compute_id)

        return issue

    async def get_next_issue_assignment(
        self,
        compute_id: str,
        compute_skills: List[str],
        compute_labels: Optional[List[str]] = None,
        compute_tools_available: Optional[List[str]] = None
    ) -> Optional[Issue]:
        """Get the next issue assignment for a compute instance."""
        ready_issues = await self.get_ready_queue()
        compute_labels = compute_labels or []
        compute_tools_available = compute_tools_available or []

        for issue in ready_issues:
            if issue.required_skills:
                has_all_skills = all(
                    skill in compute_skills
                    for skill in issue.required_skills
                )
                if not has_all_skills:
                    continue

            if issue.required_labels:
                has_all_labels = all(
                    label in compute_labels
                    for label in issue.required_labels
                )
                if not has_all_labels:
                    continue

            if issue.required_tools:
                has_all_tools = all(
                    tool in compute_tools_available
                    for tool in issue.required_tools
                )
                if not has_all_tools:
                    continue

            return await self.assign_issue_to_compute(
                issue.issue_id,
                compute_id,
                issue.required_skills
            )

        return None

    # ============ Direct Access ============

    @property
    def issues(self) -> Dict[str, Issue]:
        """Direct access to issues dictionary for WorkMapService integration."""
        return self._issues


# Global instance
_issue_ops_service: Optional[IssueOpsService] = None


def get_issue_ops_service() -> IssueOpsService:
    """Get the global issue operations service instance."""
    if _issue_ops_service is None:
        raise RuntimeError("Issue operations service not initialized")
    return _issue_ops_service


def set_issue_ops_service(service: IssueOpsService) -> None:
    """Set the global issue operations service instance."""
    global _issue_ops_service
    _issue_ops_service = service
