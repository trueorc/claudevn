"""Unit tests for FeatureFlagService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.feature_flag import FeatureFlag, FlagCategory
from services.feature_flag_service import FeatureFlagService


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis._prefix = "claudevn:"
    redis._redis = AsyncMock()
    redis._redis.get = AsyncMock(return_value=None)
    redis._redis.set = AsyncMock()
    redis._redis.delete = AsyncMock()
    return redis


@pytest.fixture
def service_no_redis():
    """FeatureFlagService without Redis."""
    return FeatureFlagService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """FeatureFlagService with mock Redis."""
    return FeatureFlagService(redis_client=mock_redis)


class TestFeatureFlagServiceInit:
    @pytest.mark.asyncio
    async def test_initialize_seeds_defaults(self, service_no_redis):
        await service_no_redis.initialize()
        flags = await service_no_redis.list_flags()
        assert len(flags) >= 1
        names = [f.name for f in flags]
        assert "control-center" in names

    @pytest.mark.asyncio
    async def test_initialize_with_redis_loads_existing(self, service_with_redis, mock_redis):
        # Simulate no existing flags in Redis
        mock_redis._redis.get.return_value = None
        await service_with_redis.initialize()
        flags = await service_with_redis.list_flags()
        assert len(flags) >= 1

    @pytest.mark.asyncio
    async def test_initialize_does_not_overwrite_existing(self, service_no_redis):
        await service_no_redis.initialize()
        # Manually toggle the default flag
        await service_no_redis.toggle_flag("control-center", True)

        # Re-initialize should NOT overwrite the toggle
        await service_no_redis.initialize()
        flag = await service_no_redis.get_flag("control-center")
        assert flag.enabled is True


class TestFeatureFlagCRUD:
    @pytest.mark.asyncio
    async def test_create_flag(self, service_no_redis):
        await service_no_redis.initialize()
        flag = await service_no_redis.create_flag(
            name="test-flag",
            description="A test flag",
            enabled=False,
            category=FlagCategory.UI,
        )
        assert flag.name == "test-flag"
        assert flag.description == "A test flag"
        assert flag.enabled is False
        assert flag.category == FlagCategory.UI

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="dup-flag")
        with pytest.raises(ValueError, match="already exists"):
            await service_no_redis.create_flag(name="dup-flag")

    @pytest.mark.asyncio
    async def test_get_flag(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="get-me")
        flag = await service_no_redis.get_flag("get-me")
        assert flag is not None
        assert flag.name == "get-me"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, service_no_redis):
        await service_no_redis.initialize()
        assert await service_no_redis.get_flag("nope") is None

    @pytest.mark.asyncio
    async def test_list_flags(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="flag-a")
        await service_no_redis.create_flag(name="flag-b")
        flags = await service_no_redis.list_flags()
        names = [f.name for f in flags]
        assert "flag-a" in names
        assert "flag-b" in names

    @pytest.mark.asyncio
    async def test_delete_flag(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="doomed")
        assert await service_no_redis.delete_flag("doomed") is True
        assert await service_no_redis.get_flag("doomed") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, service_no_redis):
        await service_no_redis.initialize()
        assert await service_no_redis.delete_flag("nope") is False


class TestFeatureFlagToggle:
    @pytest.mark.asyncio
    async def test_toggle_on(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="toggle-me", enabled=False)
        flag = await service_no_redis.toggle_flag("toggle-me", True)
        assert flag.enabled is True

    @pytest.mark.asyncio
    async def test_toggle_off(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="toggle-off", enabled=True)
        flag = await service_no_redis.toggle_flag("toggle-off", False)
        assert flag.enabled is False

    @pytest.mark.asyncio
    async def test_toggle_nonexistent_returns_none(self, service_no_redis):
        await service_no_redis.initialize()
        assert await service_no_redis.toggle_flag("nope", True) is None

    @pytest.mark.asyncio
    async def test_toggle_updates_timestamp(self, service_no_redis):
        await service_no_redis.initialize()
        flag = await service_no_redis.create_flag(name="ts-flag")
        original_updated = flag.updated_at
        toggled = await service_no_redis.toggle_flag("ts-flag", True)
        assert toggled.updated_at >= original_updated


class TestIsEnabled:
    @pytest.mark.asyncio
    async def test_is_enabled_true(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="enabled-flag", enabled=True)
        assert await service_no_redis.is_enabled("enabled-flag") is True

    @pytest.mark.asyncio
    async def test_is_enabled_false(self, service_no_redis):
        await service_no_redis.initialize()
        await service_no_redis.create_flag(name="disabled-flag", enabled=False)
        assert await service_no_redis.is_enabled("disabled-flag") is False

    @pytest.mark.asyncio
    async def test_is_enabled_unknown_returns_false(self, service_no_redis):
        await service_no_redis.initialize()
        assert await service_no_redis.is_enabled("unknown-flag") is False


class TestRedisPersistence:
    @pytest.mark.asyncio
    async def test_create_saves_to_redis(self, service_with_redis, mock_redis):
        await service_with_redis.initialize()
        await service_with_redis.create_flag(name="redis-flag", description="test")
        # Should have called set for the flag data
        calls = mock_redis._redis.set.call_args_list
        flag_keys = [c[0][0] for c in calls]
        assert any("feature_flag:redis-flag" in k for k in flag_keys)

    @pytest.mark.asyncio
    async def test_toggle_saves_to_redis(self, service_with_redis, mock_redis):
        await service_with_redis.initialize()
        await service_with_redis.create_flag(name="toggle-redis")
        mock_redis._redis.set.reset_mock()
        await service_with_redis.toggle_flag("toggle-redis", True)
        calls = mock_redis._redis.set.call_args_list
        flag_keys = [c[0][0] for c in calls]
        assert any("feature_flag:toggle-redis" in k for k in flag_keys)

    @pytest.mark.asyncio
    async def test_delete_removes_from_redis(self, service_with_redis, mock_redis):
        await service_with_redis.initialize()
        await service_with_redis.create_flag(name="del-redis")
        await service_with_redis.delete_flag("del-redis")
        mock_redis._redis.delete.assert_called()
