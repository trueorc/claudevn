"""Tests for MarketplaceClient service.

Unit tests using mocked HTTP responses for the MarketplaceClient.
Part of Tier 1 Unit Test Plan (Issue #49).
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import httpx

from services.marketplace_client import (
    MarketplaceClient,
    get_marketplace_client,
    set_marketplace_client,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create a MarketplaceClient for testing with caching disabled."""
    return MarketplaceClient(
        base_url="http://localhost:8003",
        cache_ttl=0  # Disable caching for tests
    )


@pytest.fixture
def mock_response():
    """Create a mock httpx response."""
    def _mock_response(json_data, status_code=200):
        response = MagicMock(spec=httpx.Response)
        response.status_code = status_code
        response.json.return_value = json_data
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=response
            )
        return response
    return _mock_response


# =============================================================================
# Test: Initialization
# =============================================================================

class TestMarketplaceClientInit:
    """Test client initialization."""

    def test_init_default_url(self):
        """Test client initializes with default URL."""
        client = MarketplaceClient()
        assert client.base_url == "http://localhost:8003"
        assert client.api_prefix == "/api/v1"

    def test_init_custom_url(self):
        """Test client initializes with custom URL."""
        client = MarketplaceClient(base_url="http://custom:9000")
        assert client.base_url == "http://custom:9000"

    def test_init_strips_trailing_slash(self):
        """Test client strips trailing slash from URL."""
        client = MarketplaceClient(base_url="http://localhost:8003/")
        assert client.base_url == "http://localhost:8003"


# =============================================================================
# Test: get_skill
# =============================================================================

