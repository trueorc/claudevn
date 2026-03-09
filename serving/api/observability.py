"""Observability API endpoints for real-time monitoring."""

import json
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends

from models.observability import (
    ObservabilityEvent,
    ActivityStateChangeEvent,
    ExchangeEvent,
    ProcessMapReevaluationEvent,
    BlockerEvent,
    ActivityGroupingEvent,
    SessionCreatedEvent,
    SessionCompletedEvent,
    AgentExecutionStartedEvent,
    AgentExecutionCompletedEvent,
    LLMCallMadeEvent,
    EventSubmissionResponse,
    WebSocketSubscription
)
from services.observability_event_bus import get_event_bus, ObservabilityEventBus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])


@router.post("/events", response_model=EventSubmissionResponse)
async def submit_event(
    event: ObservabilityEvent,
    event_bus: ObservabilityEventBus = Depends(get_event_bus)
):
    """
    Receive observability event from compute instance.
    
    This endpoint is called by compute instances when:
    - Activity status changes (start, complete, blocked)
    - Exchanges occur (throttled)
    - Process map is reevaluated
    - Blockers are identified
    - Activities are grouped
    - Session is created/completed
    
    Args:
        event: The observability event
        event_bus: Event bus service (injected)
    
    Returns:
        EventSubmissionResponse with status and event ID
    """
    try:
        # Emit event (persist, update process map, broadcast)
        await event_bus.emit_event(event)
        
        return EventSubmissionResponse(
            status="accepted",
            event_id=event.event_id,
            timestamp=event.timestamp
        )
    
    except Exception as e:
        logger.error(f"Failed to process event {event.event_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process event: {str(e)}"
        )


@router.websocket("/stream")
async def observability_stream(
    websocket: WebSocket,
    event_bus: ObservabilityEventBus = Depends(get_event_bus)
):
    """
    WebSocket endpoint for real-time observability updates.
    
    Protocol:
    
    Client → Server:
    {
      "action": "subscribe",
      "session_ids": ["session-abc", "session-xyz"]
    }
    
    Server → Client:
    {
      "type": "activity_state_change",
      "event": { /* ActivityStateChangeEvent */ }
    }
    
    Heartbeat:
    Server → Client: {"type": "ping", "timestamp": "..."}
    Client → Server: {"action": "pong", "timestamp": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    # Auto-register as global subscriber so this connection receives
    # broadcast events (compute_registered, compute_deregistered, etc.)
    # without needing to subscribe to specific session IDs
    event_bus.subscribe_global(websocket)

    subscribed_sessions = set()

    try:
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({
            'type': 'connected',
            'message': 'WebSocket connection established'
        }))
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get('action')
            
            if action == 'subscribe':
                # Subscribe to sessions
                session_ids = message.get('session_ids', [])
                
                for session_id in session_ids:
                    event_bus.subscribe(session_id, websocket)
                    subscribed_sessions.add(session_id)
                
                await websocket.send_text(json.dumps({
                    'type': 'subscribed',
                    'session_ids': session_ids,
                    'total_subscriptions': len(subscribed_sessions)
                }))
                
                logger.info(f"WebSocket subscribed to {len(session_ids)} session(s)")
            
            elif action == 'unsubscribe':
                # Unsubscribe from sessions
                session_ids = message.get('session_ids', [])
                
                for session_id in session_ids:
                    event_bus.unsubscribe(session_id, websocket)
                    subscribed_sessions.discard(session_id)
                
                await websocket.send_text(json.dumps({
                    'type': 'unsubscribed',
                    'session_ids': session_ids,
                    'total_subscriptions': len(subscribed_sessions)
                }))
                
                logger.info(f"WebSocket unsubscribed from {len(session_ids)} session(s)")
            
            elif action == 'typing':
                # User typing state change — notify AI agent
                project_id = message.get('project_id')
                user_id = message.get('user_id')
                is_typing = message.get('is_typing', False)
                if project_id and user_id:
                    try:
                        from services.ai_chat_agent_service import get_ai_chat_agent_service
                        agent = get_ai_chat_agent_service()
                        if agent:
                            agent.on_typing(project_id, user_id, is_typing)
                    except Exception:
                        pass  # Best-effort, don't break the WebSocket

            elif action == 'pong':
                # Heartbeat response (no action needed)
                pass

            else:
                # Unknown action
                await websocket.send_text(json.dumps({
                    'type': 'error',
                    'message': f'Unknown action: {action}'
                }))
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up subscriptions
        event_bus.unsubscribe_all(websocket)
        logger.info(f"WebSocket cleaned up ({len(subscribed_sessions)} subscriptions removed)")


@router.get("/events/{session_id}")
async def get_session_events(
    session_id: str,
    event_type: Optional[str] = None,
    limit: Optional[int] = 100,
    event_bus: ObservabilityEventBus = Depends(get_event_bus)
):
    """
    Retrieve events for a session from event log.
    
    Args:
        session_id: Session ID
        event_type: Optional filter by event type
        limit: Maximum number of events to return
        event_bus: Event bus service (injected)
    
    Returns:
        List of events
    """
    try:
        events = await event_bus.get_events(
            session_id=session_id,
            event_type=event_type,
            limit=limit
        )
        
        return {
            "session_id": session_id,
            "event_count": len(events),
            "events": events
        }
    
    except Exception as e:
        logger.error(f"Failed to retrieve events for session {session_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve events: {str(e)}"
        )


@router.get("/stats")
async def get_observability_stats(
    event_bus: ObservabilityEventBus = Depends(get_event_bus)
):
    """
    Get observability statistics.
    
    Returns:
        Statistics about WebSocket connections and event processing
    """
    return {
        "total_subscribers": event_bus.get_subscriber_count(),
        "active_sessions": len(event_bus.subscribers),
        "event_handlers": len(event_bus.handlers)
    }


