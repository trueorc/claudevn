"""Tests for compute registry service."""

import pytest
from datetime import datetime, timedelta, timezone

from models.compute import (
    ComputeInstance,
    ComputeAuthStatus,
    InstanceStatus,
    InstanceCapabilities,
    InstanceResources,
)
from services.registry_service import ComputeRegistry


@pytest.fixture
def registry():
    """Create a registry for testing."""
    return ComputeRegistry()


@pytest.fixture
def sample_instance():
    """Create a sample instance for testing."""
    return ComputeInstance(
        instance_id="test-001",
        name="Test Instance",
        endpoint="http://localhost:8003",
        capabilities=InstanceCapabilities(
            agents=["agent-a", "agent-b"],
            tools=["tool-x"],
            resources=InstanceResources(cpu_count=8, memory_gb=16.0)
        )
    )


@pytest.mark.asyncio
async def test_add_instance(registry, sample_instance):
    """Test adding an instance."""
    added = await registry.add_instance(sample_instance)
    
    assert added.instance_id == "test-001"
    assert added.status == InstanceStatus.ONLINE
    assert added.failed_health_checks == 0


@pytest.mark.asyncio
async def test_add_duplicate_instance(registry, sample_instance):
    """Test adding duplicate instance raises error."""
    await registry.add_instance(sample_instance)
    
    # Try to add again
    with pytest.raises(ValueError, match="already registered"):
        await registry.add_instance(sample_instance)


@pytest.mark.asyncio
async def test_get_instance(registry, sample_instance):
    """Test getting an instance by ID."""
    await registry.add_instance(sample_instance)
    
    retrieved = await registry.get_instance("test-001")
    
    assert retrieved is not None
    assert retrieved.instance_id == "test-001"
    assert retrieved.name == "Test Instance"


@pytest.mark.asyncio
async def test_get_nonexistent_instance(registry):
    """Test getting nonexistent instance returns None."""
    retrieved = await registry.get_instance("nonexistent")
    assert retrieved is None


@pytest.mark.asyncio
async def test_remove_instance(registry, sample_instance):
    """Test removing an instance."""
    await registry.add_instance(sample_instance)
    
    removed = await registry.remove_instance("test-001")
    assert removed is True
    
    # Should not be retrievable
    retrieved = await registry.get_instance("test-001")
    assert retrieved is None


@pytest.mark.asyncio
async def test_remove_nonexistent_instance(registry):
    """Test removing nonexistent instance returns False."""
    removed = await registry.remove_instance("nonexistent")
    assert removed is False


@pytest.mark.asyncio
async def test_list_instances(registry):
    """Test listing instances."""
    # Add multiple instances
    for i in range(3):
        instance = ComputeInstance(
            instance_id=f"test-{i:03d}",
            name=f"Test Instance {i}",
            endpoint=f"http://localhost:800{i}",
            capabilities=InstanceCapabilities(agents=[f"agent-{i}"])
        )
        await registry.add_instance(instance)
    
    instances = await registry.list_instances()
    
    assert len(instances) == 3


@pytest.mark.asyncio
async def test_list_instances_with_status_filter(registry):
    """Test listing instances with status filter."""
    # Add online instance
    online_instance = ComputeInstance(
        instance_id="test-online",
        name="Online Instance",
        endpoint="http://localhost:8003",
        status=InstanceStatus.ONLINE
    )
    await registry.add_instance(online_instance)
    
    # Add offline instance
    offline_instance = ComputeInstance(
        instance_id="test-offline",
        name="Offline Instance",
        endpoint="http://localhost:8004",
        status=InstanceStatus.OFFLINE
    )
    await registry.add_instance(offline_instance)
    
    # List online only
    online_list = await registry.list_instances(status=InstanceStatus.ONLINE)
    assert len(online_list) == 1
    assert online_list[0].instance_id == "test-online"
    
    # List offline only
    offline_list = await registry.list_instances(status=InstanceStatus.OFFLINE)
    assert len(offline_list) == 1
    assert offline_list[0].instance_id == "test-offline"


