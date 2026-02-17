"""Tests for SSE connection manager."""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.sse_connection_manager import (
    SSEConnection,
    SSEConnectionManager,
    event_generator
)


class TestSSEConnection:
    """Tests for SSEConnection dataclass."""

    def test_create_connection(self):
        """Test creating an SSE connection."""
        conn = SSEConnection(
            compute_id="compute-001",
            capabilities=["coding", "testing"],
            resources={"cpu": 4, "memory": "16gb"}
        )

        assert conn.compute_id == "compute-001"
        assert conn.capabilities == ["coding", "testing"]
        assert conn.resources == {"cpu": 4, "memory": "16gb"}
        assert conn.status == "idle"
        assert conn.current_task_id is None
        assert isinstance(conn.connected_at, datetime)

    @pytest.mark.asyncio
    async def test_send_and_get_event(self):
        """Test queueing and retrieving events."""
        conn = SSEConnection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        # Send an event
        await conn.send_event("test_event", {"key": "value"})

        # Get the event
        event = await asyncio.wait_for(conn.get_event(), timeout=1.0)

        assert event["event"] == "test_event"
        assert event["data"] == {"key": "value"}


class TestSSEConnectionManager:
    """Tests for SSEConnectionManager."""

    @pytest.mark.asyncio
    async def test_register_connection(self):
        """Test registering a new connection."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            compute_id="compute-001",
            capabilities=["coding"],
            resources={"cpu": 2}
        )

        assert conn.compute_id == "compute-001"
        assert manager.get_connection("compute-001") is conn
        assert len(manager.list_connections()) == 1

    @pytest.mark.asyncio
    async def test_unregister_connection(self):
        """Test unregistering a connection."""
        manager = SSEConnectionManager()

        await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        result = await manager.unregister_connection("compute-001")

        assert result is True
        assert manager.get_connection("compute-001") is None
        assert len(manager.list_connections()) == 0

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_connection(self):
        """Test unregistering a nonexistent connection."""
        manager = SSEConnectionManager()

        result = await manager.unregister_connection("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_replace_existing_connection(self):
        """Test replacing an existing connection."""
        manager = SSEConnectionManager()

        # Register first connection
        conn1 = await manager.register_connection(
            compute_id="compute-001",
            capabilities=["old"],
            resources={}
        )

        # Register second connection with same ID
        conn2 = await manager.register_connection(
            compute_id="compute-001",
            capabilities=["new"],
            resources={}
        )

        # Should have replaced the old connection
        assert manager.get_connection("compute-001") is conn2
        assert conn2.capabilities == ["new"]
        assert len(manager.list_connections()) == 1

    @pytest.mark.asyncio
    async def test_send_event(self):
        """Test sending an event to a specific compute."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        result = await manager.send_event(
            "compute-001",
            "test_event",
            {"data": "value"}
        )

        assert result is True

        # Verify event was queued
        event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
        assert event["event"] == "test_event"

    @pytest.mark.asyncio
    async def test_send_event_nonexistent_compute(self):
        """Test sending event to nonexistent compute."""
        manager = SSEConnectionManager()

        result = await manager.send_event(
            "nonexistent",
            "test_event",
            {}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_event(self):
        """Test broadcasting event to all connections."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )
        conn2 = await manager.register_connection(
            compute_id="compute-002",
            capabilities=[],
            resources={}
        )

        count = await manager.broadcast_event(
            "broadcast_event",
            {"message": "hello"}
        )

        assert count == 2

        # Both should have received the event
        event1 = await asyncio.wait_for(conn1.get_event(), timeout=1.0)
        event2 = await asyncio.wait_for(conn2.get_event(), timeout=1.0)

        assert event1["event"] == "broadcast_event"
        assert event2["event"] == "broadcast_event"

    @pytest.mark.asyncio
    async def test_broadcast_with_filter(self):
        """Test broadcasting with filter function."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection(
            compute_id="compute-001",
            capabilities=["coding"],
            resources={}
        )
        conn2 = await manager.register_connection(
            compute_id="compute-002",
            capabilities=["testing"],
            resources={}
        )

        # Only send to connections with "coding" capability
        count = await manager.broadcast_event(
            "filtered_event",
            {},
            filter_fn=lambda c: "coding" in c.capabilities
        )

        assert count == 1

    @pytest.mark.asyncio
    async def test_send_merge_conflict(self):
        """Test sending merge_conflict event."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        result = await manager.send_merge_conflict(
            compute_id="compute-001",
            issue_id="issue-123",
            branch="feat/test",
            conflicting_files=["file1.py", "file2.py"],
            main_head="abc123"
        )

        assert result is True

        event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
        assert event["event"] == "merge_conflict"
        assert event["data"]["issue_id"] == "issue-123"
        assert event["data"]["conflicting_files"] == ["file1.py", "file2.py"]

    @pytest.mark.asyncio
    async def test_send_work_assigned_updates_status(self):
        """Test that work_assigned updates connection status."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        assert conn.status == "idle"
        assert conn.current_task_id is None

        await manager.send_work_assigned(
            compute_id="compute-001",
            task_id="task-123",
            title="Test Task",
            description="Description",
            branch_name="feat/test",
            skills={},
            context={},
            mcp_config={}
        )

        assert conn.status == "busy"
        assert conn.current_task_id == "task-123"

    @pytest.mark.asyncio
    async def test_send_work_completed_updates_status(self):
        """Test that work_completed updates connection status."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )
        conn.status = "busy"
        conn.current_task_id = "task-123"

        await manager.send_work_completed(
            compute_id="compute-001",
            issue_id="issue-123",
            branch="feat/test",
            merge_commit="def456"
        )

        assert conn.status == "idle"
        assert conn.current_task_id is None

    @pytest.mark.asyncio
    async def test_get_idle_connections(self):
        """Test getting idle connections."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )
        conn2 = await manager.register_connection(
            compute_id="compute-002",
            capabilities=[],
            resources={}
        )

        conn1.status = "busy"

        idle = manager.get_idle_connections()

        assert len(idle) == 1
        assert idle[0].compute_id == "compute-002"

    def test_get_stats(self):
        """Test getting connection statistics."""
        manager = SSEConnectionManager()

        stats = manager.get_stats()

        assert stats["total_connections"] == 0
        assert stats["idle"] == 0
        assert stats["busy"] == 0
        assert stats["draining"] == 0

    @pytest.mark.asyncio
    async def test_on_connect_handler(self):
        """Test connect handler callback."""
        manager = SSEConnectionManager()

        connected_ids = []

        async def on_connect(compute_id: str):
            connected_ids.append(compute_id)

        manager.on_connect(on_connect)

        await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        assert "compute-001" in connected_ids

    @pytest.mark.asyncio
    async def test_on_disconnect_handler(self):
        """Test disconnect handler callback."""
        manager = SSEConnectionManager()

        disconnected_ids = []

        async def on_disconnect(compute_id: str):
            disconnected_ids.append(compute_id)

        manager.on_disconnect(on_disconnect)

        await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )
        await manager.unregister_connection("compute-001")

        assert "compute-001" in disconnected_ids


