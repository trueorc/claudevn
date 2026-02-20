"""Git infrastructure for ClaudeVN Serving component.

This module provides Git-based state management including:
- Bare repository management
- Token-based authentication for compute instances
- Git Smart HTTP backend for push/pull access
- PR queue management via Redis
- Git hooks for event notification
"""

from .redis_client import get_redis, RedisClient
from .repo_manager import RepoManager
from .git_token_service import GitTokenService, get_git_token_service, set_git_token_service
from .http_backend import router as git_http_router
from .pr_service import PRService

__all__ = [
    "get_redis",
    "RedisClient",
    "RepoManager",
    "GitTokenService",
    "get_git_token_service",
    "set_git_token_service",
    "git_http_router",
    "PRService",
]