@pytest.mark.asyncio
async def test_get_by_capability_agent(registry):
    """Test finding instances by agent capability."""
    # Add instances with different agents
    instance1 = ComputeInstance(
        instance_id="test-001",
        name="Instance 1",
        endpoint="http://localhost:8003",
        capabilities=InstanceCapabilities(agents=["agent-a", "agent-b"])
    )
    await registry.add_instance(instance1)
    
    instance2 = ComputeInstance(
        instance_id="test-002",
        name="Instance 2",
        endpoint="http://localhost:8004",
        capabilities=InstanceCapabilities(agents=["agent-b", "agent-c"])
    )
    await registry.add_instance(instance2)
    
    # Find by agent-a
    instances_a = await registry.get_by_capability(agent_id="agent-a")
    assert len(instances_a) == 1
    assert instances_a[0].instance_id == "test-001"
    
    # Find by agent-b
    instances_b = await registry.get_by_capability(agent_id="agent-b")
    assert len(instances_b) == 2


@pytest.mark.asyncio
async def test_get_by_capability_tool(registry):
    """Test finding instances by tool capability."""
    instance1 = ComputeInstance(
        instance_id="test-001",
        name="Instance 1",
        endpoint="http://localhost:8003",
        capabilities=InstanceCapabilities(tools=["tool-x", "tool-y"])
    )
    await registry.add_instance(instance1)
    
    instance2 = ComputeInstance(
        instance_id="test-002",
        name="Instance 2",
        endpoint="http://localhost:8004",
        capabilities=InstanceCapabilities(tools=["tool-y", "tool-z"])
    )
    await registry.add_instance(instance2)
    
    # Find by tool-x
    instances_x = await registry.get_by_capability(tool_id="tool-x")
    assert len(instances_x) == 1
    assert instances_x[0].instance_id == "test-001"
    
    # Find by tool-y
    instances_y = await registry.get_by_capability(tool_id="tool-y")
    assert len(instances_y) == 2


@pytest.mark.asyncio
async def test_get_by_capability_online_only(registry):
    """Test online_only filter in capability search."""
    online_instance = ComputeInstance(
        instance_id="test-online",
        name="Online Instance",
        endpoint="http://localhost:8003",
        status=InstanceStatus.ONLINE,
        capabilities=InstanceCapabilities(agents=["agent-a"])
    )
    await registry.add_instance(online_instance)
    
    offline_instance = ComputeInstance(
        instance_id="test-offline",
        name="Offline Instance",
        endpoint="http://localhost:8004",
        status=InstanceStatus.OFFLINE,
        capabilities=InstanceCapabilities(agents=["agent-a"])
    )
    await registry.add_instance(offline_instance)
    
    # Find online only
    online_only = await registry.get_by_capability(agent_id="agent-a", online_only=True)
    assert len(online_only) == 1
    assert online_only[0].instance_id == "test-online"
    
    # Find all
    all_instances = await registry.get_by_capability(agent_id="agent-a", online_only=False)
    assert len(all_instances) == 2


@pytest.mark.asyncio
async def test_update_status(registry, sample_instance):
    """Test updating instance status."""
    await registry.add_instance(sample_instance)
    
    updated = await registry.update_status(
        "test-001",
        InstanceStatus.DEGRADED,
        metadata={"reason": "high load"}
    )
    
    assert updated is True
    
    instance = await registry.get_instance("test-001")
    assert instance.status == InstanceStatus.DEGRADED
    assert instance.metadata["reason"] == "high load"


@pytest.mark.asyncio
async def test_update_heartbeat(registry, sample_instance):
    """Test updating instance heartbeat."""
    await registry.add_instance(sample_instance)
    
    # Set old heartbeat
    instance = await registry.get_instance("test-001")
    old_heartbeat = instance.last_heartbeat - timedelta(seconds=60)
    instance.last_heartbeat = old_heartbeat
    instance.failed_health_checks = 2
    instance.status = InstanceStatus.DEGRADED
    
    # Update heartbeat
    updated = await registry.update_heartbeat(
        "test-001",
        metadata={"active_tasks": 3}
    )
    
    assert updated is True
    
    instance = await registry.get_instance("test-001")
    assert instance.last_heartbeat > old_heartbeat
    assert instance.failed_health_checks == 0
    assert instance.status == InstanceStatus.ONLINE
    assert instance.metadata["active_tasks"] == 3


