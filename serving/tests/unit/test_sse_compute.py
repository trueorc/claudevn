"""Tests for SSE-based compute registration and event handling."""

import pytest
from datetime import datetime, timezone

from models.compute import (
    ComputeInstance,
    InstanceStatus,
    InstanceCapabilities,
    InstanceResources,
    # SSE Event models
    SSEEventType,
    WorkAssignedEvent,
    WorkCancelledEvent,
    ShutdownEvent,
    MergeConflictEvent,
    WorkCompletedEvent,
    KeepaliveEvent,
    # Compute Event models
    ComputeEventType,
    ComputeEventRequest,
    ComputeEventResponse,
)
from services.registry_service import ComputeRegistry


# =============================================================================
# SSE Event Model Tests
# =============================================================================


class TestSSEEventModels:
    """Tests for SSE event Pydantic models."""

    def test_work_assigned_event_creation(self):
        """Test WorkAssignedEvent model creation."""
        event = WorkAssignedEvent(
            task_id="task-123",
            title="Implement feature X",
            description="Add login functionality",
            branch_name="f/task-123/compute-001",
            skills={"ids": ["code-writer"], "merged_instructions": "# Instructions"},
            context={"repository": "git@server:repo.git", "base_branch": "main"},
            mcp_config={"server_url": "http://localhost:8002"},
        )
        assert event.task_id == "task-123"
        assert event.title == "Implement feature X"
        assert "code-writer" in event.skills["ids"]

    def test_work_cancelled_event_creation(self):
        """Test WorkCancelledEvent model creation."""
        event = WorkCancelledEvent(
            task_id="task-123",
            reason="Higher priority work",
            action="stop_gracefully",
        )
        assert event.task_id == "task-123"
        assert event.reason == "Higher priority work"
        assert event.action == "stop_gracefully"

    def test_shutdown_event_creation(self):
        """Test ShutdownEvent model creation."""
        event = ShutdownEvent(
            reason="Maintenance window",
            grace_period_seconds=120,
        )
        assert event.reason == "Maintenance window"
        assert event.grace_period_seconds == 120

    def test_merge_conflict_event_creation(self):
        """Test MergeConflictEvent model creation."""
        event = MergeConflictEvent(
            issue_id="issue-100",
            branch="f/issue-100/compute-001",
            conflicting_files=["src/api/auth.py", "src/models/user.py"],
            main_head="abc123def",
            message="Resolve conflicts and push again",
        )
        assert event.issue_id == "issue-100"
        assert len(event.conflicting_files) == 2
        assert event.main_head == "abc123def"

    def test_work_completed_event_creation(self):
        """Test WorkCompletedEvent model creation."""
        event = WorkCompletedEvent(
            issue_id="issue-100",
            branch="f/issue-100/compute-001",
            merge_commit="def456abc",
            merged_at="2026-01-30T10:30:00Z",
        )
        assert event.issue_id == "issue-100"
        assert event.merge_commit == "def456abc"

    def test_keepalive_event_creation(self):
        """Test KeepaliveEvent model creation."""
        timestamp = datetime.now(timezone.utc).isoformat()
        event = KeepaliveEvent(timestamp=timestamp)
        assert event.timestamp == timestamp


class TestComputeEventModels:
    """Tests for Compute -> Serving event models."""

    def test_compute_event_request_started(self):
        """Test ComputeEventRequest for claude_code_started."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_STARTED,
            compute_id="compute-001",
            task_id="task-456",
            instance_id="cc-789",
        )
        assert event.event == ComputeEventType.CLAUDE_CODE_STARTED
        assert event.compute_id == "compute-001"
        assert event.task_id == "task-456"
        assert event.instance_id == "cc-789"

    def test_compute_event_request_completed(self):
        """Test ComputeEventRequest for claude_code_completed."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_COMPLETED,
            compute_id="compute-001",
            task_id="task-456",
            instance_id="cc-789",
            exit_code=0,
            duration_seconds=300,
        )
        assert event.event == ComputeEventType.CLAUDE_CODE_COMPLETED
        assert event.exit_code == 0
        assert event.duration_seconds == 300

    def test_compute_event_request_failed(self):
        """Test ComputeEventRequest for claude_code_failed."""
        event = ComputeEventRequest(
            event=ComputeEventType.CLAUDE_CODE_FAILED,
            compute_id="compute-001",
            task_id="task-456",
            instance_id="cc-789",
            exit_code=137,
            error="Out of memory",
        )
        assert event.event == ComputeEventType.CLAUDE_CODE_FAILED
        assert event.exit_code == 137
        assert event.error == "Out of memory"

    def test_compute_event_response(self):
        """Test ComputeEventResponse model."""
        response = ComputeEventResponse(
            status="acknowledged",
            event="claude_code_started",
            compute_id="compute-001",
            task_id="task-456",
        )
        assert response.status == "acknowledged"
        assert response.event == "claude_code_started"


