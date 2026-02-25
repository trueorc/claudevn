"""Tests for auth API router."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import router


@pytest.fixture
def app():
    """Create a test FastAPI app with auth router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestGetStatus:
    """Test GET /auth/status (system-level overview)."""

    def test_status_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.get("/auth/status")
            assert response.status_code == 404

    def test_status_authenticated(self, client):
        mock_service = MagicMock()
        mock_service.get_status = AsyncMock(return_value={
            "status": "authenticated",
            "authenticated": True,
            "expires_at": "2026-03-01T00:00:00Z",
            "message": None,
        })
        mock_service.get_system_auth_status.return_value = {
            "serving_authorized": True,
            "compute_authorized": 2,
            "compute_unauthorized": 1,
            "tokens_expiring_soon": 0,
        }
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/status")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "authenticated"
            assert data["authenticated"] is True
            assert data["serving_authorized"] is True
            assert data["compute_authorized"] == 2
            assert data["compute_unauthorized"] == 1
            assert data["tokens_expiring_soon"] == 0

    def test_status_not_configured(self, client):
        mock_service = MagicMock()
        mock_service.get_status = AsyncMock(return_value={
            "status": "not_configured",
            "authenticated": False,
            "expires_at": None,
            "message": None,
        })
        mock_service.get_system_auth_status.return_value = {
            "serving_authorized": False,
            "compute_authorized": 0,
            "compute_unauthorized": 0,
            "tokens_expiring_soon": 0,
        }
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/status")
            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is False
            assert data["serving_authorized"] is False


class TestRefreshFromRedis:
    """Test POST /auth/refresh."""

    def test_refresh_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.post("/auth/refresh")
            assert response.status_code == 503

    def test_refresh_success(self, client):
        mock_service = MagicMock()
        mock_service.refresh_from_redis = AsyncMock(return_value={
            "status": "authenticated",
            "authenticated": True,
            "tokens_loaded": 1,
        })
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.post("/auth/refresh")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "authenticated"
            assert data["tokens_loaded"] == 1

    def test_refresh_no_tokens(self, client):
        mock_service = MagicMock()
        mock_service.refresh_from_redis = AsyncMock(return_value={
            "status": "not_configured",
            "authenticated": False,
            "tokens_loaded": 0,
        })
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.post("/auth/refresh")
            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is False
            assert data["tokens_loaded"] == 0


