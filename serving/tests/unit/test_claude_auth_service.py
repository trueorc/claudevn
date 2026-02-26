"""Tests for ClaudeAuthService (token-based)."""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from models.auth import AuthStatus, TokenStatus
from services.claude_auth_service import ClaudeAuthService, TOKEN_VALIDITY_DAYS


@pytest.fixture
def service():
    """Create a ClaudeAuthService with no Redis."""
    return ClaudeAuthService(redis_client=None, check_interval=3600)


@pytest.fixture
def redis_mock():
    """Create a mock Redis client."""
    mock = MagicMock()
    mock._prefix = "claudevn:"
    mock._redis = AsyncMock()
    mock._redis.scan = AsyncMock(return_value=(0, []))
    mock._redis.hset = AsyncMock()
    mock._redis.hgetall = AsyncMock(return_value={})
    mock._redis.delete = AsyncMock()
    return mock


@pytest.fixture
def service_with_redis(redis_mock):
    """Create a ClaudeAuthService with mock Redis."""
    return ClaudeAuthService(redis_client=redis_mock, check_interval=3600)


class TestInit:
    """Test service initialization."""

    @pytest.mark.asyncio
    async def test_initial_status(self, service):
        status = await service.get_status()
        assert status["status"] == AuthStatus.NOT_CONFIGURED.value
        assert status["authenticated"] is False

    @pytest.mark.asyncio
    async def test_initialize_no_tokens(self, service):
        await service.initialize()
        try:
            status = await service.get_status()
            assert status["status"] == AuthStatus.NOT_CONFIGURED.value
            assert status["authenticated"] is False
        finally:
            await service.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_loads_from_redis(self, service_with_redis, redis_mock):
        """Initialize loads existing tokens from Redis."""
        redis_mock._redis.scan = AsyncMock(return_value=(0, [b"claudevn:auth:serving"]))
        redis_mock._redis.hgetall = AsyncMock(return_value={
            b"token": b"sk-ant-oat01-test",
            b"component_type": b"serving",
            b"authorized_at": b"2026-01-01T00:00:00+00:00",
            b"expires_at": b"2027-01-01T00:00:00+00:00",
            b"status": b"active",
        })

        await service_with_redis.initialize()
        try:
            status = await service_with_redis.get_status()
            assert status["status"] == AuthStatus.AUTHENTICATED.value
            assert status["authenticated"] is True
        finally:
            await service_with_redis.shutdown()


class TestStoreToken:
    """Test token storage."""

    @pytest.mark.asyncio
    async def test_store_valid_token(self, service):
        result = await service.store_token("sk-ant-oat01-test-token")
        assert result["status"] == AuthStatus.AUTHENTICATED.value
        assert result["message"] == "Token stored successfully"
        assert result["expires_at"] is not None

        status = await service.get_status()
        assert status["authenticated"] is True

    @pytest.mark.asyncio
    async def test_store_token_with_custom_component(self, service):
        result = await service.store_token(
            "sk-ant-oat01-test",
            component_id="compute-1",
            component_type="compute",
        )
        assert result["status"] == AuthStatus.AUTHENTICATED.value

        token = await service.get_token("compute-1")
        assert token == "sk-ant-oat01-test"

    @pytest.mark.asyncio
    async def test_store_token_saves_to_redis(self, service_with_redis, redis_mock):
        await service_with_redis.store_token("sk-ant-oat01-redis-test")
        redis_mock._redis.hset.assert_called_once()
        call_kwargs = redis_mock._redis.hset.call_args
        assert "claudevn:auth:serving" in call_kwargs.args or call_kwargs[0][0] == "claudevn:auth:serving"

    @pytest.mark.asyncio
    async def test_store_token_sets_expiry(self, service):
        result = await service.store_token("sk-ant-oat01-test")
        expires_at = datetime.fromisoformat(result["expires_at"])
        now = datetime.now(timezone.utc)
        # Should be ~365 days from now
        delta = expires_at - now
        assert delta.days >= TOKEN_VALIDITY_DAYS - 1
        assert delta.days <= TOKEN_VALIDITY_DAYS + 1

    @pytest.mark.asyncio
    async def test_store_token_broadcasts_refresh(self, service):
        callback = AsyncMock()
        service.set_broadcast_callback(callback)
        await service.store_token("sk-ant-oat01-test")
        callback.assert_called_once()
        args = callback.call_args
        assert args[0][0] == "credentials_refresh"


