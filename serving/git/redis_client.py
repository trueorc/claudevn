"""Redis client for Git infrastructure.

Provides async Redis connection management and convenience methods
for the PR queue and branch status management.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from config import get_config, RedisConfig

logger = logging.getLogger(__name__)

# Global Redis connection pool
_redis_pool: Optional[Redis] = None


async def get_redis() -> Redis:
    """Get the global Redis connection.

    Returns:
        Redis async client instance
    """
    global _redis_pool

    if _redis_pool is None:
        config = get_config().redis
        _redis_pool = redis.from_url(
            config.url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info(f"Connected to Redis at {config.host}:{config.port}")

    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool

    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis connection closed")


# Global RedisClient instance for health checks
_redis_client: Optional["RedisClient"] = None


def get_redis_client() -> Optional["RedisClient"]:
    """Get the global RedisClient instance.

    Returns:
        RedisClient instance or None if not initialized
    """
    return _redis_client


def set_redis_client(client: Optional["RedisClient"]) -> None:
    """Set the global RedisClient instance.

    Args:
        client: RedisClient instance to set globally
    """
    global _redis_client
    _redis_client = client


class RedisClient:
    """Convenience wrapper for Redis operations with key prefixing."""

    def __init__(self, redis: Redis, prefix: Optional[str] = None):
        """Initialize Redis client.

        Args:
            redis: Redis connection
            prefix: Key prefix (defaults to config value)
        """
        self._redis = redis
        self._prefix = prefix or get_config().redis.key_prefix

    def _key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self._prefix}{key}"

    # ==========================================================================
    # Health Check Operations
    # ==========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health using PING command.

        Returns:
            Dict with health status:
                - connected: bool indicating connection status
                - response_time_ms: float response time in milliseconds (if connected)
                - error: str error message (if not connected)
        """
        import time

        start_time = time.perf_counter()
        try:
            result = await self._redis.ping()
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return {
                "connected": result is True,
                "response_time_ms": round(elapsed_ms, 2)
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(f"Redis health check failed: {e}")
            return {
                "connected": False,
                "response_time_ms": round(elapsed_ms, 2),
                "error": str(e)
            }

    # ==========================================================================
    # Branch Status Operations
    # ==========================================================================

    async def set_branch_status(
        self,
        project: str,
        branch: str,
        status: str,
        compute_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Set or update branch metadata.

        Args:
            project: Project/repo name
            branch: Branch name
            status: Branch status (pending, in_review, approved, rejected, merged, conflict)
            compute_id: Optional compute instance ID
            task_id: Optional task ID
            **extra_fields: Additional fields to store
        """
        key = self._key(f"branch:{project}:{branch}")
        now = datetime.now(timezone.utc).isoformat()

        data = {
            "status": status,
            "updated_at": now,
            **extra_fields
        }

        if compute_id:
            data["compute_id"] = compute_id
        if task_id:
            data["task_id"] = task_id

        # Use HSET for atomic update
        await self._redis.hset(key, mapping=data)

        # Set created_at only if not exists
        await self._redis.hsetnx(key, "created_at", now)

        logger.debug(f"Branch status updated: {project}/{branch} -> {status}")

    async def get_branch_status(self, project: str, branch: str) -> Optional[Dict[str, Any]]:
        """Get branch metadata.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            Branch metadata dict or None if not found
        """
        key = self._key(f"branch:{project}:{branch}")
        data = await self._redis.hgetall(key)
        return data if data else None

    async def delete_branch_status(self, project: str, branch: str) -> bool:
        """Delete branch metadata.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            True if deleted, False if not found
        """
        key = self._key(f"branch:{project}:{branch}")
        result = await self._redis.delete(key)
        return result > 0

    async def list_branches(
        self,
        project: str,
        status: Optional[str] = None,
        compute_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List branches with optional filtering.

        Args:
            project: Project/repo name
            status: Optional status filter
            compute_id: Optional compute ID filter

        Returns:
            List of branch metadata dicts
        """
        pattern = self._key(f"branch:{project}:*")
        branches = []

        async for key in self._redis.scan_iter(pattern):
            data = await self._redis.hgetall(key)
            if data:
                # Extract branch name from key
                branch_name = key.split(":")[-1]
                data["branch"] = branch_name

                # Apply filters
                if status and data.get("status") != status:
                    continue
                if compute_id and data.get("compute_id") != compute_id:
                    continue

                branches.append(data)

        return branches

    # ==========================================================================
    # PR Queue Operations
    # ==========================================================================

    async def add_to_pr_queue(self, project: str, branch: str, timestamp: Optional[float] = None) -> int:
        """Add branch to PR queue.

        Args:
            project: Project/repo name
            branch: Branch name
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Queue position (1-indexed)
        """
        key = self._key(f"pr_queue:{project}")
        score = timestamp or datetime.now(timezone.utc).timestamp()

        await self._redis.zadd(key, {branch: score})

        # Get position in queue
        rank = await self._redis.zrank(key, branch)
        return (rank or 0) + 1

    async def remove_from_pr_queue(self, project: str, branch: str) -> bool:
        """Remove branch from PR queue.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            True if removed, False if not found
        """
        key = self._key(f"pr_queue:{project}")
        result = await self._redis.zrem(key, branch)
        return result > 0

    async def get_pr_queue(self, project: str, limit: int = 100) -> List[str]:
        """Get PR queue (oldest first).

        Args:
            project: Project/repo name
            limit: Maximum number of entries

        Returns:
            List of branch names in queue order
        """
        key = self._key(f"pr_queue:{project}")
        return await self._redis.zrange(key, 0, limit - 1)

    async def get_pr_queue_position(self, project: str, branch: str) -> Optional[int]:
        """Get branch position in PR queue.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            Position (1-indexed) or None if not in queue
        """
        key = self._key(f"pr_queue:{project}")
        rank = await self._redis.zrank(key, branch)
        return (rank + 1) if rank is not None else None

    # ==========================================================================
    # Merge Queue Operations
    # ==========================================================================

    async def add_to_merge_queue(self, project: str, branch: str) -> int:
        """Add branch to merge queue.

        Args:
            project: Project/repo name
            branch: Branch name

        Returns:
            Queue length after adding
        """
        key = self._key(f"merge_queue:{project}")
        return await self._redis.rpush(key, branch)

    async def pop_merge_queue(self, project: str) -> Optional[str]:
        """Pop next branch from merge queue.

        Args:
            project: Project/repo name

        Returns:
            Branch name or None if empty
        """
        key = self._key(f"merge_queue:{project}")
        return await self._redis.lpop(key)

    async def get_merge_queue(self, project: str) -> List[str]:
        """Get merge queue contents.

        Args:
            project: Project/repo name

        Returns:
            List of branch names in order
        """
        key = self._key(f"merge_queue:{project}")
        return await self._redis.lrange(key, 0, -1)

    async def remove_from_merge_queue(self, project: str, branch: str) -> int:
        """Remove a branch from the merge queue.

        Args:
            project: Project/repo name
            branch: Branch name to remove

        Returns:
            Number of elements removed
        """
        key = self._key(f"merge_queue:{project}")
        return await self._redis.lrem(key, 0, branch)

    # ==========================================================================
    # Generic Set Operations
    # ==========================================================================

    async def sadd(self, key: str, *members: str) -> int:
        """Add members to a set.

        Args:
            key: Set key (will be prefixed)
            *members: Members to add

        Returns:
            Number of members added
        """
        return await self._redis.sadd(self._key(key), *members)

    async def srem(self, key: str, *members: str) -> int:
        """Remove members from a set.

        Args:
            key: Set key (will be prefixed)
            *members: Members to remove

        Returns:
            Number of members removed
        """
        return await self._redis.srem(self._key(key), *members)

    async def smembers(self, key: str) -> set:
        """Get all members of a set.

        Args:
            key: Set key (will be prefixed)

        Returns:
            Set of members
        """
        return await self._redis.smembers(self._key(key))

    # ==========================================================================
    # Generic Hash Operations
    # ==========================================================================

    async def hset(self, key: str, *args, **kwargs) -> int:
        """Set hash field(s).

        Args:
            key: Hash key (will be prefixed)
            *args: Field-value pairs (field, value) or positional args
            **kwargs: Passed through to redis hset (e.g., mapping=...)

        Returns:
            Number of fields added
        """
        return await self._redis.hset(self._key(key), *args, **kwargs)

    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields and values of a hash.

        Args:
            key: Hash key (will be prefixed)

        Returns:
            Dict of field-value pairs
        """
        return await self._redis.hgetall(self._key(key))

    # ==========================================================================
    # Generic Key Operations
    # ==========================================================================

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys.

        Args:
            *keys: Keys to delete (will be prefixed)

        Returns:
            Number of keys deleted
        """
        prefixed = [self._key(k) for k in keys]
        return await self._redis.delete(*prefixed)

    # ==========================================================================
    # Compute Branch Tracking
    # ==========================================================================

    async def track_compute_branch(self, compute_id: str, branch: str) -> None:
        """Track that a compute instance owns a branch.

        Args:
            compute_id: Compute instance ID
            branch: Branch name (full, including project)
        """
        key = self._key(f"compute:{compute_id}:branches")
        await self._redis.sadd(key, branch)

    async def untrack_compute_branch(self, compute_id: str, branch: str) -> None:
        """Remove branch from compute tracking.

        Args:
            compute_id: Compute instance ID
            branch: Branch name
        """
        key = self._key(f"compute:{compute_id}:branches")
        await self._redis.srem(key, branch)

    async def get_compute_branches(self, compute_id: str) -> List[str]:
        """Get all branches owned by a compute instance.

        Args:
            compute_id: Compute instance ID

        Returns:
            List of branch names
        """
        key = self._key(f"compute:{compute_id}:branches")
        return list(await self._redis.smembers(key))

    # ==========================================================================
    # Branch Metadata Operations
    # ==========================================================================

    async def set_branch_metadata(self, project: str, branch: str, key: str, value: dict) -> None:
        """Store metadata for a branch.

        Args:
            project: Project/repo name
            branch: Branch name
            key: Metadata key (e.g., 'validation_results')
            value: Metadata value (will be JSON-serialized)
        """
        redis_key = f"{self._prefix}pr:{project}:{branch}:meta:{key}"
        await self._redis.set(redis_key, json.dumps(value))

    async def get_branch_metadata(self, project: str, branch: str, key: str) -> Optional[dict]:
        """Retrieve metadata for a branch.

        Args:
            project: Project/repo name
            branch: Branch name
            key: Metadata key

        Returns:
            Metadata dict or None if not found
        """
        redis_key = f"{self._prefix}pr:{project}:{branch}:meta:{key}"
        data = await self._redis.get(redis_key)
        if data:
            return json.loads(data)
        return None

    # ==========================================================================
    # Merge Lock Operations
    # ==========================================================================

    async def acquire_merge_lock(self, project: str, timeout: int = 120) -> bool:
        """Acquire a distributed lock for merge queue processing.

        Uses SET NX EX for an atomic acquire-or-fail operation.

        Args:
            project: Project/repo name
            timeout: Lock TTL in seconds (default 120)

        Returns:
            True if lock was acquired, False if already held
        """
        key = self._key(f"merge_lock:{project}")
        result = await self._redis.set(key, "1", nx=True, ex=timeout)
        return result is not None

    async def release_merge_lock(self, project: str) -> None:
        """Release the distributed merge lock.

        Args:
            project: Project/repo name
        """
        key = self._key(f"merge_lock:{project}")
        await self._redis.delete(key)

    # ==========================================================================
    # Pub/Sub Operations
    # ==========================================================================

    async def publish_event(self, channel: str, event: Dict[str, Any]) -> int:
        """Publish event to Redis pub/sub.

        Args:
            channel: Channel name (will be prefixed)
            event: Event data

        Returns:
            Number of subscribers that received the message
        """
        full_channel = self._key(channel)
        message = json.dumps(event)
        return await self._redis.publish(full_channel, message)

    async def publish_git_event(
        self,
        project: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> int:
        """Publish Git-related event.

        Args:
            project: Project name
            event_type: Event type (push, status, merged)
            data: Event data

        Returns:
            Number of subscribers
        """
        channel = f"git:{project}:{event_type}"
        event = {
            "type": event_type,
            "project": project,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data
        }
        return await self.publish_event(channel, event)
