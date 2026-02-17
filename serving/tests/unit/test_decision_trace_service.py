"""Unit tests for DecisionTraceService.

Tests recording, querying, item-level indexing, and trace chaining.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.decision_trace import (
    DecisionContext,
    DecisionImpact,
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)
from services.decision_trace_service import (
    DecisionTraceService,
    get_decision_trace_service,
    set_decision_trace_service,
)


# =============================================================================
# Fixtures
# =============================================================================


def make_trace(
    trace_id="trace-test-001",
    project_id="proj-1",
    decision_type=DecisionPointType.PROFILE_SHIFT,
    trigger_type="new_goal",
    decision_summary="Test decision",
    affected_items=None,
    related_trace_ids=None,
):
    """Helper to create a DecisionTrace for testing."""
    return DecisionTrace(
        trace_id=trace_id,
        project_id=project_id,
        decision_type=decision_type,
        trigger=DecisionTrigger(trigger_type=trigger_type),
        decision_summary=decision_summary,
        impact=DecisionImpact(
            affected_item_ids=affected_items or [],
        ),
        related_trace_ids=related_trace_ids or [],
    )


def make_mock_redis():
    """Create a mock Redis client with the internal structure."""
    mock_redis = MagicMock()
    mock_redis._prefix = "claudevn:"
    mock_redis._redis = AsyncMock()
    return mock_redis


# =============================================================================
# TestDecisionTraceServiceInit
# =============================================================================


class TestDecisionTraceServiceInit:
    """Tests for service initialization."""

    def test_init_defaults(self):
        """Service initializes with default settings."""
        service = DecisionTraceService()
        assert service._redis is None
        assert service._retention_limit == 200
        assert service._initialized is False

    def test_init_with_redis(self):
        """Service initializes with Redis client."""
        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)
        assert service._redis is mock_redis

    def test_init_custom_retention(self):
        """Service initializes with custom retention limit."""
        service = DecisionTraceService(retention_limit=500)
        assert service._retention_limit == 500

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Initialize sets initialized flag."""
        service = DecisionTraceService()
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        """Initialize is idempotent."""
        service = DecisionTraceService()
        await service.initialize()
        await service.initialize()
        assert service._initialized is True


# =============================================================================
# TestRecordTrace
# =============================================================================


class TestRecordTrace:
    """Tests for trace recording."""

    @pytest.mark.asyncio
    async def test_record_trace_no_redis(self):
        """Recording without Redis does not raise."""
        service = DecisionTraceService(redis_client=None)
        trace = make_trace()
        await service.record_trace(trace)  # Should not raise

    @pytest.mark.asyncio
    async def test_record_trace_saves_to_redis(self):
        """Recording persists trace to Redis project list."""
        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)
        trace = make_trace()

        await service.record_trace(trace)

        mock_redis._redis.lpush.assert_called()
        call_args = mock_redis._redis.lpush.call_args_list[0]
        key = call_args[0][0]
        assert "decision_trace:project:proj-1" in key

    @pytest.mark.asyncio
    async def test_record_trace_trims_to_retention_limit(self):
        """Recording trims the list to retention limit."""
        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis, retention_limit=100)
        trace = make_trace()

        await service.record_trace(trace)

        mock_redis._redis.ltrim.assert_called()
        call_args = mock_redis._redis.ltrim.call_args_list[0]
        assert call_args[0][2] == 99  # 0-indexed limit

    @pytest.mark.asyncio
    async def test_record_trace_indexes_affected_items(self):
        """Recording indexes trace by affected item IDs."""
        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)
        trace = make_trace(affected_items=["item-1", "item-2"])

        await service.record_trace(trace)

        # Should have calls for project + 2 items = 3 lpush calls
        assert mock_redis._redis.lpush.call_count == 3

    @pytest.mark.asyncio
    async def test_record_trace_no_index_when_no_affected_items(self):
        """Recording skips item indexing when no items affected."""
        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)
        trace = make_trace(affected_items=[])

        await service.record_trace(trace)

        # Only 1 lpush call for the project list
        assert mock_redis._redis.lpush.call_count == 1

    @pytest.mark.asyncio
    async def test_record_convenience_method(self):
        """Convenience record() method creates and saves trace."""
        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)

        trace = await service.record(
            project_id="proj-1",
            decision_type=DecisionPointType.WORKER_ASSIGNMENT,
            trigger=DecisionTrigger(trigger_type="assignment"),
            decision_summary="Assigned worker to task",
            key_factors=["Context affinity"],
        )

        assert trace.project_id == "proj-1"
        assert trace.decision_type == DecisionPointType.WORKER_ASSIGNMENT
        assert "trace-worker_assignment-" in trace.trace_id
        mock_redis._redis.lpush.assert_called()

    @pytest.mark.asyncio
    async def test_record_trace_handles_redis_error(self):
        """Recording handles Redis errors gracefully."""
        mock_redis = make_mock_redis()
        mock_redis._redis.lpush.side_effect = Exception("Redis down")
        service = DecisionTraceService(redis_client=mock_redis)
        trace = make_trace()

        # Should not raise
        await service.record_trace(trace)


