"""Tests for conflict resolution handler."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import tempfile
import os

from services.conflict_handler import (
    ConflictResolutionHandler,
    ConflictResolutionContext,
    ConflictResolutionResult,
    InstructionInjectionResult,
    initialize_conflict_handler,
    get_conflict_handler,
    set_conflict_handler
)


class TestConflictResolutionContext:
    """Tests for ConflictResolutionContext dataclass."""

    def test_create_context(self):
        """Test creating a conflict resolution context."""
        ctx = ConflictResolutionContext(
            issue_id="issue-123",
            branch="feat/test",
            conflicting_files=["file1.py", "file2.py"],
            main_head="abc123",
            message="Resolve conflicts"
        )

        assert ctx.issue_id == "issue-123"
        assert ctx.branch == "feat/test"
        assert ctx.conflicting_files == ["file1.py", "file2.py"]
        assert ctx.main_head == "abc123"
        assert ctx.message == "Resolve conflicts"
        assert ctx.task_id is None

    def test_create_context_with_task_id(self):
        """Test creating a context with task_id."""
        ctx = ConflictResolutionContext(
            issue_id="issue-123",
            branch="feat/test",
            conflicting_files=["file1.py"],
            main_head="abc123",
            message="Resolve conflicts",
            task_id="task-456"
        )

        assert ctx.task_id == "task-456"


class TestConflictResolutionResult:
    """Tests for ConflictResolutionResult dataclass."""

    def test_create_success_result(self):
        """Test creating a success result."""
        result = ConflictResolutionResult(
            success=True,
            message="Conflicts resolved",
            resolved_files=["file1.py"],
            remaining_conflicts=[]
        )

        assert result.success is True
        assert result.resolved_files == ["file1.py"]
        assert result.remaining_conflicts == []

    def test_create_failure_result(self):
        """Test creating a failure result."""
        result = ConflictResolutionResult(
            success=False,
            message="Manual intervention required",
            resolved_files=[],
            remaining_conflicts=["file1.py", "file2.py"]
        )

        assert result.success is False
        assert result.remaining_conflicts == ["file1.py", "file2.py"]


class TestInstructionInjectionResult:
    """Tests for InstructionInjectionResult dataclass."""

    def test_create_success_result(self):
        """Test creating a success injection result."""
        result = InstructionInjectionResult(
            success=True,
            message="Instructions injected",
            method="stdin"
        )

        assert result.success is True
        assert result.message == "Instructions injected"
        assert result.method == "stdin"

    def test_create_failure_result(self):
        """Test creating a failure injection result."""
        result = InstructionInjectionResult(
            success=False,
            message="No process available",
            method="none"
        )

        assert result.success is False
        assert result.method == "none"

    def test_default_method(self):
        """Test default method value."""
        result = InstructionInjectionResult(
            success=False,
            message="Failed"
        )

        assert result.method == "none"


class TestConflictResolutionHandler:
    """Tests for ConflictResolutionHandler."""

    def test_init(self):
        """Test handler initialization."""
        handler = ConflictResolutionHandler(
            workspace_path="/workspace"
        )

        assert handler.workspace_path == "/workspace"
        assert handler.mcp_client is None
        assert handler._current_context is None

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_stores_context(self):
        """Test handling a merge_conflict event stores context."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py", "file2.py"],
            "main_head": "abc123",
            "message": "Resolve conflicts",
            "task_id": "task-789"
        }

        # Mock _inject_instructions to avoid spawner dependency
        with patch.object(handler, '_inject_instructions', new_callable=AsyncMock) as mock_inject:
            mock_inject.return_value = InstructionInjectionResult(
                success=True,
                message="Injected",
                method="stdin"
            )

            result = await handler.handle_merge_conflict("merge_conflict", event_data)

        # Should have stored the context
        ctx = handler.get_current_context()
        assert ctx is not None
        assert ctx.issue_id == "issue-123"
        assert ctx.branch == "feat/test"
        assert ctx.conflicting_files == ["file1.py", "file2.py"]
        assert ctx.task_id == "task-789"

        # Should return injection result
        assert result.success is True
        assert result.method == "stdin"

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_with_callback(self):
        """Test handling merge_conflict with progress callback."""
        callback_events = []

        async def callback(event_type: str, data: dict):
            callback_events.append((event_type, data))

        handler = ConflictResolutionHandler(
            workspace_path="/workspace",
            progress_callback=callback
        )

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve"
        }

        with patch.object(handler, '_inject_instructions', new_callable=AsyncMock) as mock_inject:
            mock_inject.return_value = InstructionInjectionResult(
                success=True,
                message="Injected",
                method="stdin"
            )

            await handler.handle_merge_conflict("merge_conflict", event_data)

        # Should have called the callback
        assert len(callback_events) == 1
        assert callback_events[0][0] == "conflict_resolution_started"
        assert callback_events[0][1]["branch"] == "feat/test"

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_fallback_to_automatic(self):
        """Test fallback to automatic resolution when injection fails."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve",
            "task_id": "task-456"
        }

        with patch.object(handler, '_inject_instructions', new_callable=AsyncMock) as mock_inject, \
             patch.object(handler, 'attempt_automatic_resolution', new_callable=AsyncMock) as mock_auto:

            mock_inject.return_value = InstructionInjectionResult(
                success=False,
                message="No process found",
                method="none"
            )
            mock_auto.return_value = ConflictResolutionResult(
                success=True,
                message="Auto resolved",
                resolved_files=["file1.py"],
                remaining_conflicts=[]
            )

            result = await handler.handle_merge_conflict("merge_conflict", event_data)

        # Should have attempted automatic resolution
        mock_auto.assert_called_once()

        # Should return success with automatic method
        assert result.success is True
        assert result.method == "automatic"

    @pytest.mark.asyncio
    async def test_handle_merge_conflict_both_methods_fail(self):
        """Test when both injection and automatic resolution fail."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        event_data = {
            "issue_id": "issue-123",
            "branch": "feat/test",
            "conflicting_files": ["file1.py"],
            "main_head": "abc123",
            "message": "Resolve",
            "task_id": "task-456"
        }

        with patch.object(handler, '_inject_instructions', new_callable=AsyncMock) as mock_inject, \
             patch.object(handler, 'attempt_automatic_resolution', new_callable=AsyncMock) as mock_auto:

            mock_inject.return_value = InstructionInjectionResult(
                success=False,
                message="No process found",
                method="none"
            )
            mock_auto.return_value = ConflictResolutionResult(
                success=False,
                message="Conflicts too complex",
                resolved_files=[],
                remaining_conflicts=["file1.py"]
            )

            result = await handler.handle_merge_conflict("merge_conflict", event_data)

        # Should return failure
        assert result.success is False
        assert result.method == "failed"
        assert "Injection failed" in result.message
        assert "automatic resolution also failed" in result.message

    def test_generate_resolution_instructions(self):
        """Test generating resolution instructions."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        ctx = ConflictResolutionContext(
            issue_id="issue-123",
            branch="feat/test",
            conflicting_files=["src/file1.py", "src/file2.py"],
            main_head="abc123",
            message="Test message"
        )

        instructions = handler._generate_resolution_instructions(ctx)

        # Should contain key elements
        assert "feat/test" in instructions
        assert "src/file1.py" in instructions
        assert "src/file2.py" in instructions
        assert "git fetch" in instructions
        assert "git rebase" in instructions
        assert "git push --force-with-lease" in instructions
        assert "Test message" in instructions

    @pytest.mark.asyncio
    async def test_attempt_automatic_resolution_no_context(self):
        """Test automatic resolution with no context."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        result = await handler.attempt_automatic_resolution()

        assert result.success is False
        assert "No conflict context" in result.message

    def test_clear_context(self):
        """Test clearing the current context."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        handler._current_context = ConflictResolutionContext(
            issue_id="issue-123",
            branch="feat/test",
            conflicting_files=[],
            main_head="abc123",
            message=""
        )

        handler.clear_context()

        assert handler.get_current_context() is None

    @pytest.mark.asyncio
    async def test_report_resolution_complete_no_mcp_client(self):
        """Test reporting completion without MCP client."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        result = await handler.report_resolution_complete(
            task_id="task-123",
            success=True,
            message="Done"
        )

        assert result is False  # No MCP client available

    @pytest.mark.asyncio
    async def test_report_resolution_complete_with_mcp_client(self):
        """Test reporting completion with MCP client."""
        mock_mcp = AsyncMock()
        mock_mcp.report_progress = AsyncMock()

        handler = ConflictResolutionHandler(
            workspace_path="/workspace",
            mcp_client=mock_mcp
        )

        result = await handler.report_resolution_complete(
            task_id="task-123",
            success=True,
            message="Conflicts resolved"
        )

        assert result is True
        mock_mcp.report_progress.assert_called_once_with(
            task_id="task-123",
            status="in_progress",
            message="Conflicts resolved"
        )

    @pytest.mark.asyncio
    async def test_report_resolution_blocked_status(self):
        """Test reporting blocked status when resolution fails."""
        mock_mcp = AsyncMock()
        mock_mcp.report_progress = AsyncMock()

        handler = ConflictResolutionHandler(
            workspace_path="/workspace",
            mcp_client=mock_mcp
        )

        result = await handler.report_resolution_complete(
            task_id="task-123",
            success=False,
            message="Manual intervention required"
        )

        assert result is True
        mock_mcp.report_progress.assert_called_once_with(
            task_id="task-123",
            status="blocked",
            message="Manual intervention required"
        )


