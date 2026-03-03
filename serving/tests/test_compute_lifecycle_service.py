"""Tests for ComputeLifecycleService — auto-drain of idle managed instances."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from config import AutoDrainConfig
from models.compute import ComputeInstance, InstanceStatus, LifecycleMode, InstanceCapabilities
from models.work_map import WorkStatus, BlockerType, Blocker
from services.compute_lifecycle_service import ComputeLifecycleService

# Pre-import modules that are lazily imported inside the service so patches resolve
import services.registry_service
import services.work_map_service
import services.compute_provisioner


def _make_instance(
    instance_id="compute-1",
    lifecycle_mode=LifecycleMode.MANAGED,
    status=InstanceStatus.ONLINE,
    tools_available=None,
    labels=None,
):
    return ComputeInstance(
        instance_id=instance_id,
        name=f"Test-{instance_id}",
        endpoint="http://localhost:8003",
        status=status,
        lifecycle_mode=lifecycle_mode,
        capabilities=InstanceCapabilities(
            tools_available=tools_available or [],
            labels=labels or [],
        ),
    )


def _make_work(
    work_id="work-1",
    status=WorkStatus.PENDING,
    assigned_to=None,
    required_tools=None,
    required_labels=None,
    blockers=None,
):
    work = MagicMock()
    work.work_id = work_id
    work.status = status
    work.assigned_to = assigned_to
    work.required_tools = required_tools or []
    work.required_labels = required_labels or []
    work.blockers = blockers or []
    return work


@pytest.fixture
def config():
    return AutoDrainConfig(
        enabled=True,
        check_interval_seconds=60,
        idle_grace_period_minutes=5,
    )


@pytest.fixture
def service(config):
    return ComputeLifecycleService(config)


class TestStart:
    @pytest.mark.asyncio
    async def test_starts_when_enabled(self, service):
        service._monitor_loop = AsyncMock()
        await service.start()
        assert service._running is True
        service._task.cancel()

    @pytest.mark.asyncio
    async def test_does_not_start_when_disabled(self):
        config = AutoDrainConfig(enabled=False)
        svc = ComputeLifecycleService(config)
        await svc.start()
        assert svc._running is False
        assert svc._task is None


class TestCheckIdleInstances:
    @pytest.mark.asyncio
    async def test_skips_unmanaged_instances(self, service):
        """Unmanaged (BYOC) instances should never be auto-drained."""
        unmanaged = _make_instance(lifecycle_mode=LifecycleMode.UNMANAGED)
        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [unmanaged]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = []

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc):
            await service._check_idle_instances()

        mock_registry.drain_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_already_draining_instances(self, service):
        draining = _make_instance(status=InstanceStatus.DRAINING)
        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [draining]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = []

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc):
            await service._check_idle_instances()

        mock_registry.drain_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_idle_when_instance_has_active_work(self, service):
        instance = _make_instance()
        work = _make_work(status=WorkStatus.IN_PROGRESS, assigned_to="compute-1")
        service._idle_since["compute-1"] = datetime.now(timezone.utc) - timedelta(minutes=10)

        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [instance]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = [work]

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc):
            await service._check_idle_instances()

        assert "compute-1" not in service._idle_since
        mock_registry.drain_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_idle_when_matching_pending_work(self, service):
        instance = _make_instance(tools_available=["runtime:node:22"])
        work = _make_work(status=WorkStatus.PENDING, required_tools=["runtime:node:22"])
        service._idle_since["compute-1"] = datetime.now(timezone.utc) - timedelta(minutes=10)

        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [instance]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = [work]

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc):
            await service._check_idle_instances()

        assert "compute-1" not in service._idle_since

    @pytest.mark.asyncio
    async def test_starts_idle_tracking_first_time(self, service):
        instance = _make_instance()
        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [instance]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = []

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc):
            await service._check_idle_instances()

        assert "compute-1" in service._idle_since
        mock_registry.drain_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_drains_after_grace_period(self, service):
        instance = _make_instance()
        service._idle_since["compute-1"] = datetime.now(timezone.utc) - timedelta(minutes=10)

        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [instance]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = []

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc), \
             patch("services.compute_provisioner.get_provisioner_registry") as mock_prov:
            await service._check_idle_instances()

        mock_registry.drain_instance.assert_called_once_with("compute-1", auto_deregister=True)
        assert "compute-1" not in service._idle_since

    @pytest.mark.asyncio
    async def test_does_not_drain_before_grace_period(self, service):
        instance = _make_instance()
        service._idle_since["compute-1"] = datetime.now(timezone.utc) - timedelta(minutes=2)

        mock_registry = AsyncMock()
        mock_registry.list_instances.return_value = [instance]
        mock_work_svc = AsyncMock()
        mock_work_svc.list_work.return_value = []

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_work_svc):
            await service._check_idle_instances()

        mock_registry.drain_instance.assert_not_called()


class TestHasMatchingWork:
    def test_matches_pending_work_by_tools(self, service):
        instance = _make_instance(tools_available=["runtime:node:22"])
        work = _make_work(status=WorkStatus.PENDING, required_tools=["runtime:node:22"])
        result = service._has_matching_work(
            instance, [work], {WorkStatus.PENDING, WorkStatus.BLOCKED}
        )
        assert result is True

    def test_no_match_for_different_tools(self, service):
        instance = _make_instance(tools_available=["runtime:python:3.12"])
        work = _make_work(status=WorkStatus.PENDING, required_tools=["runtime:node:22"])
        result = service._has_matching_work(
            instance, [work], {WorkStatus.PENDING, WorkStatus.BLOCKED}
        )
        assert result is False

    def test_matches_capability_blocked_work(self, service):
        instance = _make_instance(tools_available=["runtime:node:22"])
        blocker = MagicMock()
        blocker.blocker_type = BlockerType.CAPABILITY_MISSING
        blocker.resolved = False
        work = _make_work(
            status=WorkStatus.BLOCKED,
            required_tools=["runtime:node:22"],
            blockers=[blocker],
        )
        result = service._has_matching_work(
            instance, [work], {WorkStatus.PENDING, WorkStatus.BLOCKED}
        )
        assert result is True

    def test_ignores_non_capability_blocked_work(self, service):
        instance = _make_instance(tools_available=["runtime:node:22"])
        blocker = MagicMock()
        blocker.blocker_type = BlockerType.DEPENDENCY
        blocker.resolved = False
        work = _make_work(
            status=WorkStatus.BLOCKED,
            required_tools=["runtime:node:22"],
            blockers=[blocker],
        )
        result = service._has_matching_work(
            instance, [work], {WorkStatus.PENDING, WorkStatus.BLOCKED}
        )
        assert result is False

    def test_work_with_no_requirements_matches_any(self, service):
        instance = _make_instance()
        work = _make_work(status=WorkStatus.PENDING)
        result = service._has_matching_work(
            instance, [work], {WorkStatus.PENDING}
        )
        assert result is True


class TestDrainAndDeprovision:
    @pytest.mark.asyncio
    async def test_calls_drain_and_deprovision(self, service):
        mock_registry = AsyncMock()
        mock_prov = AsyncMock()

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.compute_provisioner.get_provisioner_registry", return_value=mock_prov):
            await service._drain_and_deprovision("managed-abc")

        mock_registry.drain_instance.assert_called_once_with("managed-abc", auto_deregister=True)
        mock_prov.deprovision.assert_called_once_with("managed-abc", provider_name="docker")

    @pytest.mark.asyncio
    async def test_handles_drain_failure(self, service):
        mock_registry = AsyncMock()
        mock_registry.drain_instance.side_effect = RuntimeError("drain failed")
        mock_prov = AsyncMock()

        with patch("services.registry_service.get_compute_registry", return_value=mock_registry), \
             patch("services.compute_provisioner.get_provisioner_registry", return_value=mock_prov):
            await service._drain_and_deprovision("managed-abc")

        # Deprovision should NOT be called if drain fails
        mock_prov.deprovision.assert_not_called()
