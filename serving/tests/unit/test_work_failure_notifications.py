"""Tests for work failure notification emissions (#693).

Verifies that notifications are emitted when work permanently fails:
- Timeout retries exhausted (via work_orchestrator._detect_and_handle_stale_work)
- Retry retries exhausted (via work_orchestrator._retry_failed_work)
- Direct failure (via work_map_service.fail_work_and_update_issue)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.work_orchestrator import WorkOrchestrator, _emit_failure_notification
from models.work_map import WorkItem, WorkStatus, WorkPriority
from models.notification import NotificationLevel, NotificationCategory


@pytest.fixture
def orchestrator():
    """Create an orchestrator for testing."""
    return WorkOrchestrator(
        poll_interval=1,
        max_concurrent_spawns=3,
        max_retries=2,
        retry_delay=5,
        timeout_minutes=30,
        timeout_check_interval=60,
        timeout_max_retries=3,
    )


def _make_work_item(
    work_id="work_test123",
    title="Test Task",
    status=WorkStatus.IN_PROGRESS,
    project_id="proj_abc",
    error=None,
    retry_count=0,
    last_activity_at=None,
):
    """Create a mock work item."""
    item = MagicMock()
    item.work_id = work_id
    item.title = title
    item.status = status
    item.project_id = project_id
    item.error = error
    item.retry_count = retry_count
    item.last_activity_at = last_activity_at or datetime.now(timezone.utc) - timedelta(hours=1)
    item.updated_at = datetime.now(timezone.utc)
    return item


class TestEmitFailureNotification:
    """Tests for the _emit_failure_notification helper."""

    def test_emits_notification_with_correct_fields(self):
        """Test that notification is emitted with correct level, category, and fields."""
        mock_svc = MagicMock()

        with patch("services.notification_service.get_notification_service", return_value=mock_svc):
            _emit_failure_notification(
                work_id="work_abc",
                title="My Task",
                error="Timed out after 3 retries",
                project_id="proj_123",
            )

        mock_svc.emit.assert_called_once_with(
            title="Work failed: My Task",
            message="Timed out after 3 retries",
            level=NotificationLevel.ERROR,
            category=NotificationCategory.WORK,
            project_id="proj_123",
            entity_id="work_abc",
        )

    def test_no_crash_when_notification_service_unavailable(self):
        """Test that missing notification service doesn't raise."""
        with patch(
            "services.notification_service.get_notification_service",
            side_effect=RuntimeError("not initialized"),
        ):
            # Should not raise
            _emit_failure_notification(
                work_id="work_abc",
                title="Task",
                error="error",
            )

    def test_no_crash_when_emit_raises(self):
        """Test that emit() failure doesn't propagate."""
        mock_svc = MagicMock()
        mock_svc.emit.side_effect = Exception("emit error")

        with patch("services.notification_service.get_notification_service", return_value=mock_svc):
            # Should not raise
            _emit_failure_notification(
                work_id="work_abc",
                title="Task",
                error="error",
            )


class TestTimeoutExhaustedNotification:
    """Tests for notification on timeout retry exhaustion."""

    @pytest.mark.asyncio
    async def test_notification_emitted_on_timeout_failure(self, orchestrator):
        """Test that a notification is emitted when work fails after exhausting timeout retries."""
        stale_item = _make_work_item(
            work_id="work_stale",
            title="Stale Task",
            project_id="proj_stale",
        )

        failed_result = _make_work_item(
            work_id="work_stale",
            title="Stale Task",
            status=WorkStatus.FAILED,
            project_id="proj_stale",
            error="Work timed out after 3 retries",
            retry_count=3,
        )

        mock_svc = MagicMock()

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.notification_service.get_notification_service", return_value=mock_svc):
            mock_work_map = MagicMock()
            mock_work_map.get_stale_work = AsyncMock(return_value=[stale_item])
            mock_work_map.get_stale_assigned_work = AsyncMock(return_value=[])
            mock_work_map.mark_work_timed_out = AsyncMock(return_value=failed_result)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._detect_and_handle_stale_work()

        mock_svc.emit.assert_called_once_with(
            title="Work failed: Stale Task",
            message="Work timed out after 3 retries",
            level=NotificationLevel.ERROR,
            category=NotificationCategory.WORK,
            project_id="proj_stale",
            entity_id="work_stale",
        )

    @pytest.mark.asyncio
    async def test_no_notification_when_timeout_retries_remaining(self, orchestrator):
        """Test that no notification is emitted when work is returned to PENDING."""
        stale_item = _make_work_item(work_id="work_retry")

        pending_result = _make_work_item(
            work_id="work_retry",
            status=WorkStatus.PENDING,
            retry_count=1,
        )

        mock_svc = MagicMock()

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.notification_service.get_notification_service", return_value=mock_svc):
            mock_work_map = MagicMock()
            mock_work_map.get_stale_work = AsyncMock(return_value=[stale_item])
            mock_work_map.mark_work_timed_out = AsyncMock(return_value=pending_result)
            mock_get_wms.return_value = mock_work_map

            await orchestrator._detect_and_handle_stale_work()

        mock_svc.emit.assert_not_called()


