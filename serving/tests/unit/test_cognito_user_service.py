"""Tests for Cognito user management service."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from services.cognito_user_service import (
    invite_user,
    list_users,
    remove_user,
    resend_invite,
    reset_client,
)


@pytest.fixture(autouse=True)
def reset_module():
    """Reset the cached boto3 client before each test."""
    reset_client()
    yield
    reset_client()


def _mock_config(auth_mode="cognito", pool_id="us-east-1_TestPool"):
    config = MagicMock()
    config.cognito.auth_mode = auth_mode
    config.cognito.user_pool_id = pool_id
    config.cognito.region = "us-east-1"
    return config


class TestInviteUser:
    """Test user invitation."""

    @pytest.mark.asyncio
    async def test_invite_creates_user(self):
        mock_client = MagicMock()
        mock_client.admin_create_user.return_value = {
            "User": {
                "UserStatus": "FORCE_CHANGE_PASSWORD",
                "UserCreateDate": datetime(2024, 1, 1, tzinfo=timezone.utc),
            }
        }

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                result = await invite_user("test@example.com")

        assert result["email"] == "test@example.com"
        assert result["status"] == "FORCE_CHANGE_PASSWORD"
        mock_client.admin_create_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_invite_duplicate_raises_error(self):
        mock_client = MagicMock()
        mock_client.exceptions.UsernameExistsException = type(
            "UsernameExistsException", (Exception,), {}
        )
        mock_client.admin_create_user.side_effect = (
            mock_client.exceptions.UsernameExistsException()
        )

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                with pytest.raises(ValueError, match="already exists"):
                    await invite_user("existing@example.com")


class TestListUsers:
    """Test user listing."""

    @pytest.mark.asyncio
    async def test_list_returns_users(self):
        mock_client = MagicMock()
        mock_client.list_users.return_value = {
            "Users": [
                {
                    "Username": "user1",
                    "Attributes": [{"Name": "email", "Value": "user1@test.com"}],
                    "UserStatus": "CONFIRMED",
                    "UserCreateDate": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    "UserLastModifiedDate": datetime(2024, 1, 2, tzinfo=timezone.utc),
                    "Enabled": True,
                }
            ]
        }

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                result = await list_users()

        assert len(result) == 1
        assert result[0]["email"] == "user1@test.com"
        assert result[0]["status"] == "CONFIRMED"

    @pytest.mark.asyncio
    async def test_list_paginates(self):
        mock_client = MagicMock()
        mock_client.list_users.side_effect = [
            {
                "Users": [{"Username": "u1", "Attributes": [], "UserStatus": "CONFIRMED",
                           "UserCreateDate": None, "UserLastModifiedDate": None, "Enabled": True}],
                "PaginationToken": "token123",
            },
            {
                "Users": [{"Username": "u2", "Attributes": [], "UserStatus": "CONFIRMED",
                           "UserCreateDate": None, "UserLastModifiedDate": None, "Enabled": True}],
            },
        ]

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                result = await list_users()

        assert len(result) == 2
        assert mock_client.list_users.call_count == 2


class TestRemoveUser:
    """Test user removal."""

    @pytest.mark.asyncio
    async def test_remove_existing_user(self):
        mock_client = MagicMock()

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                result = await remove_user("user1")

        assert result is True
        mock_client.admin_delete_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_false(self):
        mock_client = MagicMock()
        mock_client.exceptions.UserNotFoundException = type(
            "UserNotFoundException", (Exception,), {}
        )
        mock_client.admin_delete_user.side_effect = (
            mock_client.exceptions.UserNotFoundException()
        )

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                result = await remove_user("missing")

        assert result is False


class TestResendInvite:
    """Test invitation resend."""

    @pytest.mark.asyncio
    async def test_resend_success(self):
        mock_client = MagicMock()
        mock_client.admin_create_user.return_value = {
            "User": {"UserStatus": "FORCE_CHANGE_PASSWORD"}
        }

        with patch("services.cognito_user_service.get_config", return_value=_mock_config()):
            with patch("services.cognito_user_service._get_client", return_value=mock_client):
                result = await resend_invite("user1")

        assert result["username"] == "user1"
        mock_client.admin_create_user.assert_called_once_with(
            UserPoolId="us-east-1_TestPool",
            Username="user1",
            MessageAction="RESEND",
            DesiredDeliveryMediums=["EMAIL"],
        )
