"""Unit tests for credential monitor service."""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.credential_monitor import (
    CredentialMonitor,
    CredentialStatus,
    get_credential_monitor,
    set_credential_monitor,
    initialize_credential_monitor,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_creds(tmp_path):
    """Create a temporary credentials file."""
    creds_file = tmp_path / ".credentials.json"
    return creds_file


@pytest.fixture
def valid_creds_data():
    """Valid credentials with expiry far in the future."""
    future = datetime.now(timezone.utc) + timedelta(days=60)
    return {
        "accessToken": "test-token-12345",
        "expires_at": future.isoformat(),
    }


@pytest.fixture
def expiring_creds_data():
    """Credentials expiring within warning window."""
    soon = datetime.now(timezone.utc) + timedelta(days=3)
    return {
        "accessToken": "test-token-expiring",
        "expires_at": soon.isoformat(),
    }


@pytest.fixture
def expired_creds_data():
    """Expired credentials."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    return {
        "accessToken": "test-token-expired",
        "expires_at": past.isoformat(),
    }


@pytest.fixture
def monitor(tmp_creds):
    """Create a credential monitor with test path."""
    return CredentialMonitor(
        credentials_path=str(tmp_creds),
        check_interval=60,
        expiry_warning_days=7,
    )


# =============================================================================
# CredentialMonitor Init
# =============================================================================


class TestCredentialMonitorInit:
    """Tests for CredentialMonitor initialization."""

    def test_default_status_is_missing(self, monitor):
        """Initial status should be MISSING before first check."""
        assert monitor.status == CredentialStatus.MISSING

    def test_path_expansion(self, tmp_path):
        """Tilde paths should be expanded."""
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            m = CredentialMonitor(credentials_path="~/test.json")
            assert "~" not in str(m._credentials_path)

    def test_is_valid_false_initially(self, monitor):
        """is_valid should be False before check."""
        assert monitor.is_valid is False

    def test_is_usable_false_initially(self, monitor):
        """is_usable should be False before check."""
        assert monitor.is_usable is False


# =============================================================================
# Credential Checking
# =============================================================================


class TestCredentialChecking:
    """Tests for credential check logic."""

    @pytest.mark.asyncio
    async def test_missing_file(self, monitor):
        """Status should be MISSING when file doesn't exist."""
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.MISSING

    @pytest.mark.asyncio
    async def test_valid_credentials(self, monitor, tmp_creds, valid_creds_data):
        """Status should be VALID with good token and far expiry."""
        tmp_creds.write_text(json.dumps(valid_creds_data))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.VALID
        assert monitor.is_valid is True
        assert monitor.is_usable is True

    @pytest.mark.asyncio
    async def test_expiring_credentials(self, monitor, tmp_creds, expiring_creds_data):
        """Status should be EXPIRING within warning window."""
        tmp_creds.write_text(json.dumps(expiring_creds_data))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.EXPIRING
        assert monitor.is_valid is False
        assert monitor.is_usable is True

    @pytest.mark.asyncio
    async def test_expired_credentials(self, monitor, tmp_creds, expired_creds_data):
        """Status should be EXPIRED when past expiry."""
        tmp_creds.write_text(json.dumps(expired_creds_data))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.EXPIRED
        assert monitor.is_valid is False
        assert monitor.is_usable is False

    @pytest.mark.asyncio
    async def test_invalid_json(self, monitor, tmp_creds):
        """Status should be UNREADABLE when file has invalid JSON."""
        tmp_creds.write_text("not json at all")
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.UNREADABLE

    @pytest.mark.asyncio
    async def test_token_without_expiry(self, monitor, tmp_creds):
        """Status should be VALID when token exists but no expiry."""
        tmp_creds.write_text(json.dumps({"accessToken": "test-token"}))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.VALID

    @pytest.mark.asyncio
    async def test_empty_object(self, monitor, tmp_creds):
        """Status should be MISSING when file has empty object."""
        tmp_creds.write_text(json.dumps({}))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.MISSING

    @pytest.mark.asyncio
    async def test_unix_timestamp_expiry(self, monitor, tmp_creds):
        """Should handle numeric unix timestamps for expires_at."""
        future = datetime.now(timezone.utc) + timedelta(days=60)
        tmp_creds.write_text(json.dumps({
            "accessToken": "token",
            "expires_at": future.timestamp(),
        }))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.VALID

    @pytest.mark.asyncio
    async def test_alternate_field_names(self, monitor, tmp_creds):
        """Should recognize alternate credential field names."""
        tmp_creds.write_text(json.dumps({
            "claudeAiOauth": {"token": "abc"},
        }))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.VALID

    @pytest.mark.asyncio
    async def test_last_check_updated(self, monitor, tmp_creds, valid_creds_data):
        """last_check should be updated after each check."""
        assert monitor._last_check is None
        tmp_creds.write_text(json.dumps(valid_creds_data))
        await monitor._check_credentials()
        assert monitor._last_check is not None

    @pytest.mark.asyncio
    async def test_last_modified_tracked(self, monitor, tmp_creds, valid_creds_data):
        """File mtime should be tracked."""
        tmp_creds.write_text(json.dumps(valid_creds_data))
        await monitor._check_credentials()
        assert monitor._last_modified is not None


# =============================================================================
# Status Change Notification
# =============================================================================


class TestStatusNotification:
    """Tests for credential status change callbacks."""

    @pytest.mark.asyncio
    async def test_callback_on_expiring(self, tmp_creds, expiring_creds_data):
        """Event callback should fire when status changes to EXPIRING."""
        callback = AsyncMock()
        m = CredentialMonitor(
            credentials_path=str(tmp_creds),
            check_interval=60,
            expiry_warning_days=7,
            event_callback=callback,
        )
        tmp_creds.write_text(json.dumps(expiring_creds_data))
        await m._check_credentials()

        callback.assert_called_once()
        args = callback.call_args
        assert args[0][0] == "credentials_expiring"
        assert args[0][1]["status"] == "expiring"

    @pytest.mark.asyncio
    async def test_callback_on_expired(self, tmp_creds, expired_creds_data):
        """Event callback should fire when status changes to EXPIRED."""
        callback = AsyncMock()
        m = CredentialMonitor(
            credentials_path=str(tmp_creds),
            check_interval=60,
            expiry_warning_days=7,
            event_callback=callback,
        )
        tmp_creds.write_text(json.dumps(expired_creds_data))
        await m._check_credentials()

        callback.assert_called_once()
        args = callback.call_args
        assert args[0][0] == "credentials_expiring"
        assert args[0][1]["status"] == "expired"

    @pytest.mark.asyncio
    async def test_no_callback_when_valid(self, tmp_creds, valid_creds_data):
        """Event callback should NOT fire when status is VALID."""
        callback = AsyncMock()
        m = CredentialMonitor(
            credentials_path=str(tmp_creds),
            check_interval=60,
            expiry_warning_days=7,
            event_callback=callback,
        )
        tmp_creds.write_text(json.dumps(valid_creds_data))
        await m._check_credentials()

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_callback_when_status_unchanged(self, tmp_creds):
        """Callback should not fire when status doesn't change."""
        callback = AsyncMock()
        m = CredentialMonitor(
            credentials_path=str(tmp_creds),
            check_interval=60,
            expiry_warning_days=7,
            event_callback=callback,
        )
        # Two checks with missing file — status stays MISSING
        await m._check_credentials()
        await m._check_credentials()
        # MISSING is not EXPIRING/EXPIRED, so no callback
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_error_handled(self, tmp_creds, expiring_creds_data):
        """Callback errors should be caught, not propagated."""
        callback = AsyncMock(side_effect=RuntimeError("callback failed"))
        m = CredentialMonitor(
            credentials_path=str(tmp_creds),
            check_interval=60,
            expiry_warning_days=7,
            event_callback=callback,
        )
        tmp_creds.write_text(json.dumps(expiring_creds_data))
        # Should not raise
        await m._check_credentials()
        assert m.status == CredentialStatus.EXPIRING


# =============================================================================
# Reload Credentials
# =============================================================================


class TestReloadCredentials:
    """Tests for the reload_credentials method (SIGHUP handler)."""

    @pytest.mark.asyncio
    async def test_reload_updates_status(self, monitor, tmp_creds, valid_creds_data):
        """reload_credentials should re-check and return new status."""
        tmp_creds.write_text(json.dumps(valid_creds_data))
        result = await monitor.reload_credentials()
        assert result == CredentialStatus.VALID
        assert monitor.status == CredentialStatus.VALID

    @pytest.mark.asyncio
    async def test_reload_detects_transition(self, monitor, tmp_creds, valid_creds_data, expired_creds_data):
        """Reload should detect transition from valid to expired."""
        tmp_creds.write_text(json.dumps(valid_creds_data))
        await monitor._check_credentials()
        assert monitor.status == CredentialStatus.VALID

        # Credentials expire
        tmp_creds.write_text(json.dumps(expired_creds_data))
        result = await monitor.reload_credentials()
        assert result == CredentialStatus.EXPIRED


# =============================================================================
# get_status
# =============================================================================


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_get_status_fields(self, monitor, tmp_creds, valid_creds_data):
        """get_status should return all expected fields."""
        tmp_creds.write_text(json.dumps(valid_creds_data))
        await monitor._check_credentials()

        status = monitor.get_status()
        assert status["status"] == "valid"
        assert status["credentials_valid"] is True
        assert status["credentials_path"] == str(tmp_creds)
        assert status["expires_at"] is not None
        assert status["last_check"] is not None
        assert status["last_modified"] is not None
        assert status["check_interval"] == 60
        assert status["expiry_warning_days"] == 7

    def test_get_status_initial(self, monitor):
        """get_status should work before any check."""
        status = monitor.get_status()
        assert status["status"] == "missing"
        assert status["credentials_valid"] is False
        assert status["expires_at"] is None
        assert status["last_check"] is None


# =============================================================================
# Global Instance Management
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance get/set."""

    def test_get_set_credential_monitor(self, monitor):
        """set/get should round-trip the monitor instance."""
        set_credential_monitor(monitor)
        assert get_credential_monitor() is monitor
        # Cleanup
        set_credential_monitor(None)

    @pytest.mark.asyncio
    async def test_initialize_credential_monitor(self, tmp_creds, valid_creds_data):
        """initialize_credential_monitor should create, set global, and start."""
        tmp_creds.write_text(json.dumps(valid_creds_data))
        m = await initialize_credential_monitor(
            credentials_path=str(tmp_creds),
            check_interval=9999,
            expiry_warning_days=7,
        )
        try:
            assert get_credential_monitor() is m
            assert m.status == CredentialStatus.VALID
        finally:
            await m.stop()
            set_credential_monitor(None)
