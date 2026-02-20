"""Unit tests for SSE event client functionality."""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

import pytest

from services.sse_event_client import (
    SSEEventClient,
    MergeConflictEvent,
    WorkAssignedEvent,
    WorkCancelledEvent,
    WorkCompletedEvent,
    ShutdownEvent,
    get_sse_event_client,
    set_sse_event_client,
    initialize_sse_event_client
)


class TestDataClasses:
    """Tests for event dataclasses."""

    def test_merge_conflict_event(self):
        """Test MergeConflictEvent creation."""
        event = MergeConflictEvent(
            issue_id="issue-123",
            branch="feat/test",
            conflicting_files=["file1.py", "file2.py"],
            main_head="abc123",
            message="Conflicts detected"
        )

        assert event.issue_id == "issue-123"
        assert event.branch == "feat/test"
        assert len(event.conflicting_files) == 2
        assert event.main_head == "abc123"

    def test_work_assigned_event(self):
        """Test WorkAssignedEvent creation."""
        event = WorkAssignedEvent(
            task_id="task-123",
            title="Test Task",
            description="Test description",
            branch_name="feat/task-123",
            skills={"merged_instructions": "Test"},
            context={"repository": "test/repo"},
            mcp_config={"server_url": "http://localhost:8002"}
        )

        assert event.task_id == "task-123"
        assert event.title == "Test Task"
        assert event.branch_name == "feat/task-123"

    def test_work_cancelled_event(self):
        """Test WorkCancelledEvent creation."""
        event = WorkCancelledEvent(
            task_id="task-123",
            reason="User requested cancellation",
            action="stop"
        )

        assert event.task_id == "task-123"
        assert event.reason == "User requested cancellation"
        assert event.action == "stop"

    def test_work_completed_event(self):
        """Test WorkCompletedEvent creation."""
        event = WorkCompletedEvent(
            issue_id="issue-123",
            branch="feat/test",
            merge_commit="abc123",
            merged_at="2024-01-30T10:00:00Z"
        )

        assert event.issue_id == "issue-123"
        assert event.merge_commit == "abc123"

    def test_shutdown_event(self):
        """Test ShutdownEvent creation."""
        event = ShutdownEvent(
            reason="Maintenance window",
            grace_period_seconds=60
        )

        assert event.reason == "Maintenance window"
        assert event.grace_period_seconds == 60


