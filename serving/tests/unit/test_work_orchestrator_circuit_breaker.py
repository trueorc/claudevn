"""Tests for work orchestrator circuit-breaker logic.

Verifies that deterministic errors (configuration, permission, environment)
cause fast-fail instead of wasting time on retries, especially in
single-compute deployments.

See: https://github.com/Guarrdon/trueorc/issues/799
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.work_orchestrator import (
    WorkOrchestrator,
    DETERMINISTIC_ERROR_PATTERNS,
    _DETERMINISTIC_RE,
)
from models.work_map import WorkStatus, WorkPriority


@pytest.fixture
def orchestrator():
    """Create an orchestrator for testing."""
    return WorkOrchestrator(
        poll_interval=1,
        max_concurrent_spawns=3,
        max_retries=3,
        retry_delay=10
    )


# =============================================================================
# Test: _is_deterministic_error
# =============================================================================

class TestIsDeterministicError:
    """Test deterministic error pattern detection."""

    def test_dubious_ownership(self, orchestrator):
        """Test Git dubious ownership error is detected."""
        error = (
            "fatal: detected dubious ownership in repository at "
            "'/app/data/repos/proj_123.git'"
        )
        assert orchestrator._is_deterministic_error(error) is True

    def test_safe_directory(self, orchestrator):
        """Test Git safe.directory error is detected."""
        error = "git config --global --add safe.directory /app/data/repos/test.git"
        assert orchestrator._is_deterministic_error(error) is True

    def test_ssh_permission_denied(self, orchestrator):
        """Test SSH permission denied error is detected."""
        error = "Permission denied (publickey)."
        assert orchestrator._is_deterministic_error(error) is True

    def test_host_key_verification(self, orchestrator):
        """Test host key verification failure is detected."""
        error = "Host key verification failed"
        assert orchestrator._is_deterministic_error(error) is True

    def test_hostname_resolution(self, orchestrator):
        """Test hostname resolution failure is detected."""
        error = "ssh: Could not resolve hostname serving: Name or service not known"
        assert orchestrator._is_deterministic_error(error) is True

    def test_not_a_git_repo(self, orchestrator):
        """Test 'not a git repository' error is detected."""
        error = "fatal: not a git repository (or any parent up to mount point /)"
        assert orchestrator._is_deterministic_error(error) is True

    def test_command_not_found(self, orchestrator):
        """Test 'command not found' error is detected."""
        error = "claude: command not found"
        assert orchestrator._is_deterministic_error(error) is True

    def test_auth_failed(self, orchestrator):
        """Test 'authentication failed' error is detected."""
        error = "remote: authentication failed for 'https://github.com/test.git'"
        assert orchestrator._is_deterministic_error(error) is True

    def test_root_permissions_skip(self, orchestrator):
        """Test root permissions skip error is detected."""
        error = "Cannot use --dangerously-skip-permissions as root user"
        assert orchestrator._is_deterministic_error(error) is True

    def test_transient_error_not_detected(self, orchestrator):
        """Test transient errors are NOT flagged as deterministic."""
        transient_errors = [
            "Connection timed out",
            "rate limit exceeded",
            "internal server error",
            "503 Service Unavailable",
            "socket hang up",
            "EAGAIN",
        ]
        for error in transient_errors:
            assert orchestrator._is_deterministic_error(error) is False, (
                f"'{error}' should not be flagged as deterministic"
            )

    def test_none_error(self, orchestrator):
        """Test None error returns False."""
        assert orchestrator._is_deterministic_error(None) is False

    def test_empty_error(self, orchestrator):
        """Test empty string returns False."""
        assert orchestrator._is_deterministic_error("") is False

    def test_case_insensitive(self, orchestrator):
        """Test pattern matching is case-insensitive."""
        assert orchestrator._is_deterministic_error("DUBIOUS OWNERSHIP detected") is True
        assert orchestrator._is_deterministic_error("Authentication Failed") is True


# =============================================================================
# Test: Circuit-breaker in _retry_failed_work
# =============================================================================

class TestCircuitBreakerRetry:
    """Test circuit-breaker logic during retry processing."""

    def _make_failed_work(self, work_id="work_cb", error=None, assigned_to=None):
        """Create a mock failed work item."""
        item = MagicMock()
        item.work_id = work_id
        item.title = "Test Work"
        item.retry_count = 1
        item.status = WorkStatus.FAILED
        item.error = error
        item.assigned_to = assigned_to
        item.project_id = "project-1"
        return item

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_on_deterministic_error_single_compute(self, orchestrator):
        """Test circuit-breaker skips retries for deterministic errors on single compute."""
        failed_item = self._make_failed_work(
            error="fatal: detected dubious ownership in repository at '/app/data/repos/test.git'",
            assigned_to="compute-001"
        )

        # Mark this compute as having failed previously
        orchestrator._failed_nodes["work_cb"] = {"compute-001"}

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse, \
             patch("services.work_orchestrator._emit_failure_notification", create=True) as mock_notify:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            # mark_work_for_retry with max_retries=0 should return FAILED
            failed_result = MagicMock()
            failed_result.status = WorkStatus.FAILED
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=failed_result)
            mock_get_wms.return_value = mock_work_map

            # Single compute connected
            mock_conn = MagicMock()
            mock_conn.compute_id = "compute-001"
            mock_sse.return_value.list_connections.return_value = [mock_conn]

            retried = await orchestrator._retry_failed_work()

            # Should NOT retry — circuit-breaker tripped
            assert retried == 0
            assert orchestrator._stats["total_circuit_breaks"] == 1

            # Should have called mark_work_for_retry with max_retries=0 to force FAILED
            mock_work_map.mark_work_for_retry.assert_called_once_with("work_cb", 0)

            # Should emit notification
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args
            assert "Circuit-breaker" in call_kwargs.kwargs.get("error", call_kwargs[1].get("error", ""))

            # Should clean up tracking state
            assert "work_cb" not in orchestrator._failed_nodes
            assert "work_cb" not in orchestrator._retry_after
            assert "work_cb" not in orchestrator._retry_counts
            assert "work_cb" not in orchestrator._last_errors

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_when_all_computes_failed(self, orchestrator):
        """Test circuit-breaker trips when all available computes have failed."""
        failed_item = self._make_failed_work(
            error="Permission denied (publickey).",
            assigned_to="compute-002"
        )

        # Both computes have failed for this work
        orchestrator._failed_nodes["work_cb"] = {"compute-001", "compute-002"}

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            failed_result = MagicMock()
            failed_result.status = WorkStatus.FAILED
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=failed_result)
            mock_get_wms.return_value = mock_work_map

            # Two computes connected
            mock_sse.return_value.list_connections.return_value = [
                MagicMock(compute_id="compute-001"),
                MagicMock(compute_id="compute-002"),
            ]

            retried = await orchestrator._retry_failed_work()

            assert retried == 0
            assert orchestrator._stats["total_circuit_breaks"] == 1
            mock_work_map.mark_work_for_retry.assert_called_once_with("work_cb", 0)

    @pytest.mark.asyncio
    async def test_circuit_breaker_does_not_trip_on_transient_error(self, orchestrator):
        """Test circuit-breaker does NOT trip for transient errors."""
        failed_item = self._make_failed_work(
            error="Connection timed out after 30 seconds",
            assigned_to="compute-001"
        )

        updated_item = MagicMock()
        updated_item.work_id = "work_cb"
        updated_item.retry_count = 2
        updated_item.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated_item)
            mock_get_wms.return_value = mock_work_map

            retried = await orchestrator._retry_failed_work()

            # Should retry normally
            assert retried == 1
            assert orchestrator._stats["total_circuit_breaks"] == 0
            # Should use normal max_retries (3), not circuit-breaker (0)
            mock_work_map.mark_work_for_retry.assert_called_once_with("work_cb", 3)

    @pytest.mark.asyncio
    async def test_circuit_breaker_does_not_trip_when_other_computes_available(self, orchestrator):
        """Test circuit-breaker does NOT trip when untried computes exist."""
        failed_item = self._make_failed_work(
            error="fatal: detected dubious ownership in repository",
            assigned_to="compute-001"
        )

        # Only 1 of 2 computes has failed
        orchestrator._failed_nodes["work_cb"] = {"compute-001"}

        updated_item = MagicMock()
        updated_item.work_id = "work_cb"
        updated_item.retry_count = 2
        updated_item.status = WorkStatus.PENDING

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=updated_item)
            mock_get_wms.return_value = mock_work_map

            # Two computes — one hasn't been tried yet
            mock_sse.return_value.list_connections.return_value = [
                MagicMock(compute_id="compute-001"),
                MagicMock(compute_id="compute-002"),
            ]

            retried = await orchestrator._retry_failed_work()

            # Should retry (another compute might succeed)
            assert retried == 1
            assert orchestrator._stats["total_circuit_breaks"] == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_uses_last_errors_fallback(self, orchestrator):
        """Test circuit-breaker checks _last_errors when work.error is None."""
        failed_item = self._make_failed_work(error=None, assigned_to="compute-001")

        # Error was tracked by _handle_spawn_failure
        orchestrator._last_errors["work_cb"] = "fatal: not a git repository"
        orchestrator._failed_nodes["work_cb"] = {"compute-001"}

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            failed_result = MagicMock()
            failed_result.status = WorkStatus.FAILED
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=failed_result)
            mock_get_wms.return_value = mock_work_map

            mock_sse.return_value.list_connections.return_value = [
                MagicMock(compute_id="compute-001"),
            ]

            retried = await orchestrator._retry_failed_work()

            assert retried == 0
            assert orchestrator._stats["total_circuit_breaks"] == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_handles_sse_manager_error(self, orchestrator):
        """Test graceful fallback when SSE manager is unavailable."""
        failed_item = self._make_failed_work(
            error="fatal: detected dubious ownership",
            assigned_to="compute-001"
        )
        orchestrator._failed_nodes["work_cb"] = {"compute-001"}

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms, \
             patch("services.sse_connection_manager.get_sse_connection_manager") as mock_sse:
            mock_work_map = MagicMock()
            mock_work_map.get_failed_work = AsyncMock(return_value=[failed_item])
            failed_result = MagicMock()
            failed_result.status = WorkStatus.FAILED
            mock_work_map.mark_work_for_retry = AsyncMock(return_value=failed_result)
            mock_get_wms.return_value = mock_work_map

            # SSE manager throws
            mock_sse.side_effect = RuntimeError("not initialized")

            retried = await orchestrator._retry_failed_work()

            # total_computes=0 means single-compute path → circuit-breaker trips
            assert retried == 0
            assert orchestrator._stats["total_circuit_breaks"] == 1


# =============================================================================
# Test: _handle_spawn_failure tracks errors
# =============================================================================

class TestHandleSpawnFailureErrorTracking:
    """Test that _handle_spawn_failure records errors for circuit-breaker."""

    def test_tracks_error_message(self, orchestrator):
        """Test that spawn failure stores the error message."""
        orchestrator._handle_spawn_failure("work_123", "dubious ownership error")

        assert orchestrator._last_errors["work_123"] == "dubious ownership error"

    def test_tracks_latest_error(self, orchestrator):
        """Test that subsequent failures overwrite the previous error."""
        orchestrator._handle_spawn_failure("work_123", "first error")
        orchestrator._handle_spawn_failure("work_123", "second error")

        assert orchestrator._last_errors["work_123"] == "second error"

    def test_logs_deterministic_flag(self, orchestrator):
        """Test that deterministic flag is set in logging context."""
        # Just verify no errors - the log message contains deterministic=True/False
        orchestrator._handle_spawn_failure("work_a", "dubious ownership")
        orchestrator._handle_spawn_failure("work_b", "connection timeout")
        assert orchestrator._retry_counts["work_a"] == 1
        assert orchestrator._retry_counts["work_b"] == 1