class TestGetToken:
    """Test token retrieval."""

    @pytest.mark.asyncio
    async def test_get_token_not_found(self, service):
        token = await service.get_token("nonexistent")
        assert token is None

    @pytest.mark.asyncio
    async def test_get_token_active(self, service):
        await service.store_token("sk-ant-oat01-active", component_id="test")
        token = await service.get_token("test")
        assert token == "sk-ant-oat01-active"

    @pytest.mark.asyncio
    async def test_get_token_expired_returns_none(self, service):
        await service.store_token("sk-ant-oat01-test", component_id="test")
        # Manually expire it
        service._tokens["test"]["status"] = TokenStatus.EXPIRED.value

        token = await service.get_token("test")
        assert token is None

    @pytest.mark.asyncio
    async def test_get_token_revoked_returns_none(self, service):
        await service.store_token("sk-ant-oat01-test", component_id="test")
        service._tokens["test"]["status"] = TokenStatus.REVOKED.value

        token = await service.get_token("test")
        assert token is None


class TestGetCredentials:
    """Test credentials retrieval for compute instances."""

    @pytest.mark.asyncio
    async def test_no_credentials(self, service):
        result = await service.get_credentials()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_credentials_returns_active_token(self, service):
        await service.store_token("sk-ant-oat01-creds-test")
        result = await service.get_credentials()
        assert result is not None
        assert result["token"] == "sk-ant-oat01-creds-test"

    @pytest.mark.asyncio
    async def test_get_credentials_skips_expired(self, service):
        await service.store_token("sk-ant-oat01-test")
        service._tokens["serving"]["status"] = TokenStatus.EXPIRED.value
        result = await service.get_credentials()
        assert result is None


class TestClearCredentials:
    """Test credential clearing."""

    @pytest.mark.asyncio
    async def test_clear_no_credentials(self, service):
        result = await service.clear_credentials()
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_existing_token(self, service):
        await service.store_token("sk-ant-oat01-clear-test")
        assert (await service.get_status())["authenticated"] is True

        result = await service.clear_credentials()
        assert result is True
        assert (await service.get_status())["authenticated"] is False
        assert (await service.get_status())["status"] == AuthStatus.NOT_CONFIGURED.value

    @pytest.mark.asyncio
    async def test_clear_deletes_from_redis(self, service_with_redis, redis_mock):
        await service_with_redis.store_token("sk-ant-oat01-test")
        redis_mock._redis.hset.reset_mock()

        await service_with_redis.clear_credentials()
        redis_mock._redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_specific_component(self, service):
        await service.store_token("sk-ant-oat01-a", component_id="a")
        await service.store_token("sk-ant-oat01-b", component_id="b")

        result = await service.clear_credentials(component_id="a")
        assert result is True

        # b should still be active
        token_b = await service.get_token("b")
        assert token_b == "sk-ant-oat01-b"
        assert (await service.get_status())["authenticated"] is True