# =============================================================================
# TestGetTraces
# =============================================================================


class TestGetTraces:
    """Tests for trace querying."""

    @pytest.mark.asyncio
    async def test_get_traces_no_redis(self):
        """Querying without Redis returns empty list."""
        service = DecisionTraceService(redis_client=None)
        result = await service.get_traces("proj-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_traces_returns_traces(self):
        """Querying returns deserialized traces."""
        mock_redis = make_mock_redis()
        trace = make_trace()
        mock_redis._redis.lrange.return_value = [trace.model_dump_json().encode()]

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_traces("proj-1")

        assert len(result) == 1
        assert result[0].trace_id == "trace-test-001"

    @pytest.mark.asyncio
    async def test_get_traces_filters_by_type(self):
        """Querying with decision_type filter works."""
        mock_redis = make_mock_redis()
        trace1 = make_trace(trace_id="t1", decision_type=DecisionPointType.PROFILE_SHIFT)
        trace2 = make_trace(trace_id="t2", decision_type=DecisionPointType.BUCKET_REORGANIZATION)
        mock_redis._redis.lrange.return_value = [
            trace1.model_dump_json().encode(),
            trace2.model_dump_json().encode(),
        ]

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_traces(
            "proj-1", decision_type=DecisionPointType.PROFILE_SHIFT
        )

        assert len(result) == 1
        assert result[0].trace_id == "t1"

    @pytest.mark.asyncio
    async def test_get_traces_respects_limit(self):
        """Querying respects the limit parameter."""
        mock_redis = make_mock_redis()
        traces = [
            make_trace(trace_id=f"t{i}").model_dump_json().encode()
            for i in range(5)
        ]
        mock_redis._redis.lrange.return_value = traces

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_traces("proj-1", limit=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_traces_handles_redis_error(self):
        """Querying handles Redis errors gracefully."""
        mock_redis = make_mock_redis()
        mock_redis._redis.lrange.side_effect = Exception("Redis down")

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_traces("proj-1")
        assert result == []


# =============================================================================
# TestGetTracesForItem
# =============================================================================


class TestGetTracesForItem:
    """Tests for item-level trace querying."""

    @pytest.mark.asyncio
    async def test_get_traces_for_item_no_redis(self):
        """Item querying without Redis returns empty list."""
        service = DecisionTraceService(redis_client=None)
        result = await service.get_traces_for_item("proj-1", "item-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_traces_for_item_returns_traces(self):
        """Item querying returns relevant traces."""
        mock_redis = make_mock_redis()
        trace = make_trace(affected_items=["item-1"])
        mock_redis._redis.lrange.return_value = [trace.model_dump_json().encode()]

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_traces_for_item("proj-1", "item-1")

        assert len(result) == 1
        call_args = mock_redis._redis.lrange.call_args[0]
        assert "item:proj-1:item-1" in call_args[0]


# =============================================================================
# TestGetTraceById
# =============================================================================


class TestGetTraceById:
    """Tests for single trace retrieval."""

    @pytest.mark.asyncio
    async def test_get_trace_by_id_found(self):
        """Finding a trace by ID returns it."""
        mock_redis = make_mock_redis()
        trace = make_trace(trace_id="trace-find-me")
        mock_redis._redis.lrange.return_value = [trace.model_dump_json().encode()]

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_trace_by_id("proj-1", "trace-find-me")

        assert result is not None
        assert result.trace_id == "trace-find-me"

    @pytest.mark.asyncio
    async def test_get_trace_by_id_not_found(self):
        """Missing trace returns None."""
        mock_redis = make_mock_redis()
        mock_redis._redis.lrange.return_value = []

        service = DecisionTraceService(redis_client=mock_redis)
        result = await service.get_trace_by_id("proj-1", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_trace_by_id_no_redis(self):
        """No Redis returns None."""
        service = DecisionTraceService(redis_client=None)
        result = await service.get_trace_by_id("proj-1", "trace-id")
        assert result is None


# =============================================================================
# TestGetTraceChain
# =============================================================================


class TestGetTraceChain:
    """Tests for trace chain following."""

    @pytest.mark.asyncio
    async def test_trace_chain_single(self):
        """Chain with a single trace works."""
        mock_redis = make_mock_redis()
        trace = make_trace(trace_id="trace-root")
        mock_redis._redis.lrange.return_value = [trace.model_dump_json().encode()]

        service = DecisionTraceService(redis_client=mock_redis)
        chain = await service.get_trace_chain("proj-1", "trace-root")

        assert len(chain) == 1
        assert chain[0].trace_id == "trace-root"

    @pytest.mark.asyncio
    async def test_trace_chain_follows_related(self):
        """Chain follows related_trace_ids."""
        mock_redis = make_mock_redis()
        trace1 = make_trace(trace_id="trace-1", related_trace_ids=["trace-2"])
        trace2 = make_trace(trace_id="trace-2")

        # Return different traces based on which call
        call_count = [0]
        raw_data = {
            "trace-1": [trace1.model_dump_json().encode()],
            "trace-2": [trace2.model_dump_json().encode()],
        }

        async def mock_lrange(key, start, end):
            # Return all traces for scanning
            return [trace1.model_dump_json().encode(), trace2.model_dump_json().encode()]

        mock_redis._redis.lrange.side_effect = mock_lrange

        service = DecisionTraceService(redis_client=mock_redis)
        chain = await service.get_trace_chain("proj-1", "trace-1")

        assert len(chain) == 2

    @pytest.mark.asyncio
    async def test_trace_chain_respects_max_depth(self):
        """Chain stops at max_depth."""
        mock_redis = make_mock_redis()

        # Create a long chain
        traces = []
        for i in range(20):
            next_id = f"trace-{i+1}" if i < 19 else None
            t = make_trace(
                trace_id=f"trace-{i}",
                related_trace_ids=[next_id] if next_id else [],
            )
            traces.append(t)

        async def mock_lrange(key, start, end):
            return [t.model_dump_json().encode() for t in traces]

        mock_redis._redis.lrange.side_effect = mock_lrange

        service = DecisionTraceService(redis_client=mock_redis)
        chain = await service.get_trace_chain("proj-1", "trace-0", max_depth=5)

        assert len(chain) <= 5

    @pytest.mark.asyncio
    async def test_trace_chain_empty_when_not_found(self):
        """Chain returns empty list when starting trace not found."""
        mock_redis = make_mock_redis()
        mock_redis._redis.lrange.return_value = []

        service = DecisionTraceService(redis_client=mock_redis)
        chain = await service.get_trace_chain("proj-1", "nonexistent")

        assert chain == []


# =============================================================================
# TestGlobalInstance
# =============================================================================


class TestGlobalInstance:
    """Tests for singleton pattern."""

    def test_get_service_raises_when_not_initialized(self):
        """Getting service before initialization raises RuntimeError."""
        set_decision_trace_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_decision_trace_service()

    def test_set_and_get_service(self):
        """Setting and getting the global instance works."""
        service = DecisionTraceService()
        set_decision_trace_service(service)
        assert get_decision_trace_service() is service

        # Cleanup
        set_decision_trace_service(None)
