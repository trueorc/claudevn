"""Tests for multi-compute coordination scenarios.

Covers:
- Multi-instance registration (5+ simultaneous computes)
- Work distribution across available compute instances
- Resource contention and assignment locking
- Failure scenarios (reassignment, partial cluster failure, restarts)

Issue: #305
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.compute import (
    ComputeInstance,
    InstanceCapabilities,
    InstanceResources,
    InstanceStatus,
)
from models.work_map import (
    WorkItem,
    WorkPriority,
    WorkStatus,
)
from services.assignment_service import AssignmentService
from services.registry_service import ComputeRegistry
from services.sse_connection_manager import SSEConnection, SSEConnectionManager


# =============================================================================
# Helpers
# =============================================================================


def _make_compute_instance(
    instance_id: str,
    agents: list[str] | None = None,
    labels: list[str] | None = None,
    tools_available: list[str] | None = None,
    status: InstanceStatus = InstanceStatus.ONLINE,
    project_ids: list[str] | None = None,
) -> ComputeInstance:
    """Create a ComputeInstance for testing."""
    return ComputeInstance(
        instance_id=instance_id,
        name=f"test-{instance_id}",
        endpoint=f"http://{instance_id}:8003",
        capabilities=InstanceCapabilities(
            agents=agents or ["coding"],
            tools=[],
            resources=InstanceResources(cpu_count=4, memory_gb=16.0),
            labels=labels or [],
            tools_available=tools_available or [],
        ),
        status=status,
        project_ids=project_ids or ["*"],
    )


def _make_work_item(
    work_id: str,
    status: WorkStatus = WorkStatus.PENDING,
    priority: WorkPriority = WorkPriority.NORMAL,
    required_capabilities: list[str] | None = None,
    required_labels: list[str] | None = None,
    required_tools: list[str] | None = None,
    depends_on: list[str] | None = None,
    assigned_to: str | None = None,
    project_id: str = "project-1",
) -> WorkItem:
    """Create a WorkItem for testing."""
    return WorkItem(
        work_id=work_id,
        title=f"Test work {work_id}",
        description=f"Description for {work_id}",
        status=status,
        priority=priority,
        required_capabilities=required_capabilities or [],
        required_labels=required_labels or [],
        required_tools=required_tools or [],
        required_skills=["coding"],
        depends_on=depends_on or [],
        assigned_to=assigned_to,
        project_id=project_id,
        branch_name=f"work/{work_id}",
        base_branch="main",
    )


# =============================================================================
# Multi-Instance Registration Tests
# =============================================================================


class TestMultiInstanceRegistration:
    """Test 5+ compute instances registering simultaneously."""

    @pytest.mark.asyncio
    async def test_five_instances_register_simultaneously(self):
        """5 compute instances can register and be tracked correctly."""
        registry = ComputeRegistry()

        instances = [
            _make_compute_instance(f"compute-{i:03d}")
            for i in range(1, 6)
        ]

        results = await asyncio.gather(
            *[registry.add_instance(inst) for inst in instances]
        )

        assert len(results) == 5
        all_instances = await registry.list_instances()
        assert len(all_instances) == 5

    @pytest.mark.asyncio
    async def test_ten_instances_register_simultaneously(self):
        """10 compute instances can register without conflict."""
        registry = ComputeRegistry()

        instances = [
            _make_compute_instance(f"compute-{i:03d}")
            for i in range(1, 11)
        ]

        await asyncio.gather(
            *[registry.add_instance(inst) for inst in instances]
        )

        all_instances = await registry.list_instances(limit=20)
        assert len(all_instances) == 10

    @pytest.mark.asyncio
    async def test_registry_tracks_all_instances_by_id(self):
        """Each registered instance is retrievable by its ID."""
        registry = ComputeRegistry()

        for i in range(1, 6):
            inst = _make_compute_instance(f"compute-{i:03d}")
            await registry.add_instance(inst)

        for i in range(1, 6):
            instance = await registry.get_instance(f"compute-{i:03d}")
            assert instance is not None
            assert instance.instance_id == f"compute-{i:03d}"

    @pytest.mark.asyncio
    async def test_deregistration_does_not_affect_others(self):
        """Removing one instance does not affect the remaining instances."""
        registry = ComputeRegistry()

        for i in range(1, 6):
            inst = _make_compute_instance(f"compute-{i:03d}")
            await registry.add_instance(inst)

        removed = await registry.remove_instance("compute-003")
        assert removed is True

        remaining = await registry.list_instances()
        assert len(remaining) == 4

        assert await registry.get_instance("compute-003") is None

        for i in [1, 2, 4, 5]:
            assert await registry.get_instance(f"compute-{i:03d}") is not None

    @pytest.mark.asyncio
    async def test_duplicate_registration_raises(self):
        """Registering the same instance_id twice raises ValueError."""
        registry = ComputeRegistry()

        inst = _make_compute_instance("compute-001")
        await registry.add_instance(inst)

        duplicate = _make_compute_instance("compute-001")
        with pytest.raises(ValueError, match="already registered"):
            await registry.add_instance(duplicate)

    @pytest.mark.asyncio
    async def test_capability_index_tracks_all_instances(self):
        """Capability index correctly references all registered instances."""
        registry = ComputeRegistry()

        for i in range(1, 6):
            inst = _make_compute_instance(
                f"compute-{i:03d}",
                agents=["coding", "testing"],
            )
            await registry.add_instance(inst)

        coders = await registry.get_by_capability(agent_id="coding")
        assert len(coders) == 5

        testers = await registry.get_by_capability(agent_id="testing")
        assert len(testers) == 5

    @pytest.mark.asyncio
    async def test_sse_connections_for_multiple_instances(self):
        """Multiple SSE connections can coexist in the connection manager."""
        manager = SSEConnectionManager()

        connections = []
        for i in range(1, 6):
            conn = await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=["coding"],
                resources={"cpu": 4},
            )
            connections.append(conn)

        assert len(manager.list_connections()) == 5

        for i in range(1, 6):
            conn = manager.get_connection(f"compute-{i:03d}")
            assert conn is not None
            assert conn.status == "idle"

    @pytest.mark.asyncio
    async def test_sse_unregister_does_not_affect_other_connections(self):
        """Disconnecting one SSE connection leaves others intact."""
        manager = SSEConnectionManager()

        for i in range(1, 6):
            await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=[],
                resources={},
            )

        await manager.unregister_connection("compute-003")

        assert len(manager.list_connections()) == 4
        assert manager.get_connection("compute-003") is None
        assert manager.get_connection("compute-001") is not None
        assert manager.get_connection("compute-005") is not None


# =============================================================================
# Work Distribution Tests
# =============================================================================


class TestWorkDistribution:
    """Test work distribution across available compute instances."""

    @pytest.mark.asyncio
    async def test_round_robin_distributes_across_fleet(self):
        """Work is distributed evenly via round-robin across idle computes."""
        manager = SSEConnectionManager()

        for i in range(1, 6):
            await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=["coding"],
                resources={"cpu": 4},
            )

        assignments = []
        for _ in range(10):
            conn = manager.find_matching_connection(idle_only=True)
            assert conn is not None
            assignments.append(conn.compute_id)

        # Each compute should be selected twice in 10 assignments
        for i in range(1, 6):
            assert assignments.count(f"compute-{i:03d}") == 2

    @pytest.mark.asyncio
    async def test_capability_based_routing_with_multiple_capable(self):
        """Work requiring specific labels routes only to matching computes."""
        manager = SSEConnectionManager()

        # 3 computes with "gpu" label, 2 without
        for i in range(1, 4):
            await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=["coding"],
                resources={"cpu": 4},
                labels=["gpu"],
            )
        for i in range(4, 6):
            await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=["coding"],
                resources={"cpu": 4},
                labels=["cpu-only"],
            )

        # Request GPU-labeled computes
        assignments = set()
        for _ in range(6):
            conn = manager.find_matching_connection(
                idle_only=True,
                required_labels=["gpu"],
            )
            assert conn is not None
            assignments.add(conn.compute_id)

        assert assignments == {"compute-001", "compute-002", "compute-003"}

    @pytest.mark.asyncio
    async def test_tool_based_routing(self):
        """Work requiring specific tools routes to computes with those tools."""
        manager = SSEConnectionManager()

        await manager.register_connection(
            "compute-001", capabilities=[], resources={},
            tools_available=["deploy_prod", "db_migrate"],
        )
        await manager.register_connection(
            "compute-002", capabilities=[], resources={},
            tools_available=["deploy_staging"],
        )
        await manager.register_connection(
            "compute-003", capabilities=[], resources={},
            tools_available=["deploy_prod"],
        )

        conn = manager.find_matching_connection(
            idle_only=True,
            required_tools=["deploy_prod", "db_migrate"],
        )
        assert conn is not None
        assert conn.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_work_assignment_respects_busy_status(self):
        """Busy computes are skipped during work distribution."""
        manager = SSEConnectionManager()

        conns = []
        for i in range(1, 6):
            conn = await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=["coding"],
                resources={},
            )
            conns.append(conn)

        # Mark first 3 as busy
        for conn in conns[:3]:
            conn.status = "busy"

        idle = manager.get_idle_connections()
        assert len(idle) == 2

        assignments = set()
        for _ in range(4):
            conn = manager.find_matching_connection(idle_only=True)
            assert conn is not None
            assignments.add(conn.compute_id)

        assert assignments == {"compute-004", "compute-005"}

    @pytest.mark.asyncio
    async def test_specialization_scoring_prefers_best_match(self):
        """Specialization scores override round-robin to pick best compute."""
        manager = SSEConnectionManager()

        for i in range(1, 6):
            await manager.register_connection(
                compute_id=f"compute-{i:03d}",
                capabilities=["coding"],
                resources={},
            )

        scores = {
            "compute-001": 0.2,
            "compute-002": 0.4,
            "compute-003": 0.9,
            "compute-004": 0.1,
            "compute-005": 0.6,
        }

        # Should always pick compute-003 (highest score)
        for _ in range(5):
            conn = manager.find_matching_connection(
                idle_only=True,
                specialization_scores=scores,
            )
            assert conn.compute_id == "compute-003"

    @pytest.mark.asyncio
    async def test_assignment_service_distributes_by_priority(self):
        """Assignment service picks highest-priority pending work first."""
        service = AssignmentService()

        work_items = {
            "work-low": _make_work_item("work-low", priority=WorkPriority.LOW),
            "work-high": _make_work_item("work-high", priority=WorkPriority.HIGH),
            "work-critical": _make_work_item("work-critical", priority=WorkPriority.CRITICAL),
        }
        service.set_work_items_reference(work_items)

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
        )

        assert assignment is not None
        assert assignment.work_id == "work-critical"

    @pytest.mark.asyncio
    async def test_assignment_skips_work_with_unmet_dependencies(self):
        """Work with unmet dependencies is not assigned."""
        service = AssignmentService()

        dep_work = _make_work_item("dep-1", status=WorkStatus.IN_PROGRESS)
        blocked_work = _make_work_item("work-1", depends_on=["dep-1"])

        work_items = {
            "dep-1": dep_work,
            "work-1": blocked_work,
        }
        service.set_work_items_reference(work_items)

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
        )

        assert assignment is None

    @pytest.mark.asyncio
    async def test_assignment_proceeds_when_dependencies_met(self):
        """Work is assignable when all dependencies are completed."""
        service = AssignmentService()

        dep_work = _make_work_item("dep-1", status=WorkStatus.COMPLETED)
        blocked_work = _make_work_item("work-1", depends_on=["dep-1"])

        work_items = {
            "dep-1": dep_work,
            "work-1": blocked_work,
        }
        service.set_work_items_reference(work_items)

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
        )

        assert assignment is not None
        assert assignment.work_id == "work-1"

    @pytest.mark.asyncio
    async def test_project_scoped_assignment(self):
        """Computes with project_ids only get work from matching projects."""
        service = AssignmentService()

        work_items = {
            "work-proj-a": _make_work_item("work-proj-a", project_id="proj-a"),
            "work-proj-b": _make_work_item("work-proj-b", project_id="proj-b"),
        }
        service.set_work_items_reference(work_items)

        # Compute restricted to proj-a
        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=["proj-a"],
        )

        assert assignment is not None
        assert assignment.work_id == "work-proj-a"

    @pytest.mark.asyncio
    async def test_benched_compute_gets_no_work(self):
        """A compute with empty project_ids (benched) receives no work."""
        service = AssignmentService()

        work_items = {
            "work-1": _make_work_item("work-1"),
        }
        service.set_work_items_reference(work_items)

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[],
            project_ids=[],
        )

        assert assignment is None


# =============================================================================
# Resource Contention Tests
# =============================================================================


class TestResourceContention:
    """Test handling of multiple computes contending for the same resources."""

    @pytest.mark.asyncio
    async def test_assignment_transitions_to_assigned_status(self):
        """Assigning work moves it from PENDING to ASSIGNED, preventing double-assignment."""
        service = AssignmentService()

        work_items = {
            "work-1": _make_work_item("work-1"),
        }
        service.set_work_items_reference(work_items)

        result = await service.assign_work(
            work_id="work-1",
            compute_id="compute-001",
            skills=["coding"],
        )

        assert result is not None
        assert work_items["work-1"].status == WorkStatus.ASSIGNED
        assert work_items["work-1"].assigned_to == "compute-001"

    @pytest.mark.asyncio
    async def test_second_assignment_to_same_work_succeeds_while_assigned(self):
        """Re-assigning ASSIGNED work to a different compute is allowed (reassignment)."""
        service = AssignmentService()

        work_items = {
            "work-1": _make_work_item("work-1"),
        }
        service.set_work_items_reference(work_items)

        await service.assign_work("work-1", "compute-001", ["coding"])
        assert work_items["work-1"].assigned_to == "compute-001"

        result = await service.assign_work("work-1", "compute-002", ["coding"])
        assert result is not None
        assert work_items["work-1"].assigned_to == "compute-002"

    @pytest.mark.asyncio
    async def test_cannot_assign_in_progress_work(self):
        """Work that is IN_PROGRESS cannot be reassigned."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.IN_PROGRESS, assigned_to="compute-001")
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.assign_work("work-1", "compute-002", ["coding"])
        assert result is None

    @pytest.mark.asyncio
    async def test_sequential_assignments_exhaust_pending_queue(self):
        """Multiple sequential assignments correctly consume the pending queue."""
        service = AssignmentService()

        work_items = {
            f"work-{i}": _make_work_item(f"work-{i}")
            for i in range(1, 4)
        }
        service.set_work_items_reference(work_items)

        assigned = []
        for i in range(1, 4):
            assignment = await service.get_next_assignment(
                compute_id=f"compute-{i:03d}",
                capabilities=[],
            )
            if assignment:
                assigned.append(assignment.work_id)

        assert len(assigned) == 3
        assert set(assigned) == {"work-1", "work-2", "work-3"}

    @pytest.mark.asyncio
    async def test_connection_status_updated_on_work_assigned(self):
        """SSE connection status updates to 'busy' when work is assigned."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        assert conn.status == "idle"

        await manager.send_work_assigned(
            compute_id="compute-001",
            task_id="task-1",
            title="Test",
            description="Test work",
            branch_name="feat/test",
            skills={},
            context={},
            mcp_config={},
        )

        assert conn.status == "busy"
        assert conn.current_task_id == "task-1"

    @pytest.mark.asyncio
    async def test_connection_status_restored_on_work_completed(self):
        """SSE connection returns to 'idle' when work completes."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        conn.status = "busy"
        conn.current_task_id = "task-1"

        await manager.send_work_completed(
            compute_id="compute-001",
            issue_id="issue-1",
            branch="feat/test",
            merge_commit="abc123",
        )

        assert conn.status == "idle"
        assert conn.current_task_id is None

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_fleet_members(self):
        """Broadcast events reach every connected compute in the fleet."""
        manager = SSEConnectionManager()

        connections = []
        for i in range(1, 6):
            conn = await manager.register_connection(
                f"compute-{i:03d}", capabilities=[], resources={},
            )
            connections.append(conn)

        count = await manager.broadcast_event(
            "credentials_refresh",
            {"reason": "rotation"},
        )

        assert count == 5

        for conn in connections:
            event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
            assert event["event"] == "credentials_refresh"


