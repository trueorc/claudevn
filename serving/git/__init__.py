"""Git infrastructure for ClaudeVN Serving component.

This module provides Git-based state management including:
- Bare repository management
- SSH key management for compute instances
- SSH server for Git push/pull access
- PR queue management via Redis
- Git hooks for event notification
"""

from .redis_client import get_redis, RedisClient
from .repo_manager import RepoManager
from .ssh_key_manager import SSHKeyManager
from .ssh_server import SSHServer, get_ssh_server, set_ssh_server, start_ssh_server, stop_ssh_server
from .pr_service import PRService

__all__ = [
    "get_redis",
    "RedisClient",
    "RepoManager",
    "SSHKeyManager",
    "SSHServer",
    "get_ssh_server",
    "set_ssh_server",
    "start_ssh_server",
    "stop_ssh_server",
    "PRService",
]
