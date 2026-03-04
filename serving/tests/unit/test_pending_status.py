"""Tests for PENDING status in compute instance lifecycle."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.compute import (
    ComputeInstance,
    InstanceStatus,
    ComputeAuthStatus,
    InstanceCapabilities,
)


def _make_instance(
    status=InstanceStatus.ONLINE,
    auth_status=ComputeAuthStatus.AUTHORIZED,
    **kwargs,
):
    """Create a test instance with defaults."""
    return ComputeInstance(
        instance_id=kwargs.get("instance_id", "test-001"),
        name="Test Compute",
        endpoint="sse",
        status=status,
        auth_status=auth_status,
        capabilities=InstanceCapabilities(),
        last_heartbeat=datetime.now(timezone.utc),
        **{k: v for k, v in kwargs.items() if k != "instance_id"},
    )


class TestPendingStatus:
    """Test PENDING status in InstanceStatus enum."""

    def test_pending_enum_exists(self):
        assert InstanceStatus.PENDING == "pending"

    def test_pending_in_enum_values(self):
        assert "pending" in [s.value for s in InstanceStatus]


class TestPendingHealthAndEligibility:
    """Test that PENDING instances are not healthy or work-eligible."""

    def test_pending_is_not_healthy(self):
        instance = _make_instance(status=InstanceStatus.PENDING)
        assert instance.is_healthy() is False

    def test_pending_is_not_work_eligible(self):
        instance = _make_instance(
            status=InstanceStatus.PENDING,
            auth_status=ComputeAuthStatus.AUTHORIZED,
        )
        assert instance.is_work_eligible() is False

    def test_pending_unauthorized_is_not_work_eligible(self):
        instance = _make_instance(
            status=InstanceStatus.PENDING,
            auth_status=ComputeAuthStatus.UNAUTHORIZED,
        )
        assert instance.is_work_eligible() is False

    def test_online_authorized_is_work_eligible(self):
        """Verify existing behavior: ONLINE + AUTHORIZED = eligible."""
        instance = _make_instance(
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.AUTHORIZED,
        )
        assert instance.is_work_eligible() is True

    def test_online_unauthorized_is_not_work_eligible(self):
        """Verify existing behavior: ONLINE + UNAUTHORIZED = not eligible."""
        instance = _make_instance(
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.UNAUTHORIZED,
        )
        assert instance.is_work_eligible() is False


class TestPendingSinceField:
    """Test pending_since timestamp field."""

    def test_pending_since_default_none(self):
        instance = _make_instance()
        assert instance.pending_since is None

    def test_pending_since_set_on_pending(self):
        now = datetime.now(timezone.utc)
        instance = _make_instance(
            status=InstanceStatus.PENDING,
            pending_since=now,
        )
        assert instance.pending_since == now

    def test_pending_since_serialization(self):
        now = datetime.now(timezone.utc)
        instance = _make_instance(
            status=InstanceStatus.PENDING,
            pending_since=now,
        )
        data = instance.model_dump()
        assert data["pending_since"] is not None
        assert data["status"] == "pending"


class TestApproveInstance:
    """Test instance approval via registry."""

    @pytest.mark.asyncio
    async def test_approve_transitions_to_online(self):
        from collections import defaultdict
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {}
        registry._project_index = defaultdict(list)
        registry._capability_index = defaultdict(list)
        registry._storage = None
        registry._event_queues = {}

        instance = _make_instance(
            status=InstanceStatus.PENDING,
            pending_since=datetime.now(timezone.utc),
        )
        registry._instances["test-001"] = instance

        with patch.object(registry, "_save_to_storage", new_callable=AsyncMock):
            result = await registry.approve_instance("test-001")

        assert result.status == InstanceStatus.ONLINE
        assert result.pending_since is None

    @pytest.mark.asyncio
    async def test_approve_nonexistent_returns_none(self):
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {}

        result = await registry.approve_instance("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_non_pending_raises_error(self):
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {}

        instance = _make_instance(status=InstanceStatus.ONLINE)
        registry._instances["test-001"] = instance

        with pytest.raises(ValueError, match="not pending"):
            await registry.approve_instance("test-001")


class TestRejectInstance:
    """Test instance rejection via registry."""

    @pytest.mark.asyncio
    async def test_reject_removes_instance(self):
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {}
        registry._project_index = {}
        registry._storage = None

        instance = _make_instance(status=InstanceStatus.PENDING)
        registry._instances["test-001"] = instance

        with patch.object(registry, "remove_instance", new_callable=AsyncMock, return_value=True) as mock_remove:
            result = await registry.reject_instance("test-001")

        assert result is True
        mock_remove.assert_called_once_with("test-001")

    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_false(self):
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {}

        result = await registry.reject_instance("nonexistent")
        assert result is False


class TestGetPendingInstances:
    """Test listing pending instances."""

    @pytest.mark.asyncio
    async def test_returns_only_pending(self):
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {
            "pending-1": _make_instance(instance_id="pending-1", status=InstanceStatus.PENDING),
            "online-1": _make_instance(instance_id="online-1", status=InstanceStatus.ONLINE),
            "pending-2": _make_instance(instance_id="pending-2", status=InstanceStatus.PENDING),
        }

        result = await registry.get_pending_instances()
        assert len(result) == 2
        assert all(i.status == InstanceStatus.PENDING for i in result)

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_pending(self):
        from services.registry_service import ComputeRegistry

        registry = ComputeRegistry.__new__(ComputeRegistry)
        registry._instances = {
            "online-1": _make_instance(instance_id="online-1", status=InstanceStatus.ONLINE),
        }

        result = await registry.get_pending_instances()
        assert len(result) == 0
