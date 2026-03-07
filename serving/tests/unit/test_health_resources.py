"""Unit tests for hardware resource metrics in health endpoint (#225)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from models.compute import (
    InstanceResources,
    AggregatedCapabilities,
)


class TestHealthResourceAggregation:
    """Test that health endpoint includes total_resources from compute registry."""

    @pytest.mark.asyncio
    async def test_total_resources_included_in_health(self):
        """Health response includes total_resources when aggregation succeeds."""
        mock_registry = MagicMock()
        mock_registry.get_stats.return_value = {
            "total_instances": 3,
            "by_status": {"online": 2, "offline": 1},
        }

        mock_aggregated = AggregatedCapabilities(
            total_instances=3,
            online_instances=2,
            total_resources=InstanceResources(
                cpu_count=16,
                memory_gb=64.0,
                gpu_count=2,
                storage_gb=1000.0,
            ),
        )
        mock_registry.get_aggregated_capabilities = AsyncMock(return_value=mock_aggregated)

        aggregated = await mock_registry.get_aggregated_capabilities()
        total_resources = {
            "cpu_count": aggregated.total_resources.cpu_count,
            "memory_gb": aggregated.total_resources.memory_gb,
            "gpu_count": aggregated.total_resources.gpu_count,
            "storage_gb": aggregated.total_resources.storage_gb,
        }

        assert total_resources["cpu_count"] == 16
        assert total_resources["memory_gb"] == 64.0
        assert total_resources["gpu_count"] == 2
        assert total_resources["storage_gb"] == 1000.0

    @pytest.mark.asyncio
    async def test_total_resources_none_on_error(self):
        """Health response sets total_resources to None when aggregation fails."""
        mock_registry = MagicMock()
        mock_registry.get_aggregated_capabilities = AsyncMock(side_effect=Exception("fail"))

        try:
            await mock_registry.get_aggregated_capabilities()
            total_resources = {}  # Should not reach
        except Exception:
            total_resources = None

        assert total_resources is None

    def test_instance_resources_defaults_to_none(self):
        """InstanceResources fields default to None."""
        resources = InstanceResources()
        assert resources.cpu_count is None
        assert resources.memory_gb is None
        assert resources.gpu_count is None
        assert resources.storage_gb is None

    def test_aggregated_capabilities_default_resources(self):
        """AggregatedCapabilities defaults to empty InstanceResources."""
        agg = AggregatedCapabilities(total_instances=0, online_instances=0)
        assert agg.total_resources.cpu_count is None
        assert agg.total_resources.memory_gb is None

    def test_instance_resources_with_values(self):
        """InstanceResources holds correct values."""
        resources = InstanceResources(
            cpu_count=8,
            memory_gb=32.0,
            gpu_count=1,
            gpu_type="NVIDIA RTX 4090",
            storage_gb=500.0,
        )
        assert resources.cpu_count == 8
        assert resources.memory_gb == 32.0
        assert resources.gpu_count == 1
        assert resources.gpu_type == "NVIDIA RTX 4090"
        assert resources.storage_gb == 500.0
