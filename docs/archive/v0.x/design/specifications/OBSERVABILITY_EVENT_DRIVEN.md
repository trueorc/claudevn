# Event-Driven Observability Architecture

**Version**: 2.0  
**Date**: November 25, 2025  
**Status**: Revised Design - Event-Driven

## Overview

This document describes the **event-driven architecture** for process map observability, where compute instances push activity state changes to the serving component in near real-time (1-3 second latency).

---

## Architecture: Push, Not Pull

### Previous Design (Rejected)
❌ Frontend polls Serving every 3-5 seconds  
❌ Serving queries process maps from storage  
❌ 5+ second latency

### New Design (Event-Driven)
✅ Compute pushes events to Serving when activities start/complete  
✅ Serving streams updates to Frontend via WebSocket  
✅ 1-3 second latency (near real-time)

---

## Data Flow

```
Compute Instance (Activity State Change)
    ↓
    HTTP POST /api/v1/observability/events
    ↓
Serving Component (Event Bus)
    ↓
    WebSocket Broadcast
    ↓
Frontend (Real-Time UI Update)
```

### Event Flow Details

1. **Activity Start**: Compute sends event when Activity Facilitator begins facilitation
2. **Activity Progress**: Compute sends event after each exchange (optional, throttled)
3. **Activity Complete**: Compute sends event when activity reaches goal_met or blocked
4. **Blocker Identified**: Compute sends event when blocker detected
5. **Reevaluation**: Compute sends event when process map restructures

---

## Event Types

### ActivityStateChangeEvent

```python
class ActivityStateChangeEvent(BaseModel):
    """Event emitted when activity status changes."""
    event_type: str = "activity_state_change"
    event_id: str  # Unique event ID
    timestamp: datetime
    session_id: str
    activity_id: str
    
    # State change
    old_status: ActivityStatus
    new_status: ActivityStatus
    
    # Execution context
    compute_instance_id: str
    agent_id: Optional[str]  # Agent performing the activity
    
    # Progress details
    exchange_count: Optional[int]
    duration_seconds: Optional[int]
    
    # Blocker info (if status = blocked)
    blocker: Optional[Blocker]
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### ExchangeEvent

```python
class ExchangeEvent(BaseModel):
    """Event emitted after each exchange (throttled)."""
    event_type: str = "exchange"
    event_id: str
    timestamp: datetime
    session_id: str
    activity_id: str
    
    # Exchange details
    exchange: Exchange  # Full exchange object
    
    # Context
    compute_instance_id: str
    exchange_number: int  # 1-indexed
    total_exchanges: int  # Running total
    
    # Throttling: Only emit every Nth exchange or on important exchanges
    # (e.g., every 5th exchange, or ASSESS/CONCLUDE intents)
```

### ProcessMapReevaluationEvent

```python
class ProcessMapReevaluationEvent(BaseModel):
    """Event emitted when process map is reevaluated."""
    event_type: str = "process_map_reevaluation"
    event_id: str
    timestamp: datetime
    session_id: str
    
    # Reevaluation details
    reevaluation: ReevaluationEvent  # From process_map.py
    previous_version: int
    new_version: int
    
    # What changed
    activities_added: List[str]
    activities_removed: List[str]
    activities_modified: List[str]
    dependencies_changed: Dict[str, List[str]]  # activity_id -> new deps
    
    # Context
    triggered_by: str
    reasoning: str
```

### BlockerEvent

```python
class BlockerEvent(BaseModel):
    """Event emitted when blocker is identified."""
    event_type: str = "blocker_identified"
    event_id: str
    timestamp: datetime
    session_id: str
    activity_id: str
    
    # Blocker details
    blocker: Blocker
    
    # Impact
    affected_activities: List[str]  # Other activities this blocks
    severity: str  # "critical", "moderate", "minor"
    
    # Context
    identified_by: str  # Agent ID
    compute_instance_id: str