@pytest.mark.asyncio
async def test_update_instance(registry, sample_instance):
    """Test updating instance information."""
    await registry.add_instance(sample_instance)
    
    new_capabilities = InstanceCapabilities(
        agents=["agent-c", "agent-d"],
        tools=["tool-z"]
    )
    
    updated = await registry.update_instance(
        "test-001",
        name="Updated Name",
        capabilities=new_capabilities,
        metadata={"new_key": "new_value"}
    )
    
    assert updated is not None
    assert updated.name == "Updated Name"
    assert "agent-c" in updated.capabilities.agents
    assert updated.metadata["new_key"] == "new_value"


@pytest.mark.asyncio
async def test_get_aggregated_capabilities(registry):
    """Test getting aggregated capabilities."""
    # Add multiple instances
    instance1 = ComputeInstance(
        instance_id="test-001",
        name="Instance 1",
        endpoint="http://localhost:8003",
        capabilities=InstanceCapabilities(
            agents=["agent-a", "agent-b"],
            tools=["tool-x"],
            resources=InstanceResources(cpu_count=8, memory_gb=16.0)
        )
    )
    await registry.add_instance(instance1)
    
    instance2 = ComputeInstance(
        instance_id="test-002",
        name="Instance 2",
        endpoint="http://localhost:8004",
        capabilities=InstanceCapabilities(
            agents=["agent-b", "agent-c"],
            tools=["tool-y"],
            resources=InstanceResources(cpu_count=4, memory_gb=8.0, gpu_count=1)
        )
    )
    await registry.add_instance(instance2)
    
    agg = await registry.get_aggregated_capabilities()
    
    assert agg.total_instances == 2
    assert agg.online_instances == 2
    assert len(agg.agents) == 3  # agent-a, agent-b, agent-c
    assert len(agg.agents["agent-b"]) == 2  # Both instances have agent-b
    assert agg.total_resources.cpu_count == 12  # 8 + 4
    assert agg.total_resources.memory_gb == 24.0  # 16 + 8
    assert agg.total_resources.gpu_count == 1


@pytest.mark.asyncio
async def test_check_health(registry):
    """Test health checking."""
    # Add instance with old heartbeat
    instance = ComputeInstance(
        instance_id="test-001",
        name="Test Instance",
        endpoint="http://localhost:8003"
    )
    await registry.add_instance(instance)
    
    # Set old heartbeat
    retrieved = await registry.get_instance("test-001")
    retrieved.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=100)
    
    # Run health check
    results = await registry.check_health(
        max_heartbeat_age=90,
        degraded_threshold=60
    )
    
    assert results["total_instances"] == 1
    assert len(results["status_changes"]) == 1
    assert results["status_changes"][0]["new_status"] == "offline"


@pytest.mark.asyncio
async def test_get_stats(registry):
    """Test getting registry statistics."""
    # Add some instances
    for i in range(3):
        instance = ComputeInstance(
            instance_id=f"test-{i:03d}",
            name=f"Instance {i}",
            endpoint=f"http://localhost:800{i}",
            capabilities=InstanceCapabilities(
                agents=[f"agent-{i}"],
                tools=[f"tool-{i}"]
            )
        )
        await registry.add_instance(instance)

    stats = registry.get_stats()

    assert stats["total_instances"] == 3
    assert stats["by_status"]["online"] == 3
    assert stats["total_agents"] == 3
    assert stats["total_tools"] == 3


# =============================================================================
# Label and Tools Available Tests (Issue #125)
# =============================================================================


@pytest.fixture
def instance_with_labels():
    """Create an instance with labels and tools_available."""
    return ComputeInstance(
        instance_id="labeled-001",
        name="Labeled Instance",
        endpoint="http://localhost:8003",
        auth_status=ComputeAuthStatus.AUTHORIZED,
        capabilities=InstanceCapabilities(
            agents=["code-writer"],
            tools=["python-executor"],
            labels=["production-access", "database-admin"],
            tools_available=["deploy_prod", "db_migrate"]
        )
    )


