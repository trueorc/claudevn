"""MCP tools for compute communication."""

import logging

_logger = logging.getLogger(__name__)


async def emit_tool_error(tool_name: str, error_code: str, error_msg: str,
                          compute_id: str = None, project_id: str = None):
    """Emit an MCPToolError event for observability.

    Called from catch blocks in MCP tool handlers to ensure
    every tool error is visible on the event bus, not just logged.
    """
    try:
        from services.events.event_bus import get_event_bus
        from services.events.event_types import MCPToolError
        await get_event_bus().publish(MCPToolError(
            tool_name=tool_name,
            error_code=error_code,
            error_message=error_msg[:200],
            compute_id=compute_id,
            project_id=project_id,
        ))
    except Exception:
        _logger.debug(f"Failed to emit tool error event for {tool_name}")


from . import assignment
from . import progress
from . import review
from . import context
from . import blocker
from . import complete
from . import skill
from . import conflict
from . import issues
from . import requirement
from . import decomposition
from . import characterization
from . import challenge

__all__ = [
    "assignment",
    "progress",
    "review",
    "context",
    "blocker",
    "complete",
    "skill",
    "conflict",
    "issues",
    "requirement",
    "decomposition",
    "characterization",
    "challenge",
]
