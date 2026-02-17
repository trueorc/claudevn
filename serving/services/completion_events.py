"""Completion event registry for event-driven task signaling.

Provides an in-process asyncio.Event registry keyed by task ID. When an MCP
tool receives a result (decomposition, characterization), it calls signal() to
instantly unblock any coroutine awaiting that task's completion.

This replaces the 2-second Redis polling loops in goal_decomposer.py and
characterization_service.py. Since the MCP server and the waiting services
are all in the same process, an in-process Event is sufficient — no Redis
pub/sub needed.

Usage:
    # Caller registers before spawning compute:
    create_event(task_id)

    # MCP tool signals when result is ready:
    signal(task_id)

    # Caller waits with timeout:
    event = get_event(task_id)
    if event:
        await asyncio.wait_for(event.wait(), timeout=300)
    cleanup(task_id)
"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Global registry: task_id -> asyncio.Event
_events: Dict[str, asyncio.Event] = {}


def create_event(task_id: str) -> asyncio.Event:
    """Create and register a completion event for a task.

    Must be called before the task is dispatched to a compute, so that
    signal() calls from MCP tools are never missed.

    Args:
        task_id: Unique task identifier (decomp_id or char_id)

    Returns:
        The asyncio.Event for this task
    """
    event = asyncio.Event()
    _events[task_id] = event
    logger.debug(f"Registered completion event for task {task_id}")
    return event


def get_event(task_id: str) -> Optional[asyncio.Event]:
    """Get the completion event for a task.

    Args:
        task_id: Task identifier

    Returns:
        The asyncio.Event, or None if not registered
    """
    return _events.get(task_id)


def signal(task_id: str) -> None:
    """Signal completion for a task.

    Called by MCP tool handlers when a compute submits results. Instantly
    unblocks any coroutine awaiting this task's completion.

    Args:
        task_id: Task identifier to signal
    """
    event = _events.get(task_id)
    if event:
        event.set()
        logger.debug(f"Signaled completion for task {task_id}")
    else:
        # Event not registered — compute may have submitted after timeout cleanup.
        # This is benign; log at debug level only.
        logger.debug(
            f"No completion event registered for task {task_id} "
            "(may have already timed out)"
        )


def cleanup(task_id: str) -> None:
    """Remove a completion event from the registry.

    Call after waiting (success or timeout) to prevent memory leaks.

    Args:
        task_id: Task identifier to remove
    """
    removed = _events.pop(task_id, None)
    if removed:
        logger.debug(f"Cleaned up completion event for task {task_id}")


def active_count() -> int:
    """Return the number of active (registered) completion events."""
    return len(_events)
