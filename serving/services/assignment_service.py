"""Assignment Service for work assignment and status management.

Extracted from work_map_service.py to reduce service size and improve maintainability.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.work_map import (
    WorkItem, WorkStatus, WorkPriority,
    WorkAssignment, ProgressReport, Blocker, BlockerType
)
from models.observability import WorkStatusChangeEvent
from services.observability_event_bus import get_event_bus

logger = logging.getLogger(__name__)


class AssignmentService:
    """Service for managing work assignments.

    Provides:
    - Work assignment to compute instances
    - Status transitions with validation
    - Blocker management
    - Progress reporting
    - Timeout handling
    """

    def __init__(self, redis_client=None):
        """Initialize assignment service.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._work_items: Dict[str, WorkItem] = {}  # Reference set externally
        self._initialized = False

    def set_work_items_reference(self, work_items: Dict[str, WorkItem]) -> None:
        """Set reference to work items dictionary.

        Args:
            work_items: Reference to work items dictionary from WorkMapService
        """
        self._work_items = work_items

    async def initialize(self) -> None:
        """Initialize the service."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("Assignment service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}workmap:{key}"

    # ============ Event Emission ============

    async def _emit_status_change_event(
        self,
        work: WorkItem,
        old_status: WorkStatus,
        new_status: WorkStatus
    ) -> None:
        """Emit work status change event to event bus."""
        try:
            event_bus = get_event_bus()
            event = WorkStatusChangeEvent(
                event_id=f"wk_{uuid.uuid4().hex[:12]}",
                session_id=work.project_id,
                work_id=work.work_id,
                old_status=old_status.value,
                new_status=new_status.value,
                title=work.title,
                assigned_to=work.assigned_to,
                progress_percent=work.progress_percent
            )
            await event_bus.emit_event(event)
            logger.debug(f"Emitted work status change: {work.work_id} {old_status.value} -> {new_status.value}")
        except Exception as e:
            logger.error(f"Failed to emit work status change event: {e}")

    # ============ Assignment Operations ============

    async def assign_work(
        self,
        work_id: str,
        compute_id: str,
        skills: List[str],
        save_callback=None,
        branch_name: Optional[str] = None
    ) -> Optional[WorkAssignment]:
        """Assign work to a compute instance.

        Args:
            work_id: Work item ID
            compute_id: Compute instance ID
            skills: List of skill IDs to assign
            save_callback: Async callback to save work item to Redis
            branch_name: Final branch name to persist (e.g. work/{id}/{compute_id})

        Returns:
            Work assignment if successful
        """
        work = self._work_items.get(work_id)
        if not work:
            return None

        if work.status not in [WorkStatus.PENDING, WorkStatus.ASSIGNED]:
            logger.warning(f"Cannot assign work {work_id} in status {work.status}")
            return None

        # Check dependencies are completed
        for dep_id in work.depends_on:
            dep = self._work_items.get(dep_id)
            if dep and dep.status != WorkStatus.COMPLETED:
                logger.warning(f"Cannot assign work {work_id}: dependency {dep_id} not completed")
                return None

        # Update work item
        old_status = work.status
        work.status = WorkStatus.ASSIGNED
        work.assigned_to = compute_id
        work.assigned_skills = skills
        if branch_name:
            work.branch_name = branch_name
        work.assigned_at = datetime.now(timezone.utc)
        work.updated_at = datetime.now(timezone.utc)

        # Update status index
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"work:status:{old_status.value}"),
                work_id
            )

        if save_callback:
            await save_callback(work)

        # Emit status change event
        await self._emit_status_change_event(work, old_status, WorkStatus.ASSIGNED)

        # Collect dependency outputs
        dep_outputs = {}
        for dep_id in work.depends_on:
            dep = self._work_items.get(dep_id)
            if dep and dep.result:
                dep_outputs[dep_id] = dep.result

        assignment = WorkAssignment(
            work_id=work_id,
            title=work.title,
            description=work.description,
            skills=skills,
            skill_ids=work.skill_ids,
            branch_name=work.branch_name,
            base_branch=work.base_branch,
            context=work.context,
            dependencies=work.depends_on,
            dependency_outputs=dep_outputs
        )

        logger.info(f"Assigned work {work_id} to compute {compute_id} with skills {skills}")

        # Record decision trace for worker assignment
        await self._record_assignment_trace(
            work=work,
            compute_id=compute_id,
            skills=skills,
        )

        return assignment

    async def unassign_work(self, work_id: str, save_callback=None) -> bool:
        """Unassign work from a compute instance.

        Args:
            work_id: Work item ID
            save_callback: Async callback to save work item to Redis

        Returns:
            True if unassigned
        """
        work = self._work_items.get(work_id)
        if not work:
            return False

        if work.status not in [WorkStatus.ASSIGNED, WorkStatus.BLOCKED]:
            return False

        old_assignee = work.assigned_to
        old_status = work.status

        work.status = WorkStatus.PENDING
        work.assigned_to = None
        work.assigned_skills = []
        work.assigned_at = None
        work.updated_at = datetime.now(timezone.utc)

        # Update indexes
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"work:status:{old_status.value}"),
                work_id
            )
            if old_assignee:
                await self._redis._redis.srem(
                    self._key(f"work:assignee:{old_assignee}"),
                    work_id
                )
                await self._redis._redis.delete(
                    self._key(f"workmap:compute:{old_assignee}:current")
                )

        if save_callback:
            await save_callback(work)

        await self._emit_status_change_event(work, old_status, WorkStatus.PENDING)

        logger.info(f"Unassigned work {work_id}")
        return True

    async def get_compute_current_work(self, compute_id: str) -> Optional[str]:
        """Get the current work assignment for a compute instance."""
        if not self._redis:
            for work in self._work_items.values():
                if (work.assigned_to == compute_id and
                    work.status in [WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS]):
                    return work.work_id
            return None

        try:
            current = await self._redis._redis.get(
                self._key(f"workmap:compute:{compute_id}:current")
            )
            if current:
                return current.decode() if isinstance(current, bytes) else current
        except Exception as e:
            logger.error(f"Error getting compute current work: {e}")
        return None

    async def get_work_by_skill(self, skill: str) -> List[WorkItem]:
        """Get all work items requiring a specific skill."""
        if not self._redis:
            return [w for w in self._work_items.values()
                    if skill in w.required_skills]

        try:
            work_ids = await self._redis._redis.smembers(
                self._key(f"workmap:work:skill:{skill}")
            )
            result = []
            for work_id in work_ids:
                work_id_str = work_id.decode() if isinstance(work_id, bytes) else work_id
                work = self._work_items.get(work_id_str)
                if work:
                    result.append(work)
            return result
        except Exception as e:
            logger.error(f"Error getting work by skill: {e}")
            return []

    async def get_work_blockers(self, work_id: str) -> List[str]:
        """Get IDs of work items that block a given work item."""
        if not self._redis:
            work = self._work_items.get(work_id)
            return list(work.depends_on) if work else []

        try:
            deps = await self._redis._redis.smembers(
                self._key(f"workmap:work:depends_on:{work_id}")
            )
            return [d.decode() if isinstance(d, bytes) else d for d in deps]
        except Exception as e:
            logger.error(f"Error getting work blockers: {e}")
            return []

    async def get_blocked_by_work(self, work_id: str) -> List[str]:
        """Get IDs of work items that are blocked by a given work item."""
        if not self._redis:
            work = self._work_items.get(work_id)
            return list(work.blocks) if work else []

        try:
            blocked = await self._redis._redis.smembers(
                self._key(f"workmap:work:blocks:{work_id}")
            )
            return [b.decode() if isinstance(b, bytes) else b for b in blocked]
        except Exception as e:
            logger.error(f"Error getting blocked by work: {e}")
            return []

    async def get_pending_queue(self, limit: int = 50) -> List[WorkItem]:
        """Get the pending work queue sorted by priority score."""
        if not self._redis:
            pending = [w for w in self._work_items.values()
                       if w.status == WorkStatus.PENDING]
            pending.sort(key=lambda w: (
                {WorkPriority.CRITICAL: 0, WorkPriority.HIGH: 1,
                 WorkPriority.NORMAL: 2, WorkPriority.LOW: 3}.get(w.priority, 2),
                w.created_at
            ))
            return pending[:limit]

        try:
            work_ids = await self._redis._redis.zrange(
                self._key("workmap:work:pending:queue"),
                0, limit - 1
            )
            result = []
            for work_id in work_ids:
                work_id_str = work_id.decode() if isinstance(work_id, bytes) else work_id
                work = self._work_items.get(work_id_str)
                if work:
                    result.append(work)
            return result
        except Exception as e:
            logger.error(f"Error getting pending queue: {e}")
            return []

    async def get_next_assignment(
        self,
        compute_id: str,
        capabilities: List[str],
        labels: Optional[List[str]] = None,
        tools_available: Optional[List[str]] = None,
        project_ids: Optional[List[str]] = None,
        save_callback=None
    ) -> Optional[WorkAssignment]:
        """Get the next work assignment for a compute instance."""
        candidates = []
        labels = labels or []
        tools_available = tools_available or []

        # If project_ids is explicitly provided, apply project scope filtering
        # Empty list = benched (no work), None = no project filtering (legacy)
        has_project_filter = project_ids is not None
        if has_project_filter and not project_ids:
            # Benched computes (empty project_ids) get no work
            return None

        for work in self._work_items.values():
            if work.status != WorkStatus.PENDING:
                continue

            # Check project scope: compute must be tagged for the work's project
            if has_project_filter and "*" not in project_ids and work.project_id not in project_ids:
                continue

            # Check dependencies are completed
            deps_met = all(
                self._work_items.get(dep_id) and
                self._work_items[dep_id].status == WorkStatus.COMPLETED
                for dep_id in work.depends_on
            )
            if not deps_met:
                continue

            # Check capabilities match
            caps_match = all(
                cap in capabilities
                for cap in work.required_capabilities
            )
            if not caps_match:
                continue

            # Check labels match
            labels_match = all(
                label in labels
                for label in work.required_labels
            )
            if not labels_match:
                continue

            # Check tools match
            tools_match = all(
                tool in tools_available
                for tool in work.required_tools
            )
            if not tools_match:
                continue

            # Score by priority
            priority_score = {
                WorkPriority.CRITICAL: 4,
                WorkPriority.HIGH: 3,
                WorkPriority.NORMAL: 2,
                WorkPriority.LOW: 1
            }.get(work.priority, 2)

            candidates.append((priority_score, work.created_at, work))

        if not candidates:
            return None

        # Add specialization bonus if available
        try:
            from services.specialization_service import get_specialization_service
            spec_service = get_specialization_service()
            scored_candidates = []
            for priority_score, created_at, work_item in candidates:
                work_cluster_ids = work_item.tags if hasattr(work_item, 'tags') and work_item.tags else []
                spec_score = await spec_service.score_assignment(
                    compute_id, work_cluster_ids, None, work_item.project_id
                )
                # Boost priority by up to 1 point for perfect specialization match
                adjusted_score = priority_score + spec_score
                scored_candidates.append((adjusted_score, created_at, work_item))
            candidates = scored_candidates
        except Exception:
            pass  # Specialization not available

        # Add context affinity bonus (recency-weighted domain experience)
        try:
            from services.context_affinity_service import get_context_affinity_service
            affinity_service = get_context_affinity_service()
            affinity_scored = []
            for score, created_at, work_item in candidates:
                work_cluster_ids = work_item.tags if hasattr(work_item, 'tags') and work_item.tags else []
                affinity_score = affinity_service.score_affinity(compute_id, work_cluster_ids)
                adjusted_score = score + (affinity_score * 0.8)
                affinity_scored.append((adjusted_score, created_at, work_item))
            candidates = affinity_scored
        except Exception:
            pass  # Affinity service not available

        candidates.sort(key=lambda x: (-x[0], x[1]))
        work = candidates[0][2]

        return await self.assign_work(
            work_id=work.work_id,
            compute_id=compute_id,
            skills=work.required_skills,
            save_callback=save_callback
        )

    # ============ Status Operations ============

    async def update_status(
        self,
        work_id: str,
        status: WorkStatus,
        compute_id: Optional[str] = None,
        save_callback=None
    ) -> Optional[WorkItem]:
        """Update work status with validation."""
        work = self._work_items.get(work_id)
        if not work:
            return None

        # Authorization check
        if compute_id and work.assigned_to != compute_id:
            logger.warning(f"Compute {compute_id} not authorized for work {work_id}")
            return None

        # Validate status transition
        valid_transitions = {
            WorkStatus.PENDING: [WorkStatus.ASSIGNED],
            WorkStatus.ASSIGNED: [WorkStatus.IN_PROGRESS, WorkStatus.BLOCKED, WorkStatus.PENDING],
            WorkStatus.IN_PROGRESS: [WorkStatus.BLOCKED, WorkStatus.REVIEW, WorkStatus.COMPLETED, WorkStatus.FAILED],
            WorkStatus.BLOCKED: [WorkStatus.IN_PROGRESS, WorkStatus.PENDING],
            WorkStatus.REVIEW: [WorkStatus.COMPLETED, WorkStatus.IN_PROGRESS, WorkStatus.FAILED],
            WorkStatus.COMPLETED: [],
            WorkStatus.FAILED: [WorkStatus.PENDING],
        }

        if status not in valid_transitions.get(work.status, []):
            # Idempotent: same terminal state is a no-op, not an error (#829)
            if work.status == status and status in (WorkStatus.COMPLETED, WorkStatus.FAILED):
                logger.debug(f"Idempotent status transition for {work_id}: already {status.value}")
                return work
            logger.warning(f"Invalid status transition for {work_id}: {work.status} -> {status}")
            return None

        old_status = work.status
        work.status = status
        work.updated_at = datetime.now(timezone.utc)

        # Update timestamps
        if status == WorkStatus.IN_PROGRESS:
            if not work.started_at:
                work.started_at = datetime.now(timezone.utc)
            work.last_activity_at = datetime.now(timezone.utc)
        elif status in [WorkStatus.COMPLETED, WorkStatus.FAILED]:
            work.completed_at = datetime.now(timezone.utc)

        # Update status index
        if self._redis:
            await self._redis._redis.srem(
                self._key(f"work:status:{old_status.value}"),
                work_id
            )
            if status in [WorkStatus.COMPLETED, WorkStatus.FAILED] and work.assigned_to:
                await self._redis._redis.delete(
                    self._key(f"workmap:compute:{work.assigned_to}:current")
                )

        if save_callback:
            await save_callback(work)

        await self._emit_status_change_event(work, old_status, status)

        logger.info(f"Updated work {work_id} status: {old_status} -> {status}")
        return work

    async def report_progress(
        self,
        work_id: str,
        report: ProgressReport,
        save_callback=None
    ) -> Optional[WorkItem]:
        """Report progress on work."""
        work = self._work_items.get(work_id)
        if not work:
            return None

        work.progress_percent = report.progress_percent
        if report.note:
            work.progress_notes.append(f"[{datetime.now(timezone.utc).isoformat()}] {report.note}")
        work.updated_at = datetime.now(timezone.utc)
        work.last_activity_at = datetime.now(timezone.utc)

        # Handle status change if included
        if report.status != work.status:
            await self.update_status(work_id, report.status, save_callback=save_callback)

        # Handle new blockers
        for blocker_data in report.blockers:
            blocker = Blocker(
                blocker_id=f"blk_{uuid.uuid4().hex[:8]}",
                blocker_type=BlockerType(blocker_data.get('type', 'external')),
                description=blocker_data.get('description', ''),
                blocking_work_id=blocker_data.get('blocking_work_id')
            )
            work.blockers.append(blocker)

        if save_callback:
            await save_callback(work)

        logger.info(f"Progress update for {work_id}: {report.progress_percent}%")
        return work

    async def complete_work(
        self,
        work_id: str,
        result: Dict[str, Any],
        compute_id: Optional[str] = None,
        save_callback=None
    ) -> Optional[WorkItem]:
        """Mark work as completed with result."""
        work = self._work_items.get(work_id)
        if not work:
            return None

        if compute_id and work.assigned_to != compute_id:
            return None

        work.result = result
        work.progress_percent = 100
        work.updated_at = datetime.now(timezone.utc)

        await self.update_status(work_id, WorkStatus.COMPLETED, compute_id, save_callback)

        # Check if this unblocks other work
        await self._check_unblock_dependents(work_id, save_callback)

        logger.info(f"Work {work_id} completed")
        return work

    async def _check_unblock_dependents(self, work_id: str, save_callback=None) -> None:
        """Check if completing this work unblocks dependents."""
        work = self._work_items.get(work_id)
        if not work:
            return

        for blocked_id in work.blocks:
            blocked = self._work_items.get(blocked_id)
            if not blocked:
                continue

            # Resolve dependency blockers
            for blocker in blocked.blockers:
                if (blocker.blocker_type == BlockerType.DEPENDENCY and
                    blocker.blocking_work_id == work_id and
                    not blocker.is_resolved):
                    blocker.resolved_at = datetime.now(timezone.utc)
                    blocker.resolution_note = f"Dependency {work_id} completed"

            if save_callback:
                await save_callback(blocked)

    # ============ Blocker Operations ============

    async def add_blocker(
        self,
        work_id: str,
        blocker_type: BlockerType,
        description: str,
        blocking_work_id: Optional[str] = None,
        save_callback=None
    ) -> Optional[Blocker]:
        """Add a blocker to work."""
        work = self._work_items.get(work_id)
        if not work:
            return None

        blocker = Blocker(
            blocker_id=f"blk_{uuid.uuid4().hex[:8]}",
            blocker_type=blocker_type,
            description=description,
            blocking_work_id=blocking_work_id
        )

        work.blockers.append(blocker)

        # Update status if not already blocked
        if work.status != WorkStatus.BLOCKED:
            await self.update_status(work_id, WorkStatus.BLOCKED, save_callback=save_callback)
        elif save_callback:
            await save_callback(work)

        logger.info(f"Added blocker {blocker.blocker_id} to work {work_id}")
        return blocker

    async def resolve_blocker(
        self,
        work_id: str,
        blocker_id: str,
        resolution_note: Optional[str] = None,
        resolved_by: Optional[str] = None,
        save_callback=None
    ) -> bool:
        """Resolve a blocker."""
        work = self._work_items.get(work_id)
        if not work:
            return False

        for blocker in work.blockers:
            if blocker.blocker_id == blocker_id:
                blocker.resolved_at = datetime.now(timezone.utc)
                blocker.resolution_note = resolution_note
                blocker.resolved_by = resolved_by

                if save_callback:
                    await save_callback(work)

                # Check if work can be unblocked
                if not work.is_blocked and work.status == WorkStatus.BLOCKED:
                    await self.update_status(work_id, WorkStatus.IN_PROGRESS, save_callback=save_callback)

                logger.info(f"Resolved blocker {blocker_id} for work {work_id}")
                return True

        return False

    # ============ Timeout Operations ============

    async def get_stale_work(self, timeout_minutes: int) -> List[WorkItem]:
        """Get work items that have been IN_PROGRESS for too long without activity."""
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        stale_items = []

        for work in self._work_items.values():
            if work.status != WorkStatus.IN_PROGRESS:
                continue

            last_activity = work.last_activity_at or work.updated_at

            if last_activity < stale_threshold:
                stale_items.append(work)

        return stale_items

    async def get_stale_assigned_work(self, assigned_timeout_minutes: int) -> List[WorkItem]:
        """Get ASSIGNED work items that were never started by a compute.

        Detects work items stuck in ASSIGNED status — typically caused by a
        race between PR auto-merge resetting the SSE connection to idle and
        the compute's claude_code_completed event clobbering the assignment,
        or by an assigned compute failing on a different task without
        touching this work item.

        Args:
            assigned_timeout_minutes: Minutes after which an ASSIGNED item
                with no started_at is considered stale.

        Returns:
            List of stale ASSIGNED work items.
        """
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=assigned_timeout_minutes)
        stale_items = []

        for work in self._work_items.values():
            if work.status != WorkStatus.ASSIGNED:
                continue

            # Only recover items that were never started
            if work.started_at is not None:
                continue

            assigned_at = work.assigned_at or work.updated_at
            if assigned_at < stale_threshold:
                stale_items.append(work)

        return stale_items

    async def reset_assigned_to_pending(
        self,
        work_id: str,
        save_callback=None
    ) -> Optional[WorkItem]:
        """Reset a stale ASSIGNED work item back to PENDING for re-dispatch.

        Args:
            work_id: Work item ID
            save_callback: Async callback to persist the work item

        Returns:
            Updated work item, or None if not found / wrong status.
        """
        work = self._work_items.get(work_id)
        if not work:
            return None

        if work.status != WorkStatus.ASSIGNED:
            logger.warning(
                f"Cannot reset work {work_id}: expected ASSIGNED, got {work.status}"
            )
            return None

        old_assignee = work.assigned_to

        # Clean up Redis indices
        if self._redis:
            await self._redis._redis.srem(
                self._key("work:status:assigned"),
                work_id
            )
            if old_assignee:
                await self._redis._redis.srem(
                    self._key(f"work:assignee:{old_assignee}"),
                    work_id
                )
                await self._redis._redis.delete(
                    self._key(f"workmap:compute:{old_assignee}:current")
                )

        recovery_note = (
            f"[{datetime.now(timezone.utc).isoformat()}] "
            f"Stale ASSIGNED recovery: reset to PENDING "
            f"(was assigned to {old_assignee})"
        )
        work.progress_notes.append(recovery_note)

        work.status = WorkStatus.PENDING
        work.assigned_to = None
        work.assigned_skills = []
        work.assigned_at = None
        work.started_at = None
        work.last_activity_at = None
        work.updated_at = datetime.now(timezone.utc)

        if save_callback:
            await save_callback(work)

        await self._emit_status_change_event(work, WorkStatus.ASSIGNED, WorkStatus.PENDING)

        logger.info(
            f"Work {work_id} reset from ASSIGNED to PENDING "
            f"(was assigned to {old_assignee})"
        )
        return work

    async def mark_work_timed_out(
        self,
        work_id: str,
        max_retries: int,
        save_callback=None
    ) -> Optional[WorkItem]:
        """Handle work that has timed out."""
        work = self._work_items.get(work_id)
        if not work:
            return None

        work.retry_count += 1
        timeout_note = f"[{datetime.now(timezone.utc).isoformat()}] Timed out (retry {work.retry_count}/{max_retries})"
        work.progress_notes.append(timeout_note)

        old_assignee = work.assigned_to

        if work.retry_count >= max_retries:
            # Mark as failed
            work.error = f"Work timed out after {max_retries} retries"
            work.status = WorkStatus.FAILED
            work.completed_at = datetime.now(timezone.utc)
            work.updated_at = datetime.now(timezone.utc)

            if self._redis:
                await self._redis._redis.srem(
                    self._key("work:status:in_progress"),
                    work_id
                )
                if old_assignee:
                    await self._redis._redis.delete(
                        self._key(f"workmap:compute:{old_assignee}:current")
                    )

            if save_callback:
                await save_callback(work)
            logger.warning(f"Work {work_id} marked as FAILED after {max_retries} timeout retries")
        else:
            # Return to pending for retry
            if self._redis:
                await self._redis._redis.srem(
                    self._key("work:status:in_progress"),
                    work_id
                )
                if old_assignee:
                    await self._redis._redis.srem(
                        self._key(f"work:assignee:{old_assignee}"),
                        work_id
                    )
                    await self._redis._redis.delete(
                        self._key(f"workmap:compute:{old_assignee}:current")
                    )

            work.status = WorkStatus.PENDING
            work.assigned_to = None
            work.assigned_skills = []
            work.assigned_at = None
            work.started_at = None
            work.last_activity_at = None
            work.updated_at = datetime.now(timezone.utc)

            if save_callback:
                await save_callback(work)
            logger.info(f"Work {work_id} returned to PENDING after timeout (retry {work.retry_count})")

        return work

    async def get_failed_work(self, max_retries: int) -> List[WorkItem]:
        """Get FAILED work items that are eligible for retry.

        Returns items where retry_count < max_retries.

        Args:
            max_retries: Maximum retry attempts before permanent failure

        Returns:
            List of failed work items eligible for retry
        """
        return [
            w for w in self._work_items.values()
            if w.status == WorkStatus.FAILED and w.retry_count < max_retries
        ]

    async def mark_work_for_retry(
        self,
        work_id: str,
        max_retries: int,
        save_callback=None
    ) -> Optional[WorkItem]:
        """Return a FAILED work item to PENDING for retry.

        Increments retry_count and resets assignment fields.
        If retry_count >= max_retries, leaves item as FAILED.

        Args:
            work_id: Work item to retry
            max_retries: Maximum retry attempts
            save_callback: Async callback to save work item to Redis

        Returns:
            Updated WorkItem, or None if not found/not eligible
        """
        work = self._work_items.get(work_id)
        if not work:
            return None

        if work.status != WorkStatus.FAILED:
            logger.warning(f"Cannot retry work {work_id}: status is {work.status}, expected FAILED")
            return None

        work.retry_count += 1
        retry_note = f"[{datetime.now(timezone.utc).isoformat()}] Retrying after failure (attempt {work.retry_count}/{max_retries})"
        work.progress_notes.append(retry_note)

        if work.retry_count >= max_retries:
            # Exhausted retries — leave as FAILED
            work.error = f"Work failed after {max_retries} retry attempts"
            work.updated_at = datetime.now(timezone.utc)

            if save_callback:
                await save_callback(work)
            logger.warning(f"Work {work_id} exhausted {max_retries} retries, staying FAILED")
            return work

        old_assignee = work.assigned_to

        # Return to PENDING for retry
        if self._redis:
            await self._redis._redis.srem(
                self._key("work:status:failed"),
                work_id
            )
            if old_assignee:
                await self._redis._redis.srem(
                    self._key(f"work:assignee:{old_assignee}"),
                    work_id
                )
                await self._redis._redis.delete(
                    self._key(f"workmap:compute:{old_assignee}:current")
                )

        work.status = WorkStatus.PENDING
        work.error = None
        work.assigned_to = None
        work.assigned_skills = []
        work.assigned_at = None
        work.started_at = None
        work.completed_at = None
        work.last_activity_at = None
        work.updated_at = datetime.now(timezone.utc)

        if save_callback:
            await save_callback(work)

        await self._emit_status_change_event(work, WorkStatus.FAILED, WorkStatus.PENDING)

        logger.info(f"Work {work_id} returned to PENDING for retry (attempt {work.retry_count}/{max_retries})")
        return work

    # =========================================================================
    # Decision Traceability
    # =========================================================================

    async def _record_assignment_trace(
        self,
        work,
        compute_id: str,
        skills: List[str],
    ) -> None:
        """Record a decision trace for a worker assignment.

        Non-critical — failures are logged but do not interrupt assignment.
        """
        try:
            from services.decision_trace_service import get_decision_trace_service
            from models.decision_trace import (
                DecisionContext,
                DecisionImpact,
                DecisionPointType,
                DecisionTrigger,
            )

            service = get_decision_trace_service()
            await service.record(
                project_id=work.project_id if hasattr(work, 'project_id') else "unknown",
                decision_type=DecisionPointType.WORKER_ASSIGNMENT,
                trigger=DecisionTrigger(
                    trigger_type="assignment",
                    source_id=compute_id,
                    source_type="compute_instance",
                    description=f"Assigning work '{work.title}' to compute {compute_id}",
                ),
                decision_summary=(
                    f"Assigned '{work.title}' ({work.work_id}) to worker {compute_id} "
                    f"with skills: {', '.join(skills)}"
                ),
                key_factors=[
                    f"Skills required: {', '.join(skills)}",
                    f"Dependencies met: {len(work.depends_on)} dependency(ies) satisfied",
                ],
                impact=DecisionImpact(
                    affected_item_ids=[work.work_id],
                ),
            )
        except Exception as e:
            logger.debug(f"Could not record assignment trace: {e}")


# Global instance
_assignment_service: Optional[AssignmentService] = None


def get_assignment_service() -> AssignmentService:
    """Get the global assignment service instance."""
    if _assignment_service is None:
        raise RuntimeError("Assignment service not initialized")
    return _assignment_service


def set_assignment_service(service: AssignmentService) -> None:
    """Set the global assignment service instance."""
    global _assignment_service
    _assignment_service = service
