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


# =============================================================================
# Multi-Marketplace Resolution Tests
# =============================================================================

# =============================================================================
# Test: Fallback Normalization
# =============================================================================

class TestFallbackNormalization:
    """Test that fallback persona data is normalized to Skill model shape."""

    def test_normalize_to_skill_adds_missing_fields(self):
        """Test normalization adds missing Skill model fields."""
        persona = {"id": "test", "name": "Test Persona", "instructions": "Do stuff."}
        normalized = MarketplaceClient._normalize_to_skill(persona)

        assert normalized["specialized_tools"] == []
        assert normalized["tags"] == []
        assert normalized["conflicts_with"] == []
        assert normalized["constraints"] == []
        assert normalized["dependencies"] == []
        assert normalized["instructions"] == "Do stuff."
        assert normalized["id"] == "test"

    def test_normalize_to_skill_preserves_existing_fields(self):
        """Test normalization doesn't overwrite existing fields."""
        persona = {
            "id": "test",
            "name": "Test",
            "specialized_tools": ["tool-a"],
            "constraints": ["No refactoring"],
            "dependencies": ["dep-1"],
        }
        normalized = MarketplaceClient._normalize_to_skill(persona)

        assert normalized["specialized_tools"] == ["tool-a"]
        assert normalized["constraints"] == ["No refactoring"]
        assert normalized["dependencies"] == ["dep-1"]

    def test_get_fallback_skill_returns_normalized(self):
        """Test _get_fallback_skill returns normalized dict with all Skill fields."""
        client = MarketplaceClient(base_url="http://localhost:8003", cache_ttl=0)
        # Simulate a minimal persona loaded from YAML
        client._fallback_personas["test-skill"] = {
            "id": "test-skill",
            "name": "Test",
            "instructions": "Test instructions.",
        }

        result = client._get_fallback_skill("test-skill")

        assert result is not None
        assert result["id"] == "test-skill"
        assert result["instructions"] == "Test instructions."
        assert result["specialized_tools"] == []
        assert result["dependencies"] == []
        assert result["constraints"] == []
        assert result["conflicts_with"] == []
        assert result["source"] == "fallback"
        assert result["fallback_mode"] is True

    def test_get_fallback_skill_missing_returns_none(self):
        """Test _get_fallback_skill returns None for unknown skill."""
        client = MarketplaceClient(base_url="http://localhost:8003", cache_ttl=0)
        assert client._get_fallback_skill("nonexistent") is None

    def test_get_fallback_skills_list_normalized(self):
        """Test _get_fallback_skills_list normalizes all skills."""
        client = MarketplaceClient(
            base_url="http://localhost:8003", cache_ttl=0,
            fallback_personas_path="/nonexistent"
        )
        client._fallback_personas = {
            "s1": {"id": "s1", "name": "Skill 1"},
            "s2": {"id": "s2", "name": "Skill 2"},
        }

        result = client._get_fallback_skills_list()

        assert result["total"] == 2
        for skill in result["skills"]:
            assert "dependencies" in skill
            assert "specialized_tools" in skill
            assert "constraints" in skill
            assert skill["fallback_mode"] is True


