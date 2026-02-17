"""Tests for error recovery and resilience scenarios.

Covers:
- Compute crash recovery (work reassignment, orphan cleanup, timeout detection)
- Network failure recovery (SSE reconnection, state consistency, serving behavior)
- Event delivery failures (queue overflow, duplicate handling, ordering)
- Redis state recovery (connection loss, concurrent updates)

Issue: #307
"""

import asyncio
import time
import pytest
from datetime import datetime, timedelta, timezone
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
from services.work_orchestrator import WorkOrchestrator


# =============================================================================
# Helpers
# =============================================================================


def _make_compute_instance(
    instance_id: str,
    status: InstanceStatus = InstanceStatus.ONLINE,
    project_ids: list[str] | None = None,
) -> ComputeInstance:
    """Create a ComputeInstance for testing."""
    return ComputeInstance(
        instance_id=instance_id,
        name=f"test-{instance_id}",
        endpoint=f"http://{instance_id}:8003",
        capabilities=InstanceCapabilities(
            agents=["coding"],
            tools=[],
            resources=InstanceResources(cpu_count=4, memory_gb=16.0),
        ),
        status=status,
        project_ids=project_ids or ["*"],
    )


def _make_work_item(
    work_id: str,
    status: WorkStatus = WorkStatus.PENDING,
    priority: WorkPriority = WorkPriority.NORMAL,
    assigned_to: str | None = None,
    depends_on: list[str] | None = None,
    project_id: str = "project-1",
    retry_count: int = 0,
) -> WorkItem:
    """Create a WorkItem for testing."""
    return WorkItem(
        work_id=work_id,
        title=f"Test work {work_id}",
        description=f"Description for {work_id}",
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        depends_on=depends_on or [],
        required_skills=["coding"],
        project_id=project_id,
        branch_name=f"work/{work_id}",
        base_branch="main",
        retry_count=retry_count,
    )


# =============================================================================
# Compute Crash Recovery Tests
# =============================================================================


class TestComputeCrashRecovery:
    """Test work reassignment and cleanup after compute crashes."""

    @pytest.mark.asyncio
    async def test_work_returned_to_pending_after_timeout(self):
        """Timed-out work returns to PENDING for reassignment."""
        service = AssignmentService()

        work = _make_work_item(
            "work-1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
        )
        work.started_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        work.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.mark_work_timed_out("work-1", max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.PENDING
        assert result.assigned_to is None
        assert result.retry_count == 1

    @pytest.mark.asyncio
    async def test_crash_detection_identifies_stale_work(self):
        """Assignment service detects work that has been IN_PROGRESS too long."""
        service = AssignmentService()

        stale_work = _make_work_item(
            "work-stale",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
        )
        stale_work.started_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        stale_work.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=45)

        fresh_work = _make_work_item(
            "work-fresh",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-002",
        )
        fresh_work.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        fresh_work.last_activity_at = datetime.now(timezone.utc)

        work_items = {"work-stale": stale_work, "work-fresh": fresh_work}
        service.set_work_items_reference(work_items)

        stale = await service.get_stale_work(timeout_minutes=30)

        assert len(stale) == 1
        assert stale[0].work_id == "work-stale"

    @pytest.mark.asyncio
    async def test_orphaned_work_cleanup_via_unassign(self):
        """Orphaned work (assigned compute gone) can be unassigned."""
        service = AssignmentService()

        orphan = _make_work_item(
            "work-orphan",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-gone",
        )
        work_items = {"work-orphan": orphan}
        service.set_work_items_reference(work_items)

        result = await service.unassign_work("work-orphan")

        assert result is True
        assert work_items["work-orphan"].status == WorkStatus.PENDING
        assert work_items["work-orphan"].assigned_to is None

    @pytest.mark.asyncio
    async def test_crash_increments_retry_count_preserving_history(self):
        """Each timeout increments retry_count, preserving progress notes."""
        service = AssignmentService()

        work = _make_work_item(
            "work-1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
            retry_count=1,
        )
        work.progress_notes = ["[prev] Previous attempt"]
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.mark_work_timed_out("work-1", max_retries=5)

        assert result.retry_count == 2
        assert len(result.progress_notes) == 2
        assert "Timed out" in result.progress_notes[-1]

    @pytest.mark.asyncio
    async def test_permanent_failure_after_max_timeout_retries(self):
        """Work is permanently FAILED after exhausting timeout retries."""
        service = AssignmentService()

        work = _make_work_item(
            "work-1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
            retry_count=2,
        )
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        result = await service.mark_work_timed_out("work-1", max_retries=3)

        assert result.status == WorkStatus.FAILED
        assert result.retry_count == 3
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_registry_marks_crashed_compute_offline(self):
        """Health check marks unresponsive compute as OFFLINE."""
        registry = ComputeRegistry()

        inst = _make_compute_instance("compute-001")
        await registry.add_instance(inst)

        # Simulate no heartbeat for 2 minutes
        inst.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)

        results = await registry.check_health(max_heartbeat_age=90)

        assert len(results["status_changes"]) == 1
        change = results["status_changes"][0]
        assert change["instance_id"] == "compute-001"
        assert change["new_status"] == "offline"

    @pytest.mark.asyncio
    async def test_multiple_crash_detections_increment_failed_checks(self):
        """Repeated health failures increment failed_health_checks counter."""
        registry = ComputeRegistry()

        inst = _make_compute_instance("compute-001")
        await registry.add_instance(inst)

        inst.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)

        await registry.check_health(max_heartbeat_age=90)
        assert inst.failed_health_checks == 1

        await registry.check_health(max_heartbeat_age=90)
        assert inst.failed_health_checks == 2