# =============================================================================
# Failure Scenario Tests
# =============================================================================


class TestFailureScenarios:
    """Test handling of compute failures, reassignment, and restarts."""

    @pytest.mark.asyncio
    async def test_work_reassignment_after_failure(self):
        """Failed work can be unassigned and returned to PENDING for retry."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.ASSIGNED, assigned_to="compute-001")
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.unassign_work("work-1")
        assert result is True
        assert work_items["work-1"].status == WorkStatus.PENDING
        assert work_items["work-1"].assigned_to is None

    @pytest.mark.asyncio
    async def test_failed_work_returns_to_pending_with_retry_count(self):
        """Timed-out work returns to PENDING with incremented retry count."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.IN_PROGRESS, assigned_to="compute-001")
        work.started_at = datetime.now(timezone.utc)
        work.last_activity_at = datetime.now(timezone.utc)
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.mark_work_timed_out("work-1", max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.PENDING
        assert result.retry_count == 1
        assert result.assigned_to is None

    @pytest.mark.asyncio
    async def test_work_permanently_fails_after_max_retries(self):
        """Work is marked FAILED after exhausting retry attempts."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.IN_PROGRESS, assigned_to="compute-001")
        work.retry_count = 2  # Already retried twice
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.mark_work_timed_out("work-1", max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.FAILED
        assert result.retry_count == 3

    @pytest.mark.asyncio
    async def test_partial_cluster_failure_two_of_five_down(self):
        """With 2 of 5 computes offline, work routes to remaining 3."""
        registry = ComputeRegistry()

        for i in range(1, 6):
            inst = _make_compute_instance(f"compute-{i:03d}")
            await registry.add_instance(inst)

        # Take 2 computes offline
        await registry.update_status("compute-002", InstanceStatus.OFFLINE)
        await registry.update_status("compute-004", InstanceStatus.OFFLINE)

        online = await registry.list_instances(status=InstanceStatus.ONLINE)
        assert len(online) == 3

        online_ids = {inst.instance_id for inst in online}
        assert online_ids == {"compute-001", "compute-003", "compute-005"}

    @pytest.mark.asyncio
    async def test_partial_cluster_failure_sse_routing(self):
        """SSE manager skips busy/draining computes from failed cluster."""
        manager = SSEConnectionManager()

        conns = {}
        for i in range(1, 6):
            conn = await manager.register_connection(
                f"compute-{i:03d}", capabilities=["coding"], resources={},
            )
            conns[f"compute-{i:03d}"] = conn

        # Simulate 2 computes going down (draining)
        conns["compute-002"].status = "draining"
        conns["compute-004"].status = "draining"

        idle = manager.get_idle_connections()
        assert len(idle) == 3

        # All routing should go to remaining idle computes
        selected = set()
        for _ in range(6):
            conn = manager.find_matching_connection(idle_only=True)
            assert conn is not None
            selected.add(conn.compute_id)

        assert selected == {"compute-001", "compute-003", "compute-005"}

    @pytest.mark.asyncio
    async def test_exclude_failed_nodes_on_retry(self):
        """Retries deprioritize computes that previously failed for a work item."""
        manager = SSEConnectionManager()

        for i in range(1, 4):
            await manager.register_connection(
                f"compute-{i:03d}", capabilities=[], resources={},
            )

        # compute-001 failed previously - exclude it
        failed_nodes = {"compute-001"}

        selected = set()
        for _ in range(4):
            conn = manager.find_matching_connection(
                idle_only=True,
                exclude_compute_ids=failed_nodes,
            )
            assert conn is not None
            selected.add(conn.compute_id)

        assert "compute-001" not in selected
        assert selected == {"compute-002", "compute-003"}

    @pytest.mark.asyncio
    async def test_exclude_falls_back_when_all_preferred_busy(self):
        """If all non-excluded computes are busy, excluded ones are used as last resort."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        conn2 = await manager.register_connection(
            "compute-002", capabilities=[], resources={},
        )
        conn3 = await manager.register_connection(
            "compute-003", capabilities=[], resources={},
        )

        # Preferred computes (002, 003) are busy
        conn2.status = "busy"
        conn3.status = "busy"

        # compute-001 previously failed but is the only idle node
        conn = manager.find_matching_connection(
            idle_only=True,
            exclude_compute_ids={"compute-001"},
        )

        assert conn is not None
        assert conn.compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_compute_restart_during_active_work(self):
        """Simulates compute disconnect and SSE re-registration."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            "compute-001", capabilities=["coding"], resources={"cpu": 4},
        )
        conn.status = "busy"
        conn.current_task_id = "task-1"

        # Compute disconnects
        await manager.unregister_connection("compute-001")
        assert manager.get_connection("compute-001") is None

        # Compute restarts and re-registers
        new_conn = await manager.register_connection(
            "compute-001", capabilities=["coding"], resources={"cpu": 4},
        )

        assert new_conn is not None
        assert new_conn.status == "idle"
        assert new_conn.current_task_id is None
        assert len(manager.list_connections()) == 1

    @pytest.mark.asyncio
    async def test_drain_stops_new_assignments(self):
        """Draining a compute removes its project tags to stop new work."""
        registry = ComputeRegistry()

        inst = _make_compute_instance("compute-001", project_ids=["proj-a", "proj-b"])
        await registry.add_instance(inst)

        drained = await registry.drain_instance("compute-001")
        assert drained is not None
        assert drained.status == InstanceStatus.DRAINING
        assert drained.project_ids == []

        # Should not appear in project queries
        proj_a_instances = await registry.get_by_project("proj-a")
        assert len(proj_a_instances) == 0

    @pytest.mark.asyncio
    async def test_cancel_drain_restores_online_status(self):
        """Cancelling a drain restores ONLINE status."""
        registry = ComputeRegistry()

        inst = _make_compute_instance("compute-001", project_ids=["proj-a"])
        await registry.add_instance(inst)

        await registry.drain_instance("compute-001")
        assert (await registry.get_instance("compute-001")).status == InstanceStatus.DRAINING

        restored = await registry.cancel_drain("compute-001")
        assert restored.status == InstanceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_health_check_marks_stale_instances_offline(self):
        """Health check transitions stale instances to OFFLINE."""
        registry = ComputeRegistry()

        for i in range(1, 4):
            inst = _make_compute_instance(f"compute-{i:03d}")
            await registry.add_instance(inst)

        # Make compute-002 stale by setting old heartbeat
        stale_inst = await registry.get_instance("compute-002")
        from datetime import timedelta
        stale_inst.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)

        results = await registry.check_health(max_heartbeat_age=90)

        assert len(results["status_changes"]) == 1
        assert results["status_changes"][0]["instance_id"] == "compute-002"
        assert results["status_changes"][0]["new_status"] == "offline"

        # Other instances remain online
        for iid in ["compute-001", "compute-003"]:
            inst = await registry.get_instance(iid)
            assert inst.status == InstanceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_status_transition_authorization(self):
        """Only the assigned compute can update work status."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.ASSIGNED, assigned_to="compute-001")
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        # Unauthorized compute
        result = await service.update_status(
            "work-1", WorkStatus.IN_PROGRESS, compute_id="compute-002",
        )
        assert result is None
        assert work_items["work-1"].status == WorkStatus.ASSIGNED

        # Authorized compute
        result = await service.update_status(
            "work-1", WorkStatus.IN_PROGRESS, compute_id="compute-001",
        )
        assert result is not None
        assert result.status == WorkStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_completion_cascade_unblocks_dependents(self):
        """Completing work triggers dependency cascade for blocked items."""
        service = AssignmentService()

        dep = _make_work_item("dep-1", status=WorkStatus.IN_PROGRESS, assigned_to="compute-001")
        dep.blocks = ["work-1"]

        from models.work_map import Blocker, BlockerType
        blocker = Blocker(
            blocker_id="blk-1",
            blocker_type=BlockerType.DEPENDENCY,
            description="Waiting on dep-1",
            blocking_work_id="dep-1",
        )
        blocked = _make_work_item("work-1", status=WorkStatus.BLOCKED)
        blocked.blockers = [blocker]

        work_items = {"dep-1": dep, "work-1": blocked}
        service.set_work_items_reference(work_items)

        await service.complete_work(
            "dep-1", result={"output": "done"}, compute_id="compute-001",
        )

        assert work_items["dep-1"].status == WorkStatus.COMPLETED
        # Blocker should be resolved
        assert work_items["work-1"].blockers[0].is_resolved

    @pytest.mark.asyncio
    async def test_failed_work_eligible_for_retry(self):
        """FAILED work with retry_count < max is eligible for retry."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.FAILED, assigned_to="compute-001")
        work.retry_count = 1
        work.error = "Timed out"
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        eligible = await service.get_failed_work(max_retries=3)
        assert len(eligible) == 1
        assert eligible[0].work_id == "work-1"

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_returns_to_pending(self):
        """mark_work_for_retry moves FAILED work back to PENDING."""
        service = AssignmentService()

        work = _make_work_item("work-1", status=WorkStatus.FAILED, assigned_to="compute-001")
        work.retry_count = 0
        work.error = "timeout"
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.mark_work_for_retry("work-1", max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.PENDING
        assert result.retry_count == 1
        assert result.assigned_to is None
        assert result.error is None