class TestSSEEventClientInitialization:
    """Tests for SSEEventClient initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=["claude_code"],
            resources={"cpu": 4, "memory": "8GB"}
        )

        assert client.serving_url == "http://localhost:8002"
        assert client.compute_id == "compute-001"
        assert client.api_key == "test-key"
        assert client.capabilities == ["claude_code"]
        assert client.resources == {"cpu": 4, "memory": "8GB"}
        assert client._running is False
        assert client._connected is False
        assert client._last_event_time is None

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from serving_url."""
        client = SSEEventClient(
            serving_url="http://localhost:8002///",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        assert client.serving_url == "http://localhost:8002"

    def test_init_registers_builtin_handlers(self):
        """Test that built-in handlers are registered."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        assert "work_assigned" in client._handlers
        assert "work_cancelled" in client._handlers
        assert "work_completed" in client._handlers
        assert "merge_conflict" in client._handlers
        assert len(client._handlers["work_assigned"]) == 1
        assert len(client._handlers["work_cancelled"]) == 1
        assert len(client._handlers["work_completed"]) == 1
        assert len(client._handlers["merge_conflict"]) == 1

    def test_init_with_custom_reconnect_settings(self):
        """Test initialization with custom reconnect settings."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={},
            reconnect_delay=10,
            max_reconnect_delay=120
        )

        assert client.reconnect_delay == 10
        assert client.max_reconnect_delay == 120

    def test_init_shutdown_state(self):
        """Test that shutdown state is properly initialized."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=["python"],
            resources={"cpu": 1, "memory": "1gb"}
        )

        assert client._shutdown_requested is False
        assert client._shutdown_callback is None
        assert client._shutdown_task is None


class TestEventHandlerRegistration:
    """Tests for event handler registration."""

    @pytest.mark.asyncio
    async def test_register_handler(self):
        """Test registering an event handler."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def custom_handler(event_type: str, data: dict):
            pass

        client.on("custom_event", custom_handler)

        assert "custom_event" in client._handlers
        assert custom_handler in client._handlers["custom_event"]

    @pytest.mark.asyncio
    async def test_register_multiple_handlers_same_event(self):
        """Test registering multiple handlers for the same event."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def handler1(event_type: str, data: dict):
            pass

        async def handler2(event_type: str, data: dict):
            pass

        client.on("test_event", handler1)
        client.on("test_event", handler2)

        # Should include built-in handlers + our custom handlers
        assert handler1 in client._handlers["test_event"]
        assert handler2 in client._handlers["test_event"]

    @pytest.mark.asyncio
    async def test_unregister_specific_handler(self):
        """Test unregistering a specific handler."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def handler1(event_type: str, data: dict):
            pass

        async def handler2(event_type: str, data: dict):
            pass

        client.on("test_event", handler1)
        client.on("test_event", handler2)
        client.off("test_event", handler1)

        assert handler1 not in client._handlers["test_event"]
        assert handler2 in client._handlers["test_event"]

    @pytest.mark.asyncio
    async def test_unregister_all_handlers_for_event(self):
        """Test unregistering all handlers for an event."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def handler1(event_type: str, data: dict):
            pass

        async def handler2(event_type: str, data: dict):
            pass

        client.on("test_event", handler1)
        client.on("test_event", handler2)
        client.off("test_event")

        assert "test_event" not in client._handlers


class TestShutdownHandling:
    """Tests for SSE event client shutdown functionality."""

    def test_set_shutdown_callback(self):
        """Test setting the shutdown callback."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def my_callback(grace_period: int) -> None:
            pass

        client.set_shutdown_callback(my_callback)

        assert client._shutdown_callback is my_callback

    def test_is_shutdown_requested_property(self):
        """Test is_shutdown_requested property."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        assert client.is_shutdown_requested is False

        client._shutdown_requested = True

        assert client.is_shutdown_requested is True

    @pytest.mark.asyncio
    async def test_handle_shutdown_event_sets_flag(self):
        """Test that handling shutdown event sets the shutdown flag."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "reason": "Maintenance window",
            "grace_period_seconds": 30
        }

        # Mock the stop method to prevent actual shutdown
        client.stop = AsyncMock()

        await client._handle_shutdown_event("shutdown", event_data)

        assert client._shutdown_requested is True

    @pytest.mark.asyncio
    async def test_handle_shutdown_event_ignores_duplicate(self):
        """Test that duplicate shutdown events are ignored."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        # Set shutdown as already requested
        client._shutdown_requested = True

        event_data = {
            "reason": "Another shutdown",
            "grace_period_seconds": 60
        }

        # Should not create a new shutdown task
        await client._handle_shutdown_event("shutdown", event_data)

        assert client._shutdown_task is None

    @pytest.mark.asyncio
    async def test_handle_shutdown_event_with_callback(self):
        """Test shutdown event with registered callback."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        callback_called = False
        callback_grace_period = None

        async def my_callback(grace_period: int) -> None:
            nonlocal callback_called, callback_grace_period
            callback_called = True
            callback_grace_period = grace_period

        client.set_shutdown_callback(my_callback)
        client.stop = AsyncMock()

        event_data = {
            "reason": "Scheduled maintenance",
            "grace_period_seconds": 45
        }

        await client._handle_shutdown_event("shutdown", event_data)

        # Wait for the shutdown task to be created and start executing
        assert client._shutdown_task is not None
        await client._shutdown_task

        assert callback_called is True
        assert callback_grace_period == 45

    @pytest.mark.asyncio
    async def test_handle_shutdown_event_default_values(self):
        """Test shutdown event with missing fields uses defaults."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        callback_grace_period = None

        async def my_callback(grace_period: int) -> None:
            nonlocal callback_grace_period
            callback_grace_period = grace_period

        client.set_shutdown_callback(my_callback)
        client.stop = AsyncMock()

        # Empty event data - should use defaults
        event_data = {}

        await client._handle_shutdown_event("shutdown", event_data)
        await client._shutdown_task

        assert callback_grace_period == 60  # Default grace period

    @pytest.mark.asyncio
    async def test_execute_graceful_shutdown_calls_callback(self):
        """Test that _execute_graceful_shutdown calls the callback."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        callback_called = False

        async def my_callback(grace_period: int) -> None:
            nonlocal callback_called
            callback_called = True

        client._shutdown_callback = my_callback
        client.stop = AsyncMock()

        await client._execute_graceful_shutdown(30)

        assert callback_called is True
        client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_graceful_shutdown_handles_callback_error(self):
        """Test that callback errors are handled gracefully."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def failing_callback(grace_period: int) -> None:
            raise Exception("Callback error")

        client._shutdown_callback = failing_callback
        client.stop = AsyncMock()

        # Should not raise, should still call stop
        await client._execute_graceful_shutdown(30)

        client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_delayed_stop(self):
        """Test the delayed stop functionality."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        client.stop = AsyncMock()

        # Use a very short delay for testing
        await client._delayed_stop(0)

        client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_delayed_stop_cancelled(self):
        """Test that delayed stop can be cancelled."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        client.stop = AsyncMock()

        # Start delayed stop with longer delay
        task = asyncio.create_task(client._delayed_stop(10))

        # Cancel it immediately
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Stop should not have been called
        client.stop.assert_not_called()

    def test_get_status_includes_shutdown_requested(self):
        """Test that get_status includes shutdown_requested field."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        status = client.get_status()

        assert "shutdown_requested" in status
        assert status["shutdown_requested"] is False

        client._shutdown_requested = True

        status = client.get_status()
        assert status["shutdown_requested"] is True

    @pytest.mark.asyncio
    async def test_stop_cancels_shutdown_task(self):
        """Test that stop() cancels any pending shutdown task."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        # Create a mock shutdown task
        async def long_task():
            await asyncio.sleep(100)

        client._shutdown_task = asyncio.create_task(long_task())

        # Stop should cancel the task
        await client.stop()

        assert client._shutdown_task is None


class TestWorkAssignedHandler:
    """Tests for _handle_work_assigned built-in handler."""

    @pytest.mark.asyncio
    async def test_handle_work_assigned_no_spawner(self):
        """Test work_assigned handler when no spawner is available."""
        from services.claude_code_spawner import set_claude_code_spawner

        # Ensure no spawner is set
        set_claude_code_spawner(None)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "Test",
            "skills": {},
            "context": {},
            "mcp_config": {}
        }

        # Should not raise, just log error
        await client._handle_work_assigned("work_assigned", event_data)

    @pytest.mark.asyncio
    async def test_handle_work_assigned_success(self):
        """Test work_assigned handler successfully spawns Claude Code."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "Test",
            "skills": {"merged_instructions": "Test skills"},
            "context": {"repository": "test/repo"},
            "mcp_config": {}
        }

        await client._handle_work_assigned("work_assigned", event_data)

        mock_spawner.spawn.assert_called_once_with(event_data)

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_assigned_spawn_fails(self):
        """Test work_assigned handler when spawn fails."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(return_value=False)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-456",
            "title": "Test Task",
            "skills": {},
            "context": {},
            "mcp_config": {}
        }

        # Should not raise, just log warning
        await client._handle_work_assigned("work_assigned", event_data)

        mock_spawner.spawn.assert_called_once()

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_assigned_exception(self):
        """Test work_assigned handler when spawn raises exception."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(side_effect=Exception("Spawn error"))
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-789",
            "skills": {},
            "context": {},
            "mcp_config": {}
        }

        # Should not raise, just log error
        await client._handle_work_assigned("work_assigned", event_data)

        # Cleanup
        set_claude_code_spawner(None)


