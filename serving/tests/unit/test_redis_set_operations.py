"""Unit tests for RedisClient generic set, hash, and key operations."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from git.redis_client import RedisClient


@pytest.fixture
def mock_redis():
    """Create a mock Redis connection."""
    r = AsyncMock()
    return r


@pytest.fixture
def redis_client(mock_redis):
    """Create a RedisClient with mock Redis and known prefix."""
    return RedisClient(redis=mock_redis, prefix="test:")


# =============================================================================
# Test: sadd
# =============================================================================

class TestSadd:
    """Tests for RedisClient.sadd()."""

    @pytest.mark.asyncio
    async def test_sadd_single_member(self, redis_client, mock_redis):
        """Test adding a single member to a set."""
        mock_redis.sadd.return_value = 1

        result = await redis_client.sadd("projects:all", "proj_abc")

        assert result == 1
        mock_redis.sadd.assert_awaited_once_with("test:projects:all", "proj_abc")

    @pytest.mark.asyncio
    async def test_sadd_multiple_members(self, redis_client, mock_redis):
        """Test adding multiple members to a set."""
        mock_redis.sadd.return_value = 3

        result = await redis_client.sadd("myset", "a", "b", "c")

        assert result == 3
        mock_redis.sadd.assert_awaited_once_with("test:myset", "a", "b", "c")

    @pytest.mark.asyncio
    async def test_sadd_applies_prefix(self, redis_client, mock_redis):
        """Test that sadd applies key prefix."""
        mock_redis.sadd.return_value = 1

        await redis_client.sadd("mykey", "value")

        call_args = mock_redis.sadd.call_args
        assert call_args[0][0] == "test:mykey"


# =============================================================================
# Test: srem
# =============================================================================

class TestSrem:
    """Tests for RedisClient.srem()."""

    @pytest.mark.asyncio
    async def test_srem_single_member(self, redis_client, mock_redis):
        """Test removing a single member from a set."""
        mock_redis.srem.return_value = 1

        result = await redis_client.srem("projects:all", "proj_abc")

        assert result == 1
        mock_redis.srem.assert_awaited_once_with("test:projects:all", "proj_abc")

    @pytest.mark.asyncio
    async def test_srem_multiple_members(self, redis_client, mock_redis):
        """Test removing multiple members from a set."""
        mock_redis.srem.return_value = 2

        result = await redis_client.srem("myset", "a", "b")

        assert result == 2
        mock_redis.srem.assert_awaited_once_with("test:myset", "a", "b")

    @pytest.mark.asyncio
    async def test_srem_nonexistent_member(self, redis_client, mock_redis):
        """Test removing a member that doesn't exist returns 0."""
        mock_redis.srem.return_value = 0

        result = await redis_client.srem("myset", "nonexistent")

        assert result == 0


# =============================================================================
# Test: smembers
# =============================================================================

class TestSmembers:
    """Tests for RedisClient.smembers()."""

    @pytest.mark.asyncio
    async def test_smembers_returns_set(self, redis_client, mock_redis):
        """Test that smembers returns a set of members."""
        mock_redis.smembers.return_value = {"proj_a", "proj_b", "proj_c"}

        result = await redis_client.smembers("projects:all")

        assert result == {"proj_a", "proj_b", "proj_c"}
        mock_redis.smembers.assert_awaited_once_with("test:projects:all")

    @pytest.mark.asyncio
    async def test_smembers_empty_set(self, redis_client, mock_redis):
        """Test smembers on empty set."""
        mock_redis.smembers.return_value = set()

        result = await redis_client.smembers("empty_set")

        assert result == set()

    @pytest.mark.asyncio
    async def test_smembers_applies_prefix(self, redis_client, mock_redis):
        """Test that smembers applies key prefix."""
        mock_redis.smembers.return_value = set()

        await redis_client.smembers("mykey")

        mock_redis.smembers.assert_awaited_once_with("test:mykey")


# =============================================================================
# Test: hset
# =============================================================================

class TestHset:
    """Tests for RedisClient.hset()."""

    @pytest.mark.asyncio
    async def test_hset_field_value(self, redis_client, mock_redis):
        """Test setting a hash field with positional args."""
        mock_redis.hset.return_value = 1

        result = await redis_client.hset("project:abc", "data", '{"name":"test"}')

        assert result == 1
        mock_redis.hset.assert_awaited_once_with(
            "test:project:abc", "data", '{"name":"test"}'
        )

    @pytest.mark.asyncio
    async def test_hset_with_mapping(self, redis_client, mock_redis):
        """Test setting hash fields with mapping kwarg."""
        mock_redis.hset.return_value = 2

        result = await redis_client.hset(
            "project:abc", mapping={"field1": "val1", "field2": "val2"}
        )

        assert result == 2
        mock_redis.hset.assert_awaited_once_with(
            "test:project:abc", mapping={"field1": "val1", "field2": "val2"}
        )

    @pytest.mark.asyncio
    async def test_hset_applies_prefix(self, redis_client, mock_redis):
        """Test that hset applies key prefix."""
        mock_redis.hset.return_value = 1

        await redis_client.hset("mykey", "field", "value")

        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "test:mykey"


