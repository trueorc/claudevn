"""Unit tests for SSE event client registration before connection.

Tests that compute instances register with Serving before establishing
SSE connection for instant UI visibility (issue #791).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import httpx

from services.sse_event_client import SSEEventClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for HTTP requests."""
    client = MagicMock()
    client.post = AsyncMock()
    client.stream = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


@pytest.fixture
def sse_client():
    """Create an SSE event client for testing."""
    return SSEEventClient(
        serving_url="http://serving:8002",
        compute_id="compute-001",
        api_key="test-key",
        capabilities=["agent-a", "agent-b"],
        resources={"cpu": 4, "memory": 16},
        reconnect_delay=1,
        max_reconnect_delay=5,
    )


# =============================================================================
# Registration Before Connection Tests
# =============================================================================


class TestSSEClientRegistration:
    """Test SSE client registration before connection."""

    @pytest.mark.asyncio
    async def test_start_calls_register_before_connect(self, sse_client):
        """start() should call _register() before establishing SSE connection."""
        call_order = []

        async def mock_register():
            call_order.append("register")
            return True

        async def mock_connection_loop():
            call_order.append("connection_loop")
            # Immediately stop to prevent infinite loop
            sse_client._running = False

        with patch.object(sse_client, "_register", side_effect=mock_register):
            with patch.object(
                sse_client, "_connection_loop", side_effect=mock_connection_loop
            ):
                await sse_client.start()
                # Wait for the background task to complete
                if sse_client._task:
                    await sse_client._task

        # Verify _register was called before _connection_loop
        assert call_order == ["register", "connection_loop"]

    @pytest.mark.asyncio
    async def test_register_posts_to_correct_endpoint(self, sse_client):
        """_register() should POST to /api/v1/compute/register."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        assert result is True
        assert mock_client.post.called

        # Verify endpoint
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://serving:8002/api/v1/compute/register"

    @pytest.mark.asyncio
    async def test_register_sends_correct_payload(self, sse_client):
        """_register() should send correct registration payload."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        # Verify payload structure
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]

        assert payload["instance_id"] == "compute-001"
        assert payload["name"] == "Compute compute-001"
        assert payload["endpoint"] == "sse"
        assert payload["capabilities"]["agents"] == ["agent-a", "agent-b"]
        assert payload["metadata"]["connection_type"] == "sse"
        assert payload["metadata"]["pre_registered"] is True

    @pytest.mark.asyncio
    async def test_register_includes_auth_header(self, sse_client):
        """_register() should include Authorization header with API key."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        # Verify auth header
        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]

        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_register_success_returns_true(self, sse_client):
        """_register() should return True on successful registration (201)."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        assert result is True

    @pytest.mark.asyncio
    async def test_register_already_registered_returns_true(self, sse_client):
        """_register() should return True if already registered (400)."""
        mock_response = MagicMock()
        mock_response.status_code = 400

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        # Already registered is OK - backward compatibility
        assert result is True


# =============================================================================
# Registration Failure Handling Tests
# =============================================================================


class TestRegistrationFailureHandling:
    """Test graceful handling of registration failures."""

    @pytest.mark.asyncio
    async def test_register_failure_returns_false(self, sse_client):
        """_register() should return False on server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        assert result is False

    @pytest.mark.asyncio
    async def test_register_network_error_returns_false(self, sse_client):
        """_register() should return False on network error."""
        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            # Exception raised during __aenter__
            mock_client_class.side_effect = httpx.ConnectError("Connection failed")

            result = await sse_client._register()

        assert result is False

    @pytest.mark.asyncio
    async def test_register_timeout_returns_false(self, sse_client):
        """_register() should return False on timeout."""
        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            # Exception raised during __aenter__
            mock_client_class.side_effect = httpx.TimeoutException("Timeout")

            result = await sse_client._register()

        assert result is False

    @pytest.mark.asyncio
    async def test_sse_connection_continues_after_register_failure(self, sse_client):
        """SSE connection should continue even if registration fails."""
        async def mock_register_fail():
            return False  # Registration failed

        call_order = []

        async def mock_connection_loop():
            call_order.append("connection_loop")
            sse_client._running = False

        with patch.object(sse_client, "_register", side_effect=mock_register_fail):
            with patch.object(
                sse_client, "_connection_loop", side_effect=mock_connection_loop
            ):
                await sse_client.start()
                # Wait for the background task to complete
                if sse_client._task:
                    await sse_client._task

        # Verify connection loop still ran despite registration failure
        assert "connection_loop" in call_order


# =============================================================================
# Registration Without API Key Tests
# =============================================================================


class TestRegistrationWithoutAPIKey:
    """Test registration when API key is not provided."""

    @pytest.mark.asyncio
    async def test_register_without_api_key_omits_auth_header(self):
        """_register() should omit Authorization header if no API key."""
        client = SSEEventClient(
            serving_url="http://serving:8002",
            compute_id="compute-001",
            api_key="",  # No API key
            capabilities=["agent-a"],
            resources={},
        )

        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await client._register()

        # Verify no Authorization header
        call_args = mock_client.post.call_args
        headers = call_args[1]["headers"]

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility with existing compute instances."""

    @pytest.mark.asyncio
    async def test_existing_instances_not_double_registered(self, sse_client):
        """Already registered instances should not be registered again."""
        # Simulate instance already registered (400 response)
        mock_response = MagicMock()
        mock_response.status_code = 400

        with patch("services.sse_event_client.httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await sse_client._register()

        # Should still return True (backward compatible)
        assert result is True


# =============================================================================
# Integration with start() Tests
# =============================================================================


class TestStartIntegration:
    """Test integration of registration with start() method."""

    @pytest.mark.asyncio
    async def test_start_sets_running_after_register(self, sse_client):
        """start() should set _running=True after registration."""
        async def mock_register():
            return True

        async def mock_connection_loop():
            # Check that _running is True when connection loop starts
            assert sse_client._running is True
            sse_client._running = False  # Stop immediately

        with patch.object(sse_client, "_register", side_effect=mock_register):
            with patch.object(
                sse_client, "_connection_loop", side_effect=mock_connection_loop
            ):
                await sse_client.start()
                # Wait for the background task to complete
                if sse_client._task:
                    await sse_client._task

        # Verify _running was set to False by mock
        assert sse_client._running is False

    @pytest.mark.asyncio
    async def test_start_only_registers_once(self, sse_client):
        """start() should only register once, not on reconnections."""
        register_count = 0

        async def mock_register():
            nonlocal register_count
            register_count += 1
            return True

        async def mock_connection_loop():
            sse_client._running = False

        with patch.object(sse_client, "_register", side_effect=mock_register):
            with patch.object(
                sse_client, "_connection_loop", side_effect=mock_connection_loop
            ):
                await sse_client.start()

        # Should only register once on start
        assert register_count == 1

    @pytest.mark.asyncio
    async def test_multiple_start_calls_dont_double_register(self, sse_client):
        """Calling start() multiple times should not double-register."""
        register_count = 0

        async def mock_register():
            nonlocal register_count
            register_count += 1
            return True

        async def mock_connection_loop():
            sse_client._running = False

        with patch.object(sse_client, "_register", side_effect=mock_register):
            with patch.object(
                sse_client, "_connection_loop", side_effect=mock_connection_loop
            ):
                await sse_client.start()

                # Try to start again
                sse_client._running = False
                await sse_client.start()

        # Should register twice (once per start call)
        assert register_count == 2