class TestWorkCancelledHandler:
    """Tests for _handle_work_cancelled built-in handler."""

    @pytest.mark.asyncio
    async def test_handle_work_cancelled_no_spawner(self):
        """Test work_cancelled handler when no spawner is available."""
        from services.claude_code_spawner import set_claude_code_spawner

        set_claude_code_spawner(None)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-123",
            "reason": "User cancelled",
            "action": "stop"
        }

        # Should not raise, just log error
        await client._handle_work_cancelled("work_cancelled", event_data)

    @pytest.mark.asyncio
    async def test_handle_work_cancelled_success(self):
        """Test work_cancelled handler successfully stops Claude Code."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.stop = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-123",
            "reason": "Timeout",
            "action": "stop"
        }

        await client._handle_work_cancelled("work_cancelled", event_data)

        mock_spawner.stop.assert_called_once_with("task-123", force=False, timeout=30)

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_cancelled_no_reason(self):
        """Test work_cancelled handler with missing reason."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.stop = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-456"
        }

        await client._handle_work_cancelled("work_cancelled", event_data)

        mock_spawner.stop.assert_called_once()

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_cancelled_stop_fails(self):
        """Test work_cancelled handler when stop fails."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.stop = AsyncMock(return_value=False)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-789",
            "reason": "Test"
        }

        # Should not raise, just log warning
        await client._handle_work_cancelled("work_cancelled", event_data)

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_cancelled_exception(self):
        """Test work_cancelled handler when stop raises exception."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.stop = AsyncMock(side_effect=Exception("Stop error"))
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "task_id": "task-999",
            "reason": "Test"
        }

        # Should not raise, just log error
        await client._handle_work_cancelled("work_cancelled", event_data)

        # Cleanup
        set_claude_code_spawner(None)