class TestSubmitToken:
    """Test POST /auth/token."""

    def test_token_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.post("/auth/token", json={
                "token": "sk-ant-oat01-test",
            })
            assert response.status_code == 503

    def test_token_success(self, client):
        mock_service = MagicMock()
        mock_service.store_token = AsyncMock(return_value={
            "status": "authenticated",
            "message": "Token stored successfully",
            "expires_at": "2027-02-14T00:00:00Z",
        })
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.post("/auth/token", json={
                "token": "sk-ant-oat01-test-token",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "authenticated"
            assert data["message"] == "Token stored successfully"
            mock_service.store_token.assert_called_once_with(
                token="sk-ant-oat01-test-token",
                component_id="serving",
                component_type="serving",
            )

    def test_token_invalid_format(self, client):
        """Token validation happens at Pydantic level."""
        with patch("api.auth.get_claude_auth_service", return_value=MagicMock()):
            response = client.post("/auth/token", json={
                "token": "invalid-token",
            })
            assert response.status_code == 422

    def test_token_missing_body(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=MagicMock()):
            response = client.post("/auth/token", json={})
            assert response.status_code == 422

    def test_token_custom_component(self, client):
        mock_service = MagicMock()
        mock_service.store_token = AsyncMock(return_value={
            "status": "authenticated",
            "message": "Token stored successfully",
            "expires_at": "2027-02-14T00:00:00Z",
        })
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.post("/auth/token", json={
                "token": "sk-ant-oat01-test",
                "component_id": "compute-1",
                "component_type": "compute",
            })
            assert response.status_code == 200
            mock_service.store_token.assert_called_once_with(
                token="sk-ant-oat01-test",
                component_id="compute-1",
                component_type="compute",
            )


class TestGetTokenInfo:
    """Test GET /auth/token/{component_id}."""

    def test_token_info_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.get("/auth/token/serving")
            assert response.status_code == 503

    def test_token_info_found(self, client):
        mock_service = MagicMock()
        mock_service.get_token_info.return_value = {
            "component_id": "compute-1",
            "status": "active",
            "authorized_at": "2026-02-14T00:00:00Z",
            "expires_at": "2027-02-14T00:00:00Z",
            "component_type": "compute",
        }
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/token/compute-1")
            assert response.status_code == 200
            data = response.json()
            assert data["component_id"] == "compute-1"
            assert data["status"] == "active"
            assert data["component_type"] == "compute"
            assert "token" not in data  # Raw token must NOT be exposed

    def test_token_info_not_found(self, client):
        mock_service = MagicMock()
        mock_service.get_token_info.return_value = None
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/token/nonexistent")
            assert response.status_code == 404


class TestRevokeToken:
    """Test DELETE /auth/token/{component_id}."""

    def test_revoke_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.delete("/auth/token/serving")
            assert response.status_code == 503

    def test_revoke_success(self, client):
        mock_service = MagicMock()
        mock_service.clear_credentials = AsyncMock(return_value=True)
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.delete("/auth/token/compute-1")
            assert response.status_code == 200
            data = response.json()
            assert data["revoked"] is True
            mock_service.clear_credentials.assert_called_once_with(component_id="compute-1")

    def test_revoke_not_found(self, client):
        mock_service = MagicMock()
        mock_service.clear_credentials = AsyncMock(return_value=False)
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.delete("/auth/token/nonexistent")
            assert response.status_code == 404


class TestListTokens:
    """Test GET /auth/tokens."""

    def test_list_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.get("/auth/tokens")
            assert response.status_code == 503

    def test_list_empty(self, client):
        mock_service = MagicMock()
        mock_service.list_tokens.return_value = []
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/tokens")
            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []

    def test_list_multiple(self, client):
        mock_service = MagicMock()
        mock_service.list_tokens.return_value = [
            {
                "component_id": "serving",
                "status": "active",
                "authorized_at": "2026-02-14T00:00:00Z",
                "expires_at": "2027-02-14T00:00:00Z",
                "component_type": "serving",
            },
            {
                "component_id": "compute-1",
                "status": "active",
                "authorized_at": "2026-02-14T00:00:00Z",
                "expires_at": "2027-02-14T00:00:00Z",
                "component_type": "compute",
            },
        ]
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/tokens")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 2
            # Verify no raw tokens exposed
            for item in data["items"]:
                assert "token" not in item


class TestGetCredentials:
    """Test GET /auth/credentials (unauthenticated - internal network only)."""

    def test_credentials_service_disabled(self, client):
        with patch("api.auth.get_claude_auth_service", return_value=None):
            response = client.get("/auth/credentials")
            assert response.status_code == 503

    def test_credentials_not_available(self, client):
        mock_service = MagicMock()
        mock_service.get_credentials = AsyncMock(return_value=None)
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/credentials")
            assert response.status_code == 503

    def test_credentials_available(self, client):
        mock_service = MagicMock()
        mock_service.get_credentials = AsyncMock(return_value={
            "token": "sk-ant-oat01-test",
        })
        mock_service.get_status = AsyncMock(return_value={
            "expires_at": "2026-03-01T00:00:00Z",
        })
        with patch("api.auth.get_claude_auth_service", return_value=mock_service):
            response = client.get("/auth/credentials")
            assert response.status_code == 200
            data = response.json()
            assert data["credentials"]["token"] == "sk-ant-oat01-test"
            assert data["expires_at"] == "2026-03-01T00:00:00Z"