@pytest.mark.asyncio
async def test_add_instance_with_labels(registry, instance_with_labels):
    """Test adding an instance with labels and tools_available."""
    added = await registry.add_instance(instance_with_labels)

    assert added.instance_id == "labeled-001"
    assert "production-access" in added.capabilities.labels
    assert "database-admin" in added.capabilities.labels
    assert "deploy_prod" in added.capabilities.tools_available
    assert "db_migrate" in added.capabilities.tools_available


@pytest.mark.asyncio
async def test_get_by_label(registry, instance_with_labels):
    """Test finding instances by routing label."""
    await registry.add_instance(instance_with_labels)

    # Add another instance without the labels
    standard_instance = ComputeInstance(
        instance_id="standard-001",
        name="Standard Instance",
        endpoint="http://localhost:8004",
        capabilities=InstanceCapabilities(
            agents=["code-writer"],
            labels=["standard"]
        )
    )
    await registry.add_instance(standard_instance)

    # Find by production-access label
    prod_instances = await registry.get_by_label(label="production-access")
    assert len(prod_instances) == 1
    assert prod_instances[0].instance_id == "labeled-001"

    # Find by standard label
    std_instances = await registry.get_by_label(label="standard")
    assert len(std_instances) == 1
    assert std_instances[0].instance_id == "standard-001"


@pytest.mark.asyncio
async def test_get_by_tool_available(registry, instance_with_labels):
    """Test finding instances by available tool."""
    await registry.add_instance(instance_with_labels)

    # Find by deploy_prod tool
    deploy_instances = await registry.get_by_tool_available(tool="deploy_prod")
    assert len(deploy_instances) == 1
    assert deploy_instances[0].instance_id == "labeled-001"

    # Find by db_migrate tool
    db_instances = await registry.get_by_tool_available(tool="db_migrate")
    assert len(db_instances) == 1
    assert db_instances[0].instance_id == "labeled-001"


@pytest.mark.asyncio
async def test_get_by_label_online_only(registry, instance_with_labels):
    """Test online_only filter in label search."""
    await registry.add_instance(instance_with_labels)

    # Add offline instance with same label
    offline_instance = ComputeInstance(
        instance_id="offline-001",
        name="Offline Instance",
        endpoint="http://localhost:8004",
        status=InstanceStatus.OFFLINE,
        capabilities=InstanceCapabilities(labels=["production-access"])
    )
    await registry.add_instance(offline_instance)

    # Find online only
    online_only = await registry.get_by_label(label="production-access", online_only=True)
    assert len(online_only) == 1
    assert online_only[0].instance_id == "labeled-001"

    # Find all
    all_instances = await registry.get_by_label(label="production-access", online_only=False)
    assert len(all_instances) == 2


@pytest.mark.asyncio
async def test_find_matching_compute_by_labels(registry, instance_with_labels):
    """Test finding compute by required labels."""
    await registry.add_instance(instance_with_labels)

    # Add standard instance
    standard_instance = ComputeInstance(
        instance_id="standard-001",
        name="Standard Instance",
        endpoint="http://localhost:8004",
        capabilities=InstanceCapabilities(labels=["standard"])
    )
    await registry.add_instance(standard_instance)

    # Find compute requiring production-access
    match = await registry.find_matching_compute(required_labels=["production-access"])
    assert match is not None
    assert match.instance_id == "labeled-001"

    # Find compute requiring multiple labels
    match = await registry.find_matching_compute(
        required_labels=["production-access", "database-admin"]
    )
    assert match is not None
    assert match.instance_id == "labeled-001"

    # Find compute requiring label that no one has
    match = await registry.find_matching_compute(required_labels=["nonexistent"])
    assert match is None


@pytest.mark.asyncio
async def test_find_matching_compute_by_tools(registry, instance_with_labels):
    """Test finding compute by required tools."""
    await registry.add_instance(instance_with_labels)

    # Find compute requiring deploy_prod tool
    match = await registry.find_matching_compute(required_tools=["deploy_prod"])
    assert match is not None
    assert match.instance_id == "labeled-001"

    # Find compute requiring multiple tools
    match = await registry.find_matching_compute(
        required_tools=["deploy_prod", "db_migrate"]
    )
    assert match is not None
    assert match.instance_id == "labeled-001"

    # Find compute requiring tool that no one has
    match = await registry.find_matching_compute(required_tools=["nonexistent"])
    assert match is None


