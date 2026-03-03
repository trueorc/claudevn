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

    @staticmethod
    def _clean_tool_name(name: str) -> str:
        """Strip common prefixes from MCP tool names."""
        if name and name.startswith("claudevn_"):
            return name[len("claudevn_"):]
        return name

    async def get_aggregate_stats(self, limit: int = 100) -> List[AggregateStats]:
        """Compute aggregate stats across recent work items.

        MCP tool calls are broken out by individual tool name rather than
        being grouped as a single "mcp_tool_call" category.

        Args:
            limit: Number of recent work items to aggregate over

        Returns:
            List of AggregateStats, one per (phase, tool_name) combination
        """
        timings = await self.get_recent_timings(limit)

        # Collect durations by (phase, tool_name) where tool_name is set
        # only for MCP tool calls.
        by_key: Dict[tuple, List[float]] = {}
        for timing in timings:
            for entry in timing.entries:
                if entry.duration_ms is None:
                    continue
                if entry.phase == TimingPhase.MCP_TOOL_CALL:
                    raw_name = (entry.metadata or {}).get("tool_name", "")
                    tool_name = self._clean_tool_name(raw_name) if raw_name else "unknown"
                    key = (entry.phase, tool_name)
                else:
                    key = (entry.phase, None)
                by_key.setdefault(key, []).append(entry.duration_ms)

        results = []
        # Non-MCP phases first (in enum order), then MCP tools sorted by name
        for phase in TimingPhase:
            if phase == TimingPhase.MCP_TOOL_CALL:
                continue
            durations = by_key.get((phase, None), [])
            if not durations:
                continue
            results.append(self._make_aggregate(phase, None, durations))

        # MCP tool calls sorted alphabetically by tool name
        mcp_keys = sorted(
            (k for k in by_key if k[0] == TimingPhase.MCP_TOOL_CALL),
            key=lambda k: k[1] or "",
        )
        for key in mcp_keys:
            phase, tool_name = key
            durations = by_key[key]
            results.append(self._make_aggregate(phase, tool_name, durations))

        return results

    def _make_aggregate(
        self, phase: TimingPhase, tool_name: Optional[str], durations: List[float]
    ) -> AggregateStats:
        """Build an AggregateStats from a list of durations."""
        durations_sorted = sorted(durations)
        count = len(durations_sorted)
        return AggregateStats(
            phase=phase,
            tool_name=tool_name,
            count=count,
            avg_ms=round(statistics.mean(durations_sorted), 1),
            p50_ms=round(self._percentile(durations_sorted, 50), 1),
            p95_ms=round(self._percentile(durations_sorted, 95), 1),
            p99_ms=round(self._percentile(durations_sorted, 99), 1),
            min_ms=round(durations_sorted[0], 1),
            max_ms=round(durations_sorted[-1], 1),
        )

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
        """Enrich work items with issue and directive context.

        Looks up each work_id in the work map service to find the associated
        issue ID and title.  Also traces directive-level work items
        (decomp-*, char-*, conflict-*) back to their parent directive.
        Modifies work items in place.
        """
        try:
            from services.work_map_service import get_work_map_service
            wm_service = get_work_map_service()
        except (RuntimeError, ImportError):
            logger.debug("Work map service not available for issue enrichment")
            wm_service = None

        # Optional services for directive tracing
        goal_service = None
        directive_service = None
        try:
            from services.goal_service import get_goal_service
            goal_service = get_goal_service()
        except (RuntimeError, ImportError):
            pass
        try:
            from services.unified_directive_service import get_unified_directive_service
            directive_service = get_unified_directive_service()
        except (RuntimeError, ImportError):
            pass

        for item in work_items:
            # Enrich issue context from work map
            if not item.issue_id and wm_service:
                try:
                    work = await wm_service.get_work(item.work_id)
                    if work and work.issue_id:
                        item.issue_id = work.issue_id
                        item.issue_title = work.title
                except Exception:
                    logger.debug(f"Could not look up issue for work_id={item.work_id}")

            # Trace directive-level work (decomp-*, char-*, conflict-*)
            if not item.directive_id:
                await self._enrich_directive_context(
                    item, goal_service, directive_service
                )

    async def _enrich_directive_context(
        self,
        item: WorkItemTiming,
        goal_service,
        directive_service,
    ) -> None:
        """Trace a work item back to its parent directive if possible.

        Handles decomp-{id}, char-{id}, and conflict-{work_id}-{hex} patterns
        by looking up the goal associated with the decomposition/characterization
        and then finding the directive that created the goal.
        """
        work_id = item.work_id
        goal_id = None

        try:
            if work_id.startswith("decomp-") and goal_service:
                # decomp-{decomposition_id} — find goal by decomposition_id
                decomp_id = work_id
                goals = await goal_service.list_goals()
                for goal in goals:
                    if getattr(goal, "decomposition_id", None) == decomp_id:
                        goal_id = goal.goal_id
                        break
            elif work_id.startswith("char-") and goal_service:
                # char-{id} — characterization tasks tie to a goal similarly
                goals = await goal_service.list_goals()
                for goal in goals:
                    passes = getattr(goal, "decomposition_passes", []) or []
                    for p in passes:
                        if isinstance(p, dict) and p.get("characterization_id") == work_id:
                            goal_id = goal.goal_id
                            break
                    if goal_id:
                        break
            elif work_id.startswith("conflict-"):
                # conflict-{original_work_id}-{hex} — no direct goal link;
                # mark as directive-level system work
                item.directive_id = "__system__"
                item.directive_title = "Conflict Resolution"
                return
            elif work_id.startswith("compute-"):
                # compute lifecycle — system-level
                item.directive_id = "__system__"
                item.directive_title = "Compute Lifecycle"
                return
            else:
                return  # Not a directive-level work item

            # Resolve goal → directive
            if goal_id and directive_service:
                directives = await directive_service.list_directives()
                for d in directives:
                    outcome = getattr(d, "outcome", None)
                    if outcome and getattr(outcome, "goal_id_created", None) == goal_id:
                        item.directive_id = d.directive_id
                        item.directive_title = getattr(d, "title", None) or d.directive_id
                        return

            # Could resolve goal but not directive — still mark as directive-level
            if goal_id:
                item.directive_id = f"goal:{goal_id}"
                item.directive_title = f"Goal {goal_id[:8]}..."
        except Exception:
            logger.debug(f"Could not trace directive for work_id={work_id}")

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
