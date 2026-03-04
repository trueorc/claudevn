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


def _make_work_item(work_id, entries, issue_id=None, issue_title=None, project_id=None):
    """Create a WorkItemTiming with given entries."""
    return WorkItemTiming(
        work_id=work_id,
        instance_id="compute-1",
        entries=entries,
        issue_id=issue_id,
        issue_title=issue_title,
        project_id=project_id,
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


class TestToolUseAggregateStats:
    """Tests for TOOL_USE per-tool aggregate breakdown."""

    @pytest.fixture
    def service(self):
        return TimingService(redis_client=None)

    @pytest.mark.asyncio
    async def test_tool_use_broken_out_by_tool_name(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 50.0, "Read"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 100.0, "Read"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 4200.0, "Bash"),
        )

        stats = await service.get_aggregate_stats(limit=10)
        tool_stats = [s for s in stats if s.phase == TimingPhase.TOOL_USE]
        assert len(tool_stats) == 2

        bash_stat = next(s for s in tool_stats if s.tool_name == "Bash")
        assert bash_stat.count == 1
        assert bash_stat.avg_ms == 4200.0

        read_stat = next(s for s in tool_stats if s.tool_name == "Read")
        assert read_stat.count == 2
        assert read_stat.avg_ms == 75.0

    @pytest.mark.asyncio
    async def test_tool_use_appears_before_mcp_in_results(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 50.0, "Read"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.MCP_TOOL_CALL, 200.0, "claudevn_get_context"),
        )

        stats = await service.get_aggregate_stats(limit=10)
        phases = [s.phase for s in stats]
        tool_use_idx = phases.index(TimingPhase.TOOL_USE)
        mcp_idx = phases.index(TimingPhase.MCP_TOOL_CALL)
        assert tool_use_idx < mcp_idx

    @pytest.mark.asyncio
    async def test_tool_use_sorted_alphabetically(self, service):
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 100.0, "Write"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 50.0, "Bash"),
        )
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.TOOL_USE, 75.0, "Read"),
        )

        stats = await service.get_aggregate_stats(limit=10)
        tool_names = [s.tool_name for s in stats if s.phase == TimingPhase.TOOL_USE]
        assert tool_names == ["Bash", "Read", "Write"]


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


class TestUpdateSessionMetrics:
    """Tests for update_session_metrics method."""

    @pytest.fixture
    def service(self):
        return TimingService(redis_client=None)

    @pytest.mark.asyncio
    async def test_creates_record_if_not_exists(self, service):
        await service.update_session_metrics(
            work_id="w1", instance_id="c1",
            cost_usd=0.47, input_tokens=142000, output_tokens=18000,
            num_turns=12, session_id="sess-abc",
        )
        timing = await service.get_work_item_timing("w1", "c1")
        assert timing is not None
        assert timing.total_cost_usd == 0.47
        assert timing.input_tokens == 142000
        assert timing.output_tokens == 18000
        assert timing.num_turns == 12
        assert timing.session_id == "sess-abc"

    @pytest.mark.asyncio
    async def test_updates_existing_record(self, service):
        # Create a record with an entry first
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 100.0),
        )
        await service.update_session_metrics(
            work_id="w1", instance_id="c1",
            cost_usd=0.25, num_turns=5,
        )
        timing = await service.get_work_item_timing("w1", "c1")
        assert timing.total_cost_usd == 0.25
        assert timing.num_turns == 5
        assert len(timing.entries) == 1  # Existing entry preserved

    @pytest.mark.asyncio
    async def test_partial_update(self, service):
        await service.update_session_metrics(
            work_id="w1", instance_id="c1",
            cost_usd=0.10,
        )
        timing = await service.get_work_item_timing("w1", "c1")
        assert timing.total_cost_usd == 0.10
        assert timing.input_tokens is None
        assert timing.num_turns is None


class TestDashboardProjectFilter:
    """Tests for project_id filtering in get_dashboard."""

    @pytest.fixture
    def service(self):
        return TimingService(redis_client=None)

    def _seed_items(self, service):
        """Seed service with work items that have project_id set."""
        # Use service's append method to create items, then set project_id
        service._memory_append_entry(
            "w1:c1", "w1", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 100.0),
        )
        service._memory["w1:c1"].project_id = "proj-a"

        service._memory_append_entry(
            "w2:c1", "w2", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 200.0),
        )
        service._memory["w2:c1"].project_id = "proj-a"

        service._memory_append_entry(
            "w3:c1", "w3", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 300.0),
        )
        service._memory["w3:c1"].project_id = "proj-b"

        service._memory_append_entry(
            "w4:c1", "w4", "c1",
            _make_entry(TimingPhase.SDK_LAUNCH, 400.0),
        )

    @pytest.mark.asyncio
    async def test_no_filter_returns_all(self, service):
        self._seed_items(service)
        # Patch out enrichment since items already have project_id set
        with patch.object(service, "_enrich_issue_context", new_callable=AsyncMock):
            result = await service.get_dashboard(limit=10)
        assert len(result.work_items) == 4

    @pytest.mark.asyncio
    async def test_filter_by_project_a(self, service):
        self._seed_items(service)
        with patch.object(service, "_enrich_issue_context", new_callable=AsyncMock):
            result = await service.get_dashboard(limit=10, project_id="proj-a")
        assert len(result.work_items) == 2
        assert all(w.project_id == "proj-a" for w in result.work_items)

    @pytest.mark.asyncio
    async def test_filter_by_project_b(self, service):
        self._seed_items(service)
        with patch.object(service, "_enrich_issue_context", new_callable=AsyncMock):
            result = await service.get_dashboard(limit=10, project_id="proj-b")
        assert len(result.work_items) == 1
        assert result.work_items[0].work_id == "w3"

    @pytest.mark.asyncio
    async def test_filter_nonexistent_project_returns_empty(self, service):
        self._seed_items(service)
        with patch.object(service, "_enrich_issue_context", new_callable=AsyncMock):
            result = await service.get_dashboard(limit=10, project_id="proj-z")
        assert len(result.work_items) == 0
        assert result.total_work_items == 0

    @pytest.mark.asyncio
    async def test_aggregates_scoped_to_filtered_items(self, service):
        self._seed_items(service)
        with patch.object(service, "_enrich_issue_context", new_callable=AsyncMock):
            result = await service.get_dashboard(limit=10, project_id="proj-a")
        # Aggregates should only be from proj-a items (100ms and 200ms)
        sdk_stats = [a for a in result.aggregates if a.phase == TimingPhase.SDK_LAUNCH]
        assert len(sdk_stats) == 1
        assert sdk_stats[0].count == 2
        assert sdk_stats[0].avg_ms == 150.0

    @pytest.mark.asyncio
    async def test_enrichment_sets_project_id(self, service):
        """Test that _enrich_issue_context populates project_id from work_map_service."""
        item = _make_work_item("w1", [])
        assert item.project_id is None

        mock_work = MagicMock()
        mock_work.issue_id = "issue-1"
        mock_work.title = "Test issue"
        mock_work.project_id = "proj-x"

        mock_wm_service = AsyncMock()
        mock_wm_service.get_work = AsyncMock(return_value=mock_work)

        with patch(
            "services.work_map_service.get_work_map_service",
            return_value=mock_wm_service,
        ):
            await service._enrich_issue_context([item])

        assert item.project_id == "proj-x"
        assert item.issue_id == "issue-1"