class TestWorkCompletedHandler:
    """Tests for _handle_work_completed built-in handler."""

    @pytest.mark.asyncio
    async def test_handle_work_completed_no_spawner(self):
        """Test work_completed handler when no spawner is available."""
        from services.claude_code_spawner import set_claude_code_spawner

        set_claude_code_spawner(None)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/issue-123",
            "merge_commit": "abc123def",
            "merged_at": "2026-01-30T10:30:00Z"
        }

        # Should not raise, just log warning
        await client._handle_work_completed("work_completed", event_data)

    @pytest.mark.asyncio
    async def test_handle_work_completed_with_matching_instance(self):
        """Test work_completed handler deletes branch and cleans up workspace."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = MagicMock()
        mock_spawner._instances = {
            "task-456": {
                "instance_id": "cc-12345678",
                "task_id": "task-456",
                "branch_name": "feat/issue-123"
            }
        }
        mock_spawner._cleanup_instance = MagicMock()
        mock_spawner.delete_local_branch = MagicMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/issue-123",
            "merge_commit": "abc123def",
            "merged_at": "2026-01-30T10:30:00Z"
        }

        await client._handle_work_completed("work_completed", event_data)

        # Should explicitly delete the local branch by name
        mock_spawner.delete_local_branch.assert_called_once_with("feat/issue-123")
        # Should clean up the instance with workspace cleanup
        mock_spawner._cleanup_instance.assert_called_once_with("task-456", cleanup_workspace=True)

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_completed_no_matching_instance(self):
        """Test work_completed handler when no instance matches the branch."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = MagicMock()
        mock_spawner._instances = {
            "task-456": {
                "instance_id": "cc-12345678",
                "task_id": "task-456",
                "branch_name": "feat/other-branch"
            }
        }
        mock_spawner._cleanup_instance = MagicMock()
        mock_spawner.delete_local_branch = MagicMock(return_value=False)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/issue-123",
            "merge_commit": "abc123def",
            "merged_at": "2026-01-30T10:30:00Z"
        }

        # Should not raise, just log info
        await client._handle_work_completed("work_completed", event_data)

        # Should still attempt branch deletion even if no tracked instance
        mock_spawner.delete_local_branch.assert_called_once_with("feat/issue-123")
        # Should NOT call workspace cleanup since no matching instance
        mock_spawner._cleanup_instance.assert_not_called()

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_completed_empty_instances(self):
        """Test work_completed handler when instances dict is empty."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = MagicMock()
        mock_spawner._instances = {}
        mock_spawner._cleanup_instance = MagicMock()
        mock_spawner.delete_local_branch = MagicMock(return_value=False)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/issue-123",
            "merge_commit": "abc123def",
            "merged_at": "2026-01-30T10:30:00Z"
        }

        # Should not raise
        await client._handle_work_completed("work_completed", event_data)

        # Should still attempt branch deletion even with empty instances
        mock_spawner.delete_local_branch.assert_called_once_with("feat/issue-123")
        # Should NOT call workspace cleanup since no instances
        mock_spawner._cleanup_instance.assert_not_called()

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_completed_minimal_data(self):
        """Test work_completed handler with minimal event data."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = MagicMock()
        mock_spawner._instances = {}
        mock_spawner.delete_local_branch = MagicMock(return_value=False)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        # Minimal data with only required fields
        event_data = {
            "branch": "feat/test"
        }

        # Should not raise even with minimal data
        await client._handle_work_completed("work_completed", event_data)

        # Branch deletion should still be attempted
        mock_spawner.delete_local_branch.assert_called_once_with("feat/test")

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_completed_missing_branch_skips_gracefully(self):
        """Test work_completed handler when branch is missing from event data."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = MagicMock()
        mock_spawner._instances = {}
        mock_spawner.delete_local_branch = MagicMock()
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        # Event data with no branch field
        event_data = {
            "issue_id": "issue-123",
            "merge_commit": "abc123def"
        }

        # Should not raise — just log warning and return
        await client._handle_work_completed("work_completed", event_data)

        # Should NOT attempt branch deletion without a branch name
        mock_spawner.delete_local_branch.assert_not_called()

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_work_completed_multiple_instances(self):
        """Test work_completed handler finds correct instance among multiple."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = MagicMock()
        mock_spawner._instances = {
            "task-111": {
                "instance_id": "cc-aaaaaaaa",
                "task_id": "task-111",
                "branch_name": "feat/branch-a"
            },
            "task-222": {
                "instance_id": "cc-bbbbbbbb",
                "task_id": "task-222",
                "branch_name": "feat/branch-b"
            },
            "task-333": {
                "instance_id": "cc-cccccccc",
                "task_id": "task-333",
                "branch_name": "feat/branch-c"
            }
        }
        mock_spawner._cleanup_instance = MagicMock()
        mock_spawner.delete_local_branch = MagicMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-222",
            "branch": "feat/branch-b",
            "merge_commit": "def456ghi",
            "merged_at": "2026-01-30T11:00:00Z"
        }

        await client._handle_work_completed("work_completed", event_data)

        # Should explicitly delete the correct branch
        mock_spawner.delete_local_branch.assert_called_once_with("feat/branch-b")
        # Should clean up only the matching instance
        mock_spawner._cleanup_instance.assert_called_once_with("task-222", cleanup_workspace=True)

        # Cleanup
        set_claude_code_spawner(None)


