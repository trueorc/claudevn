"""Priority dispatch queue for work units.

Simple priority queue that orders work units by dependency DAG
topological order. No affinity scoring, no skill matching beyond
basic capability, no multi-round orchestration.

This is a priority queue with capability routing, not an orchestration engine.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from models.work_unit import WorkUnit, WorkUnitStatus

logger = logging.getLogger(__name__)


@dataclass
class QueueEntry:
    """An entry in the dispatch queue."""
    work_unit: WorkUnit
    priority: int = 0  # Lower = higher priority (topological order)
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DispatchQueue:
    """Priority queue for work unit dispatch.

    Work units enter the queue when their dependencies are satisfied
    (status transitions to READY). The queue is ordered by topological
    position in the dependency DAG — upstream units dispatch first.

    Event-driven: the queue signals when work is available.
    """

    def __init__(self):
        self._queue: List[QueueEntry] = []
        self._work_available = asyncio.Event()
        self._completed_ids: Set[str] = set()
        self._pending_ids: Set[str] = set()
        # Store pending units so we can re-enqueue when deps are met
        self._pending_units: Dict[str, Tuple[WorkUnit, int]] = {}

    def enqueue(self, unit: WorkUnit, priority: int = 0) -> None:
        """Add a work unit to the dispatch queue.

        Only enqueues if all dependencies are satisfied. Otherwise,
        tracks it as pending until dependencies complete.
        """
        unmet = [
            dep for dep in unit.independence.depends_on
            if dep not in self._completed_ids
        ]

        if unmet:
            self._pending_ids.add(unit.id)
            self._pending_units[unit.id] = (unit, priority)
            logger.debug(
                f"Work unit {unit.id} waiting on dependencies: {unmet}"
            )
            return

        entry = QueueEntry(work_unit=unit, priority=priority)
        self._queue.append(entry)
        self._queue.sort(key=lambda e: e.priority)
        unit.status = WorkUnitStatus.QUEUED

        # Remove from pending if it was there
        self._pending_ids.discard(unit.id)
        self._pending_units.pop(unit.id, None)

        self._work_available.set()
        logger.info(f"Work unit {unit.id} queued at priority {priority}")

    def enqueue_batch(self, units: List[WorkUnit]) -> None:
        """Enqueue multiple work units, respecting dependency order.

        Computes topological order and enqueues each unit at the
        correct priority. Units with unmet dependencies are deferred.
        """
        order = self._topological_sort(units)
        for priority, unit in enumerate(order):
            self.enqueue(unit, priority=priority)

    def mark_completed(self, unit_id: str) -> List[WorkUnit]:
        """Mark a work unit as completed and unblock dependents.

        Checks all pending units to see if their dependencies are now
        satisfied and re-enqueues them.

        Returns:
            List of newly unblocked work units that were added to the queue.
        """
        self._completed_ids.add(unit_id)
        unblocked = []

        # Check if any pending units are now unblocked
        still_pending = {}
        for pid, (unit, priority) in self._pending_units.items():
            unmet = [
                dep for dep in unit.independence.depends_on
                if dep not in self._completed_ids
            ]
            if not unmet:
                # All deps satisfied — enqueue
                entry = QueueEntry(work_unit=unit, priority=priority)
                self._queue.append(entry)
                unit.status = WorkUnitStatus.QUEUED
                unblocked.append(unit)
                self._pending_ids.discard(pid)
                logger.info(f"Work unit {pid} unblocked by {unit_id}, queued at priority {priority}")
            else:
                still_pending[pid] = (unit, priority)

        self._pending_units = still_pending
        self._pending_ids = set(still_pending.keys())

        if unblocked:
            self._queue.sort(key=lambda e: e.priority)
            self._work_available.set()

        return unblocked

    def _pop_next(self) -> Optional[WorkUnit]:
        """Non-blocking pop of the next work unit. Returns None if queue is empty.

        Used by the reactive dispatcher's evaluate() method.
        Does NOT change status — the dispatcher handles that.
        """
        if not self._queue:
            return None
        entry = self._queue.pop(0)
        if not self._queue:
            self._work_available.clear()
        logger.info(f"Dispatching work unit {entry.work_unit.id}")
        return entry.work_unit

    async def next(self) -> WorkUnit:
        """Wait for and return the next work unit to dispatch.

        Blocks until a work unit is available.
        """
        while True:
            if self._queue:
                entry = self._queue.pop(0)
                entry.work_unit.status = WorkUnitStatus.EXECUTING
                logger.info(f"Dispatching work unit {entry.work_unit.id}")
                if not self._queue:
                    self._work_available.clear()
                return entry.work_unit

            self._work_available.clear()
            await self._work_available.wait()

    async def next_timeout(self, timeout: float) -> Optional[WorkUnit]:
        """Wait for the next work unit with a timeout."""
        try:
            return await asyncio.wait_for(self.next(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    @property
    def size(self) -> int:
        """Number of units currently in the queue (ready to dispatch)."""
        return len(self._queue)

    @property
    def pending_count(self) -> int:
        """Number of units waiting for dependencies."""
        return len(self._pending_ids)

    @property
    def queued_items(self) -> List[WorkUnit]:
        """Work units currently in the queue."""
        return [e.work_unit for e in self._queue]

    @property
    def completed_ids(self) -> Set[str]:
        """IDs of completed work units."""
        return set(self._completed_ids)

    def _topological_sort(self, units: List[WorkUnit]) -> List[WorkUnit]:
        """Sort work units by dependency order (Kahn's algorithm)."""
        unit_map = {u.id: u for u in units}
        in_degree: Dict[str, int] = {u.id: 0 for u in units}

        for u in units:
            for dep in u.independence.depends_on:
                if dep in in_degree:
                    in_degree[u.id] += 1

        queue = deque([uid for uid, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            uid = queue.popleft()
            result.append(unit_map[uid])
            for u in units:
                if uid in u.independence.depends_on:
                    in_degree[u.id] -= 1
                    if in_degree[u.id] == 0:
                        queue.append(u.id)

        # Any remaining units have circular deps (should be caught by validator)
        remaining = [u for u in units if u.id not in {r.id for r in result}]
        result.extend(remaining)

        return result
