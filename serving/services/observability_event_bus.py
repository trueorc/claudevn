"""Event bus for observability events - receives from compute, broadcasts to frontend."""

import json
import logging
from pathlib import Path
from typing import Dict, Set, Callable, List, Optional
from datetime import datetime
from fastapi import WebSocket

from models.observability import (
    ObservabilityEvent,
    ActivityStateChangeEvent,
    ExchangeEvent,
    ProcessMapReevaluationEvent,
    BlockerEvent,
    ActivityGroupingEvent,
    SessionCreatedEvent,
    SessionCompletedEvent,
    WorkStatusChangeEvent,
    CommentEvaluationStatusEvent,
    ComputeRegisteredEvent,
    ComputeDeregisteredEvent
)
from services.process_map_service import get_process_map_service

logger = logging.getLogger(__name__)


class ObservabilityEventBus:
    """
    Central event bus for observability.
    
    Responsibilities:
    1. Receive events from compute instances
    2. Persist events to log files
    3. Update process map storage
    4. Broadcast events to WebSocket subscribers
    """
    
    def __init__(self, event_log_path: str = "./data/serving/observability_events"):
        """
        Initialize event bus.
        
        Args:
            event_log_path: Directory for event logs
        """
        self.event_log_path = Path(event_log_path)
        self.event_log_path.mkdir(parents=True, exist_ok=True)
        
        # WebSocket connections: session_id -> set of websocket connections
        self.subscribers: Dict[str, Set[WebSocket]] = {}

        # Global subscribers: receive ALL broadcast events (compute_registered, etc.)
        # without needing to subscribe to specific sessions
        self.global_subscribers: Set[WebSocket] = set()

        # Event handlers (for processing before broadcast)
        self.handlers: List[Callable] = []
        
        logger.info(f"ObservabilityEventBus initialized with log path: {self.event_log_path}")
    
    async def emit_event(self, event: ObservabilityEvent):
        """
        Receive event from compute, persist, and broadcast to subscribers.
        
        Args:
            event: The observability event
        """
        try:
            # 1. Persist event to log
            await self._persist_event(event)
            
            # 2. Update process map storage (if needed)
            await self._update_process_map(event)
            
            # 3. Run handlers (e.g., analytics, monitoring)
            for handler in self.handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Event handler failed: {e}")
            
            # 4. Broadcast to WebSocket subscribers
            await self._broadcast_event(event)
            
            logger.debug(f"Event processed: {event.event_type} for session {event.session_id}")
        
        except Exception as e:
            logger.error(f"Failed to process event {event.event_id}: {e}")
            raise
    
    async def _persist_event(self, event: ObservabilityEvent):
        """
        Persist event to JSONL log file.
        
        Args:
            event: Event to persist
        """
        log_file = self.event_log_path / f"{event.session_id}_events.jsonl"
        
        try:
            with open(log_file, 'a') as f:
                event_json = json.dumps(event.model_dump(), default=str)
                f.write(event_json + '\n')
        except Exception as e:
            logger.error(f"Failed to persist event to {log_file}: {e}")
            raise
    
    async def _update_process_map(self, event: ObservabilityEvent):
        """
        Update process map storage with event data.
        
        Args:
            event: Event to process
        """
        process_map_service = get_process_map_service()
        
        try:
            if isinstance(event, ActivityStateChangeEvent):
                # Update activity status in process map
                await process_map_service.update_activity_status(
                    session_id=event.session_id,
                    activity_id=event.activity_id,
                    status=event.new_status
                )
                
                # Store compute instance assignment
                activity = await process_map_service.get_activity(
                    session_id=event.session_id,
                    activity_id=event.activity_id
                )
                if activity and not hasattr(activity, 'compute_instance_id'):
                    activity.metadata['compute_instance_id'] = event.compute_instance_id
            
            elif isinstance(event, ExchangeEvent):
                # Add exchange to activity
                await process_map_service.add_exchange(
                    session_id=event.session_id,
                    activity_id=event.activity_id,
                    exchange=event.exchange
                )
            
            elif isinstance(event, ProcessMapReevaluationEvent):
                # Reevaluation already happened on compute
                # Event is for notification only
                pass
            
            elif isinstance(event, BlockerEvent):
                # Blocker already added to activity on compute
                # Event is for notification only
                pass
            
            elif isinstance(event, ActivityGroupingEvent):
                # Add group to process map
                process_map = await process_map_service.get_map(event.session_id)
                if process_map:
                    if not hasattr(process_map, 'activity_groups'):
                        process_map.activity_groups = {}
                        process_map.group_order = []
                    
                    process_map.activity_groups[event.group.group_id] = event.group
                    process_map.group_order.append(event.group.group_id)
                    
                    # Save updated map
                    await process_map_service._save_map(process_map)
        
        except Exception as e:
            logger.error(f"Failed to update process map for event {event.event_id}: {e}")
            # Don't raise - broadcast should still happen
    
    async def _broadcast_event(self, event: ObservabilityEvent):
        """
        Broadcast event to WebSocket subscribers.

        Args:
            event: Event to broadcast
        """
        # For work status events, comment evaluation events, and compute events, broadcast to ALL subscribers
        if isinstance(event, (WorkStatusChangeEvent, CommentEvaluationStatusEvent, ComputeRegisteredEvent, ComputeDeregisteredEvent)):
            await self._broadcast_to_all(event)
            return

        session_id = event.session_id

        if session_id not in self.subscribers or not self.subscribers[session_id]:
            # No subscribers for this session
            return

        # Serialize event
        message = json.dumps({
            'type': event.event_type,
            'event': event.dict()
        }, default=str)

        # Send to all subscribers for this session
        dead_connections = set()
        for ws in self.subscribers[session_id]:
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send event to WebSocket: {e}")
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.subscribers[session_id].discard(ws)
            logger.debug(f"Removed dead WebSocket connection for session {session_id}")

    async def _broadcast_to_all(self, event: ObservabilityEvent):
        """
        Broadcast event to ALL WebSocket subscribers (session-based and global).

        Args:
            event: Event to broadcast to all connected clients
        """
        if not self.subscribers and not self.global_subscribers:
            return

        message = json.dumps({
            'type': event.event_type,
            'event': event.dict()
        }, default=str)

        # Track all websockets we've already sent to (avoid duplicates)
        sent_to: Set[WebSocket] = set()
        dead_connections = []

        # Send to session-based subscribers
        for session_id, subscribers in self.subscribers.items():
            for ws in subscribers:
                if ws in sent_to:
                    continue
                try:
                    await ws.send_text(message)
                    sent_to.add(ws)
                except Exception as e:
                    logger.warning(f"Failed to send event to WebSocket: {e}")
                    dead_connections.append((session_id, ws))

        # Send to global subscribers (e.g., compute monitoring connections)
        dead_global = set()
        for ws in self.global_subscribers:
            if ws in sent_to:
                continue
            try:
                await ws.send_text(message)
                sent_to.add(ws)
            except Exception as e:
                logger.warning(f"Failed to send event to global WebSocket: {e}")
                dead_global.add(ws)

        # Clean up dead connections
        for session_id, ws in dead_connections:
            if session_id in self.subscribers:
                self.subscribers[session_id].discard(ws)
                if not self.subscribers[session_id]:
                    del self.subscribers[session_id]

        self.global_subscribers -= dead_global
    
    async def _broadcast_raw(self, message: str):
        """
        Broadcast a pre-serialized JSON string to ALL connected WebSocket clients.

        Used by services that need to push non-observability events (e.g.
        conversation messages) over the same WebSocket channel.

        Args:
            message: Pre-serialized JSON string to send
        """
        if not self.subscribers and not self.global_subscribers:
            return

        sent_to: Set[WebSocket] = set()
        dead_connections = []

        for session_id, subscribers in self.subscribers.items():
            for ws in subscribers:
                if ws in sent_to:
                    continue
                try:
                    await ws.send_text(message)
                    sent_to.add(ws)
                except Exception as e:
                    logger.warning(f"Failed to send raw message to WebSocket: {e}")
                    dead_connections.append((session_id, ws))

        dead_global: Set[WebSocket] = set()
        for ws in self.global_subscribers:
            if ws in sent_to:
                continue
            try:
                await ws.send_text(message)
                sent_to.add(ws)
            except Exception as e:
                logger.warning(f"Failed to send raw message to global WebSocket: {e}")
                dead_global.add(ws)

        for session_id, ws in dead_connections:
            if session_id in self.subscribers:
                self.subscribers[session_id].discard(ws)
                if not self.subscribers[session_id]:
                    del self.subscribers[session_id]

        self.global_subscribers -= dead_global

    def subscribe_global(self, websocket: WebSocket):
        """
        Subscribe WebSocket to all broadcast events (compute_registered, etc.).

        Global subscribers receive events from _broadcast_to_all without
        needing to subscribe to specific session IDs.

        Args:
            websocket: WebSocket connection
        """
        self.global_subscribers.add(websocket)
        logger.info("WebSocket subscribed globally for broadcast events")

    def unsubscribe_global(self, websocket: WebSocket):
        """
        Remove WebSocket from global subscribers.

        Args:
            websocket: WebSocket connection
        """
        self.global_subscribers.discard(websocket)

    def subscribe(self, session_id: str, websocket: WebSocket):
        """
        Subscribe WebSocket to session events.

        Args:
            session_id: Session to subscribe to
            websocket: WebSocket connection
        """
        if session_id not in self.subscribers:
            self.subscribers[session_id] = set()

        self.subscribers[session_id].add(websocket)
        logger.info(f"WebSocket subscribed to session {session_id}")
    
    def unsubscribe(self, session_id: str, websocket: WebSocket):
        """
        Unsubscribe WebSocket from session events.
        
        Args:
            session_id: Session to unsubscribe from
            websocket: WebSocket connection
        """
        if session_id in self.subscribers:
            self.subscribers[session_id].discard(websocket)
            
            # Clean up empty subscriber sets
            if not self.subscribers[session_id]:
                del self.subscribers[session_id]
            
            logger.info(f"WebSocket unsubscribed from session {session_id}")
    
    def unsubscribe_all(self, websocket: WebSocket):
        """
        Unsubscribe WebSocket from all sessions and global broadcasts.

        Args:
            websocket: WebSocket connection
        """
        sessions_to_remove = []
        for session_id, subscribers in self.subscribers.items():
            if websocket in subscribers:
                subscribers.discard(websocket)
                if not subscribers:
                    sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.subscribers[session_id]

        self.global_subscribers.discard(websocket)

        logger.info("WebSocket unsubscribed from all sessions")
    
    def add_handler(self, handler: Callable):
        """
        Add event handler.
        
        Args:
            handler: Async function that processes events
        """
        self.handlers.append(handler)
        logger.info(f"Added event handler: {handler.__name__}")
    
    async def get_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Retrieve events from log file.
        
        Args:
            session_id: Session ID
            event_type: Optional filter by event type
            limit: Optional limit on number of events
            
        Returns:
            List of events
        """
        log_file = self.event_log_path / f"{session_id}_events.jsonl"
        
        if not log_file.exists():
            return []
        
        events = []
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    event_dict = json.loads(line)
                    
                    # Filter by event type if specified
                    if event_type and event_dict.get('event_type') != event_type:
                        continue
                    
                    events.append(event_dict)
                    
                    # Check limit
                    if limit and len(events) >= limit:
                        break
        
        except Exception as e:
            logger.error(f"Failed to read events from {log_file}: {e}")
        
        return events
    
    def get_subscriber_count(self, session_id: Optional[str] = None) -> int:
        """
        Get number of subscribers.

        Args:
            session_id: Optional filter by session

        Returns:
            Number of subscribers
        """
        if session_id:
            return len(self.subscribers.get(session_id, set()))
        else:
            session_count = sum(len(subs) for subs in self.subscribers.values())
            return session_count + len(self.global_subscribers)


# Global instance
_event_bus: Optional[ObservabilityEventBus] = None


def get_event_bus() -> ObservabilityEventBus:
    """Get global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = ObservabilityEventBus()
    return _event_bus


def set_event_bus(event_bus: ObservabilityEventBus):
    """Set global event bus instance."""
    global _event_bus
    _event_bus = event_bus


