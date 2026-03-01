"""Tests for timing service (in-memory mode)."""

import pytest
from datetime import datetime, timezone, timedelta

from models.timing import TimingPhase
from services.timing_service import TimingService


@pytest.fixture
def service():
    """Create a TimingService with in-memory storage."""
    return TimingService(redis_client=None)


class TestTimingServiceInit:
    """Test TimingService initialization."""

    def test_init_no_redis(self):
        svc = TimingService()
        assert svc._redis is None
        assert svc._memory == {}

    def test_init_with_redis(self):
        svc = TimingService(redis_client="fake")
        assert svc._redis == "fake"


class TestRecordPhase:
    """Test recording complete phases."""

    @pytest.mark.asyncio
    async def test_record_phase(self, service):
        start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.WORKSPACE_SETUP,
            start, end, {"key": "value"}
        )

        timing = await service.get_work_item_timing("work-1", "compute-1")
        assert timing is not None
        assert timing.work_id == "work-1"
        assert timing.instance_id == "compute-1"
        assert len(timing.entries) == 1
        assert timing.entries[0].phase == TimingPhase.WORKSPACE_SETUP
        assert timing.entries[0].duration_ms == 5000.0
        assert timing.entries[0].metadata["key"] == "value"

    @pytest.mark.asyncio
    async def test_record_multiple_phases(self, service):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.WORKSPACE_SETUP,
            base, base + timedelta(seconds=2)
        )
        await service.record_phase(
            "work-1", "compute-1", TimingPhase.REPO_CLONE,
            base + timedelta(seconds=2), base + timedelta(seconds=8)
        )
        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base + timedelta(seconds=8), base + timedelta(seconds=10)
        )

        timing = await service.get_work_item_timing("work-1", "compute-1")
        assert len(timing.entries) == 3
        assert timing.entries[0].duration_ms == 2000.0
        assert timing.entries[1].duration_ms == 6000.0
        assert timing.entries[2].duration_ms == 2000.0


class TestStartEnd:
    """Test start/end phase recording."""

    @pytest.mark.asyncio
    async def test_start_and_end(self, service):
        await service.record_phase_start(
            "work-1", "compute-1", TimingPhase.TOTAL_WALL_TIME
        )
        await service.record_phase_end(
            "work-1", "compute-1", TimingPhase.TOTAL_WALL_TIME
        )

        timing = await service.get_work_item_timing("work-1", "compute-1")
        assert len(timing.entries) == 1
        assert timing.entries[0].end is not None
        assert timing.entries[0].duration_ms is not None
        assert timing.entries[0].duration_ms >= 0

    @pytest.mark.asyncio
    async def test_end_without_start(self, service):
        await service.record_phase_end(
            "work-1", "compute-1", TimingPhase.GIT_PUSH
        )

        timing = await service.get_work_item_timing("work-1", "compute-1")
        assert len(timing.entries) == 1
        assert timing.entries[0].duration_ms == 0.0


class TestRecentTimings:
    """Test recent timings retrieval."""

    @pytest.mark.asyncio
    async def test_get_recent_empty(self, service):
        result = await service.get_recent_timings()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_ordering(self, service):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        for i in range(5):
            await service.record_phase(
                f"work-{i}", "compute-1", TimingPhase.SDK_LAUNCH,
                base, base + timedelta(seconds=i + 1)
            )

        result = await service.get_recent_timings(limit=3)
        assert len(result) == 3
        # Most recent first
        assert result[0].work_id == "work-4"
        assert result[1].work_id == "work-3"
        assert result[2].work_id == "work-2"

    @pytest.mark.asyncio
    async def test_get_recent_limit(self, service):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            await service.record_phase(
                f"work-{i}", "compute-1", TimingPhase.SDK_LAUNCH,
                base, base + timedelta(seconds=1)
            )

        result = await service.get_recent_timings(limit=3)
        assert len(result) == 3


