"""MCP authentication for compute instances.

Persists compute API keys to Redis for durability across restarts.
Falls back to in-memory-only storage when Redis is unavailable.
Fails closed: rejects all requests when no keys are registered.

Keys are stored per-compute as a set of valid keys. This allows sequential
tasks on the same compute to overlap briefly without 401 errors — a new
task's key registration doesn't invalidate the previous task's key (#828).
"""

import os
import logging
import secrets
from typing import Optional, Tuple

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# Default TTL for API keys: 24 hours
DEFAULT_KEY_TTL = 86400

# Redis client for persistence (optional)
_redis = None

# In-memory cache (always maintained; Redis is source of truth when available)
# Each compute can have multiple valid keys (one per active/recent task)
_compute_api_keys: dict[str, set[str]] = {}  # compute_id -> {api_key, ...}


def set_auth_redis(redis_client) -> None:
    """Set the Redis client for auth key persistence."""
    global _redis
    _redis = redis_client


def get_auth_redis():
    """Get the Redis client used for auth key persistence."""
    return _redis


def _redis_key(compute_id: str) -> str:
    """Build the Redis key for a compute API key set."""
    prefix = getattr(_redis, '_prefix', 'claudevn:') if _redis else 'claudevn:'
    return f"{prefix}compute:apikeys:{compute_id}"


def _legacy_redis_key(compute_id: str) -> str:
    """Build the legacy Redis key (single-key format) for migration."""
    prefix = getattr(_redis, '_prefix', 'claudevn:') if _redis else 'claudevn:'
    return f"{prefix}compute:apikey:{compute_id}"


def _is_auth_bypass_enabled() -> bool:
    """Check if MCP auth bypass is enabled.

    Returns True if MCP_AUTH_BYPASS=true is set, which allows any valid
    Bearer token format to authenticate. Used for integration testing.
    """
    return os.getenv("MCP_AUTH_BYPASS", "").lower() == "true"


async def initialize_from_redis() -> None:
    """Load existing API keys from Redis into the in-memory cache.

    Called during app startup so that keys survive Serving restarts.
    Handles both new set-based format and legacy single-key format.
    """
    if not _redis:
        return

    try:
        prefix = getattr(_redis, '_prefix', 'claudevn:')
        loaded = 0

        # Load new set-based keys
        pattern = f"{prefix}compute:apikeys:*"
        prefix_len = len(f"{prefix}compute:apikeys:")
        cursor = 0
        while True:
            cursor, keys = await _redis._redis.scan(
                cursor, match=pattern, count=100
            )
            for key in keys:
                compute_id = key[prefix_len:]
                members = await _redis._redis.smembers(key)
                if members:
                    _compute_api_keys[compute_id] = set(members)
                    loaded += len(members)
            if cursor == 0:
                break

        # Also load legacy single-key format for migration
        legacy_pattern = f"{prefix}compute:apikey:*"
        legacy_prefix_len = len(f"{prefix}compute:apikey:")
        cursor = 0
        while True:
            cursor, keys = await _redis._redis.scan(
                cursor, match=legacy_pattern, count=100
            )
            for key in keys:
                compute_id = key[legacy_prefix_len:]
                api_key = await _redis._redis.get(key)
                if api_key:
                    if compute_id not in _compute_api_keys:
                        _compute_api_keys[compute_id] = set()
                    _compute_api_keys[compute_id].add(api_key)
                    loaded += 1
            if cursor == 0:
                break

        logger.info(f"Loaded {loaded} compute API key(s) from Redis")
    except Exception as e:
        logger.error(f"Error loading API keys from Redis: {e}")


async def register_compute_key(
    compute_id: str, api_key: str, ttl: int = DEFAULT_KEY_TTL
) -> None:
    """Register an API key for a compute instance.

    Adds the key to the compute's valid key set. Previous keys remain valid
    until explicitly revoked, preventing 401 errors during task transitions.
    """
    if compute_id not in _compute_api_keys:
        _compute_api_keys[compute_id] = set()
    _compute_api_keys[compute_id].add(api_key)

    if _redis:
        try:
            key = _redis_key(compute_id)
            await _redis._redis.sadd(key, api_key)
            await _redis._redis.expire(key, ttl)
        except Exception as e:
            logger.error(f"Error persisting API key to Redis for {compute_id}: {e}")

    logger.info(f"Registered API key for compute {compute_id}")