@pytest.mark.asyncio
async def test_find_matching_compute_combined(registry, instance_with_labels):
    """Test finding compute with combined requirements."""
    await registry.add_instance(instance_with_labels)

    # Add another instance with different capabilities
    other_instance = ComputeInstance(
        instance_id="other-001",
        name="Other Instance",
        endpoint="http://localhost:8004",
        auth_status=ComputeAuthStatus.AUTHORIZED,
        capabilities=InstanceCapabilities(
            agents=["code-writer"],
            labels=["production-access"],
            tools_available=["other_tool"]
        )
    )
    await registry.add_instance(other_instance)

    # Find compute requiring specific labels, tools, and capabilities
    match = await registry.find_matching_compute(
        required_labels=["production-access", "database-admin"],
        required_tools=["deploy_prod"],
        required_capabilities=["code-writer"]
    )
    assert match is not None
    assert match.instance_id == "labeled-001"


@pytest.mark.asyncio
async def test_label_indexing_on_add(registry, instance_with_labels):
    """Test that labels are indexed when instance is added."""
    await registry.add_instance(instance_with_labels)

    # Check internal capability index
    assert "label:production-access" in registry._capability_index
    assert "labeled-001" in registry._capability_index["label:production-access"]
    assert "label:database-admin" in registry._capability_index
    assert "labeled-001" in registry._capability_index["label:database-admin"]


@pytest.mark.asyncio
async def test_tools_available_indexing_on_add(registry, instance_with_labels):
    """Test that tools_available are indexed when instance is added."""
    await registry.add_instance(instance_with_labels)

    # Check internal capability index
    assert "tool_available:deploy_prod" in registry._capability_index
    assert "labeled-001" in registry._capability_index["tool_available:deploy_prod"]
    assert "tool_available:db_migrate" in registry._capability_index
    assert "labeled-001" in registry._capability_index["tool_available:db_migrate"]


@pytest.mark.asyncio
async def test_label_indexing_on_remove(registry, instance_with_labels):
    """Test that labels are removed from index when instance is removed."""
    await registry.add_instance(instance_with_labels)

    # Verify indexed
    assert "label:production-access" in registry._capability_index

    # Remove instance
    await registry.remove_instance("labeled-001")

    # Verify removed from index
    assert "label:production-access" not in registry._capability_index


@pytest.mark.asyncio
async def test_get_aggregated_capabilities_with_labels(registry, instance_with_labels):
    """Test that aggregated capabilities include labels and tools_available."""
    await registry.add_instance(instance_with_labels)

    # Add another instance with different labels
    other_instance = ComputeInstance(
        instance_id="other-001",
        name="Other Instance",
        endpoint="http://localhost:8004",
        capabilities=InstanceCapabilities(
            labels=["production-access", "security-tools"],
            tools_available=["security_scan"]
        )
    )
    await registry.add_instance(other_instance)

    agg = await registry.get_aggregated_capabilities()

    # Check labels aggregation
    assert "production-access" in agg.labels
    assert len(agg.labels["production-access"]) == 2  # Both instances
    assert "database-admin" in agg.labels
    assert len(agg.labels["database-admin"]) == 1  # Only labeled-001
    assert "security-tools" in agg.labels
    assert len(agg.labels["security-tools"]) == 1  # Only other-001

    # Check tools_available aggregation
    assert "deploy_prod" in agg.tools_available
    assert "db_migrate" in agg.tools_available
    assert "security_scan" in agg.tools_available


@pytest.mark.asyncio
async def test_get_stats_includes_labels_and_tools(registry, instance_with_labels):
    """Test that stats include label and tools_available counts."""
    await registry.add_instance(instance_with_labels)

    stats = registry.get_stats()

    assert stats["total_labels"] == 2  # production-access, database-admin
    assert stats["total_tools_available"] == 2  # deploy_prod, db_migrate

