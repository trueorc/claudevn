"""Tests for timing models."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from models.timing import (
    TimingPhase,
    TimingEntry,
    WorkItemTiming,
    AggregateStats,
    TimingDashboardResponse,
)


class TestTimingPhase:
    """Test TimingPhase enum."""

    def test_enum_values(self):
        assert TimingPhase.WORKSPACE_SETUP == "workspace_setup"
        assert TimingPhase.REPO_CLONE == "repo_clone"
        assert TimingPhase.SDK_LAUNCH == "sdk_launch"
        assert TimingPhase.MCP_TOOL_CALL == "mcp_tool_call"
        assert TimingPhase.API_INFERENCE == "api_inference"
        assert TimingPhase.GIT_PUSH == "git_push"
        assert TimingPhase.TOTAL_WALL_TIME == "total_wall_time"

    def test_all_phases_exist(self):
        assert len(TimingPhase) == 9


class TestTimingEntry:
    """Test TimingEntry model."""

    def test_create_minimal(self):
        entry = TimingEntry(
            phase=TimingPhase.WORKSPACE_SETUP,
            start=datetime.now(timezone.utc),
        )
        assert entry.phase == TimingPhase.WORKSPACE_SETUP
        assert entry.end is None
        assert entry.duration_ms is None
        assert entry.metadata == {}

    def test_create_complete(self):
        start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        entry = TimingEntry(
            phase=TimingPhase.REPO_CLONE,
            start=start,
            end=end,
            duration_ms=5000.0,
            metadata={"repo_url": "http://example.com"},
        )
        assert entry.duration_ms == 5000.0
        assert entry.metadata["repo_url"] == "http://example.com"

    def test_requires_phase_and_start(self):
        with pytest.raises(ValidationError):
            TimingEntry(phase=TimingPhase.SDK_LAUNCH)


class TestWorkItemTiming:
    """Test WorkItemTiming model."""

    def test_create_minimal(self):
        timing = WorkItemTiming(
            work_id="work-1",
            instance_id="compute-1",
        )
        assert timing.work_id == "work-1"
        assert timing.instance_id == "compute-1"
        assert timing.entries == []
        assert timing.created_at is not None

    def test_with_entries(self):
        entry = TimingEntry(
            phase=TimingPhase.WORKSPACE_SETUP,
            start=datetime.now(timezone.utc),
            duration_ms=100.0,
        )
        timing = WorkItemTiming(
            work_id="work-1",
            instance_id="compute-1",
            entries=[entry],
        )
        assert len(timing.entries) == 1
        assert timing.entries[0].phase == TimingPhase.WORKSPACE_SETUP


class TestAggregateStats:
    """Test AggregateStats model."""

    def test_create(self):
        stats = AggregateStats(
            phase=TimingPhase.SDK_LAUNCH,
            count=10,
            avg_ms=500.0,
            p50_ms=450.0,
            p95_ms=900.0,
            p99_ms=950.0,
            min_ms=100.0,
            max_ms=1000.0,
        )
        assert stats.count == 10
        assert stats.avg_ms == 500.0

    def test_defaults(self):
        stats = AggregateStats(phase=TimingPhase.GIT_PUSH)
        assert stats.count == 0
        assert stats.avg_ms == 0.0


class TestTimingDashboardResponse:
    """Test TimingDashboardResponse model."""

    def test_empty(self):
        resp = TimingDashboardResponse()
        assert resp.work_items == []
        assert resp.aggregates == []
        assert resp.total_work_items == 0

    def test_with_data(self):
        timing = WorkItemTiming(work_id="w1", instance_id="c1")
        stats = AggregateStats(phase=TimingPhase.SDK_LAUNCH, count=5)
        resp = TimingDashboardResponse(
            work_items=[timing],
            aggregates=[stats],
            total_work_items=1,
        )
        assert len(resp.work_items) == 1
        assert len(resp.aggregates) == 1
        assert resp.total_work_items == 1
