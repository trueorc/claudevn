"""Unit tests for approved/rejected SSE event handlers (#132).

Tests that compute instances:
- Handle 'approved' events by storing project_ids and approved state
- Handle 'rejected' events by logging and initiating shutdown
- Are resilient to missing/unexpected fields in event data
"""

import sys
from unittest.mock import MagicMock

# Mock external dependencies not available in test environment
_mock_sdk = MagicMock()
for mod in (
    "claude_agent_sdk",
    "claude_agent_sdk.client",
    "claude_agent_sdk._internal",
    "claude_agent_sdk._internal.message_parser",
):
    if mod not in sys.modules:
        sys.modules[mod] = _mock_sdk

import pytest
from unittest.mock import AsyncMock, patch

from services.sse_event_client import SSEEventClient


@pytest.fixture
def client():
    """Create an SSE event client for testing."""
    return SSEEventClient(
        serving_url="http://serving:8002",
        compute_id="compute-001",
        api_key="test-key",
        capabilities=["agent-a"],
        resources={},
        reconnect_delay=1,
        max_reconnect_delay=5,
    )


# =============================================================================
# Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Verify approved/rejected handlers are registered."""

    def test_approved_handler_registered(self, client):
        """'approved' event has a registered handler."""
        assert "approved" in client._handlers
        assert len(client._handlers["approved"]) == 1

    def test_rejected_handler_registered(self, client):
        """'rejected' event has a registered handler."""
        assert "rejected" in client._handlers
        assert len(client._handlers["rejected"]) == 1


# =============================================================================
# Approved Handler
# =============================================================================


class TestHandleApproved:
    """Tests for _handle_approved event handler."""

    @pytest.mark.asyncio
    async def test_sets_approved_flag(self, client):
        """Approved event sets is_approved to True."""
        assert client.is_approved is False

        await client._handle_approved("approved", {
            "status": "online",
            "project_ids": ["proj-1"],
        })

        assert client.is_approved is True

    @pytest.mark.asyncio
    async def test_stores_project_ids(self, client):
        """Approved event stores assigned project_ids."""
        assert client.project_ids == []

        await client._handle_approved("approved", {
            "status": "online",
            "project_ids": ["proj-1", "proj-2"],
        })

        assert client.project_ids == ["proj-1", "proj-2"]

    @pytest.mark.asyncio
    async def test_empty_project_ids(self, client):
        """Approved with empty project_ids stores empty list (benched)."""
        await client._handle_approved("approved", {
            "status": "online",
            "project_ids": [],
        })

        assert client.is_approved is True
        assert client.project_ids == []

    @pytest.mark.asyncio
    async def test_missing_project_ids_defaults_empty(self, client):
        """Missing project_ids field defaults to empty list."""
        await client._handle_approved("approved", {
            "status": "online",
        })

        assert client.is_approved is True
        assert client.project_ids == []

    @pytest.mark.asyncio
    async def test_missing_status_no_crash(self, client):
        """Missing status field does not crash."""
        await client._handle_approved("approved", {
            "project_ids": ["proj-1"],
        })

        assert client.is_approved is True
        assert client.project_ids == ["proj-1"]

    @pytest.mark.asyncio
    async def test_empty_data_no_crash(self, client):
        """Empty event data does not crash."""
        await client._handle_approved("approved", {})

        assert client.is_approved is True
        assert client.project_ids == []


# =============================================================================
# Rejected Handler
# =============================================================================


class TestHandleRejected:
    """Tests for _handle_rejected event handler."""

    @pytest.mark.asyncio
    async def test_initiates_shutdown(self, client):
        """Rejected event calls stop() for graceful shutdown."""
        client._running = True
        with patch.object(client, "stop", new_callable=AsyncMock) as mock_stop:
            await client._handle_rejected("rejected", {
                "status": "rejected",
                "message": "Not authorized",
            })

            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_message_no_crash(self, client):
        """Missing message field does not crash."""
        with patch.object(client, "stop", new_callable=AsyncMock):
            await client._handle_rejected("rejected", {
                "status": "rejected",
            })
        # No exception raised

    @pytest.mark.asyncio
    async def test_empty_data_no_crash(self, client):
        """Empty event data does not crash."""
        with patch.object(client, "stop", new_callable=AsyncMock):
            await client._handle_rejected("rejected", {})
        # No exception raised

    @pytest.mark.asyncio
    async def test_does_not_set_approved(self, client):
        """Rejected event does not set approved flag."""
        with patch.object(client, "stop", new_callable=AsyncMock):
            await client._handle_rejected("rejected", {
                "status": "rejected",
                "message": "Denied",
            })

        assert client.is_approved is False


# =============================================================================
# Integration: Event Dispatch
# =============================================================================


class TestEventDispatch:
    """Test approved/rejected events dispatched through _handle_event."""

    @pytest.mark.asyncio
    async def test_approved_event_dispatched(self, client):
        """Approved event dispatched through the normal event pipeline."""
        await client._handle_event("approved", '{"status": "online", "project_ids": ["proj-1"]}')

        assert client.is_approved is True
        assert client.project_ids == ["proj-1"]

    @pytest.mark.asyncio
    async def test_rejected_event_dispatched(self, client):
        """Rejected event dispatched through the normal event pipeline."""
        with patch.object(client, "stop", new_callable=AsyncMock):
            await client._handle_event("rejected", '{"status": "rejected", "message": "Denied"}')
        # No crash, stop was called

    @pytest.mark.asyncio
    async def test_malformed_json_no_crash(self, client):
        """Malformed JSON in event data does not crash."""
        await client._handle_event("approved", "not valid json")
        # Should log error, not crash
        assert client.is_approved is False
