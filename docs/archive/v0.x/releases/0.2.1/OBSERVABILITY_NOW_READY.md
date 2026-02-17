# Observability UI - Ready to Test! 🎉

## Issues Fixed

1. ✅ **Port 3000 issue** - Frontend is served from the **Serving component at port 8002**, not a separate server
2. ✅ **Compute startup failure** - Missing `tiktoken` dependency installed
3. ✅ **UI Integration** - Observability tab now integrated into the serving UI navigation
4. ✅ **React Router** - Removed dependency, using simple state-based navigation like the rest of the app
5. ✅ **Test script** - Fixed to use correct port and handle errors properly

## How to Access Observability UI

### 1. Start All Services

```bash
./start_all.sh
```

### 2. Open Browser

Navigate to the **Serving UI**:

```
http://localhost:8002
```

### 3. Click "Observability" Tab

You'll see it in the top navigation bar:
- Dashboard
- Compute Registry
- Process Maps  
- **Observability** ← Click this!

### 4. View the Observability Dashboard

You'll see:
- System stats (sessions, activities, compute resources, agents)
- Live connection status (🟢 Live when WebSocket connected)
- List of all sessions with real-time updates
- Filter buttons (All, In Progress, Blocked, Completed)

### 5. View Session Details

Click **"View Details"** on any session card to see:
- **Overview Tab**: Summary stats and progress
- **Workflow Tab**: Visual activity graph with real-time updates
- **Timeline Tab**: Chronological event stream
- **Resources Tab**: Compute and agent utilization

## Test with Artificial Delays

To see observability updates at a visible pace:

```bash
./test_observability.sh
```

This script will:
1. Stop all services
2. Start services with **5-second agent execution delays**
3. Create a test session
4. Guide you through viewing real-time updates

**Important**: The test script will open `http://localhost:8002` (not 3000!)

## Quick Manual Test

```bash
# 1. Set 5-second delay
export COMPUTE_AGENT_EXECUTION_DELAY=5.0

# 2. Restart compute with delay
cd compute
./stop.sh
./start.sh
cd ..

# 3. Open browser to http://localhost:8002
# 4. Click "Observability" tab
# 5. You should see any active sessions updating in real-time

# 6. Create a new session to watch it execute
curl -X POST http://localhost:8002/api/v1/sessions/facilitated \
  -H "Content-Type: application/json" \
  -d '{
    "business_goal": "Analyze Q4 sales and create executive report",
    "coordination_mode": "facilitated"
  }'

# 7. Execute the session and watch the UI update!
curl -X POST http://localhost:8002/api/v1/sessions/{session-id}/execute
```

## What You'll See

With 5-second delays, each activity takes ~5 seconds, so you can watch:

- ✅ **Activity status changes**: Proposed → In Progress → Completed
- ✅ **Timeline events**: New events appearing as they happen
- ✅ **Workflow graph**: Nodes changing colors in real-time
- ✅ **Resource metrics**: CPU/memory updates per compute instance
- ✅ **Live indicator**: 🟢 showing WebSocket connection

## UI Navigation

```
http://localhost:8002
├── Dashboard (default)
├── Compute Registry
├── Process Maps
└── Observability ★ 
    ├── System Stats
    ├── Connection Status (🟢 Live)
    ├── Session List (with real-time updates)
    └── Session Detail (click "View Details")
        ├── Overview Tab
        ├── Workflow Tab (visual graph)
        ├── Timeline Tab (event stream)
        └── Resources Tab (metrics)
```

## Troubleshooting

### Observability tab not showing?

The frontend needs to be rebuilt after the changes:

```bash
cd serving/frontend
npm run build
cd ../..
./stop_all.sh
./start_all.sh
```

### WebSocket not connecting (🔴 Disconnected)?

1. Check serving is running: `curl http://localhost:8002/api/v1/health`
2. Check browser console for errors (F12 → Console tab)
3. Verify WebSocket endpoint: `ws://localhost:8002/api/v1/observability/stream`

### No sessions showing?

Create a test session:

```bash
curl -X POST http://localhost:8002/api/v1/sessions/facilitated \
  -H "Content-Type: application/json" \
  -d '{"business_goal": "Test observability", "coordination_mode": "facilitated"}'
```

### Activities executing too fast to see?

Use the delay:

```bash
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
cd compute && ./stop.sh && ./start.sh && cd ..
```

## Documentation

- 📖 [Observability Testing Guide](docs/guides/OBSERVABILITY_TESTING_GUIDE.md) - Comprehensive testing guide
- 📘 [Quick Start](OBSERVABILITY_TESTING_QUICKSTART.md) - Quick reference
- 📗 [Implementation Complete](docs/development/OBSERVABILITY_IMPLEMENTATION_COMPLETE.md) - Full implementation details

## Current Status

- ✅ All observability features implemented (v0.2.1)
- ✅ Fully integrated into serving UI at port 8002
- ✅ Real-time WebSocket updates working
- ✅ Test script fixed and ready to use
- ✅ All dependencies installed
- ✅ Documentation updated

---

**Ready to test!** 🚀

Just open http://localhost:8002 and click the "Observability" tab!

