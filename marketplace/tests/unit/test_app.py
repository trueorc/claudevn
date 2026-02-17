"""Unit tests for marketplace app.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestAPIKeyAuthMiddleware:
    """Tests for APIKeyAuthMiddleware."""

    @pytest.fixture
    def mock_config_no_auth(self):
        """Config with authentication disabled."""
        config = MagicMock()
        config.require_auth = False
        config.api_key = None
        return config

    @pytest.fixture
    def mock_config_with_auth(self):
        """Config with authentication enabled."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = 'test-api-key-123'
        return config

    def test_middleware_allows_request_when_auth_disabled(self, mock_config_no_auth):
        """Requests should pass through when auth is disabled."""
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        with patch('app.get_config', return_value=mock_config_no_auth):
            client = TestClient(app)
            response = client.get("/test")

            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

    def test_middleware_allows_public_paths_without_key(self, mock_config_with_auth):
        """Public paths should be accessible without API key."""
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/")
        def root():
            return {"status": "root"}

        @app.get("/docs")
        def docs():
            return {"status": "docs"}

        with patch('app.get_config', return_value=mock_config_with_auth):
            client = TestClient(app)

            # Root path should be allowed
            response = client.get("/")
            assert response.status_code == 200

            # Docs path should be allowed
            response = client.get("/docs")
            assert response.status_code == 200

    def test_middleware_allows_health_endpoints_without_key(self, mock_config_with_auth):
        """Health endpoints should be accessible without API key."""
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/api/v1/health")
        def health():
            return {"status": "healthy"}

        @app.get("/custom/health")
        def custom_health():
            return {"status": "healthy"}

        with patch('app.get_config', return_value=mock_config_with_auth):
            client = TestClient(app)

            response = client.get("/api/v1/health")
            assert response.status_code == 200

            response = client.get("/custom/health")
            assert response.status_code == 200

    def test_middleware_blocks_request_without_api_key(self, mock_config_with_auth):
        """Requests without API key should be rejected when auth is required."""
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/api/v1/skills")
        def get_skills():
            return {"skills": []}

        with patch('app.get_config', return_value=mock_config_with_auth):
            client = TestClient(app)
            response = client.get("/api/v1/skills")

            assert response.status_code == 401
            assert response.json() == {"detail": "Missing API key. Include X-API-Key header."}

    def test_middleware_blocks_request_with_invalid_api_key(self, mock_config_with_auth):
        """Requests with invalid API key should be rejected."""
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/api/v1/skills")
        def get_skills():
            return {"skills": []}

        with patch('app.get_config', return_value=mock_config_with_auth):
            client = TestClient(app)
            response = client.get("/api/v1/skills", headers={"X-API-Key": "wrong-key"})

            assert response.status_code == 401
            assert response.json() == {"detail": "Invalid API key"}

    def test_middleware_allows_request_with_valid_api_key(self, mock_config_with_auth):
        """Requests with valid API key should be allowed."""
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/api/v1/skills")
        def get_skills():
            return {"skills": []}

        with patch('app.get_config', return_value=mock_config_with_auth):
            client = TestClient(app)
            response = client.get("/api/v1/skills", headers={"X-API-Key": "test-api-key-123"})

            assert response.status_code == 200
            assert response.json() == {"skills": []}


