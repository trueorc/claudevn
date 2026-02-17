"""Tests for user registration and authentication service."""

import pytest
import time
from unittest.mock import patch

from models.user import User, UserRole
from services.user_service import UserService


@pytest.fixture
def service():
    """Create user service with no Redis."""
    return UserService(redis_client=None, secret_key="test-secret-key-1234")


class TestRegistration:
    @pytest.mark.asyncio
    async def test_first_user_becomes_owner(self, service):
        user, token = await service.register("alice")
        assert user.role == UserRole.OWNER
        assert user.username == "alice"
        assert token

    @pytest.mark.asyncio
    async def test_second_user_becomes_member(self, service):
        await service.register("alice")
        user, token = await service.register("bob")
        assert user.role == UserRole.MEMBER

    @pytest.mark.asyncio
    async def test_duplicate_username_rejected(self, service):
        await service.register("alice")
        with pytest.raises(ValueError, match="already taken"):
            await service.register("alice")

    @pytest.mark.asyncio
    async def test_registration_with_email(self, service):
        user, _ = await service.register("alice", email="alice@example.com")
        assert user.email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_registration_sets_last_login(self, service):
        user, _ = await service.register("alice")
        assert user.last_login is not None


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, service):
        await service.register("alice")
        user, token = await service.login("alice")
        assert user.username == "alice"
        assert token

    @pytest.mark.asyncio
    async def test_login_unknown_user(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.login("nonexistent")

    @pytest.mark.asyncio
    async def test_login_updates_last_login(self, service):
        user1, _ = await service.register("alice")
        first_login = user1.last_login

        user2, _ = await service.login("alice")
        assert user2.last_login >= first_login


class TestTokenVerification:
    @pytest.mark.asyncio
    async def test_valid_token(self, service):
        user, token = await service.register("alice")
        verified_id = service.verify_token(token)
        assert verified_id == user.user_id

    @pytest.mark.asyncio
    async def test_invalid_token(self, service):
        assert service.verify_token("invalid.token") is None

    @pytest.mark.asyncio
    async def test_tampered_token(self, service):
        _, token = await service.register("alice")
        parts = token.split(".")
        assert service.verify_token(parts[0] + ".tampered") is None

    @pytest.mark.asyncio
    async def test_expired_token(self, service):
        user, _ = await service.register("alice")
        # Create token that expires immediately
        with patch("services.user_service.TOKEN_VALIDITY_SECONDS", -1):
            token = service._create_token(user.user_id)
        assert service.verify_token(token) is None

    @pytest.mark.asyncio
    async def test_empty_token(self, service):
        assert service.verify_token("") is None

    @pytest.mark.asyncio
    async def test_malformed_token(self, service):
        assert service.verify_token("no-dots-here") is None


class TestUserManagement:
    @pytest.mark.asyncio
    async def test_get_user(self, service):
        user, _ = await service.register("alice")
        found = await service.get_user(user.user_id)
        assert found is not None
        assert found.username == "alice"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, service):
        found = await service.get_user("nonexistent")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, service):
        user, _ = await service.register("alice")
        found = await service.get_user_by_username("alice")
        assert found is not None
        assert found.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_update_username(self, service):
        user, _ = await service.register("alice")
        updated = await service.update_user(user.user_id, username="alice2")
        assert updated.username == "alice2"

        # Old username should be freed
        found = await service.get_user_by_username("alice")
        assert found is None
        found2 = await service.get_user_by_username("alice2")
        assert found2 is not None

    @pytest.mark.asyncio
    async def test_update_username_conflict(self, service):
        await service.register("alice")
        user2, _ = await service.register("bob")
        with pytest.raises(ValueError, match="already taken"):
            await service.update_user(user2.user_id, username="alice")

    @pytest.mark.asyncio
    async def test_update_email(self, service):
        user, _ = await service.register("alice")
        updated = await service.update_user(user.user_id, email="new@example.com")
        assert updated.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_update_nonexistent_user(self, service):
        result = await service.update_user("nonexistent", username="x")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_users(self, service):
        await service.register("alice")
        await service.register("bob")
        users = await service.list_users()
        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_is_owner(self, service):
        owner, _ = await service.register("alice")
        member, _ = await service.register("bob")
        assert service.is_owner(owner.user_id) is True
        assert service.is_owner(member.user_id) is False
        assert service.is_owner("nonexistent") is False