class TestMergeConflictHandler:
    """Tests for _handle_merge_conflict built-in handler."""

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_delegates_to_conflict_handler(self):
        """Test merge_conflict handler delegates to ConflictResolutionHandler."""
        from services.conflict_handler import set_conflict_handler, ConflictResolutionHandler

        mock_handler = AsyncMock(spec=ConflictResolutionHandler)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.method = "stdin"
        mock_handler.handle_merge_conflict = AsyncMock(return_value=mock_result)
        set_conflict_handler(mock_handler)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py", "file2.py"],
            "main_head": "abc123",
            "message": "Resolve conflicts"
        }

        await client._handle_merge_conflict("merge_conflict", event_data)

        mock_handler.handle_merge_conflict.assert_called_once_with("merge_conflict", event_data)

        # Cleanup
        set_conflict_handler(None)

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_initializes_handler_if_missing(self):
        """Test merge_conflict handler creates ConflictResolutionHandler if not set."""
        from services.conflict_handler import set_conflict_handler, get_conflict_handler
        from services.claude_code_spawner import set_claude_code_spawner

        set_conflict_handler(None)
        set_claude_code_spawner(None)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve",
            "task_id": "task-123"
        }

        # Mock the handler's handle_merge_conflict after initialization
        with patch('services.conflict_handler.ConflictResolutionHandler.handle_merge_conflict',
                   new_callable=AsyncMock) as mock_handle:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.method = "automatic"
            mock_handle.return_value = mock_result

            await client._handle_merge_conflict("merge_conflict", event_data)

        # Handler should have been initialized
        handler = get_conflict_handler()
        assert handler is not None

        # Cleanup
        set_conflict_handler(None)

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_finds_task_id_from_spawner(self):
        """Test merge_conflict handler finds task_id from spawner instances."""
        from services.conflict_handler import set_conflict_handler, ConflictResolutionHandler
        from services.claude_code_spawner import set_claude_code_spawner

        mock_handler = AsyncMock(spec=ConflictResolutionHandler)
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.method = "stdin"
        mock_handler.handle_merge_conflict = AsyncMock(return_value=mock_result)
        set_conflict_handler(mock_handler)

        # Set up spawner with an instance matching the branch
        mock_spawner = MagicMock()
        mock_spawner._instances = {
            "task-456": {
                "instance_id": "cc-12345678",
                "branch_name": "feat/test"
            }
        }
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        # Event without task_id - should be resolved from spawner
        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve"
        }

        await client._handle_merge_conflict("merge_conflict", event_data)

        # Should have been called with task_id added
        call_args = mock_handler.handle_merge_conflict.call_args
        assert call_args[0][1]["task_id"] == "task-456"

        # Cleanup
        set_conflict_handler(None)
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_spawns_resolver_on_failure(self):
        """Test merge_conflict handler spawns resolver when handling fails."""
        from services.conflict_handler import set_conflict_handler, ConflictResolutionHandler
        from services.claude_code_spawner import set_claude_code_spawner

        mock_handler = AsyncMock(spec=ConflictResolutionHandler)
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "All methods failed"
        mock_handler.handle_merge_conflict = AsyncMock(return_value=mock_result)
        set_conflict_handler(mock_handler)

        mock_spawner = AsyncMock()
        mock_spawner._instances = {}
        mock_spawner.workspace_path = "/workspace"
        mock_spawner.spawn_conflict_resolution = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve",
            "task_id": "task-789"
        }

        await client._handle_merge_conflict("merge_conflict", event_data)

        mock_spawner.spawn_conflict_resolution.assert_called_once_with(event_data)

        # Cleanup
        set_conflict_handler(None)
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_handles_exception(self):
        """Test merge_conflict handler handles exceptions gracefully."""
        from services.conflict_handler import set_conflict_handler, ConflictResolutionHandler

        mock_handler = AsyncMock(spec=ConflictResolutionHandler)
        mock_handler.handle_merge_conflict = AsyncMock(
            side_effect=Exception("Unexpected error")
        )
        set_conflict_handler(mock_handler)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve"
        }

        # Should not raise
        await client._handle_merge_conflict("merge_conflict", event_data)

        # Cleanup
        set_conflict_handler(None)

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_no_spawner_for_fallback(self):
        """Test merge_conflict handler when no spawner available for fallback."""
        from services.conflict_handler import set_conflict_handler, ConflictResolutionHandler
        from services.claude_code_spawner import set_claude_code_spawner

        mock_handler = AsyncMock(spec=ConflictResolutionHandler)
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.message = "Failed"
        mock_handler.handle_merge_conflict = AsyncMock(return_value=mock_result)
        set_conflict_handler(mock_handler)

        set_claude_code_spawner(None)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve"
        }

        # Should not raise even without spawner
        await client._handle_merge_conflict("merge_conflict", event_data)

        # Cleanup
        set_conflict_handler(None)


