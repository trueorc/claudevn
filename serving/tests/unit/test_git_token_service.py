"""Unit tests for git_token_service.py"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from git.git_token_service import (
    COMPUTE_TOKEN_PREFIX,
    PAT_TOKEN_PREFIX,
    GitTokenService,
    get_git_token_service,
    set_git_token_service,
)


class TestGitTokenService:
    """Test cases for GitTokenService."""

    @pytest.fixture
    def service_no_redis(self):
        """Create service without Redis (in-memory mode)."""
        return GitTokenService(redis_client=None)

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = MagicMock()
        redis.hset = AsyncMock()
        redis.hgetall = AsyncMock()
        redis.set = AsyncMock()
        redis.get = AsyncMock()
        redis.delete = AsyncMock()
        redis.scan = AsyncMock()
        return redis

    @pytest.fixture
    def service_with_redis(self, mock_redis):
        """Create service with mocked Redis."""
        return GitTokenService(redis_client=mock_redis)

    def _hash_token(self, token: str) -> str:
        """Helper to hash tokens like the service does."""
        return hashlib.sha256(token.encode()).hexdigest()

    # ==========================================================================
    # Token Creation Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_create_compute_token_no_redis(self, service_no_redis):
        """Test creating compute token without Redis."""
        compute_id = "compute-123"
        token = await service_no_redis.create_compute_token(compute_id)

        # Token should have correct prefix
        assert token.startswith(COMPUTE_TOKEN_PREFIX)

        # Token should be stored in memory
        token_hash = self._hash_token(token)
        assert token_hash in service_no_redis._tokens

        # Token data should be correct
        token_data = service_no_redis._tokens[token_hash]
        assert token_data["type"] == "compute"
        assert token_data["compute_id"] == compute_id
        assert "created_at" in token_data
        assert token_data["token_hash"] == token_hash

    @pytest.mark.asyncio
    async def test_create_compute_token_with_redis(self, service_with_redis, mock_redis):
        """Test creating compute token with Redis."""
        compute_id = "compute-456"
        token = await service_with_redis.create_compute_token(compute_id)

        assert token.startswith(COMPUTE_TOKEN_PREFIX)

        # Verify Redis calls
        token_hash = self._hash_token(token)
        assert mock_redis.hset.call_count >= 1
        assert mock_redis.set.call_count >= 1

        # Extract hset call arguments
        hset_call = mock_redis.hset.call_args
        assert hset_call[0][0] == f"claudevn:git_token:{token_hash}"
        mapping = hset_call[1]["mapping"]
        assert mapping["type"] == "compute"
        assert mapping["compute_id"] == compute_id

        # Extract set call for index
        set_call = mock_redis.set.call_args
        assert set_call[0][0] == f"claudevn:git_token_idx:{compute_id}"
        assert set_call[0][1] == token_hash

    @pytest.mark.asyncio
    async def test_create_compute_token_revokes_existing(self, service_no_redis):
        """Test that creating a new compute token revokes the old one."""
        compute_id = "compute-789"

        # Create first token
        token1 = await service_no_redis.create_compute_token(compute_id)
        token1_hash = self._hash_token(token1)
        assert token1_hash in service_no_redis._tokens

        # Create second token - should revoke first
        token2 = await service_no_redis.create_compute_token(compute_id)
        token2_hash = self._hash_token(token2)

        # First token should be revoked
        assert token1_hash not in service_no_redis._tokens
        # Second token should exist
        assert token2_hash in service_no_redis._tokens

    @pytest.mark.asyncio
    async def test_create_personal_access_token_no_redis(self, service_no_redis):
        """Test creating PAT without Redis."""
        owner = "user123"
        description = "Development token"
        token = await service_no_redis.create_personal_access_token(owner, description)

        # Token should have correct prefix
        assert token.startswith(PAT_TOKEN_PREFIX)

        # Token should be stored in memory
        token_hash = self._hash_token(token)
        assert token_hash in service_no_redis._tokens

        # Token data should be correct
        token_data = service_no_redis._tokens[token_hash]
        assert token_data["type"] == "pat"
        assert token_data["owner"] == owner
        assert token_data["description"] == description
        assert "created_at" in token_data

    @pytest.mark.asyncio
    async def test_create_personal_access_token_with_redis(self, service_with_redis, mock_redis):
        """Test creating PAT with Redis."""
        owner = "user456"
        description = "CI/CD token"
        token = await service_with_redis.create_personal_access_token(owner, description)

        assert token.startswith(PAT_TOKEN_PREFIX)

        # Verify Redis hset call
        token_hash = self._hash_token(token)
        assert mock_redis.hset.called
        hset_call = mock_redis.hset.call_args
        assert hset_call[0][0] == f"claudevn:git_token:{token_hash}"
        mapping = hset_call[1]["mapping"]
        assert mapping["type"] == "pat"
        assert mapping["owner"] == owner
        assert mapping["description"] == description

    @pytest.mark.asyncio
    async def test_create_token_redis_failure_fallback(self, service_with_redis, mock_redis):
        """Test fallback to in-memory when Redis fails during creation."""
        mock_redis.hset.side_effect = Exception("Redis connection error")

        compute_id = "compute-error"
        token = await service_with_redis.create_compute_token(compute_id)

        # Token should still be created in memory
        token_hash = self._hash_token(token)
        assert token_hash in service_with_redis._tokens
        assert service_with_redis._tokens[token_hash]["compute_id"] == compute_id

    # ==========================================================================
    # Token Validation Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_validate_token_valid_no_redis(self, service_no_redis):
        """Test validating a valid token without Redis."""
        compute_id = "compute-valid"
        token = await service_no_redis.create_compute_token(compute_id)

        result = await service_no_redis.validate_token(token)

        assert result is not None
        assert result["type"] == "compute"
        assert result["compute_id"] == compute_id

    @pytest.mark.asyncio
    async def test_validate_token_invalid_no_redis(self, service_no_redis):
        """Test validating an invalid token without Redis."""
        invalid_token = f"{COMPUTE_TOKEN_PREFIX}invalid-token-12345"

        result = await service_no_redis.validate_token(invalid_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_valid_with_redis(self, service_with_redis, mock_redis):
        """Test validating a valid token with Redis."""
        token = f"{COMPUTE_TOKEN_PREFIX}test-token"
        token_hash = self._hash_token(token)

        # Mock Redis to return token data
        mock_redis.hgetall.return_value = {
            "type": "compute",
            "compute_id": "compute-123",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "token_hash": token_hash,
        }

        result = await service_with_redis.validate_token(token)

        assert result is not None
        assert result["type"] == "compute"
        assert result["compute_id"] == "compute-123"

        # Verify correct Redis key was queried
        mock_redis.hgetall.assert_called_once_with(f"claudevn:git_token:{token_hash}")

    @pytest.mark.asyncio
    async def test_validate_token_invalid_with_redis(self, service_with_redis, mock_redis):
        """Test validating an invalid token with Redis."""
        invalid_token = f"{COMPUTE_TOKEN_PREFIX}invalid"
        mock_redis.hgetall.return_value = {}

        result = await service_with_redis.validate_token(invalid_token)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_redis_failure_fallback(self, service_with_redis, mock_redis):
        """Test fallback to in-memory when Redis fails during validation."""
        compute_id = "compute-fallback"
        token = f"{COMPUTE_TOKEN_PREFIX}fallback-token"
        token_hash = self._hash_token(token)

        # Add token to in-memory storage
        service_with_redis._tokens[token_hash] = {
            "type": "compute",
            "compute_id": compute_id,
        }

        # Make Redis fail
        mock_redis.hgetall.side_effect = Exception("Redis error")

        result = await service_with_redis.validate_token(token)

        # Should fall back to in-memory and find the token
        assert result is not None
        assert result["compute_id"] == compute_id

    # ==========================================================================
    # Token Revocation Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_revoke_compute_token_no_redis(self, service_no_redis):
        """Test revoking compute token without Redis."""
        compute_id = "compute-revoke"
        token = await service_no_redis.create_compute_token(compute_id)
        token_hash = self._hash_token(token)

        # Verify token exists
        assert token_hash in service_no_redis._tokens

        # Revoke token
        result = await service_no_redis.revoke_compute_token(compute_id)

        assert result is True
        assert token_hash not in service_no_redis._tokens

    @pytest.mark.asyncio
    async def test_revoke_compute_token_not_found(self, service_no_redis):
        """Test revoking non-existent compute token."""
        result = await service_no_redis.revoke_compute_token("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_compute_token_with_redis(self, service_with_redis, mock_redis):
        """Test revoking compute token with Redis."""
        compute_id = "compute-redis-revoke"
        token_hash = "abc123"

        # Mock Redis to return token hash from index
        mock_redis.get.return_value = token_hash
        mock_redis.delete.return_value = 1

        result = await service_with_redis.revoke_compute_token(compute_id)

        assert result is True

        # Verify Redis calls
        mock_redis.get.assert_called_once_with(f"claudevn:git_token_idx:{compute_id}")
        assert mock_redis.delete.call_count == 2
        # Should delete both the token and the index
        delete_calls = [call[0][0] for call in mock_redis.delete.call_args_list]
        assert f"claudevn:git_token:{token_hash}" in delete_calls
        assert f"claudevn:git_token_idx:{compute_id}" in delete_calls

    @pytest.mark.asyncio
    async def test_revoke_pat_no_redis(self, service_no_redis):
        """Test revoking PAT without Redis."""
        owner = "user-pat"
        token = await service_no_redis.create_personal_access_token(owner, "test")
        token_hash = self._hash_token(token)

        # Verify token exists
        assert token_hash in service_no_redis._tokens

        # Revoke token
        result = await service_no_redis.revoke_pat(token_hash)

        assert result is True
        assert token_hash not in service_no_redis._tokens

    @pytest.mark.asyncio
    async def test_revoke_pat_not_found(self, service_no_redis):
        """Test revoking non-existent PAT."""
        result = await service_no_redis.revoke_pat("nonexistent-hash")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_pat_with_redis(self, service_with_redis, mock_redis):
        """Test revoking PAT with Redis."""
        token_hash = "pat-hash-123"
        mock_redis.delete.return_value = 1

        result = await service_with_redis.revoke_pat(token_hash)

        assert result is True
        mock_redis.delete.assert_called_once_with(f"claudevn:git_token:{token_hash}")

    # ==========================================================================
    # Token Listing Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_list_tokens_no_redis_empty(self, service_no_redis):
        """Test listing tokens when none exist."""
        result = await service_no_redis.list_tokens()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_tokens_no_redis_all(self, service_no_redis):
        """Test listing all tokens without Redis."""
        # Create multiple tokens
        await service_no_redis.create_compute_token("compute-1")
        await service_no_redis.create_compute_token("compute-2")
        await service_no_redis.create_personal_access_token("user-1", "Token 1")

        result = await service_no_redis.list_tokens()

        assert len(result) == 3
        # Verify token_hash is not exposed but prefix is
        for token_data in result:
            assert "token_hash" not in token_data
            assert "token_hash_prefix" in token_data
            assert len(token_data["token_hash_prefix"]) == 12

    @pytest.mark.asyncio
    async def test_list_tokens_no_redis_filter_compute(self, service_no_redis):
        """Test listing only compute tokens."""
        await service_no_redis.create_compute_token("compute-1")
        await service_no_redis.create_compute_token("compute-2")
        await service_no_redis.create_personal_access_token("user-1", "Token 1")

        result = await service_no_redis.list_tokens(token_type="compute")

        assert len(result) == 2
        for token_data in result:
            assert token_data["type"] == "compute"

    @pytest.mark.asyncio
    async def test_list_tokens_no_redis_filter_pat(self, service_no_redis):
        """Test listing only PATs."""
        await service_no_redis.create_compute_token("compute-1")
        await service_no_redis.create_personal_access_token("user-1", "Token 1")
        await service_no_redis.create_personal_access_token("user-2", "Token 2")

        result = await service_no_redis.list_tokens(token_type="pat")

        assert len(result) == 2
        for token_data in result:
            assert token_data["type"] == "pat"

    @pytest.mark.asyncio
    async def test_list_tokens_with_redis(self, service_with_redis, mock_redis):
        """Test listing tokens with Redis."""
        # Mock Redis scan to return token keys
        mock_redis.scan.side_effect = [
            (0, [
                b"claudevn:git_token:hash1",
                b"claudevn:git_token:hash2",
            ]),
        ]

        # Mock hgetall to return token data
        mock_redis.hgetall.side_effect = [
            {
                "type": "compute",
                "compute_id": "compute-1",
                "token_hash": "hash1" * 10,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "type": "pat",
                "owner": "user-1",
                "description": "Test PAT",
                "token_hash": "hash2" * 10,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

        result = await service_with_redis.list_tokens()

        assert len(result) == 2
        assert result[0]["type"] == "compute"
        assert result[1]["type"] == "pat"
        # Verify token_hash is not exposed
        for token_data in result:
            assert "token_hash" not in token_data
            assert "token_hash_prefix" in token_data

    @pytest.mark.asyncio
    async def test_list_tokens_redis_failure_fallback(self, service_with_redis, mock_redis):
        """Test fallback to in-memory when Redis fails during listing."""
        # Add tokens to in-memory storage
        service_with_redis._tokens = {
            "hash1": {"type": "compute", "compute_id": "compute-1"},
            "hash2": {"type": "pat", "owner": "user-1"},
        }

        # Make Redis fail
        mock_redis.scan.side_effect = Exception("Redis error")

        result = await service_with_redis.list_tokens()

        # Should fall back to in-memory
        assert len(result) == 2

    # ==========================================================================
    # Helper Method Tests
    # ==========================================================================

    def test_hash_token(self, service_no_redis):
        """Test token hashing produces consistent SHA-256 hashes."""
        token = "test-token-123"
        expected_hash = hashlib.sha256(token.encode()).hexdigest()

        result = service_no_redis._hash_token(token)

        assert result == expected_hash
        assert len(result) == 64  # SHA-256 produces 64-character hex string

    def test_redis_key(self, service_no_redis):
        """Test Redis key generation for token hash."""
        token_hash = "abc123"
        expected_key = f"claudevn:git_token:{token_hash}"

        result = service_no_redis._redis_key(token_hash)

        assert result == expected_key

    def test_compute_index_key(self, service_no_redis):
        """Test Redis key generation for compute ID index."""
        compute_id = "compute-xyz"
        expected_key = f"claudevn:git_token_idx:{compute_id}"

        result = service_no_redis._compute_index_key(compute_id)

        assert result == expected_key

    # ==========================================================================
    # Global Service Getter/Setter Tests
    # ==========================================================================

    def test_get_set_global_service(self):
        """Test global service getter and setter."""
        original = get_git_token_service()

        try:
            # Set new service
            test_service = GitTokenService()
            set_git_token_service(test_service)

            # Get should return the same instance
            retrieved = get_git_token_service()
            assert retrieved is test_service

            # Set to None
            set_git_token_service(None)
            assert get_git_token_service() is None

        finally:
            # Restore original
            set_git_token_service(original)

    # ==========================================================================
    # Token Prefix Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_compute_token_prefix_validation(self, service_no_redis):
        """Test that compute tokens always have the correct prefix."""
        token = await service_no_redis.create_compute_token("compute-test")

        assert token.startswith(COMPUTE_TOKEN_PREFIX)
        assert COMPUTE_TOKEN_PREFIX == "cvn-ct-"

    @pytest.mark.asyncio
    async def test_pat_token_prefix_validation(self, service_no_redis):
        """Test that PATs always have the correct prefix."""
        token = await service_no_redis.create_personal_access_token("user", "test")

        assert token.startswith(PAT_TOKEN_PREFIX)
        assert PAT_TOKEN_PREFIX == "cvn-pat-"
