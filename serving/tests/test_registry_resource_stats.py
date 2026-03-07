"""Unit tests for aggregate hardware resources in registry stats.

Verifies that get_stats() includes total_resources aggregated from
all registered compute instances (#207).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from models.compute import ComputeInstance, InstanceCapabilities, InstanceResources
from services.registry_service import ComputeRegistry


def _make_instance(instance_id, resources=None, status="online"):
    """Create a ComputeInstance with optional resources."""
    from models.compute import InstanceStatus
    inst = ComputeInstance(
        instance_id=instance_id,
        name=f"node-{instance_id}",
        endpoint=f"http://{instance_id}:9000",
        capabilities=InstanceCapabilities(resources=resources),
    )
    inst.status = InstanceStatus(status)
    return inst


@pytest.fixture
def registry():
    """Create a ComputeRegistry with a mocked storage backend."""
    storage = MagicMock()
    storage.load_all = AsyncMock(return_value=[])
    reg = ComputeRegistry(storage_backend=storage)
    return reg


class TestGetStatsWithResources:
    """Verify get_stats includes total_resources."""

    def test_empty_registry_returns_null_resources(self, registry):
        stats = registry.get_stats()
        assert "total_resources" in stats
        assert stats["total_resources"]["cpu_count"] is None
        assert stats["total_resources"]["memory_gb"] is None
        assert stats["total_resources"]["gpu_count"] is None
        assert stats["total_resources"]["gpu_type"] is None

    def test_single_instance_with_resources(self, registry):
        inst = _make_instance("c1", resources=InstanceResources(
            cpu_count=8, memory_gb=32.0, gpu_count=1, gpu_type="NVIDIA RTX 4090"
        ))
        registry._instances["c1"] = inst

        stats = registry.get_stats()
        res = stats["total_resources"]
        assert res["cpu_count"] == 8
        assert res["memory_gb"] == 32.0
        assert res["gpu_count"] == 1
        assert res["gpu_type"] == "NVIDIA RTX 4090"

    def test_multiple_instances_aggregated(self, registry):
        registry._instances["c1"] = _make_instance("c1", resources=InstanceResources(
            cpu_count=8, memory_gb=32.0, gpu_count=1, gpu_type="NVIDIA RTX 4090"
        ))
        registry._instances["c2"] = _make_instance("c2", resources=InstanceResources(
            cpu_count=16, memory_gb=64.0, gpu_count=2, gpu_type="NVIDIA RTX 4090"
        ))
        registry._instances["c3"] = _make_instance("c3", resources=InstanceResources(
            cpu_count=4, memory_gb=16.0
        ))

        stats = registry.get_stats()
        res = stats["total_resources"]
        assert res["cpu_count"] == 28
        assert res["memory_gb"] == 112.0
        assert res["gpu_count"] == 3
        assert res["gpu_type"] == "NVIDIA RTX 4090"

    def test_multiple_gpu_types_joined(self, registry):
        registry._instances["c1"] = _make_instance("c1", resources=InstanceResources(
            gpu_count=1, gpu_type="NVIDIA RTX 4090"
        ))
        registry._instances["c2"] = _make_instance("c2", resources=InstanceResources(
            gpu_count=2, gpu_type="NVIDIA A100"
        ))

        stats = registry.get_stats()
        res = stats["total_resources"]
        assert res["gpu_count"] == 3
        # Sorted alphabetically, comma-separated
        assert res["gpu_type"] == "NVIDIA A100, NVIDIA RTX 4090"

    def test_instance_without_resources_skipped(self, registry):
        registry._instances["c1"] = _make_instance("c1", resources=InstanceResources(
            cpu_count=8, memory_gb=32.0
        ))
        registry._instances["c2"] = _make_instance("c2", resources=None)

        stats = registry.get_stats()
        res = stats["total_resources"]
        assert res["cpu_count"] == 8
        assert res["memory_gb"] == 32.0

    def test_stats_still_includes_other_fields(self, registry):
        """Ensure adding total_resources didn't break existing fields."""
        stats = registry.get_stats()
        assert "total_instances" in stats
        assert "by_status" in stats
        assert "by_auth_status" in stats
        assert "total_agents" in stats
        assert "total_tools" in stats
