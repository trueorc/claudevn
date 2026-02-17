"""Unit tests for MarketplaceRegistrationClient."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from services.registration_client import MarketplaceRegistrationClient


@pytest.fixture
def registration_client():
    """Create a registration client for testing."""
    return MarketplaceRegistrationClient(
        serving_url="http://localhost:8002",
        marketplace_id="test-marketplace",
        marketplace_name="Test Marketplace",
        endpoint="http://localhost:8003",
        version="1.0.0",
        heartbeat_interval=60
    )


class TestMarketplaceRegistrationClientInit:
    """Tests for client initialization."""

    def test_init_sets_properties(self, registration_client):
        """Test that init sets all properties correctly."""
        assert registration_client.serving_url == "http://localhost:8002"
        assert registration_client.marketplace_id == "test-marketplace"
        assert registration_client.marketplace_name == "Test Marketplace"
        assert registration_client.endpoint == "http://localhost:8003"
        assert registration_client.version == "1.0.0"
        assert registration_client.heartbeat_interval == 60
        assert registration_client.is_registered is False
        assert registration_client.heartbeat_task is None

    def test_init_strips_trailing_slash_from_serving_url(self):
        """Test that trailing slash is stripped from serving_url."""
        client = MarketplaceRegistrationClient(
            serving_url="http://localhost:8002/",
            marketplace_id="test",
            marketplace_name="Test",
            endpoint="http://localhost:8003"
        )
        assert client.serving_url == "http://localhost:8002"


class TestUpdateCapabilities:
    """Tests for update_capabilities method."""

    def test_update_capabilities(self, registration_client):
        """Test that capabilities are updated."""
        registration_client.update_capabilities(
            skill_count=10,
            persona_count=5,
            tool_count=25
        )

        assert registration_client.skill_count == 10
        assert registration_client.persona_count == 5
        assert registration_client.tool_count == 25


class TestRegister:
    """Tests for register method."""

    @pytest.mark.asyncio
    async def test_register_success(self, registration_client):
        """Test successful registration."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "status": "registered",
            "marketplace_id": "test-marketplace",
            "heartbeat_interval": 60,
            "heartbeat_endpoint": "/api/v1/marketplaces/test-marketplace/heartbeat"
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await registration_client.register()

            assert result is True
            assert registration_client.is_registered is True
            assert registration_client.heartbeat_endpoint == "/api/v1/marketplaces/test-marketplace/heartbeat"

    @pytest.mark.asyncio
    async def test_register_failure(self, registration_client):
        """Test registration failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await registration_client.register()

            assert result is False
            assert registration_client.is_registered is False

    @pytest.mark.asyncio
    async def test_register_connect_error_returns_false(self, registration_client):
        """Test that connection errors return False (standalone mode)."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            result = await registration_client.register()

            assert result is False
            assert registration_client.is_registered is False


class TestDeregister:
    """Tests for deregister method."""

    @pytest.mark.asyncio
    async def test_deregister_success(self, registration_client):
        """Test successful deregistration."""
        registration_client.is_registered = True

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete = AsyncMock(
                return_value=mock_response
            )

            result = await registration_client.deregister()

            assert result is True
            assert registration_client.is_registered is False

    @pytest.mark.asyncio
    async def test_deregister_not_found_is_success(self, registration_client):
        """Test that 404 is treated as successful deregistration."""
        registration_client.is_registered = True

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete = AsyncMock(
                return_value=mock_response
            )

            result = await registration_client.deregister()

            assert result is True
            assert registration_client.is_registered is False

    @pytest.mark.asyncio
    async def test_deregister_skips_if_not_registered(self, registration_client):
        """Test that deregister skips if not registered locally."""
        registration_client.is_registered = False

        result = await registration_client.deregister()

        assert result is True


class TestSendHeartbeat:
    """Tests for send_heartbeat method."""

    @pytest.mark.asyncio
    async def test_send_heartbeat_success(self, registration_client):
        """Test successful heartbeat."""
        registration_client.is_registered = True
        registration_client.heartbeat_endpoint = "/api/v1/marketplaces/test/heartbeat"
        registration_client.update_capabilities(skill_count=5, persona_count=2, tool_count=10)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await registration_client.send_heartbeat()

            assert result is True

    @pytest.mark.asyncio
    async def test_send_heartbeat_returns_false_if_not_registered(self, registration_client):
        """Test that heartbeat returns False if not registered."""
        registration_client.is_registered = False

        result = await registration_client.send_heartbeat()

        assert result is False

    @pytest.mark.asyncio
    async def test_send_heartbeat_returns_false_if_no_endpoint(self, registration_client):
        """Test that heartbeat returns False if no heartbeat endpoint."""
        registration_client.is_registered = True
        registration_client.heartbeat_endpoint = None

        result = await registration_client.send_heartbeat()

        assert result is False