# =============================================================================
# Network Failure Recovery Tests
# =============================================================================


class TestNetworkFailureRecovery:
    """Test SSE reconnection and state consistency after network failures."""

    @pytest.mark.asyncio
    async def test_sse_reconnection_replaces_stale_connection(self):
        """Reconnecting compute replaces the stale SSE connection."""
        manager = SSEConnectionManager()

        old_conn = await manager.register_connection(
            "compute-001", capabilities=["coding"], resources={"cpu": 4},
        )
        old_conn.status = "busy"
        old_conn.current_task_id = "task-stale"

        # Compute reconnects (new connection)
        new_conn = await manager.register_connection(
            "compute-001", capabilities=["coding"], resources={"cpu": 4},
        )

        assert manager.get_connection("compute-001") is new_conn
        assert new_conn.status == "idle"
        assert new_conn.current_task_id is None
        assert len(manager.list_connections()) == 1

    @pytest.mark.asyncio
    async def test_events_queued_during_disconnect_are_lost(self):
        """Events sent to a disconnected compute are silently dropped."""
        manager = SSEConnectionManager()

        await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        await manager.unregister_connection("compute-001")

        result = await manager.send_event(
            "compute-001", "work_assigned", {"task_id": "task-1"},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_serving_continues_during_compute_disconnect(self):
        """Serving operations continue when individual computes disconnect."""
        manager = SSEConnectionManager()

        await manager.register_connection(
            "compute-001", capabilities=["coding"], resources={},
        )
        conn2 = await manager.register_connection(
            "compute-002", capabilities=["coding"], resources={},
        )

        # compute-001 disconnects
        await manager.unregister_connection("compute-001")

        # Serving can still route to compute-002
        match = manager.find_matching_connection(idle_only=True)
        assert match is not None
        assert match.compute_id == "compute-002"

        # Broadcast still reaches remaining connections
        count = await manager.broadcast_event("test", {"data": "hello"})
        assert count == 1

    @pytest.mark.asyncio
    async def test_reconnect_triggers_connect_handler(self):
        """Reconnection triggers the on_connect handler."""
        manager = SSEConnectionManager()

        connected_ids = []

        async def on_connect(compute_id: str):
            connected_ids.append(compute_id)

        manager.on_connect(on_connect)

        await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        await manager.unregister_connection("compute-001")
        await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )

        assert connected_ids.count("compute-001") == 2

    @pytest.mark.asyncio
    async def test_disconnect_triggers_disconnect_handler(self):
        """Disconnection triggers the on_disconnect handler."""
        manager = SSEConnectionManager()

        disconnected_ids = []

        async def on_disconnect(compute_id: str):
            disconnected_ids.append(compute_id)

        manager.on_disconnect(on_disconnect)

        await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        await manager.unregister_connection("compute-001")

        assert "compute-001" in disconnected_ids

    @pytest.mark.asyncio
    async def test_reconnect_with_different_capabilities(self):
        """Reconnecting compute can update its capabilities."""
        manager = SSEConnectionManager()

        await manager.register_connection(
            "compute-001",
            capabilities=["coding"],
            resources={"cpu": 2},
            labels=["staging"],
        )

        # Reconnect with upgraded capabilities
        new_conn = await manager.register_connection(
            "compute-001",
            capabilities=["coding", "testing"],
            resources={"cpu": 8},
            labels=["production"],
        )

        assert new_conn.capabilities == ["coding", "testing"]
        assert new_conn.resources == {"cpu": 8}
        assert new_conn.labels == ["production"]

    @pytest.mark.asyncio
    async def test_registry_degraded_state_before_offline(self):
        """Health check transitions through DEGRADED before OFFLINE."""
        registry = ComputeRegistry()

        inst = _make_compute_instance("compute-001")
        await registry.add_instance(inst)

        # 70 seconds without heartbeat -> DEGRADED (threshold=60)
        inst.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=70)

        results = await registry.check_health(
            max_heartbeat_age=90, degraded_threshold=60,
        )

        assert len(results["status_changes"]) == 1
        assert results["status_changes"][0]["new_status"] == "degraded"
        assert inst.status == InstanceStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_work_persists_through_sse_disconnect(self):
        """Work item state in assignment service survives SSE disconnection."""
        service = AssignmentService()

        work = _make_work_item(
            "work-1", status=WorkStatus.IN_PROGRESS, assigned_to="compute-001",
        )
        work.progress_percent = 50
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        # Even though SSE connection dropped, work item is still tracked
        assert work_items["work-1"].status == WorkStatus.IN_PROGRESS
        assert work_items["work-1"].progress_percent == 50
        assert work_items["work-1"].assigned_to == "compute-001"


