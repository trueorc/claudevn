"""Tests for local auth mode login flow and auto-provisioning."""

import pytest
from unittest.mock import patch, MagicMock

from models.user import UserRole
from services.user_service import UserService
from services.local_auth_provider import LocalAuthProvider


@pytest.fixture
def users_file(tmp_path):
    """Create a temporary users file."""
    f = tmp_path / "users.local"
    f.write_text("matt:password\njason:secret\nmom:hello\n")
    return str(f)


@pytest.fixture
def provider(users_file):
    return LocalAuthProvider(users_file)


@pytest.fixture
def service():
    return UserService(redis_client=None, secret_key="test-local-auth-key")


class TestAutoProvision:
    @pytest.mark.asyncio
    async def test_provisions_new_users(self, service, provider):
        count = await service.auto_provision_from_file(provider.list_usernames())
        assert count == 3
        users = await service.list_users()
        assert len(users) == 3

    @pytest.mark.asyncio
    async def test_first_provisioned_is_owner(self, service, provider):
        await service.auto_provision_from_file(provider.list_usernames())
        matt = await service.get_user_by_username("matt")
        assert matt.role == UserRole.OWNER

    @pytest.mark.asyncio
    async def test_subsequent_provisioned_are_members(self, service, provider):
        await service.auto_provision_from_file(provider.list_usernames())
        jason = await service.get_user_by_username("jason")
        mom = await service.get_user_by_username("mom")
        assert jason.role == UserRole.MEMBER
        assert mom.role == UserRole.MEMBER

    @pytest.mark.asyncio
    async def test_skips_existing_users(self, service, provider):
        await service.register("matt")
        count = await service.auto_provision_from_file(provider.list_usernames())
        assert count == 2  # jason and mom only

    @pytest.mark.asyncio
    async def test_idempotent(self, service, provider):
        await service.auto_provision_from_file(provider.list_usernames())
        count = await service.auto_provision_from_file(provider.list_usernames())
        assert count == 0


class TestLocalModeLogin:
    @pytest.mark.asyncio
    async def test_login_with_correct_password(self, service, provider):
        await service.auto_provision_from_file(provider.list_usernames())

        mock_config = MagicMock()
        mock_config.cognito.auth_mode = "local"

        with patch("config.get_config", return_value=mock_config), \
             patch("services.local_auth_provider.get_local_auth_provider", return_value=provider):
            user, token = await service.login("matt", password="password")
            assert user.username == "matt"
            assert token

    @pytest.mark.asyncio
    async def test_login_with_wrong_password(self, service, provider):
        await service.auto_provision_from_file(provider.list_usernames())

        mock_config = MagicMock()
        mock_config.cognito.auth_mode = "local"

        with patch("config.get_config", return_value=mock_config), \
             patch("services.local_auth_provider.get_local_auth_provider", return_value=provider):
            with pytest.raises(ValueError, match="Invalid username or password"):
                await service.login("matt", password="wrong")

    @pytest.mark.asyncio
    async def test_login_without_password_in_local_mode(self, service, provider):
        await service.auto_provision_from_file(provider.list_usernames())

        mock_config = MagicMock()
        mock_config.cognito.auth_mode = "local"

        with patch("config.get_config", return_value=mock_config), \
             patch("services.local_auth_provider.get_local_auth_provider", return_value=provider):
            with pytest.raises(ValueError, match="Password is required"):
                await service.login("matt")

    @pytest.mark.asyncio
    async def test_login_bypass_mode_ignores_password(self, service):
        await service.register("matt")

        mock_config = MagicMock()
        mock_config.cognito.auth_mode = "bypass"

        with patch("config.get_config", return_value=mock_config):
            user, token = await service.login("matt")
            assert user.username == "matt"
