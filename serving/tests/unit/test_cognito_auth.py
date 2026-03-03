"""Tests for Cognito JWT verification middleware."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from middleware.cognito_auth import (
    verify_cognito_token,
    get_current_user,
    BYPASS_USER,
    reset_jwk_client,
)
from middleware.cognito_middleware import _is_public_route
from config import CognitoConfig, ServingConfig


class TestBypassMode:
    """Test auth bypass mode for local development."""

    @pytest.mark.asyncio
    async def test_bypass_returns_dev_user(self):
        """In bypass mode, returns hardcoded dev user without token."""
        bypass_config = ServingConfig(
            cognito=CognitoConfig(auth_mode="bypass")
        )
        with patch("middleware.cognito_auth.get_config", return_value=bypass_config):
            request = MagicMock()
            result = await verify_cognito_token(request, credentials=None)
            assert result == BYPASS_USER
            assert result["sub"] == "bypass-dev-user"
            assert result["email"] == "dev@localhost"
            assert "admin" in result["cognito:groups"]

    @pytest.mark.asyncio
    async def test_bypass_ignores_credentials(self):
        """In bypass mode, any credentials are ignored."""
        bypass_config = ServingConfig(
            cognito=CognitoConfig(auth_mode="bypass")
        )
        with patch("middleware.cognito_auth.get_config", return_value=bypass_config):
            request = MagicMock()
            creds = MagicMock()
            creds.credentials = "some-invalid-token"
            result = await verify_cognito_token(request, credentials=creds)
            assert result == BYPASS_USER


class TestCognitoMode:
    """Test Cognito token verification."""

    def setup_method(self):
        reset_jwk_client()

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self):
        """Missing Bearer token raises 401."""
        cognito_config = ServingConfig(
            cognito=CognitoConfig(
                auth_mode="cognito",
                user_pool_id="us-east-1_TestPool",
                app_client_id="test-client",
            )
        )
        with patch("middleware.cognito_auth.get_config", return_value=cognito_config):
            request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await verify_cognito_token(request, credentials=None)
            assert exc_info.value.status_code == 401
            assert "Missing" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        """Invalid token raises 401."""
        cognito_config = ServingConfig(
            cognito=CognitoConfig(
                auth_mode="cognito",
                user_pool_id="us-east-1_TestPool",
                app_client_id="test-client",
            )
        )
        with patch("middleware.cognito_auth.get_config", return_value=cognito_config):
            # Mock _decode_cognito_token to raise
            with patch(
                "middleware.cognito_auth._decode_cognito_token",
                side_effect=ValueError("bad token"),
            ):
                request = MagicMock()
                creds = MagicMock()
                creds.credentials = "invalid-jwt-token"
                with pytest.raises(HTTPException) as exc_info:
                    await verify_cognito_token(request, credentials=creds)
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_payload(self):
        """Valid token returns decoded payload."""
        cognito_config = ServingConfig(
            cognito=CognitoConfig(
                auth_mode="cognito",
                user_pool_id="us-east-1_TestPool",
                app_client_id="test-client",
            )
        )
        expected_payload = {
            "sub": "user-123",
            "email": "user@example.com",
            "cognito:groups": ["admin"],
        }
        with patch("middleware.cognito_auth.get_config", return_value=cognito_config):
            with patch(
                "middleware.cognito_auth._decode_cognito_token",
                return_value=expected_payload,
            ):
                request = MagicMock()
                creds = MagicMock()
                creds.credentials = "valid-jwt-token"
                result = await verify_cognito_token(request, credentials=creds)
                assert result == expected_payload


class TestGetCurrentUser:
    """Test get_current_user dependency."""

    def test_passes_through_payload(self):
        payload = {"sub": "user-1", "email": "a@b.com", "cognito:groups": []}
        result = get_current_user(token_payload=payload)
        assert result == payload


class TestPublicRoutes:
    """Test public route detection."""

    @pytest.mark.parametrize("path", [
        "/api/v1/health",
        "/api/v1/compute/connect",
        "/api/v1/compute/register",
        "/api/v1/compute/refresh-credentials",
        "/api/v1/mcp/tools/call",
        "/api/v1/mcp/status",
        "/api/v1/auth/credentials",
        "/api/v1/auth/cognito-config",
        "/api/v1/auth/token",
        "/api/v1/auth/status",
        "/api/v1/marketplace/register",
        "/health",
    ])
    def test_public_routes_detected(self, path):
        assert _is_public_route(path) is True

    @pytest.mark.parametrize("path", [
        "/api/v1/compute",
        "/api/v1/compute/search/by-project/abc",
        "/api/v1/work/items",
        "/api/v1/skills",
        "/api/v1/agents",
        "/api/v1/projects",
        "/api/v1/goals",
        "/api/v1/users",
    ])
    def test_protected_routes_detected(self, path):
        assert _is_public_route(path) is False

    @pytest.mark.parametrize("path", [
        "/",
        "/login",
        "/static/app.js",
        "/index.html",
    ])
    def test_non_api_routes_are_public(self, path):
        """Non-API routes (frontend static files) are always public."""
        assert _is_public_route(path) is True
