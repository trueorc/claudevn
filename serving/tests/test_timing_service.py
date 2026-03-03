"""Tests for timing service aggregate stats and enrichment."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from serving.models.timing import (
    AggregateStats,
    TimingEntry,
    TimingPhase,
    WorkItemTiming,
)
from serving.services.timing_service import TimingService


def _make_entry(phase, duration_ms, tool_name=None):
    """Create a TimingEntry with optional tool_name metadata."""
    meta = {}
    if tool_name:
        meta["tool_name"] = tool_name
    return TimingEntry(
        phase=phase,
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 1, tzinfo=timezone.utc),
        duration_ms=duration_ms,
        metadata=meta,
    )


def _make_work_item(work_id, entries, issue_id=None, issue_title=None):
    """Create a WorkItemTiming with given entries."""
    return WorkItemTiming(
        work_id=work_id,
        instance_id="compute-1",
        entries=entries,
        issue_id=issue_id,
        issue_title=issue_title,
    )


class TestCleanToolName:
    """Tests for _clean_tool_name static method."""

    def test_strips_claudevn_prefix(self):
        assert TimingService._clean_tool_name("claudevn_get_context") == "get_context"

    def test_leaves_names_without_prefix(self):
        assert TimingService._clean_tool_name("get_context") == "get_context"

    def test_handles_empty_string(self):
        assert TimingService._clean_tool_name("") == ""


class TestGetAggregateStats:
    """Tests for aggregate stats with per-tool MCP breakdown."""

    @pytest.fixture
    def service(self):
        return TimingService(redis_client=None)

    @pytest.mark.asyncio
    async def test_empty_returns_empty(self, service):
        stats = await service.get_aggregate_stats(limit=10)
        assert stats == []

    @pytest.mark.asyncio
    async def test_non_mcp_phases_aggregated_normally(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 100.0),
        )
        service._memory_append_entry(
            "w2:c1", "w2", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 200.0),
        )

        stats = await service.get_aggregate_stats(limit=10)
        assert len(stats) == 1
        assert stats[0].phase == TimingPhase.SDK_LAUNCH
        assert stats[0].tool_name is None
        assert stats[0].count == 2
        assert stats[0].avg_ms == 150.0

    @pytest.mark.asyncio
    async def test_mcp_calls_broken_out_by_tool_name(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 100.0, "claudevn_get_context"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 200.0, "claudevn_get_context"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 300.0, "claudevn_report_progress"),
        )

        stats = await service.get_aggregate_stats(limit=10)

        # Should have 2 MCP groups: get_context and report_progress
        mcp_stats = [s for s in stats if s.phase == TimingPhase.MCP_TOOL_CALL]
        assert len(mcp_stats) == 2

        gc = next(s for s in mcp_stats if s.tool_name == "get_context")
        assert gc.count == 2
        assert gc.avg_ms == 150.0

        rp = next(s for s in mcp_stats if s.tool_name == "report_progress")
        assert rp.count == 1
        assert rp.avg_ms == 300.0

    @pytest.mark.asyncio
    async def test_mcp_without_tool_name_uses_unknown(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 100.0),
        )

        stats = await service.get_aggregate_stats(limit=10)
        mcp_stats = [s for s in stats if s.phase == TimingPhase.MCP_TOOL_CALL]
        assert len(mcp_stats) == 1
        assert mcp_stats[0].tool_name == "unknown"

    @pytest.mark.asyncio
    async def test_non_mcp_before_mcp_in_results(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 100.0),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 200.0, "claudevn_get_context"),
        )

        stats = await service.get_aggregate_stats(limit=10)
        assert len(stats) == 2
        assert stats[0].phase == TimingPhase.SDK_LAUNCH
        assert stats[1].phase == TimingPhase.MCP_TOOL_CALL
        assert stats[1].tool_name == "get_context"

    @pytest.mark.asyncio
    async def test_mcp_tools_sorted_alphabetically(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 100.0, "claudevn_report_progress"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 200.0, "claudevn_get_context"),
        )

        stats = await service.get_aggregate_stats(limit=10)
        tool_names = [s.tool_name for s in stats if s.phase == TimingPhase.MCP_TOOL_CALL]
        assert tool_names == ["get_context", "report_progress"]


class TestEnrichDirectiveContext:
    """Tests for directive-level work item enrichment."""

    @pytest.fixture
    def service(self):
        return TimingService(redis_client=None)

    @pytest.mark.asyncio
    async def test_conflict_work_id_marked_as_system(self, service):
        item = _make_work_item("conflict-w1-abc123", [])
        await service._enrich_directive_context(item, None, None)
        assert item.directive_id == "__system__"
        assert item.directive_title == "Conflict Resolution"

    @pytest.mark.asyncio
    async def test_compute_work_id_marked_as_system(self, service):
        item = _make_work_item("compute-lifecycle-xyz", [])
        await service._enrich_directive_context(item, None, None)
        assert item.directive_id == "__system__"
        assert item.directive_title == "Compute Lifecycle"

    @pytest.mark.asyncio
    async def test_regular_work_id_not_enriched(self, service):
        item = _make_work_item("regular-work-item", [])
        await service._enrich_directive_context(item, None, None)
        assert item.directive_id is None
        assert item.directive_title is None

    @pytest.mark.asyncio
    async def test_decomp_traced_to_goal_and_directive(self, service):
        # Mock goal service
        mock_goal = MagicMock()
        mock_goal.goal_id = "goal-1"
        mock_goal.decomposition_id = "decomp-abc"

        goal_service = AsyncMock()
        goal_service.list_goals = AsyncMock(return_value=[mock_goal])

        # Mock directive service
        mock_directive = MagicMock()
        mock_directive.directive_id = "dir-1"
        mock_directive.title = "Build authentication"
        mock_outcome = MagicMock()
        mock_outcome.goal_id_created = "goal-1"
        mock_directive.outcome = mock_outcome

        directive_service = AsyncMock()
        directive_service.list_directives = AsyncMock(return_value=[mock_directive])

        item = _make_work_item("decomp-abc", [])
        await service._enrich_directive_context(item, goal_service, directive_service)

        assert item.directive_id == "dir-1"
        assert item.directive_title == "Build authentication"

    @pytest.mark.asyncio
    async def test_decomp_with_goal_but_no_directive(self, service):
        mock_goal = MagicMock()
        mock_goal.goal_id = "goal-1"
        mock_goal.decomposition_id = "decomp-abc"

        goal_service = AsyncMock()
        goal_service.list_goals = AsyncMock(return_value=[mock_goal])

        directive_service = AsyncMock()
        directive_service.list_directives = AsyncMock(return_value=[])

        item = _make_work_item("decomp-abc", [])
        await service._enrich_directive_context(item, goal_service, directive_service)

        assert item.directive_id == "goal:goal-1"

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self, service):
        goal_service = AsyncMock()
        goal_service.list_goals = AsyncMock(side_effect=RuntimeError("boom"))

        item = _make_work_item("decomp-abc", [])
        # Should not raise
        await service._enrich_directive_context(item, goal_service, None)
        assert item.directive_id is None