class TestGetSkill:
    """Test get_skill method."""

    @pytest.mark.asyncio
    async def test_get_skill_success(self, client, mock_response):
        """Test successfully getting a skill."""
        skill_data = {
            "skill_id": "skill-001",
            "name": "Code Writer",
            "description": "Writes code",
            "capabilities": ["python", "javascript"]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response(skill_data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.get_skill("skill-001")

            assert result == skill_data
            mock_instance.get.assert_called_once_with(
                "http://localhost:8003/api/v1/skills/skill-001",
                headers=ANY,
                timeout=ANY
            )

    @pytest.mark.asyncio
    async def test_get_skill_not_found(self, client, mock_response):
        """Test getting a skill that doesn't exist raises error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response({}, status_code=404))
            mock_client.return_value.__aenter__.return_value = mock_instance

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_skill("nonexistent")


# =============================================================================
# Test: search_skills / list_skills
# =============================================================================

class TestListSkills:
    """Test list_skills method."""

    @pytest.mark.asyncio
    async def test_list_skills_no_filters(self, client, mock_response):
        """Test listing all skills without filters."""
        skills_data = {
            "skills": [
                {"skill_id": "skill-001", "name": "Code Writer"},
                {"skill_id": "skill-002", "name": "Debugger"}
            ],
            "total": 2
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response(skills_data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.list_skills()

            assert result == skills_data
            mock_instance.get.assert_called_once_with(
                "http://localhost:8003/api/v1/skills",
                params={},
                headers=ANY,
                timeout=ANY
            )

    @pytest.mark.asyncio
    async def test_list_skills_with_tags(self, client, mock_response):
        """Test listing skills filtered by tags."""
        skills_data = {
            "skills": [{"skill_id": "skill-001", "name": "Code Writer"}],
            "total": 1
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response(skills_data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.list_skills(tags=["python", "backend"])

            assert result == skills_data
            mock_instance.get.assert_called_once_with(
                "http://localhost:8003/api/v1/skills",
                params={"tags": "python,backend"},
                headers=ANY,
                timeout=ANY
            )

    @pytest.mark.asyncio
    async def test_list_skills_empty_result(self, client, mock_response):
        """Test listing skills when none match."""
        skills_data = {"skills": [], "total": 0}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response(skills_data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.list_skills(tags=["nonexistent"])

            assert result["skills"] == []
            assert result["total"] == 0


# =============================================================================
# Test: compose_agent
# =============================================================================

class TestComposeAgent:
    """Test compose_agent method."""

    @pytest.mark.asyncio
    async def test_compose_agent_basic(self, client, mock_response):
        """Test composing an agent with basic parameters."""
        compose_result = {
            "agent_id": "agent-001",
            "skills": ["skill-001"],
            "claude_md": "# Agent\nComposed agent content"
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response(compose_result))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.compose_agent(
                task_id="task-001",
                task_description="Write a function",
                required_capabilities=["python"]
            )

            assert result == compose_result
            call_args = mock_instance.post.call_args
            assert call_args[0][0] == "http://localhost:8003/api/v1/skills/compose"
            payload = call_args[1]["json"]
            assert payload["task"]["task_id"] == "task-001"
            assert payload["task"]["description"] == "Write a function"

    @pytest.mark.asyncio
    async def test_compose_agent_with_skill_ids(self, client, mock_response):
        """Test composing an agent with specific skill IDs."""
        compose_result = {"agent_id": "agent-001", "skills": ["skill-001", "skill-002"]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response(compose_result))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.compose_agent(
                task_id="task-001",
                task_description="Complex task",
                required_capabilities=["python", "testing"],
                skill_ids=["skill-001", "skill-002"]
            )

            call_args = mock_instance.post.call_args
            payload = call_args[1]["json"]
            assert payload["skill_ids"] == ["skill-001", "skill-002"]

    @pytest.mark.asyncio
    async def test_compose_agent_with_context(self, client, mock_response):
        """Test composing an agent with additional context."""
        compose_result = {"agent_id": "agent-001"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response(compose_result))
            mock_client.return_value.__aenter__.return_value = mock_instance

            context = {"project": "claudevn", "priority": "high"}
            result = await client.compose_agent(
                task_id="task-001",
                task_description="Task with context",
                required_capabilities=["python"],
                context=context
            )

            call_args = mock_instance.post.call_args
            payload = call_args[1]["json"]
            assert payload["context"] == context


# =============================================================================
# Test: health_check
# =============================================================================

class TestHealthCheck:
    """Test health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_response):
        """Test successful health check."""
        health_data = {"status": "healthy", "version": "1.0.0"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response(health_data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.health_check()

            assert result == health_data
            mock_instance.get.assert_called_once_with(
                "http://localhost:8003/api/v1/health",
                headers=ANY
            )

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, client, mock_response):
        """Test health check when service is unhealthy."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response({}, status_code=503))
            mock_client.return_value.__aenter__.return_value = mock_instance

            with pytest.raises(httpx.HTTPStatusError):
                await client.health_check()


# =============================================================================
# Test: get_stats
# =============================================================================

class TestGetStats:
    """Test get_stats method."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, client, mock_response):
        """Test getting marketplace statistics."""
        stats_data = {
            "total_skills": 10,
            "total_capabilities": 25,
            "active_agents": 3
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response(stats_data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await client.get_stats()

            assert result == stats_data
            mock_instance.get.assert_called_once_with(
                "http://localhost:8003/api/v1/skills/stats",
                headers=ANY,
                timeout=ANY
            )


# =============================================================================
# Test: Connection Error Handling
# =============================================================================

class TestConnectionErrorHandling:
    """Test connection error handling."""

    @pytest.mark.asyncio
    async def test_connection_error_on_get_returns_fallback(self, client):
        """Test handling connection error on GET request returns fallback if available."""
        # Client has fallback personas loaded
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Non-fallback skill should raise error
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_skill("nonexistent-skill")

    @pytest.mark.asyncio
    async def test_connection_error_on_post(self, client):
        """Test handling connection error on POST request."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            with pytest.raises(httpx.ConnectError):
                await client.compose_agent(
                    task_id="task-001",
                    task_description="Test",
                    required_capabilities=["python"]
                )


# =============================================================================
# Test: Timeout Handling
# =============================================================================

class TestTimeoutHandling:
    """Test timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_on_request_returns_fallback(self, client):
        """Test handling request timeout returns fallback list."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Should return fallback data instead of raising
            result = await client.list_skills()
            assert "skills" in result
            assert result.get("fallback_mode", False) is True

    @pytest.mark.asyncio
    async def test_timeout_on_health_check(self, client):
        """Test handling timeout during health check."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("Health check timed out")
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            with pytest.raises(httpx.TimeoutException):
                await client.health_check()


# =============================================================================
# Test: Global Instance Management
# =============================================================================

class TestGlobalInstance:
    """Test global client instance management."""

    def _reset_config(self):
        """Reset global config state."""
        import config
        config._config = None

    def test_get_marketplace_client_creates_instance(self):
        """Test get_marketplace_client creates instance on first call."""
        # Reset global state
        set_marketplace_client(None)
        self._reset_config()

        with patch.dict("os.environ", {"MARKETPLACE_URL": "http://test:9000"}):
            client = get_marketplace_client()

            assert client is not None
            assert client.base_url == "http://test:9000"

    def test_get_marketplace_client_returns_same_instance(self):
        """Test get_marketplace_client returns same instance."""
        set_marketplace_client(None)
        self._reset_config()

        client1 = get_marketplace_client()
        client2 = get_marketplace_client()

        assert client1 is client2

    def test_set_marketplace_client(self):
        """Test setting a custom marketplace client."""
        set_marketplace_client(None)
        self._reset_config()

        custom_client = MarketplaceClient(base_url="http://custom:7000")
        set_marketplace_client(custom_client)

        retrieved = get_marketplace_client()

        assert retrieved is custom_client
        assert retrieved.base_url == "http://custom:7000"

    def test_get_marketplace_client_default_url(self):
        """Test get_marketplace_client uses default URL when env not set."""
        set_marketplace_client(None)
        self._reset_config()

        with patch.dict("os.environ", {}, clear=True):
            # Remove MARKETPLACE_URL if present
            import os
            os.environ.pop("MARKETPLACE_URL", None)

            client = get_marketplace_client()

            assert client.base_url == "http://localhost:8003"
