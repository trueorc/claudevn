"""Reconciliation manager — safety net for the event-driven dispatcher.

Runs a periodic (30–60s) check to catch cases the event-driven path misses:

  1. Stuck IN_PROGRESS items (last_heartbeat > STALE_THRESHOLD) → requeue
  2. Idle computes with no assignment for too long → re-trigger dispatch
  3. Orphaned tasks (assigned to a compute that has disconnected) → requeue
  4. Consistency check: READY items + idle computes but nothing dispatched
     → re-trigger dispatch cycle (catches dropped push events)

The reconciliation loop is the last line of defense, not the primary
mechanism. Its job is to recover from the 1-in-N case where a push event
was dropped or a compute crashed mid-task.

Design reference: GitHub issue #874, §3 Reconciliation Manager
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Module-level singleton
_reconciliation_manager: Optional["ReconciliationManager"] = None

# Threshold: compute idle for more than this without work → re-trigger dispatch
IDLE_STALE_THRESHOLD_SECONDS = 30

# Threshold: characterization/decomp task with no heartbeat → likely stuck
TASK_STALE_THRESHOLD_SECONDS = 120


def get_reconciliation_manager() -> "ReconciliationManager":
    """Get the singleton ReconciliationManager instance."""
    global _reconciliation_manager
    if _reconciliation_manager is None:
        raise RuntimeError(
            "ReconciliationManager not initialized. "
            "Call set_reconciliation_manager() first."
        )
    return _reconciliation_manager


def set_reconciliation_manager(manager: "ReconciliationManager") -> None:
    """Set the singleton ReconciliationManager instance."""
    global _reconciliation_manager
    _reconciliation_manager = manager


class ReconciliationManager:
    """Background safety net for the event-driven dispatch system.

    Runs every `check_interval` seconds and detects inconsistencies that
    the push-based event flow might have missed, then re-triggers dispatch
    or requeues stuck work items.
    """

    def __init__(self, check_interval: int = 45) -> None:
        """Initialize the reconciliation manager.

        Args:
            check_interval: Seconds between reconciliation cycles (30–60)
        """
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats: Dict[str, int] = {
            "cycles": 0,
            "stale_items_requeued": 0,
            "orphaned_items_requeued": 0,
            "idle_dispatch_triggers": 0,
            "consistency_triggers": 0,
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start the reconciliation background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._reconcile_loop(), name="reconciliation-manager"
        )
        logger.info(
            f"ReconciliationManager started (interval={self.check_interval}s)"
        )

    async def stop(self) -> None:
        """Stop the reconciliation loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ReconciliationManager stopped")

    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "running": self._running}

    # =========================================================================
    # Reconciliation Loop
    # =========================================================================

    async def _reconcile_loop(self) -> None:
        """Main reconciliation loop."""
        logger.debug("ReconciliationManager loop started")

        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                if not self._running:
                    break
                self._stats["cycles"] += 1
                await self._run_reconciliation()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconciliation error: {e}", exc_info=True)

        logger.debug("ReconciliationManager loop exited")

    async def _run_reconciliation(self) -> None:
        """Run one reconciliation cycle — detect and fix inconsistencies."""
        logger.debug("Running reconciliation cycle")

        triggered_dispatch = False

        # 1. Detect stuck IN_PROGRESS items and requeue
        requeued = await self._requeue_stuck_work()
        if requeued > 0:
            self._stats["stale_items_requeued"] += requeued
            triggered_dispatch = True

        # 2. Detect orphaned tasks (assigned to disconnected computes)
        orphaned = await self._requeue_orphaned_work()
        if orphaned > 0:
            self._stats["orphaned_items_requeued"] += orphaned
            triggered_dispatch = True

        # 3. Detect idle computes with no assignment
        idle_triggered = await self._check_idle_computes()
        if idle_triggered:
            self._stats["idle_dispatch_triggers"] += 1
            triggered_dispatch = True

        # 4. Consistency check: READY items + idle computes → trigger dispatch
        consistent = await self._consistency_check()
        if not consistent:
            self._stats["consistency_triggers"] += 1
            triggered_dispatch = True

        if triggered_dispatch:
            self._fire_dispatch()

    async def _requeue_stuck_work(self) -> int:
        """Detect IN_PROGRESS work items that have exceeded the stale threshold."""
        try:
            from services.work_map_service import get_work_map_service
            from models.work_map import WorkStatus

            work_map = get_work_map_service()

            # Use the existing stale work detection (WorkOrchestrator already tracks this,
            # but we run an independent check as a safety net)
            try:
                orchestrator_timeout = 30  # minutes — shorter than orchestrator default for safety net
                stale_work = await work_map.get_stale_work(orchestrator_timeout)
            except Exception:
                return 0

            if not stale_work:
                return 0

            requeued = 0
            for work in stale_work:
                try:
                    logger.warning(
                        f"[Reconciliation] Requeuing stuck work {work.work_id} "
                        f"(status={work.status.value}, "
                        f"assigned_to={work.assigned_to})"
                    )
                    updated = await work_map.mark_work_timed_out(
                        work.work_id, max_retries=3
                    )
                    if updated:
                        requeued += 1
                except Exception as e:
                    logger.error(
                        f"[Reconciliation] Failed to requeue work {work.work_id}: {e}"
                    )

            return requeued

        except RuntimeError:
            return 0  # Service not initialized yet
        except Exception as e:
            logger.error(f"[Reconciliation] Error checking stuck work: {e}")
            return 0

    async def _requeue_orphaned_work(self) -> int:
        """Detect work assigned to computes that are no longer connected."""
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            from services.work_map_service import get_work_map_service
            from models.work_map import WorkStatus

            sse_manager = get_sse_connection_manager()
            work_map = get_work_map_service()

            # Get set of currently connected compute IDs
            connected_ids = {c.compute_id for c in sse_manager.list_connections()}

            # Get all ASSIGNED and IN_PROGRESS work items
            requeued = 0
            for status in (WorkStatus.ASSIGNED, WorkStatus.IN_PROGRESS):
                try:
                    result = await work_map.list_work(status=status, limit=100)
                    for work in result.items:
                        if work.assigned_to and work.assigned_to not in connected_ids:
                            logger.warning(
                                f"[Reconciliation] Requeuing orphaned work {work.work_id} "
                                f"(assigned to disconnected compute {work.assigned_to})"
                            )
                            try:
                                await work_map.mark_work_timed_out(
                                    work.work_id, max_retries=3
                                )
                                requeued += 1
                            except Exception as e:
                                logger.error(
                                    f"[Reconciliation] Failed to requeue orphaned "
                                    f"work {work.work_id}: {e}"
                                )
                except Exception:
                    continue

            return requeued

        except RuntimeError:
            return 0
        except Exception as e:
            logger.error(f"[Reconciliation] Error checking orphaned work: {e}")
            return 0

    async def _check_idle_computes(self) -> bool:
        """Check for computes that have been idle longer than IDLE_STALE_THRESHOLD_SECONDS."""
        try:
            from services.sse_connection_manager import get_sse_connection_manager

            sse_manager = get_sse_connection_manager()
            idle_connections = [
                c for c in sse_manager.list_connections()
                if c.status == "idle"
            ]

            if idle_connections:
                logger.debug(
                    f"[Reconciliation] {len(idle_connections)} idle compute(s) detected — "
                    "re-triggering dispatch"
                )
                return True

            return False

        except RuntimeError:
            return False
        except Exception as e:
            logger.error(f"[Reconciliation] Error checking idle computes: {e}")
            return False

    async def _consistency_check(self) -> bool:
        """Check for READY items and idle computes with no active dispatch.

        Returns True if consistent (no action needed), False if inconsistency
        was detected and dispatch should be re-triggered.
        """
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            from services.work_map_service import get_work_map_service
            from models.work_map import WorkStatus

            sse_manager = get_sse_connection_manager()
            work_map = get_work_map_service()

            idle_count = sum(
                1 for c in sse_manager.list_connections()
                if c.status == "idle"
            )

            if idle_count == 0:
                return True  # No idle computes — nothing to fix

            # Check for PENDING work items (ready to execute)
            result = await work_map.list_work(status=WorkStatus.PENDING, limit=1)
            if result.items:
                logger.warning(
                    f"[Reconciliation] Consistency issue: {idle_count} idle compute(s) + "
                    f"pending work items — re-triggering dispatch"
                )
                return False  # Inconsistency: should have dispatched

            return True  # Consistent

        except RuntimeError:
            return True
        except Exception as e:
            logger.error(f"[Reconciliation] Consistency check error: {e}")
            return True

    def _fire_dispatch(self) -> None:
        """Fire the WorkDispatcher trigger."""
        try:
            from services.work_dispatcher import get_work_dispatcher
            dispatcher = get_work_dispatcher()
            dispatcher.trigger(reason="reconciliation")
        except RuntimeError:
            pass  # Dispatcher not initialized yet
        except Exception as e:
            logger.debug(f"[Reconciliation] Could not fire dispatch: {e}")


async def start_reconciliation_manager(check_interval: int = 45) -> ReconciliationManager:
    """Create, register, and start the ReconciliationManager singleton."""
    manager = ReconciliationManager(check_interval=check_interval)
    set_reconciliation_manager(manager)
    await manager.start()
    return manager


async def stop_reconciliation_manager() -> None:
    """Stop the ReconciliationManager singleton if running."""
    global _reconciliation_manager
    if _reconciliation_manager and _reconciliation_manager.is_running():
        await _reconciliation_manager.stop()
