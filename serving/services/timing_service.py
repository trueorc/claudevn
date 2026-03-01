"""Timing Service for compute lifecycle instrumentation.

Collects, persists, and queries per-work-item timing data.
Uses Redis for storage when available, falls back to in-memory.
"""

import json
import logging
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.timing import (
    AggregateStats,
    TimingDashboardResponse,
    TimingEntry,
    TimingPhase,
    WorkItemTiming,
)

logger = logging.getLogger(__name__)

# Redis key prefix for timing data
TIMING_KEY_PREFIX = "timing"
# Max work items to keep in memory (fallback)
MAX_IN_MEMORY_ITEMS = 500
# Default TTL for timing data in Redis (7 days)
TIMING_TTL_SECONDS = 7 * 24 * 3600


class TimingService:
    """Service for recording and querying compute lifecycle timing."""

    def __init__(self, redis_client=None):
        """Initialize timing service.

        Args:
            redis_client: Optional RedisClient for persistence.
                          Falls back to in-memory storage if None.
        """
        self._redis = redis_client
        self._memory: Dict[str, WorkItemTiming] = {}
        self._index: List[str] = []  # ordered keys for in-memory fallback

    def _make_key(self, work_id: str, instance_id: str) -> str:
        """Create a composite key for a work item timing record."""
        return f"{work_id}:{instance_id}"

    async def record_phase_start(
        self,
        work_id: str,
        instance_id: str,
        phase: TimingPhase,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record the start of a timing phase.

        Args:
            work_id: Work item ID
            instance_id: Compute instance ID
            phase: Lifecycle phase starting
            metadata: Optional phase-specific metadata
        """
        entry = TimingEntry(
            phase=phase,
            start=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

        key = self._make_key(work_id, instance_id)

        if self._redis:
            await self._redis_append_entry(key, work_id, instance_id, entry)
        else:
            self._memory_append_entry(key, work_id, instance_id, entry)

        logger.debug(f"Timing start: {phase.value} for {work_id}/{instance_id}")

    async def record_phase_end(
        self,
        work_id: str,
        instance_id: str,
        phase: TimingPhase,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record the end of a timing phase, computing duration.

        Args:
            work_id: Work item ID
            instance_id: Compute instance ID
            phase: Lifecycle phase ending
            metadata: Optional additional metadata to merge
        """
        now = datetime.now(timezone.utc)
        key = self._make_key(work_id, instance_id)

        timing = await self._get_timing(key, work_id, instance_id)
        if not timing:
            logger.warning(f"No timing record for {key}, creating with end only")
            entry = TimingEntry(
                phase=phase,
                start=now,
                end=now,
                duration_ms=0.0,
                metadata=metadata or {},
            )
            if self._redis:
                await self._redis_append_entry(key, work_id, instance_id, entry)
            else:
                self._memory_append_entry(key, work_id, instance_id, entry)
            return

        # Find the most recent open entry for this phase
        for entry in reversed(timing.entries):
            if entry.phase == phase and entry.end is None:
                entry.end = now
                entry.duration_ms = (now - entry.start).total_seconds() * 1000
                if metadata:
                    entry.metadata.update(metadata)
                break
        else:
            # No open entry found - record as a point-in-time
            logger.warning(f"No open entry for phase {phase.value} in {key}")
            timing.entries.append(TimingEntry(
                phase=phase,
                start=now,
                end=now,
                duration_ms=0.0,
                metadata=metadata or {},
            ))

        await self._save_timing(key, timing)
        logger.debug(f"Timing end: {phase.value} for {work_id}/{instance_id}")

    async def record_phase(
        self,
        work_id: str,
        instance_id: str,
        phase: TimingPhase,
        start: datetime,
        end: datetime,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record a complete phase with known start and end times.

        Args:
            work_id: Work item ID
            instance_id: Compute instance ID
            phase: Lifecycle phase
            start: Phase start time
            end: Phase end time
            metadata: Optional phase-specific metadata
        """
        duration_ms = (end - start).total_seconds() * 1000
        entry = TimingEntry(
            phase=phase,
            start=start,
            end=end,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

        key = self._make_key(work_id, instance_id)

        if self._redis:
            await self._redis_append_entry(key, work_id, instance_id, entry)
        else:
            self._memory_append_entry(key, work_id, instance_id, entry)

        logger.debug(
            f"Timing recorded: {phase.value} = {duration_ms:.0f}ms "
            f"for {work_id}/{instance_id}"
        )

    async def get_work_item_timing(
        self, work_id: str, instance_id: str
    ) -> Optional[WorkItemTiming]:
        """Get timing data for a specific work item.

        Args:
            work_id: Work item ID
            instance_id: Compute instance ID

        Returns:
            WorkItemTiming or None
        """
        key = self._make_key(work_id, instance_id)
        return await self._get_timing(key, work_id, instance_id)

    async def get_recent_timings(self, limit: int = 50) -> List[WorkItemTiming]:
        """Get timing data for recent work items.

        Args:
            limit: Maximum number of items to return

        Returns:
            List of WorkItemTiming, most recent first
        """
        if self._redis:
            return await self._redis_get_recent(limit)

        # In-memory: return from index in reverse order
        keys = self._index[-limit:]
        keys.reverse()
        return [self._memory[k] for k in keys if k in self._memory]

    async def get_aggregate_stats(self, limit: int = 100) -> List[AggregateStats]:
        """Compute aggregate stats across recent work items.

        Args:
            limit: Number of recent work items to aggregate over

        Returns:
            List of AggregateStats, one per phase
        """
        timings = await self.get_recent_timings(limit)

        # Collect durations by phase
        by_phase: Dict[TimingPhase, List[float]] = {}
        for timing in timings:
            for entry in timing.entries:
                if entry.duration_ms is not None:
                    by_phase.setdefault(entry.phase, []).append(entry.duration_ms)

        results = []
        for phase in TimingPhase:
            durations = by_phase.get(phase, [])
            if not durations:
                continue

            durations_sorted = sorted(durations)
            count = len(durations_sorted)

            results.append(AggregateStats(
                phase=phase,
                count=count,
                avg_ms=round(statistics.mean(durations_sorted), 1),
                p50_ms=round(self._percentile(durations_sorted, 50), 1),
                p95_ms=round(self._percentile(durations_sorted, 95), 1),
                p99_ms=round(self._percentile(durations_sorted, 99), 1),
                min_ms=round(durations_sorted[0], 1),
                max_ms=round(durations_sorted[-1], 1),
            ))

        return results

    async def get_dashboard(self, limit: int = 20) -> TimingDashboardResponse:
        """Get dashboard data combining recent timings and aggregates.

        Enriches work items with issue context from the work map service
        when available.

        Args:
            limit: Number of recent work items to show

        Returns:
            TimingDashboardResponse
        """
        work_items = await self.get_recent_timings(limit)
        aggregates = await self.get_aggregate_stats(100)

        # Enrich work items with issue context
        await self._enrich_issue_context(work_items)

        # Count total work items
        if self._redis:
            total = await self._redis_count()
        else:
            total = len(self._memory)

        return TimingDashboardResponse(
            work_items=work_items,
            aggregates=aggregates,
            total_work_items=total,
        )

    async def _enrich_issue_context(
        self, work_items: List[WorkItemTiming]
    ) -> None:
        """Enrich work items with issue context from the work map service.

        Looks up each work_id in the work map service to find the associated
        issue ID and title. Modifies work items in place.
        """
        try:
            from services.work_map_service import get_work_map_service
            wm_service = get_work_map_service()
        except (RuntimeError, ImportError):
            logger.debug("Work map service not available for issue enrichment")
            return

        for item in work_items:
            if item.issue_id:
                continue  # Already has issue context
            try:
                work = await wm_service.get_work(item.work_id)
                if work and work.issue_id:
                    item.issue_id = work.issue_id
                    item.issue_title = work.title
            except Exception:
                logger.debug(f"Could not look up issue for work_id={item.work_id}")

    # =========================================================================
    # Private helpers
    # =========================================================================

    @staticmethod
    def _percentile(sorted_data: List[float], p: float) -> float:
        """Compute percentile from sorted data."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * (p / 100)
        f = int(k)
        c = f + 1
        if c >= len(sorted_data):
            return sorted_data[-1]
        d0 = sorted_data[f] * (c - k)
        d1 = sorted_data[c] * (k - f)
        return d0 + d1

    # =========================================================================
    # In-memory storage
    # =========================================================================

    def _memory_append_entry(
        self, key: str, work_id: str, instance_id: str, entry: TimingEntry
    ) -> None:
        """Append a timing entry to in-memory storage."""
        if key not in self._memory:
            self._memory[key] = WorkItemTiming(
                work_id=work_id, instance_id=instance_id
            )
            self._index.append(key)
            # Evict oldest if over limit
            if len(self._index) > MAX_IN_MEMORY_ITEMS:
                old_key = self._index.pop(0)
                self._memory.pop(old_key, None)

        self._memory[key].entries.append(entry)

    # =========================================================================
    # Redis storage
    # =========================================================================

    async def _redis_append_entry(
        self, key: str, work_id: str, instance_id: str, entry: TimingEntry
    ) -> None:
        """Append a timing entry to Redis storage."""
        redis_key = f"{TIMING_KEY_PREFIX}:{key}"

        # Get or create the timing record
        existing = await self._redis.hgetall(redis_key)

        if existing:
            entries_json = existing.get("entries", "[]")
            entries = json.loads(entries_json)
        else:
            entries = []
            # Set metadata fields
            await self._redis.hset(redis_key, mapping={
                "work_id": work_id,
                "instance_id": instance_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            # Add to index sorted set
            await self._redis._redis.zadd(
                self._redis._key(f"{TIMING_KEY_PREFIX}:index"),
                {key: datetime.now(timezone.utc).timestamp()},
            )

        entries.append(entry.model_dump(mode="json"))
        await self._redis.hset(redis_key, mapping={"entries": json.dumps(entries)})

        # Set TTL
        await self._redis._redis.expire(
            self._redis._key(redis_key), TIMING_TTL_SECONDS
        )

    async def _get_timing(
        self, key: str, work_id: str, instance_id: str
    ) -> Optional[WorkItemTiming]:
        """Get timing record by key."""
        if self._redis:
            redis_key = f"{TIMING_KEY_PREFIX}:{key}"
            data = await self._redis.hgetall(redis_key)
            if not data:
                return None
            entries = json.loads(data.get("entries", "[]"))
            return WorkItemTiming(
                work_id=data.get("work_id", work_id),
                instance_id=data.get("instance_id", instance_id),
                entries=[TimingEntry(**e) for e in entries],
                created_at=datetime.fromisoformat(data["created_at"])
                if "created_at" in data else datetime.now(timezone.utc),
            )

        return self._memory.get(key)

    async def _save_timing(self, key: str, timing: WorkItemTiming) -> None:
        """Save a complete timing record."""
        if self._redis:
            redis_key = f"{TIMING_KEY_PREFIX}:{key}"
            entries = [e.model_dump(mode="json") for e in timing.entries]
            await self._redis.hset(redis_key, mapping={
                "entries": json.dumps(entries),
            })
        else:
            self._memory[key] = timing

    async def _redis_get_recent(self, limit: int) -> List[WorkItemTiming]:
        """Get recent timing records from Redis."""
        index_key = f"{TIMING_KEY_PREFIX}:index"
        # Get most recent keys from sorted set
        keys = await self._redis._redis.zrevrange(
            self._redis._key(index_key), 0, limit - 1
        )

        results = []
        for key in keys:
            timing = await self._get_timing(key, "", "")
            if timing:
                results.append(timing)

        return results

    async def _redis_count(self) -> int:
        """Count total timing records in Redis."""
        index_key = f"{TIMING_KEY_PREFIX}:index"
        return await self._redis._redis.zcard(
            self._redis._key(index_key)
        )


# =========================================================================
# Global singleton
# =========================================================================

_timing_service: Optional[TimingService] = None


def get_timing_service() -> TimingService:
    """Get the global timing service instance."""
    if _timing_service is None:
        raise RuntimeError("Timing service not initialized")
    return _timing_service


def set_timing_service(service: Optional[TimingService]) -> None:
    """Set the global timing service instance."""
    global _timing_service
    _timing_service = service
