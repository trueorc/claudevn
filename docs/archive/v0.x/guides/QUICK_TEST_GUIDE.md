# Quick UI Testing Guide 🚀

## TL;DR - Start Testing in 30 Seconds

### 1. Open Your Browser
```
Marketplace UI:  http://localhost:8001
Serving UI:      http://localhost:8002
```

### 2. What to Test

#### 🏪 Marketplace (http://localhost:8001)
**Has pre-loaded data - ready to test immediately!**

| Tab | What to Try | Expected Result |
|-----|-------------|-----------------|
| **Agent Browser** | Search for "data" or "web" | See filtered agent cards |
| | Click on an agent card | View detailed agent info |
| | Browse by category | See categorized agents |
| **User Management** | Click "Add User" | Create a new user |
| | Edit/delete users | Changes persist |
| **Organizations** | Create "Test Org" | Organization appears in list |
| | Add members | Members linked to org |
| **Access Control** | Grant user access to agent | Permission entry created |

#### 🔧 Serving (http://localhost:8002)
**Test data loaded - 4 compute instances registered!**

| View | What to See | What It Means |
|------|-------------|---------------|
| **Dashboard** | Total: 4 instances | All test instances active |
| | Status: 4 online, 0 degraded, 0 offline | Health monitoring working |
| | Aggregated capabilities | Combined resources view |
| **Compute Registry** | 4 instance cards | Each with name, status, endpoint |
| | Green "online" badges | All healthy |
| | Last heartbeat times | Monitoring active |
| | Capabilities list | Agents/tools per instance |

---

## 📸 What You Should See

### Marketplace UI
```
┌─────────────────────────────────────────┐
│  ClaudeVN Marketplace                    │
├─────────────────────────────────────────┤
│ [Agent Browser] [Users] [Orgs] [Access] │
├─────────────────────────────────────────┤
│  🔍 Search agents...                     │
│                                          │
│  ┌───────────┐  ┌───────────┐          │
│  │ Data      │  │ Web       │          │
│  │ Analyzer  │  │ Scraper   │  ...     │
│  └───────────┘  └───────────┘          │
└─────────────────────────────────────────┘
```

### Serving UI
```
┌─────────────────────────────────────────┐
│  ClaudeVN Serving Component              │
├─────────────────────────────────────────┤
│ [Dashboard] [Compute Registry]          │
├─────────────────────────────────────────┤
│  📊 Stats                                │
│  Total Instances: 4                     │
│  Online: 4  Degraded: 0  Offline: 0    │
│                                          │
│  Compute Instances:                     │
│  ┌─────────────────────────────────┐   │
│  │ 🟢 Data Processing Node          │   │
│  │    compute-001                   │   │
│  │    Agents: 3  Tools: 3           │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │ 🟢 Web Services Node             │   │
│  │    compute-002                   │   │
│  │    Agents: 3  Tools: 3           │   │
│  └─────────────────────────────────┘   │
│  ... (2 more)                           │
└─────────────────────────────────────────┘
```

---

## ✅ 5-Minute Full Test

1. **Open Marketplace** (http://localhost:8001)
   - ✓ Browse agents (should see ~10 agents)
   - ✓ Create a user named "Test User"
   - ✓ Verify user appears in list

2. **Open Serving** (http://localhost:8002)
   - ✓ Click "Dashboard" - see 4 instances
   - ✓ Click "Compute Registry" - see instance cards
   - ✓ Verify all show green "online" status

3. **Test Real-Time Updates**
   - Keep Serving UI open
   - In terminal: `./test_serving_ui.sh` (run again)
   - Refresh page - data should persist

4. **Test Navigation**
   - Switch between tabs in each UI
   - Data should load without delay
   - No console errors (press F12 to check)

---

## 🔧 Troubleshooting

**Nothing loads?**
```bash
# Check if services are running
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health

# If not, restart
./stop_all.sh && ./start_all.sh
```

**Serving UI is empty?**
```bash
# Reload test data
./test_serving_ui.sh
```

**Console errors?**
```bash
# Check logs
tail -f logs/marketplace.log
tail -f logs/serving.log
```

---

## 🎯 Success Criteria

After testing, you should have:
- ✅ Created users/organizations in Marketplace
- ✅ Viewed compute instances in Serving
- ✅ Confirmed real-time UI updates
- ✅ No browser console errors
- ✅ Modern, responsive design

---

## 📚 Want More Details?

See `TESTING_GUIDE.md` for comprehensive testing scenarios.

**Current Status:**
- ✅ Marketplace: Fully functional with test data
- ✅ Serving: Fully functional with 4 test compute instances
- ⚠️  Compute: Not yet implemented (Phase 3)

**Ready to Test! Open your browser now! 🚀**