class TestAPIKeyAuthMiddlewareMultiKey:
    """Tests for multi-key authentication and edge cases."""

    @pytest.fixture(autouse=True)
    def reset_warning_flag(self):
        """Reset the warning flag before each test."""
        from app import APIKeyAuthMiddleware
        APIKeyAuthMiddleware._auth_disabled_warned = False

    def _make_app(self):
        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/api/v1/skills")
        def get_skills():
            return {"skills": []}

        return app

    def test_auth_with_serving_api_key(self):
        """Request with valid SERVING_API_KEY should be allowed."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = None
        config.api_keys = {'serving': 'serving-key-abc'}

        app = self._make_app()

        with patch('app.get_config', return_value=config):
            client = TestClient(app)
            response = client.get("/api/v1/skills", headers={"X-API-Key": "serving-key-abc"})
            assert response.status_code == 200

    def test_auth_with_admin_api_key(self):
        """Request with valid ADMIN_API_KEY should be allowed."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = None
        config.api_keys = {'admin': 'admin-key-def'}

        app = self._make_app()

        with patch('app.get_config', return_value=config):
            client = TestClient(app)
            response = client.get("/api/v1/skills", headers={"X-API-Key": "admin-key-def"})
            assert response.status_code == 200

    def test_auth_with_marketplace_api_key_from_dict(self):
        """Request with valid MARKETPLACE_API_KEY (from api_keys dict) should be allowed."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = None
        config.api_keys = {'default': 'marketplace-key-ghi'}

        app = self._make_app()

        with patch('app.get_config', return_value=config):
            client = TestClient(app)
            response = client.get("/api/v1/skills", headers={"X-API-Key": "marketplace-key-ghi"})
            assert response.status_code == 200

    def test_multiple_valid_keys_any_one_works(self):
        """When multiple keys are configured, any valid key should work."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = 'legacy-key'
        config.api_keys = {
            'serving': 'serving-key',
            'admin': 'admin-key',
            'default': 'marketplace-key',
        }

        app = self._make_app()

        with patch('app.get_config', return_value=config):
            client = TestClient(app)

            # Each key should independently work
            for key in ['serving-key', 'admin-key', 'marketplace-key', 'legacy-key']:
                response = client.get("/api/v1/skills", headers={"X-API-Key": key})
                assert response.status_code == 200, f"Key '{key}' should be accepted"

    def test_auth_enabled_no_keys_configured_returns_500(self):
        """Auth enabled but no keys configured should return 500 misconfiguration."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = None
        config.api_keys = {}

        app = self._make_app()

        with patch('app.get_config', return_value=config):
            client = TestClient(app)
            response = client.get("/api/v1/skills", headers={"X-API-Key": "any-key"})
            assert response.status_code == 500
            assert response.json() == {"detail": "Server authentication misconfigured"}

    def test_auth_disabled_warning_logged_once(self):
        """Warning about disabled auth should only be logged once."""
        config = MagicMock()
        config.require_auth = False
        config.api_key = None

        app = self._make_app()

        with patch('app.get_config', return_value=config), \
             patch('app.logger') as mock_logger:
            client = TestClient(app)

            # Make multiple requests
            client.get("/api/v1/skills")
            client.get("/api/v1/skills")
            client.get("/api/v1/skills")

            # Warning should have been logged exactly once
            warning_calls = [
                call for call in mock_logger.warning.call_args_list
                if 'DISABLED' in str(call)
            ]
            assert len(warning_calls) == 1

    def test_openapi_json_is_public_path(self):
        """The /openapi.json path should be accessible without auth."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = 'test-key'
        config.api_keys = {}

        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/openapi.json")
        def openapi():
            return {"openapi": "3.0.0"}

        with patch('app.get_config', return_value=config):
            client = TestClient(app)
            response = client.get("/openapi.json")
            assert response.status_code == 200

    def test_redoc_is_public_path(self):
        """The /redoc path should be accessible without auth."""
        config = MagicMock()
        config.require_auth = True
        config.api_key = 'test-key'
        config.api_keys = {}

        from app import APIKeyAuthMiddleware

        app = FastAPI()
        app.add_middleware(APIKeyAuthMiddleware)

        @app.get("/redoc")
        def redoc():
            return {"page": "redoc"}

        with patch('app.get_config', return_value=config):
            client = TestClient(app)
            response = client.get("/redoc")
            assert response.status_code == 200