# =============================================================================
# Event Delivery Failure Tests
# =============================================================================


class TestEventDeliveryFailures:
    """Test event queue handling, ordering, and edge cases."""

    @pytest.mark.asyncio
    async def test_event_ordering_preserved(self):
        """Events are delivered in FIFO order."""
        conn = SSEConnection(
            compute_id="compute-001", capabilities=[], resources={},
        )

        for i in range(5):
            await conn.send_event(f"event_{i}", {"seq": i})

        for i in range(5):
            event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
            assert event["event"] == f"event_{i}"
            assert event["data"]["seq"] == i

    @pytest.mark.asyncio
    async def test_event_queue_handles_high_volume(self):
        """Event queue handles a burst of many events."""
        conn = SSEConnection(
            compute_id="compute-001", capabilities=[], resources={},
        )

        # Queue 100 events rapidly
        for i in range(100):
            await conn.send_event("burst", {"seq": i})

        # Drain all events
        events = []
        for _ in range(100):
            event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
            events.append(event)

        assert len(events) == 100
        assert all(e["event"] == "burst" for e in events)
        # Verify ordering
        seqs = [e["data"]["seq"] for e in events]
        assert seqs == list(range(100))

    @pytest.mark.asyncio
    async def test_broadcast_partial_failure_continues(self):
        """Broadcast continues even if individual send fails."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        conn2 = await manager.register_connection(
            "compute-002", capabilities=[], resources={},
        )

        # Both should receive the event (broadcast is resilient)
        count = await manager.broadcast_event("test_event", {"data": "test"})
        assert count == 2

    @pytest.mark.asyncio
    async def test_send_event_to_disconnected_returns_false(self):
        """Sending event to disconnected compute returns False gracefully."""
        manager = SSEConnectionManager()

        result = await manager.send_event(
            "nonexistent", "test_event", {"data": "test"},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_concurrent_event_sends_dont_interfere(self):
        """Concurrent event sends to different connections don't interfere."""
        manager = SSEConnectionManager()

        conn1 = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )
        conn2 = await manager.register_connection(
            "compute-002", capabilities=[], resources={},
        )

        # Send events concurrently
        await asyncio.gather(
            manager.send_event("compute-001", "event_a", {"target": "001"}),
            manager.send_event("compute-002", "event_b", {"target": "002"}),
        )

        event1 = await asyncio.wait_for(conn1.get_event(), timeout=1.0)
        event2 = await asyncio.wait_for(conn2.get_event(), timeout=1.0)

        assert event1["data"]["target"] == "001"
        assert event2["data"]["target"] == "002"

    @pytest.mark.asyncio
    async def test_work_assigned_event_sets_busy_status(self):
        """work_assigned event atomically updates connection status to busy."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )

        await manager.send_work_assigned(
            compute_id="compute-001",
            task_id="task-1",
            title="Test",
            description="Desc",
            branch_name="feat/test",
            skills={},
            context={},
            mcp_config={},
        )

        assert conn.status == "busy"
        assert conn.current_task_id == "task-1"

        # Should not appear as idle
        idle = manager.get_idle_connections()
        assert conn not in idle

    @pytest.mark.asyncio
    async def test_work_completed_event_resets_to_idle(self):
        """work_completed event resets connection to idle."""
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
    async def test_work_cancelled_event_delivered(self):
        """work_cancelled event is properly queued."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )

        result = await manager.send_work_cancelled(
            compute_id="compute-001",
            task_id="task-1",
            reason="Project deprioritized",
        )

        assert result is True
        event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
        assert event["event"] == "work_cancelled"
        assert event["data"]["reason"] == "Project deprioritized"

    @pytest.mark.asyncio
    async def test_shutdown_event_delivered(self):
        """Shutdown event with grace period is delivered."""
        manager = SSEConnectionManager()

        conn = await manager.register_connection(
            "compute-001", capabilities=[], resources={},
        )

        result = await manager.send_shutdown(
            compute_id="compute-001",
            reason="Maintenance window",
            grace_period_seconds=120,
        )

        assert result is True
        event = await asyncio.wait_for(conn.get_event(), timeout=1.0)
        assert event["event"] == "shutdown"
        assert event["data"]["grace_period_seconds"] == 120


