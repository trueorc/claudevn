"""Tests for SystemIntegrityMonitor."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from services.system_integrity_monitor import (
    SystemIntegrityMonitor,
    AnomalyResult,
    COOLDOWNS,
    ESCALATION_THRESHOLD,
)


# Patch targets — lazy imports inside methods resolve from the source module
WM_PATCH = "services.work_map_service.get_work_map_service"
PR_PATCH = "api.git.get_pr_service"
SSE_PATCH = "services.sse_connection_manager.get_sse_connection_manager"
NOTIF_PATCH = "services.notification_service.get_notification_service"
DISPATCH_PATCH = "services.work_dispatcher.get_work_dispatcher"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeWorkItem:
    work_id: str
    status: object
    branch_name: str = ""
    project_id: str = "proj_test"
    assigned_to: str = None
    issue_id: str = "issue_1"
    progress_percent: int = 0
    last_activity_at: datetime = None


@dataclass
class FakeIssue:
    issue_id: str
    status: object
    project_id: str = "proj_test"
    goal_id: str = "goal_1"


@dataclass
class FakeGoal:
    goal_id: str
    status: object
    project_id: str = "proj_test"


@dataclass
class FakePR:
    branch: str
    status: object
    updated_at: datetime = None


@dataclass
class FakeListResult:
    items: list


@dataclass
class FakeSSEConnection:
    compute_id: str
    status: str = "idle"


# ---------------------------------------------------------------------------
# Lifecycle Tests
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_init_defaults(self):
        monitor = SystemIntegrityMonitor()
        assert monitor.check_interval == 60
        assert not monitor.is_running()
        assert monitor.get_stats()["cycles"] == 0

    def test_custom_interval(self):
        monitor = SystemIntegrityMonitor(check_interval=30)
        assert monitor.check_interval == 30

    @pytest.mark.asyncio
    async def test_start_stop(self):
        monitor = SystemIntegrityMonitor(check_interval=9999)
        await monitor.start()
        assert monitor.is_running()
        await monitor.stop()
        assert not monitor.is_running()

    @pytest.mark.asyncio
    async def test_double_start(self):
        monitor = SystemIntegrityMonitor(check_interval=9999)
        await monitor.start()
        await monitor.start()  # Should not error
        assert monitor.is_running()
        await monitor.stop()


# ---------------------------------------------------------------------------
# Throttling Tests
# ---------------------------------------------------------------------------

class TestThrottling:
    def test_first_attempt_not_throttled(self):
        monitor = SystemIntegrityMonitor()
        assert not monitor._should_throttle("merged:w1", "merged_not_finalized")

    def test_throttled_within_cooldown(self):
        monitor = SystemIntegrityMonitor()
        monitor._record_attempt("merged:w1")
        assert monitor._should_throttle("merged:w1", "merged_not_finalized")

    def test_not_throttled_after_cooldown(self):
        monitor = SystemIntegrityMonitor()
        monitor._record_attempt("merged:w1")
        monitor._attempt_tracker["merged:w1"]["last_attempt"] = (
            datetime.now(timezone.utc) - timedelta(seconds=COOLDOWNS["merged_not_finalized"] + 1)
        )
        assert not monitor._should_throttle("merged:w1", "merged_not_finalized")

    def test_attempt_count_increments(self):
        monitor = SystemIntegrityMonitor()
        monitor._record_attempt("key1")
        monitor._record_attempt("key1")
        monitor._record_attempt("key1")
        assert monitor._attempt_tracker["key1"]["attempt_count"] == 3

    def test_cleanup_removes_stale_entries(self):
        monitor = SystemIntegrityMonitor()
        monitor._record_attempt("old_key")
        # 2000s > 1800s threshold → should be cleaned
        monitor._attempt_tracker["old_key"]["last_attempt"] = (
            datetime.now(timezone.utc) - timedelta(seconds=2000)
        )
        monitor._cleanup_tracker()
        assert "old_key" not in monitor._attempt_tracker

    def test_cleanup_keeps_recent_entries(self):
        monitor = SystemIntegrityMonitor()
        monitor._record_attempt("recent_key")
        # 60s < 1800s threshold → should stay
        monitor._attempt_tracker["recent_key"]["last_attempt"] = (
            datetime.now(timezone.utc) - timedelta(seconds=60)
        )
        monitor._cleanup_tracker()
        assert "recent_key" in monitor._attempt_tracker


# ---------------------------------------------------------------------------
# Notification Tests
# ---------------------------------------------------------------------------

class TestNotification:
    def test_success_notification(self):
        monitor = SystemIntegrityMonitor()
        anomaly = AnomalyResult(
            check_type="merged_not_finalized",
            entity_type="work",
            entity_id="w1",
            project_id="proj_test",
            description="Work w1 auto-finalized",
            remediation_action="finalize_work",
        )

        with patch(NOTIF_PATCH) as mock_get:
            mock_svc = MagicMock()
            mock_get.return_value = mock_svc
            monitor._notify_success(anomaly)
            mock_svc.emit.assert_called_once()
            from models.notification import NotificationLevel
            call_kwargs = mock_svc.emit.call_args
            assert call_kwargs.kwargs.get("level") == NotificationLevel.SUCCESS

    def test_failure_warning_below_threshold(self):
        monitor = SystemIntegrityMonitor()
        anomaly = AnomalyResult(
            check_type="stuck_goal",
            entity_type="goal",
            entity_id="g1",
            project_id="proj_test",
            description="Goal stuck",
            remediation_action=None,
        )

        with patch(NOTIF_PATCH) as mock_get:
            mock_svc = MagicMock()
            mock_get.return_value = mock_svc
            monitor._notify_failure(anomaly, consecutive=1)
            mock_svc.emit.assert_called_once()
            from models.notification import NotificationLevel
            call_kwargs = mock_svc.emit.call_args
            assert call_kwargs.kwargs.get("level") == NotificationLevel.WARNING
            assert "Will retry" in call_kwargs.kwargs.get("message", "")

    def test_failure_error_at_threshold(self):
        monitor = SystemIntegrityMonitor()
        anomaly = AnomalyResult(
            check_type="stuck_goal",
            entity_type="goal",
            entity_id="g1",
            project_id="proj_test",
            description="Goal stuck",
            remediation_action=None,
        )

        with patch(NOTIF_PATCH) as mock_get:
            mock_svc = MagicMock()
            mock_get.return_value = mock_svc
            monitor._notify_failure(anomaly, consecutive=ESCALATION_THRESHOLD)
            mock_svc.emit.assert_called_once()
            from models.notification import NotificationLevel
            call_kwargs = mock_svc.emit.call_args
            assert call_kwargs.kwargs.get("level") == NotificationLevel.ERROR
            assert "Manual intervention" in call_kwargs.kwargs.get("message", "")


# ---------------------------------------------------------------------------
# Check 1: Merged Not Finalized
# ---------------------------------------------------------------------------

class TestMergedNotFinalized:
    @pytest.mark.asyncio
    async def test_detects_merged_branch_with_active_work(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import WorkStatus
        from git.pr_service import PRStatus

        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.IN_PROGRESS,
            branch_name="f/issue_123", project_id="proj_a",
        )
        fake_pr = FakePR(branch="f/issue_123", status=PRStatus.MERGED)

        async def list_work_by_status(status=None, **kwargs):
            if status == WorkStatus.IN_PROGRESS:
                return FakeListResult(items=[fake_work])
            return FakeListResult(items=[])

        mock_wm = AsyncMock()
        mock_wm.list_work = AsyncMock(side_effect=list_work_by_status)

        mock_pr_svc = AsyncMock()
        mock_pr_svc.get_pr = AsyncMock(return_value=fake_pr)

        with patch(WM_PATCH, return_value=mock_wm), \
             patch(PR_PATCH, return_value=mock_pr_svc):
            results = await monitor._check_merged_not_finalized()

        assert len(results) == 1
        assert results[0].check_type == "merged_not_finalized"
        assert results[0].entity_id == "w1"
        assert results[0].remediation_action == "finalize_work"

    @pytest.mark.asyncio
    async def test_no_anomaly_when_pr_not_merged(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import WorkStatus
        from git.pr_service import PRStatus

        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.IN_PROGRESS,
            branch_name="f/issue_123", project_id="proj_a",
        )
        fake_pr = FakePR(branch="f/issue_123", status=PRStatus.IN_REVIEW)

        async def list_work_by_status(status=None, **kwargs):
            if status == WorkStatus.IN_PROGRESS:
                return FakeListResult(items=[fake_work])
            return FakeListResult(items=[])

        mock_wm = AsyncMock()
        mock_wm.list_work = AsyncMock(side_effect=list_work_by_status)

        mock_pr_svc = AsyncMock()
        mock_pr_svc.get_pr = AsyncMock(return_value=fake_pr)

        with patch(WM_PATCH, return_value=mock_wm), \
             patch(PR_PATCH, return_value=mock_pr_svc):
            results = await monitor._check_merged_not_finalized()

        assert len(results) == 0


# ---------------------------------------------------------------------------
# Check 2: Stuck Issues
# ---------------------------------------------------------------------------

class TestStuckIssues:
    @pytest.mark.asyncio
    async def test_detects_issue_with_all_work_completed(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import IssueStatus, WorkStatus

        fake_issue = FakeIssue(issue_id="issue_1", status=IssueStatus.IN_PROGRESS)
        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.COMPLETED, issue_id="issue_1"
        )

        async def list_issues_by_status(status=None, **kwargs):
            if status == IssueStatus.IN_PROGRESS:
                return FakeListResult(items=[fake_issue])
            return FakeListResult(items=[])

        mock_wm = AsyncMock()
        mock_wm.list_issues = AsyncMock(side_effect=list_issues_by_status)
        mock_wm._work_items = {"w1": fake_work}

        with patch(WM_PATCH, return_value=mock_wm):
            results = await monitor._check_stuck_issues()

        assert len(results) == 1
        assert results[0].check_type == "stuck_issue"
        assert results[0].remediation_action == "finalize_issue"

    @pytest.mark.asyncio
    async def test_no_anomaly_when_work_still_active(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import IssueStatus, WorkStatus

        fake_issue = FakeIssue(issue_id="issue_1", status=IssueStatus.IN_PROGRESS)
        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.IN_PROGRESS, issue_id="issue_1"
        )

        async def list_issues_by_status(status=None, **kwargs):
            if status == IssueStatus.IN_PROGRESS:
                return FakeListResult(items=[fake_issue])
            return FakeListResult(items=[])

        mock_wm = AsyncMock()
        mock_wm.list_issues = AsyncMock(side_effect=list_issues_by_status)
        mock_wm._work_items = {"w1": fake_work}

        with patch(WM_PATCH, return_value=mock_wm):
            results = await monitor._check_stuck_issues()

        assert len(results) == 0


# ---------------------------------------------------------------------------
# Check 3: Stuck Goals
# ---------------------------------------------------------------------------

class TestStuckGoals:
    @pytest.mark.asyncio
    async def test_detects_goal_with_all_issues_done(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import GoalStatus, IssueStatus

        fake_goal = FakeGoal(goal_id="goal_1", status=GoalStatus.IN_PROGRESS)
        fake_issues = [
            FakeIssue(issue_id="i1", status=IssueStatus.DONE),
            FakeIssue(issue_id="i2", status=IssueStatus.DONE),
        ]

        mock_wm = AsyncMock()
        mock_wm.list_goals = AsyncMock(
            return_value=FakeListResult(items=[fake_goal])
        )
        mock_wm.get_goal_issues = AsyncMock(return_value=fake_issues)

        with patch(WM_PATCH, return_value=mock_wm):
            results = await monitor._check_stuck_goals()

        assert len(results) == 1
        assert results[0].check_type == "stuck_goal"
        assert results[0].remediation_action == "check_goal_completion"

    @pytest.mark.asyncio
    async def test_no_anomaly_when_issues_not_all_done(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import GoalStatus, IssueStatus

        fake_goal = FakeGoal(goal_id="goal_1", status=GoalStatus.IN_PROGRESS)
        fake_issues = [
            FakeIssue(issue_id="i1", status=IssueStatus.DONE),
            FakeIssue(issue_id="i2", status=IssueStatus.IN_PROGRESS),
        ]

        mock_wm = AsyncMock()
        mock_wm.list_goals = AsyncMock(
            return_value=FakeListResult(items=[fake_goal])
        )
        mock_wm.get_goal_issues = AsyncMock(return_value=fake_issues)

        with patch(WM_PATCH, return_value=mock_wm):
            results = await monitor._check_stuck_goals()

        assert len(results) == 0


# ---------------------------------------------------------------------------
# Check 6: Pipeline Stall
# ---------------------------------------------------------------------------

class TestPipelineStall:
    @pytest.mark.asyncio
    async def test_detects_pending_work_with_idle_computes(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import WorkStatus

        fake_work = FakeWorkItem(work_id="w1", status=WorkStatus.PENDING)

        mock_wm = AsyncMock()
        mock_wm.list_work = AsyncMock(
            return_value=FakeListResult(items=[fake_work])
        )

        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [
            FakeSSEConnection(compute_id="c1", status="idle")
        ]

        with patch(WM_PATCH, return_value=mock_wm), \
             patch(SSE_PATCH, return_value=mock_sse):
            results = await monitor._check_pipeline_stall()

        assert len(results) == 1
        assert results[0].check_type == "pipeline_stall"
        assert results[0].remediation_action == "trigger_dispatch"

    @pytest.mark.asyncio
    async def test_no_stall_when_no_idle_computes(self):
        monitor = SystemIntegrityMonitor()

        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [
            FakeSSEConnection(compute_id="c1", status="busy")
        ]

        with patch(SSE_PATCH, return_value=mock_sse):
            results = await monitor._check_pipeline_stall()

        assert len(results) == 0


# ---------------------------------------------------------------------------
# Check 7: Orphaned Work
# ---------------------------------------------------------------------------

class TestOrphanedWork:
    @pytest.mark.asyncio
    async def test_detects_work_on_disconnected_compute(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import WorkStatus

        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.IN_PROGRESS,
            assigned_to="dead-compute-001",
        )

        async def list_work_by_status(status=None, **kwargs):
            if status == WorkStatus.IN_PROGRESS:
                return FakeListResult(items=[fake_work])
            return FakeListResult(items=[])

        mock_wm = AsyncMock()
        mock_wm.list_work = AsyncMock(side_effect=list_work_by_status)

        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [
            FakeSSEConnection(compute_id="alive-compute-001", status="idle")
        ]

        with patch(WM_PATCH, return_value=mock_wm), \
             patch(SSE_PATCH, return_value=mock_sse):
            results = await monitor._check_orphaned_work()

        assert len(results) == 1
        assert results[0].check_type == "orphaned_work"
        assert results[0].remediation_action == "requeue_orphaned"

    @pytest.mark.asyncio
    async def test_no_orphan_when_compute_connected(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import WorkStatus

        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.IN_PROGRESS,
            assigned_to="c1",
        )

        async def list_work_by_status(status=None, **kwargs):
            if status == WorkStatus.IN_PROGRESS:
                return FakeListResult(items=[fake_work])
            return FakeListResult(items=[])

        mock_wm = AsyncMock()
        mock_wm.list_work = AsyncMock(side_effect=list_work_by_status)

        mock_sse = MagicMock()
        mock_sse.list_connections.return_value = [
            FakeSSEConnection(compute_id="c1", status="busy")
        ]

        with patch(WM_PATCH, return_value=mock_wm), \
             patch(SSE_PATCH, return_value=mock_sse):
            results = await monitor._check_orphaned_work()

        assert len(results) == 0


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_structure(self):
        monitor = SystemIntegrityMonitor()
        stats = monitor.get_stats()
        assert stats["cycles"] == 0
        assert stats["running"] is False
        assert "by_check_type" in stats
        assert "merged_not_finalized" in stats["by_check_type"]
        assert "orphaned_work" in stats["by_check_type"]


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------

class TestRemediation:
    @pytest.mark.asyncio
    async def test_finalize_work_remediation(self):
        monitor = SystemIntegrityMonitor()

        from models.work_map import WorkStatus

        fake_work = FakeWorkItem(
            work_id="w1", status=WorkStatus.IMPLEMENTED,
        )

        mock_wm = AsyncMock()
        mock_wm._work_items = {"w1": fake_work}
        mock_wm.finalize_work = AsyncMock(return_value=fake_work)

        anomaly = AnomalyResult(
            check_type="merged_not_finalized",
            entity_type="work",
            entity_id="w1",
            project_id="proj_test",
            description="test",
            remediation_action="finalize_work",
            context={"branch": "f/test"},
        )

        with patch(WM_PATCH, return_value=mock_wm):
            success = await monitor._attempt_remediation(anomaly)

        assert success
        mock_wm.finalize_work.assert_awaited_once_with("w1")

    @pytest.mark.asyncio
    async def test_trigger_dispatch_remediation(self):
        monitor = SystemIntegrityMonitor()

        mock_dispatcher = MagicMock()

        anomaly = AnomalyResult(
            check_type="pipeline_stall",
            entity_type="system",
            entity_id="stall",
            project_id=None,
            description="test",
            remediation_action="trigger_dispatch",
        )

        with patch(DISPATCH_PATCH, return_value=mock_dispatcher):
            success = await monitor._attempt_remediation(anomaly)

        assert success
        mock_dispatcher.trigger.assert_called_once_with(reason="integrity_pipeline_stall")