class TestInjectInstructions:
    """Tests for _inject_instructions method."""

    @pytest.mark.asyncio
    async def test_inject_no_task_id(self):
        """Test injection fails without task_id."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        result = await handler._inject_instructions(None, "instructions")

        assert result.success is False
        assert "No task_id" in result.message
        assert result.method == "none"

    @pytest.mark.asyncio
    async def test_inject_no_spawner(self):
        """Test injection fails when spawner not available."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=None):
            result = await handler._inject_instructions("task-123", "instructions")

        assert result.success is False
        assert "No ClaudeCodeSpawner available" in result.message
        assert result.method == "none"

    @pytest.mark.asyncio
    async def test_inject_no_process_for_task(self):
        """Test injection fails when no process for task."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        mock_spawner = MagicMock()
        mock_spawner._processes = {}  # No processes

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=mock_spawner):
            result = await handler._inject_instructions("task-123", "instructions")

        assert result.success is False
        assert "No process found" in result.message
        assert result.method == "none"

    @pytest.mark.asyncio
    async def test_inject_process_no_stdin(self):
        """Test injection fails when process has no stdin."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        mock_process = MagicMock()
        mock_process.stdin = None

        mock_spawner = MagicMock()
        mock_spawner._processes = {"task-123": mock_process}

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=mock_spawner):
            result = await handler._inject_instructions("task-123", "instructions")

        assert result.success is False
        assert "has no stdin" in result.message
        assert result.method == "none"

    @pytest.mark.asyncio
    async def test_inject_success(self):
        """Test successful instruction injection."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        mock_stdin = AsyncMock()
        mock_stdin.write = Mock()
        mock_stdin.drain = AsyncMock()

        mock_process = MagicMock()
        mock_process.stdin = mock_stdin

        mock_spawner = MagicMock()
        mock_spawner._processes = {"task-123": mock_process}

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=mock_spawner):
            result = await handler._inject_instructions("task-123", "test instructions")

        assert result.success is True
        assert result.method == "stdin"
        assert "task-123" in result.message

        # Verify write was called with encoded instructions
        mock_stdin.write.assert_called_once()
        written_data = mock_stdin.write.call_args[0][0]
        assert b"URGENT: Merge Conflict Detected" in written_data
        assert b"test instructions" in written_data

        # Verify drain was called
        mock_stdin.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_write_error(self):
        """Test injection handles write errors."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        mock_stdin = AsyncMock()
        mock_stdin.write = Mock(side_effect=BrokenPipeError("Pipe closed"))
        mock_stdin.drain = AsyncMock()

        mock_process = MagicMock()
        mock_process.stdin = mock_stdin

        mock_spawner = MagicMock()
        mock_spawner._processes = {"task-123": mock_process}

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=mock_spawner):
            result = await handler._inject_instructions("task-123", "instructions")

        assert result.success is False
        assert "Pipe closed" in result.message
        assert result.method == "none"

    @pytest.mark.asyncio
    async def test_inject_drain_error(self):
        """Test injection handles drain errors."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        mock_stdin = AsyncMock()
        mock_stdin.write = Mock()
        mock_stdin.drain = AsyncMock(side_effect=ConnectionResetError("Connection reset"))

        mock_process = MagicMock()
        mock_process.stdin = mock_stdin

        mock_spawner = MagicMock()
        mock_spawner._processes = {"task-123": mock_process}

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=mock_spawner):
            result = await handler._inject_instructions("task-123", "instructions")

        assert result.success is False
        assert "Connection reset" in result.message
        assert result.method == "none"


class TestGlobalHandlerFunctions:
    """Tests for global handler management functions."""

    def test_get_handler_returns_none_initially(self):
        """Test that get_conflict_handler returns None initially."""
        # Reset global state
        set_conflict_handler(None)

        handler = get_conflict_handler()
        assert handler is None

    def test_set_and_get_handler(self):
        """Test setting and getting global handler."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        set_conflict_handler(handler)

        retrieved = get_conflict_handler()
        assert retrieved is handler

        # Cleanup
        set_conflict_handler(None)

    def test_initialize_conflict_handler(self):
        """Test initialize_conflict_handler function."""
        handler = initialize_conflict_handler(
            workspace_path="/workspace"
        )

        assert handler is not None
        assert handler.workspace_path == "/workspace"
        assert get_conflict_handler() is handler

        # Cleanup
        set_conflict_handler(None)