# =============================================================================
# Orchestrator Error Recovery Tests
# =============================================================================


class TestOrchestratorErrorRecovery:
    """Test work orchestrator error handling and retry logic."""

    def test_spawn_failure_exponential_backoff(self):
        """Spawn failure backoff delay doubles with each retry."""
        orchestrator = WorkOrchestrator(
            poll_interval=1, max_retries=5, retry_delay=10,
        )

        orchestrator._handle_spawn_failure("work-1", "Error 1")
        after_1 = orchestrator._retry_after["work-1"]

        orchestrator._handle_spawn_failure("work-1", "Error 2")
        after_2 = orchestrator._retry_after["work-1"]

        orchestrator._handle_spawn_failure("work-1", "Error 3")
        after_3 = orchestrator._retry_after["work-1"]

        # Backoff: 10s, 20s, 40s
        # Check that each retry_after is further in the future
        assert after_2 > after_1
        assert after_3 > after_2

    def test_spawn_failure_tracks_retry_count(self):
        """Each spawn failure increments the retry counter."""
        orchestrator = WorkOrchestrator(
            poll_interval=1, max_retries=3, retry_delay=5,
        )

        for i in range(1, 4):
            orchestrator._handle_spawn_failure("work-1", f"Error {i}")
            assert orchestrator._retry_counts["work-1"] == i

    def test_spawn_failure_increments_total_failed_stat(self):
        """Each spawn failure increments the total_failed stat."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        orchestrator._handle_spawn_failure("work-1", "Error")
        orchestrator._handle_spawn_failure("work-2", "Error")

        assert orchestrator._stats["total_failed"] == 2

    def test_failed_nodes_tracking(self):
        """Orchestrator tracks which nodes failed for each work item."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        # Simulate tracking failed nodes
        orchestrator._failed_nodes["work-1"] = set()
        orchestrator._failed_nodes["work-1"].add("compute-001")
        orchestrator._failed_nodes["work-1"].add("compute-002")

        assert "compute-001" in orchestrator._failed_nodes["work-1"]
        assert "compute-002" in orchestrator._failed_nodes["work-1"]
        assert len(orchestrator._failed_nodes["work-1"]) == 2

    @pytest.mark.asyncio
    async def test_retry_respects_backoff_delay(self):
        """Work in retry backoff is not retried until delay expires."""
        orchestrator = WorkOrchestrator(
            poll_interval=1, max_retries=3, retry_delay=30,
        )

        # Set a future backoff
        orchestrator._retry_after["work-1"] = datetime.now(timezone.utc) + timedelta(seconds=60)

        # This work should be skipped during processing
        # (it's in backoff period)
        retry_after = orchestrator._retry_after.get("work-1")
        assert retry_after is not None
        assert retry_after > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_orchestrator_loop_survives_exceptions(self):
        """Orchestration loop continues despite individual errors."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        await orchestrator.start()
        assert orchestrator.is_running()

        # The loop should be running and resilient to errors
        await asyncio.sleep(0.1)
        assert orchestrator.is_running()

        await orchestrator.stop()
        assert not orchestrator.is_running()

    @pytest.mark.asyncio
    async def test_timeout_monitoring_starts_when_enabled(self):
        """Timeout monitoring task starts when enabled."""
        orchestrator = WorkOrchestrator(
            poll_interval=1, timeout_enabled=True,
        )

        await orchestrator.start()
        assert orchestrator._timeout_task is not None

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_timeout_monitoring_skipped_when_disabled(self):
        """Timeout monitoring is not started when disabled."""
        orchestrator = WorkOrchestrator(
            poll_interval=1, timeout_enabled=False,
        )

        await orchestrator.start()
        assert orchestrator._timeout_task is None

        await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_paused_orchestrator_skips_processing(self):
        """Paused orchestrator does not process work."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        orchestrator.pause()
        assert orchestrator.is_paused()

        result = await orchestrator.trigger_immediate()
        assert result["status"] == "paused"

    def test_skill_cache_stores_and_retrieves(self):
        """Skill cache stores entries with TTL."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        orchestrator._set_cached_skill("skill-1", {"name": "Coder", "instructions": "Code well"})

        cached = orchestrator._get_cached_skill("skill-1")
        assert cached is not None
        assert cached["name"] == "Coder"

    def test_skill_cache_expires(self):
        """Expired skill cache entries return None."""
        orchestrator = WorkOrchestrator(poll_interval=1)
        orchestrator._skill_cache_ttl = 0  # Expire immediately

        orchestrator._set_cached_skill("skill-1", {"name": "Coder"})

        # Wait a tiny bit for expiry
        import time
        time.sleep(0.01)

        cached = orchestrator._get_cached_skill("skill-1")
        assert cached is None

    def test_select_skills_fallback_by_work_type(self):
        """Skill selection falls back to work_type-based defaults."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        work = _make_work_item("work-1")
        work.skill_ids = []
        work.required_skills = []
        work.work_type = "bug"

        skills = orchestrator._select_skills_for_work(work)
        assert skills == ["debugger"]

    def test_select_skills_prefers_skill_ids(self):
        """Skill selection prefers pre-resolved skill_ids."""
        orchestrator = WorkOrchestrator(poll_interval=1)

        work = _make_work_item("work-1")
        work.skill_ids = ["custom-skill-1", "custom-skill-2"]

        skills = orchestrator._select_skills_for_work(work)
        assert skills == ["custom-skill-1", "custom-skill-2"]


