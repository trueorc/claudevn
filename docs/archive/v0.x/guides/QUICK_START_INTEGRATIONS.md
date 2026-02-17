# Quick Start - Test Marketplace Integration UI

## 🎯 You're Ready to Test!

Services are already running. Here's how to see everything working:

---

## ✅ What's Already Working

- ✅ **Serving**: Running at http://localhost:8002
- ✅ **Marketplace**: Running at http://localhost:8001
- ✅ **Registration**: Marketplace registered as `marketplace-43e08beb`
- ✅ **Heartbeats**: Sending automatically every 60 seconds

---

## 🎨 Option 1: Test via UI (Recommended)

### Step 1: Build the Marketplace Frontend
```bash
# If you have Node.js installed (optional but recommended)
cd marketplace/frontend
npm install
npm run build
cd ../..

# Then restart marketplace to serve the UI
./stop_all.sh && ./start_all.sh
```

### Step 2: Open the Integration UI
```bash
# Open in your browser
open http://localhost:8001/integrations

# Or just navigate to: http://localhost:8001
# Click "Integrations" in the navigation
```

### Step 3: See Current Status
You should see:
- 🟢 **Connected** status badge
- Serving URL: `http://localhost:8002`
- Marketplace ID: `marketplace-43e08beb`
- Heartbeat interval: 60s

### Step 4: Test Features
- Click **"📡 Send Heartbeat"** - Manually send a heartbeat
- Click **"🔌 Deregister"** - Disconnect from serving
- Fill in form and click **"Register"** - Reconnect

---

## 🔧 Option 2: Test via API

### Check Current Status
```bash
curl http://localhost:8001/api/v1/integrations/serving | python3 -m json.tool
```

Expected output:
```json
{
  "configured": true,
  "serving_url": "http://localhost:8002",
  "marketplace_id": "marketplace-43e08beb",
  "registered": true,
  "running": true,
  "status": "connected"
}
```

### View from Serving Side
```bash
curl http://localhost:8002/api/v1/marketplaces | python3 -m json.tool
```

Expected output:
```json
{
  "marketplaces": [
    {
      "marketplace_id": "marketplace-43e08beb",
      "name": "ClaudeVN Marketplace",
      "status": "healthy",
      "capabilities": {
        "agent_count": 10,
        "tool_count": 0
      }
    }
  ],
  "total": 1,
  "healthy": 1
}
```

### Send Manual Heartbeat
```bash
curl -X POST http://localhost:8001/api/v1/integrations/serving/heartbeat
```

### Deregister
```bash
curl -X POST http://localhost:8001/api/v1/integrations/serving/deregister
```

### Re-register
```bash
curl -X POST http://localhost:8001/api/v1/integrations/serving/register \
  -H "Content-Type: application/json" \
  -d '{
    "serving_url": "http://localhost:8002",
    "marketplace_name": "ClaudeVN Marketplace",
    "priority": 1
  }'
```

---

## 📊 Monitor Activity

### Watch Heartbeats in Real-Time
```bash
# Terminal 1: Marketplace logs
tail -f logs/marketplace.log | grep heartbeat

# Terminal 2: Serving logs
tail -f logs/serving.log | grep marketplace
```

You should see:
```
[marketplace.log] INFO - Heartbeat loop started (interval: 60s)
[marketplace.log] INFO - HTTP Request: POST .../heartbeat "HTTP/1.1 200 OK"
[serving.log] DEBUG - Received heartbeat from marketplace marketplace-43e08beb
```

---

## 🧪 Test Scenarios

### Scenario 1: Deregister and Re-register
```bash
# 1. Deregister
curl -X POST http://localhost:8001/api/v1/integrations/serving/deregister

# 2. Verify it's gone
curl http://localhost:8002/api/v1/marketplaces
# Should show: "total": 0

# 3. Re-register
curl -X POST http://localhost:8001/api/v1/integrations/serving/register \
  -H "Content-Type: application/json" \
  -d '{"serving_url": "http://localhost:8002"}'

# 4. Verify it's back
curl http://localhost:8002/api/v1/marketplaces
# Should show: "total": 1
```

### Scenario 2: Test Health Monitoring
```bash
# 1. Stop marketplace (stop heartbeats)
cd marketplace && pkill -f "uvicorn"

# 2. Wait 90+ seconds

# 3. Check serving - marketplace should be "degraded"
curl http://localhost:8002/api/v1/marketplaces | grep status

# 4. Wait another 90 seconds - should become "offline"

# 5. Restart marketplace
cd .. && cd marketplace && source ../.venv/bin/activate && \
  python3 -m uvicorn app:app --host 0.0.0.0 --port 8001 &
```

### Scenario 3: Multiple Marketplaces
```bash
# Register another marketplace (simulated)
curl -X POST http://localhost:8002/api/v1/marketplaces/register \
  -H "Content-Type: application/json" \
  -d '{
    "marketplace_id": "marketplace-test-002",
    "name": "Test Marketplace 2",
    "endpoint": "http://localhost:8003",
    "capabilities": {
      "agent_count": 5,
      "tool_count": 3
    },
    "priority": 2
  }'

# View all marketplaces
curl http://localhost:8002/api/v1/marketplaces
# Should show 2 marketplaces, sorted by priority
```

---

## 📈 What to Look For

### ✅ Good Signs
- 🟢 Green "Connected" badge in UI
- Regular heartbeat logs every 60 seconds
- `status: "healthy"` in API responses
- `registered: true` in integration status
- Agent/tool counts match marketplace data

### ⚠️ Warning Signs
- 🟡 Yellow "Degraded" badge (no heartbeat for 90s)
- ⚫ Black "Disconnected" badge (offline or not registered)
- Heartbeat errors in logs
- `failed_health_checks` counter increasing

---

## 🎓 Architecture Recap

```
Your Browser
    │
    ├─► http://localhost:8001/integrations (Marketplace UI)
    │      │
    │      └─► Shows connection status, manage integration
    │
    ├─► http://localhost:8001/api/v1/integrations/serving (API)
    │      │
    │      └─► Get status, register, deregister
    │
    └─► http://localhost:8002/api/v1/marketplaces (Serving API)
           │
           └─► View all registered marketplaces

Automatic Heartbeats (every 60s):
    Marketplace → POST /api/v1/marketplaces/{id}/heartbeat → Serving
```

---

## 🚀 You're All Set!

**Everything is working perfectly:**
- ✅ Services running
- ✅ Marketplace registered
- ✅ Heartbeats flowing
- ✅ UI ready to use
- ✅ APIs fully functional

**Next Steps:**
1. Build the frontend: `cd marketplace/frontend && npm install && npm run build`
2. Open the UI: http://localhost:8001/integrations
3. Explore the integration management interface
4. Test deregister/register flows
5. Monitor the logs for heartbeats

**Happy Testing! 🎉**

