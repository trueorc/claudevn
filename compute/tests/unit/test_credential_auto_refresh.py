"""Tests for auto-refresh on credential expiry (#749)."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from services.credential_monitor import CredentialMonitor, CredentialStatus


@pytest.fixture
def tmp_creds(tmp_path):
    """Temporary credentials file path."""
    return tmp_path / ".credentials.json"


@pytest.fixture
def expired_creds_data():
    """Expired credentials."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    return {
        "accessToken": "test-token-expired",
        "expires_at": past.isoformat(),
    }


@pytest.fixture
def valid_creds_data():
    """Valid credentials with future expiry."""
    future = datetime.now(timezone.utc) + timedelta(days=60)
    return {
        "accessToken": "test-token-valid",
        "expires_at": future.isoformat(),
    }


def make_monitor(tmp_creds, auth_mode="serving", serving_auth_url="http://serving:8002/api/v1/auth"):
    """Create a monitor with auto-refresh config."""
    return CredentialMonitor(
        credentials_path=str(tmp_creds),
        check_interval=60,
        expiry_warning_days=7,
        auth_mode=auth_mode,
        serving_auth_url=serving_auth_url,
    )


class TestAutoRefreshTriggered:
    """Test that auto-refresh triggers on EXPIRED and MISSING statuses."""

    @pytest.mark.asyncio
    async def test_auto_refresh_on_expired(self, tmp_creds, expired_creds_data):
        """Should call fetch_from_serving when credentials are expired."""
        monitor = make_monitor(tmp_creds)
        tmp_creds.write_text(json.dumps(expired_creds_data))

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.VALID) as mock_fetch:
            await monitor._check_credentials()
            mock_fetch.assert_called_once_with("http://serving:8002/api/v1/auth")

    @pytest.mark.asyncio
    async def test_auto_refresh_on_missing(self, tmp_creds):
        """Should call fetch_from_serving when credentials file is missing."""
        monitor = make_monitor(tmp_creds)
        # Don't create the file — it's missing

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.VALID) as mock_fetch:
            await monitor._check_credentials()
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_auto_refresh_when_valid(self, tmp_creds, valid_creds_data):
        """Should NOT call fetch_from_serving when credentials are valid."""
        monitor = make_monitor(tmp_creds)
        tmp_creds.write_text(json.dumps(valid_creds_data))

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock) as mock_fetch:
            await monitor._check_credentials()
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_auto_refresh_without_serving_mode(self, tmp_creds, expired_creds_data):
        """Should NOT auto-refresh when auth_mode is not 'serving'."""
        monitor = make_monitor(tmp_creds, auth_mode=None)
        tmp_creds.write_text(json.dumps(expired_creds_data))

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock) as mock_fetch:
            await monitor._check_credentials()
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_auto_refresh_without_url(self, tmp_creds, expired_creds_data):
        """Should NOT auto-refresh when serving_auth_url is not set."""
        monitor = make_monitor(tmp_creds, serving_auth_url=None)
        tmp_creds.write_text(json.dumps(expired_creds_data))

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock) as mock_fetch:
            await monitor._check_credentials()
            mock_fetch.assert_not_called()


class TestAutoRefreshBackoff:
    """Test exponential backoff on repeated failures."""

    @pytest.mark.asyncio
    async def test_no_backoff_on_first_attempt(self, tmp_creds, expired_creds_data):
        """First auto-refresh should not sleep."""
        monitor = make_monitor(tmp_creds)
        tmp_creds.write_text(json.dumps(expired_creds_data))

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.EXPIRED):
            with patch("services.credential_monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await monitor._auto_refresh()
                mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_backoff_after_failure(self, tmp_creds, expired_creds_data):
        """Subsequent attempts should have increasing backoff."""
        monitor = make_monitor(tmp_creds)
        monitor._refresh_failures = 1  # simulate one prior failure

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.EXPIRED):
            with patch("services.credential_monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await monitor._auto_refresh()
                # 2^1 * 10 = 20 seconds
                mock_sleep.assert_called_once_with(20)

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max(self, tmp_creds):
        """Backoff should not exceed max_refresh_backoff."""
        monitor = make_monitor(tmp_creds)
        monitor._refresh_failures = 20  # would be 2^20 * 10 = huge

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.EXPIRED):
            with patch("services.credential_monitor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await monitor._auto_refresh()
                mock_sleep.assert_called_once_with(3600)

    @pytest.mark.asyncio
    async def test_failures_reset_on_success(self, tmp_creds):
        """Failure counter should reset after successful refresh."""
        monitor = make_monitor(tmp_creds)
        monitor._refresh_failures = 3

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.VALID):
            with patch("services.credential_monitor.asyncio.sleep", new_callable=AsyncMock):
                await monitor._auto_refresh()
                assert monitor._refresh_failures == 0

    @pytest.mark.asyncio
    async def test_failures_increment_on_failure(self, tmp_creds):
        """Failure counter should increment on failed refresh."""
        monitor = make_monitor(tmp_creds)
        assert monitor._refresh_failures == 0

        with patch.object(monitor, "fetch_from_serving", new_callable=AsyncMock, return_value=CredentialStatus.MISSING):
            await monitor._auto_refresh()
            assert monitor._refresh_failures == 1