class TestAggregateStats:
    """Test aggregate statistics computation."""

    @pytest.mark.asyncio
    async def test_aggregate_empty(self, service):
        result = await service.get_aggregate_stats()
        assert result == []

    @pytest.mark.asyncio
    async def test_aggregate_single_phase(self, service):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=1)
        )
        await service.record_phase(
            "work-2", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=3)
        )
        await service.record_phase(
            "work-3", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=2)
        )

        result = await service.get_aggregate_stats()
        assert len(result) == 1
        assert result[0].phase == TimingPhase.SDK_LAUNCH
        assert result[0].count == 3
        assert result[0].avg_ms == 2000.0
        assert result[0].min_ms == 1000.0
        assert result[0].max_ms == 3000.0

    @pytest.mark.asyncio
    async def test_aggregate_multiple_phases(self, service):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.WORKSPACE_SETUP,
            base, base + timedelta(seconds=1)
        )
        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base + timedelta(seconds=1), base + timedelta(seconds=5)
        )

        result = await service.get_aggregate_stats()
        phases = {s.phase for s in result}
        assert TimingPhase.WORKSPACE_SETUP in phases
        assert TimingPhase.SDK_LAUNCH in phases


class TestDashboard:
    """Test dashboard response."""

    @pytest.mark.asyncio
    async def test_empty_dashboard(self, service):
        result = await service.get_dashboard()
        assert result.work_items == []
        assert result.aggregates == []
        assert result.total_work_items == 0

    @pytest.mark.asyncio
    async def test_dashboard_with_data(self, service):
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=2)
        )

        result = await service.get_dashboard()
        assert len(result.work_items) == 1
        assert len(result.aggregates) == 1
        assert result.total_work_items == 1


class TestIssueContext:
    """Test issue context fields on WorkItemTiming."""

    @pytest.mark.asyncio
    async def test_work_item_timing_has_issue_fields(self, service):
        """WorkItemTiming should have optional issue_id and issue_title."""
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=2)
        )

        timing = await service.get_work_item_timing("work-1", "compute-1")
        assert timing.issue_id is None
        assert timing.issue_title is None

    @pytest.mark.asyncio
    async def test_dashboard_without_work_map_service(self, service):
        """Dashboard should work when work map service is not available."""
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=2)
        )

        result = await service.get_dashboard()
        assert len(result.work_items) == 1
        # issue_id should be None when work map service isn't available
        assert result.work_items[0].issue_id is None

    @pytest.mark.asyncio
    async def test_dashboard_enriches_issue_context(self, service, monkeypatch):
        """Dashboard should enrich work items with issue context from work map."""
        from unittest.mock import AsyncMock, MagicMock

        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        await service.record_phase(
            "work-1", "compute-1", TimingPhase.SDK_LAUNCH,
            base, base + timedelta(seconds=2)
        )

        # Mock work map service
        mock_work = MagicMock()
        mock_work.issue_id = "issue-42"
        mock_work.title = "Fix auth bug"

        mock_wm_service = MagicMock()
        mock_wm_service.get_work = AsyncMock(return_value=mock_work)

        import services.timing_service as ts_module
        monkeypatch.setattr(
            "services.work_map_service.get_work_map_service",
            lambda: mock_wm_service
        )

        result = await service.get_dashboard()
        assert result.work_items[0].issue_id == "issue-42"
        assert result.work_items[0].issue_title == "Fix auth bug"


class TestMemoryEviction:
    """Test in-memory storage limits."""

    @pytest.mark.asyncio
    async def test_eviction(self):
        svc = TimingService(redis_client=None)
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Fill beyond MAX_IN_MEMORY_ITEMS (500)
        for i in range(510):
            await svc.record_phase(
                f"work-{i}", "compute-1", TimingPhase.SDK_LAUNCH,
                base, base + timedelta(seconds=1)
            )

        assert len(svc._memory) == 500
        # Oldest items should be evicted
        assert "work-0:compute-1" not in svc._memory
        assert "work-510:compute-1" not in svc._memory  # doesn't exist
        assert "work-509:compute-1" in svc._memory


class TestPercentile:
    """Test percentile calculation."""

    def test_single_value(self):
        assert TimingService._percentile([100.0], 50) == 100.0
        assert TimingService._percentile([100.0], 95) == 100.0

    def test_empty(self):
        assert TimingService._percentile([], 50) == 0.0

    def test_two_values(self):
        result = TimingService._percentile([100.0, 200.0], 50)
        assert result == 150.0

    def test_known_values(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        p50 = TimingService._percentile(data, 50)
        assert 5.0 <= p50 <= 6.0
