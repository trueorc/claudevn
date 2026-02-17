"""Tests for HealthMonitor service."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.health_monitor import (
    HealthMonitor,
    get_health_monitor,
    set_health_monitor,
    start_health_monitoring,
    stop_health_monitoring
)


@pytest.fixture
def mock_compute_registry():
    """Create mock compute registry."""
    registry = MagicMock()
    registry.check_health = AsyncMock(return_value={
        "checked_at": "2026-01-01T00:00:00",
        "total_instances": 2,
        "status_changes": []
    })
    registry.check_auth_expiry = AsyncMock(return_value=[])
    return registry


@pytest.fixture
def mock_marketplace_registry():
    """Create mock marketplace registry."""
    registry = MagicMock()
    registry.check_health = AsyncMock(return_value={
        "degraded": 0,
        "offline": 0,
        "deregistered": 0
    })
    return registry


@pytest.fixture
def health_monitor(mock_compute_registry):
    """Create health monitor with mocked compute registry only."""
    return HealthMonitor(
        compute_registry=mock_compute_registry,
        check_interval=1,  # Fast interval for tests
        degraded_threshold=60,
        offline_threshold=90,
        max_failed_checks=3
    )


@pytest.fixture
def health_monitor_with_marketplace(mock_compute_registry, mock_marketplace_registry):
    """Create health monitor with both registries."""
    return HealthMonitor(
        compute_registry=mock_compute_registry,
        marketplace_registry=mock_marketplace_registry,
        check_interval=1,
        degraded_threshold=60,
        offline_threshold=90,
        max_failed_checks=3
    )


class TestHealthMonitorInit:
    """Test HealthMonitor initialization."""

    def test_init_with_compute_only(self, mock_compute_registry):
        """Test initialization with compute registry only."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            check_interval=30,
            degraded_threshold=60,
            offline_threshold=90
        )

        assert monitor.compute_registry is mock_compute_registry
        assert monitor.marketplace_registry is None
        assert monitor.check_interval == 30
        assert monitor.degraded_threshold == 60
        assert monitor.offline_threshold == 90
        assert monitor.is_running() is False

    def test_init_with_both_registries(
        self, mock_compute_registry, mock_marketplace_registry
    ):
        """Test initialization with both registries."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            marketplace_registry=mock_marketplace_registry,
            check_interval=15
        )

        assert monitor.compute_registry is mock_compute_registry
        assert monitor.marketplace_registry is mock_marketplace_registry

    def test_init_with_auto_deregister(self, mock_compute_registry):
        """Test initialization with auto_deregister flag."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            auto_deregister=True
        )

        assert monitor.auto_deregister is True


class TestHealthMonitorStartStop:
    """Test start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self, health_monitor):
        """Test start sets running flag."""
        await health_monitor.start()

        assert health_monitor.is_running() is True

        await health_monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self, health_monitor):
        """Test stop clears running flag."""
        await health_monitor.start()
        await health_monitor.stop()

        assert health_monitor.is_running() is False

    @pytest.mark.asyncio
    async def test_start_twice_is_safe(self, health_monitor):
        """Test calling start twice doesn't create duplicate tasks."""
        await health_monitor.start()
        await health_monitor.start()  # Should be a no-op

        assert health_monitor.is_running() is True
        assert health_monitor._task is not None

        await health_monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_safe(self, health_monitor):
        """Test stop when not running is safe."""
        # Should not raise
        await health_monitor.stop()
        assert health_monitor.is_running() is False


class TestHealthMonitorCheckComputeHealth:
    """Test compute health checking."""

    @pytest.mark.asyncio
    async def test_check_compute_health_called(
        self, health_monitor, mock_compute_registry
    ):
        """Test that compute registry check_health is called."""
        await health_monitor._check_health()

        mock_compute_registry.check_health.assert_called_once_with(
            max_heartbeat_age=90,  # offline_threshold
            degraded_threshold=60
        )

    @pytest.mark.asyncio
    async def test_check_compute_health_with_status_changes(
        self, mock_compute_registry
    ):
        """Test handling of compute status changes."""
        mock_compute_registry.check_health = AsyncMock(return_value={
            "checked_at": "2026-01-01T00:00:00",
            "total_instances": 2,
            "status_changes": [
                {
                    "instance_id": "compute-001",
                    "old_status": "online",
                    "new_status": "degraded",
                    "heartbeat_age": 65
                }
            ]
        })

        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            check_interval=1
        )

        # Should not raise
        await monitor._check_health()

        mock_compute_registry.check_health.assert_called_once()


