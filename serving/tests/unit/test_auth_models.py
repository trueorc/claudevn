"""Tests for auth models."""

import pytest
from pydantic import ValidationError
from models.auth import (
    AuthStatus,
    TokenStatus,
    AuthStatusResponse,
    TokenSubmitRequest,
    TokenSubmitResponse,
    CredentialsResponse,
)


class TestAuthStatus:
    """Test AuthStatus enum."""

    def test_enum_values(self):
        assert AuthStatus.NOT_CONFIGURED == "not_configured"
        assert AuthStatus.AUTHENTICATED == "authenticated"
        assert AuthStatus.EXPIRED == "expired"
        assert AuthStatus.ERROR == "error"

    def test_all_values_exist(self):
        assert len(AuthStatus) == 4


class TestTokenStatus:
    """Test TokenStatus enum."""

    def test_enum_values(self):
        assert TokenStatus.ACTIVE == "active"
        assert TokenStatus.EXPIRED == "expired"
        assert TokenStatus.REVOKED == "revoked"

    def test_all_values_exist(self):
        assert len(TokenStatus) == 3


class TestAuthStatusResponse:
    """Test AuthStatusResponse model."""

    def test_authenticated_response(self):
        resp = AuthStatusResponse(
            status=AuthStatus.AUTHENTICATED,
            authenticated=True,
            expires_at="2026-03-01T00:00:00Z",
        )
        assert resp.status == AuthStatus.AUTHENTICATED
        assert resp.authenticated is True
        assert resp.expires_at == "2026-03-01T00:00:00Z"
        assert resp.message is None

    def test_not_configured_response(self):
        resp = AuthStatusResponse(
            status=AuthStatus.NOT_CONFIGURED,
            authenticated=False,
        )
        assert resp.status == AuthStatus.NOT_CONFIGURED
        assert resp.authenticated is False

    def test_serialization(self):
        resp = AuthStatusResponse(
            status=AuthStatus.NOT_CONFIGURED,
            authenticated=False,
        )
        data = resp.model_dump()
        assert data["status"] == "not_configured"
        assert data["authenticated"] is False


class TestTokenSubmitRequest:
    """Test TokenSubmitRequest model."""

    def test_valid_token(self):
        req = TokenSubmitRequest(token="sk-ant-oat01-test-token-12345")
        assert req.token == "sk-ant-oat01-test-token-12345"
        assert req.component_id == "serving"
        assert req.component_type == "serving"

    def test_custom_component(self):
        req = TokenSubmitRequest(
            token="sk-ant-oat01-test",
            component_id="compute-1",
            component_type="compute",
        )
        assert req.component_id == "compute-1"
        assert req.component_type == "compute"

    def test_invalid_token_prefix(self):
        with pytest.raises(ValidationError) as exc_info:
            TokenSubmitRequest(token="invalid-token")
        assert "sk-ant-oat01-" in str(exc_info.value)

    def test_empty_token(self):
        with pytest.raises(ValidationError):
            TokenSubmitRequest(token="")


class TestTokenSubmitResponse:
    """Test TokenSubmitResponse model."""

    def test_success_response(self):
        resp = TokenSubmitResponse(
            status=AuthStatus.AUTHENTICATED,
            message="Token stored successfully",
            expires_at="2027-02-14T00:00:00Z",
        )
        assert resp.status == AuthStatus.AUTHENTICATED
        assert resp.message == "Token stored successfully"
        assert resp.expires_at == "2027-02-14T00:00:00Z"

    def test_response_without_expiry(self):
        resp = TokenSubmitResponse(
            status=AuthStatus.ERROR,
            message="Invalid token",
        )
        assert resp.expires_at is None


class TestCredentialsResponse:
    """Test CredentialsResponse model."""

    def test_credentials_response(self):
        resp = CredentialsResponse(
            credentials={"token": "sk-ant-oat01-test"},
            expires_at="2026-03-01T00:00:00Z",
        )
        assert resp.credentials["token"] == "sk-ant-oat01-test"
        assert resp.expires_at == "2026-03-01T00:00:00Z"

    def test_credentials_without_expiry(self):
        resp = CredentialsResponse(
            credentials={"token": "sk-ant-oat01-test"},
        )
        assert resp.expires_at is None
