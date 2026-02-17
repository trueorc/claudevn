"""Unit tests for MCP compute authentication (serving/mcp/auth.py)."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from mcp.auth import (
    DEFAULT_KEY_TTL,
    _compute_api_keys,
    _redis_key,
    generate_api_key,
    initialize_from_redis,
    refresh_key_ttl,
    register_compute_key,
    revoke_compute_key,
    rotate_compute_key,
    set_auth_redis,
    verify_compute_auth,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_state():
    """Reset module-level state between tests."""
    _compute_api_keys.clear()
    set_auth_redis(None)
    yield
    _compute_api_keys.clear()
    set_auth_redis(None)


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient matching the project's wrapper pattern."""
    client = MagicMock()
    client._prefix = "claudevn:"
    client._redis = MagicMock()
    client._redis.sadd = AsyncMock()
    client._redis.srem = AsyncMock()
    client._redis.smembers = AsyncMock(return_value=set())
    client._redis.scard = AsyncMock(return_value=0)
    client._redis.set = AsyncMock()
    client._redis.get = AsyncMock(return_value=None)
    client._redis.delete = AsyncMock()
    client._redis.expire = AsyncMock(return_value=True)
    client._redis.scan = AsyncMock(return_value=(0, []))
    return client


# ---------------------------------------------------------------------------
# generate_api_key
# ---------------------------------------------------------------------------

class TestGenerateApiKey:
    def test_prefix(self):
        key = generate_api_key()
        assert key.startswith("troc_")

    def test_length(self):
        key = generate_api_key()
        # "troc_" (5) + 48 hex chars = 53
        assert len(key) == 53

    def test_uniqueness(self):
        keys = {generate_api_key() for _ in range(50)}
        assert len(keys) == 50


# ---------------------------------------------------------------------------
# register_compute_key
# ---------------------------------------------------------------------------

class TestRegisterComputeKey:
    @pytest.mark.asyncio
    async def test_register_in_memory_only(self):
        await register_compute_key("comp-1", "key-1")
        assert "key-1" in _compute_api_keys["comp-1"]

    @pytest.mark.asyncio
    async def test_register_persists_to_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        await register_compute_key("comp-1", "key-1")

        assert "key-1" in _compute_api_keys["comp-1"]
        mock_redis._redis.sadd.assert_awaited_once_with(
            "claudevn:compute:apikeys:comp-1", "key-1"
        )
        mock_redis._redis.expire.assert_awaited_once_with(
            "claudevn:compute:apikeys:comp-1", DEFAULT_KEY_TTL
        )

    @pytest.mark.asyncio
    async def test_register_custom_ttl(self, mock_redis):
        set_auth_redis(mock_redis)
        await register_compute_key("comp-1", "key-1", ttl=3600)

        mock_redis._redis.expire.assert_awaited_once_with(
            "claudevn:compute:apikeys:comp-1", 3600
        )

    @pytest.mark.asyncio
    async def test_register_redis_error_still_caches(self, mock_redis):
        mock_redis._redis.sadd.side_effect = Exception("connection lost")
        set_auth_redis(mock_redis)

        await register_compute_key("comp-1", "key-1")
        assert "key-1" in _compute_api_keys["comp-1"]

    @pytest.mark.asyncio
    async def test_register_multiple_keys_for_same_compute(self):
        """Multiple keys can coexist for the same compute (#828)."""
        await register_compute_key("comp-1", "key-A")
        await register_compute_key("comp-1", "key-B")

        assert _compute_api_keys["comp-1"] == {"key-A", "key-B"}


# ---------------------------------------------------------------------------
# revoke_compute_key
# ---------------------------------------------------------------------------

class TestRevokeComputeKey:
    @pytest.mark.asyncio
    async def test_revoke_all_keys(self):
        _compute_api_keys["comp-1"] = {"key-1", "key-2"}
        await revoke_compute_key("comp-1")
        assert "comp-1" not in _compute_api_keys

    @pytest.mark.asyncio
    async def test_revoke_specific_key(self):
        _compute_api_keys["comp-1"] = {"key-1", "key-2"}
        await revoke_compute_key("comp-1", api_key="key-1")
        assert _compute_api_keys["comp-1"] == {"key-2"}

    @pytest.mark.asyncio
    async def test_revoke_last_specific_key_removes_compute(self):
        _compute_api_keys["comp-1"] = {"key-1"}
        await revoke_compute_key("comp-1", api_key="key-1")
        assert "comp-1" not in _compute_api_keys

    @pytest.mark.asyncio
    async def test_revoke_deletes_from_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        _compute_api_keys["comp-1"] = {"key-1"}

        await revoke_compute_key("comp-1")

        assert "comp-1" not in _compute_api_keys
        mock_redis._redis.delete.assert_awaited_once_with(
            "claudevn:compute:apikeys:comp-1"
        )

    @pytest.mark.asyncio
    async def test_revoke_specific_key_from_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        _compute_api_keys["comp-1"] = {"key-1", "key-2"}

        await revoke_compute_key("comp-1", api_key="key-1")

        mock_redis._redis.srem.assert_awaited_once_with(
            "claudevn:compute:apikeys:comp-1", "key-1"
        )

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key(self, mock_redis):
        set_auth_redis(mock_redis)
        await revoke_compute_key("comp-999")
        # Should not raise
        mock_redis._redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoke_redis_error_still_removes_cache(self, mock_redis):
        mock_redis._redis.delete.side_effect = Exception("connection lost")
        set_auth_redis(mock_redis)
        _compute_api_keys["comp-1"] = {"key-1"}

        await revoke_compute_key("comp-1")
        assert "comp-1" not in _compute_api_keys