class TestFindMatchingConnection:
    """Tests for find_matching_connection with round-robin selection."""

    @pytest.mark.asyncio
    async def test_round_robin_distributes_across_idle_nodes(self):
        """Test that consecutive calls rotate across idle compute nodes."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        selected = [
            manager.find_matching_connection(idle_only=True).compute_id
            for _ in range(6)
        ]

        # Should cycle through all three nodes twice
        assert selected == [
            "compute-001", "compute-002", "compute-003",
            "compute-001", "compute-002", "compute-003",
        ]

    @pytest.mark.asyncio
    async def test_round_robin_skips_busy_nodes(self):
        """Test that round-robin only selects from idle candidates."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        conn1.status = "busy"

        selected = [
            manager.find_matching_connection(idle_only=True).compute_id
            for _ in range(4)
        ]

        # Should only rotate between the two idle nodes
        assert selected == ["compute-002", "compute-003", "compute-002", "compute-003"]

    @pytest.mark.asyncio
    async def test_round_robin_returns_none_when_all_busy(self):
        """Test that None is returned when no idle nodes exist."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection("compute-001", capabilities=[], resources={})
        conn1.status = "busy"

        result = manager.find_matching_connection(idle_only=True)
        assert result is None

    @pytest.mark.asyncio
    async def test_specialization_scores_override_round_robin(self):
        """Test that specialization scores take priority over round-robin."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        scores = {"compute-001": 0.1, "compute-002": 0.9, "compute-003": 0.5}

        # Should always pick compute-002 (highest score) regardless of round-robin
        for _ in range(3):
            result = manager.find_matching_connection(
                idle_only=True, specialization_scores=scores
            )
            assert result.compute_id == "compute-002"

    @pytest.mark.asyncio
    async def test_round_robin_with_single_node(self):
        """Test round-robin with only one node always returns it."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})

        for _ in range(3):
            result = manager.find_matching_connection(idle_only=True)
            assert result.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_round_robin_with_label_filter(self):
        """Test round-robin respects label filtering."""
        manager = SSEConnectionManager()

        await manager.register_connection(
            "compute-001", capabilities=[], resources={}, labels=["gpu"]
        )
        await manager.register_connection(
            "compute-002", capabilities=[], resources={}, labels=["cpu"]
        )
        await manager.register_connection(
            "compute-003", capabilities=[], resources={}, labels=["gpu"]
        )

        selected = [
            manager.find_matching_connection(
                idle_only=True, required_labels=["gpu"]
            ).compute_id
            for _ in range(4)
        ]

        # Only gpu-labeled nodes should be selected
        assert all(cid in ("compute-001", "compute-003") for cid in selected)
        assert selected == ["compute-001", "compute-003", "compute-001", "compute-003"]

    @pytest.mark.asyncio
    async def test_round_robin_wraps_after_node_removal(self):
        """Test round-robin handles node removal gracefully."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        # Advance round-robin
        manager.find_matching_connection(idle_only=True)  # compute-001
        manager.find_matching_connection(idle_only=True)  # compute-002

        # Remove compute-003
        await manager.unregister_connection("compute-003")

        # Should wrap around with modulo on remaining 2 candidates
        result = manager.find_matching_connection(idle_only=True)
        assert result is not None
        assert result.compute_id in ("compute-001", "compute-002")