class TestHealthMonitorCheckMarketplaceHealth:
    """Test marketplace health checking."""

    @pytest.mark.asyncio
    async def test_check_marketplace_health_called(
        self, health_monitor_with_marketplace, mock_marketplace_registry
    ):
        """Test that marketplace registry check_health is called."""
        await health_monitor_with_marketplace._check_health()

        mock_marketplace_registry.check_health.assert_called_once_with(
            degraded_threshold=60,
            offline_threshold=90,
            max_failed_checks=3
        )

    @pytest.mark.asyncio
    async def test_marketplace_not_called_when_not_configured(
        self, health_monitor, mock_compute_registry
    ):
        """Test marketplace check is skipped when not configured."""
        await health_monitor._check_health()

        # Only compute should be called
        mock_compute_registry.check_health.assert_called_once()
        # No marketplace registry, so no marketplace call

    @pytest.mark.asyncio
    async def test_check_marketplace_with_changes(
        self, mock_compute_registry, mock_marketplace_registry
    ):
        """Test handling of marketplace status changes."""
        mock_marketplace_registry.check_health = AsyncMock(return_value={
            "degraded": 1,
            "offline": 1,
            "deregistered": 0
        })

        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            marketplace_registry=mock_marketplace_registry,
            check_interval=1
        )

        # Should not raise
        await monitor._check_health()

        mock_marketplace_registry.check_health.assert_called_once()


class TestHealthMonitorThresholds:
    """Test threshold configuration."""

    @pytest.mark.asyncio
    async def test_degraded_threshold_passed_to_compute(self, mock_compute_registry):
        """Test degraded threshold is passed to compute registry."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            degraded_threshold=45,
            offline_threshold=120
        )

        await monitor._check_health()

        mock_compute_registry.check_health.assert_called_with(
            max_heartbeat_age=120,
            degraded_threshold=45
        )

    @pytest.mark.asyncio
    async def test_offline_threshold_passed_to_compute(self, mock_compute_registry):
        """Test offline threshold is passed to compute registry."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            degraded_threshold=30,
            offline_threshold=180
        )

        await monitor._check_health()

        mock_compute_registry.check_health.assert_called_with(
            max_heartbeat_age=180,
            degraded_threshold=30
        )

    @pytest.mark.asyncio
    async def test_thresholds_passed_to_marketplace(
        self, mock_compute_registry, mock_marketplace_registry
    ):
        """Test thresholds are passed to marketplace registry."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            marketplace_registry=mock_marketplace_registry,
            degraded_threshold=45,
            offline_threshold=120,
            max_failed_checks=5
        )

        await monitor._check_health()

        mock_marketplace_registry.check_health.assert_called_with(
            degraded_threshold=45,
            offline_threshold=120,
            max_failed_checks=5
        )


class TestHealthMonitorInterval:
    """Test health check interval."""

    @pytest.mark.asyncio
    async def test_check_interval_stored(self, mock_compute_registry):
        """Test check interval is stored correctly."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            check_interval=15
        )

        assert monitor.check_interval == 15

    @pytest.mark.asyncio
    async def test_monitoring_loop_uses_interval(
        self, mock_compute_registry
    ):
        """Test monitoring loop respects check interval."""
        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            check_interval=1  # 1 second for fast test
        )

        await monitor.start()

        # Wait for at least 2 intervals
        await asyncio.sleep(2.5)

        await monitor.stop()

        # Should have been called at least twice
        assert mock_compute_registry.check_health.call_count >= 2