# ---------------------------------------------------------------------------
# initialize_from_redis
# ---------------------------------------------------------------------------

class TestInitializeFromRedis:
    @pytest.mark.asyncio
    async def test_no_redis_is_noop(self):
        await initialize_from_redis()  # should not raise
        assert _compute_api_keys == {}

    @pytest.mark.asyncio
    async def test_loads_set_keys_from_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        # First scan for new set-based keys
        mock_redis._redis.scan.side_effect = [
            (0, ["claudevn:compute:apikeys:comp-1"]),  # set-based scan
            (0, []),  # legacy scan
        ]
        mock_redis._redis.smembers.return_value = {"key-1", "key-2"}

        await initialize_from_redis()

        assert _compute_api_keys["comp-1"] == {"key-1", "key-2"}

    @pytest.mark.asyncio
    async def test_loads_legacy_keys_from_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        # First scan for set-based keys (empty), then legacy
        mock_redis._redis.scan.side_effect = [
            (0, []),  # set-based scan
            (0, ["claudevn:compute:apikey:comp-1"]),  # legacy scan
        ]
        mock_redis._redis.get.return_value = "legacy-key"

        await initialize_from_redis()

        assert "legacy-key" in _compute_api_keys["comp-1"]

    @pytest.mark.asyncio
    async def test_redis_error_during_init(self, mock_redis):
        set_auth_redis(mock_redis)
        mock_redis._redis.scan.side_effect = Exception("connection lost")

        await initialize_from_redis()  # should not raise
        assert _compute_api_keys == {}


# ---------------------------------------------------------------------------
# verify_compute_auth
# ---------------------------------------------------------------------------

class TestVerifyComputeAuth:
    @pytest.mark.asyncio
    async def test_missing_authorization(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(authorization=None, x_compute_id="comp-1")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "MISSING_AUTH"

    @pytest.mark.asyncio
    async def test_missing_compute_id(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Bearer some-key", x_compute_id=None
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "MISSING_COMPUTE_ID"

    @pytest.mark.asyncio
    async def test_non_bearer_token(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Basic abc", x_compute_id="comp-1"
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "INVALID_AUTH"

    @pytest.mark.asyncio
    async def test_auth_bypass(self):
        with patch.dict("os.environ", {"MCP_AUTH_BYPASS": "true"}):
            result = await verify_compute_auth(
                authorization="Bearer any-key", x_compute_id="comp-1"
            )
        assert result == ("comp-1", "any-key")

    @pytest.mark.asyncio
    async def test_fail_closed_no_keys_registered(self):
        """When no keys are registered, auth must REJECT (fail closed)."""
        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Bearer some-key", x_compute_id="comp-1"
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["code"] == "UNKNOWN_COMPUTE"

    @pytest.mark.asyncio
    async def test_valid_key_from_cache(self):
        _compute_api_keys["comp-1"] = {"correct-key"}

        result = await verify_compute_auth(
            authorization="Bearer correct-key", x_compute_id="comp-1"
        )
        assert result == ("comp-1", "correct-key")

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        _compute_api_keys["comp-1"] = {"correct-key"}

        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Bearer wrong-key", x_compute_id="comp-1"
            )
        assert exc_info.value.detail["code"] == "INVALID_KEY"

    @pytest.mark.asyncio
    async def test_unknown_compute(self):
        _compute_api_keys["comp-1"] = {"key-1"}

        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Bearer key-1", x_compute_id="comp-unknown"
            )
        assert exc_info.value.detail["code"] == "UNKNOWN_COMPUTE"

    @pytest.mark.asyncio
    async def test_cache_miss_falls_through_to_redis(self, mock_redis):
        """Key not in memory but present in Redis -> allow and cache."""
        set_auth_redis(mock_redis)
        mock_redis._redis.smembers.return_value = {"redis-key"}

        result = await verify_compute_auth(
            authorization="Bearer redis-key", x_compute_id="comp-1"
        )
        assert result == ("comp-1", "redis-key")
        assert "redis-key" in _compute_api_keys["comp-1"]

    @pytest.mark.asyncio
    async def test_cache_miss_and_redis_miss(self, mock_redis):
        """Key not in memory and not in Redis -> reject."""
        set_auth_redis(mock_redis)
        mock_redis._redis.smembers.return_value = set()

        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Bearer some-key", x_compute_id="comp-1"
            )
        assert exc_info.value.detail["code"] == "UNKNOWN_COMPUTE"

    @pytest.mark.asyncio
    async def test_redis_error_during_verify(self, mock_redis):
        """Redis error during verify -> falls back to cache-only check."""
        set_auth_redis(mock_redis)
        mock_redis._redis.smembers.side_effect = Exception("connection lost")

        with pytest.raises(HTTPException) as exc_info:
            await verify_compute_auth(
                authorization="Bearer key", x_compute_id="comp-1"
            )
        assert exc_info.value.detail["code"] == "UNKNOWN_COMPUTE"

    @pytest.mark.asyncio
    async def test_multiple_keys_any_valid(self):
        """Any of the registered keys should be accepted (#828)."""
        _compute_api_keys["comp-1"] = {"key-A", "key-B"}

        result_a = await verify_compute_auth(
            authorization="Bearer key-A", x_compute_id="comp-1"
        )
        assert result_a == ("comp-1", "key-A")

        result_b = await verify_compute_auth(
            authorization="Bearer key-B", x_compute_id="comp-1"
        )
        assert result_b == ("comp-1", "key-B")

    @pytest.mark.asyncio
    async def test_old_key_still_valid_after_new_registration(self):
        """Registering a new key doesn't invalidate the old one (#828)."""
        await register_compute_key("comp-1", "key-old")
        await register_compute_key("comp-1", "key-new")

        # Both keys should work
        result = await verify_compute_auth(
            authorization="Bearer key-old", x_compute_id="comp-1"
        )
        assert result == ("comp-1", "key-old")


