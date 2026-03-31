"""Reactive dispatcher — evaluates conditions on state change, dispatches when ready.

v2.0 replacement for the polling-based WorkOrchestrator.

Two conditions must both be true for dispatch to occur:
  1. Work is queued (queue has ready units)
  2. Compute is available (idle instance exists)

When EITHER condition changes, evaluate. If both true → dispatch.
No polling loops. No grace periods. No placeholders.
"""

import asyncio
import logging
from typing import Dict, List, Optional

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

    Not a loop. Not a poller. Just an evaluate() method called whenever:
    - Work enters the queue (enqueue)
    - A compute instance connects or becomes idle
    - An execution completes (frees capacity)
    - Pause/resume changes

    evaluate() checks: is there work AND is there compute AND not paused?
    If yes → dispatch. If no → do nothing, wait for next trigger.
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
        self._paused = False
        self._evaluating = False  # guard against re-entrant evaluate
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
        logger.info("Dispatcher started (reactive — no dispatch loop)")

    async def stop(self) -> None:
        """Stop the dispatcher."""
        self._running = False
        logger.info("Dispatcher stopped")

    def pause(self) -> None:
        """Pause dispatch — evaluate() will be a no-op until resumed."""
        self._paused = True
        logger.info("Dispatcher paused")

    def resume(self) -> None:
        """Resume dispatch and immediately evaluate."""
        self._paused = False
        logger.info("Dispatcher resumed")
        asyncio.create_task(self.evaluate())

    async def evaluate(self) -> None:
        """Core method: check conditions and dispatch if ready.

        Called by event handlers whenever state changes. Dispatches
        as many units as possible given current conditions.

        Conditions:
          - Not paused
          - Queue has work
          - Idle compute exists
          - Under max_concurrent limit
        """
        if not self._running or self._paused:
            return

        # Guard against re-entrant calls (evaluate triggers events that trigger evaluate)
        if self._evaluating:
            return
        self._evaluating = True

        try:
            while True:
                # Check all conditions
                if self._paused:
                    break
                if self.active_count >= self._max_concurrent:
                    break
                if self._queue.size == 0:
                    break

                # Find available compute
                compute = await self._find_idle_compute()
                if not compute:
                    break

                # Pull next unit from queue
                unit = self._queue._pop_next()
                if not unit:
                    break

                # Dispatch
                await self._dispatch_to_compute(unit, compute)

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

        Frees the instance slot, emits events, unblocks dependents,
        then evaluates for more work.
        """
        unit = self._active.pop(instance_id, None)
        if not unit:
            logger.warning(f"Completion for unknown instance: {instance_id}")
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

        # State changed — evaluate for more work
        await self.evaluate()

    async def _find_idle_compute(self):
        """Find an available compute instance. Returns connection or None."""
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()
            if not sse_manager:
                return None

            idle = sse_manager.get_idle_connections()
            if not idle:
                return None

            # TODO: project affinity — prefer connections assigned to the
            # next unit's project. For now, any idle connection works.
            return idle[0]
        except Exception as e:
            logger.debug(f"Error finding idle compute: {e}")
            return None

    async def _dispatch_to_compute(self, unit: WorkUnit, connection) -> None:
        """Send a work unit to a compute instance via SSE."""
        instance_id = connection.compute_id

        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()

            branch = f"wu/{unit.id}"
            task_data = {
                "work_unit_id": unit.id,
                "goal_id": unit.goal_ref,
                "project_id": unit.project_id,
                "description": unit.description,
                "branch": branch,
                "target_files": unit.formal_spec.target_files if unit.formal_spec else [],
                "acceptance_criteria": unit.acceptance_criteria or [],
            }
            await sse_manager.send_event(
                compute_id=instance_id,
                event_type="work_assigned",
                data=task_data,
            )
        except Exception as e:
            logger.error(f"Failed to send work to {instance_id}: {e}")
            # Return to queue
            self._queue.enqueue(unit, priority=0)
            return

        # Track
        unit.status = WorkUnitStatus.EXECUTING
        unit.assigned_instance = instance_id
        unit.branch = f"wu/{unit.id}"
        self._active[instance_id] = unit

        await self._bus.publish(ExecutionStarted(
            project_id=unit.project_id,
            work_unit_id=unit.id,
            goal_id=unit.goal_ref,
            instance_id=instance_id,
            branch=f"wu/{unit.id}",
        ))

        logger.info(f"Dispatched {unit.id} to {instance_id}")


# -- Singleton access --

_dispatcher: Optional[Dispatcher] = None


def get_dispatcher() -> Optional[Dispatcher]:
    """Get the singleton Dispatcher instance."""
    return _dispatcher


def set_dispatcher(dispatcher: Dispatcher) -> None:
    """Set the singleton Dispatcher instance."""
    global _dispatcher
    _dispatcher = dispatcher
