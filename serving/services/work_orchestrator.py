"""Work Orchestrator Service.

Background service that monitors PENDING work and orchestrates compute
spawning and assignment. This is the bridge between work creation and execution.

The orchestrator:
1. Polls for PENDING work at a configurable interval
2. Selects appropriate personas/skills for each work item
3. Spawns compute instances with those skills
4. Assigns work to the spawned compute
5. Tracks orchestration actions and handles errors gracefully
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.work_map import WorkStatus, WorkPriority, IssueStatus
from models.compute_spawner import SpawnRequest, ComputeState
from models.notification import NotificationLevel, NotificationCategory

logger = logging.getLogger(__name__)

# Error patterns that indicate deterministic failures which won't resolve on retry.
# These are configuration, permission, or environment issues that require human
# intervention rather than just retrying the same operation.
DETERMINISTIC_ERROR_PATTERNS = [
    r"dubious ownership",
    r"safe\.directory",
    r"Permission denied \(publickey\)",
    r"Host key verification failed",
    r"Could not resolve hostname",
    r"not a git repository",
    r"does not appear to be a git repository",
    r"authentication failed",
    r"Invalid username or password",
    r"command not found",
    r"No such file or directory.*claude",
    r"--dangerously-skip-permissions.*root",
]

# Compiled patterns for efficient matching
_DETERMINISTIC_RE = re.compile("|".join(DETERMINISTIC_ERROR_PATTERNS), re.IGNORECASE)


def _emit_failure_notification(
    work_id: str,
    title: str,
    error: str,
    project_id: Optional[str] = None,
) -> None:
    """Emit a notification for a work failure. No-op if notification service unavailable."""
    try:
        from services.notification_service import get_notification_service
        svc = get_notification_service()
        svc.emit(
            title=f"Work failed: {title}",
            message=error,
            level=NotificationLevel.ERROR,
            category=NotificationCategory.WORK,
            project_id=project_id,
            entity_id=work_id,
        )
    except Exception:
        logger.debug(f"Could not emit failure notification for {work_id}")


class WorkOrchestrator:
    """Background service for orchestrating work execution.

    Monitors pending work and spawns compute instances to execute it.
    Also monitors for stuck/stale work and handles timeout recovery.
    """

    def __init__(
        self,
        poll_interval: int = 10,
        max_concurrent_spawns: int = 5,
        max_retries: int = 0,
        retry_delay: int = 30,
        timeout_minutes: int = 30,
        timeout_check_interval: int = 60,
        timeout_max_retries: int = 3,
        timeout_enabled: bool = True,
        assigned_timeout_minutes: int = 3,
    ):
        """Initialize the work orchestrator.

        Args:
            poll_interval: Seconds between polling for pending work
            max_concurrent_spawns: Maximum concurrent spawn operations
            max_retries: Maximum retries for failed spawn attempts
            retry_delay: Seconds to wait before retrying failed work
            timeout_minutes: Minutes before work is considered stuck
            timeout_check_interval: Seconds between timeout checks
            timeout_max_retries: Maximum retries before marking work as FAILED
            timeout_enabled: Whether to enable stuck-work detection
            assigned_timeout_minutes: Minutes before ASSIGNED work with no
                started_at is considered orphaned and reset to PENDING
        """
        self.poll_interval = poll_interval
        self.max_concurrent_spawns = max_concurrent_spawns
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Timeout configuration
        self.timeout_minutes = timeout_minutes
        self.timeout_check_interval = timeout_check_interval
        self.timeout_max_retries = timeout_max_retries
        self.timeout_enabled = timeout_enabled
        self.assigned_timeout_minutes = assigned_timeout_minutes

        self._task: Optional[asyncio.Task] = None
        self._timeout_task: Optional[asyncio.Task] = None
        self._running = False
        self._paused = False

        # Track orchestration state
        self._active_spawns: Dict[str, datetime] = {}  # work_id -> spawn_started
        self._retry_counts: Dict[str, int] = {}  # work_id -> retry count
        self._retry_after: Dict[str, datetime] = {}  # work_id -> retry after time
        self._failed_nodes: Dict[str, set] = {}  # work_id -> set of compute_ids that failed
        self._last_errors: Dict[str, str] = {}  # work_id -> last error message

        # Skill content cache: {skill_id: (content_dict, expiry_timestamp)}
        self._skill_cache: Dict[str, tuple] = {}
        self._skill_cache_ttl = 300  # 5 minutes

        # Statistics
        self._stats = {
            "total_spawned": 0,
            "total_assigned": 0,
            "total_failed": 0,
            "total_failed_retries": 0,
            "total_timeouts": 0,
            "total_timeout_retries": 0,
            "total_resource_conflicts": 0,
            "total_circuit_breaks": 0,
            "total_assigned_recoveries": 0,
            "last_poll": None,
            "last_spawn": None,
            "last_timeout_check": None,
            "last_resource_conflict_check": None
        }

        logger.info(
            f"Initialized WorkOrchestrator "
            f"(poll_interval={poll_interval}s, "
            f"max_concurrent={max_concurrent_spawns}, "
            f"max_retries={max_retries}, "
            f"timeout={timeout_minutes}m, "
            f"timeout_enabled={timeout_enabled})"
        )

    async def start(self) -> None:
        """Start the orchestration loop."""
        if self._running:
            logger.warning("Work orchestrator already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._orchestration_loop())

        # Start timeout monitoring if enabled
        if self.timeout_enabled:
            self._timeout_task = asyncio.create_task(self._timeout_monitoring_loop())
            logger.info("Work orchestrator started (with timeout monitoring)")
        else:
            logger.info("Work orchestrator started (timeout monitoring disabled)")

    async def stop(self) -> None:
        """Stop the orchestration loop."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

        logger.info("Work orchestrator stopped")

    def pause(self) -> None:
        """Pause orchestration (stops spawning new work)."""
        self._paused = True
        logger.info("Work orchestrator paused")

    def resume(self) -> None:
        """Resume orchestration."""
        self._paused = False
        logger.info("Work orchestrator resumed")

    def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._running

    def is_paused(self) -> bool:
        """Check if orchestrator is paused."""
        return self._paused

    def get_stats(self) -> Dict:
        """Get orchestrator statistics."""
        return {
            **self._stats,
            "running": self._running,
            "paused": self._paused,
            "active_spawns": len(self._active_spawns),
            "pending_retries": len(self._retry_after),
            "timeout_monitoring_enabled": self.timeout_enabled,
            "timeout_minutes": self.timeout_minutes,
            "assigned_timeout_minutes": self.assigned_timeout_minutes
        }

    async def _orchestration_loop(self) -> None:
        """Polling fallback for orchestration.

        The primary dispatch path is event-driven via WorkDispatcher (triggered
        by compute idle events in api/compute.py). This loop runs at the
        configured poll_interval as a fallback to catch any work that slips
        through the event path (e.g., work created while no compute was idle).

        In steady state with an active WorkDispatcher, this loop runs idle most
        of the time — the dispatcher handles immediate assignment.
        """
        logger.info("Orchestration loop started (polling fallback)")

        while self._running:
            try:
                if not self._paused:
                    await self._process_pending_work()

                self._stats["last_poll"] = datetime.now(timezone.utc).isoformat()
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Orchestration loop cancelled")
                break

            except Exception as e:
                logger.error(f"Error in orchestration loop: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(self.poll_interval)

    async def _timeout_monitoring_loop(self) -> None:
        """Background loop for detecting and handling stuck work."""
        logger.info("Timeout monitoring loop started")

        while self._running:
            try:
                if not self._paused:
                    await self._detect_and_handle_stale_work()

                self._stats["last_timeout_check"] = datetime.now(timezone.utc).isoformat()
                await asyncio.sleep(self.timeout_check_interval)

            except asyncio.CancelledError:
                logger.info("Timeout monitoring loop cancelled")
                break

            except Exception as e:
                logger.error(f"Error in timeout monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.timeout_check_interval)

    async def _detect_and_handle_stale_work(self) -> None:
        """Detect stuck work and handle it.

        Checks two categories:
        1. IN_PROGRESS items with no activity beyond timeout_minutes.
        2. ASSIGNED items that were never started (started_at is None)
           beyond assigned_timeout_minutes — typically caused by SSE
           connection state races where a compute's idle reset clobbers
           a pending assignment.
        """
        from services.work_map_service import get_work_map_service

        try:
            work_map = get_work_map_service()

            # --- Recover stale ASSIGNED items ---
            stale_assigned = await work_map.get_stale_assigned_work(
                self.assigned_timeout_minutes
            )
            if stale_assigned:
                logger.info(
                    f"Found {len(stale_assigned)} stale ASSIGNED work items"
                )
            for work in stale_assigned:
                try:
                    updated = await work_map.reset_assigned_to_pending(
                        work.work_id
                    )
                    if updated:
                        self._stats["total_assigned_recoveries"] += 1
                        logger.warning(
                            f"Recovered stale ASSIGNED work {work.work_id} "
                            f"(was assigned to {work.assigned_to}, "
                            f"assigned_at={work.assigned_at})"
                        )
                except Exception as e:
                    logger.error(
                        f"Error recovering stale assigned work "
                        f"{work.work_id}: {e}"
                    )

            # --- Handle stale IN_PROGRESS items ---
            stale_work = await work_map.get_stale_work(self.timeout_minutes)

            if not stale_work and not stale_assigned:
                logger.debug("No stale work detected")
                return

            if stale_work:
                logger.info(f"Found {len(stale_work)} stale IN_PROGRESS work items")

            for work in stale_work:
                try:
                    # Handle the timeout
                    updated = await work_map.mark_work_timed_out(
                        work.work_id,
                        self.timeout_max_retries
                    )

                    if updated:
                        self._stats["total_timeouts"] += 1
                        if updated.status == WorkStatus.PENDING:
                            self._stats["total_timeout_retries"] += 1
                            logger.info(
                                f"Work {work.work_id} timed out and returned to PENDING "
                                f"(retry {updated.retry_count}/{self.timeout_max_retries})"
                            )
                        else:
                            logger.warning(
                                f"Work {work.work_id} timed out and marked as FAILED "
                                f"after {self.timeout_max_retries} retries"
                            )
                            _emit_failure_notification(
                                work_id=work.work_id,
                                title=updated.title,
                                error=updated.error or f"Timed out after {self.timeout_max_retries} retries",
                                project_id=updated.project_id,
                            )

                except Exception as e:
                    logger.error(f"Error handling stale work {work.work_id}: {e}")

        except Exception as e:
            logger.error(f"Error detecting stale work: {e}", exc_info=True)

    @staticmethod
    def _is_deterministic_error(error: Optional[str]) -> bool:
        """Check if an error message indicates a deterministic failure.

        Deterministic failures are configuration, permission, or environment
        issues that won't resolve by simply retrying the same operation on the
        same compute node. Examples: Git dubious ownership, SSH auth failures,
        missing binaries.

        Args:
            error: Error message string

        Returns:
            True if the error matches a known deterministic pattern
        """
        if not error or not isinstance(error, str):
            return False
        return bool(_DETERMINISTIC_RE.search(error))

    async def _retry_failed_work(self) -> int:
        """Retry failed work items that are eligible for re-processing.

        Scans for FAILED work items that haven't exceeded max_retries and
        returns them to PENDING with exponential backoff. This ensures that
        transient failures (e.g., git clone errors, network issues) don't
        permanently block the pipeline.

        Returns:
            Number of work items returned to PENDING for retry
        """
        from services.work_map_service import get_work_map_service

        try:
            work_map = get_work_map_service()

            # Get failed items eligible for retry
            failed_work = await work_map.get_failed_work(self.max_retries)

            if not failed_work:
                return 0

            retried = 0
            now = datetime.now(timezone.utc)

            for work in failed_work:
                # Check backoff delay using bare work_id key
                # (must match the key used in _process_pending_work and _handle_spawn_failure)
                retry_after = self._retry_after.get(work.work_id)
                if retry_after and now < retry_after:
                    continue

                # Record the compute node that failed (before mark_work_for_retry clears assigned_to)
                if work.assigned_to:
                    if work.work_id not in self._failed_nodes:
                        self._failed_nodes[work.work_id] = set()
                    self._failed_nodes[work.work_id].add(work.assigned_to)

                # Circuit-breaker: if the error is deterministic and the same
                # compute would be retried (single-node deployment or all nodes
                # already failed), skip retries and fail fast.
                error_msg = work.error or self._last_errors.get(work.work_id)
                if self._is_deterministic_error(error_msg):
                    from services.sse_connection_manager import get_sse_connection_manager
                    try:
                        sse_manager = get_sse_connection_manager()
                        total_computes = len(sse_manager.list_connections())
                    except Exception:
                        total_computes = 0

                    failed_nodes = self._failed_nodes.get(work.work_id, set())
                    # Trip circuit-breaker when: single compute, OR every
                    # available compute has already failed for this work
                    if total_computes <= 1 or (total_computes > 0 and len(failed_nodes) >= total_computes):
                        self._stats["total_circuit_breaks"] += 1
                        # Force-exhaust retries so service marks it FAILED
                        updated = await work_map.mark_work_for_retry(
                            work.work_id, 0  # max_retries=0 forces FAILED
                        )
                        logger.warning(
                            f"Circuit-breaker tripped for work {work.work_id}: "
                            f"deterministic error on {'single' if total_computes <= 1 else 'all'} "
                            f"compute(s) — skipping retries. Error: {error_msg[:200]}"
                        )
                        # Clean up tracking state
                        self._failed_nodes.pop(work.work_id, None)
                        self._retry_after.pop(work.work_id, None)
                        self._retry_counts.pop(work.work_id, None)
                        self._last_errors.pop(work.work_id, None)
                        _emit_failure_notification(
                            work_id=work.work_id,
                            title=work.title,
                            error=(
                                f"Circuit-breaker: deterministic error, retries skipped. "
                                f"{error_msg[:300]}"
                            ),
                            project_id=work.project_id,
                        )
                        continue

                # Attempt retry via service
                updated = await work_map.mark_work_for_retry(
                    work.work_id, self.max_retries
                )

                if updated and updated.status == WorkStatus.PENDING:
                    retried += 1
                    self._stats["total_failed_retries"] += 1

                    # Set backoff for next potential retry
                    delay = self.retry_delay * (2 ** (updated.retry_count - 1))
                    self._retry_after[work.work_id] = now + timedelta(seconds=delay)

                    logger.info(
                        f"Retried failed work {work.work_id} "
                        f"(attempt {updated.retry_count}/{self.max_retries}, "
                        f"backoff {delay}s, "
                        f"excluded nodes: {self._failed_nodes.get(work.work_id, set())})"
                    )
                elif updated and updated.status == WorkStatus.FAILED:
                    # Retries exhausted — clean up tracking state
                    self._failed_nodes.pop(work.work_id, None)
                    self._retry_after.pop(work.work_id, None)
                    self._last_errors.pop(work.work_id, None)
                    _emit_failure_notification(
                        work_id=work.work_id,
                        title=updated.title,
                        error=updated.error or f"Failed after {self.max_retries} retry attempts",
                        project_id=updated.project_id,
                    )

            if retried > 0:
                logger.info(f"Retried {retried} failed work items")

            return retried

        except Exception as e:
            logger.error(f"Error retrying failed work: {e}", exc_info=True)
            return 0

    async def _convert_ready_issues(self) -> int:
        """Convert ready Issues into pending WorkItems.

        Scans the issue backlog for issues in READY status and creates
        corresponding WorkItems. This bridges the gap between the backlog
        (Issues) and execution (WorkItems).

        Returns:
            Number of issues converted
        """
        from services.work_map_service import get_work_map_service

        try:
            work_map = get_work_map_service()
            ready_issues = await work_map.get_ready_queue(limit=20)

            if not ready_issues:
                return 0

            converted = 0
            for issue in ready_issues:
                try:
                    work = await work_map.create_work_from_issue(issue.issue_id)
                    if work:
                        converted += 1
                        logger.info(
                            f"Converted issue {issue.issue_id} -> work {work.work_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error converting issue {issue.issue_id} to work: {e}"
                    )

            if converted > 0:
                logger.info(f"Converted {converted} ready issues to work items")

            return converted

        except Exception as e:
            logger.error(f"Error converting ready issues: {e}", exc_info=True)
            return 0

    async def _decompose_planning_goals(self) -> int:
        """Trigger auto-decomposition for goals stuck in PLANNING status.

        Finds goals with status=PLANNING that haven't started decomposition
        yet (planning_started_at is None) and launches background
        decomposition for each.

        Returns:
            Number of goals queued for decomposition.
        """
        try:
            from services.goal_service import get_goal_service
            from models.work_map import GoalStatus

            goal_service = get_goal_service()
            result = await goal_service.list_goals(status=GoalStatus.PLANNING)

            queued = 0
            for goal in result.items:
                # Skip goals already being decomposed
                if goal.planning_started_at is not None:
                    continue

                # Skip goals without a project_id (can't decompose)
                if not goal.project_id:
                    continue

                try:
                    from api.slim_claude_code import _auto_process_background
                    import asyncio

                    asyncio.create_task(
                        _auto_process_background(goal.goal_id, None)
                    )
                    queued += 1
                    self._stats["total_decompositions_triggered"] = (
                        self._stats.get("total_decompositions_triggered", 0) + 1
                    )
                    logger.info(
                        f"Auto-triggered decomposition for goal {goal.goal_id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to trigger decomposition for goal {goal.goal_id}: {e}"
                    )

            if queued > 0:
                logger.info(f"Queued {queued} planning goals for decomposition")

            return queued

        except Exception as e:
            logger.error(f"Error checking planning goals: {e}", exc_info=True)
            return 0

    async def _process_pending_work(self) -> None:
        """Process pending work items.

        First decomposes any planning goals, converts ready Issues to
        WorkItems, then processes pending WorkItems using bucket tree
        ordering when available. Falls back to flat priority sorting
        when no bucket tree exists.
        """
        from services.work_map_service import get_work_map_service

        try:
            # Auto-decompose planning goals
            await self._decompose_planning_goals()

            # Bridge: convert ready issues to pending work items
            await self._convert_ready_issues()

            # Retry eligible failed work items (returns them to PENDING)
            await self._retry_failed_work()

            work_map = get_work_map_service()

            # Get pending work items
            result = await work_map.list_work(status=WorkStatus.PENDING, limit=50)
            pending_work = result.items

            if not pending_work:
                logger.debug("No pending work to process")
                return

            logger.info(f"Found {len(pending_work)} pending work items")

            # Filter to work that can be processed
            # First pass: cheap local checks (no I/O)
            candidates = []
            now = datetime.now(timezone.utc)

            for work in pending_work:
                # Skip if already being spawned
                if work.work_id in self._active_spawns:
                    continue

                # Skip if in retry delay
                retry_after = self._retry_after.get(work.work_id)
                if retry_after and now < retry_after:
                    continue

                # Skip if exceeded max retries (only if retries are enabled)
                retry_count = self._retry_counts.get(work.work_id, 0)
                if self.max_retries > 0 and retry_count >= self.max_retries:
                    logger.warning(
                        f"Work {work.work_id} exceeded max retries ({self.max_retries}), "
                        "requires manual intervention"
                    )
                    continue

                candidates.append(work)

            # Second pass: batch dependency check (single call instead of N)
            processable = []
            if candidates:
                candidate_ids = [w.work_id for w in candidates]
                deps_met = await work_map.get_dependencies_bulk(candidate_ids)

                for work in candidates:
                    if not deps_met.get(work.work_id, True):
                        logger.debug(f"Work {work.work_id} has unmet dependencies")
                        continue
                    processable.append(work)

            # Third pass: gate on characterization completion (#841)
            # Skip work items whose project still has pending characterizations
            ready = []
            characterizing_projects: dict[str, bool] = {}
            for work in processable:
                pid = getattr(work, 'project_id', None)
                if pid and pid not in characterizing_projects:
                    try:
                        from services.characterization_service import (
                            get_characterization_service,
                        )
                        char_svc = get_characterization_service()
                        characterizing_projects[pid] = (
                            await char_svc.has_pending_characterizations(pid)
                        )
                    except Exception:
                        characterizing_projects[pid] = False

                if pid and characterizing_projects.get(pid, False):
                    logger.debug(
                        f"Work {work.work_id} skipped: project {pid} "
                        "characterization still in progress"
                    )
                    continue
                ready.append(work)

            processable = ready

            if not processable:
                logger.debug("No processable work after filtering")
                return

            # Check for resource conflicts before assignment
            await self._check_resource_conflicts(processable)

            # Limit concurrent spawns
            available_slots = self.max_concurrent_spawns - len(self._active_spawns)
            if available_slots <= 0:
                logger.debug(f"Max concurrent spawns reached ({self.max_concurrent_spawns})")
                return

            # Order by bucket tree when available, fall back to flat priority
            ordered = await self._order_by_bucket_tree(processable)

            # Process work items
            to_process = ordered[:available_slots]
            logger.info(f"Processing {len(to_process)} work items")

            for work in to_process:
                try:
                    await self._spawn_for_work(work)
                    # After successful assignment, remove item from bucket tree
                    await self._remove_from_bucket_tree(work)
                except Exception as e:
                    logger.error(f"Error spawning for work {work.work_id}: {e}")
                    self._handle_spawn_failure(work.work_id, str(e))

        except Exception as e:
            logger.error(f"Error processing pending work: {e}", exc_info=True)

    async def _order_by_bucket_tree(self, processable: List) -> List:
        """Order processable work items using bucket tree priority.

        Groups work items by project_id, loads the bucket tree for each
        project, and uses the tree's assignment queue to determine
        execution order. Items not found in any tree are sorted by
        flat priority as a fallback.

        Args:
            processable: Filtered work items ready for assignment

        Returns:
            Work items ordered by bucket tree priority
        """
        from services.bucket_tree_store import get_bucket_tree_store

        try:
            store = get_bucket_tree_store()
        except RuntimeError:
            # Store not initialized — fall back to flat priority
            return self._sort_by_flat_priority(processable)

        # Group work items by project_id
        by_project: Dict[str, List] = {}
        for work in processable:
            by_project.setdefault(work.project_id, []).append(work)

        ordered: List = []
        flat_fallback: List = []

        for project_id, work_items in by_project.items():
            tree = await store.load(project_id)
            if not tree:
                # No bucket tree for this project — use flat priority later
                flat_fallback.extend(work_items)
                continue

            # Get assignment queue: ready items ordered by bucket rank
            # then intra-bucket priority (readiness > blocking > score)
            assignment_queue = tree.get_assignment_queue()
            queue_order = {
                item.item_id: idx
                for idx, item in enumerate(assignment_queue)
            }

            # Items found in the tree get tree ordering
            tree_ordered = []
            remaining = []
            for work in work_items:
                if work.work_id in queue_order:
                    tree_ordered.append((queue_order[work.work_id], work))
                else:
                    remaining.append(work)

            tree_ordered.sort(key=lambda t: t[0])
            ordered.extend(w for _, w in tree_ordered)

            if remaining:
                logger.debug(
                    f"Project {project_id}: {len(remaining)} items not in bucket tree, "
                    "using flat priority fallback"
                )
                flat_fallback.extend(remaining)

            if tree_ordered:
                logger.info(
                    f"Project {project_id}: ordered {len(tree_ordered)} items "
                    f"via bucket tree (version {tree.version})"
                )

        # Append flat-fallback items sorted by priority
        if flat_fallback:
            flat_fallback = self._sort_by_flat_priority(flat_fallback)
            ordered.extend(flat_fallback)

        return ordered

    async def _check_resource_conflicts(self, processable: List) -> None:
        """Check for resource conflicts between work demands and compute capacity.

        Builds resource demands from pending processable work plus currently
        in-progress work, queries SSE connections for available compute, and
        calls ConflictDetectionService.detect_resource_conflicts() when
        demand exceeds capacity. Detected conflicts are stored incrementally
        (resource conflicts only) without overwriting other conflict types.

        Args:
            processable: Filtered work items ready for assignment
        """
        from services.sse_connection_manager import get_sse_connection_manager
        from services.conflict_detection_service import get_conflict_detection_service
        from services.work_map_service import get_work_map_service

        try:
            conflict_service = get_conflict_detection_service()
        except RuntimeError:
            return  # Service not initialized

        sse_manager = get_sse_connection_manager()
        connections = sse_manager.list_connections()

        # Build available resources from all SSE connections (idle + busy)
        available_resources = [
            {"worker_id": conn.compute_id, "capabilities": conn.capabilities}
            for conn in connections
        ]

        if not available_resources:
            return  # No compute registered — nothing to compare against

        # Group processable work by project
        by_project: Dict[str, List] = {}
        for work in processable:
            by_project.setdefault(work.project_id, []).append(work)

        work_map = get_work_map_service()

        for project_id, pending_items in by_project.items():
            # Build resource demands from pending work
            resource_demands = []
            for work in pending_items:
                for cap in (work.required_capabilities or []):
                    resource_demands.append({
                        "task_id": work.work_id,
                        "capability": cap,
                        "priority": work.priority.value if hasattr(work.priority, 'value') else str(work.priority),
                    })

            # Include in-progress work as demands (consuming resources now)
            in_progress_result = await work_map.list_work(
                status=WorkStatus.IN_PROGRESS, project_id=project_id, limit=50
            )
            for work in in_progress_result.items:
                for cap in (work.required_capabilities or []):
                    resource_demands.append({
                        "task_id": work.work_id,
                        "capability": cap,
                        "priority": work.priority.value if hasattr(work.priority, 'value') else str(work.priority),
                    })

            if not resource_demands:
                continue

            # Detect resource conflicts
            reports = conflict_service.detect_resource_conflicts(
                project_id=project_id,
                resource_demands=resource_demands,
                available_resources=available_resources,
            )

            # Store results (replaces previous resource conflicts only)
            await conflict_service.store_resource_conflicts(project_id, reports)

            if reports:
                self._stats["total_resource_conflicts"] += len(reports)
                logger.info(
                    f"Detected {len(reports)} resource conflict(s) for "
                    f"project {project_id}"
                )

        self._stats["last_resource_conflict_check"] = datetime.now(timezone.utc).isoformat()

    def _sort_by_flat_priority(self, items: List) -> List:
        """Sort work items by flat priority (CRITICAL > HIGH > NORMAL > LOW).

        This is the legacy ordering used when no bucket tree is available.
        """
        priority_order = {
            WorkPriority.CRITICAL: 0,
            WorkPriority.HIGH: 1,
            WorkPriority.NORMAL: 2,
            WorkPriority.LOW: 3,
        }
        return sorted(
            items,
            key=lambda w: (priority_order.get(w.priority, 2), w.created_at),
        )

    async def _remove_from_bucket_tree(self, work) -> None:
        """Remove an assigned work item from its project's bucket tree.

        Called after successful assignment so the item is not
        re-selected on the next orchestration cycle.
        """
        from services.bucket_tree_store import get_bucket_tree_store

        try:
            store = get_bucket_tree_store()
            removed = await store.remove_item(work.project_id, work.work_id)
            if removed:
                logger.debug(
                    f"Removed work {work.work_id} from bucket tree "
                    f"for project {work.project_id}"
                )
        except RuntimeError:
            pass  # Store not initialized — no bucket tree to update
        except Exception as e:
            logger.warning(f"Error removing work from bucket tree: {e}")

    def _sync_project_repo(self, project_id: str) -> None:
        """Sync the bare repo from upstream before compute clones from it.

        For linked repos, fetches the latest state from the upstream origin
        so that compute instances clone from the most up-to-date default
        branch. This prevents spurious merge conflicts when multiple
        computes branch from the same stale HEAD.

        Internal (non-linked) repos are skipped — their bare repo IS the
        source of truth and is updated directly by merges.

        Args:
            project_id: Project/repo name
        """
        import subprocess
        from pathlib import Path
        from config import get_config
        from git.repo_manager import RepoManager

        config = get_config()
        repo_path = Path(config.git.repos_path) / f"{project_id}.git"

        if not repo_path.exists():
            logger.debug(f"Repo not found for sync: {project_id}")
            return

        # Check if this is a linked repo
        result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "claudevn.isLinked"],
            capture_output=True, text=True
        )
        if result.returncode != 0 or result.stdout.strip() != "true":
            return

        # Resolve SSH key for authenticated fetch
        ssh_key_path = None
        key_result = subprocess.run(
            ["git", "-C", str(repo_path), "config", "--get", "claudevn.sshKeyId"],
            capture_output=True, text=True
        )
        if key_result.returncode == 0 and key_result.stdout.strip():
            ssh_key_id = key_result.stdout.strip()
            try:
                from git.ssh_key_service import get_ssh_key_service
                ssh_service = get_ssh_key_service()
                private_path = ssh_service._private_key_path(ssh_key_id)
                if private_path.exists():
                    ssh_key_path = str(private_path)
            except Exception:
                pass

        logger.info(f"Pre-clone upstream sync for linked repo: {project_id}")
        try:
            repo_manager = RepoManager()
            repo_manager.pull_from_origin(project_id, ssh_key_path=ssh_key_path)
        except Exception as e:
            # Non-fatal: sync failure should not block work assignment.
            # The compute will clone whatever state the bare repo has.
            logger.warning(
                f"Pre-clone upstream sync failed for {project_id}: {e}. "
                "Proceeding with existing repo state."
            )

    async def _spawn_for_work(self, work) -> None:
        """Assign work to a compute instance.

        First attempts to find an SSE-connected compute instance and assign
        work via SSE event. Falls back to direct spawning only if no suitable
        compute is available.

        Args:
            work: WorkItem to assign
        """
        work_id = work.work_id
        logger.info(f"Assigning work {work_id}: {work.title}")

        # Sync bare repo from upstream so compute clones start from
        # the latest HEAD (prevents stale-HEAD merge conflicts).
        if work.project_id:
            self._sync_project_repo(work.project_id)

        # Mark as being processed
        self._active_spawns[work_id] = datetime.now(timezone.utc)

        try:
            # Select skills based on work requirements (sync — no HTTP calls)
            skills = self._select_skills_for_work(work)

            # Resolve model from skill preferences
            resolved_model = await self._resolve_model_for_skills(skills)

            # First, try to find an SSE-connected compute instance
            # Only exclude previously-failed nodes if multiple computes are available.
            # With a single compute, excluding it would block all work.
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()
            total_compute_count = len(sse_manager.list_connections())
            exclude_compute_ids = self._failed_nodes.get(work_id) if total_compute_count > 1 else None
            assigned_via_sse = await self._try_assign_via_sse(work, skills, exclude_compute_ids, resolved_model)

            if assigned_via_sse:
                logger.info(f"Work {work_id} assigned via SSE")
                self._stats["total_assigned"] += 1
                self._stats["last_spawn"] = datetime.now(timezone.utc).isoformat()
                # Clear orchestrator-local retry tracking on assignment.
                # NOTE: _failed_nodes is intentionally NOT cleared here —
                # if the assigned compute fails and the work retries, the
                # orchestrator needs to remember which computes already
                # failed so it can try a different one (issue #691).
                self._retry_counts.pop(work_id, None)
                self._retry_after.pop(work_id, None)
                self._last_errors.pop(work_id, None)
            else:
                # Check if SSE computes exist but are all busy
                # (reuse sse_manager from above)
                if total_compute_count > 0:
                    # Computes exist but are busy — don't fallback to spawner,
                    # don't count as failure. Work stays PENDING for next poll.
                    logger.info(
                        f"All SSE computes busy for {work_id}, will retry next poll"
                    )
                else:
                    # No SSE computes at all — fall back to direct spawning
                    logger.info(f"No SSE compute available, spawning new instance for {work_id}")
                    await self._spawn_new_compute(work, skills, resolved_model)
                    # Clear orchestrator-local retry tracking on assignment.
                    # _failed_nodes intentionally preserved (see issue #691).
                    self._retry_counts.pop(work_id, None)
                    self._retry_after.pop(work_id, None)
                    self._last_errors.pop(work_id, None)

        except Exception as e:
            logger.error(f"Failed to assign work {work_id}: {e}")
            raise

        finally:
            # Remove from active spawns
            self._active_spawns.pop(work_id, None)

    async def _try_assign_via_sse(self, work, skills: List[str], exclude_compute_ids: Optional[set] = None, model: Optional[str] = None) -> bool:
        """Try to assign work to an SSE-connected compute instance.

        Args:
            work: WorkItem to assign
            skills: Selected skills for the work
            exclude_compute_ids: Compute IDs to deprioritize (previously failed for this work)
            model: Resolved Claude model identifier for compute execution

        Returns:
            True if work was assigned via SSE, False otherwise
        """
        from services.sse_connection_manager import get_sse_connection_manager
        from services.work_map_service import get_work_map_service

        try:
            sse_manager = get_sse_connection_manager()

            # Compute specialization scores for idle connections
            specialization_scores = None
            try:
                from services.specialization_service import get_specialization_service
                spec_service = get_specialization_service()
                idle_connections = sse_manager.get_idle_connections()
                if idle_connections and work.project_id:
                    specialization_scores = {}
                    # Resolve work item cluster IDs from tags
                    work_cluster_ids = work.tags if hasattr(work, 'tags') and work.tags else []
                    work_type = None
                    for conn in idle_connections:
                        score = await spec_service.score_assignment(
                            conn.compute_id, work_cluster_ids, work_type, work.project_id
                        )
                        specialization_scores[conn.compute_id] = score
            except Exception:
                pass  # Specialization not available, fall back to default

            # Find a matching idle connection
            # WorkItem model has required_labels and required_tools fields with default empty lists
            connection = sse_manager.find_matching_connection(
                required_capabilities=work.required_capabilities if work.required_capabilities else None,
                required_labels=work.required_labels if work.required_labels else None,
                required_tools=work.required_tools if work.required_tools else None,
                idle_only=True,
                specialization_scores=specialization_scores,
                phase="work_execution",
                exclude_compute_ids=exclude_compute_ids,
            )

            if not connection:
                logger.debug(f"No idle SSE connection found for work {work.work_id}")
                return False

            # Compose skills into merged instructions
            skills_content = await self._compose_skills_for_sse(
                skills, connection.compute_id,
                work_id=work.work_id,
                task_description=work.description or "",
            )

            # Resolve repository details for linked repos
            repo_details = None
            try:
                from services.project_service import get_project_service
                project_service = get_project_service()
                repo_details = await project_service.resolve_repo_details(work.project_id)
            except Exception as e:
                logger.debug(f"Could not resolve repo details for {work.project_id}: {e}")

            # Build work context — merge stored context (has repo_url, goal_id, etc.)
            # and map repo_url → repository for compute-side consumption
            context = {
                **work.context,
                "repository": work.context.get("repo_url") or work.context.get("repository"),
                "base_branch": work.base_branch or "main",
                "relevant_files": work.context.get("relevant_files", []),
                "requirements": work.description,
            }

            # Include repo details so compute knows the correct clone URL and project name.
            # Always override repository and base_branch — compute must clone from
            # the internal serving URL, never from an external origin.
            if repo_details:
                context["git_project_name"] = repo_details["git_project_name"]
                context["clone_url"] = repo_details["clone_url"]
                context["default_branch"] = repo_details["default_branch"]
                context["repository"] = repo_details["clone_url"]
                context["base_branch"] = repo_details["default_branch"]

            # Generate a real API key for this work assignment
            from mcp.auth import generate_api_key, register_compute_key
            task_api_key = generate_api_key()
            await register_compute_key(connection.compute_id, task_api_key)

            mcp_config = {
                "server_url": "http://serving:8002",  # Internal Docker network
                "api_key": task_api_key
            }

            # Build hook-compliant branch name: {type}/{issue_id}/{compute_id}
            _type_prefix_map = {
                "feature": "f", "bug": "b", "refactor": "r",
                "docs": "d", "test": "t",
            }
            type_prefix = _type_prefix_map.get(work.work_type, "f")
            issue_or_work_id = work.issue_id or work.context.get("issue_id") or work.work_id
            branch_name = f"{type_prefix}/{issue_or_work_id}/{connection.compute_id}"

            # Send work_assigned event via SSE
            success = await sse_manager.send_work_assigned(
                compute_id=connection.compute_id,
                task_id=work.work_id,
                title=work.title,
                description=work.description,
                branch_name=branch_name,
                skills={"ids": skills, "merged_instructions": skills_content},
                context=context,
                mcp_config=mcp_config,
                model=model,
                work_type=work.work_type,
            )

            if success:
                # Update work map to mark as assigned
                work_map = get_work_map_service()
                await work_map.assign_work(
                    work_id=work.work_id,
                    compute_id=connection.compute_id,
                    skills=skills,
                    branch_name=branch_name
                )

                # Set assigned_compute_id and mark IN_PROGRESS on the parent Issue.
                # Status transitions READY → IN_PROGRESS only after successful dispatch,
                # not at work item creation time (fixes #860).
                issue_id = work.issue_id or work.context.get("issue_id")
                if issue_id:
                    await work_map.set_issue_compute_id(issue_id, connection.compute_id)
                    await work_map.update_issue_status(
                        issue_id, IssueStatus.IN_PROGRESS, connection.compute_id
                    )

                logger.info(
                    f"Work {work.work_id} assigned to SSE compute {connection.compute_id}"
                )
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to assign via SSE: {e}")
            return False

    def _get_cached_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get a skill from the in-memory cache if not expired."""
        if skill_id in self._skill_cache:
            data, expiry = self._skill_cache[skill_id]
            if time.time() < expiry:
                return data
            del self._skill_cache[skill_id]
        return None

    def _set_cached_skill(self, skill_id: str, data: Dict[str, Any]) -> None:
        """Store a skill in the in-memory cache with TTL."""
        self._skill_cache[skill_id] = (data, time.time() + self._skill_cache_ttl)

    async def _compose_skills_for_sse(
        self, skill_ids: List[str], compute_id: str,
        work_id: str = "", task_description: str = ""
    ) -> str:
        """Compose skills into merged instructions for SSE assignment.

        Uses the marketplace compose endpoint for dependency resolution,
        conflict detection, and structured CLAUDE.md generation. Falls back
        to inline skill fetching if the compose endpoint is unavailable.

        Args:
            skill_ids: List of skill IDs to compose
            compute_id: Compute instance ID
            work_id: Work item ID for compose request context
            task_description: Task description for compose request context

        Returns:
            Merged skill instructions
        """
        from services.marketplace_client import get_marketplace_client

        if not skill_ids:
            return "Execute the assigned work according to the task description."

        client = get_marketplace_client()

        # Primary path: use marketplace compose endpoint
        try:
            result = await client.compose_agent(
                task_id=work_id or compute_id,
                task_description=task_description or "Execute assigned work",
                required_capabilities=[],
                skill_ids=skill_ids,
            )

            # Log any conflict warnings from the compose response
            if result.get("conflict_warnings"):
                conflict_info = result["conflict_warnings"]
                if isinstance(conflict_info, dict):
                    if conflict_info.get("has_conflicts"):
                        logger.warning(
                            f"Skill conflicts detected for {compute_id}: "
                            f"{conflict_info.get('conflicts', [])}"
                        )
                    for warning in conflict_info.get("warnings", []):
                        logger.warning(f"Skill composition warning: {warning}")

            merged = result.get("merged_instructions", "")
            if merged:
                return merged

            logger.warning("Compose endpoint returned empty merged_instructions, using fallback")
        except Exception as e:
            logger.warning(
                f"Marketplace compose endpoint unavailable for {compute_id}: {e}. "
                f"Falling back to inline skill fetching."
            )

        # Fallback: fetch skills individually and concatenate inline
        try:
            sections = []
            for skill_id in skill_ids:
                skill = self._get_cached_skill(skill_id)
                if skill is None:
                    skill = await client.get_skill(skill_id)
                    if skill:
                        self._set_cached_skill(skill_id, skill)

                if skill:
                    sections.append(f"# {skill['name']}")
                    if skill.get('instructions'):
                        sections.append(skill['instructions'])
                    sections.append("")

            return "\n".join(sections) if sections else "Execute the assigned work."

        except Exception as e:
            logger.warning(f"Error in fallback skill composition for SSE: {e}")
            return "Execute the assigned work according to the task description."

    async def _spawn_new_compute(self, work, skills: List[str], model: Optional[str] = None) -> None:
        """Spawn a new compute instance for work (fallback when no SSE compute available).

        Args:
            work: WorkItem to assign
            skills: Selected skills for the work
            model: Resolved Claude model identifier (None = use default)
        """
        from services.compute_spawner import get_compute_spawner

        spawner = get_compute_spawner()

        # Create spawn request with labels and tools for work matching
        spawn_request = SpawnRequest(
            name=f"Worker for {work.work_id}",
            skills=skills,
            capabilities=work.required_capabilities,
            labels=work.required_labels,
            tools_available=work.required_tools,
            work_id=work.work_id,
            project_id=work.project_id,
            base_branch=work.base_branch,
            model=model,
        )

        # Spawn the compute instance
        response = await spawner.spawn(spawn_request)

        logger.info(
            f"Spawned compute {response.compute_id} for work {work.work_id} "
            f"(state: {response.state})"
        )

        # Update statistics
        self._stats["total_spawned"] += 1
        self._stats["last_spawn"] = datetime.now(timezone.utc).isoformat()

        if response.initial_work:
            self._stats["total_assigned"] += 1
            logger.info(f"Work {work.work_id} assigned to compute {response.compute_id}")

    async def _resolve_model_for_skills(self, skill_ids: List[str]) -> Optional[str]:
        """Resolve the Claude model to use based on skill preferences.

        Checks cached skill data for preferred_model hints and resolves
        conflicts using priority ordering: opus > sonnet > haiku.

        Args:
            skill_ids: Skill IDs to check for model preferences

        Returns:
            Resolved model identifier string, or None for default (Sonnet)
        """
        from models.claude_client import ClaudeModel

        MODEL_PRIORITY = {
            "opus": ClaudeModel.OPUS_4.value,
            "sonnet": ClaudeModel.SONNET_4.value,
            "haiku": ClaudeModel.HAIKU_35.value,
        }
        MODEL_RANK = {"opus": 3, "sonnet": 2, "haiku": 1}

        preferred_models = []
        for skill_id in skill_ids:
            skill = self._get_cached_skill(skill_id)
            if skill is None:
                # Fetch and cache if not present
                try:
                    from services.marketplace_client import get_marketplace_client
                    client = get_marketplace_client()
                    skill = await client.get_skill(skill_id)
                    if skill:
                        self._set_cached_skill(skill_id, skill)
                except Exception:
                    continue

            if skill and skill.get("preferred_model"):
                preferred_models.append(skill["preferred_model"].lower())

        if not preferred_models:
            return None

        # Pick highest-priority model among preferences
        best = max(preferred_models, key=lambda m: MODEL_RANK.get(m, 0))
        resolved = MODEL_PRIORITY.get(best)
        if resolved:
            logger.info(f"Model resolved to {best} ({resolved}) from skills {skill_ids}")
        return resolved

    def _select_skills_for_work(self, work) -> List[str]:
        """Select appropriate skills for a work item.

        Uses pre-resolved skill data stored on the WorkItem — no external
        HTTP calls. Skills are resolved at Issue/WorkItem creation time
        (see SkillSelectionService and WorkMapService.create_work).

        Resolution order:
        1. work.skill_ids — pre-resolved at creation time
        2. work.required_skills — explicit skill requirements from the Issue
        3. Deterministic fallback based on work_type

        Args:
            work: WorkItem to select skills for

        Returns:
            List of skill IDs to use
        """
        # 1. Pre-resolved skills (set at WorkItem creation)
        if work.skill_ids:
            return work.skill_ids

        # 2. Explicit skill requirements from the Issue
        if work.required_skills:
            return work.required_skills

        # 3. Deterministic fallback based on work type — no HTTP calls
        default_skills = {
            "feature": ["code-writer"],
            "bug": ["debugger"],
            "refactor": ["refactorer"],
            "test": ["test-automator"],
            "docs": ["doc-writer"],
            "review": ["code-reviewer"]
        }

        work_type = work.work_type.lower() if work.work_type else "feature"
        return default_skills.get(work_type, ["code-writer"])

    def _handle_spawn_failure(self, work_id: str, error: str) -> None:
        """Handle a spawn failure.

        Args:
            work_id: Work ID that failed
            error: Error message
        """
        # Track error for circuit-breaker analysis
        self._last_errors[work_id] = error

        # Increment retry count
        self._retry_counts[work_id] = self._retry_counts.get(work_id, 0) + 1
        retry_count = self._retry_counts[work_id]

        # Set retry delay (exponential backoff)
        delay = self.retry_delay * (2 ** (retry_count - 1))
        self._retry_after[work_id] = datetime.now(timezone.utc) + \
            timedelta(seconds=delay)

        self._stats["total_failed"] += 1

        deterministic = self._is_deterministic_error(error)
        logger.warning(
            f"Spawn failed for work {work_id} "
            f"(attempt {retry_count}/{self.max_retries}, "
            f"retry in {delay}s, "
            f"deterministic={deterministic}): {error}"
        )

    async def trigger_immediate(self) -> Dict:
        """Trigger an immediate orchestration cycle.

        Returns:
            Results of the orchestration cycle
        """
        logger.info("Triggering immediate orchestration cycle")

        if self._paused:
            return {"status": "paused", "message": "Orchestrator is paused"}

        try:
            await self._process_pending_work()
            return {
                "status": "completed",
                "stats": self.get_stats()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


# Global instance
_orchestrator: Optional[WorkOrchestrator] = None


def get_work_orchestrator() -> Optional[WorkOrchestrator]:
    """Get the global work orchestrator instance."""
    return _orchestrator


def set_work_orchestrator(orchestrator: WorkOrchestrator) -> None:
    """Set the global work orchestrator instance."""
    global _orchestrator
    _orchestrator = orchestrator


async def start_work_orchestration(
    poll_interval: int = 10,
    max_concurrent_spawns: int = 5,
    max_retries: int = 0,
    retry_delay: int = 30,
    timeout_minutes: int = 30,
    timeout_check_interval: int = 60,
    timeout_max_retries: int = 3,
    timeout_enabled: bool = True,
    assigned_timeout_minutes: int = 3,
) -> None:
    """Start the global work orchestrator.

    Args:
        poll_interval: Seconds between polling for pending work
        max_concurrent_spawns: Maximum concurrent spawn operations
        max_retries: Maximum retries for failed spawn attempts
        retry_delay: Seconds to wait before retrying failed work
        timeout_minutes: Minutes before work is considered stuck
        timeout_check_interval: Seconds between timeout checks
        timeout_max_retries: Maximum retries before marking work as FAILED
        timeout_enabled: Whether to enable stuck-work detection
        assigned_timeout_minutes: Minutes before ASSIGNED work with no
            started_at is considered orphaned and reset to PENDING
    """
    global _orchestrator

    if _orchestrator and _orchestrator.is_running():
        logger.warning("Work orchestrator already running")
        return

    _orchestrator = WorkOrchestrator(
        poll_interval=poll_interval,
        max_concurrent_spawns=max_concurrent_spawns,
        max_retries=max_retries,
        retry_delay=retry_delay,
        timeout_minutes=timeout_minutes,
        timeout_check_interval=timeout_check_interval,
        timeout_max_retries=timeout_max_retries,
        timeout_enabled=timeout_enabled,
        assigned_timeout_minutes=assigned_timeout_minutes,
    )

    await _orchestrator.start()


async def stop_work_orchestration() -> None:
    """Stop the global work orchestrator."""
    global _orchestrator

    if _orchestrator:
        await _orchestrator.stop()