class TestClientLifecycle:
    """Tests for client start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_client(self):
        """Test starting the SSE client."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        with patch.object(client, '_connection_loop', new_callable=AsyncMock):
            await client.start()

        assert client._running is True
        assert client._task is not None

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test starting client when already running."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        with patch.object(client, '_connection_loop', new_callable=AsyncMock):
            await client.start()
            task1 = client._task

            # Try to start again
            await client.start()
            task2 = client._task

        # Should be the same task
        assert task1 is task2

    @pytest.mark.asyncio
    async def test_stop_client(self):
        """Test stopping the SSE client."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        with patch.object(client, '_connection_loop', new_callable=AsyncMock):
            await client.start()
            await client.stop()

        assert client._running is False
        assert client._task is None
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_is_connected_property(self):
        """Test is_connected property."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        assert client.is_connected is False

        client._connected = True
        assert client.is_connected is True


class TestHandleEvent:
    """Tests for _handle_event method."""

    @pytest.mark.asyncio
    async def test_handle_event_parses_json(self):
        """Test that _handle_event parses JSON data."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        handler_called = asyncio.Event()
        received_data = {}

        async def test_handler(event_type: str, data: dict):
            received_data.update(data)
            handler_called.set()

        client.on("test_event", test_handler)

        data_str = json.dumps({"key": "value", "number": 42})
        await client._handle_event("test_event", data_str)

        await asyncio.wait_for(handler_called.wait(), timeout=1.0)

        assert received_data["key"] == "value"
        assert received_data["number"] == 42
        assert client._last_event_time is not None

    @pytest.mark.asyncio
    async def test_handle_event_invalid_json(self):
        """Test handling event with invalid JSON."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        handler_called = False

        async def test_handler(event_type: str, data: dict):
            nonlocal handler_called
            handler_called = True

        client.on("test_event", test_handler)

        # Invalid JSON should not call handler
        await client._handle_event("test_event", "{invalid json}")

        await asyncio.sleep(0.1)
        assert handler_called is False

    @pytest.mark.asyncio
    async def test_handle_event_no_handlers(self):
        """Test handling event with no registered handlers."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        data_str = json.dumps({"test": "data"})

        # Should not raise
        await client._handle_event("unknown_event", data_str)

    @pytest.mark.asyncio
    async def test_handle_event_catchall_handler(self):
        """Test handling event with catch-all handler."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        handler_called = asyncio.Event()
        received_event_type = None

        async def catchall_handler(event_type: str, data: dict):
            nonlocal received_event_type
            received_event_type = event_type
            handler_called.set()

        client.on("*", catchall_handler)

        data_str = json.dumps({"test": "data"})
        await client._handle_event("any_event", data_str)

        await asyncio.wait_for(handler_called.wait(), timeout=1.0)

        assert received_event_type == "any_event"

    @pytest.mark.asyncio
    async def test_handle_event_handler_exception(self):
        """Test that handler exceptions don't break event processing."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        handler1_called = asyncio.Event()
        handler2_called = asyncio.Event()

        async def failing_handler(event_type: str, data: dict):
            handler1_called.set()
            raise Exception("Handler error")

        async def working_handler(event_type: str, data: dict):
            handler2_called.set()

        client.on("test_event", failing_handler)
        client.on("test_event", working_handler)

        data_str = json.dumps({"test": "data"})
        await client._handle_event("test_event", data_str)

        # Both handlers should be called
        await asyncio.wait_for(handler1_called.wait(), timeout=1.0)
        await asyncio.wait_for(handler2_called.wait(), timeout=1.0)


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_initial(self):
        """Test status when client is just created."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=["claude_code"],
            resources={"cpu": 4}
        )

        status = client.get_status()

        assert status["connected"] is False
        assert status["running"] is False
        assert status["compute_id"] == "compute-001"
        assert status["serving_url"] == "http://localhost:8002"
        assert status["last_event_time"] is None
        assert "work_assigned" in status["registered_handlers"]
        assert "work_cancelled" in status["registered_handlers"]

    @pytest.mark.asyncio
    async def test_get_status_after_event(self):
        """Test status after receiving an event."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        async def test_handler(event_type: str, data: dict):
            pass

        client.on("custom_event", test_handler)

        # Simulate receiving an event
        data_str = json.dumps({"test": "data"})
        await client._handle_event("custom_event", data_str)

        status = client.get_status()

        assert status["last_event_time"] is not None
        assert "custom_event" in status["registered_handlers"]


class TestGlobalClientFunctions:
    """Tests for global client management functions."""

    def test_get_client_returns_none_initially(self):
        """Test that get_sse_event_client returns None initially."""
        set_sse_event_client(None)
        client = get_sse_event_client()
        assert client is None

    def test_set_and_get_client(self):
        """Test setting and getting global client."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        set_sse_event_client(client)
        retrieved = get_sse_event_client()

        assert retrieved is client

        # Cleanup
        set_sse_event_client(None)

    @pytest.mark.asyncio
    async def test_initialize_sse_event_client(self):
        """Test initialize_sse_event_client function."""
        with patch.object(SSEEventClient, 'start', new_callable=AsyncMock):
            client = await initialize_sse_event_client(
                serving_url="http://localhost:9000",
                compute_id="compute-002",
                api_key="init-key",
                capabilities=["claude_code"],
                resources={"cpu": 8}
            )

        assert client is not None
        assert client.serving_url == "http://localhost:9000"
        assert client.compute_id == "compute-002"
        assert client.api_key == "init-key"
        assert client.capabilities == ["claude_code"]
        assert get_sse_event_client() is client

        # Cleanup
        set_sse_event_client(None)

    @pytest.mark.asyncio
    async def test_initialize_sse_event_client_with_custom_reconnect_settings(self):
        """Test initialize_sse_event_client with custom reconnect settings."""
        with patch.object(SSEEventClient, 'start', new_callable=AsyncMock):
            client = await initialize_sse_event_client(
                serving_url="http://localhost:9000",
                compute_id="compute-003",
                api_key="init-key",
                capabilities=["claude_code"],
                resources={"cpu": 8},
                reconnect_delay=10,
                max_reconnect_delay=120
            )

        assert client is not None
        assert client.reconnect_delay == 10
        assert client.max_reconnect_delay == 120
        assert get_sse_event_client() is client

        # Cleanup
        set_sse_event_client(None)

    @pytest.mark.asyncio
    async def test_initialize_sse_event_client_default_reconnect_settings(self):
        """Test initialize_sse_event_client uses default reconnect settings."""
        with patch.object(SSEEventClient, 'start', new_callable=AsyncMock):
            client = await initialize_sse_event_client(
                serving_url="http://localhost:9000",
                compute_id="compute-004",
                api_key="init-key",
                capabilities=[],
                resources={}
            )

        # Should use default values
        assert client.reconnect_delay == 5
        assert client.max_reconnect_delay == 60

        # Cleanup
        set_sse_event_client(None)