async def revoke_compute_key(compute_id: str, api_key: Optional[str] = None) -> None:
    """Revoke API key(s) for a compute instance.

    If api_key is provided, revokes only that key. Otherwise revokes all keys.
    """
    if api_key:
        # Revoke specific key
        keys = _compute_api_keys.get(compute_id, set())
        keys.discard(api_key)
        if not keys:
            _compute_api_keys.pop(compute_id, None)

        if _redis:
            try:
                await _redis._redis.srem(_redis_key(compute_id), api_key)
            except Exception as e:
                logger.error(f"Error removing API key from Redis for {compute_id}: {e}")

        logger.info(f"Revoked specific API key for compute {compute_id}")
    else:
        # Revoke all keys
        removed = _compute_api_keys.pop(compute_id, None)

        if _redis:
            try:
                await _redis._redis.delete(_redis_key(compute_id))
            except Exception as e:
                logger.error(f"Error removing API keys from Redis for {compute_id}: {e}")

        if removed:
            logger.info(f"Revoked all API keys for compute {compute_id}")


async def rotate_compute_key(
    compute_id: str, ttl: int = DEFAULT_KEY_TTL
) -> Optional[str]:
    """Rotate the API key for a compute instance.

    Generates a new key and revokes all previous keys.
    Returns the new API key, or None if the compute_id is not registered.
    """
    if compute_id not in _compute_api_keys:
        if _redis:
            try:
                existing = await _redis._redis.scard(_redis_key(compute_id))
                if not existing:
                    return None
            except Exception as e:
                logger.error(f"Error checking Redis during key rotation: {e}")
                return None
        else:
            return None

    # Revoke all old keys, register new one
    await revoke_compute_key(compute_id)
    new_key = generate_api_key()
    await register_compute_key(compute_id, new_key, ttl)
    logger.info(f"Rotated API key for compute {compute_id}")
    return new_key


async def refresh_key_ttl(compute_id: str, ttl: int = DEFAULT_KEY_TTL) -> bool:
    """Refresh the TTL on a compute's API keys (e.g., on heartbeat).

    Returns True if the key exists and TTL was refreshed.
    """
    if not _redis:
        return compute_id in _compute_api_keys

    try:
        key = _redis_key(compute_id)
        result = await _redis._redis.expire(key, ttl)
        return bool(result)
    except Exception as e:
        logger.error(f"Error refreshing key TTL for {compute_id}: {e}")
        return False


async def verify_compute_auth(
    authorization: Optional[str] = Header(None),
    x_compute_id: Optional[str] = Header(None, alias="X-Compute-ID"),
) -> Tuple[str, str]:
    """Verify compute authentication from headers.

    Returns:
        Tuple of (compute_id, api_key)

    Raises:
        HTTPException if authentication fails
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MISSING_AUTH", "message": "Authorization header required"},
        )

    if not x_compute_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "MISSING_COMPUTE_ID",
                "message": "X-Compute-ID header required",
            },
        )

    # Extract bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_AUTH", "message": "Bearer token required"},
        )

    api_key = authorization[7:]  # Remove "Bearer " prefix

    # Allow bypass in testing mode (MCP_AUTH_BYPASS=true)
    if _is_auth_bypass_enabled():
        logger.debug(f"MCP auth bypass enabled, allowing compute {x_compute_id}")
        return x_compute_id, api_key

    # Check in-memory cache first
    valid_keys = _compute_api_keys.get(x_compute_id)

    if valid_keys is None and _redis:
        # Cache miss - check Redis (keys may have been loaded by another process)
        try:
            members = await _redis._redis.smembers(_redis_key(x_compute_id))
            if members:
                valid_keys = set(members)
                _compute_api_keys[x_compute_id] = valid_keys
        except Exception as e:
            logger.error(f"Error checking Redis for compute key: {e}")

    # Fail closed: reject if compute is not registered
    if not valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNKNOWN_COMPUTE",
                "message": f"Compute {x_compute_id} not registered",
            },
        )

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_KEY", "message": "Invalid API key for compute"},
        )

    return x_compute_id, api_key


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"troc_{secrets.token_hex(24)}"
