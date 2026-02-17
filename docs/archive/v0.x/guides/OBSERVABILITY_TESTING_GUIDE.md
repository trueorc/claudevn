# Observability Testing Guide

## Overview

This guide explains how to test the ClaudeVN observability system with artificial delays to see real-time updates in the UI.

## Quick Start

The fastest way to test observability with visible delays:

```bash
./test_observability.sh
```

This script will:
1. Stop all services
2. Start services with 5-second agent execution delays
3. Create a test session with multiple activities
4. Guide you through observing real-time updates

## Manual Testing

If you want more control over the testing process, follow these steps:

### 1. Configure Agent Execution Delay

Set the delay environment variable before starting the compute service:

```bash
export COMPUTE_AGENT_EXECUTION_DELAY=5.0  # 5 seconds per agent execution
```

You can adjust this value:
- `3.0` - 3 seconds (faster testing)
- `5.0` - 5 seconds (recommended)
- `10.0` - 10 seconds (very visible, good for demos)

### 2. Start Services

Start all services in the correct order:

```bash
# Start marketplace
cd marketplace && ./start.sh && cd ..

# Start serving
cd serving && ./start.sh && cd ..

# Start compute with delay
cd compute
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
./start.sh
cd ..
```

Wait a few seconds for services to fully initialize and register.

### 3. Open the Observability UI

Open your browser to the serving UI:

```
http://localhost:8002
```

Then click the **Observability** tab in the top navigation to access the observability dashboard.

### 4. Create a Test Session

Create a session with a complex business goal to generate multiple activities:

```bash
curl -X POST http://localhost:8002/api/v1/sessions/facilitated \
  -H "Content-Type: application/json" \
  -d '{
    "business_goal": "Analyze Q4 2024 sales performance and create an executive report with recommendations",
    "context": {
      "data_available": "Q4 2024 sales transactions",
      "total_revenue": "$24,127.50",
      "transaction_count": 95,
      "date_range": "Oct 1 - Dec 31, 2024"
    },
    "coordination_mode": "facilitated"
  }'
```

This will return a `session_id`. Copy it for the next step.

### 5. View Session in UI

Navigate to the serving UI and click the **Observability** tab:

```
http://localhost:8002
```

You'll see all active sessions. Click **View Details** on any session card to see the detailed session view with tabs.

### 6. Execute the Session

Start the session execution and watch the real-time updates:

```bash
curl -X POST http://localhost:8002/api/v1/sessions/{session_id}/execute
```

## What to Observe

With the delays enabled, you should see:

### Dashboard View (`/observability`)
- **System Stats**: Total sessions, activities, compute resources, and active agents
- **Session Cards**: Each session shows live status updates
- **Activity Counts**: Real-time counts of proposed, in-progress, completed, and blocked activities
- **Progress Bars**: Visual progress updating as activities complete
- **Connection Status**: 🟢 Live indicator showing WebSocket connection

### Session Detail View (`/observability/sessions/{session_id}`)

#### Overview Tab
- Session status and progress
- Activity breakdown with live counts
- Duration timer
- Recent activity list updating in real-time