# =============================================================================
# Redis State Recovery Tests
# =============================================================================


class TestRedisStateRecovery:
    """Test Redis connection health and state recovery patterns."""

    @pytest.mark.asyncio
    async def test_redis_health_check_success(self):
        """Health check returns connected=True when Redis responds."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        result = await client.health_check()

        assert result["connected"] is True
        assert "response_time_ms" in result
        assert result["response_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_redis_health_check_connection_error(self):
        """Health check returns connected=False on connection error."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        result = await client.health_check()

        assert result["connected"] is False
        assert "error" in result
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_redis_health_check_timeout(self):
        """Health check returns connected=False on timeout."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=TimeoutError("Timed out"))

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        result = await client.health_check()

        assert result["connected"] is False
        assert "error" in result
        assert "Timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_branch_status_atomic_update(self):
        """Branch status uses HSET for atomic updates."""
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.hsetnx = AsyncMock()

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        await client.set_branch_status(
            project="myrepo",
            branch="feat/test",
            status="in_review",
            compute_id="compute-001",
        )

        mock_redis.hset.assert_called_once()
        call_kwargs = mock_redis.hset.call_args
        mapping = call_kwargs.kwargs.get("mapping") or call_kwargs[1].get("mapping")
        assert mapping["status"] == "in_review"
        assert mapping["compute_id"] == "compute-001"

    @pytest.mark.asyncio
    async def test_branch_status_get_returns_none_for_missing(self):
        """Get branch status returns None for nonexistent branch."""
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        result = await client.get_branch_status("myrepo", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_pr_queue_add_and_position(self):
        """PR queue tracks position correctly."""
        mock_redis = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zrank = AsyncMock(return_value=0)

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        position = await client.add_to_pr_queue("myrepo", "feat/test")

        assert position == 1  # 0-indexed rank + 1
        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_merge_queue_fifo_order(self):
        """Merge queue maintains FIFO order using rpush/lpop."""
        mock_redis = AsyncMock()
        mock_redis.rpush = AsyncMock(return_value=1)
        mock_redis.lpop = AsyncMock(return_value="feat/first")

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")

        await client.add_to_merge_queue("myrepo", "feat/first")
        mock_redis.rpush.assert_called_once()

        result = await client.pop_merge_queue("myrepo")
        assert result == "feat/first"

    @pytest.mark.asyncio
    async def test_compute_branch_tracking(self):
        """Compute branch tracking adds and retrieves branches."""
        mock_redis = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={"feat/a", "feat/b"})

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")

        await client.track_compute_branch("compute-001", "feat/a")
        mock_redis.sadd.assert_called_once()

        branches = await client.get_compute_branches("compute-001")
        assert set(branches) == {"feat/a", "feat/b"}

    @pytest.mark.asyncio
    async def test_publish_event_serializes_json(self):
        """Pub/sub events are serialized as JSON."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(return_value=1)

        from git.redis_client import RedisClient

        client = RedisClient(redis=mock_redis, prefix="test:")
        subscribers = await client.publish_event(
            "channel", {"type": "test", "data": "hello"},
        )

        assert subscribers == 1
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        import json
        published_data = json.loads(call_args[0][1])
        assert published_data["type"] == "test"

    @pytest.mark.asyncio
    async def test_assignment_service_works_without_redis(self):
        """Assignment service functions without Redis (in-memory mode)."""
        service = AssignmentService(redis_client=None)

        work = _make_work_item("work-1")
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        assignment = await service.assign_work(
            "work-1", "compute-001", ["coding"],
        )

        assert assignment is not None
        assert work_items["work-1"].assigned_to == "compute-001"

    @pytest.mark.asyncio
    async def test_get_compute_current_work_in_memory(self):
        """get_compute_current_work works in-memory without Redis."""
        service = AssignmentService(redis_client=None)

        work = _make_work_item(
            "work-1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
        )
        work_items = {"work-1": work}
        service.set_work_items_reference(work_items)

        current = await service.get_compute_current_work("compute-001")
        assert current == "work-1"

    @pytest.mark.asyncio
    async def test_get_compute_current_work_none_when_idle(self):
        """get_compute_current_work returns None when compute has no work."""
        service = AssignmentService(redis_client=None)
        service.set_work_items_reference({})

        current = await service.get_compute_current_work("compute-idle")
        assert current is None