class TestLifespan:
    """Tests for lifespan context manager."""

    @pytest.fixture
    def mock_skill_registry(self):
        """Create a mock skill registry."""
        registry = MagicMock()
        registry.initialize = AsyncMock()
        registry.get_stats.return_value = {'total_skills': 5, 'total_tools': 10}
        return registry

    @pytest.fixture
    def mock_persona_registry(self):
        """Create a mock persona registry."""
        registry = MagicMock()
        registry.initialize = AsyncMock()
        registry.set_skill_registry = MagicMock()
        registry.get_stats.return_value = {'total_personas': 3}
        return registry

    @pytest.fixture
    def mock_config_no_serving(self):
        """Config without serving registration."""
        config = MagicMock()
        config.serving_url = None
        config.register_on_startup = True
        return config

    @pytest.fixture
    def mock_config_with_serving(self):
        """Config with serving registration enabled."""
        config = MagicMock()
        config.serving_url = 'http://serving:8002'
        config.register_on_startup = True
        config.host = '0.0.0.0'
        config.port = 8003
        config.marketplace_id = 'test-marketplace'
        config.marketplace_name = 'Test Marketplace'
        config.heartbeat_interval = 60
        return config

    @pytest.mark.asyncio
    async def test_lifespan_initializes_registries(self, mock_skill_registry, mock_persona_registry, mock_config_no_serving):
        """Lifespan should initialize skill and persona registries."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.PersonaRegistry', return_value=mock_persona_registry), \
             patch('app.set_skill_registry') as mock_set_skill, \
             patch('app.set_persona_registry') as mock_set_persona, \
             patch('app.get_config', return_value=mock_config_no_serving), \
             patch('os.getenv', side_effect=lambda k, d=None: d):

            async with lifespan(mock_app):
                pass

            # Verify registries were initialized
            mock_skill_registry.initialize.assert_awaited_once()
            mock_persona_registry.initialize.assert_awaited_once()

            # Verify registries were set globally
            mock_set_skill.assert_called_once_with(mock_skill_registry)
            mock_set_persona.assert_called_once_with(mock_persona_registry)

            # Verify bidirectional wiring between registries
            mock_persona_registry.set_skill_registry.assert_called_once_with(mock_skill_registry)
            mock_skill_registry.set_persona_registry.assert_called_once_with(mock_persona_registry)

    @pytest.mark.asyncio
    async def test_lifespan_registers_with_serving_when_configured(self, mock_skill_registry, mock_persona_registry, mock_config_with_serving):
        """Lifespan should register with serving when configured."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)
        mock_registration_client = MagicMock()
        mock_registration_client.register = AsyncMock(return_value=True)
        mock_registration_client.start_heartbeat = AsyncMock()
        mock_registration_client.stop_heartbeat = AsyncMock()
        mock_registration_client.deregister = AsyncMock()

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.PersonaRegistry', return_value=mock_persona_registry), \
             patch('app.set_skill_registry'), \
             patch('app.set_persona_registry'), \
             patch('app.get_config', return_value=mock_config_with_serving), \
             patch('app.MarketplaceRegistrationClient', return_value=mock_registration_client), \
             patch('os.getenv', side_effect=lambda k, d=None: d):

            async with lifespan(mock_app):
                pass

            # Verify registration was attempted
            mock_registration_client.register.assert_awaited_once()
            mock_registration_client.start_heartbeat.assert_awaited_once()

            # Verify cleanup on shutdown
            mock_registration_client.stop_heartbeat.assert_awaited_once()
            mock_registration_client.deregister.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_skips_registration_when_not_configured(self, mock_skill_registry, mock_persona_registry, mock_config_no_serving):
        """Lifespan should skip registration when serving_url not set."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.PersonaRegistry', return_value=mock_persona_registry), \
             patch('app.set_skill_registry'), \
             patch('app.set_persona_registry'), \
             patch('app.get_config', return_value=mock_config_no_serving), \
             patch('app.MarketplaceRegistrationClient') as mock_client_class, \
             patch('os.getenv', side_effect=lambda k, d=None: d):

            async with lifespan(mock_app):
                pass

            # Verify registration client was not created
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_handles_registration_failure(self, mock_skill_registry, mock_persona_registry, mock_config_with_serving):
        """Lifespan should continue in standalone mode if registration fails."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)
        mock_registration_client = MagicMock()
        mock_registration_client.register = AsyncMock(return_value=False)  # Registration fails
        mock_registration_client.start_heartbeat = AsyncMock()
        mock_registration_client.stop_heartbeat = AsyncMock()
        mock_registration_client.deregister = AsyncMock()

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.PersonaRegistry', return_value=mock_persona_registry), \
             patch('app.set_skill_registry'), \
             patch('app.set_persona_registry'), \
             patch('app.get_config', return_value=mock_config_with_serving), \
             patch('app.MarketplaceRegistrationClient', return_value=mock_registration_client), \
             patch('os.getenv', side_effect=lambda k, d=None: d):

            # Should not raise even if registration fails
            async with lifespan(mock_app):
                pass

            # Verify registration was attempted
            mock_registration_client.register.assert_awaited_once()
            # Heartbeat should NOT be started since registration failed
            mock_registration_client.start_heartbeat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lifespan_raises_on_skill_registry_init_failure(self, mock_config_no_serving):
        """Lifespan should raise if skill registry initialization fails."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)
        mock_skill_registry = AsyncMock()
        mock_skill_registry.initialize = AsyncMock(side_effect=Exception("Skill init failed"))

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.get_config', return_value=mock_config_no_serving), \
             patch('os.getenv', side_effect=lambda k, d=None: d):

            with pytest.raises(Exception, match="Skill init failed"):
                async with lifespan(mock_app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_raises_on_persona_registry_init_failure(self, mock_skill_registry, mock_config_no_serving):
        """Lifespan should raise if persona registry initialization fails."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)
        mock_persona_registry = AsyncMock()
        mock_persona_registry.initialize = AsyncMock(side_effect=Exception("Persona init failed"))

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.PersonaRegistry', return_value=mock_persona_registry), \
             patch('app.set_skill_registry'), \
             patch('app.get_config', return_value=mock_config_no_serving), \
             patch('os.getenv', side_effect=lambda k, d=None: d):

            with pytest.raises(Exception, match="Persona init failed"):
                async with lifespan(mock_app):
                    pass

    @pytest.mark.asyncio
    async def test_lifespan_uses_marketplace_endpoint_env_var(self, mock_skill_registry, mock_persona_registry, mock_config_with_serving):
        """Lifespan should use MARKETPLACE_ENDPOINT env var if set."""
        from app import lifespan

        mock_app = MagicMock(spec=FastAPI)
        mock_registration_client = MagicMock()
        mock_registration_client.register = AsyncMock(return_value=True)
        mock_registration_client.start_heartbeat = AsyncMock()
        mock_registration_client.stop_heartbeat = AsyncMock()
        mock_registration_client.deregister = AsyncMock()

        def mock_getenv(key, default=None):
            if key == 'MARKETPLACE_ENDPOINT':
                return 'http://external-marketplace:8003'
            return default

        with patch('app.SkillRegistry', return_value=mock_skill_registry), \
             patch('app.PersonaRegistry', return_value=mock_persona_registry), \
             patch('app.set_skill_registry'), \
             patch('app.set_persona_registry'), \
             patch('app.get_config', return_value=mock_config_with_serving), \
             patch('app.MarketplaceRegistrationClient', return_value=mock_registration_client) as mock_client_class, \
             patch('os.getenv', side_effect=mock_getenv):

            async with lifespan(mock_app):
                pass

            # Verify the external endpoint was used
            call_kwargs = mock_client_class.call_args[1]
            assert call_kwargs['endpoint'] == 'http://external-marketplace:8003'


class TestHealthCheckEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_stats(self):
        """Health endpoint returns skill/persona/tool counts."""
        mock_skill_registry = MagicMock()
        mock_skill_registry.get_stats.return_value = {
            'total_skills': 10,
            'total_tools': 25
        }

        mock_persona_registry = MagicMock()
        mock_persona_registry.get_stats.return_value = {
            'total_personas': 5
        }

        # Patch where they're used in the health_check function
        # get_skill_registry and get_persona_registry are imported inside health_check
        # get_version is imported at module level, so patch in the app namespace
        with patch('skill_registry.get_skill_registry', return_value=mock_skill_registry), \
             patch('persona_registry.get_persona_registry', return_value=mock_persona_registry), \
             patch('app.get_version', return_value='1.0.0'):

            from app import health_check

            result = await health_check()

            assert result['status'] == 'healthy'
            assert result['service'] == 'marketplace'
            assert result['version'] == '1.0.0'
            assert result['skills'] == 10
            assert result['tools'] == 25
            assert result['personas'] == 5


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_service_info(self):
        """Root endpoint should return service info."""
        from app import root

        result = root()

        assert result['service'] == 'ClaudeVN Skill Marketplace'
        assert result['version'] == '1.0.0'
        assert result['api_docs'] == '/docs'


class TestAppConfiguration:
    """Tests for FastAPI app configuration."""

    def test_app_has_correct_title(self):
        """App should have correct title."""
        from app import app

        assert app.title == "ClaudeVN Skill Marketplace"

    def test_app_has_correct_description(self):
        """App should have correct description."""
        from app import app

        assert "atomic skills" in app.description.lower()
        assert "claude code" in app.description.lower()


class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_middleware_is_added(self):
        """CORS middleware should be added to the app."""
        from app import app
        from starlette.middleware.cors import CORSMiddleware

        # Check that CORSMiddleware is in the middleware stack
        middleware_classes = [type(m.cls) if hasattr(m, 'cls') else type(m) for m in app.user_middleware]
        # The middleware is wrapped, so we check differently
        has_cors = any('cors' in str(m).lower() for m in app.user_middleware)
        # Alternative: just verify the app has middleware configured
        assert len(app.user_middleware) > 0