# ---------------------------------------------------------------------------
# rotate_compute_key
# ---------------------------------------------------------------------------

class TestRotateComputeKey:
    @pytest.mark.asyncio
    async def test_rotate_existing_key(self):
        _compute_api_keys["comp-1"] = {"old-key"}

        new_key = await rotate_compute_key("comp-1")
        assert new_key is not None
        assert new_key != "old-key"
        assert new_key.startswith("troc_")
        # After rotation, only the new key should be valid
        assert _compute_api_keys["comp-1"] == {new_key}

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_key_no_redis(self):
        result = await rotate_compute_key("comp-999")
        assert result is None

    @pytest.mark.asyncio
    async def test_rotate_key_from_redis(self, mock_redis):
        """Key exists in Redis but not in cache -> rotation succeeds."""
        set_auth_redis(mock_redis)
        mock_redis._redis.scard.return_value = 1

        new_key = await rotate_compute_key("comp-1")
        assert new_key is not None
        assert new_key.startswith("troc_")

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_in_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        mock_redis._redis.scard.return_value = 0

        result = await rotate_compute_key("comp-999")
        assert result is None


# ---------------------------------------------------------------------------
# refresh_key_ttl
# ---------------------------------------------------------------------------

class TestRefreshKeyTtl:
    @pytest.mark.asyncio
    async def test_refresh_no_redis(self):
        _compute_api_keys["comp-1"] = {"key-1"}
        result = await refresh_key_ttl("comp-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_refresh_no_redis_unknown_key(self):
        result = await refresh_key_ttl("comp-999")
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_with_redis(self, mock_redis):
        set_auth_redis(mock_redis)
        mock_redis._redis.expire.return_value = True

        result = await refresh_key_ttl("comp-1", ttl=7200)
        assert result is True
        mock_redis._redis.expire.assert_awaited_once_with(
            "claudevn:compute:apikeys:comp-1", 7200
        )

    @pytest.mark.asyncio
    async def test_refresh_expired_key(self, mock_redis):
        set_auth_redis(mock_redis)
        mock_redis._redis.expire.return_value = False

        result = await refresh_key_ttl("comp-1")
        assert result is False


# ---------------------------------------------------------------------------
# _redis_key helper
# ---------------------------------------------------------------------------

class TestRedisKey:
    def test_default_prefix(self):
        assert _redis_key("comp-1") == "claudevn:compute:apikeys:comp-1"

    def test_custom_prefix(self, mock_redis):
        mock_redis._prefix = "custom:"
        set_auth_redis(mock_redis)
        assert _redis_key("comp-1") == "custom:compute:apikeys:comp-1"


# ---------------------------------------------------------------------------
# Production config safety
# ---------------------------------------------------------------------------

class TestProductionConfig:
    """Verify MCP_AUTH_BYPASS is not in production docker-compose.yml."""

    def test_no_auth_bypass_in_production_compose(self):
        """docker-compose.yml must NOT contain MCP_AUTH_BYPASS."""
        compose_path = Path(__file__).parent.parent.parent.parent / "docker-compose.yml"
        content = compose_path.read_text()
        # Check non-comment lines only
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "MCP_AUTH_BYPASS" not in stripped, (
                f"MCP_AUTH_BYPASS found in production docker-compose.yml: {stripped}"
            )

    def test_auth_bypass_in_test_compose(self):
        """docker-compose.test.yml should contain MCP_AUTH_BYPASS=true."""
        test_compose = Path(__file__).parent.parent.parent.parent / "docker-compose.test.yml"
        assert test_compose.exists(), "docker-compose.test.yml not found"
        content = test_compose.read_text()
        assert "MCP_AUTH_BYPASS=true" in content
