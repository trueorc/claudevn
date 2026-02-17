"""Unit tests for ObservabilityEventBus global subscriber support."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.observability_event_bus import ObservabilityEventBus


class FakeWebSocket:
    """Fake WebSocket for testing."""

    def __init__(self, should_fail=False):
        self.sent_messages = []
        self.should_fail = should_fail

    async def send_text(self, message):
        if self.should_fail:
            raise ConnectionError("Connection closed")
        self.sent_messages.append(message)


class FakeEvent:
    """Fake observability event for testing."""

    def __init__(self, event_type="compute_registered", session_id="global", event_id="test-1"):
        self.event_type = event_type
        self.session_id = session_id
        self.event_id = event_id

    def model_dump(self):
        return {"event_type": self.event_type, "session_id": self.session_id, "event_id": self.event_id}

    def dict(self):
        return self.model_dump()


@pytest.fixture
def event_bus(tmp_path):
    return ObservabilityEventBus(event_log_path=str(tmp_path / "events"))


class TestGlobalSubscribers:
    """Tests for global subscriber functionality."""

    def test_subscribe_global(self, event_bus):
        ws = FakeWebSocket()
        event_bus.subscribe_global(ws)
        assert ws in event_bus.global_subscribers

    def test_unsubscribe_global(self, event_bus):
        ws = FakeWebSocket()
        event_bus.subscribe_global(ws)
        event_bus.unsubscribe_global(ws)
        assert ws not in event_bus.global_subscribers

    def test_unsubscribe_global_not_subscribed(self, event_bus):
        ws = FakeWebSocket()
        # Should not raise
        event_bus.unsubscribe_global(ws)

    def test_unsubscribe_all_clears_global(self, event_bus):
        ws = FakeWebSocket()
        event_bus.subscribe_global(ws)
        event_bus.subscribe("session-1", ws)
        event_bus.unsubscribe_all(ws)
        assert ws not in event_bus.global_subscribers
        assert "session-1" not in event_bus.subscribers

    def test_subscriber_count_includes_global(self, event_bus):
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        event_bus.subscribe("session-1", ws1)
        event_bus.subscribe_global(ws2)
        assert event_bus.get_subscriber_count() == 2


class TestBroadcastToAll:
    """Tests for _broadcast_to_all with global subscribers."""

    @pytest.mark.asyncio
    async def test_broadcast_reaches_global_subscribers(self, event_bus):
        ws = FakeWebSocket()
        event_bus.subscribe_global(ws)

        event = FakeEvent()
        await event_bus._broadcast_to_all(event)

        assert len(ws.sent_messages) == 1
        parsed = json.loads(ws.sent_messages[0])
        assert parsed["type"] == "compute_registered"

    @pytest.mark.asyncio
    async def test_broadcast_reaches_session_and_global(self, event_bus):
        ws_session = FakeWebSocket()
        ws_global = FakeWebSocket()
        event_bus.subscribe("session-1", ws_session)
        event_bus.subscribe_global(ws_global)

        event = FakeEvent()
        await event_bus._broadcast_to_all(event)

        assert len(ws_session.sent_messages) == 1
        assert len(ws_global.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_broadcast_deduplicates_same_ws(self, event_bus):
        """A WS that is both session-subscribed and global should only get one message."""
        ws = FakeWebSocket()
        event_bus.subscribe("session-1", ws)
        event_bus.subscribe_global(ws)

        event = FakeEvent()
        await event_bus._broadcast_to_all(event)

        assert len(ws.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_broadcast_no_subscribers(self, event_bus):
        """No subscribers at all should not raise."""
        event = FakeEvent()
        await event_bus._broadcast_to_all(event)

    @pytest.mark.asyncio
    async def test_broadcast_cleans_dead_global_connections(self, event_bus):
        ws_dead = FakeWebSocket(should_fail=True)
        ws_alive = FakeWebSocket()
        event_bus.subscribe_global(ws_dead)
        event_bus.subscribe_global(ws_alive)

        event = FakeEvent()
        await event_bus._broadcast_to_all(event)

        # Dead connection should be removed
        assert ws_dead not in event_bus.global_subscribers
        assert ws_alive in event_bus.global_subscribers
        assert len(ws_alive.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_broadcast_cleans_dead_session_connections(self, event_bus):
        ws_dead = FakeWebSocket(should_fail=True)
        event_bus.subscribe("session-1", ws_dead)

        event = FakeEvent()
        await event_bus._broadcast_to_all(event)

        # Dead connection should be removed, empty session cleaned up
        assert "session-1" not in event_bus.subscribers