class TestPhaseSpecificRoundRobin:
    """Tests for phase-specific round-robin counter isolation."""

    @pytest.mark.asyncio
    async def test_phases_have_independent_counters(self):
        """Each phase should rotate independently through all nodes."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        # Decomposition: 3 calls
        decomp = [
            manager.find_matching_connection(idle_only=True, phase="decomposition").compute_id
            for _ in range(3)
        ]
        assert decomp == ["compute-001", "compute-002", "compute-003"]

        # Characterization starts its own rotation from the beginning
        char = [
            manager.find_matching_connection(idle_only=True, phase="characterization").compute_id
            for _ in range(3)
        ]
        assert char == ["compute-001", "compute-002", "compute-003"]

        # Work execution also starts its own rotation
        work = [
            manager.find_matching_connection(idle_only=True, phase="work_execution").compute_id
            for _ in range(3)
        ]
        assert work == ["compute-001", "compute-002", "compute-003"]

    @pytest.mark.asyncio
    async def test_interleaved_phases_dont_interfere(self):
        """Interleaving calls from different phases should not disrupt each other."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        # Interleave: decomp, char, work, decomp, char, work
        d1 = manager.find_matching_connection(idle_only=True, phase="decomposition").compute_id
        c1 = manager.find_matching_connection(idle_only=True, phase="characterization").compute_id
        w1 = manager.find_matching_connection(idle_only=True, phase="work_execution").compute_id
        d2 = manager.find_matching_connection(idle_only=True, phase="decomposition").compute_id
        c2 = manager.find_matching_connection(idle_only=True, phase="characterization").compute_id
        w2 = manager.find_matching_connection(idle_only=True, phase="work_execution").compute_id

        # Each phase should progress independently: 001 -> 002
        assert d1 == "compute-001"
        assert d2 == "compute-002"
        assert c1 == "compute-001"
        assert c2 == "compute-002"
        assert w1 == "compute-001"
        assert w2 == "compute-002"

    @pytest.mark.asyncio
    async def test_specialization_doesnt_advance_phase_counter(self):
        """Specialization-based selection should not affect round-robin counter."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        scores = {"compute-001": 0.1, "compute-002": 0.9, "compute-003": 0.5}

        # Work execution with specialization scores
        result = manager.find_matching_connection(
            idle_only=True, specialization_scores=scores, phase="work_execution"
        )
        assert result.compute_id == "compute-002"  # Highest score wins

        # Next work execution without scores should start from compute-001
        result = manager.find_matching_connection(idle_only=True, phase="work_execution")
        assert result.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_no_phase_uses_default_counter(self):
        """Calls without a phase parameter use a shared default counter."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})

        # Two calls without phase
        r1 = manager.find_matching_connection(idle_only=True).compute_id
        r2 = manager.find_matching_connection(idle_only=True).compute_id

        assert r1 == "compute-001"
        assert r2 == "compute-002"

        # Phase-based call should be independent
        r3 = manager.find_matching_connection(idle_only=True, phase="decomposition").compute_id
        assert r3 == "compute-001"  # Decomposition starts fresh

    @pytest.mark.asyncio
    async def test_phase_counter_with_busy_nodes(self):
        """Phase counter should work correctly when some nodes are busy."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        conn1.status = "busy"

        # Decomposition should rotate over idle nodes only
        selected = [
            manager.find_matching_connection(idle_only=True, phase="decomposition").compute_id
            for _ in range(4)
        ]
        assert selected == ["compute-002", "compute-003", "compute-002", "compute-003"]


class TestExcludeComputeIds:
    """Tests for exclude_compute_ids parameter (retry node rotation).

    Regression: retries should prefer different nodes than ones that previously
    failed for a given work item.

    See: https://github.com/Guarrdon/claudevn/issues/663
    """

    @pytest.mark.asyncio
    async def test_exclude_deprioritizes_failed_node(self):
        """Excluded nodes should not be selected when alternatives exist."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        # Exclude compute-001 (it failed before)
        result = manager.find_matching_connection(
            idle_only=True, exclude_compute_ids={"compute-001"}
        )
        assert result.compute_id != "compute-001"

    @pytest.mark.asyncio
    async def test_exclude_falls_back_to_excluded_as_last_resort(self):
        """If all non-excluded nodes are busy, excluded nodes should still be used."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection("compute-001", capabilities=[], resources={})
        conn2 = await manager.register_connection("compute-002", capabilities=[], resources={})

        # Make compute-002 busy
        conn2.status = "busy"

        # Exclude compute-001 (it failed before), but compute-002 is busy
        # Should fall back to compute-001 since it's the only idle node
        result = manager.find_matching_connection(
            idle_only=True, exclude_compute_ids={"compute-001"}
        )
        assert result is not None
        assert result.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_exclude_multiple_nodes(self):
        """Multiple nodes can be excluded."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        # Exclude both compute-001 and compute-002
        result = manager.find_matching_connection(
            idle_only=True, exclude_compute_ids={"compute-001", "compute-002"}
        )
        assert result.compute_id == "compute-003"

    @pytest.mark.asyncio
    async def test_exclude_all_nodes_falls_back(self):
        """If all candidates are excluded, still return one (last resort)."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})

        result = manager.find_matching_connection(
            idle_only=True, exclude_compute_ids={"compute-001", "compute-002"}
        )
        # Should still return a node since exclusions are soft (deprioritize, not hard exclude)
        assert result is not None

    @pytest.mark.asyncio
    async def test_exclude_with_round_robin(self):
        """Exclusions should work with round-robin rotation."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})
        await manager.register_connection("compute-003", capabilities=[], resources={})

        # With compute-001 excluded, round-robin should rotate between 002 and 003
        selected = [
            manager.find_matching_connection(
                idle_only=True, exclude_compute_ids={"compute-001"}
            ).compute_id
            for _ in range(4)
        ]
        assert "compute-001" not in selected
        assert set(selected) == {"compute-002", "compute-003"}

    @pytest.mark.asyncio
    async def test_exclude_none_has_no_effect(self):
        """Passing None for exclude should work normally."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})

        result = manager.find_matching_connection(
            idle_only=True, exclude_compute_ids=None
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_exclude_empty_set_has_no_effect(self):
        """Passing empty set for exclude should work normally."""
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})

        result = manager.find_matching_connection(
            idle_only=True, exclude_compute_ids=set()
        )
        assert result is not None


class TestEventGenerator:
    """Tests for event_generator function."""

    @pytest.mark.asyncio
    async def test_event_generator_format(self):
        """Test that event generator produces correct SSE format."""
        conn = SSEConnection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        # Queue an event
        await conn.send_event("test_event", {"key": "value"})

        # Get one event from generator
        gen = event_generator(conn)
        event_str = await asyncio.wait_for(gen.__anext__(), timeout=1.0)

        # Verify SSE format
        assert "event: test_event\n" in event_str
        assert 'data: {"key": "value"}\n' in event_str
        assert event_str.endswith("\n\n")


class TestAuthStatusFiltering:
    """Tests for auth_status filtering in find_matching_connection.

    Regression test for issue #788: SSE find_matching_connection should filter by auth_status.
    https://github.com/Guarrdon/claudevn/issues/788
    """

    @pytest.mark.asyncio
    async def test_filters_by_auth_status_when_registry_available(self):
        """Test that only AUTHORIZED compute instances are selected when registry is provided."""
        from services.registry_service import ComputeRegistry
        from models.compute import ComputeInstance, ComputeAuthStatus, InstanceStatus, InstanceCapabilities

        # Create registry with compute instances
        registry = ComputeRegistry()

        # Add authorized instance
        instance1 = ComputeInstance(
            instance_id="compute-001",
            name="Authorized Instance",
            endpoint="http://localhost:8001",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.AUTHORIZED,
            capabilities=InstanceCapabilities()
        )
        await registry.add_instance(instance1)

        # Add unauthorized instance
        instance2 = ComputeInstance(
            instance_id="compute-002",
            name="Unauthorized Instance",
            endpoint="http://localhost:8002",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.UNAUTHORIZED,
            capabilities=InstanceCapabilities()
        )
        await registry.add_instance(instance2)

        # Create SSE manager with registry
        manager = SSEConnectionManager(registry=registry)

        # Register SSE connections for both
        await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )
        await manager.register_connection(
            compute_id="compute-002",
            capabilities=[],
            resources={}
        )

        # Should only select the authorized instance
        result = manager.find_matching_connection(idle_only=True)
        assert result is not None
        assert result.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_authorized_instances(self):
        """Test that None is returned when all instances are unauthorized."""
        from services.registry_service import ComputeRegistry
        from models.compute import ComputeInstance, ComputeAuthStatus, InstanceStatus, InstanceCapabilities

        registry = ComputeRegistry()

        # Add only unauthorized instance
        instance = ComputeInstance(
            instance_id="compute-001",
            name="Unauthorized Instance",
            endpoint="http://localhost:8001",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.UNAUTHORIZED,
            capabilities=InstanceCapabilities()
        )
        await registry.add_instance(instance)

        manager = SSEConnectionManager(registry=registry)
        await manager.register_connection(
            compute_id="compute-001",
            capabilities=[],
            resources={}
        )

        # Should return None since no authorized instances
        result = manager.find_matching_connection(idle_only=True)
        assert result is None

    @pytest.mark.asyncio
    async def test_filters_expired_auth_status(self):
        """Test that EXPIRED auth instances are also filtered out."""
        from services.registry_service import ComputeRegistry
        from models.compute import ComputeInstance, ComputeAuthStatus, InstanceStatus, InstanceCapabilities

        registry = ComputeRegistry()

        # Add authorized instance
        instance1 = ComputeInstance(
            instance_id="compute-001",
            name="Authorized Instance",
            endpoint="http://localhost:8001",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.AUTHORIZED,
            capabilities=InstanceCapabilities()
        )
        await registry.add_instance(instance1)

        # Add expired auth instance
        instance2 = ComputeInstance(
            instance_id="compute-002",
            name="Expired Instance",
            endpoint="http://localhost:8002",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.EXPIRED,
            capabilities=InstanceCapabilities()
        )
        await registry.add_instance(instance2)

        manager = SSEConnectionManager(registry=registry)
        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})

        # Should only select the authorized instance
        result = manager.find_matching_connection(idle_only=True)
        assert result is not None
        assert result.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_auth_filter_works_with_other_filters(self):
        """Test that auth filtering works alongside label/tool/capability filters."""
        from services.registry_service import ComputeRegistry
        from models.compute import ComputeInstance, ComputeAuthStatus, InstanceStatus, InstanceCapabilities

        registry = ComputeRegistry()

        # Authorized with label "gpu"
        instance1 = ComputeInstance(
            instance_id="compute-001",
            name="Authorized GPU",
            endpoint="http://localhost:8001",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.AUTHORIZED,
            capabilities=InstanceCapabilities(labels=["gpu"])
        )
        await registry.add_instance(instance1)

        # Unauthorized with label "gpu" (should be filtered)
        instance2 = ComputeInstance(
            instance_id="compute-002",
            name="Unauthorized GPU",
            endpoint="http://localhost:8002",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.UNAUTHORIZED,
            capabilities=InstanceCapabilities(labels=["gpu"])
        )
        await registry.add_instance(instance2)

        # Authorized without label "gpu"
        instance3 = ComputeInstance(
            instance_id="compute-003",
            name="Authorized CPU",
            endpoint="http://localhost:8003",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.AUTHORIZED,
            capabilities=InstanceCapabilities(labels=["cpu"])
        )
        await registry.add_instance(instance3)

        manager = SSEConnectionManager(registry=registry)
        await manager.register_connection("compute-001", capabilities=[], resources={}, labels=["gpu"])
        await manager.register_connection("compute-002", capabilities=[], resources={}, labels=["gpu"])
        await manager.register_connection("compute-003", capabilities=[], resources={}, labels=["cpu"])

        # Should select only compute-001 (authorized + has gpu label)
        result = manager.find_matching_connection(
            idle_only=True,
            required_labels=["gpu"]
        )
        assert result is not None
        assert result.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_no_registry_skips_auth_filtering(self):
        """Test that auth filtering is skipped when no registry is provided (backward compatibility)."""
        # Manager without registry
        manager = SSEConnectionManager()

        await manager.register_connection("compute-001", capabilities=[], resources={})
        await manager.register_connection("compute-002", capabilities=[], resources={})

        # Should work normally without auth filtering
        result = manager.find_matching_connection(idle_only=True)
        assert result is not None
        # No auth filtering, so either instance could be selected
        assert result.compute_id in ["compute-001", "compute-002"]

    @pytest.mark.asyncio
    async def test_auth_filter_with_round_robin(self):
        """Test that auth filtering works with round-robin selection."""
        from services.registry_service import ComputeRegistry
        from models.compute import ComputeInstance, ComputeAuthStatus, InstanceStatus, InstanceCapabilities

        registry = ComputeRegistry()

        # Two authorized instances
        for i in range(1, 3):
            instance = ComputeInstance(
                instance_id=f"compute-00{i}",
                name=f"Authorized {i}",
                endpoint=f"http://localhost:800{i}",
                status=InstanceStatus.ONLINE,
                auth_status=ComputeAuthStatus.AUTHORIZED,
                capabilities=InstanceCapabilities()
            )
            await registry.add_instance(instance)

        # One unauthorized instance
        instance3 = ComputeInstance(
            instance_id="compute-003",
            name="Unauthorized",
            endpoint="http://localhost:8003",
            status=InstanceStatus.ONLINE,
            auth_status=ComputeAuthStatus.UNAUTHORIZED,
            capabilities=InstanceCapabilities()
        )
        await registry.add_instance(instance3)

        manager = SSEConnectionManager(registry=registry)
        for i in range(1, 4):
            await manager.register_connection(f"compute-00{i}", capabilities=[], resources={})

        # Should round-robin between only the authorized instances
        selected = [
            manager.find_matching_connection(idle_only=True).compute_id
            for _ in range(4)
        ]

        assert selected == ["compute-001", "compute-002", "compute-001", "compute-002"]
        assert "compute-003" not in selected
