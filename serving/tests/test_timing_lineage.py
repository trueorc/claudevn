"""Unit tests for timing lineage enrichment and project summary (#122)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.timing import (
    ProjectTimingSummary,
    TimingEntry,
    TimingPhase,
    WorkItemTiming,
)
from services.timing_service import TimingService


# =========================================================================
# Fixtures
# =========================================================================


def _make_timing(work_id, issue_id=None, goal_id=None, directive_id=None, wall_ms=1000):
    """Create a WorkItemTiming with optional lineage fields and a wall time entry."""
    entries = [
        TimingEntry(
            phase=TimingPhase.TOTAL_WALL_TIME,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration_ms=wall_ms,
        ),
        TimingEntry(
            phase=TimingPhase.MCP_TOOL_CALL,
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration_ms=200,
            metadata={"tool_name": "claudevn_get_context"},
        ),
    ]
    return WorkItemTiming(
        work_id=work_id,
        instance_id="compute-1",
        entries=entries,
        issue_id=issue_id,
        goal_id=goal_id,
        directive_id=directive_id,
    )


# =========================================================================
# ProjectTimingSummary tests
# =========================================================================


class TestComputeProjectSummary:
    """Tests for TimingService._compute_project_summary."""

    def test_empty_work_items(self):
        summary = TimingService._compute_project_summary([], 0)
        assert summary.total_duration_ms == 0.0
        assert summary.directive_count == 0
        assert summary.issue_count == 0
        assert summary.timing_event_count == 0
        assert summary.work_item_count == 0

    def test_counts_unique_directives_and_issues(self):
        items = [
            _make_timing("w1", issue_id="i-1", directive_id="d-1"),
            _make_timing("w2", issue_id="i-1", directive_id="d-1"),
            _make_timing("w3", issue_id="i-2", directive_id="d-2"),
            _make_timing("w4"),  # no issue or directive
        ]
        summary = TimingService._compute_project_summary(items, 10)
        assert summary.directive_count == 2
        assert summary.issue_count == 2
        assert summary.work_item_count == 10

    def test_sums_wall_time(self):
        items = [
            _make_timing("w1", wall_ms=5000),
            _make_timing("w2", wall_ms=3000),
        ]
        summary = TimingService._compute_project_summary(items, 2)
        assert summary.total_duration_ms == 8000.0

    def test_counts_all_timing_entries(self):
        items = [
            _make_timing("w1"),  # 2 entries (wall + mcp_tool_call)
            _make_timing("w2"),  # 2 entries
        ]
        summary = TimingService._compute_project_summary(items, 2)
        assert summary.timing_event_count == 4


# =========================================================================
# Lineage enrichment tests
# =========================================================================


class TestEnrichIssueContext:
    """Tests for TimingService._enrich_issue_context lineage chain."""

    @pytest.mark.asyncio
    async def test_resolves_issue_from_work(self):
        """work_id -> issue_id via work map service."""
        service = TimingService()
        item = _make_timing("w1")

        mock_work = MagicMock()
        mock_work.issue_id = "i-42"
        mock_work.title = "Fix bug"

        mock_wm = AsyncMock()
        mock_wm.get_work = AsyncMock(return_value=mock_work)
        mock_wm.get_issue = AsyncMock(return_value=None)

        with patch("services.work_map_service.get_work_map_service", return_value=mock_wm):
            await service._enrich_issue_context([item])

        assert item.issue_id == "i-42"
        assert item.issue_title == "Fix bug"

    @pytest.mark.asyncio
    async def test_resolves_goal_from_issue(self):
        """issue_id -> goal_id via work map service."""
        service = TimingService()
        item = _make_timing("w1", issue_id="i-42")

        mock_issue = MagicMock()
        mock_issue.goal_id = "g-100"

        mock_wm = AsyncMock()
        mock_wm.get_issue = AsyncMock(return_value=mock_issue)

        mock_goal = MagicMock()
        mock_goal.directive_id = None
        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)

        with patch("services.work_map_service.get_work_map_service", return_value=mock_wm):
            with patch("services.goal_service.get_goal_service", return_value=mock_goal_service):
                await service._enrich_issue_context([item])

        assert item.goal_id == "g-100"

    @pytest.mark.asyncio
    async def test_resolves_directive_from_goal(self):
        """goal_id -> directive_id via goal service."""
        service = TimingService()
        item = _make_timing("w1", issue_id="i-42", goal_id="g-100")

        mock_wm = AsyncMock()
        mock_wm.get_issue = AsyncMock(return_value=None)

        mock_goal = MagicMock()
        mock_goal.directive_id = "d-50"
        mock_goal.project_id = "proj-1"

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)

        mock_directive = MagicMock()
        mock_directive.text = "Build the authentication system"

        mock_uds = AsyncMock()
        mock_uds.get_directive = AsyncMock(return_value=mock_directive)

        with patch("services.work_map_service.get_work_map_service", return_value=mock_wm):
            with patch("services.goal_service.get_goal_service", return_value=mock_goal_service):
                with patch(
                    "services.unified_directive_service.get_unified_directive_service",
                    return_value=mock_uds,
                ):
                    await service._enrich_issue_context([item])

        assert item.directive_id == "d-50"
        assert item.directive_text == "Build the authentication system"

    @pytest.mark.asyncio
    async def test_skips_already_enriched_items(self):
        """Items with existing issue_id should not re-query work map."""
        service = TimingService()
        item = _make_timing("w1", issue_id="i-42", goal_id="g-100", directive_id="d-50")

        mock_wm = AsyncMock()
        mock_wm.get_work = AsyncMock()
        mock_wm.get_issue = AsyncMock()

        with patch("services.work_map_service.get_work_map_service", return_value=mock_wm):
            await service._enrich_issue_context([item])

        mock_wm.get_work.assert_not_called()
        mock_wm.get_issue.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_work_map_service(self):
        """Should not crash when work map service is unavailable."""
        service = TimingService()
        item = _make_timing("w1")

        with patch(
            "services.work_map_service.get_work_map_service",
            side_effect=RuntimeError("not init"),
        ):
            await service._enrich_issue_context([item])

        assert item.issue_id is None

    @pytest.mark.asyncio
    async def test_caches_issue_lookups(self):
        """Multiple items with same issue_id should reuse cached issue."""
        service = TimingService()
        items = [
            _make_timing("w1", issue_id="i-42"),
            _make_timing("w2", issue_id="i-42"),
        ]

        mock_issue = MagicMock()
        mock_issue.goal_id = "g-100"

        mock_wm = AsyncMock()
        mock_wm.get_issue = AsyncMock(return_value=mock_issue)

        mock_goal = MagicMock()
        mock_goal.directive_id = None
        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)

        with patch("services.work_map_service.get_work_map_service", return_value=mock_wm):
            with patch("services.goal_service.get_goal_service", return_value=mock_goal_service):
                await service._enrich_issue_context(items)

        # get_issue should be called only once (cached)
        assert mock_wm.get_issue.call_count == 1
        assert items[0].goal_id == "g-100"
        assert items[1].goal_id == "g-100"

    @pytest.mark.asyncio
    async def test_truncates_long_directive_text(self):
        """Directive text longer than 120 chars should be truncated."""
        service = TimingService()
        item = _make_timing("w1", issue_id="i-42", goal_id="g-100")

        mock_wm = AsyncMock()
        mock_wm.get_issue = AsyncMock(return_value=None)

        mock_goal = MagicMock()
        mock_goal.directive_id = "d-50"
        mock_goal.project_id = "proj-1"

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)

        long_text = "A" * 200
        mock_directive = MagicMock()
        mock_directive.text = long_text

        mock_uds = AsyncMock()
        mock_uds.get_directive = AsyncMock(return_value=mock_directive)

        with patch("services.work_map_service.get_work_map_service", return_value=mock_wm):
            with patch("services.goal_service.get_goal_service", return_value=mock_goal_service):
                with patch(
                    "services.unified_directive_service.get_unified_directive_service",
                    return_value=mock_uds,
                ):
                    await service._enrich_issue_context([item])

        assert len(item.directive_text) == 123  # 120 + "..."
        assert item.directive_text.endswith("...")