class TestGitTokenProvisionedHandler:
    """Tests for _handle_git_token_provisioned built-in handler."""

    def test_git_token_initialized_to_none(self):
        """Test that _git_token is initialized to None."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        assert client._git_token is None

    def test_git_token_provisioned_handler_registered(self):
        """Test that git_token_provisioned handler is registered."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        assert "git_token_provisioned" in client._handlers
        assert len(client._handlers["git_token_provisioned"]) == 1

    @pytest.mark.asyncio
    async def test_handle_git_token_provisioned_stores_token(self):
        """Test that handler stores the token."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-test",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "token": "cvn-ct-abc123def456",
            "compute_id": "compute-test"
        }

        await client._handle_git_token_provisioned("git_token_provisioned", event_data)

        assert client._git_token == "cvn-ct-abc123def456"

    @pytest.mark.asyncio
    async def test_handle_git_token_provisioned_no_token(self):
        """Test handler with missing token field."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "compute_id": "compute-001"
            # No token
        }

        await client._handle_git_token_provisioned("git_token_provisioned", event_data)

        assert client._git_token is None

    @pytest.mark.asyncio
    async def test_handle_git_token_provisioned_empty_token(self):
        """Test handler with empty token."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )

        event_data = {
            "token": "",
            "compute_id": "compute-001"
        }

        await client._handle_git_token_provisioned("git_token_provisioned", event_data)

        # Empty string is falsy, should be treated as missing
        assert client._git_token is None


class TestWorkAssignedWithGitToken:
    """Tests for Git token injection into work_assigned context."""

    @pytest.mark.asyncio
    async def test_work_assigned_injects_git_token(self):
        """Test that work_assigned injects git_token when available."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )
        client._git_token = "cvn-ct-testtoken123"

        event_data = {
            "task_id": "task-123",
            "title": "Test Task",
            "description": "Test",
            "skills": {},
            "context": {"repository": "test/repo"},
            "mcp_config": {}
        }

        await client._handle_work_assigned("work_assigned", event_data)

        # Verify spawn was called with git_token injected into context
        call_args = mock_spawner.spawn.call_args[0][0]
        assert call_args["context"]["git_token"] == "cvn-ct-testtoken123"
        assert call_args["context"]["repository"] == "test/repo"

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_work_assigned_no_git_token_leaves_context_unchanged(self):
        """Test that work_assigned doesn't modify context when no git_token."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )
        # _git_token is None by default

        event_data = {
            "task_id": "task-456",
            "title": "Test Task",
            "description": "Test",
            "skills": {},
            "context": {"repository": "test/repo"},
            "mcp_config": {}
        }

        await client._handle_work_assigned("work_assigned", event_data)

        call_args = mock_spawner.spawn.call_args[0][0]
        assert "git_token" not in call_args["context"]

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_work_assigned_creates_context_if_missing(self):
        """Test that git_token injection creates context dict if not present."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )
        client._git_token = "cvn-ct-testtoken789"

        event_data = {
            "task_id": "task-789",
            "title": "Test Task",
            "skills": {},
            "mcp_config": {}
            # No "context" key
        }

        await client._handle_work_assigned("work_assigned", event_data)

        call_args = mock_spawner.spawn.call_args[0][0]
        assert call_args["context"]["git_token"] == "cvn-ct-testtoken789"

        # Cleanup
        set_claude_code_spawner(None)

    @pytest.mark.asyncio
    async def test_work_assigned_does_not_mutate_original_data(self):
        """Test that git_token injection doesn't mutate the original event data dict."""
        from services.claude_code_spawner import set_claude_code_spawner

        mock_spawner = AsyncMock()
        mock_spawner.spawn = AsyncMock(return_value=True)
        set_claude_code_spawner(mock_spawner)

        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={}
        )
        client._git_token = "cvn-ct-testtoken101"

        original_context = {"repository": "test/repo"}
        event_data = {
            "task_id": "task-101",
            "title": "Test",
            "skills": {},
            "context": original_context,
            "mcp_config": {}
        }

        await client._handle_work_assigned("work_assigned", event_data)

        call_args = mock_spawner.spawn.call_args[0][0]
        assert call_args["context"]["git_token"] == "cvn-ct-testtoken101"

        # Cleanup
        set_claude_code_spawner(None)


