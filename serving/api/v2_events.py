"""SSE event stream endpoint for v2.0 real-time updates.

Replaces all polling with push-based event delivery.
Project-scoped — clients only receive events for their project.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from services.events.event_bus import get_event_bus
from services.events.sse_bridge import SSEBridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

_bridge: Optional[SSEBridge] = None


def _get_bridge() -> SSEBridge:
    global _bridge
    if _bridge is None:
        _bridge = SSEBridge(get_event_bus())
    return _bridge


@router.get("/stream")
async def event_stream(
    request: Request,
    pattern: List[str] = Query(default=["*"], description="Event patterns to subscribe to"),
    client_id: str = Query(default="", description="Client identifier"),
    project_id: Optional[str] = Query(default=None, description="Project to scope events to"),
):
    """Server-Sent Events stream for real-time updates.

    Subscribe to event patterns (e.g., decomposition.*, verification.*)
    scoped to a specific project. Events are pushed as they occur —
    no polling needed.
    """
    bridge = _get_bridge()

    return StreamingResponse(
        bridge.stream(
            patterns=set(pattern),
            client_id=client_id,
            project_id=project_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/clients")
async def get_connected_clients():
    """Get the number of connected SSE clients."""
    bridge = _get_bridge()
    return {"active_clients": bridge.active_client_count}
