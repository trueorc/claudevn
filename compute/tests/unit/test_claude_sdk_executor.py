"""Unit tests for the Claude Agent SDK executor module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from services.claude_sdk_executor import (
    ExecutionResult,
    build_mcp_servers,
    execute_task,
)


class TestExecutionResult:
    """Tests for the ExecutionResult dataclass."""

    def test_default_values(self):
        result = ExecutionResult(success=True)
        assert result.success is True
        assert result.exit_code == 0
        assert result.output == ""
        assert result.duration_ms == 0
        assert result.session_id == ""
        assert result.cost_usd is None
        assert result.error is None
        assert result.tool_calls == []

    def test_failure_result(self):
        result = ExecutionResult(
            success=False,
            exit_code=1,
            error="Something went wrong",
            output="partial output",
        )
        assert result.success is False
        assert result.exit_code == 1
        assert result.error == "Something went wrong"


class TestBuildMcpServers:
    """Tests for build_mcp_servers helper."""

    def test_builds_correct_config(self):
        config = build_mcp_servers(
            mcp_script_path=Path("/app/mcp/stdio_server.py"),
            server_url="http://serving:8002",
            compute_id="compute-001",
            api_key="test-key-123",
        )

        assert "claudevn" in config
        server = config["claudevn"]
        assert server["type"] == "stdio"
        assert server["command"] == "python"
        assert server["args"] == [
            "/app/mcp/stdio_server.py",
            "--serving-url", "http://serving:8002",
        ]
        assert server["env"]["CLAUDEVN_COMPUTE_ID"] == "compute-001"
        assert server["env"]["CLAUDEVN_API_KEY"] == "test-key-123"


class TestExecuteTask:
    """Tests for the execute_task function."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, tmp_path):
        """Test successful SDK execution with text output."""
        text_block = TextBlock(text="Task completed successfully")
        assistant_msg = AssistantMessage(
            content=[text_block],
            model="claude-sonnet-4-5-20250929",
        )
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=5000,
            duration_api_ms=4000,
            is_error=False,
            num_turns=3,
            session_id="session-abc",
            total_cost_usd=0.05,
            result='{"status": "done"}',
        )

        with patch("services.claude_sdk_executor.query") as mock_query:
            async def fake_query(**kwargs):
                yield assistant_msg
                yield result_msg

            mock_query.side_effect = fake_query

            result = await execute_task(
                prompt="Do the thing",
                cwd=tmp_path,
                mcp_servers={},
            )

        assert result.success is True
        assert result.exit_code == 0
        assert "Task completed successfully" in result.output
        assert result.duration_ms == 5000
        assert result.session_id == "session-abc"
        assert result.cost_usd == 0.05
        assert result.error is None

    @pytest.mark.asyncio
    async def test_failed_execution(self, tmp_path):
        """Test SDK execution that returns an error."""
        result_msg = ResultMessage(
            subtype="error",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=True,
            num_turns=1,
            session_id="session-err",
            total_cost_usd=0.01,
            result="Permission denied",
        )

        with patch("services.claude_sdk_executor.query") as mock_query:
            async def fake_query(**kwargs):
                yield result_msg

            mock_query.side_effect = fake_query

            result = await execute_task(
                prompt="Do the thing",
                cwd=tmp_path,
                mcp_servers={},
            )

        assert result.success is False
        assert result.exit_code == 1
        assert result.error == "Permission denied"

    @pytest.mark.asyncio
    async def test_exception_during_execution(self, tmp_path):
        """Test that exceptions are caught and returned as failed results."""
        with patch("services.claude_sdk_executor.query") as mock_query:
            async def fake_query(**kwargs):
                raise RuntimeError("CLI not found")
                yield  # make it a generator

            mock_query.side_effect = fake_query

            result = await execute_task(
                prompt="Do the thing",
                cwd=tmp_path,
                mcp_servers={},
            )

        assert result.success is False
        assert result.exit_code == -1
        assert "CLI not found" in result.error

    @pytest.mark.asyncio
    async def test_no_result_message(self, tmp_path):
        """Test handling when no ResultMessage is yielded."""
        # Only yield a non-result message type (e.g. just text)
        text_block = TextBlock(text="some output")
        assistant_msg = AssistantMessage(
            content=[text_block],
            model="claude-sonnet-4-5-20250929",
        )

        with patch("services.claude_sdk_executor.query") as mock_query:
            async def fake_query(**kwargs):
                yield assistant_msg

            mock_query.side_effect = fake_query

            result = await execute_task(
                prompt="Do the thing",
                cwd=tmp_path,
                mcp_servers={},
            )

        assert result.success is False
        assert "No ResultMessage" in result.error

    @pytest.mark.asyncio
    async def test_tool_calls_tracked(self, tmp_path):
        """Test that tool use blocks are tracked."""
        tool_block = ToolUseBlock(id="tu_123", name="Bash", input={"command": "ls"})
        assistant_msg = AssistantMessage(
            content=[tool_block],
            model="claude-sonnet-4-5-20250929",
        )
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=2000,
            duration_api_ms=1500,
            is_error=False,
            num_turns=2,
            session_id="session-tools",
            total_cost_usd=0.02,
            result=None,
        )

        with patch("services.claude_sdk_executor.query") as mock_query:
            async def fake_query(**kwargs):
                yield assistant_msg
                yield result_msg

            mock_query.side_effect = fake_query

            result = await execute_task(
                prompt="Run a command",
                cwd=tmp_path,
                mcp_servers={},
            )

        assert result.success is True
        assert "Bash" in result.tool_calls

    @pytest.mark.asyncio
    async def test_env_vars_and_options_passed(self, tmp_path):
        """Test that environment variables and options are configured correctly."""
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=50,
            is_error=False,
            num_turns=1,
            session_id="s",
            total_cost_usd=0.0,
            result=None,
        )

        captured_options = {}

        with patch("services.claude_sdk_executor.query") as mock_query, \
             patch("services.claude_sdk_executor.ClaudeAgentOptions") as MockOptions:

            mock_options_instance = MockOptions.return_value

            async def fake_query(**kwargs):
                captured_options.update(kwargs)
                yield result_msg

            mock_query.side_effect = fake_query

            await execute_task(
                prompt="test",
                cwd=tmp_path,
                mcp_servers={"claudevn": {"type": "stdio"}},
                env_vars={"MY_VAR": "my_value"},
            )

        # Verify ClaudeAgentOptions was created with correct params
        MockOptions.assert_called_once()
        call_kwargs = MockOptions.call_args
        assert call_kwargs.kwargs["cwd"] == str(tmp_path)
        assert call_kwargs.kwargs["env"] == {"MY_VAR": "my_value"}
        assert call_kwargs.kwargs["permission_mode"] == "bypassPermissions"
        assert call_kwargs.kwargs["setting_sources"] == ["project"]

    @pytest.mark.asyncio
    async def test_result_text_appended(self, tmp_path):
        """Test that ResultMessage.result is appended to output."""
        text_block = TextBlock(text="thinking...")
        assistant_msg = AssistantMessage(
            content=[text_block],
            model="claude-sonnet-4-5-20250929",
        )
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=50,
            is_error=False,
            num_turns=1,
            session_id="s",
            total_cost_usd=0.0,
            result="Final answer here",
        )

        with patch("services.claude_sdk_executor.query") as mock_query:
            async def fake_query(**kwargs):
                yield assistant_msg
                yield result_msg

            mock_query.side_effect = fake_query

            result = await execute_task(
                prompt="test",
                cwd=tmp_path,
                mcp_servers={},
            )

        assert "thinking..." in result.output
        assert "Final answer here" in result.output