```

### ActivityGroupingEvent

```python
class ActivityGroupingEvent(BaseModel):
    """Event emitted when activities are grouped (new!)."""
    event_type: str = "activity_grouping"
    event_id: str
    timestamp: datetime
    session_id: str
    
    # Grouping details
    group_id: str
    group_name: str  # e.g., "Decomposition & Planning", "Data Collection"
    group_description: Optional[str]
    
    # Activities in this group
    activity_ids: List[str]
    
    # Group status (derived from activities)
    group_status: str  # "proposed", "in_progress", "completed", "blocked"
    
    # Can this group be collapsed?
    collapsible: bool = True
    
    # Created by Process Mapper or user
    created_by: str
```

---

## API Endpoints

### Event Submission (Compute → Serving)

```python
POST /api/v1/observability/events
Content-Type: application/json

Request Body: ActivityStateChangeEvent | ExchangeEvent | ProcessMapReevaluationEvent | BlockerEvent | ActivityGroupingEvent

Response:
{
  "status": "accepted",
  "event_id": "evt-abc123",
  "timestamp": "2025-11-25T15:30:45Z"
}
```

**Authentication**: Compute instance JWT token (existing)

**Rate Limiting**: 100 events/second per compute instance

**Reliability**: 
- Events are fire-and-forget (no retry logic in compute)
- Serving persists events to event log (JSONL file or database)
- If event submission fails, compute logs error but continues

---

## WebSocket Protocol (Serving → Frontend)

### Connection

```javascript
// Frontend connects to WebSocket
const ws = new WebSocket('ws://localhost:8002/api/v1/observability/stream');

// Subscribe to session(s)
ws.send(JSON.stringify({
  action: 'subscribe',
  session_ids: ['improve-retention-abc123', 'analyze-sales-xyz789']
}));
```

### Server → Client Messages

```javascript
// Activity state change
{
  "type": "activity_state_change",
  "event": { /* ActivityStateChangeEvent */ }
}

// Exchange event
{
  "type": "exchange",
  "event": { /* ExchangeEvent */ }
}

// Process map reevaluation
{
  "type": "process_map_reevaluation",
  "event": { /* ProcessMapReevaluationEvent */ }
}

// Blocker identified
{
  "type": "blocker_identified",
  "event": { /* BlockerEvent */ }
}

// Activity grouping
{
  "type": "activity_grouping",
  "event": { /* ActivityGroupingEvent */ }
}

// Heartbeat (keep-alive)
{
  "type": "ping",
  "timestamp": "2025-11-25T15:30:45Z"
}
```

### Client → Server Messages

```javascript
// Subscribe to additional sessions
{
  "action": "subscribe",
  "session_ids": ["customer-segmentation-def456"]
}

// Unsubscribe from sessions
{
  "action": "unsubscribe",
  "session_ids": ["improve-retention-abc123"]
}