class TestMultiMarketplaceResolution:
    """Test tier-based skill resolution across multiple marketplaces."""

    @pytest.fixture
    def multi_client(self):
        """Create a client with multiple marketplace endpoints."""
        return MarketplaceClient(
            base_url="http://root-marketplace:8003",
            cache_ttl=0,
            additional_marketplaces=[
                {"url": "http://team-marketplace:8003", "tier": "team", "name": "team-mp"},
                {"url": "http://user-marketplace:8003", "tier": "user", "name": "user-mp"},
            ],
        )

    def test_marketplace_endpoints_initialized(self, multi_client):
        """Test that additional marketplaces are registered."""
        assert len(multi_client._marketplace_endpoints) == 3
        assert multi_client._marketplace_endpoints[0] == (
            "http://root-marketplace:8003", "root", "primary"
        )
        assert multi_client._marketplace_endpoints[1] == (
            "http://team-marketplace:8003", "team", "team-mp"
        )
        assert multi_client._marketplace_endpoints[2] == (
            "http://user-marketplace:8003", "user", "user-mp"
        )

    @pytest.mark.asyncio
    async def test_resolve_skill_most_specific_tier_wins(self, multi_client):
        """Test that the most specific tier (user > team > root) wins."""
        root_skill = {"id": "code-writer", "name": "Root Code Writer", "marketplace_tier": "root"}
        team_skill = {"id": "code-writer", "name": "Team Code Writer", "marketplace_tier": "team"}

        async def mock_fetch(url, tier, name, skill_id):
            if "root" in url:
                return {**root_skill, "marketplace_tier": tier, "marketplace_name": name}
            if "team" in url:
                return {**team_skill, "marketplace_tier": tier, "marketplace_name": name}
            return None

        with patch.object(multi_client, "_fetch_skill_from_endpoint", side_effect=mock_fetch):
            result = await multi_client.resolve_skill("code-writer")

        assert result is not None
        assert result["marketplace_tier"] == "team"

    @pytest.mark.asyncio
    async def test_resolve_skill_user_beats_team(self, multi_client):
        """Test that user tier takes precedence over team tier."""
        async def mock_fetch(url, tier, name, skill_id):
            if "user" in url:
                return {"id": skill_id, "name": "User Skill", "marketplace_tier": tier}
            if "team" in url:
                return {"id": skill_id, "name": "Team Skill", "marketplace_tier": tier}
            return None

        with patch.object(multi_client, "_fetch_skill_from_endpoint", side_effect=mock_fetch):
            result = await multi_client.resolve_skill("code-writer")

        assert result["marketplace_tier"] == "user"

    @pytest.mark.asyncio
    async def test_resolve_skill_falls_back_to_root(self, multi_client):
        """Test fallback to root when skill only exists there."""
        async def mock_fetch(url, tier, name, skill_id):
            if "root" in url:
                return {"id": skill_id, "name": "Root Skill", "marketplace_tier": tier}
            return None

        with patch.object(multi_client, "_fetch_skill_from_endpoint", side_effect=mock_fetch):
            result = await multi_client.resolve_skill("code-writer")

        assert result is not None
        assert result["marketplace_tier"] == "root"

    @pytest.mark.asyncio
    async def test_resolve_skill_returns_none_when_not_found(self, multi_client):
        """Test resolve returns None when no marketplace has the skill."""
        async def mock_fetch(url, tier, name, skill_id):
            return None

        with patch.object(multi_client, "_fetch_skill_from_endpoint", side_effect=mock_fetch):
            result = await multi_client.resolve_skill("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_skills_bulk(self, multi_client):
        """Test bulk skill resolution."""
        async def mock_fetch(url, tier, name, skill_id):
            if skill_id == "code-writer" and "root" in url:
                return {"id": skill_id, "name": "Root Writer", "marketplace_tier": tier}
            if skill_id == "test-writer" and "team" in url:
                return {"id": skill_id, "name": "Team Tester", "marketplace_tier": tier}
            return None

        with patch.object(multi_client, "_fetch_skill_from_endpoint", side_effect=mock_fetch):
            result = await multi_client.resolve_skills(["code-writer", "test-writer"])

        assert result["code-writer"]["name"] == "Root Writer"
        assert result["test-writer"]["name"] == "Team Tester"

    @pytest.mark.asyncio
    async def test_resolve_skills_empty_list(self, multi_client):
        """Test resolve_skills with empty list."""
        result = await multi_client.resolve_skills([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolve_skill_single_marketplace_uses_get_skill(self):
        """Test that single-marketplace client delegates to get_skill."""
        client = MarketplaceClient(base_url="http://localhost:8003", cache_ttl=0)
        assert len(client._marketplace_endpoints) == 1

        with patch.object(client, "get_skill", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": "code-writer", "name": "Writer"}
            result = await client.resolve_skill("code-writer")

        assert result["name"] == "Writer"
        mock_get.assert_called_once_with("code-writer")

    @pytest.mark.asyncio
    async def test_resolve_skill_handles_endpoint_errors(self, multi_client):
        """Test resolve handles individual endpoint failures gracefully."""
        async def mock_fetch(url, tier, name, skill_id):
            if "team" in url:
                raise Exception("Connection refused")
            if "root" in url:
                return {"id": skill_id, "name": "Root Skill", "marketplace_tier": tier}
            return None

        with patch.object(multi_client, "_fetch_skill_from_endpoint", side_effect=mock_fetch):
            result = await multi_client.resolve_skill("code-writer")

        # Should fall back to root despite team error
        assert result["marketplace_tier"] == "root"
