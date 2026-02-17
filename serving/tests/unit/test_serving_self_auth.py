"""Tests for serving self-auth: token env application and onboarding flag."""

import json
import os
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from models.auth import AuthStatus, TokenStatus
from services.claude_auth_service import ClaudeAuthService


@pytest.fixture
def tmp_claude_config(tmp_path):
    """Temporary Claude config directory."""
    return str(tmp_path / ".claude")


@pytest.fixture
def auth_service(tmp_claude_config):
    """Create auth service with no Redis (in-memory only)."""
    service = ClaudeAuthService(redis_client=None, claude_config_dir=tmp_claude_config)
    return service


class TestServingTokenEnvApplication:
    """Tests for applying serving token to process environment."""

    @pytest.mark.asyncio
    async def test_store_serving_token_sets_env(self, auth_service):
        result = await auth_service.store_token(
            token="sk-ant-oat01-test-token",
            component_id="serving",
            component_type="serving",
        )

        assert result["status"] == AuthStatus.AUTHENTICATED.value
        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-test-token"

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_store_compute_token_does_not_set_env(self, auth_service):
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

        await auth_service.store_token(
            token="sk-ant-oat01-compute-token",
            component_id="compute-001",
            component_type="compute",
        )

        assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ

    @pytest.mark.asyncio
    async def test_clear_serving_credentials_removes_env(self, auth_service):
        await auth_service.store_token(
            token="sk-ant-oat01-test-token",
            component_id="serving",
        )
        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-test-token"

        cleared = await auth_service.clear_credentials("serving")

        assert cleared is True
        assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ

    @pytest.mark.asyncio
    async def test_clear_compute_credentials_does_not_remove_env(self, auth_service):
        # Set serving token first
        await auth_service.store_token(
            token="sk-ant-oat01-serving-tok",
            component_id="serving",
        )
        # Store compute token
        await auth_service.store_token(
            token="sk-ant-oat01-compute-tok",
            component_id="compute-001",
            component_type="compute",
        )

        # Clear compute - should NOT affect serving env
        await auth_service.clear_credentials("compute-001")
        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-serving-tok"

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_initialize_applies_existing_serving_token(self, auth_service):
        """If serving token is already in cache, initialize should apply it to env."""
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

        # Simulate token already loaded
        auth_service._tokens["serving"] = {
            "token": "sk-ant-oat01-preexisting",
            "status": TokenStatus.ACTIVE.value,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        }

        # Patch _load_from_redis to do nothing (tokens already set)
        auth_service._load_from_redis = AsyncMock()

        await auth_service.initialize()

        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-preexisting"

        # Cleanup
        await auth_service.shutdown()
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_initialize_does_not_apply_expired_token(self, auth_service):
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

        auth_service._tokens["serving"] = {
            "token": "sk-ant-oat01-expired",
            "status": TokenStatus.EXPIRED.value,
        }

        auth_service._load_from_redis = AsyncMock()
        await auth_service.initialize()

        assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ

        await auth_service.shutdown()


class TestOnboardingFlag:
    """Tests for onboarding flag file creation."""

    @pytest.mark.asyncio
    async def test_store_serving_token_writes_onboarding_flag(self, auth_service, tmp_claude_config):
        await auth_service.store_token(
            token="sk-ant-oat01-test-token",
            component_id="serving",
        )

        flag_path = Path(tmp_claude_config) / ".onboarding_complete"
        assert flag_path.exists()

        data = json.loads(flag_path.read_text())
        assert data["source"] == "claudevn_serving"
        assert "completed_at" in data

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_store_compute_token_does_not_write_onboarding(self, auth_service, tmp_claude_config):
        await auth_service.store_token(
            token="sk-ant-oat01-compute-tok",
            component_id="compute-001",
            component_type="compute",
        )

        flag_path = Path(tmp_claude_config) / ".onboarding_complete"
        assert not flag_path.exists()

    @pytest.mark.asyncio
    async def test_onboarding_flag_creates_config_dir(self, auth_service, tmp_claude_config):
        """Config dir should be created if it doesn't exist."""
        assert not Path(tmp_claude_config).exists()

        await auth_service.store_token(
            token="sk-ant-oat01-test-token",
            component_id="serving",
        )

        assert Path(tmp_claude_config).is_dir()

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)


class TestTokenExpiryEnvCleanup:
    """Tests for env cleanup when serving token expires."""

    @pytest.mark.asyncio
    async def test_expiry_check_removes_serving_env(self, auth_service):
        # Store a serving token that is already expired
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        auth_service._tokens["serving"] = {
            "token": "sk-ant-oat01-expired",
            "status": TokenStatus.ACTIVE.value,
            "expires_at": past.isoformat(),
        }
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-expired"

        await auth_service._check_expiry()

        assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ
        assert auth_service._tokens["serving"]["status"] == TokenStatus.EXPIRED.value

    @pytest.mark.asyncio
    async def test_expiry_check_does_not_remove_for_compute(self, auth_service):
        # Store a compute token that is already expired
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        auth_service._tokens["compute-001"] = {
            "token": "sk-ant-oat01-compute-exp",
            "status": TokenStatus.ACTIVE.value,
            "expires_at": past.isoformat(),
        }
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-serving-still-valid"

        await auth_service._check_expiry()

        # Serving env should NOT have been removed
        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == "sk-ant-oat01-serving-still-valid"

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)


class TestGracefulDegradation:
    """Tests for graceful degradation when unauthorized."""

    @pytest.mark.asyncio
    async def test_status_not_configured_by_default(self, auth_service):
        status = auth_service.get_status()
        assert status["status"] == AuthStatus.NOT_CONFIGURED.value
        assert status["authenticated"] is False

    @pytest.mark.asyncio
    async def test_get_token_returns_none_when_not_configured(self, auth_service):
        token = await auth_service.get_token("serving")
        assert token is None

    @pytest.mark.asyncio
    async def test_get_credentials_returns_none_when_not_configured(self, auth_service):
        creds = await auth_service.get_credentials()
        assert creds is None
