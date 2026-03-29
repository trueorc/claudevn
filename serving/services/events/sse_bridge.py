"""SSE bridge — forwards event bus events to frontend clients.

Frontend clients connect via SSE and receive real-time events
instead of polling. Each client subscribes to event patterns
based on their current view.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional, Set
from pydantic import BaseModel

from .event_bus import EventBus, Subscription, get_event_bus

logger = logging.getLogger(__name__)


class SSEBridge:
    """Bridges the event bus to Server-Sent Events for frontend clients.

    Each connected frontend client gets a Subscription to the event bus.
    Events are serialized as SSE and streamed to the client.

    Usage (in a FastAPI endpoint):
        bridge = SSEBridge(get_event_bus())

        @app.get("/events")
        async def events(request: Request):
            patterns = {"decomposition.*", "execution.*", "verification.*"}
            return StreamingResponse(
                bridge.stream(patterns, client_id="browser-1"),
                media_type="text/event-stream"
            )
    """

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus or get_event_bus()
        self._active_streams: dict[str, Subscription] = {}

    async def stream(
        self,
        patterns: Set[str],
        client_id: str = "",
        keepalive_seconds: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """Generate SSE events for a frontend client.

        Args:
            patterns: Event patterns this client wants.
            client_id: Identifier for logging/debugging.
            keepalive_seconds: Interval for keepalive pings.

        Yields:
            SSE-formatted strings ("event: ...\ndata: ...\n\n")
        """
        sub = self._bus.subscribe(patterns, f"sse:{client_id}")
        self._active_streams[client_id] = sub

        try:
            logger.info(f"SSE stream started: {client_id} -> {patterns}")
            while True:
                event = await sub.receive_timeout(keepalive_seconds)
                if event is None:
                    # Keepalive
                    yield ": keepalive\n\n"
                else:
                    yield self._format_sse(event)
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled: {client_id}")
        finally:
            self._bus.unsubscribe(sub)
            self._active_streams.pop(client_id, None)

    def _format_sse(self, event: BaseModel) -> str:
        """Format a Pydantic event as an SSE message."""
        event_name = getattr(event, "event", "unknown")
        data = event.model_dump_json()
        return f"event: {event_name}\ndata: {data}\n\n"

    @property
    def active_client_count(self) -> int:
        """Number of currently connected SSE clients."""
        return len(self._active_streams)
