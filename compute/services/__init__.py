"""Services for compute engine.

v1.0 architecture: Claude Code CLI serves as the execution runtime.
These services support the compute infrastructure.
"""

from .claude_code_spawner import ClaudeCodeSpawner
from .conflict_handler import ConflictResolutionHandler, initialize_conflict_handler
from .sse_event_client import SSEEventClient

__all__ = [
    "ClaudeCodeSpawner",
    "ConflictResolutionHandler",
    "initialize_conflict_handler",
    "SSEEventClient",
]
