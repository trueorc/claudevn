"""Decision Trace Service for recording and querying planning decisions.

Provides a centralized service for all planning components to record
decision traces, and for the UI/debugging tools to query them.

Traces are stored in Redis with a retention policy (configurable max entries
per project) and can be queried by project, decision type, or item ID.

Reference: docs/work_management_framework.md — Section 11
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.decision_trace import (
    DecisionContext,
    DecisionImpact,
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)

logger = logging.getLogger(__name__)

# Maximum number of traces to retain per project in Redis
DEFAULT_RETENTION_LIMIT = 200

# Maximum number of traces per item index entry
ITEM_INDEX_LIMIT = 50


class DecisionTraceService:
    """Service for recording and querying decision traces.

    Provides methods for planning services to record traces and for
    query endpoints to retrieve them. Uses Redis list-based storage
    with automatic retention trimming.
    """

    def __init__(self, redis_client=None, retention_limit: int = DEFAULT_RETENTION_LIMIT):
        """Initialize the decision trace service.

        Args:
            redis_client: Optional Redis client for persistence.
            retention_limit: Maximum traces to keep per project.
        """
        self._redis = redis_client
        self._retention_limit = retention_limit
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("Decision trace service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}decision_trace:{key}"

    # =========================================================================
    # Recording
    # =========================================================================

    async def record_trace(self, trace: DecisionTrace) -> None:
        """Record a decision trace.

        Persists the trace to Redis, updates the item-level index
        for "why is this task here?" queries, and emits an event
        to the ObservabilityEventBus for real-time notification.

        Args:
            trace: The decision trace to record.
        """
        logger.info(
            f"Recording decision trace: type={trace.decision_type.value}, "
            f"project={trace.project_id}, trace_id={trace.trace_id}"
        )

        await self._save_trace_to_redis(trace)
        await self._index_by_items(trace)
        await self._emit_event(trace)

    async def record(
        self,
        project_id: str,
        decision_type: DecisionPointType,
        trigger: DecisionTrigger,
        decision_summary: str,
        key_factors: Optional[List[str]] = None,
        context: Optional[DecisionContext] = None,
        impact: Optional[DecisionImpact] = None,
        related_trace_ids: Optional[List[str]] = None,
    ) -> DecisionTrace:
        """Convenience method to create and record a trace in one call.

        Args:
            project_id: Project this decision belongs to.
            decision_type: Classification of the decision point.
            trigger: What initiated this decision.
            decision_summary: Concise description of the decision.
            key_factors: 2-3 reasons driving the decision.
            context: System state at decision time.
            impact: Downstream effects.
            related_trace_ids: IDs of related traces.

        Returns:
            The recorded DecisionTrace.
        """
        trace = DecisionTrace(
            trace_id=f"trace-{decision_type.value}-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            decision_type=decision_type,
            trigger=trigger,
            context=context or DecisionContext(),
            decision_summary=decision_summary,
            key_factors=key_factors or [],
            impact=impact or DecisionImpact(),
            related_trace_ids=related_trace_ids or [],
        )

        await self.record_trace(trace)
        return trace

    # =========================================================================
    # Querying
    # =========================================================================

    async def get_traces(
        self,
        project_id: str,
        decision_type: Optional[DecisionPointType] = None,
        limit: int = 50,
    ) -> List[DecisionTrace]:
        """Get decision traces for a project.

        Args:
            project_id: Project to query.
            decision_type: Optional filter by decision type.
            limit: Maximum traces to return.

        Returns:
            List of DecisionTrace, most recent first.
        """
        if not self._redis:
            return []

        try:
            key = self._key(f"project:{project_id}")
            # Fetch more than limit if filtering to account for type filtering
            fetch_limit = limit * 3 if decision_type else limit
            raw_entries = await self._redis._redis.lrange(key, 0, fetch_limit - 1)

            traces = []
            for raw in raw_entries:
                data = raw.decode() if isinstance(raw, bytes) else raw
                trace = DecisionTrace(**json.loads(data))

                if decision_type and trace.decision_type != decision_type:
                    continue

                traces.append(trace)
                if len(traces) >= limit:
                    break

            return traces
        except Exception as e:
            logger.error(f"Error loading decision traces for project {project_id}: {e}")
            return []

    async def get_traces_for_item(
        self,
        project_id: str,
        item_id: str,
        limit: int = 20,
    ) -> List[DecisionTrace]:
        """Get decision traces that affected a specific work item.

        Answers the question: "Why is this task here?"

        Args:
            project_id: Project the item belongs to.
            item_id: Work item ID to query.
            limit: Maximum traces to return.

        Returns:
            List of DecisionTrace affecting this item, most recent first.
        """
        if not self._redis:
            return []

        try:
            key = self._key(f"item:{project_id}:{item_id}")
            raw_entries = await self._redis._redis.lrange(key, 0, limit - 1)

            traces = []
            for raw in raw_entries:
                data = raw.decode() if isinstance(raw, bytes) else raw
                traces.append(DecisionTrace(**json.loads(data)))

            return traces
        except Exception as e:
            logger.error(f"Error loading traces for item {item_id}: {e}")
            return []

    async def get_trace_by_id(
        self,
        project_id: str,
        trace_id: str,
    ) -> Optional[DecisionTrace]:
        """Get a specific trace by its ID.

        Scans the project trace list for the matching trace_id.

        Args:
            project_id: Project to search.
            trace_id: Trace ID to find.

        Returns:
            The DecisionTrace if found, None otherwise.
        """
        if not self._redis:
            return None

        try:
            key = self._key(f"project:{project_id}")
            raw_entries = await self._redis._redis.lrange(key, 0, self._retention_limit - 1)

            for raw in raw_entries:
                data = raw.decode() if isinstance(raw, bytes) else raw
                trace = DecisionTrace(**json.loads(data))
                if trace.trace_id == trace_id:
                    return trace

            return None
        except Exception as e:
            logger.error(f"Error finding trace {trace_id}: {e}")
            return None

    async def get_trace_chain(
        self,
        project_id: str,
        trace_id: str,
        max_depth: int = 10,
    ) -> List[DecisionTrace]:
        """Follow the chain of related traces from a starting trace.

        Useful for understanding the full decision path that led to
        a particular state.

        Args:
            project_id: Project to search.
            trace_id: Starting trace ID.
            max_depth: Maximum chain depth to follow.

        Returns:
            Ordered list of traces in the chain.
        """
        chain: List[DecisionTrace] = []
        visited: set = set()
        to_visit = [trace_id]

        while to_visit and len(chain) < max_depth:
            current_id = to_visit.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            trace = await self.get_trace_by_id(project_id, current_id)
            if trace:
                chain.append(trace)
                for related_id in trace.related_trace_ids:
                    if related_id not in visited:
                        to_visit.append(related_id)

        return chain

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def _save_trace_to_redis(self, trace: DecisionTrace) -> None:
        """Persist a decision trace to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"project:{trace.project_id}")
            data = trace.model_dump_json()
            await self._redis._redis.lpush(key, data)
            await self._redis._redis.ltrim(key, 0, self._retention_limit - 1)
        except Exception as e:
            logger.error(f"Error saving decision trace to Redis: {e}")

    async def _index_by_items(self, trace: DecisionTrace) -> None:
        """Index a trace by affected item IDs for item-level queries."""
        if not self._redis:
            return

        affected_ids = trace.impact.affected_item_ids
        if not affected_ids:
            return

        try:
            data = trace.model_dump_json()
            for item_id in affected_ids:
                key = self._key(f"item:{trace.project_id}:{item_id}")
                await self._redis._redis.lpush(key, data)
                await self._redis._redis.ltrim(key, 0, ITEM_INDEX_LIMIT - 1)
        except Exception as e:
            logger.error(f"Error indexing trace by items: {e}")

    # =========================================================================
    # ObservabilityEventBus Integration
    # =========================================================================

    async def _emit_event(self, trace: DecisionTrace) -> None:
        """Emit a DecisionTraceEvent to the ObservabilityEventBus.

        Broadcasts a lightweight event so WebSocket subscribers and
        event handlers are notified in real time.
        """
        try:
            from services.observability_event_bus import get_event_bus
            from models.observability import DecisionTraceEvent

            event = DecisionTraceEvent(
                event_id=f"evt-{trace.trace_id}",
                session_id=trace.project_id,
                trace_id=trace.trace_id,
                decision_type=trace.decision_type,
                decision_summary=trace.decision_summary,
                trigger_type=trace.trigger.trigger_type,
                trigger_source_id=trace.trigger.source_id,
                affected_item_count=len(trace.impact.affected_item_ids),
                affected_bucket_count=len(trace.impact.affected_bucket_ids),
            )

            event_bus = get_event_bus()
            await event_bus.emit_event(event)
        except Exception as e:
            # Event bus emission is non-critical — log and continue
            logger.debug(f"Could not emit decision trace event: {e}")


# =============================================================================
# Global Instance
# =============================================================================


_decision_trace_service: Optional[DecisionTraceService] = None


def get_decision_trace_service() -> DecisionTraceService:
    """Get the global decision trace service instance."""
    if _decision_trace_service is None:
        raise RuntimeError("Decision trace service not initialized")
    return _decision_trace_service


def set_decision_trace_service(
    service: Optional[DecisionTraceService],
) -> None:
    """Set the global decision trace service instance."""
    global _decision_trace_service
    _decision_trace_service = service
