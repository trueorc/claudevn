"""Claude Agent SDK Executor for Compute Infrastructure.

Wraps the claude-agent-sdk `query()` function to execute tasks. Replaces the
previous subprocess-based approach (asyncio.create_subprocess_exec) which caused
OAuth refresh token race conditions when multiple concurrent processes shared
credentials (GitHub #24317).

Each task gets its own `query()` call with isolated `cwd`, `mcp_servers`, and
`ClaudeAgentOptions`. The SDK manages the Claude Code subprocess lifecycle
internally.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from claude_agent_sdk import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result from a Claude Agent SDK task execution.

    Maps SDK response to the event contract expected by the spawner
    (claude_code_started, claude_code_completed, claude_code_failed).
    """

    success: bool
    exit_code: int = 0
    output: str = ""
    duration_ms: int = 0
    session_id: str = ""
    cost_usd: Optional[float] = None
    error: Optional[str] = None
    tool_calls: List[str] = field(default_factory=list)


def build_mcp_servers(
    mcp_script_path: Path,
    server_url: str,
    compute_id: str,
    api_key: str,
) -> Dict[str, Any]:
    """Build MCP server configuration for the SDK.

    Args:
        mcp_script_path: Absolute path to the MCP stdio server script
        server_url: Serving component URL
        compute_id: Compute instance ID
        api_key: Per-task API key for authentication

    Returns:
        Dict suitable for ClaudeAgentOptions.mcp_servers
    """
    return {
        "claudevn": {
            "type": "stdio",
            "command": "python",
            "args": [
                str(mcp_script_path),
                "--serving-url", server_url,
            ],
            "env": {
                "CLAUDEVN_COMPUTE_ID": compute_id,
                "CLAUDEVN_API_KEY": api_key,
            },
        }
    }


async def execute_task(
    prompt: str,
    cwd: Path,
    mcp_servers: Dict[str, Any],
    env_vars: Optional[Dict[str, str]] = None,
    allowed_tools: Optional[List[str]] = None,
    max_turns: Optional[int] = None,
) -> ExecutionResult:
    """Execute a task using the Claude Agent SDK query() function.

    Each call creates an independent session with its own cwd, MCP servers,
    and environment. The SDK manages the Claude Code subprocess internally,
    avoiding the OAuth token race conditions of direct subprocess spawning.

    Args:
        prompt: Task prompt (e.g. "Read CLAUDE.md and complete the task.")
        cwd: Working directory for the agent
        mcp_servers: MCP server configuration dict
        env_vars: Additional environment variables for the CLI subprocess
        allowed_tools: List of allowed tool names (None = all tools)
        max_turns: Maximum conversation turns (None = unlimited)

    Returns:
        ExecutionResult with output, status, and metadata
    """
    options = ClaudeAgentOptions(
        cwd=str(cwd),
        mcp_servers=mcp_servers,
        permission_mode="bypassPermissions",
        setting_sources=["project"],
        env=env_vars or {},
        max_turns=max_turns,
        allowed_tools=allowed_tools or [],
    )

    output_parts: List[str] = []
    tool_calls: List[str] = []
    result_message: Optional[ResultMessage] = None

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_parts.append(block.text)
                        # Log output in real-time for visibility
                        if block.text.strip():
                            logger.info(f"[sdk] output: {block.text[:500]}")
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append(block.name)
                        logger.debug(f"[sdk] tool call: {block.name}")

            elif isinstance(message, ResultMessage):
                result_message = message

        if result_message is None:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                error="No ResultMessage received from SDK",
                output="\n".join(output_parts),
                tool_calls=tool_calls,
            )

        full_output = "\n".join(output_parts)
        # Include the final result text if present
        if result_message.result:
            full_output = full_output + "\n" + result_message.result if full_output else result_message.result

        return ExecutionResult(
            success=not result_message.is_error,
            exit_code=0 if not result_message.is_error else 1,
            output=full_output,
            duration_ms=result_message.duration_ms,
            session_id=result_message.session_id,
            cost_usd=result_message.total_cost_usd,
            error=result_message.result if result_message.is_error else None,
            tool_calls=tool_calls,
        )

    except Exception as e:
        logger.error(f"SDK execution failed: {e}")
        return ExecutionResult(
            success=False,
            exit_code=-1,
            output="\n".join(output_parts),
            error=str(e),
            tool_calls=tool_calls,
        )
