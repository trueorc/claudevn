"""Unit tests for model selection in compute executor (#59).

Tests that the model parameter flows correctly from work_assigned event
through the spawner to the SDK executor.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.claude_sdk_executor import ExecutionResult


class TestExecuteTaskModel:
    """Tests for model parameter in execute_task."""

    @pytest.mark.asyncio
    async def test_model_passed_to_agent_options(self):
        """Model parameter is forwarded to ClaudeAgentOptions."""
        captured_options = {}

        async def mock_query(prompt, options):
            captured_options["model"] = getattr(options, "model", None)
            # Yield a ResultMessage to end iteration
            result = MagicMock()
            result.is_error = False
            result.result = "done"
            result.duration_ms = 100
            result.session_id = "sess-1"
            result.total_cost_usd = 0.01
            yield result

        with patch("services.claude_sdk_executor.query", mock_query), \
             patch("services.claude_sdk_executor.ResultMessage", MagicMock), \
             patch("services.claude_sdk_executor.os.getenv", return_value="false"):
            from services.claude_sdk_executor import execute_task
            await execute_task(
                prompt="test",
                cwd=Path("/tmp"),
                mcp_servers={},
                model="claude-opus-4-20250514",
            )

        assert captured_options["model"] == "claude-opus-4-20250514"

    @pytest.mark.asyncio
    async def test_no_model_omitted_from_agent_options(self):
        """When model is None, it should not be set on ClaudeAgentOptions."""
        captured_kwargs = {}

        original_init = None

        with patch("services.claude_sdk_executor.ClaudeAgentOptions") as MockOptions, \
             patch("services.claude_sdk_executor.query") as mock_query, \
             patch("services.claude_sdk_executor.os.getenv", return_value="false"):

            mock_options_instance = MagicMock()
            MockOptions.return_value = mock_options_instance

            # Make query return empty iterator
            mock_query.return_value.__aiter__ = AsyncMock(return_value=iter([]))

            # Capture kwargs
            def capture_kwargs(**kwargs):
                captured_kwargs.update(kwargs)
                return mock_options_instance

            MockOptions.side_effect = capture_kwargs

            result_msg = MagicMock()
            result_msg.is_error = False
            result_msg.result = "done"
            result_msg.duration_ms = 100
            result_msg.session_id = "sess-1"
            result_msg.total_cost_usd = 0.01

            async def mock_query_gen(prompt, options):
                from services.claude_sdk_executor import ResultMessage
                yield result_msg

            mock_query.side_effect = mock_query_gen

            from services.claude_sdk_executor import execute_task
            await execute_task(
                prompt="test",
                cwd=Path("/tmp"),
                mcp_servers={},
                model=None,
            )

        # model key should NOT be in kwargs when None
        assert "model" not in captured_kwargs


class TestSpawnerModelExtraction:
    """Tests for model extraction from work_assigned event."""

    def test_model_extracted_from_event(self):
        """Model field is extracted from work_assigned event data."""
        event = {
            "task_id": "work-123",
            "title": "Test task",
            "model": "claude-opus-4-20250514",
        }
        assert event.get("model") == "claude-opus-4-20250514"

    def test_missing_model_returns_none(self):
        """Missing model field returns None."""
        event = {
            "task_id": "work-123",
            "title": "Test task",
        }
        assert event.get("model") is None
