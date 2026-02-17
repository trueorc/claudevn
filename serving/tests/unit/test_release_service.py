"""Tests for ReleaseService - Release CRUD operations."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from models.work_map import (
    Release, ReleaseStatus, ReleaseCreateRequest, ReleaseUpdateRequest
)
from services.release_service import (
    ReleaseService, get_release_service, set_release_service
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock RedisClient."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._prefix = 'claudevn:'

    # Storage for sets
    sets_storage = {}

    async def sadd_side_effect(key, *values):
        if key not in sets_storage:
            sets_storage[key] = set()
        for value in values:
            sets_storage[key].add(value)
        return len(values)

    async def srem_side_effect(key, *values):
        if key in sets_storage:
            for value in values:
                sets_storage[key].discard(value)
        return len(values)

    # Mock async methods
    redis._redis.scan = AsyncMock(return_value=(0, []))
    redis._redis.hgetall = AsyncMock(return_value={})
    redis._redis.hset = AsyncMock()
    redis._redis.delete = AsyncMock()
    redis._redis.sadd = AsyncMock(side_effect=sadd_side_effect)
    redis._redis.srem = AsyncMock(side_effect=srem_side_effect)

    return redis


@pytest.fixture
async def release_service(mock_redis):
    """Create ReleaseService with mocked dependencies."""
    service = ReleaseService(redis_client=mock_redis)
    await service.initialize()
    return service


@pytest.fixture
async def release_service_no_redis():
    """Create ReleaseService without Redis."""
    service = ReleaseService(redis_client=None)
    await service.initialize()
    return service


@pytest.fixture
def sample_release():
    """Create a sample Release instance."""
    return Release(
        release_id="release_abc123",
        name="v1.0.0",
        description="First major release",
        target_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        status=ReleaseStatus.PLANNED
    )


# ============================================================================
# Model Tests
# ============================================================================

class TestReleaseModel:
    """Test Release model."""

    def test_release_defaults(self):
        """Test Release model default values."""
        release = Release(
            release_id="release_test",
            name="Test Release"
        )

        assert release.release_id == "release_test"
        assert release.name == "Test Release"
        assert release.description is None
        assert release.target_date is None
        assert release.status == ReleaseStatus.PLANNED
        assert release.created_at is not None
        assert release.updated_at is not None

    def test_release_with_all_fields(self, sample_release):
        """Test Release model with all fields set."""
        assert sample_release.release_id == "release_abc123"
        assert sample_release.name == "v1.0.0"
        assert sample_release.description == "First major release"
        assert sample_release.target_date == datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert sample_release.status == ReleaseStatus.PLANNED

    def test_release_status_values(self):
        """Test ReleaseStatus enum values."""
        assert ReleaseStatus.PLANNED.value == "planned"
        assert ReleaseStatus.ACTIVE.value == "active"
        assert ReleaseStatus.RELEASED.value == "released"


# ============================================================================
# Service Initialization Tests
# ============================================================================

class TestReleaseServiceInit:
    """Test ReleaseService initialization."""

    def test_init_stores_redis_client(self, mock_redis):
        """Test initialization stores Redis client."""
        service = ReleaseService(redis_client=mock_redis)

        assert service._redis is mock_redis
        assert service._initialized is False
        assert service._releases == {}

    def test_init_without_redis(self):
        """Test initialization without Redis client."""
        service = ReleaseService(redis_client=None)

        assert service._redis is None
        assert service._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_loads_data(self, mock_redis):
        """Test initialize loads data from Redis."""
        service = ReleaseService(redis_client=mock_redis)
        await service.initialize()

        assert service._initialized is True
        mock_redis._redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_initialize_only_once(self, mock_redis):
        """Test initialize only runs once."""
        service = ReleaseService(redis_client=mock_redis)

        await service.initialize()
        await service.initialize()  # Second call should be no-op

        assert mock_redis._redis.scan.call_count == 1


# ============================================================================
# CRUD Tests - Create
# ============================================================================

class TestReleaseServiceCreate:
    """Test release creation."""

    @pytest.mark.asyncio
    async def test_create_release_generates_id(self, release_service):
        """Test create_release generates unique ID."""
        request = ReleaseCreateRequest(
            name="v1.0.0",
            description="Initial release"
        )

        release = await release_service.create_release(request)

        assert release.release_id.startswith("release_")
        assert len(release.release_id) == 20  # 'release_' + 12 hex chars
        assert release.name == "v1.0.0"
        assert release.description == "Initial release"

    @pytest.mark.asyncio
    async def test_create_release_with_defaults(self, release_service):
        """Test create_release uses default values."""
        request = ReleaseCreateRequest(name="v2.0.0")

        release = await release_service.create_release(request)

        assert release.status == ReleaseStatus.PLANNED
        assert release.description is None
        assert release.target_date is None

    @pytest.mark.asyncio
    async def test_create_release_with_all_fields(self, release_service):
        """Test create_release with all fields."""
        target = datetime(2024, 12, 31, tzinfo=timezone.utc)
        request = ReleaseCreateRequest(
            name="v3.0.0",
            description="Major release",
            target_date=target,
            status=ReleaseStatus.ACTIVE
        )

        release = await release_service.create_release(request)

        assert release.name == "v3.0.0"
        assert release.description == "Major release"
        assert release.target_date == target
        assert release.status == ReleaseStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_release_stores_in_memory(self, release_service):
        """Test created release is stored in memory."""
        request = ReleaseCreateRequest(name="v1.0.0")

        release = await release_service.create_release(request)

        assert release.release_id in release_service._releases
        assert release_service._releases[release.release_id] == release

    @pytest.mark.asyncio
    async def test_create_release_saves_to_redis(self, release_service, mock_redis):
        """Test created release is saved to Redis."""
        request = ReleaseCreateRequest(name="v1.0.0")

        release = await release_service.create_release(request)

        mock_redis._redis.hset.assert_called()
        mock_redis._redis.sadd.assert_called()


# ============================================================================
# CRUD Tests - Read
# ============================================================================

class TestReleaseServiceRead:
    """Test release retrieval."""

    @pytest.mark.asyncio
    async def test_get_release_returns_created(self, release_service):
        """Test get_release returns created release."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)

        retrieved = await release_service.get_release(created.release_id)

        assert retrieved is not None
        assert retrieved.release_id == created.release_id
        assert retrieved.name == created.name

    @pytest.mark.asyncio
    async def test_get_release_returns_none_for_missing(self, release_service):
        """Test get_release returns None for non-existent release."""
        result = await release_service.get_release("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_releases_property(self, release_service):
        """Test direct access to releases dictionary."""
        request1 = ReleaseCreateRequest(name="v1.0.0")
        request2 = ReleaseCreateRequest(name="v2.0.0")

        release1 = await release_service.create_release(request1)
        release2 = await release_service.create_release(request2)

        releases = release_service.releases

        assert len(releases) == 2
        assert release1.release_id in releases
        assert release2.release_id in releases


# ============================================================================
# CRUD Tests - Update
# ============================================================================

class TestReleaseServiceUpdate:
    """Test release updates."""

    @pytest.mark.asyncio
    async def test_update_release_name(self, release_service):
        """Test updating release name."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)

        update = ReleaseUpdateRequest(name="v1.0.1")
        updated = await release_service.update_release(created.release_id, update)

        assert updated is not None
        assert updated.name == "v1.0.1"

    @pytest.mark.asyncio
    async def test_update_release_description(self, release_service):
        """Test updating release description."""
        request = ReleaseCreateRequest(name="v1.0.0", description="Original")
        created = await release_service.create_release(request)

        update = ReleaseUpdateRequest(description="Updated description")
        updated = await release_service.update_release(created.release_id, update)

        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.name == "v1.0.0"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_release_target_date(self, release_service):
        """Test updating release target date."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)

        new_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
        update = ReleaseUpdateRequest(target_date=new_date)
        updated = await release_service.update_release(created.release_id, update)

        assert updated is not None
        assert updated.target_date == new_date

    @pytest.mark.asyncio
    async def test_update_release_status(self, release_service):
        """Test updating release status."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)
        assert created.status == ReleaseStatus.PLANNED

        update = ReleaseUpdateRequest(status=ReleaseStatus.ACTIVE)
        updated = await release_service.update_release(created.release_id, update)

        assert updated is not None
        assert updated.status == ReleaseStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_update_release_updates_updated_at(self, release_service):
        """Test update modifies updated_at timestamp."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)
        original_updated_at = created.updated_at

        # Brief pause to ensure timestamp differs
        import time
        time.sleep(0.01)

        update = ReleaseUpdateRequest(name="v1.0.1")
        updated = await release_service.update_release(created.release_id, update)

        assert updated.updated_at > original_updated_at

    @pytest.mark.asyncio
    async def test_update_nonexistent_release_returns_none(self, release_service):
        """Test updating non-existent release returns None."""
        update = ReleaseUpdateRequest(name="New Name")
        result = await release_service.update_release("nonexistent", update)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_release_status_updates_redis_index(self, release_service, mock_redis):
        """Test status change updates Redis index."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)

        update = ReleaseUpdateRequest(status=ReleaseStatus.ACTIVE)
        await release_service.update_release(created.release_id, update)

        # Should remove from old status index
        mock_redis._redis.srem.assert_called()


# ============================================================================
# CRUD Tests - Delete
# ============================================================================

class TestReleaseServiceDelete:
    """Test release deletion."""

    @pytest.mark.asyncio
    async def test_delete_release_removes_from_memory(self, release_service):
        """Test delete removes release from memory."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)

        assert created.release_id in release_service._releases

        result = await release_service.delete_release(created.release_id)

        assert result is True
        assert created.release_id not in release_service._releases

    @pytest.mark.asyncio
    async def test_delete_release_returns_false_for_missing(self, release_service):
        """Test delete returns False for non-existent release."""
        result = await release_service.delete_release("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_release_removes_from_redis(self, release_service, mock_redis):
        """Test delete removes release from Redis."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service.create_release(request)

        await release_service.delete_release(created.release_id)

        mock_redis._redis.delete.assert_called()
        mock_redis._redis.srem.assert_called()


# ============================================================================
# List Tests
# ============================================================================

class TestReleaseServiceList:
    """Test release listing."""

    @pytest.mark.asyncio
    async def test_list_releases_empty(self, release_service):
        """Test listing when no releases exist."""
        result = await release_service.list_releases()

        assert result.items == []
        assert result.total == 0
        assert result.by_status == {}

    @pytest.mark.asyncio
    async def test_list_releases_returns_all(self, release_service):
        """Test listing returns all releases."""
        await release_service.create_release(ReleaseCreateRequest(name="v1.0"))
        await release_service.create_release(ReleaseCreateRequest(name="v2.0"))
        await release_service.create_release(ReleaseCreateRequest(name="v3.0"))

        result = await release_service.list_releases()

        assert len(result.items) == 3
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_list_releases_filters_by_status(self, release_service):
        """Test listing filters by status."""
        await release_service.create_release(
            ReleaseCreateRequest(name="v1.0", status=ReleaseStatus.PLANNED)
        )
        await release_service.create_release(
            ReleaseCreateRequest(name="v2.0", status=ReleaseStatus.ACTIVE)
        )
        await release_service.create_release(
            ReleaseCreateRequest(name="v3.0", status=ReleaseStatus.RELEASED)
        )

        result = await release_service.list_releases(status=ReleaseStatus.ACTIVE)

        assert len(result.items) == 1
        assert result.items[0].name == "v2.0"
        assert result.total == 3  # Total still includes all

    @pytest.mark.asyncio
    async def test_list_releases_respects_limit(self, release_service):
        """Test listing respects limit parameter."""
        for i in range(5):
            await release_service.create_release(
                ReleaseCreateRequest(name=f"v{i}.0")
            )

        result = await release_service.list_releases(limit=3)

        assert len(result.items) == 3
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_list_releases_sorted_by_target_date(self, release_service):
        """Test releases are sorted by target date."""
        await release_service.create_release(
            ReleaseCreateRequest(
                name="v3.0",
                target_date=datetime(2024, 12, 1, tzinfo=timezone.utc)
            )
        )
        await release_service.create_release(
            ReleaseCreateRequest(
                name="v1.0",
                target_date=datetime(2024, 6, 1, tzinfo=timezone.utc)
            )
        )
        await release_service.create_release(
            ReleaseCreateRequest(
                name="v2.0",
                target_date=datetime(2024, 9, 1, tzinfo=timezone.utc)
            )
        )

        result = await release_service.list_releases()

        assert result.items[0].name == "v1.0"
        assert result.items[1].name == "v2.0"
        assert result.items[2].name == "v3.0"

    @pytest.mark.asyncio
    async def test_list_releases_null_dates_last(self, release_service):
        """Test releases with null target_date come last."""
        await release_service.create_release(
            ReleaseCreateRequest(name="v1.0")  # No target_date
        )
        await release_service.create_release(
            ReleaseCreateRequest(
                name="v2.0",
                target_date=datetime(2024, 6, 1, tzinfo=timezone.utc)
            )
        )

        result = await release_service.list_releases()

        assert result.items[0].name == "v2.0"
        assert result.items[1].name == "v1.0"

    @pytest.mark.asyncio
    async def test_list_releases_includes_stats(self, release_service):
        """Test listing includes status statistics."""
        await release_service.create_release(
            ReleaseCreateRequest(name="v1.0", status=ReleaseStatus.PLANNED)
        )
        await release_service.create_release(
            ReleaseCreateRequest(name="v2.0", status=ReleaseStatus.PLANNED)
        )
        await release_service.create_release(
            ReleaseCreateRequest(name="v3.0", status=ReleaseStatus.ACTIVE)
        )

        result = await release_service.list_releases()

        assert result.by_status['planned'] == 2
        assert result.by_status['active'] == 1


# ============================================================================
# Global Service Instance Tests
# ============================================================================

class TestReleaseServiceGlobal:
    """Test global service instance management."""

    def test_get_service_raises_when_not_set(self):
        """Test get_release_service raises when not initialized."""
        # Clear any existing global instance
        import services.release_service as rs
        rs._release_service = None

        with pytest.raises(RuntimeError, match="Release service not initialized"):
            get_release_service()

    def test_set_service_and_get(self, release_service):
        """Test set_release_service and get_release_service."""
        set_release_service(release_service)

        retrieved = get_release_service()

        assert retrieved is release_service

        # Cleanup
        import services.release_service as rs
        rs._release_service = None


# ============================================================================
# Service Without Redis Tests
# ============================================================================

class TestReleaseServiceNoRedis:
    """Test ReleaseService without Redis persistence."""

    @pytest.mark.asyncio
    async def test_create_without_redis(self, release_service_no_redis):
        """Test create works without Redis."""
        request = ReleaseCreateRequest(name="v1.0.0")

        release = await release_service_no_redis.create_release(request)

        assert release.name == "v1.0.0"
        assert release.release_id in release_service_no_redis._releases

    @pytest.mark.asyncio
    async def test_update_without_redis(self, release_service_no_redis):
        """Test update works without Redis."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service_no_redis.create_release(request)

        update = ReleaseUpdateRequest(name="v1.0.1")
        updated = await release_service_no_redis.update_release(created.release_id, update)

        assert updated.name == "v1.0.1"

    @pytest.mark.asyncio
    async def test_delete_without_redis(self, release_service_no_redis):
        """Test delete works without Redis."""
        request = ReleaseCreateRequest(name="v1.0.0")
        created = await release_service_no_redis.create_release(request)

        result = await release_service_no_redis.delete_release(created.release_id)

        assert result is True
        assert created.release_id not in release_service_no_redis._releases
