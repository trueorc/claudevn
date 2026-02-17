"""Unit tests for Redis health check functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from redis.exceptions import ConnectionError, TimeoutError

from git.redis_client import (
    RedisClient,
    get_redis_client,
    set_redis_client,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis connection."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def redis_client(mock_redis):
    """Create a RedisClient with mock Redis."""
    return RedisClient(redis=mock_redis, prefix="test:")


class TestRedisClientHealthCheck:
    """Tests for RedisClient.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, redis_client, mock_redis):
        """Test successful health check returns connected status."""
        result = await redis_client.health_check()

        assert result["connected"] is True
        assert "response_time_ms" in result
        assert result["response_time_ms"] >= 0
        assert "error" not in result
        mock_redis.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, redis_client, mock_redis):
        """Test health check handles connection errors."""
        mock_redis.ping.side_effect = ConnectionError("Connection refused")

        result = await redis_client.health_check()

        assert result["connected"] is False
        assert "response_time_ms" in result
        assert "error" in result
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_timeout_error(self, redis_client, mock_redis):
        """Test health check handles timeout errors."""
        mock_redis.ping.side_effect = TimeoutError("Connection timed out")

        result = await redis_client.health_check()

        assert result["connected"] is False
        assert "response_time_ms" in result
        assert "error" in result
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_ping_returns_false(self, redis_client, mock_redis):
        """Test health check when ping returns False."""
        mock_redis.ping.return_value = False

        result = await redis_client.health_check()

        assert result["connected"] is False
        assert "response_time_ms" in result

    @pytest.mark.asyncio
    async def test_health_check_response_time_measured(self, redis_client, mock_redis):
        """Test that response time is measured in milliseconds."""
        result = await redis_client.health_check()

        assert isinstance(result["response_time_ms"], float)
        assert result["response_time_ms"] >= 0


class TestRedisClientGlobalGetterSetter:
    """Tests for global getter/setter functions."""

    def test_set_and_get_redis_client(self, redis_client):
        """Test setting and getting the global Redis client."""
        # Clear any existing state
        set_redis_client(None)
        assert get_redis_client() is None

        # Set the client
        set_redis_client(redis_client)
        assert get_redis_client() == redis_client

        # Clean up
        set_redis_client(None)

    def test_get_redis_client_when_not_set(self):
        """Test getting Redis client when not initialized."""
        set_redis_client(None)
        assert get_redis_client() is None

    def test_set_redis_client_to_none(self, redis_client):
        """Test setting Redis client to None."""
        set_redis_client(redis_client)
        assert get_redis_client() is not None

        set_redis_client(None)
        assert get_redis_client() is None


class TestHealthEndpointRedisIntegration:
    """Tests for Redis status in health endpoint response."""

    @pytest.mark.asyncio
    async def test_health_endpoint_includes_redis_connected(self, redis_client):
        """Test health endpoint returns Redis connected status."""
        set_redis_client(redis_client)

        # Simulate what the health endpoint does
        client = get_redis_client()
        assert client is not None

        health = await client.health_check()
        assert health["connected"] is True

        # Clean up
        set_redis_client(None)

    @pytest.mark.asyncio
    async def test_health_endpoint_redis_not_initialized(self):
        """Test health endpoint when Redis client is not initialized."""
        set_redis_client(None)

        client = get_redis_client()
        assert client is None

        # This is how the health endpoint should handle it
        if client:
            redis_stats = await client.health_check()
        else:
            redis_stats = {"connected": False, "error": "Redis client not initialized"}

        assert redis_stats["connected"] is False
        assert "error" in redis_stats