// Heartbeat response
{
  "action": "pong",
  "timestamp": "2025-11-25T15:30:45Z"
}
```

---

## Implementation: Compute Side

### Event Emission Points

**In Activity Facilitator** (compute/services/coordinating_team_service.py):

```python
class ActivityFacilitator:
    def __init__(self, serving_url: str, compute_instance_id: str):
        self.serving_url = serving_url
        self.compute_instance_id = compute_instance_id
        self.event_client = ObservabilityEventClient(serving_url)
    
    async def facilitate_activity(
        self,
        session_id: str,
        activity_id: str,
        activity_goal: str,
        participants: List[str]
    ) -> FacilitationResult:
        """Facilitate one activity to completion."""
        
        # Emit: Activity started
        await self.event_client.emit_activity_state_change(
            session_id=session_id,
            activity_id=activity_id,
            old_status=ActivityStatus.PROPOSED,
            new_status=ActivityStatus.IN_PROGRESS,
            compute_instance_id=self.compute_instance_id,
            agent_id=participants[0] if participants else None
        )
        
        exchanges = []
        exchange_count = 0
        
        # Facilitation loop
        while not self.is_goal_met(exchanges):
            exchange = await self.conduct_exchange(...)
            exchanges.append(exchange)
            exchange_count += 1
            
            # Emit exchange event (throttled - every 5th exchange or important)
            if exchange_count % 5 == 0 or exchange.intent in [ExchangeIntent.ASSESS, ExchangeIntent.CONCLUDE]:
                await self.event_client.emit_exchange(
                    session_id=session_id,
                    activity_id=activity_id,
                    exchange=exchange,
                    compute_instance_id=self.compute_instance_id,
                    exchange_number=exchange_count,
                    total_exchanges=exchange_count
                )
            
            # Check for blockers
            if self.detect_blocker(exchange):
                blocker = self.create_blocker(...)
                
                # Emit: Blocker identified
                await self.event_client.emit_blocker(
                    session_id=session_id,
                    activity_id=activity_id,
                    blocker=blocker,
                    compute_instance_id=self.compute_instance_id
                )
                
                # Emit: Activity blocked
                await self.event_client.emit_activity_state_change(
                    session_id=session_id,
                    activity_id=activity_id,
                    old_status=ActivityStatus.IN_PROGRESS,
                    new_status=ActivityStatus.BLOCKED,
                    compute_instance_id=self.compute_instance_id,
                    blocker=blocker
                )
                
                return FacilitationResult(status=ActivityStatus.BLOCKED, blocker=blocker)
        
        # Emit: Activity completed
        await self.event_client.emit_activity_state_change(
            session_id=session_id,
            activity_id=activity_id,
            old_status=ActivityStatus.IN_PROGRESS,
            new_status=ActivityStatus.GOAL_MET,
            compute_instance_id=self.compute_instance_id,
            duration_seconds=calculate_duration(...),
            exchange_count=exchange_count
        )
        
        return FacilitationResult(status=ActivityStatus.GOAL_MET, exchanges=exchanges)
```

**In Process Mapper** (when reevaluating):

```python
class ProcessMapper:
    async def reevaluate_process_map(
        self,
        session_id: str,
        process_map: ProcessMap,
        trigger: str,
        reasoning: str
    ) -> ProcessMap:
        """Reevaluate and restructure process map."""
        
        old_version = process_map.map_version
        
        # Perform reevaluation (split activities, add dependencies, etc.)
        new_map = self.restructure_map(process_map, reasoning)
        
        # Determine what changed
        activities_added = self.find_added_activities(process_map, new_map)
        activities_removed = self.find_removed_activities(process_map, new_map)
        dependencies_changed = self.find_dependency_changes(process_map, new_map)
        
        # Emit: Process map reevaluation
        await self.event_client.emit_reevaluation(
            session_id=session_id,
            previous_version=old_version,
            new_version=new_map.map_version,
            activities_added=activities_added,
            activities_removed=activities_removed,
            activities_modified=activities_modified,
            dependencies_changed=dependencies_changed,
            triggered_by=trigger,
            reasoning=reasoning
        )
        
        return new_map
```

**In Process Mapper** (when grouping activities):

```python
class ProcessMapper:
    async def group_activities(
        self,
        session_id: str,
        activity_ids: List[str],
        group_name: str,
        group_description: str
    ) -> str:
        """Create a semantic grouping of activities."""
        
        group_id = f"group-{uuid.uuid4()}"
        
        # Emit: Activity grouping
        await self.event_client.emit_activity_grouping(
            session_id=session_id,
            group_id=group_id,
            group_name=group_name,
            group_description=group_description,
            activity_ids=activity_ids,
            created_by="process-mapper-v1"
        )
        
        return group_id
```

---

## Implementation: Serving Side

### Event Bus Service

```python
# serving/services/observability_event_bus.py

from typing import Dict, Set, Callable
import asyncio
import json
from datetime import datetime
from pathlib import Path

