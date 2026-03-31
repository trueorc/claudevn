"""Simple dispatch loop — the v2.0 replacement for WorkOrchestrator.

Pulls work units from the queue, injects context packages, and
dispatches to available Claude Code instances. Event-driven
throughout — no polling loops.

This is ~200 lines replacing ~1,800 lines of WorkOrchestrator.
"""

import asyncio
import logging
from typing import Callable, Awaitable, Dict, List, Optional

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
    """Simple dispatch loop for work unit execution.

    Replaces the v1.0 WorkOrchestrator with a straightforward loop:
    1. Wait for work in the queue (event-driven, not polling)
    2. Wait for an available instance
    3. Inject context package
    4. Dispatch and track

    No affinity scoring. No feedback aggregation. No multi-round
    coordination. Just a queue and capability routing.
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
        self._instance_available = asyncio.Event()
        self._running = False
        self._paused = False
        self._resume_signal = asyncio.Event()
        self._resume_signal.set()  # Start unpaused
        self._task: Optional[asyncio.Task] = None

    @property
    def queue(self) -> DispatchQueue:
        """Access the dispatch queue."""
        return self._queue

    @property
    def active_count(self) -> int:
        """Number of currently executing work units."""
        return len(self._active)

    @property
    def active_units(self) -> List[WorkUnit]:
        """Currently executing work units."""
        return list(self._active.values())

    @property
    def is_paused(self) -> bool:
        """Whether dispatch is paused."""
        return self._paused

    async def start(self) -> None:
        """Start the dispatch loop."""
        if self._running:
            return
        self._running = True
        self._instance_available.set()  # Start ready to dispatch
        self._task = asyncio.create_task(self._dispatch_loop())
        logger.info(f"Dispatcher started (max_concurrent={self._max_concurrent})")

    async def stop(self) -> None:
        """Stop the dispatch loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Dispatcher stopped")

    def pause(self) -> None:
        """Pause dispatch — no new work will be assigned.

        In-flight work continues to completion.
        """
        self._paused = True
        self._resume_signal.clear()
        logger.info("Dispatcher paused — no new work will be dispatched")

    def resume(self) -> None:
        """Resume dispatch — new work can be assigned again."""
        self._paused = False
        self._resume_signal.set()
        logger.info("Dispatcher resumed")

    def notify_instance_available(self, instance_id: str) -> None:
        """Signal that a compute instance is available for work."""
        self._instance_available.set()
        logger.debug(f"Instance available: {instance_id}")

    async def on_execution_complete(
        self,
        instance_id: str,
        success: bool,
        branch: Optional[str] = None,
    ) -> None:
        """Handle work unit execution completion.

        Frees the instance slot and emits the appropriate event.
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
            # Trigger verification
            await self._bus.publish(VerificationStarted(
                project_id=unit.project_id,
                work_unit_id=unit.id,
                goal_id=unit.goal_ref,
                checks=[c.type.value for c in unit.verification_criteria.automated],
            ))
            # Unblock dependents
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

        self._instance_available.set()

    async def _dispatch_loop(self) -> None:
        """Main dispatch loop — event-driven, not polling."""
        while self._running:
            try:
                # Wait if paused
                if self._paused:
                    await self._resume_signal.wait()

                # Wait until we have capacity
                while self.active_count >= self._max_concurrent:
                    self._instance_available.clear()
                    await self._instance_available.wait()

                # Wait for work
                unit = await self._queue.next_timeout(timeout=5.0)
                if unit is None:
                    continue

                # Emit queued event
                await self._bus.publish(ExecutionQueued(
                    project_id=unit.project_id,
                    work_unit_id=unit.id,
                    goal_id=unit.goal_ref,
                    queue_position=self._queue.size,
                ))

                # Dispatch to an available instance
                await self._dispatch_unit(unit)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _dispatch_unit(self, unit: WorkUnit) -> None:
        """Dispatch a work unit to an available Claude Code instance.

        Selects an idle compute instance via the SSE connection manager,
        pushes the work assignment via SSE, and tracks the execution.
        Falls back to tracking-only if no compute is available.
        """
        instance_id = None

        # Try to find an available compute instance
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()

            if sse_manager:
                # Find an idle connection assigned to this project
                idle = sse_manager.get_idle_connections()

                # Filter to connections assigned to this project via registry
                connection = None
                try:
                    from services.registry_service import get_compute_registry
                    registry = get_compute_registry()
                    for conn in idle:
                        instance = await registry.get_instance(conn.compute_id) if registry else None
                        if instance and unit.project_id in (instance.project_ids or []):
                            connection = conn
                            break
                    # Fallback: any idle connection if no project-specific one
                    if not connection and idle:
                        connection = idle[0]
                except Exception:
                    if idle:
                        connection = idle[0]

                if connection:
                    instance_id = connection.compute_id

                    # Push work assignment via SSE
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
                    logger.info(f"Dispatched {unit.id} to compute {instance_id} via SSE")
        except Exception as e:
            logger.warning(f"Could not dispatch {unit.id} to compute: {e}")

        # Fallback: track assignment even without compute
        if not instance_id:
            instance_id = f"pending-{unit.id}"
            logger.info(f"No compute available for {unit.id} — queued as pending assignment")

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
