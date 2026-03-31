"""Reactive dispatcher — evaluates conditions on state change, dispatches when ready.

v2.0 replacement for the polling-based WorkOrchestrator.

Two conditions must both be true for dispatch to occur:
  1. Work is queued (queue has ready units with deps satisfied)
  2. Compute is available (idle instance exists with capacity)

When EITHER condition changes, evaluate. If both true → dispatch.
No polling loops. No grace periods. No placeholders.

Dispatches one unit at a time per compute. Respects chain ordering —
within a dependency chain, units execute sequentially. Independent
chains can run on separate computes in parallel.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set

from models.work_unit import WorkUnit, WorkUnitStatus
from services.events.event_bus import EventBus, get_event_bus
from services.events.event_types import (
    ExecutionQueued,
    ExecutionStarted,
    ExecutionCompleted,
    ExecutionFailed,
    VerificationStarted,
)
from .queue import DispatchQueue

logger = logging.getLogger(__name__)


class Dispatcher:
    """Reactive dispatcher — evaluates and dispatches on state changes.

    evaluate() checks: is there work AND is there compute AND not paused?
    If yes → dispatch ONE unit to ONE compute. Then re-evaluate.
    """

    def __init__(
        self,
        queue: Optional[DispatchQueue] = None,
        bus: Optional[EventBus] = None,
        max_concurrent: int = 5,
    ):
        self._queue = queue or DispatchQueue()
        self._bus = bus or get_event_bus()
        self._max_concurrent = max_concurrent
        self._active: Dict[str, WorkUnit] = {}  # instance_id -> work unit
        self._busy_computes: Set[str] = set()   # compute_ids currently executing
        self._paused = False
        self._evaluating = False
        self._running = False

        logger.info(f"Dispatcher initialized (max_concurrent={max_concurrent})")

    @property
    def queue(self) -> DispatchQueue:
        return self._queue

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def active_units(self) -> List[WorkUnit]:
        return list(self._active.values())

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def start(self) -> None:
        """Mark the dispatcher as running. No loop to start."""
        self._running = True
        logger.info("Dispatcher started (reactive)")

    async def stop(self) -> None:
        self._running = False
        logger.info("Dispatcher stopped")

    def pause(self) -> None:
        self._paused = True
        logger.info("Dispatcher paused")

    def resume(self) -> None:
        self._paused = False
        logger.info("Dispatcher resumed")
        asyncio.create_task(self.evaluate())

    async def evaluate(self) -> None:
        """Core: check conditions and dispatch if ready.

        Called whenever state changes. Dispatches at most ONE unit
        per idle compute, then re-evaluates. This ensures we never
        overwhelm a compute with multiple assignments.
        """
        if not self._running or self._paused:
            return
        if self._evaluating:
            return
        self._evaluating = True

        try:
            dispatched_any = True
            while dispatched_any:
                dispatched_any = False

                if self._paused or self.active_count >= self._max_concurrent:
                    break
                if self._queue.size == 0:
                    break

                # Find an idle compute that is NOT already busy
                compute = await self._find_available_compute()
                if not compute:
                    break

                # Pull next unit from queue
                unit = self._queue._pop_next()
                if not unit:
                    break

                # Dispatch ONE unit to this compute
                success = await self._dispatch_to_compute(unit, compute)
                if success:
                    dispatched_any = True
                    # Mark this compute as busy so we don't send it more work
                    self._busy_computes.add(compute.compute_id)
                else:
                    # Failed to dispatch — return to queue
                    self._queue.enqueue(unit, priority=0)

        except Exception as e:
            logger.error(f"Error during dispatch evaluation: {e}", exc_info=True)
        finally:
            self._evaluating = False

    async def on_execution_complete(
        self,
        instance_id: str,
        success: bool,
        branch: Optional[str] = None,
    ) -> None:
        """Handle work unit execution completion.

        Frees the compute slot, emits events, unblocks dependents,
        then re-evaluates for more work.
        """
        unit = self._active.pop(instance_id, None)
        self._busy_computes.discard(instance_id)

        if not unit:
            logger.warning(f"Completion for unknown instance: {instance_id}")
            # Still evaluate — the compute is now free
            await self.evaluate()
            return

        if success:
            unit.status = WorkUnitStatus.SUBMITTED
            unit.branch = branch
            await self._bus.publish(ExecutionCompleted(
                project_id=unit.project_id,
                work_unit_id=unit.id,
                goal_id=unit.goal_ref,
                instance_id=instance_id,
                branch=branch or "",
            ))
            await self._bus.publish(VerificationStarted(
                project_id=unit.project_id,
                work_unit_id=unit.id,
                goal_id=unit.goal_ref,
                checks=[c.type.value for c in unit.verification_criteria.automated],
            ))
            unblocked = self._queue.mark_completed(unit.id)
            if unblocked:
                logger.info(f"Unblocked {len(unblocked)} dependents after {unit.id} completed")
        else:
            unit.status = WorkUnitStatus.FAILED_VERIFICATION
            await self._bus.publish(ExecutionFailed(
                project_id=unit.project_id,
                work_unit_id=unit.id,
                goal_id=unit.goal_ref,
                instance_id=instance_id,
                reason="Execution failed",
            ))

        logger.info(f"Execution complete: {unit.id} on {instance_id} (success={success})")

        # State changed — re-evaluate
        await self.evaluate()

    async def on_execution_rejected(
        self,
        instance_id: str,
        work_unit_id: str,
        reason: str = "",
    ) -> None:
        """Handle work unit rejection by compute (at capacity, etc).

        Returns the unit to the queue and marks the compute as busy.
        """
        unit = self._active.pop(instance_id, None)
        # Compute is busy (that's why it rejected) — keep in busy set
        self._busy_computes.add(instance_id)

        if unit:
            unit.status = WorkUnitStatus.QUEUED
            self._queue.enqueue(unit, priority=0)
            logger.info(f"Work {unit.id} rejected by {instance_id} ({reason}) — returned to queue")
        else:
            logger.warning(f"Rejection for unknown work on {instance_id}: {work_unit_id}")

    async def _get_project_repo_url(self, project_id: str) -> Optional[str]:
        """Look up the primary repository URL for a project."""
        try:
            from services.project_service import get_project_service
            ps = get_project_service()
            project = await ps.get_project(project_id)
            if project and project.repos:
                # Use primary repo or first repo
                primary = next(
                    (r for r in project.repos if r.repo_id == project.primary_repo_id),
                    project.repos[0]
                )
                # Externalize URL for compute access
                from git.url_utils import externalize_url
                return externalize_url(primary.url)
        except Exception as e:
            logger.warning(f"Could not look up repo URL for {project_id}: {e}")
        return None

    async def _find_available_compute(self):
        """Find an idle compute that is NOT already busy with our work."""
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()
            if not sse_manager:
                return None

            idle = sse_manager.get_idle_connections()
            if not idle:
                return None

            # Filter out computes we've already assigned work to
            for conn in idle:
                if conn.compute_id not in self._busy_computes:
                    return conn

            return None
        except Exception as e:
            logger.debug(f"Error finding available compute: {e}")
            return None

    async def _dispatch_to_compute(self, unit: WorkUnit, connection) -> bool:
        """Send a work unit to a compute instance via SSE. Returns True on success."""
        instance_id = connection.compute_id

        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()

            # Branch name follows git hook convention: {type}/{identifier}/{compute-id}
            # e.g., f/work_59f333e41fed/test11-compute_node_vitest_eslint
            unit_short = unit.id.replace("wu-", "")
            branch = f"f/work_{unit_short}/{instance_id}"

            # Look up the project's repo URL for git integration
            repo_url = await self._get_project_repo_url(unit.project_id)

            # Determine base branch: if this unit depends on another,
            # branch from the predecessor's branch so we build on their work.
            # This is how chain continuity works — Unit B sees Unit A's code.
            base_branch = "main"
            if unit.independence.depends_on:
                # Use the most recently completed dependency's branch
                for dep_id in reversed(unit.independence.depends_on):
                    if dep_id in self._queue._completed_ids:
                        dep_short = dep_id.replace("wu-", "")
                        base_branch = f"f/work_{dep_short}/{instance_id}"
                        break

            task_data = {
                # v1.0 compute compatibility
                "task_id": unit.id,
                "title": unit.description[:120],
                "description": unit.description,
                "branch_name": branch,
                "context": {
                    "repository": repo_url or "",
                    "repo_url": repo_url or "",
                    "base_branch": base_branch,
                    "branch": branch,
                    "target_files": unit.formal_spec.target_files if unit.formal_spec else [],
                    "acceptance_criteria": unit.acceptance_criteria or [],
                    "interface_produces": unit.interface_produces or [],
                    "interface_consumes": unit.interface_consumes or [],
                },
                # v2.0 fields
                "work_unit_id": unit.id,
                "goal_id": unit.goal_ref,
                "project_id": unit.project_id,
            }
            await sse_manager.send_event(
                compute_id=instance_id,
                event_type="work_assigned",
                data=task_data,
            )
        except Exception as e:
            logger.error(f"Failed to send work to {instance_id}: {e}")
            return False

        # Track
        unit.status = WorkUnitStatus.EXECUTING
        unit.assigned_instance = instance_id
        unit.branch = branch
        self._active[instance_id] = unit

        await self._bus.publish(ExecutionStarted(
            project_id=unit.project_id,
            work_unit_id=unit.id,
            goal_id=unit.goal_ref,
            instance_id=instance_id,
            branch=branch,
        ))

        logger.info(f"Dispatched {unit.id} to {instance_id} (branch={branch})")
        return True


# -- Singleton access --

_dispatcher: Optional[Dispatcher] = None


def get_dispatcher() -> Optional[Dispatcher]:
    return _dispatcher


def set_dispatcher(dispatcher: Dispatcher) -> None:
    global _dispatcher
    _dispatcher = dispatcher