class ObservabilityEventBus:
    """Central event bus for observability events."""
    
    def __init__(self, event_log_path: str = "./data/serving/observability_events"):
        self.event_log_path = Path(event_log_path)
        self.event_log_path.mkdir(parents=True, exist_ok=True)
        
        # WebSocket connections: session_id -> set of websocket connections
        self.subscribers: Dict[str, Set] = {}
        
        # Event handlers (for processing before broadcast)
        self.handlers: List[Callable] = []
    
    async def emit_event(self, event: Union[ActivityStateChangeEvent, ExchangeEvent, ...]):
        """
        Receive event from compute, persist, and broadcast to subscribers.
        """
        # 1. Persist event to log
        await self._persist_event(event)
        
        # 2. Update process map storage (if needed)
        await self._update_process_map(event)
        
        # 3. Run handlers (e.g., analytics, monitoring)
        for handler in self.handlers:
            await handler(event)
        
        # 4. Broadcast to WebSocket subscribers
        await self._broadcast_event(event)
    
    async def _persist_event(self, event):
        """Persist event to JSONL log file."""
        log_file = self.event_log_path / f"{event.session_id}_events.jsonl"
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(event.dict(), default=str) + '\n')
    
    async def _update_process_map(self, event):
        """Update process map storage with event data."""
        if isinstance(event, ActivityStateChangeEvent):
            # Update activity status in process map
            process_map_service = get_process_map_service()
            await process_map_service.update_activity_status(
                session_id=event.session_id,
                activity_id=event.activity_id,
                status=event.new_status
            )
        
        elif isinstance(event, ExchangeEvent):
            # Add exchange to activity
            process_map_service = get_process_map_service()
            await process_map_service.add_exchange(
                session_id=event.session_id,
                activity_id=event.activity_id,
                exchange=event.exchange
            )
        
        # ... handle other event types
    
    async def _broadcast_event(self, event):
        """Broadcast event to WebSocket subscribers."""
        session_id = event.session_id
        
        if session_id not in self.subscribers:
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
                logger.error(f"Failed to send event to WebSocket: {e}")
                dead_connections.add(ws)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.subscribers[session_id].discard(ws)
    
    def subscribe(self, session_id: str, websocket):
        """Subscribe WebSocket to session events."""
        if session_id not in self.subscribers:
            self.subscribers[session_id] = set()
        self.subscribers[session_id].add(websocket)
    
    def unsubscribe(self, session_id: str, websocket):
        """Unsubscribe WebSocket from session events."""
        if session_id in self.subscribers:
            self.subscribers[session_id].discard(websocket)
            if not self.subscribers[session_id]:
                del self.subscribers[session_id]

# Global instance
_event_bus: Optional[ObservabilityEventBus] = None

def get_event_bus() -> ObservabilityEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = ObservabilityEventBus()
    return _event_bus
```

### API Endpoint (Receive Events from Compute)

```python
# serving/api/observability.py

from fastapi import APIRouter, HTTPException, Depends
from services.observability_event_bus import get_event_bus, ObservabilityEventBus

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

