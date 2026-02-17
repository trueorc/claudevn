# ✅ Observability Testing - Simplified Workflow

## Issues Fixed

1. ✅ **Marketplace disconnect** - New script doesn't restart services
2. ✅ **API endpoint error** - Uses correct demo endpoint
3. ✅ **Compute venv issue** - Fixed in start.sh (uses venv python)

## New Recommended Workflow

### Step 1: Start All Services (You handle this)

```bash
./start_all.sh
```

### Step 2: (Optional) Enable 5-Second Delays

Only if you want to see slow-motion updates:

```bash
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
cd compute && ./stop.sh && ./start.sh && cd ..
```

### Step 3: Run Simple Test Script

```bash
./test_observability_simple.sh
```

This script will:
- ✅ **Verify** services are running (doesn't start/stop them)
- ✅ **Guide** you to open the UI
- ✅ **Run** a demo business process
- ✅ **Show** examples of how to create more test sessions

## What's Different?

### Old Script (`test_observability.sh`)
- ❌ Stops all services
- ❌ Starts them individually (causes marketplace disconnect)
- ❌ Uses wrong API endpoint (`/sessions/facilitated` doesn't exist)
- ❌ Complex flow

### New Script (`test_observability_simple.sh`)
- ✅ Assumes services already running
- ✅ Just verifies they're healthy
- ✅ Uses correct API endpoints
- ✅ Simple, focused workflow
- ✅ You control the service lifecycle

## How to Test Now

### Quick Test (No Delays)

```bash
# 1. Start services (if not already running)
./start_all.sh

# 2. Run test
./test_observability_simple.sh

# 3. Open browser to http://localhost:8002
# 4. Click "Observability" tab
# 5. Watch the demo process that the script runs
```

### Test with Delays (5 seconds per agent)

```bash
# 1. Start services (if not already running)
./start_all.sh

# 2. Restart compute with delay
export COMPUTE_AGENT_EXECUTION_DELAY=5.0
cd compute && ./stop.sh && ./start.sh && cd ..

# 3. Run test
./test_observability_simple.sh

# 4. Open browser and watch slow-motion updates!
```

## Manual Testing

Once services are running, you can also test manually:

```bash
# View API docs
open http://localhost:8002/docs

# Create a simple task
curl -X POST http://localhost:8002/api/v1/tasks/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "agent_id": "data-analyst-v1",
    "prompt": "Analyze Q4 sales data",
    "output_format": "markdown"
  }'

# Run demo business process
curl -X POST http://localhost:8002/api/v1/tasks/demo/business-process

# Watch in UI: http://localhost:8002 → Observability tab
```

## Observability Features

Access at **http://localhost:8002** → Click **"Observability"** tab

You'll see:
- 🟢 **Live indicator** - Shows WebSocket connection status
- 📊 **System stats** - Sessions, activities, compute resources, agents
- 📋 **Session list** - Real-time status updates
- 🔍 **View Details** - Deep dive into any session

## Files

- ✅ `test_observability_simple.sh` - NEW simple test script (recommended)
- ⚠️ `test_observability.sh` - OLD script (stops/starts services, has API errors)

## Key Benefits

1. **No service disruption** - Marketplace stays connected
2. **You control lifecycle** - Start services when you want
3. **Correct API usage** - No "Method Not Allowed" errors
4. **Simpler flow** - Verify, guide, demo

---

## Summary

**Recommended workflow:**
1. **You run:** `./start_all.sh`
2. **You run (optional):** Enable delays by restarting compute
3. **You run:** `./test_observability_simple.sh`
4. **You open:** http://localhost:8002 → Observability tab
5. **You watch:** Real-time updates as the demo runs!

All issues fixed and ready to test! 🚀