class TestIntegrationScenarios:
    """Integration tests for conflict handler scenarios."""

    @pytest.mark.asyncio
    async def test_full_injection_flow(self):
        """Test the full instruction injection flow."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        # Setup mock spawner with a running process
        mock_stdin = AsyncMock()
        mock_stdin.write = Mock()
        mock_stdin.drain = AsyncMock()

        mock_process = MagicMock()
        mock_process.stdin = mock_stdin

        mock_spawner = MagicMock()
        mock_spawner._processes = {"task-integration": mock_process}

        event_data = {
            "issue_id": "issue-integration",
            "branch": "feat/integration-test",
            "conflicting_files": ["src/app.py", "tests/test_app.py"],
            "main_head": "def456",
            "message": "Please resolve these conflicts ASAP",
            "task_id": "task-integration"
        }

        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=mock_spawner):
            result = await handler.handle_merge_conflict("merge_conflict", event_data)

        assert result.success is True
        assert result.method == "stdin"

        # Verify instructions were written
        mock_stdin.write.assert_called_once()
        written_data = mock_stdin.write.call_args[0][0].decode()
        assert "feat/integration-test" in written_data
        assert "src/app.py" in written_data
        assert "tests/test_app.py" in written_data
        assert "git fetch origin main" in written_data
        assert "Please resolve these conflicts ASAP" in written_data

    @pytest.mark.asyncio
    async def test_injection_then_automatic_fallback(self):
        """Test injection failure followed by successful automatic resolution."""
        handler = ConflictResolutionHandler(workspace_path="/workspace")

        event_data = {
            "issue_id": "issue-fallback",
            "branch": "feat/fallback",
            "conflicting_files": ["file.py"],
            "main_head": "abc",
            "message": "Test",
            "task_id": "task-fallback"
        }

        # No spawner available - injection will fail
        with patch('services.claude_code_spawner.get_claude_code_spawner', return_value=None), \
             patch.object(handler, 'attempt_automatic_resolution', new_callable=AsyncMock) as mock_auto:

            mock_auto.return_value = ConflictResolutionResult(
                success=True,
                message="Auto resolved",
                resolved_files=["file.py"],
                remaining_conflicts=[]
            )

            result = await handler.handle_merge_conflict("merge_conflict", event_data)

        assert result.success is True
        assert result.method == "automatic"
        mock_auto.assert_called_once()