class TestConnectionLoop:
    """Tests for connection loop behavior."""

    @pytest.mark.asyncio
    async def test_connection_loop_reconnect_on_error(self):
        """Test that connection loop reconnects on error."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={},
            reconnect_delay=0.01,  # Use short delay for testing
            max_reconnect_delay=5
        )

        connection_attempts = []

        async def mock_connect():
            connection_attempts.append(datetime.now())
            if len(connection_attempts) < 3:
                raise Exception("Connection failed")
            # Stop after 3 attempts
            client._running = False

        # Set _running = True so the loop enters
        client._running = True

        with patch.object(client, '_connect_and_listen', side_effect=mock_connect):
            await client._connection_loop()

        # Should have attempted to connect 3 times
        assert len(connection_attempts) == 3

    @pytest.mark.asyncio
    async def test_connection_loop_exponential_backoff(self):
        """Test that connection loop uses exponential backoff."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={},
            reconnect_delay=1,
            max_reconnect_delay=8
        )

        sleep_delays = []

        async def mock_connect():
            raise Exception("Connection failed")

        async def mock_sleep(delay):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 3:
                client._running = False

        # Set _running = True so the loop enters
        client._running = True

        with patch.object(client, '_connect_and_listen', side_effect=mock_connect), \
             patch('services.sse_event_client.asyncio.sleep', side_effect=mock_sleep):

            await client._connection_loop()

        # Should have exponential backoff: 1, 2, 4
        assert sleep_delays[0] == 1
        assert sleep_delays[1] == 2
        assert sleep_delays[2] == 4

    @pytest.mark.asyncio
    async def test_connection_loop_respects_max_delay(self):
        """Test that connection loop respects max reconnect delay."""
        client = SSEEventClient(
            serving_url="http://localhost:8002",
            compute_id="compute-001",
            api_key="test-key",
            capabilities=[],
            resources={},
            reconnect_delay=2,
            max_reconnect_delay=5
        )

        sleep_delays = []

        async def mock_connect():
            raise Exception("Connection failed")

        async def mock_sleep(delay):
            sleep_delays.append(delay)
            if len(sleep_delays) >= 4:
                client._running = False

        # Set _running = True so the loop enters
        client._running = True

        with patch.object(client, '_connect_and_listen', side_effect=mock_connect), \
             patch('services.sse_event_client.asyncio.sleep', side_effect=mock_sleep):

            await client._connection_loop()

        # Should cap at max_reconnect_delay: 2, 4, 5 (capped), 5 (capped)
        assert sleep_delays[0] == 2
        assert sleep_delays[1] == 4
        assert sleep_delays[2] == 5  # Capped at max
        assert sleep_delays[3] == 5  # Capped at max
