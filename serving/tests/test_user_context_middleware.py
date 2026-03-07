"""Tests for UserContextMiddleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient
from fastapi import FastAPI, Request

from middleware.user_context import UserContextMiddleware, get_current_user, get_current_user_id


@pytest.fixture
def app():
    """Create a test FastAPI app with UserContextMiddleware."""
    app = FastAPI()
    app.add_middleware(UserContextMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        user = get_current_user()
        user_from_state = getattr(request.state, 'user', None)
        return {
            "context_user": user,
            "state_user": user_from_state,
            "user_id": get_current_user_id(),
        }

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@patch("middleware.user_context.get_config")
def test_bypass_mode_provides_dev_user(mock_config, client):
    """In bypass mode, requests without tokens get dev user."""
    mock_config.return_value.cognito.auth_mode = "bypass"

    response = client.get("/test")
    assert response.status_code == 200
    data = response.json()
    assert data["context_user"]["sub"] == "bypass-dev-user"
    assert data["user_id"] == "bypass-dev-user"
    assert data["state_user"]["sub"] == "bypass-dev-user"


@patch("middleware.user_context.get_config")
def test_no_token_cognito_mode(mock_config, client):
    """In cognito mode, requests without tokens have no user."""
    mock_config.return_value.cognito.auth_mode = "cognito"

    response = client.get("/test")
    assert response.status_code == 200
    data = response.json()
    assert data["context_user"] is None
    assert data["user_id"] is None


@patch("services.user_service.get_user_service")
@patch("middleware.user_context.get_config")
def test_local_token_verification(mock_config, mock_get_service, client):
    """Local user service token is verified and user context set."""
    mock_config.return_value.cognito.auth_mode = "bypass"

    mock_user = MagicMock()
    mock_user.user_id = "user-123"
    mock_user.email = "test@example.com"
    mock_user.username = "testuser"
    mock_user.role.value = "member"

    mock_service = MagicMock()
    mock_service.verify_token.return_value = "user-123"
    mock_service.get_user = AsyncMock(return_value=mock_user)
    mock_get_service.return_value = mock_service

    response = client.get("/test", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user-123"
    assert data["context_user"]["username"] == "testuser"


@patch("middleware.user_context.get_config")
def test_invalid_token(mock_config, client):
    """Invalid tokens result in no user context."""
    mock_config.return_value.cognito.auth_mode = "cognito"

    response = client.get("/test", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["context_user"] is None


def test_context_isolation():
    """get_current_user returns None outside request context."""
    assert get_current_user() is None
    assert get_current_user_id() is None
