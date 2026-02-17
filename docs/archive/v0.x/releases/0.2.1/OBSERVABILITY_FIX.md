# Observability Test Fix

## Problem Identified

The `test_observability_simple.sh` script was not showing any activity in the Observability dashboard because:

1. **Wrong Endpoint**: The script was calling `/api/v1/tasks/demo/business-process`
2. **No Observability Events**: This endpoint executes individual agents directly without using the coordinating team service
3. **Missing Context**: Observability events are only emitted when using facilitated sessions with the Activity Facilitator

## Root Cause

The observability system works by having compute instances emit events through the `ObservabilityEventClient` when:
- Activity Facilitator coordinates agent conversations
- Process Mapper creates/evolves process maps
- Activities change state (proposed → in_progress → completed)

**Two issues were found:**

1. **Wrong Endpoint**: The test script was calling `/api/v1/tasks/demo/business-process` which executes agents directly without using the coordinating team service
2. **Missing Initialization**: The compute instance was **not initializing the observability client** on startup, so even if events were supposed to be emitted, they would fail silently

The old demo endpoint bypassed facilitation by calling agents directly via `/agents/execute`.

## Solution

### 1. New Endpoint: `/api/v1/tasks/demo/observability`

Created a proper demo endpoint that:
- ✅ Creates a facilitated session
- ✅ Creates a process map
- ✅ Adds activities to the map
- ✅ Assigns agents to activities
- ✅ Invokes Activity Facilitator (triggers observability events!)
- ✅ Updates activity states through proper channels

### 2. Updated Test Script

Modified `test_observability_simple.sh` to:
- Call the new `/tasks/demo/observability` endpoint
- Display the session_id for easy tracking
- Provide clearer instructions about what to observe

### 3. Files Modified

- **`serving/api/tasks.py`** - Added new `/demo/observability` endpoint
- **`compute/app.py`** - **CRITICAL FIX**: Initialize observability client on startup
- **`test_observability_simple.sh`** - Updated to use new endpoint

## How to Test

```bash
# IMPORTANT: Restart compute service to initialize observability client!
cd compute && ./stop.sh && ./start.sh && cd ..

# 1. Make sure all services are running
./start_all.sh

# 2. (Optional) Enable delays for easier observation
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
cd compute && ./stop.sh && ./start.sh && cd ..

# 3. Run the test script
./test_observability_simple.sh

# 4. Open browser to http://localhost:8002
# 5. Click "Observability" tab
# 6. Watch the session appear with real-time updates!
```

**Note:** The compute service MUST be restarted after this fix for the observability client to be initialized!

## What You Should See Now

When you run the test, the Observability UI should show:

✅ **New session appears** in the sessions list with ID like `obs-demo-12345678`
✅ **Activity state changes** from proposed → in_progress → completed
✅ **Timeline events** showing when each state change occurred
✅ **Live connection** indicator showing 🟢 Connected
✅ **System stats** updating with compute instance activity

## Why the Old Endpoint Didn't Work

```python
# OLD: Direct agent execution (no observability events)
response = await client.post(
    f"{instance.endpoint}/agents/execute",
    json={"agent_id": "data-analyst-v1", "prompt": "..."}
)

# NEW: Coordinated facilitation (emits observability events)
result = await coordinating_service.invoke_activity_facilitator(
    session_id=session_id,
    activity=activity_data,
    conversation_history=[],
    current_situation=initial_prompt,
    assigned_agents=assigned_agents
)
```

The key difference is that `invoke_activity_facilitator` uses the coordinating team service which:
1. Creates activity state change events
2. Emits them via `ObservabilityEventClient`
3. Events are broadcast via WebSocket to the UI
4. UI updates in real-time

## Technical Details

### Event Flow

```
Compute Instance (coordinating_team_service.py)
    └─> ObservabilityEventClient.emit_activity_state_change()
        └─> HTTP POST to Serving /api/v1/observability/events
            └─> ObservabilityEventBus.emit_event()
                └─> WebSocket broadcast to connected clients
                    └─> Frontend receives event
                        └─> UI updates in real-time
```

### Event Types Emitted

- `activity_state_change` - When activities transition between states
- `exchange` - When agents exchange messages (every 5th exchange)
- `process_map_reevaluation` - When the process map evolves
- `blocker_identified` - When blockers are detected
- `session_created` - When new sessions start
- `session_completed` - When sessions finish

## Additional Testing

To create more test sessions:

```bash
# Via API
curl -X POST http://localhost:8002/api/v1/tasks/demo/observability

# Via test script (run multiple times)
./test_observability_simple.sh
```

Each run creates a new session with a unique ID that you can track in the UI.

## Next Steps

Consider enhancing with:
- [ ] More complex multi-activity workflows
- [ ] Blocker detection scenarios
- [ ] Process map evolution examples
- [ ] Multiple concurrent sessions
- [ ] Resource utilization stress tests
