"""Tests for compute models."""

import pytest
from datetime import datetime, timedelta, timezone

from models.compute import (
    ComputeInstance,
    InstanceStatus,
    InstanceCapabilities,
    InstanceResources,
    RegistrationRequest,
    RegistrationResponse,
    HeartbeatRequest,
    AggregatedCapabilities,
)


def test_instance_status_enum():
    """Test InstanceStatus enum."""
    assert InstanceStatus.ONLINE == "online"
    assert InstanceStatus.OFFLINE == "offline"
    assert InstanceStatus.DEGRADED == "degraded"
    assert InstanceStatus.ERROR == "error"


def test_instance_resources():
    """Test InstanceResources model."""
    resources = InstanceResources(
        cpu_count=8,
        memory_gb=32.0,
        gpu_count=1,
        gpu_type="NVIDIA RTX 4090",
        storage_gb=500.0
    )
    
    assert resources.cpu_count == 8
    assert resources.memory_gb == 32.0
    assert resources.gpu_count == 1


def test_instance_capabilities():
    """Test InstanceCapabilities model."""
    capabilities = InstanceCapabilities(
        agents=["agent-a", "agent-b"],
        tools=["tool-x", "tool-y"],
        resources=InstanceResources(cpu_count=4, memory_gb=16.0),
        features=["gpu-acceleration"]
    )
    
    assert len(capabilities.agents) == 2
    assert "agent-a" in capabilities.agents
    assert len(capabilities.tools) == 2
    assert capabilities.resources.cpu_count == 4


def test_compute_instance_creation():
    """Test ComputeInstance creation."""
    instance = ComputeInstance(
        instance_id="test-001",
        name="Test Instance",
        endpoint="http://localhost:8003",
        health_endpoint="http://localhost:8003/health",
        capabilities=InstanceCapabilities(agents=["agent-a"]),
        metadata={"location": "local"},
        status=InstanceStatus.ONLINE,
    )

    assert instance.instance_id == "test-001"
    assert instance.name == "Test Instance"
    assert instance.status == InstanceStatus.ONLINE
    assert instance.failed_health_checks == 0
    assert isinstance(instance.registered_at, datetime)


def test_compute_instance_is_healthy():
    """Test instance health check."""
    instance = ComputeInstance(
        instance_id="test-001",
        name="Test Instance",
        endpoint="http://localhost:8003",
        status=InstanceStatus.ONLINE,
    )

    # Just created, should be healthy
    assert instance.is_healthy() is True
    
    # Set old heartbeat
    instance.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=100)
    assert instance.is_healthy(max_heartbeat_age=90) is False
    
    # Offline status
    instance.status = InstanceStatus.OFFLINE
    assert instance.is_healthy() is False


def test_compute_instance_update_heartbeat():
    """Test heartbeat update."""
    instance = ComputeInstance(
        instance_id="test-001",
        name="Test Instance",
        endpoint="http://localhost:8003",
        status=InstanceStatus.DEGRADED
    )
    
    instance.failed_health_checks = 2
    old_heartbeat = instance.last_heartbeat
    
    # Update heartbeat
    instance.update_heartbeat()
    
    assert instance.last_heartbeat > old_heartbeat
    assert instance.failed_health_checks == 0
    assert instance.status == InstanceStatus.ONLINE


def test_registration_request():
    """Test RegistrationRequest model."""
    request = RegistrationRequest(
        instance_id="test-001",
        name="Test Instance",
        endpoint="http://localhost:8003",
        capabilities=InstanceCapabilities(agents=["agent-a"]),
        heartbeat_interval=30
    )
    
    assert request.instance_id == "test-001"
    assert request.heartbeat_interval == 30


def test_registration_request_validation():
    """Test RegistrationRequest validation."""
    # Invalid heartbeat interval (too low)
    with pytest.raises(Exception):
        RegistrationRequest(
            instance_id="test-001",
            name="Test Instance",
            endpoint="http://localhost:8003",
            heartbeat_interval=5  # Below minimum of 10
        )


def test_registration_response():
    """Test RegistrationResponse model."""
    response = RegistrationResponse(
        status="registered",
        instance_id="test-001",
        heartbeat_interval=30,
        heartbeat_endpoint="/api/v1/compute/test-001/health",
        message="Success"
    )
    
    assert response.status == "registered"
    assert response.heartbeat_interval == 30


def test_heartbeat_request():
    """Test HeartbeatRequest model."""
    request = HeartbeatRequest(
        status=InstanceStatus.ONLINE,
        metadata={"active_tasks": 3}
    )
    
    assert request.status == InstanceStatus.ONLINE
    assert request.metadata["active_tasks"] == 3


def test_aggregated_capabilities():
    """Test AggregatedCapabilities model."""
    agg = AggregatedCapabilities(
        total_instances=3,
        online_instances=2,
        agents={
            "agent-a": ["compute-001", "compute-002"],
            "agent-b": ["compute-003"]
        },
        tools={
            "tool-x": ["compute-001"]
        },
        total_resources=InstanceResources(cpu_count=24, memory_gb=96.0)
    )
    
    assert agg.total_instances == 3
    assert agg.online_instances == 2
    assert len(agg.agents) == 2
    assert len(agg.agents["agent-a"]) == 2

