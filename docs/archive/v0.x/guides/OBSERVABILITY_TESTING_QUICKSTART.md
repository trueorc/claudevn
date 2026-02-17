# Observability Testing Quick Start

## 🎯 Test Observability with Visible Delays

Want to see the observability features in action with enough time to actually observe them? Use the artificial delay feature!

## Quick Test

```bash
# 1. Start all services
./start_all.sh

# 2. (Optional) Enable 5-second delays
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
cd compute && ./stop.sh && ./start.sh && cd ..

# 3. Run simple test
./test_observability_simple.sh
```

This will:
1. Verify all services are running
2. Guide you to the observability UI  
3. Run a demo process for you to watch

## Manual Quick Start

```bash
# 1. Set the delay (5 seconds per agent)
export COMPUTE_AGENT_EXECUTION_DELAY=5.0

# 2. Start all services
./start_all.sh

# 3. Open browser to serving UI (click Observability tab)
open http://localhost:8002

# 4. Create a test session
curl -X POST http://localhost:8002/api/v1/sessions/facilitated \
  -H "Content-Type: application/json" \
  -d '{
    "business_goal": "Analyze Q4 2024 sales and create executive report",
    "coordination_mode": "facilitated"
  }'

# 5. Copy the session_id from response and execute
curl -X POST http://localhost:8002/api/v1/sessions/{session_id}/execute

# 6. Watch the UI update in real-time!
```

## What You'll See

With 5-second delays, you can actually watch:

- ✅ **Real-time status updates** - Activities change from proposed → in_progress → completed
- ✅ **Timeline events** - New events appear as they happen
- ✅ **Workflow visualization** - Graph nodes change colors live
- ✅ **Activity groups** - Semantic grouping of related activities
- ✅ **Resource monitoring** - CPU/memory usage per compute instance
- ✅ **WebSocket live indicator** - See the connection status (🟢 Live)

## Views to Explore

| View | URL | What to Watch |
|------|-----|---------------|
| **Main UI** | `http://localhost:8002` | Serving component with all tabs |
| **Observability Tab** | (click in navigation) | All sessions, system stats |
| **Session Details** | (click session card) | Single session with full details |
| **Workflow View** | (in session detail) | Visual activity graph |
| **Timeline View** | (in session detail) | Chronological event stream |
| **Resources View** | (in session detail) | Compute instance metrics |

## Adjust the Delay

Change the delay to suit your needs:

```bash
# Faster (3 seconds)
export COMPUTE_AGENT_EXECUTION_DELAY=3.0

# Slower for demos (10 seconds)
export COMPUTE_AGENT_EXECUTION_DELAY=10.0

# Normal speed (no delay)
export COMPUTE_AGENT_EXECUTION_DELAY=0.0
# or just don't set it
```

## Full Documentation

For detailed testing procedures, troubleshooting, and advanced scenarios:

📖 [Full Observability Testing Guide](docs/guides/OBSERVABILITY_TESTING_GUIDE.md)

## Implementation Status

✅ All observability features are **fully implemented** in v0.2.1:
- Event-driven architecture
- Real-time WebSocket streaming  
- Dynamic activity grouping
- Multi-view UI (Dashboard, Workflow, Timeline, Resources)
- Sub-second latency for updates

See [Observability Implementation Complete](docs/development/OBSERVABILITY_IMPLEMENTATION_COMPLETE.md) for details.

---

**Quick Tip**: The delay only affects agent execution time - all observability events still happen in real-time with sub-second latency!