class TestGetStatus:
    """Test status reporting."""

    @pytest.mark.asyncio
    async def test_status_not_configured(self, service):
        status = await service.get_status()
        assert status["status"] == "not_configured"
        assert status["authenticated"] is False

    @pytest.mark.asyncio
    async def test_status_authenticated(self, service):
        await service.store_token("sk-ant-oat01-test")
        status = await service.get_status()
        assert status["status"] == "authenticated"
        assert status["authenticated"] is True
        assert status["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_status_expired(self, service):
        await service.store_token("sk-ant-oat01-test")
        service._tokens["serving"]["status"] = TokenStatus.EXPIRED.value
        service._update_status()

        status = await service.get_status()
        assert status["status"] == "expired"
        assert status["authenticated"] is False


class TestBroadcast:
    """Test SSE broadcast callback."""

    @pytest.mark.asyncio
    async def test_set_broadcast_callback(self, service):
        callback = AsyncMock()
        service.set_broadcast_callback(callback)
        assert service._broadcast_callback is callback

    @pytest.mark.asyncio
    async def test_broadcast_called_on_store(self, service):
        callback = AsyncMock()
        service.set_broadcast_callback(callback)
        await service.store_token("sk-ant-oat01-test")
        callback.assert_called_once()
        args = callback.call_args
        assert args[0][0] == "credentials_refresh"

    @pytest.mark.asyncio
    async def test_no_broadcast_without_callback(self, service):
        # Should not raise
        await service._broadcast_credentials_refresh()


class TestPushTokenToCompute:
    """Test SSE-based token push to compute instances."""

    @pytest.mark.asyncio
    async def test_push_without_callback(self, service):
        await service.store_token("sk-ant-oat01-test", component_id="c1", component_type="compute")
        # No send_event callback set
        result = await service.push_token_to_compute("c1")
        assert result is False

    @pytest.mark.asyncio
    async def test_push_to_connected_compute(self, service):
        send_event = AsyncMock(return_value=True)
        service.set_send_event_callback(send_event)
        await service.store_token("sk-ant-oat01-test", component_id="c1", component_type="compute")

        # push_token_to_compute was already called by store_token for compute type
        send_event.assert_called_once()
        call_args = send_event.call_args
        assert call_args[0][0] == "c1"
        assert call_args[0][1] == "auth_token"
        assert call_args[0][2]["token"] == "sk-ant-oat01-test"
        assert "timestamp" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_push_not_called_for_serving(self, service):
        send_event = AsyncMock(return_value=True)
        service.set_send_event_callback(send_event)
        await service.store_token("sk-ant-oat01-test", component_id="serving", component_type="serving")
        # send_event should NOT be called for serving type
        send_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_nonexistent_component(self, service):
        send_event = AsyncMock(return_value=False)
        service.set_send_event_callback(send_event)
        result = await service.push_token_to_compute("nonexistent")
        assert result is False
        send_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_expired_token(self, service):
        send_event = AsyncMock(return_value=True)
        service.set_send_event_callback(send_event)
        # Store and then expire
        await service.store_token("sk-ant-oat01-test", component_id="c1", component_type="compute")
        send_event.reset_mock()
        service._tokens["c1"]["status"] = TokenStatus.EXPIRED.value

        result = await service.push_token_to_compute("c1")
        assert result is False
        send_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_on_reconnect(self, service):
        """Simulates the reconnect flow: token exists, compute reconnects."""
        send_event = AsyncMock(return_value=True)
        service.set_send_event_callback(send_event)
        await service.store_token("sk-ant-oat01-reconnect", component_id="c1", component_type="compute")
        send_event.reset_mock()

        # Simulate reconnect - push again
        result = await service.push_token_to_compute("c1")
        assert result is True
        send_event.assert_called_once()
        assert send_event.call_args[0][2]["token"] == "sk-ant-oat01-reconnect"


class TestExpiryCheck:
    """Test periodic expiry checking."""

    @pytest.mark.asyncio
    async def test_check_expiry_marks_expired(self, service):
        await service.store_token("sk-ant-oat01-test")
        # Set expiry to the past
        service._tokens["serving"]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()

        await service._check_expiry()
        assert service._tokens["serving"]["status"] == TokenStatus.EXPIRED.value
        assert (await service.get_status())["status"] == AuthStatus.EXPIRED.value

    @pytest.mark.asyncio
    async def test_check_expiry_keeps_valid(self, service):
        await service.store_token("sk-ant-oat01-test")
        # Expiry is ~365 days in the future by default
        await service._check_expiry()
        assert service._tokens["serving"]["status"] == TokenStatus.ACTIVE.value
        assert (await service.get_status())["status"] == AuthStatus.AUTHENTICATED.value

    @pytest.mark.asyncio
    async def test_check_expiry_saves_to_redis(self, service_with_redis, redis_mock):
        await service_with_redis.store_token("sk-ant-oat01-test")
        service_with_redis._tokens["serving"]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        redis_mock._redis.hset.reset_mock()

        await service_with_redis._check_expiry()
        redis_mock._redis.hset.assert_called_once()


class TestShutdown:
    """Test service shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_clean(self, service):
        await service.initialize()
        await service.shutdown()
        assert service._monitor_task is None

    @pytest.mark.asyncio
    async def test_shutdown_without_initialize(self, service):
        # Should not raise
        await service.shutdown()
        assert service._monitor_task is None


class TestGetTokenInfo:
    """Test token info retrieval (no raw token)."""

    def test_token_info_not_found(self, service):
        assert service.get_token_info("nonexistent") is None

    @pytest.mark.asyncio
    async def test_token_info_found(self, service):
        await service.store_token("sk-ant-oat01-test", component_id="c1", component_type="compute")
        info = service.get_token_info("c1")
        assert info is not None
        assert info["component_id"] == "c1"
        assert info["status"] == TokenStatus.ACTIVE.value
        assert info["component_type"] == "compute"
        assert info["authorized_at"] is not None
        assert info["expires_at"] is not None
        assert "token" not in info  # Raw token must NOT be returned


class TestListTokens:
    """Test listing all token metadata."""

    def test_list_empty(self, service):
        assert service.list_tokens() == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, service):
        await service.store_token("sk-ant-oat01-a", component_id="serving")
        await service.store_token("sk-ant-oat01-b", component_id="compute-1", component_type="compute")
        items = service.list_tokens()
        assert len(items) == 2
        ids = {item["component_id"] for item in items}
        assert ids == {"serving", "compute-1"}
        for item in items:
            assert "token" not in item


class TestSystemAuthStatus:
    """Test system-level auth overview."""

    def test_empty(self, service):
        status = service.get_system_auth_status()
        assert status["serving_authorized"] is False
        assert status["compute_authorized"] == 0
        assert status["compute_unauthorized"] == 0
        assert status["tokens_expiring_soon"] == 0

    @pytest.mark.asyncio
    async def test_serving_authorized(self, service):
        await service.store_token("sk-ant-oat01-test")
        status = service.get_system_auth_status()
        assert status["serving_authorized"] is True

    @pytest.mark.asyncio
    async def test_compute_counts(self, service):
        await service.store_token("sk-ant-oat01-a", component_id="c1", component_type="compute")
        await service.store_token("sk-ant-oat01-b", component_id="c2", component_type="compute")
        # Manually expire one
        service._tokens["c2"]["status"] = TokenStatus.EXPIRED.value

        status = service.get_system_auth_status()
        assert status["compute_authorized"] == 1
        assert status["compute_unauthorized"] == 1

    @pytest.mark.asyncio
    async def test_expiring_soon(self, service):
        await service.store_token("sk-ant-oat01-test")
        # Set expiry to 15 days from now (within 30-day threshold)
        service._tokens["serving"]["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(days=15)
        ).isoformat()

        status = service.get_system_auth_status()
        assert status["tokens_expiring_soon"] == 1


class TestRedisKey:
    """Test Redis key generation."""

    def test_redis_key_with_prefix(self, service_with_redis):
        key = service_with_redis._redis_key("serving")
        assert key == "claudevn:auth:serving"

    def test_redis_key_without_redis(self, service):
        key = service._redis_key("test-id")
        assert key == "claudevn:auth:test-id"


class TestRegistryAuthStatusSync:
    """Test synchronization of auth_status between AuthManager and Registry."""

    @pytest.mark.asyncio
    async def test_store_compute_token_updates_registry(self, service):
        """When storing a compute token, registry auth_status should be updated to AUTHORIZED."""
        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_registry = AsyncMock()
            mock_registry.update_auth_status = AsyncMock()
            mock_get_registry.return_value = mock_registry

            result = await service.store_token(
                "sk-ant-oat01-test",
                component_id="compute-001",
                component_type="compute"
            )

            # Verify registry was updated
            mock_registry.update_auth_status.assert_called_once()
            call_args = mock_registry.update_auth_status.call_args
            assert call_args[0][0] == "compute-001"
            # Verify auth_status is AUTHORIZED
            from models.compute import ComputeAuthStatus
            assert call_args[0][1] == ComputeAuthStatus.AUTHORIZED
            # Verify expires_at was passed
            assert call_args[1]["auth_expires_at"] is not None

    @pytest.mark.asyncio
    async def test_store_serving_token_skips_registry(self, service):
        """When storing a serving token, registry should NOT be updated."""
        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_registry = AsyncMock()
            mock_registry.update_auth_status = AsyncMock()
            mock_get_registry.return_value = mock_registry

            await service.store_token(
                "sk-ant-oat01-test",
                component_id="serving",
                component_type="serving"
            )

            # Verify registry was NOT called
            mock_registry.update_auth_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_compute_token_updates_registry(self, service):
        """When clearing a compute token, registry auth_status should be updated to UNAUTHORIZED."""
        # First store a compute token
        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_registry = AsyncMock()
            mock_registry.update_auth_status = AsyncMock()
            mock_get_registry.return_value = mock_registry

            await service.store_token(
                "sk-ant-oat01-test",
                component_id="compute-001",
                component_type="compute"
            )
            mock_registry.update_auth_status.reset_mock()

            # Now clear it
            await service.clear_credentials(component_id="compute-001")

            # Verify registry was updated to UNAUTHORIZED
            mock_registry.update_auth_status.assert_called_once()
            call_args = mock_registry.update_auth_status.call_args
            assert call_args[0][0] == "compute-001"
            from models.compute import ComputeAuthStatus
            assert call_args[0][1] == ComputeAuthStatus.UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_clear_serving_token_skips_registry(self, service):
        """When clearing a serving token, registry should NOT be updated."""
        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_registry = AsyncMock()
            mock_registry.update_auth_status = AsyncMock()
            mock_get_registry.return_value = mock_registry

            await service.store_token("sk-ant-oat01-test", component_id="serving")
            mock_registry.update_auth_status.reset_mock()

            await service.clear_credentials(component_id="serving")

            # Verify registry was NOT called
            mock_registry.update_auth_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_registry_update_handles_no_registry(self, service):
        """Should not fail if registry is None."""
        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_get_registry.return_value = None

            # Should not raise
            result = await service.store_token(
                "sk-ant-oat01-test",
                component_id="compute-001",
                component_type="compute"
            )
            assert result["status"] == AuthStatus.AUTHENTICATED.value

    @pytest.mark.asyncio
    async def test_initialize_syncs_existing_compute_tokens(self, service_with_redis, redis_mock):
        """On initialization, existing compute tokens should sync with registry."""
        # Mock Redis to return existing compute token
        redis_mock._redis.scan = AsyncMock(return_value=(0, [b"claudevn:auth:compute-001"]))
        redis_mock._redis.hgetall = AsyncMock(return_value={
            b"token": b"sk-ant-oat01-test",
            b"component_type": b"compute",
            b"authorized_at": b"2026-01-01T00:00:00+00:00",
            b"expires_at": b"2027-01-01T00:00:00+00:00",
            b"status": b"active",
        })

        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_registry = AsyncMock()
            mock_registry.update_auth_status = AsyncMock()
            mock_get_registry.return_value = mock_registry

            await service_with_redis.initialize()

            try:
                # Verify registry was synced on startup
                mock_registry.update_auth_status.assert_called_once()
                call_args = mock_registry.update_auth_status.call_args
                assert call_args[0][0] == "compute-001"
                from models.compute import ComputeAuthStatus
                assert call_args[0][1] == ComputeAuthStatus.AUTHORIZED
            finally:
                await service_with_redis.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_syncs_expired_tokens_as_unauthorized(self, service_with_redis, redis_mock):
        """Expired tokens should sync as UNAUTHORIZED on initialization."""
        redis_mock._redis.scan = AsyncMock(return_value=(0, [b"claudevn:auth:compute-002"]))
        redis_mock._redis.hgetall = AsyncMock(return_value={
            b"token": b"sk-ant-oat01-expired",
            b"component_type": b"compute",
            b"authorized_at": b"2025-01-01T00:00:00+00:00",
            b"expires_at": b"2025-06-01T00:00:00+00:00",
            b"status": b"expired",
        })

        with patch("services.registry_service.get_compute_registry") as mock_get_registry:
            mock_registry = AsyncMock()
            mock_registry.update_auth_status = AsyncMock()
            mock_get_registry.return_value = mock_registry

            await service_with_redis.initialize()

            try:
                # Verify expired token synced as UNAUTHORIZED
                mock_registry.update_auth_status.assert_called_once()
                call_args = mock_registry.update_auth_status.call_args
                assert call_args[0][0] == "compute-002"
                from models.compute import ComputeAuthStatus
                assert call_args[0][1] == ComputeAuthStatus.UNAUTHORIZED
            finally:
                await service_with_redis.shutdown()


class TestLazyRedisCheck:
    """Test lazy Redis check when status is NOT_CONFIGURED."""

    @pytest.mark.asyncio
    async def test_lazy_check_detects_imported_credentials(self, service_with_redis, redis_mock):
        """get_status detects externally-imported credentials on first poll."""
        # Service starts NOT_CONFIGURED with no cached tokens
        assert service_with_redis._status == AuthStatus.NOT_CONFIGURED
        assert len(service_with_redis._tokens) == 0

        # Simulate external import: Redis now has a serving token
        redis_mock._redis.exists = AsyncMock(return_value=1)
        redis_mock._redis.scan = AsyncMock(return_value=(0, [b"claudevn:auth:serving"]))
        redis_mock._redis.hgetall = AsyncMock(return_value={
            b"token": b"sk-ant-oat01-imported",
            b"component_type": b"serving",
            b"authorized_at": b"2026-02-24T00:00:00+00:00",
            b"expires_at": b"2027-02-24T00:00:00+00:00",
            b"status": b"active",
        })

        # get_status should auto-detect the imported token
        status = await service_with_redis.get_status()
        assert status["status"] == AuthStatus.AUTHENTICATED.value
        assert status["authenticated"] is True

    @pytest.mark.asyncio
    async def test_lazy_check_skips_when_already_authenticated(self, service_with_redis, redis_mock):
        """No Redis check when already authenticated."""
        await service_with_redis.store_token("sk-ant-oat01-existing")
        redis_mock._redis.exists = AsyncMock()

        status = await service_with_redis.get_status()
        assert status["authenticated"] is True
        # exists should NOT have been called (skipped because already authenticated)
        redis_mock._redis.exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_lazy_check_skips_without_redis(self, service):
        """No lazy check when Redis is not configured."""
        status = await service.get_status()
        assert status["status"] == AuthStatus.NOT_CONFIGURED.value
        # Should not raise - gracefully handles no Redis

    @pytest.mark.asyncio
    async def test_lazy_check_no_keys_in_redis(self, service_with_redis, redis_mock):
        """Stays NOT_CONFIGURED when Redis has no auth keys."""
        redis_mock._redis.exists = AsyncMock(return_value=0)

        status = await service_with_redis.get_status()
        assert status["status"] == AuthStatus.NOT_CONFIGURED.value
        assert status["authenticated"] is False

    @pytest.mark.asyncio
    async def test_lazy_check_handles_redis_error(self, service_with_redis, redis_mock):
        """Gracefully handles Redis errors during lazy check."""
        redis_mock._redis.exists = AsyncMock(side_effect=ConnectionError("Redis down"))

        # Should not raise
        status = await service_with_redis.get_status()
        assert status["status"] == AuthStatus.NOT_CONFIGURED.value


class TestRefreshFromRedis:
    """Test explicit refresh_from_redis method."""

    @pytest.mark.asyncio
    async def test_refresh_loads_new_tokens(self, service_with_redis, redis_mock):
        """refresh_from_redis picks up externally-imported credentials."""
        redis_mock._redis.scan = AsyncMock(return_value=(0, [b"claudevn:auth:serving"]))
        redis_mock._redis.hgetall = AsyncMock(return_value={
            b"token": b"sk-ant-oat01-refreshed",
            b"component_type": b"serving",
            b"authorized_at": b"2026-02-24T00:00:00+00:00",
            b"expires_at": b"2027-02-24T00:00:00+00:00",
            b"status": b"active",
        })

        result = await service_with_redis.refresh_from_redis()
        assert result["status"] == AuthStatus.AUTHENTICATED.value
        assert result["authenticated"] is True
        assert result["tokens_loaded"] == 1

    @pytest.mark.asyncio
    async def test_refresh_applies_serving_token_to_env(self, service_with_redis, redis_mock):
        """refresh_from_redis applies serving token to process environment."""
        redis_mock._redis.scan = AsyncMock(return_value=(0, [b"claudevn:auth:serving"]))
        redis_mock._redis.hgetall = AsyncMock(return_value={
            b"token": b"sk-ant-oat01-env-test",
            b"component_type": b"serving",
            b"authorized_at": b"2026-02-24T00:00:00+00:00",
            b"expires_at": b"2027-02-24T00:00:00+00:00",
            b"status": b"active",
        })

        with patch.object(service_with_redis, "_apply_token_to_env") as mock_apply:
            await service_with_redis.refresh_from_redis()
            mock_apply.assert_called_once_with("sk-ant-oat01-env-test")

    @pytest.mark.asyncio
    async def test_refresh_returns_not_configured_when_empty(self, service_with_redis, redis_mock):
        """refresh_from_redis returns NOT_CONFIGURED when Redis is empty."""
        redis_mock._redis.scan = AsyncMock(return_value=(0, []))

        result = await service_with_redis.refresh_from_redis()
        assert result["status"] == AuthStatus.NOT_CONFIGURED.value
        assert result["authenticated"] is False
        assert result["tokens_loaded"] == 0

    @pytest.mark.asyncio
    async def test_refresh_without_redis(self, service):
        """refresh_from_redis works gracefully without Redis."""
        result = await service.refresh_from_redis()
        assert result["status"] == AuthStatus.NOT_CONFIGURED.value
        assert result["tokens_loaded"] == 0