#### Workflow Tab
- **Activity Graph**: Visual representation of activities and dependencies
- **Status Colors**: 
  - 🟡 Yellow: Proposed
  - 🔵 Blue: In Progress (you'll see this for ~5 seconds per activity)
  - 🟢 Green: Completed
  - 🔴 Red: Blocked (if any errors occur)
- **Activity Groups**: Semantic grouping of related activities
- **Collapsible Groups**: Click to expand/collapse groups
- **Activity Details**: Click any activity to see detailed information

#### Timeline Tab
- **Chronological Event Stream**: All events as they happen
- **Event Types**:
  - Session Created
  - Activity State Change (proposed → in_progress → completed)
  - Exchange Events (agent conversations)
  - Process Map Reevaluation
  - Blocker Identified (if any)
  - Activity Grouping
- **Auto-scroll**: Timeline automatically scrolls to latest events
- **Relative Timestamps**: "2m ago", "30s ago", etc.
- **Expandable Details**: Click events to see full details

#### Resources Tab
- **Compute Instances**: List of compute resources
- **CPU Usage**: Real-time CPU metrics
- **Memory Usage**: Real-time memory metrics
- **Active Agents**: Which agents are currently executing
- **Agent-Activity Mapping**: See which activities each agent is working on

## Expected Behavior

With a 5-second delay:

1. **Activity Start**: You'll see an activity change from "proposed" to "in_progress"
2. **Visible Duration**: The activity stays "in_progress" for ~5 seconds
3. **Activity Complete**: The activity changes to "completed"
4. **Next Activity**: The next activity begins (if dependencies are met)
5. **Timeline Updates**: Each state change appears in the timeline immediately
6. **Workflow Updates**: The graph updates colors in real-time

## Testing Different Scenarios

### Multiple Activities in Parallel

If you have multiple compute instances, you can see parallel execution:

```bash
# Start a second compute instance on a different port
cd compute
export COMPUTE_PORT=8004
export COMPUTE_INSTANCE_ID=compute-2
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
./start.sh
```

Now create a session with many activities to see them execute in parallel.

### Blocker Simulation

To test blocker detection and display, you can modify an agent to fail intentionally or create an activity with impossible requirements.

### Process Map Evolution

Create a session, let some activities complete, then trigger a reevaluation:

```bash
curl -X POST http://localhost:8002/api/v1/sessions/{session_id}/reevaluate \
  -H "Content-Type: application/json" \
  -d '{
    "trigger": "manual_test",
    "reasoning": "Testing process map evolution and observability events"
  }'
```

## Performance Testing

### Without Delays (Production Mode)

To test performance without delays:

```bash
# Don't set COMPUTE_AGENT_EXECUTION_DELAY or set it to 0
export COMPUTE_AGENT_EXECUTION_DELAY=0.0
./start_all.sh
```

Activities will execute at full speed. You should still see real-time updates, but they'll happen much faster.

### Stress Testing

Test with many concurrent sessions:

```bash
# Create 10 sessions
for i in {1..10}; do
  curl -X POST http://localhost:8002/api/v1/sessions/facilitated \
    -H "Content-Type: application/json" \
    -d "{
      \"business_goal\": \"Test session $i\",
      \"coordination_mode\": \"facilitated\"
    }"
done
```

Monitor the dashboard to see all sessions updating in real-time.

## Troubleshooting

### Events Not Appearing in UI

1. **Check WebSocket Connection**: Look for "🟢 Live" in the UI
2. **Check Browser Console**: Open DevTools and look for WebSocket errors
3. **Verify Compute Registration**: `curl http://localhost:8002/api/v1/compute`
4. **Check Observability Client**: Look in compute logs for "ObservabilityEventClient initialized"

### Delays Not Working

1. **Verify Environment Variable**: `echo $COMPUTE_AGENT_EXECUTION_DELAY`
2. **Check Compute Logs**: Should see "Agent executor initialized with Xs execution delay"
3. **Restart Compute**: Make sure you set the variable *before* starting

### UI Not Updating

1. **Check Frontend**: Is it running? `curl http://localhost:3000`
2. **Hard Refresh**: Clear browser cache (Cmd+Shift+R)
3. **Check WebSocket URL**: Should be `ws://localhost:8002/api/v1/observability/stream`

### Session Execution Hangs

1. **Check Compute Logs**: `tail -f compute/logs/compute.log`
2. **Check Agent Registry**: `curl http://localhost:8003/agents`
3. **Verify LLM Provider**: Mock provider should be working by default

## Advanced Testing

### Custom Event Emission

You can emit custom observability events for testing:

```bash
curl -X POST http://localhost:8002/api/v1/observability/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "activity_state_change",
    "event_id": "evt-test-123",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S)'",
    "session_id": "test-session-1",
    "activity_id": "test-activity-1",
    "old_status": "proposed",
    "new_status": "in_progress",
    "compute_instance_id": "test-compute",
    "metadata": {}
  }'
```

### WebSocket Testing

Connect to the WebSocket directly for testing:

```javascript
// In browser console
const ws = new WebSocket('ws://localhost:8002/api/v1/observability/stream');
ws.onopen = () => {
  console.log('Connected');
  ws.send(JSON.stringify({
    action: 'subscribe',
    session_ids: ['your-session-id']
  }));
};
ws.onmessage = (event) => {
  console.log('Event:', JSON.parse(event.data));
};
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `COMPUTE_AGENT_EXECUTION_DELAY` | Artificial delay in seconds | 0.0 | 5.0 |
| `COMPUTE_INSTANCE_ID` | Unique instance identifier | auto-generated | compute-1 |
| `SERVING_URL` | Serving component URL | http://localhost:8002 | http://serving:8002 |

### Delay Recommendations

| Use Case | Recommended Delay | Reason |
|----------|-------------------|--------|
| Development | 0.0 - 1.0s | Fast iteration |
| Manual Testing | 3.0 - 5.0s | Visible but not slow |
| Demos | 5.0 - 10.0s | Very visible for audience |
| Screenshots/Videos | 10.0s | Easy to capture states |
| Production | 0.0s | Maximum performance |

## Related Documentation

- [Observability Implementation Complete](../development/OBSERVABILITY_IMPLEMENTATION_COMPLETE.md) - Full implementation details
- [Observability Performance Guide](../development/OBSERVABILITY_PERFORMANCE_GUIDE.md) - Performance tuning
- [Quick Test Guide](QUICK_TEST_GUIDE.md) - General testing guide
- [Execution Flow](EXECUTION_FLOW.md) - How the system executes tasks

## Version History

- **v0.2.1** (November 25, 2025): Initial observability testing guide with delay configuration

---

**Pro Tip**: For the best observability testing experience, use a delay of 5 seconds and have multiple browser tabs open showing different views (Dashboard, Workflow, Timeline) to see how they all update together in real-time!

