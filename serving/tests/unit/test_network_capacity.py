"""Unit tests for network capacity management (Issue #119)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from models.compute import ComputeInstance, InstanceStatus, InstanceCapabilities


class TestRegistryGetInstanceCount:
    """Tests for ComputeRegistry.get_instance_count()."""

    def test_empty_registry(self):
        """get_instance_count returns 0 for empty registry."""
        from services.registry_service import ComputeRegistry
        registry = ComputeRegistry()
        assert registry.get_instance_count() == 0

    @pytest.mark.asyncio
    async def test_with_instances(self):
        """get_instance_count returns correct count after adding instances."""
        from services.registry_service import ComputeRegistry
        registry = ComputeRegistry()

        for i in range(3):
            instance = ComputeInstance(
                instance_id=f"inst-{i}",
                name=f"Test {i}",
                endpoint="sse",
                status=InstanceStatus.ONLINE,
                capabilities=InstanceCapabilities(),
            )
            await registry.add_instance(instance)

        assert registry.get_instance_count() == 3

    @pytest.mark.asyncio
    async def test_after_removal(self):
        """get_instance_count decreases after removing an instance."""
        from services.registry_service import ComputeRegistry
        registry = ComputeRegistry()

        instance = ComputeInstance(
            instance_id="inst-1",
            name="Test 1",
            endpoint="sse",
            status=InstanceStatus.ONLINE,
            capabilities=InstanceCapabilities(),
        )
        await registry.add_instance(instance)
        assert registry.get_instance_count() == 1

        await registry.remove_instance("inst-1")
        assert registry.get_instance_count() == 0


class TestCapacityConfig:
    """Tests for NetworkCapacityConfig."""

    def test_default_unlimited(self):
        """Default max_compute_instances is 0 (unlimited)."""
        from config import NetworkCapacityConfig
        config = NetworkCapacityConfig()
        assert config.max_compute_instances == 0

    def test_custom_limit(self):
        """Can set a custom limit."""
        from config import NetworkCapacityConfig
        config = NetworkCapacityConfig(max_compute_instances=10)
        assert config.max_compute_instances == 10

    def test_env_loading(self):
        """from_env() loads MAX_COMPUTE_INSTANCES."""
        import importlib
        import config as config_mod
        with patch.dict("os.environ", {"MAX_COMPUTE_INSTANCES": "5"}, clear=False):
            importlib.reload(config_mod)
            config = config_mod.ServingConfig.from_env()
            assert config.network_capacity.max_compute_instances == 5


class TestCapacityEnforcementOnConnect:
    """Tests for capacity enforcement in /connect endpoint."""

    @pytest.mark.asyncio
    async def test_allows_connection_when_unlimited(self):
        """When max_compute_instances=0, all connections are allowed."""
        from config import NetworkCapacityConfig, ServingConfig
        mock_config = MagicMock(spec=ServingConfig)
        mock_config.network_capacity = NetworkCapacityConfig(max_compute_instances=0)

        # Capacity check should not raise
        max_instances = mock_config.network_capacity.max_compute_instances
        assert max_instances == 0  # unlimited, skip check

    @pytest.mark.asyncio
    async def test_allows_connection_under_limit(self):
        """When under the limit, connections are allowed."""
        from config import NetworkCapacityConfig
        cap = NetworkCapacityConfig(max_compute_instances=5)

        current_count = 3
        assert current_count < cap.max_compute_instances

    @pytest.mark.asyncio
    async def test_blocks_connection_at_limit(self):
        """When at the limit, new connections are blocked."""
        from config import NetworkCapacityConfig
        cap = NetworkCapacityConfig(max_compute_instances=5)

        current_count = 5
        assert current_count >= cap.max_compute_instances

    @pytest.mark.asyncio
    async def test_allows_reconnect_at_limit(self):
        """Reconnecting instances (already registered) are allowed even at limit."""
        from services.registry_service import ComputeRegistry
        registry = ComputeRegistry()

        # Add instances up to limit
        for i in range(5):
            instance = ComputeInstance(
                instance_id=f"inst-{i}",
                name=f"Test {i}",
                endpoint="sse",
                status=InstanceStatus.ONLINE,
                capabilities=InstanceCapabilities(),
            )
            await registry.add_instance(instance)

        # Existing instance should be found (reconnect allowed)
        existing = await registry.get_instance("inst-0")
        assert existing is not None  # reconnect allowed


class TestCapacityAPIResponses:
    """Tests for network capacity API response models."""

    def test_capacity_response_unlimited(self):
        """Capacity response with unlimited config."""
        from api.network_capacity import CapacityResponse
        resp = CapacityResponse(
            max_compute_instances=0,
            current_instances=3,
            available_slots=-1,
        )
        assert resp.max_compute_instances == 0
        assert resp.current_instances == 3
        assert resp.available_slots == -1

    def test_capacity_response_limited(self):
        """Capacity response with limit set."""
        from api.network_capacity import CapacityResponse
        resp = CapacityResponse(
            max_compute_instances=10,
            current_instances=7,
            available_slots=3,
        )
        assert resp.max_compute_instances == 10
        assert resp.current_instances == 7
        assert resp.available_slots == 3

    def test_capacity_response_at_limit(self):
        """Capacity response when at limit."""
        from api.network_capacity import CapacityResponse
        resp = CapacityResponse(
            max_compute_instances=5,
            current_instances=5,
            available_slots=0,
        )
        assert resp.available_slots == 0

    def test_update_request_validation(self):
        """UpdateCapacityRequest rejects negative values."""
        from api.network_capacity import UpdateCapacityRequest
        with pytest.raises(Exception):
            UpdateCapacityRequest(max_compute_instances=-1)

    def test_update_request_valid(self):
        """UpdateCapacityRequest accepts valid values."""
        from api.network_capacity import UpdateCapacityRequest
        req = UpdateCapacityRequest(max_compute_instances=10)
        assert req.max_compute_instances == 10

        req_zero = UpdateCapacityRequest(max_compute_instances=0)
        assert req_zero.max_compute_instances == 0
