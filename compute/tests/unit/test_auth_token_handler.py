"""Unit tests for auth_token SSE event handler and credential monitor apply_token."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.sse_event_client import SSEEventClient
from services.credential_monitor import (
    CredentialMonitor,
    CredentialStatus,
    set_credential_monitor,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sse_client():
    """Create an SSE event client."""
    return SSEEventClient(
        serving_url="http://localhost:8002",
        compute_id="compute-001",
        api_key="test-key",
        capabilities=[],
        resources={},
    )


@pytest.fixture
def credential_monitor(tmp_path):
    """Create a credential monitor with temp path."""
    return CredentialMonitor(
        credentials_path=str(tmp_path / ".credentials.json"),
        check_interval=3600,
        expiry_warning_days=7,
    )


# =============================================================================
# TestAuthTokenHandlerRegistration
# =============================================================================


class TestAuthTokenHandlerRegistration:
    """Tests for auth_token handler registration."""

    def test_auth_token_handler_registered(self, sse_client):
        """Test that auth_token handler is registered as a built-in handler."""
        assert "auth_token" in sse_client._handlers
        assert len(sse_client._handlers["auth_token"]) == 1

    def test_auth_token_handler_is_builtin(self, sse_client):
        """Test that auth_token handler points to the correct method."""
        handlers = sse_client._handlers["auth_token"]
        assert handlers[0] == sse_client._handle_auth_token


# =============================================================================
# TestHandleAuthToken
# =============================================================================


class TestHandleAuthToken:
    """Tests for _handle_auth_token SSE event handler."""

    @pytest.mark.asyncio
    async def test_sets_env_var(self, sse_client, tmp_path):
        """Test that auth_token sets CLAUDE_CODE_OAUTH_TOKEN env var."""
        token = "sk-ant-oat01-test-token-12345678"
        event_data = {
            "token": token,
            "component_id": "compute-001",
            "expires_at": "2027-02-14T00:00:00+00:00",
        }

        mock_monitor = MagicMock()
        mock_monitor.status = CredentialStatus.VALID
        claude_dir = tmp_path / ".claude"

        with patch("services.credential_monitor.get_credential_monitor", return_value=mock_monitor), \
             patch("os.path.expanduser", return_value=str(claude_dir)):
            await sse_client._handle_auth_token("auth_token", event_data)

        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == token

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_no_token_returns_early(self, sse_client):
        """Test that missing token logs error and returns."""
        event_data = {
            "component_id": "compute-001",
        }

        with patch("services.credential_monitor.get_credential_monitor") as mock_get:
            await sse_client._handle_auth_token("auth_token", event_data)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_token_returns_early(self, sse_client):
        """Test that empty token logs error and returns."""
        event_data = {
            "token": "",
            "component_id": "compute-001",
        }

        with patch("services.credential_monitor.get_credential_monitor") as mock_get:
            await sse_client._handle_auth_token("auth_token", event_data)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_writes_onboarding_flag(self, sse_client, tmp_path):
        """Test that handler writes hasCompletedOnboarding to ~/.claude/.claude.json."""
        token = "sk-ant-oat01-test-token-12345678"
        event_data = {
            "token": token,
            "component_id": "compute-001",
        }

        mock_monitor = MagicMock()
        mock_monitor.status = CredentialStatus.VALID

        claude_dir = tmp_path / ".claude"
        claude_json = claude_dir / ".claude.json"

        with patch("services.credential_monitor.get_credential_monitor", return_value=mock_monitor), \
             patch("os.path.expanduser", return_value=str(claude_dir)):
            await sse_client._handle_auth_token("auth_token", event_data)

        assert claude_json.exists()
        data = json.loads(claude_json.read_text())
        assert data["hasCompletedOnboarding"] is True

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_merges_existing_claude_json(self, sse_client, tmp_path):
        """Test that handler merges with existing ~/.claude/.claude.json content."""
        token = "sk-ant-oat01-test-token-12345678"
        event_data = {
            "token": token,
            "component_id": "compute-001",
        }

        mock_monitor = MagicMock()
        mock_monitor.status = CredentialStatus.VALID

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        claude_json = claude_dir / ".claude.json"
        claude_json.write_text(json.dumps({"existingKey": "existingValue"}))

        with patch("services.credential_monitor.get_credential_monitor", return_value=mock_monitor), \
             patch("os.path.expanduser", return_value=str(claude_dir)):
            await sse_client._handle_auth_token("auth_token", event_data)

        data = json.loads(claude_json.read_text())
        assert data["hasCompletedOnboarding"] is True
        assert data["existingKey"] == "existingValue"

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_calls_apply_token_on_monitor(self, sse_client, tmp_path):
        """Test that handler calls apply_token on credential monitor."""
        token = "sk-ant-oat01-test-token-12345678"
        expires_at = "2027-02-14T00:00:00+00:00"
        event_data = {
            "token": token,
            "component_id": "compute-001",
            "expires_at": expires_at,
        }

        mock_monitor = MagicMock()
        mock_monitor.status = CredentialStatus.VALID

        claude_dir = tmp_path / ".claude"

        with patch("services.credential_monitor.get_credential_monitor", return_value=mock_monitor), \
             patch("os.path.expanduser", return_value=str(claude_dir)):
            await sse_client._handle_auth_token("auth_token", event_data)

        mock_monitor.apply_token.assert_called_once_with(token, expires_at=expires_at)

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_no_monitor_still_sets_env(self, sse_client, tmp_path):
        """Test that env var is set even when no credential monitor exists."""
        token = "sk-ant-oat01-test-token-12345678"
        event_data = {
            "token": token,
            "component_id": "compute-001",
        }

        claude_dir = tmp_path / ".claude"

        with patch("services.credential_monitor.get_credential_monitor", return_value=None), \
             patch("os.path.expanduser", return_value=str(claude_dir)):
            await sse_client._handle_auth_token("auth_token", event_data)

        assert os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") == token

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    @pytest.mark.asyncio
    async def test_masks_token_in_logs(self, sse_client, tmp_path):
        """Test that token is masked in log output (only last 8 chars shown)."""
        token = "sk-ant-oat01-abcdefghijklmnop12345678"
        event_data = {
            "token": token,
            "component_id": "compute-001",
        }

        mock_monitor = MagicMock()
        mock_monitor.status = CredentialStatus.VALID

        claude_dir = tmp_path / ".claude"

        with patch("services.credential_monitor.get_credential_monitor", return_value=mock_monitor), \
             patch("os.path.expanduser", return_value=str(claude_dir)), \
             patch("services.sse_event_client.logger") as mock_logger:
            await sse_client._handle_auth_token("auth_token", event_data)

        # Check that the full token was NOT logged
        for call in mock_logger.info.call_args_list:
            msg = str(call)
            assert token not in msg

        # Cleanup
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)


# =============================================================================
# TestApplyToken
# =============================================================================


class TestApplyToken:
    """Tests for CredentialMonitor.apply_token method."""

    def test_apply_valid_token(self, credential_monitor):
        """Test applying a token with future expiry sets status to VALID."""
        future = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=future)

        assert credential_monitor.status == CredentialStatus.VALID
        assert credential_monitor._expires_at is not None
        assert credential_monitor._refresh_failures == 0

    def test_apply_expiring_token(self, credential_monitor):
        """Test applying a token expiring within warning window sets EXPIRING."""
        soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=soon)

        assert credential_monitor.status == CredentialStatus.EXPIRING

    def test_apply_expired_token(self, credential_monitor):
        """Test applying an already-expired token sets EXPIRED."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=past)

        assert credential_monitor.status == CredentialStatus.EXPIRED

    def test_apply_token_no_expiry(self, credential_monitor):
        """Test applying a token without expiry sets VALID."""
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=None)

        assert credential_monitor.status == CredentialStatus.VALID

    def test_apply_token_invalid_expiry(self, credential_monitor):
        """Test applying a token with invalid expiry format sets VALID."""
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at="not-a-date")

        assert credential_monitor.status == CredentialStatus.VALID
        assert credential_monitor._expires_at is None

    def test_apply_token_resets_refresh_failures(self, credential_monitor):
        """Test that apply_token resets the refresh failure counter."""
        credential_monitor._refresh_failures = 5
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=None)

        assert credential_monitor._refresh_failures == 0

    def test_apply_token_updates_last_check(self, credential_monitor):
        """Test that apply_token updates _last_check."""
        assert credential_monitor._last_check is None
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=None)

        assert credential_monitor._last_check is not None

    def test_apply_token_z_suffix_expiry(self, credential_monitor):
        """Test applying a token with Z-suffixed expiry timestamp."""
        future = datetime.now(timezone.utc) + timedelta(days=60)
        z_format = future.isoformat().replace("+00:00", "Z")
        credential_monitor.apply_token("sk-ant-oat01-test", expires_at=z_format)

        assert credential_monitor.status == CredentialStatus.VALID
        assert credential_monitor._expires_at is not None
