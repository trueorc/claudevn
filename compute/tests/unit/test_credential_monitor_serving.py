"""Tests for CredentialMonitor.fetch_from_serving method."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from services.credential_monitor import CredentialMonitor, CredentialStatus


@pytest.fixture
def tmp_creds_path(tmp_path):
    """Create a temporary credentials path."""
    return str(tmp_path / ".credentials.json")


@pytest.fixture
def monitor(tmp_creds_path):
    """Create a CredentialMonitor with temp path."""
    return CredentialMonitor(
        credentials_path=tmp_creds_path,
        check_interval=3600,
    )


class TestFetchFromServing:
    """Test fetch_from_serving method."""

    @pytest.mark.asyncio
    async def test_fetch_success(self, monitor, tmp_creds_path):
        """Test successful credential fetch from serving."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "credentials": {
                "access_token": "test-token-from-serving",
                "expires_at": "2026-12-01T00:00:00Z",
            },
            "expires_at": "2026-12-01T00:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            status = await monitor.fetch_from_serving("http://serving:8002/api/v1/auth")

        assert status == CredentialStatus.VALID
        assert Path(tmp_creds_path).exists()
        data = json.loads(Path(tmp_creds_path).read_text())
        assert data["access_token"] == "test-token-from-serving"

    @pytest.mark.asyncio
    async def test_fetch_503_no_creds(self, monitor, tmp_creds_path):
        """Test fetch when serving returns 503 (no credentials)."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            status = await monitor.fetch_from_serving("http://serving:8002/api/v1/auth")

        assert status == CredentialStatus.MISSING
        assert not Path(tmp_creds_path).exists()

    @pytest.mark.asyncio
    async def test_fetch_network_error(self, monitor, tmp_creds_path):
        """Test fetch when network error occurs."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            status = await monitor.fetch_from_serving("http://serving:8002/api/v1/auth")

        assert status == CredentialStatus.MISSING

    @pytest.mark.asyncio
    async def test_fetch_writes_with_correct_permissions(self, monitor, tmp_creds_path):
        """Test that fetched credentials file has 600 permissions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "credentials": {"access_token": "tok"},
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await monitor.fetch_from_serving("http://serving:8002/api/v1/auth")

        creds_path = Path(tmp_creds_path)
        assert creds_path.exists()
        mode = oct(creds_path.stat().st_mode)[-3:]
        assert mode == "600"

    @pytest.mark.asyncio
    async def test_fetch_trailing_slash_url(self, monitor, tmp_creds_path):
        """Test that URL trailing slash is handled."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"credentials": {"access_token": "tok"}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await monitor.fetch_from_serving("http://serving:8002/api/v1/auth/")

        # Verify the URL was correct (no double slash)
        call_args = mock_client.get.call_args
        assert "/auth//credentials" not in call_args[0][0]
