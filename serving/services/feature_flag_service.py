"""Feature flag service with Redis persistence."""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.feature_flag import FeatureFlag, FlagCategory

logger = logging.getLogger(__name__)

# Default flags shipped with the system
DEFAULT_FLAGS = [
    FeatureFlag(
        name="control-center",
        description="Enable the new control center dashboard layout",
        enabled=False,
        category=FlagCategory.UI,
    ),
]


class FeatureFlagService:
    """Manages feature flags with in-memory cache and Redis persistence."""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._flags: Dict[str, FeatureFlag] = {}

    def _redis_key(self, name: str) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}feature_flag:{name}"

    def _index_key(self) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}feature_flag_index"

    async def initialize(self) -> None:
        """Load flags from Redis, then seed any missing defaults."""
        await self._load_from_redis()

        # Seed default flags that don't exist yet
        for default in DEFAULT_FLAGS:
            if default.name not in self._flags:
                self._flags[default.name] = default
                await self._save_flag_to_redis(default)

        await self._save_index_to_redis()
        logger.info(f"Feature flag service initialized with {len(self._flags)} flag(s)")

    async def list_flags(self) -> List[FeatureFlag]:
        """List all feature flags."""
        return list(self._flags.values())

    async def get_flag(self, name: str) -> Optional[FeatureFlag]:
        """Get a single feature flag by name."""
        return self._flags.get(name)

    async def is_enabled(self, name: str) -> bool:
        """Check if a flag is enabled. Returns False for unknown flags."""
        flag = self._flags.get(name)
        return flag.enabled if flag else False

    async def create_flag(
        self,
        name: str,
        description: str = "",
        enabled: bool = False,
        category: FlagCategory = FlagCategory.EXPERIMENTAL,
    ) -> FeatureFlag:
        """Create a new feature flag.

        Raises:
            ValueError: If flag name already exists
        """
        if name in self._flags:
            raise ValueError(f"Feature flag '{name}' already exists")

        flag = FeatureFlag(
            name=name,
            description=description,
            enabled=enabled,
            category=category,
        )
        self._flags[name] = flag
        await self._save_flag_to_redis(flag)
        await self._save_index_to_redis()
        logger.info(f"Created feature flag '{name}' (enabled={enabled})")
        return flag

    async def toggle_flag(self, name: str, enabled: bool) -> Optional[FeatureFlag]:
        """Toggle a feature flag on/off.

        Returns:
            Updated flag or None if not found
        """
        flag = self._flags.get(name)
        if not flag:
            return None

        flag.enabled = enabled
        flag.updated_at = datetime.now(timezone.utc)
        await self._save_flag_to_redis(flag)
        logger.info(f"Toggled feature flag '{name}' -> enabled={enabled}")
        return flag

    async def delete_flag(self, name: str) -> bool:
        """Delete a feature flag.

        Returns:
            True if deleted, False if not found
        """
        if name not in self._flags:
            return False

        del self._flags[name]
        await self._delete_flag_from_redis(name)
        await self._save_index_to_redis()
        logger.info(f"Deleted feature flag '{name}'")
        return True

    # =========================================================================
    # Redis persistence
    # =========================================================================

    async def _save_flag_to_redis(self, flag: FeatureFlag) -> None:
        if not self._redis:
            return
        try:
            key = self._redis_key(flag.name)
            data = flag.model_dump_json()
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Failed to save feature flag to Redis: {e}")

    async def _delete_flag_from_redis(self, name: str) -> None:
        if not self._redis:
            return
        try:
            key = self._redis_key(name)
            await self._redis._redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete feature flag from Redis: {e}")

    async def _save_index_to_redis(self) -> None:
        if not self._redis:
            return
        try:
            key = self._index_key()
            names = list(self._flags.keys())
            await self._redis._redis.set(key, json.dumps(names))
        except Exception as e:
            logger.error(f"Failed to save feature flag index to Redis: {e}")

    async def _load_from_redis(self) -> None:
        if not self._redis:
            return
        try:
            index_key = self._index_key()
            index_data = await self._redis._redis.get(index_key)
            if not index_data:
                return

            raw = index_data.decode() if isinstance(index_data, bytes) else index_data
            names = json.loads(raw)

            for name in names:
                flag_key = self._redis_key(name)
                flag_data = await self._redis._redis.get(flag_key)
                if flag_data:
                    raw = flag_data.decode() if isinstance(flag_data, bytes) else flag_data
                    flag = FeatureFlag.model_validate_json(raw)
                    self._flags[flag.name] = flag

            logger.info(f"Loaded {len(self._flags)} feature flag(s) from Redis")
        except Exception as e:
            logger.warning(f"Failed to load feature flags from Redis: {e}")


# Module-level singleton
_feature_flag_service: Optional[FeatureFlagService] = None


def get_feature_flag_service() -> Optional[FeatureFlagService]:
    """Get the global feature flag service instance."""
    return _feature_flag_service


def set_feature_flag_service(service: Optional[FeatureFlagService]) -> None:
    """Set the global feature flag service instance."""
    global _feature_flag_service
    _feature_flag_service = service
