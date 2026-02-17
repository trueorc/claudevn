"""Release Service for managing releases (versioned milestones).

Releases allow issues to be grouped by version or milestone for planning purposes.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.work_map import (
    Release, ReleaseStatus, ReleaseCreateRequest, ReleaseUpdateRequest, ReleaseListResponse
)

logger = logging.getLogger(__name__)


class ReleaseService:
    """Service for managing releases.

    Provides:
    - Release CRUD operations
    - Release listing with filtering
    """

    def __init__(self, redis_client=None):
        """Initialize release service.

        Args:
            redis_client: Optional Redis client for persistence
        """
        self._redis = redis_client
        self._releases: Dict[str, Release] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service, loading data from Redis if available."""
        if self._initialized:
            return

        await self._load_releases_from_redis()
        self._initialized = True
        logger.info("Release service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}workmap:{key}"

    # ============ Redis Persistence ============

    async def _load_releases_from_redis(self) -> None:
        """Load releases from Redis on initialization."""
        if not self._redis:
            return

        try:
            cursor = 0
            while True:
                cursor, keys = await self._redis._redis.scan(
                    cursor,
                    match=self._key("release:data:*"),
                    count=100
                )
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    try:
                        data = await self._redis._redis.hgetall(key)
                        if data:
                            release_data = {
                                (k.decode() if isinstance(k, bytes) else k):
                                (v.decode() if isinstance(v, bytes) else v)
                                for k, v in data.items()
                            }
                            # Parse target_date timestamp
                            target_date_str = release_data.get('target_date', '')
                            target_date = None
                            if target_date_str:
                                target_date = datetime.fromisoformat(target_date_str)

                            release = Release(
                                release_id=release_data.get('release_id', ''),
                                name=release_data.get('name', ''),
                                description=release_data.get('description') or None,
                                target_date=target_date,
                                status=ReleaseStatus(release_data.get('status', 'planned')),
                                created_at=datetime.fromisoformat(
                                    release_data.get('created_at', datetime.now(timezone.utc).isoformat())
                                ),
                                updated_at=datetime.fromisoformat(
                                    release_data.get('updated_at', datetime.now(timezone.utc).isoformat())
                                )
                            )
                            self._releases[release.release_id] = release
                    except Exception as e:
                        logger.error(f"Error loading release from {key_str}: {e}")

                if cursor == 0:
                    break

            logger.info(f"Loaded {len(self._releases)} releases from Redis")
        except Exception as e:
            logger.error(f"Error loading releases from Redis: {e}")

    async def _save_release_to_redis(self, release: Release) -> None:
        """Save release to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"release:data:{release.release_id}")
            mapping = {
                'release_id': release.release_id,
                'name': release.name,
                'description': release.description or '',
                'target_date': release.target_date.isoformat() if release.target_date else '',
                'status': release.status.value,
                'created_at': release.created_at.isoformat(),
                'updated_at': release.updated_at.isoformat()
            }
            await self._redis._redis.hset(key, mapping=mapping)

            # Update status index
            await self._redis._redis.sadd(
                self._key(f"release:status:{release.status.value}"),
                release.release_id
            )
        except Exception as e:
            logger.error(f"Error saving release to Redis: {e}")

    async def _delete_release_from_redis(self, release_id: str) -> None:
        """Delete release from Redis."""
        if not self._redis:
            return

        try:
            release = self._releases.get(release_id)
            if release:
                await self._redis._redis.srem(
                    self._key(f"release:status:{release.status.value}"),
                    release_id
                )
            await self._redis._redis.delete(self._key(f"release:data:{release_id}"))
        except Exception as e:
            logger.error(f"Error deleting release from Redis: {e}")

    # ============ Release CRUD Operations ============

    async def create_release(self, request: ReleaseCreateRequest) -> Release:
        """Create a new release.

        Args:
            request: Release creation request

        Returns:
            Created release
        """
        release_id = f"release_{uuid.uuid4().hex[:12]}"

        release = Release(
            release_id=release_id,
            name=request.name,
            description=request.description,
            target_date=request.target_date,
            status=request.status
        )

        self._releases[release_id] = release
        await self._save_release_to_redis(release)

        logger.info(f"Created release {release_id}: {release.name}")
        return release

    async def get_release(self, release_id: str) -> Optional[Release]:
        """Get a release by ID.

        Args:
            release_id: Release ID to retrieve

        Returns:
            Release if found
        """
        return self._releases.get(release_id)

    async def update_release(
        self,
        release_id: str,
        request: ReleaseUpdateRequest
    ) -> Optional[Release]:
        """Update a release.

        Args:
            release_id: Release ID to update
            request: Update request

        Returns:
            Updated release or None if not found
        """
        release = self._releases.get(release_id)
        if not release:
            return None

        old_status = release.status

        if request.name is not None:
            release.name = request.name
        if request.description is not None:
            release.description = request.description
        if request.target_date is not None:
            release.target_date = request.target_date
        if request.status is not None:
            release.status = request.status

        release.updated_at = datetime.now(timezone.utc)

        # Update Redis indexes if status changed
        if self._redis and request.status is not None and old_status != release.status:
            await self._redis._redis.srem(
                self._key(f"release:status:{old_status.value}"),
                release_id
            )

        await self._save_release_to_redis(release)

        logger.info(f"Updated release {release_id}")
        return release

    async def delete_release(self, release_id: str) -> bool:
        """Delete a release.

        Args:
            release_id: Release ID to delete

        Returns:
            True if deleted, False if not found
        """
        if release_id not in self._releases:
            return False

        await self._delete_release_from_redis(release_id)
        del self._releases[release_id]

        logger.info(f"Deleted release {release_id}")
        return True

    async def list_releases(
        self,
        status: Optional[ReleaseStatus] = None,
        limit: int = 100
    ) -> ReleaseListResponse:
        """List releases with optional filtering.

        Args:
            status: Filter by release status
            limit: Maximum number of releases to return

        Returns:
            ReleaseListResponse with releases and stats
        """
        items = list(self._releases.values())

        if status:
            items = [r for r in items if r.status == status]

        # Sort by target_date (None values last), then by created_at
        def sort_key(r: Release):
            target_ts = r.target_date.timestamp() if r.target_date else float('inf')
            return (target_ts, r.created_at.timestamp())

        items.sort(key=sort_key)
        items = items[:limit]

        # Calculate stats
        all_releases = list(self._releases.values())
        by_status = {}
        for r in all_releases:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1

        return ReleaseListResponse(
            items=items,
            total=len(all_releases),
            by_status=by_status
        )

    # ============ Direct Access ============

    @property
    def releases(self) -> Dict[str, Release]:
        """Direct access to releases dictionary."""
        return self._releases


# Global instance
_release_service: Optional[ReleaseService] = None


def get_release_service() -> ReleaseService:
    """Get the global release service instance."""
    if _release_service is None:
        raise RuntimeError("Release service not initialized")
    return _release_service


def set_release_service(service: ReleaseService) -> None:
    """Set the global release service instance."""
    global _release_service
    _release_service = service