@router.post("/events")
async def submit_event(
    event: Union[ActivityStateChangeEvent, ExchangeEvent, ProcessMapReevaluationEvent, BlockerEvent, ActivityGroupingEvent],
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
    """
    try:
        await event_bus.emit_event(event)
        
        return {
            "status": "accepted",
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat()
        }
    
    except Exception as e:
        logger.error(f"Failed to process event: {e}")
        raise HTTPException(status_code=500, detail="Failed to process event")
```

### WebSocket Endpoint

```python
# serving/api/observability.py

from fastapi import WebSocket, WebSocketDisconnect
import json

@router.websocket("/stream")
async def observability_stream(
    websocket: WebSocket,
    event_bus: ObservabilityEventBus = Depends(get_event_bus)
):
    """
    WebSocket endpoint for real-time observability updates.
    
    Clients connect and subscribe to session IDs to receive events.
    """
    await websocket.accept()
    
    subscribed_sessions = set()
    
    try:
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
                    'session_ids': session_ids
                }))
            
            elif action == 'unsubscribe':
                # Unsubscribe from sessions
                session_ids = message.get('session_ids', [])
                for session_id in session_ids:
                    event_bus.unsubscribe(session_id, websocket)
                    subscribed_sessions.discard(session_id)
                
                await websocket.send_text(json.dumps({
                    'type': 'unsubscribed',
                    'session_ids': session_ids
                }))
            
            elif action == 'pong':
                # Heartbeat response
                pass
    
    except WebSocketDisconnect:
        # Clean up subscriptions
        for session_id in subscribed_sessions:
            event_bus.unsubscribe(session_id, websocket)
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        for session_id in subscribed_sessions:
            event_bus.unsubscribe(session_id, websocket)
```

---

## Implementation: Frontend Side

### WebSocket Client

```javascript
// serving/frontend/src/services/observabilityWebSocket.js

class ObservabilityWebSocket {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.subscribers = new Map(); // event_type -> [callback functions]
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
  }
  
  connect() {
    this.ws = new WebSocket(this.url);
    
    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const { type, event: eventData } = data;
      
      // Notify all subscribers for this event type
      if (this.subscribers.has(type)) {
        for (const callback of this.subscribers.get(type)) {
          callback(eventData);
        }
      }
    };
    
    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.reconnect();
    };
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }
  
  reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached');
      return;
    }
    
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    
    console.log(`Reconnecting in ${delay}ms...`);
    setTimeout(() => this.connect(), delay);
  }
  
  subscribe(sessionIds) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'subscribe',
        session_ids: sessionIds
      }));
    }
  }
  
  unsubscribe(sessionIds) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'unsubscribe',
        session_ids: sessionIds
      }));
    }
  }
  
  on(eventType, callback) {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, []);
    }
    this.subscribers.get(eventType).push(callback);
  }
  
  off(eventType, callback) {
    if (this.subscribers.has(eventType)) {
      const callbacks = this.subscribers.get(eventType);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export default ObservabilityWebSocket;
```

### React Hook for Observability

```javascript
// serving/frontend/src/hooks/useObservability.js

import { useEffect, useState } from 'react';
import ObservabilityWebSocket from '../services/observabilityWebSocket';

export function useObservability(sessionIds) {
  const [ws] = useState(() => new ObservabilityWebSocket('ws://localhost:8002/api/v1/observability/stream'));
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  
  useEffect(() => {
    // Connect WebSocket
    ws.connect();
    
    // Listen for connection status
    ws.on('subscribed', () => setConnected(true));
    ws.on('unsubscribed', () => setConnected(false));
    
    // Subscribe to sessions
    if (sessionIds && sessionIds.length > 0) {
      ws.subscribe(sessionIds);
    }
    
    // Cleanup on unmount
    return () => {
      if (sessionIds && sessionIds.length > 0) {
        ws.unsubscribe(sessionIds);
      }
      ws.disconnect();
    };
  }, [sessionIds]);
  
  useEffect(() => {
    // Listen for all event types
    const eventTypes = [
      'activity_state_change',
      'exchange',
      'process_map_reevaluation',
      'blocker_identified',
      'activity_grouping'
    ];
    
    const handleEvent = (eventData) => {
      setEvents(prev => [...prev, eventData]);
    };
    
    for (const eventType of eventTypes) {
      ws.on(eventType, handleEvent);
    }
    
    return () => {
      for (const eventType of eventTypes) {
        ws.off(eventType, handleEvent);
      }
    };
  }, [ws]);
  
  return { connected, events, ws };
}
```

### Using in Component

```javascript
// serving/frontend/src/components/ProcessMapViewer.jsx

import { useObservability } from '../hooks/useObservability';

function ProcessMapViewer({ sessionId }) {
  const [processMap, setProcessMap] = useState(null);
  const { connected, events, ws } = useObservability([sessionId]);
  
  // Listen for specific event types
  useEffect(() => {
    const handleActivityStateChange = (event) => {
      console.log('Activity state changed:', event);
      
      // Update local state
      setProcessMap(prev => {
        if (!prev) return prev;
        
        const activity = prev.activities[event.activity_id];
        if (activity) {
          activity.status = event.new_status;
        }
        
        return { ...prev };
      });
    };
    
    ws.on('activity_state_change', handleActivityStateChange);
    
    return () => {
      ws.off('activity_state_change', handleActivityStateChange);
    };
  }, [ws]);
  
  return (
    <div>
      <div>WebSocket: {connected ? '🟢 Connected' : '🔴 Disconnected'}</div>
      {/* ... rest of component ... */}
    </div>
  );
}
```

---

## Latency Analysis

### End-to-End Latency

```
Activity completes on Compute
  ↓ (< 100ms)
HTTP POST to Serving /api/v1/observability/events
  ↓ (< 50ms)
Event Bus processes and persists
  ↓ (< 50ms)
WebSocket broadcast to Frontend
  ↓ (< 100ms)
Frontend UI updates

Total: ~300ms (< 1 second)
```

**Near real-time achieved!** ✅

---

## Reliability Considerations

### What if event submission fails?

**Scenario**: Compute tries to emit event but Serving is down or network is unavailable.

**Solution**:
1. Compute logs error but continues (fire-and-forget)
2. Serving has event log; on reconnect, can query Serving for current state
3. Frontend can re-fetch process map if WebSocket disconnects

**Trade-off**: Accept occasional missed events for simplicity. Process map storage is source of truth.

### What if WebSocket disconnects?

**Solution**:
1. Frontend automatically reconnects (exponential backoff)
2. On reconnect, re-subscribe to sessions
3. Frontend re-fetches current process map state to sync

---

## Comparison: Event-Driven vs. Polling

| Aspect | Polling (Old) | Event-Driven (New) |
|--------|---------------|-------------------|
| **Latency** | 3-5 seconds | < 1 second |
| **Backend Load** | High (constant queries) | Low (only on events) |
| **Scalability** | Poor (N clients × M sessions) | Good (event-driven) |
| **Complexity** | Simple | Moderate (WebSocket management) |
| **Real-Time** | No | Yes (near real-time) |
| **User Experience** | Delayed | Instant |

---

## Implementation Phases

### Phase 1: Event Infrastructure (Week 1)
- [ ] Create event models (ActivityStateChangeEvent, etc.)
- [ ] Implement ObservabilityEventBus
- [ ] Create `/api/v1/observability/events` endpoint
- [ ] Create `/api/v1/observability/stream` WebSocket endpoint

### Phase 2: Compute Event Emission (Week 2)
- [ ] Create ObservabilityEventClient in compute
- [ ] Add event emission to Activity Facilitator
- [ ] Add event emission to Process Mapper
- [ ] Add event emission to Consistency Manager

### Phase 3: Frontend WebSocket Integration (Week 3)
- [ ] Implement ObservabilityWebSocket service
- [ ] Create useObservability React hook
- [ ] Update ProcessMapViewer to use WebSocket
- [ ] Update Multi-Session Dashboard to use WebSocket

### Phase 4: Activity Grouping (Week 4)
- [ ] Implement dynamic activity grouping in Process Mapper
- [ ] Emit ActivityGroupingEvent
- [ ] Update frontend to display grouped activities
- [ ] Implement collapsible group UI

### Phase 5: Testing & Optimization (Week 5)
- [ ] Load testing (50 concurrent sessions)
- [ ] WebSocket reconnection testing
- [ ] Event throughput testing
- [ ] Latency optimization

---

## Summary

✅ **Event-Driven Architecture**: Compute pushes updates to Serving, Serving streams to Frontend  
✅ **Near Real-Time**: < 1 second end-to-end latency  
✅ **WebSocket**: Bidirectional communication for subscriptions  
✅ **Scalable**: Event-driven design scales better than polling  
✅ **Reliable**: Event log provides durability, reconnection logic handles failures  

---

**Next**: Design dynamic activity grouping system (separate document)

---

**Version**: 2.0  
**Date**: November 25, 2025  
**Status**: Revised - Event-Driven