class TestHealthMonitorForceCheck:
    """Test force_check functionality."""

    @pytest.mark.asyncio
    async def test_force_check_calls_check_health(
        self, health_monitor, mock_compute_registry
    ):
        """Test force_check triggers immediate health check."""
        result = await health_monitor.force_check()

        assert result == {"status": "check_completed"}
        mock_compute_registry.check_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_check_while_running(self, health_monitor, mock_compute_registry):
        """Test force_check works while monitor is running."""
        await health_monitor.start()

        # Force an immediate check
        result = await health_monitor.force_check()

        assert result == {"status": "check_completed"}

        await health_monitor.stop()


class TestHealthMonitorErrorHandling:
    """Test error handling in health checks."""

    @pytest.mark.asyncio
    async def test_compute_check_error_handled(self, mock_compute_registry):
        """Test compute check error doesn't crash monitor."""
        mock_compute_registry.check_health = AsyncMock(
            side_effect=Exception("Compute check failed")
        )

        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            check_interval=1
        )

        # Should not raise
        await monitor._check_health()

    @pytest.mark.asyncio
    async def test_marketplace_check_error_handled(
        self, mock_compute_registry, mock_marketplace_registry
    ):
        """Test marketplace check error doesn't crash monitor."""
        mock_marketplace_registry.check_health = AsyncMock(
            side_effect=Exception("Marketplace check failed")
        )

        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            marketplace_registry=mock_marketplace_registry,
            check_interval=1
        )

        # Should not raise
        await monitor._check_health()


class TestHealthMonitorGlobals:
    """Test global instance management."""

    def test_set_get_health_monitor(self, health_monitor):
        """Test setting and getting global health monitor."""
        set_health_monitor(health_monitor)

        retrieved = get_health_monitor()
        assert retrieved is health_monitor

    def test_get_health_monitor_not_set(self):
        """Test getting health monitor when not set returns None."""
        set_health_monitor(None)
        result = get_health_monitor()
        assert result is None

    @pytest.mark.asyncio
    async def test_start_health_monitoring_function(
        self, mock_compute_registry, mock_marketplace_registry
    ):
        """Test start_health_monitoring convenience function."""
        await start_health_monitoring(
            compute_registry=mock_compute_registry,
            marketplace_registry=mock_marketplace_registry,
            check_interval=1
        )

        monitor = get_health_monitor()
        assert monitor is not None
        assert monitor.is_running() is True

        await stop_health_monitoring()

    @pytest.mark.asyncio
    async def test_stop_health_monitoring_function(self, mock_compute_registry):
        """Test stop_health_monitoring convenience function."""
        await start_health_monitoring(
            compute_registry=mock_compute_registry,
            check_interval=1
        )

        await stop_health_monitoring()

        monitor = get_health_monitor()
        assert monitor.is_running() is False


class TestHealthMonitorConcurrentChecks:
    """Test concurrent health check behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_force_checks(
        self, health_monitor, mock_compute_registry
    ):
        """Test multiple concurrent force_check calls are safe."""
        # Run multiple force checks concurrently
        results = await asyncio.gather(
            health_monitor.force_check(),
            health_monitor.force_check(),
            health_monitor.force_check()
        )

        # All should complete successfully
        assert len(results) == 3
        assert all(r == {"status": "check_completed"} for r in results)

    @pytest.mark.asyncio
    async def test_force_check_during_loop_check(
        self, mock_compute_registry
    ):
        """Test force_check during scheduled check doesn't conflict."""
        # Make check_health take some time
        async def slow_check(**kwargs):
            await asyncio.sleep(0.1)
            return {
                "checked_at": "2026-01-01T00:00:00",
                "total_instances": 0,
                "status_changes": []
            }

        mock_compute_registry.check_health = AsyncMock(side_effect=slow_check)

        monitor = HealthMonitor(
            compute_registry=mock_compute_registry,
            check_interval=1
        )

        await monitor.start()

        # Force check while loop is potentially running
        result = await monitor.force_check()
        assert result == {"status": "check_completed"}

        await monitor.stop()