# =============================================================================
# Registry SSE Event Queue Tests
# =============================================================================


class TestRegistrySSEEventQueue:
    """Tests for ComputeRegistry SSE event queue functionality."""

    @pytest.fixture
    def registry(self):
        """Create a registry for testing."""
        return ComputeRegistry()

    @pytest.fixture
    def sample_instance(self):
        """Create a sample instance for testing."""
        return ComputeInstance(
            instance_id="compute-001",
            name="Test Compute",
            endpoint="sse",
            capabilities=InstanceCapabilities(
                agents=["coding", "testing"],
            ),
            metadata={
                "connection_type": "sse",
            },
        )

    @pytest.mark.asyncio
    async def test_event_queue_created_on_get_pending(self, registry, sample_instance):
        """Test that event queue is created lazily on get_pending_event."""
        await registry.add_instance(sample_instance)

        # Event queue should be created on first access
        event = await registry.get_pending_event("compute-001", timeout=0.01)

        # Should return None (no events pending)
        assert event is None

        # But should now have an event queue
        assert registry.has_sse_connection("compute-001")

    @pytest.mark.asyncio
    async def test_queue_and_get_event(self, registry, sample_instance):
        """Test queuing and retrieving an event."""
        await registry.add_instance(sample_instance)

        # Initialize the queue
        await registry.get_pending_event("compute-001", timeout=0.01)

        # Queue an event
        queued = await registry.queue_event(
            "compute-001",
            "work_assigned",
            {"task_id": "task-123", "title": "Test task"},
        )
        assert queued is True

        # Get the event
        event = await registry.get_pending_event("compute-001", timeout=1.0)
        assert event is not None
        assert event["event_type"] == "work_assigned"
        assert event["data"]["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_queue_event_not_connected(self, registry):
        """Test queuing event for non-connected instance."""
        # Try to queue event for non-existent instance
        queued = await registry.queue_event(
            "nonexistent",
            "work_assigned",
            {"task_id": "task-123"},
        )
        assert queued is False

    @pytest.mark.asyncio
    async def test_event_queue_removed_on_deregister(self, registry, sample_instance):
        """Test that event queue is removed when instance is deregistered."""
        await registry.add_instance(sample_instance)

        # Initialize queue
        await registry.get_pending_event("compute-001", timeout=0.01)
        assert registry.has_sse_connection("compute-001")

        # Remove instance
        await registry.remove_instance("compute-001")

        # Queue should be gone
        assert not registry.has_sse_connection("compute-001")

    @pytest.mark.asyncio
    async def test_multiple_events_fifo_order(self, registry, sample_instance):
        """Test that events are delivered in FIFO order."""
        await registry.add_instance(sample_instance)
        await registry.get_pending_event("compute-001", timeout=0.01)

        # Queue multiple events
        await registry.queue_event("compute-001", "event1", {"order": 1})
        await registry.queue_event("compute-001", "event2", {"order": 2})
        await registry.queue_event("compute-001", "event3", {"order": 3})

        # Get events - should be in order
        event1 = await registry.get_pending_event("compute-001", timeout=0.1)
        event2 = await registry.get_pending_event("compute-001", timeout=0.1)
        event3 = await registry.get_pending_event("compute-001", timeout=0.1)

        assert event1["event_type"] == "event1"
        assert event1["data"]["order"] == 1
        assert event2["event_type"] == "event2"
        assert event2["data"]["order"] == 2
        assert event3["event_type"] == "event3"
        assert event3["data"]["order"] == 3

    @pytest.mark.asyncio
    async def test_stats_includes_sse_connections(self, registry, sample_instance):
        """Test that get_stats includes SSE connection count."""
        await registry.add_instance(sample_instance)

        # Before queue initialization
        stats = registry.get_stats()
        assert stats["sse_connections"] == 0

        # After queue initialization
        await registry.get_pending_event("compute-001", timeout=0.01)
        stats = registry.get_stats()
        assert stats["sse_connections"] == 1


# =============================================================================
# SSE Endpoint Helper Function Tests
# =============================================================================


class TestSSEHelperFunctions:
    """Tests for SSE endpoint helper functions."""

    def test_parse_capabilities(self):
        """Test _parse_capabilities helper function."""
        from api.compute import _parse_capabilities

        # Basic parsing
        caps = _parse_capabilities("coding,testing,documentation")
        assert caps == ["coding", "testing", "documentation"]

        # With spaces
        caps = _parse_capabilities("coding, testing , documentation")
        assert caps == ["coding", "testing", "documentation"]

        # Empty string
        caps = _parse_capabilities("")
        assert caps == []

        # None
        caps = _parse_capabilities(None)
        assert caps == []

    def test_parse_resources(self):
        """Test _parse_resources helper function."""
        from api.compute import _parse_resources

        # Basic parsing
        res = _parse_resources("cpu=4,memory=16gb")
        assert res["cpu"] == 4
        assert res["memory"] == 16

        # Float values
        res = _parse_resources("cpu=4.5,memory=16.5gb")
        assert res["cpu"] == 4.5
        assert res["memory"] == 16.5

        # Empty string
        res = _parse_resources("")
        assert res == {}

        # None
        res = _parse_resources(None)
        assert res == {}


# =============================================================================
# Stale Registry Reconnection Tests
# =============================================================================


class TestStaleRegistryReconnection:
    """Tests for stale compute instance reconnection after serving restart."""

    @pytest.fixture
    def registry(self):
        """Create a registry for testing."""
        return ComputeRegistry()

    @pytest.fixture
    def sample_instance(self):
        """Create a sample instance for testing."""
        return ComputeInstance(
            instance_id="compute-001",
            name="Test Compute",
            endpoint="sse",
            capabilities=InstanceCapabilities(
                agents=["coding", "testing"],
            ),
            metadata={
                "connection_type": "sse",
            },
        )

    @pytest.mark.asyncio
    async def test_stale_instance_has_no_sse_connection(self, registry, sample_instance):
        """Instances loaded from storage have no SSE event queue."""
        await registry.add_instance(sample_instance)

        # Instance exists but has no SSE connection (simulates post-restart state)
        instance = await registry.get_instance("compute-001")
        assert instance is not None
        assert not registry.has_sse_connection("compute-001")

    @pytest.mark.asyncio
    async def test_active_instance_has_sse_connection(self, registry, sample_instance):
        """Instances with active SSE streams have an event queue."""
        await registry.add_instance(sample_instance)

        # Simulate SSE connection by accessing the event queue
        await registry.get_pending_event("compute-001", timeout=0.01)

        assert registry.has_sse_connection("compute-001")

    @pytest.mark.asyncio
    async def test_stale_instance_can_be_removed_for_reconnection(self, registry, sample_instance):
        """Stale instances (no SSE) can be removed to allow reconnection."""
        await registry.add_instance(sample_instance)

        # Verify stale (no SSE connection)
        assert not registry.has_sse_connection("compute-001")

        # Remove stale entry
        removed = await registry.remove_instance("compute-001")
        assert removed is True

        # Can now re-add
        sample_instance.registered_at = None
        sample_instance.last_heartbeat = None
        await registry.add_instance(sample_instance)
        instance = await registry.get_instance("compute-001")
        assert instance is not None

    @pytest.mark.asyncio
    async def test_active_instance_cannot_be_re_added(self, registry, sample_instance):
        """Active instances (with SSE) should reject duplicate registration."""
        await registry.add_instance(sample_instance)
        await registry.get_pending_event("compute-001", timeout=0.01)

        assert registry.has_sse_connection("compute-001")

        # Attempting to add again should fail
        duplicate = ComputeInstance(
            instance_id="compute-001",
            name="Duplicate",
            endpoint="sse",
            capabilities=InstanceCapabilities(agents=[]),
        )
        with pytest.raises(ValueError, match="already registered"):
            await registry.add_instance(duplicate)
