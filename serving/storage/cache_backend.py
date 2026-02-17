"""Cache backend for TrueOrc Serving component.

Provides filesystem-based caching with TTL support.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Global cache backend instance
_cache_backend: Optional["FilesystemCache"] = None


def get_cache_backend() -> Optional["FilesystemCache"]:
    """Get the global cache backend instance."""
    return _cache_backend


def set_cache_backend(backend: "FilesystemCache") -> None:
    """Set the global cache backend instance."""
    global _cache_backend
    _cache_backend = backend


class FilesystemCache:
    """Filesystem-based cache with TTL support.

    Stores cached data as JSON files with expiration metadata.
    """

    def __init__(self, cache_path: str, default_ttl: int = 300):
        """Initialize filesystem cache.

        Args:
            cache_path: Path to cache directory
            default_ttl: Default TTL in seconds (default: 5 minutes)
        """
        self._cache_path = Path(cache_path)
        self._default_ttl = default_ttl

        # Ensure cache directory exists
        self._cache_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized filesystem cache at {self._cache_path}")

    def _key_to_filename(self, key: str) -> str:
        """Convert cache key to safe filename.

        Args:
            key: Cache key

        Returns:
            Safe filename for the key
        """
        # Use MD5 hash for consistent, safe filenames
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return f"{key_hash}.json"

    def _get_file_path(self, key: str) -> Path:
        """Get file path for a cache key.

        Args:
            key: Cache key

        Returns:
            Path to cache file
        """
        return self._cache_path / self._key_to_filename(key)

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        file_path = self._get_file_path(key)

        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                cache_entry = json.load(f)

            # Check expiration
            expires_at = datetime.fromisoformat(cache_entry["expires_at"])
            if datetime.utcnow() > expires_at:
                # Expired - delete and return None
                file_path.unlink(missing_ok=True)
                logger.debug(f"Cache expired: {key}")
                return None

            logger.debug(f"Cache hit: {key}")
            return cache_entry["value"]

        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if None)
        """
        file_path = self._get_file_path(key)
        ttl = ttl or self._default_ttl

        cache_entry = {
            "key": key,
            "value": value,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=ttl)).isoformat(),
            "ttl": ttl
        }

        try:
            with open(file_path, "w") as f:
                json.dump(cache_entry, f, indent=2, default=str)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")

    async def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        file_path = self._get_file_path(key)

        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Cache deleted: {key}")
            return True

        return False

    async def clear(self) -> int:
        """Clear all cached entries.

        Returns:
            Number of entries cleared
        """
        count = 0
        for file_path in self._cache_path.glob("*.json"):
            try:
                file_path.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"Failed to delete {file_path}: {e}")

        logger.info(f"Cache cleared: {count} entries")
        return count

    async def cleanup_expired(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of entries removed
        """
        count = 0
        now = datetime.utcnow()

        for file_path in self._cache_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    cache_entry = json.load(f)

                expires_at = datetime.fromisoformat(cache_entry["expires_at"])
                if now > expires_at:
                    file_path.unlink()
                    count += 1

            except Exception as e:
                logger.warning(f"Error checking {file_path}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} expired cache entries")

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        total_entries = 0
        total_size = 0
        expired_entries = 0
        now = datetime.utcnow()

        for file_path in self._cache_path.glob("*.json"):
            total_entries += 1
            total_size += file_path.stat().st_size

            try:
                with open(file_path) as f:
                    cache_entry = json.load(f)

                expires_at = datetime.fromisoformat(cache_entry["expires_at"])
                if now > expires_at:
                    expired_entries += 1
            except Exception:
                pass

        return {
            "total_entries": total_entries,
            "active_entries": total_entries - expired_entries,
            "expired_entries": expired_entries,
            "total_size_bytes": total_size,
            "cache_path": str(self._cache_path),
            "default_ttl": self._default_ttl
        }


# Type alias for backward compatibility
CacheBackend = FilesystemCache