class TestRetryExhaustedNotification:
    """Tests for notification on retry exhaustion."""

    @pytest.mark.asyncio
    async def test_notification_emitted_on_retry_exhaustion(self, orchestrator):
        """Test that a notification is emitted when retries are exhausted."""
        failed_item = _make_work_item(
            work_id="work_exhausted",
            title="Exhausted Task",
            status=WorkStatus.FAILED,
            project_id="proj_exh",
            retry_count=2,
        )

        still_failed = _make_work_item(
            work_id="work_exhausted",
            title="Exhausted Task",
            status=WorkStatus.FAILED,
            project_id="proj_exh",
            error="Work failed after 2 retry attempts",
            retry_count=3,
        )

        mock_svc = MagicMock()

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.notification_service.get_notification_service", return_value=mock_svc):
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=still_failed)
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

        assert retried == 0
        mock_svc.emit.assert_called_once_with(
            title="Work failed: Exhausted Task",
            message="Work failed after 2 retry attempts",
            level=NotificationLevel.ERROR,
            category=NotificationCategory.WORK,
            project_id="proj_exh",
            entity_id="work_exhausted",
        )

    @pytest.mark.asyncio
    async def test_no_notification_when_retry_succeeds(self, orchestrator):
        """Test that no notification is emitted when retry returns to PENDING."""
        failed_item = _make_work_item(
            work_id="work_retrying",
            status=WorkStatus.FAILED,
            retry_count=0,
        )

        pending_result = _make_work_item(
            work_id="work_retrying",
            status=WorkStatus.PENDING,
            retry_count=1,
        )

        mock_svc = MagicMock()

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.notification_service.get_notification_service", return_value=mock_svc):
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=pending_result)
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

        assert retried == 1
        mock_svc.emit.assert_not_called()


class TestDirectFailureNotification:
    """Tests for notification on direct work failure via fail_work_and_update_issue."""

    @pytest.mark.asyncio
    async def test_notification_emitted_on_direct_failure(self):
        """Test that fail_work_and_update_issue emits a notification."""
        from services.work_map_service import WorkMapService

        mock_assignment = MagicMock()
        mock_assignment.update_status = AsyncMock(return_value=True)
        mock_issue = MagicMock()
        mock_issue.update_issue_status = AsyncMock(return_value=None)

        svc = WorkMapService.__new__(WorkMapService)
        svc._work_items = {}
        svc._assignment_service = mock_assignment
        svc._issue_service = mock_issue
        svc._save_to_redis = AsyncMock()

        work = MagicMock()
        work.work_id = "work_direct"
        work.title = "Direct Fail Task"
        work.project_id = "proj_direct"
        work.error = None
        work.context = {"issue_id": "issue_abc"}
        svc._work_items["work_direct"] = work

        mock_notif = MagicMock()

        with patch("services.notification_service.get_notification_service", return_value=mock_notif):
            result = await svc.fail_work_and_update_issue(
                "work_direct", "Clone failed: permission denied"
            )

        assert result is not None
        mock_notif.emit.assert_called_once_with(
            title="Work failed: Direct Fail Task",
            message="Clone failed: permission denied",
            level=NotificationLevel.ERROR,
            category=NotificationCategory.WORK,
            project_id="proj_direct",
            entity_id="work_direct",
        )

    @pytest.mark.asyncio
    async def test_notification_not_emitted_when_work_not_found(self):
        """Test that no notification is emitted when work item doesn't exist."""
        from services.work_map_service import WorkMapService

        svc = WorkMapService.__new__(WorkMapService)
        svc._work_items = {}

        mock_notif = MagicMock()

        with patch("services.notification_service.get_notification_service", return_value=mock_notif):
            result = await svc.fail_work_and_update_issue("work_missing", "error")

        assert result is None
        mock_notif.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_crash_when_notification_service_missing(self):
        """Test that missing notification service doesn't prevent failure handling."""
        from services.work_map_service import WorkMapService

        mock_assignment = MagicMock()
        mock_assignment.update_status = AsyncMock(return_value=True)
        mock_issue = MagicMock()
        mock_issue.update_issue_status = AsyncMock(return_value=None)

        svc = WorkMapService.__new__(WorkMapService)
        svc._work_items = {}
        svc._assignment_service = mock_assignment
        svc._issue_service = mock_issue
        svc._save_to_redis = AsyncMock()

        work = MagicMock()
        work.work_id = "work_nonotif"
        work.title = "No Notif Task"
        work.project_id = "proj_nn"
        work.error = None
        work.context = {}
        svc._work_items["work_nonotif"] = work

        with patch(
            "services.notification_service.get_notification_service",
            side_effect=RuntimeError("not initialized"),
        ):
            # Should not raise — failure handling must complete
            result = await svc.fail_work_and_update_issue("work_nonotif", "some error")

        assert result is not None