# =============================================================================
# Test: hgetall
# =============================================================================

class TestHgetall:
    """Tests for RedisClient.hgetall()."""

    @pytest.mark.asyncio
    async def test_hgetall_returns_dict(self, redis_client, mock_redis):
        """Test that hgetall returns field-value dict."""
        mock_redis.hgetall.return_value = {"data": '{"name":"test"}', "status": "active"}

        result = await redis_client.hgetall("project:abc")

        assert result == {"data": '{"name":"test"}', "status": "active"}
        mock_redis.hgetall.assert_awaited_once_with("test:project:abc")

    @pytest.mark.asyncio
    async def test_hgetall_empty_hash(self, redis_client, mock_redis):
        """Test hgetall on non-existent key."""
        mock_redis.hgetall.return_value = {}

        result = await redis_client.hgetall("nonexistent")

        assert result == {}

    @pytest.mark.asyncio
    async def test_hgetall_applies_prefix(self, redis_client, mock_redis):
        """Test that hgetall applies key prefix."""
        mock_redis.hgetall.return_value = {}

        await redis_client.hgetall("mykey")

        mock_redis.hgetall.assert_awaited_once_with("test:mykey")


# =============================================================================
# Test: delete
# =============================================================================

class TestDelete:
    """Tests for RedisClient.delete()."""

    @pytest.mark.asyncio
    async def test_delete_single_key(self, redis_client, mock_redis):
        """Test deleting a single key."""
        mock_redis.delete.return_value = 1

        result = await redis_client.delete("project:abc")

        assert result == 1
        mock_redis.delete.assert_awaited_once_with("test:project:abc")

    @pytest.mark.asyncio
    async def test_delete_multiple_keys(self, redis_client, mock_redis):
        """Test deleting multiple keys."""
        mock_redis.delete.return_value = 2

        result = await redis_client.delete("key1", "key2")

        assert result == 2
        mock_redis.delete.assert_awaited_once_with("test:key1", "test:key2")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, redis_client, mock_redis):
        """Test deleting non-existent key returns 0."""
        mock_redis.delete.return_value = 0

        result = await redis_client.delete("nonexistent")

        assert result == 0

    @pytest.mark.asyncio
    async def test_delete_applies_prefix_to_all(self, redis_client, mock_redis):
        """Test that delete prefixes all keys."""
        mock_redis.delete.return_value = 3

        await redis_client.delete("a", "b", "c")

        mock_redis.delete.assert_awaited_once_with("test:a", "test:b", "test:c")


# =============================================================================
# Test: Integration with ProjectService pattern
# =============================================================================

class TestProjectServicePattern:
    """Test the exact usage patterns from ProjectService."""

    @pytest.mark.asyncio
    async def test_project_service_initialize_pattern(self, redis_client, mock_redis):
        """Test the pattern used by ProjectService.initialize()."""
        mock_redis.smembers.return_value = {"proj_123", "proj_456"}

        project_ids = await redis_client.smembers("projects:all")

        assert "proj_123" in project_ids
        assert "proj_456" in project_ids

    @pytest.mark.asyncio
    async def test_project_service_save_pattern(self, redis_client, mock_redis):
        """Test the pattern used by ProjectService._save_project()."""
        mock_redis.sadd.return_value = 1
        mock_redis.hset.return_value = 1

        await redis_client.sadd("projects:all", "proj_abc")
        await redis_client.hset("project:proj_abc", "data", '{"name":"Test"}')

        mock_redis.sadd.assert_awaited_once_with("test:projects:all", "proj_abc")
        mock_redis.hset.assert_awaited_once_with(
            "test:project:proj_abc", "data", '{"name":"Test"}'
        )

    @pytest.mark.asyncio
    async def test_project_service_delete_pattern(self, redis_client, mock_redis):
        """Test the pattern used by ProjectService._delete_project_storage()."""
        mock_redis.srem.return_value = 1
        mock_redis.delete.return_value = 1

        await redis_client.srem("projects:all", "proj_abc")
        await redis_client.delete("project:proj_abc")

        mock_redis.srem.assert_awaited_once_with("test:projects:all", "proj_abc")
        mock_redis.delete.assert_awaited_once_with("test:project:proj_abc")
