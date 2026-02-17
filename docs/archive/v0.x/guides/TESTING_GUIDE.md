# ClaudeVN Platform - UI Testing Guide 🧪

## Prerequisites
Make sure all services are running:
```bash
./start_all.sh
```

---

## 1️⃣ Marketplace UI Testing
**URL**: http://localhost:8001

### What You Can Test:

#### A. Browse Agents (Pre-loaded)
1. Open http://localhost:8001 in your browser
2. Click **"Agent Browser"** tab
3. You should see ~10 pre-loaded sample agents
4. **Test interactions**:
   - Search for agents by name (e.g., "data", "web")
   - Filter by category
   - Click on an agent card to view details
   - Check the agent's capabilities, tools, and metadata

#### B. User Management
1. Click **"User Management"** tab
2. **Create a test user**:
   - Click "Add User"
   - Fill in: Name, Email, Role (admin/developer/user)
   - Click "Create"
3. **Test operations**:
   - View user list
   - Edit a user (click pencil icon)
   - Delete a user (click trash icon)
   - Verify the UI updates in real-time

#### C. Organization Management
1. Click **"Organizations"** tab
2. **Create a test organization**:
   - Click "Add Organization"
   - Fill in: Name, Description
   - Click "Create"
3. **Test operations**:
   - View organization list
   - Add members to organization
   - Edit organization details
   - Delete organization

#### D. Access Control
1. Click **"Access Control"** tab
2. **Grant permissions**:
   - Select a user
   - Select an agent/tool
   - Set permission level (read/write/admin)
   - Grant access
3. **Test operations**:
   - View all access control entries
   - Revoke access
   - Filter by user or resource

---

## 2️⃣ Serving UI Testing
**URL**: http://localhost:8002

### Current State:
The Serving UI is designed to show **compute instances** that register with the system. Since we haven't implemented the compute component yet, you have two options:

#### Option A: View Empty State (Quick)
1. Open http://localhost:8002
2. Navigate to **"Compute Registry"** tab
3. You'll see an empty state with "No compute instances registered"
4. This confirms the UI is working

#### Option B: Test with Mock Data (Recommended)
Run this script to register test compute instances:

```bash
./test_serving_ui.sh
```

Then refresh http://localhost:8002 and you'll see:
- **Dashboard** showing stats (total instances, status breakdown)
- **Compute Registry** showing registered instances with:
  - Instance name, ID, status
  - Endpoint URL
  - Capabilities (agents, tools, resources)
  - Last heartbeat time
  - Color-coded status badges (online=green, degraded=yellow, offline=red)

### What to Look For:
- ✅ Clean, modern UI layout
- ✅ Real-time status indicators
- ✅ Capability aggregation (shows all available agents/tools)
- ✅ Instance health monitoring
- ✅ Responsive design

---

## 3️⃣ End-to-End Workflow Test

### Scenario: Set up a complete agent execution environment

1. **Marketplace - Register Agents**:
   - Go to http://localhost:8001
   - Browse the pre-loaded agents
   - Note their capabilities

2. **Marketplace - Create Users & Organizations**:
   - Create a "DataTeam" organization
   - Add team members (users)
   - Grant them access to specific agents

3. **Serving - View Compute Resources**:
   - Run `./test_serving_ui.sh` to simulate compute instances
   - Go to http://localhost:8002
   - View the "virtual compute resource" (all registered instances)
   - Check aggregated capabilities

4. **Verify Integration Points**:
   - Marketplace shows what agents are available
   - Serving shows where those agents can run (compute capacity)
   - Access control determines who can use what

---

## 4️⃣ Testing Checklist

### Marketplace UI ✅
- [ ] Agent browser loads and displays agents
- [ ] Search/filter functionality works
- [ ] User creation/editing/deletion works
- [ ] Organization management works
- [ ] Access control grants/revokes work
- [ ] UI is responsive and updates in real-time

### Serving UI ✅
- [ ] Dashboard loads without errors
- [ ] Compute Registry displays registered instances
- [ ] Status indicators are color-coded correctly
- [ ] Capability aggregation shows all agents/tools
- [ ] Last heartbeat timestamps update
- [ ] Empty states display properly when no instances

### Cross-Component ✅
- [ ] Both UIs load without console errors
- [ ] Navigation works smoothly
- [ ] Styling is consistent and modern
- [ ] Data persists across page refreshes

---

## 5️⃣ Known Limitations (Expected)

1. **No Compute Component Yet**: 
   - Serving UI will be empty unless you use test data
   - This is expected - compute component is next phase

2. **No Real Agent Execution**:
   - You can browse agents and manage access
   - Actual execution pipeline is not yet implemented

3. **No Marketplace Proxy**:
   - Serving can't yet query multiple marketplaces
   - This feature is planned for Phase 2

---

## 6️⃣ Troubleshooting

### UI doesn't load?
```bash
# Check services are running
curl http://localhost:8001/api/v1/health
curl http://localhost:8002/api/v1/health

# Check logs
tail -f logs/*.log
```

### No data showing?
```bash
# For Marketplace: Agents should be pre-loaded
# Check: http://localhost:8001/api/v1/agents

# For Serving: Use test script
./test_serving_ui.sh
```

### Port conflicts?
```bash
# Stop and restart
./stop_all.sh
./start_all.sh
```

---

## 🎯 Recommended Testing Order

1. **Start Simple**: Test Marketplace UI first (has pre-loaded data)
2. **Test CRUD Operations**: Create/edit/delete users and organizations
3. **Populate Serving**: Run `./test_serving_ui.sh`
4. **View Integration**: See how compute instances show available agents
5. **Test Edge Cases**: Try empty states, invalid inputs, rapid clicks

---

## 📊 What Success Looks Like

After testing, you should see:
- ✅ Modern, responsive UIs for both components
- ✅ Real-time data updates without page refresh
- ✅ Proper error handling and validation
- ✅ Clear visual feedback for all actions
- ✅ Consistent design language across both UIs

---

## Next Steps After Testing

Once you're satisfied with UI functionality:
1. Implement Compute component with registration
2. Add agent execution pipeline
3. Implement marketplace proxy (multi-marketplace support)
4. Add authentication/authorization layer
5. Build monitoring and observability features

---

**Happy Testing! 🚀**

For questions or issues, check the logs at: `logs/*.log`

