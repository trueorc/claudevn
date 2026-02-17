# Facilitated Process Testing Guide

## Current Status (Nov 24, 2025)

### ✅ What's Working
1. **Session Creation** - Facilitated sessions can be created
2. **Process Map Storage** - Maps are created and stored
3. **Process Map API** - All CRUD endpoints work
4. **UI Components** - ProcessMapViewer renders correctly
5. **Data Models** - All models defined and working
6. **Coordinating Agents** - 6 agent definitions exist

### ⚠️ Known Issues
1. **Process Mapper Invocation** - ComputeRegistry method mismatch
   - Sessions work but create empty process maps (0 activities)
   - Process Mapper agent definition exists but can't be invoked yet
   - Error: `'ComputeRegistry' object has no attribute 'find_instances_with_agent'`

## Testing Methods

### Method 1: API Testing (Works Now)

#### Create Facilitated Session
```bash
curl -X POST http://localhost:8002/api/v1/sessions/create-facilitated \
  -H "Content-Type: application/json" \
  -d '{"business_goal": "Increase customer retention by 20%"}'
```

**Expected Response:**
```json
{
  "session_id": "sess-xxxxxxxx",
  "process_map_id": "map-sess-xxxxxxxx",
  "business_goal": "Increase customer retention by 20%",
  "initial_activities": 0,
  "map_version": 1,
  "status": "initiated",
  "message": "Session created but Process Mapper unavailable: [error]"
}
```

#### Get Process Map
```bash
curl http://localhost:8002/api/v1/process-maps/sessions/sess-xxxxxxxx/map
```

#### Add Activity Manually
```bash
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/sess-xxxxxxxx/map/activities \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Analyze customer churn data",
    "description": "Identify patterns in customer exit data",
    "depends_on": []
  }'
```

#### Update Activity Status
```bash
curl -X PUT http://localhost:8002/api/v1/process-maps/sessions/sess-xxxxxxxx/activities/act-1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

#### Get Progress
```bash
curl http://localhost:8002/api/v1/process-maps/sessions/sess-xxxxxxxx/map/progress
```

### Method 2: UI Testing (Partially Works)

#### Access UI
1. Open browser: http://localhost:8002
2. Click "Process Maps" tab
3. View ProcessMapViewer component

#### Create Session (UI)
1. Click "✨ Create New Facilitated Session"
2. Enter business goal (e.g., "Increase customer retention")
3. Click "🚀 Create Session"

**Current Behavior:**
- ✅ Session is created
- ✅ Process map is created
- ⚠️ No activities generated (Process Mapper issue)
- ✅ UI shows empty map with session info

#### Manual Activity Testing
After creating a session:

1. **Load Session**
   - Enter session ID in "Load Existing Session" field
   - Click "Load Process Map"

2. **Add Activity**
   - Click "+ Add Activity"
   - Enter goal and description
   - Click "Add Activity"
   - ✅ Activity appears in grid

3. **Update Status**
   - Click activity card
   - Use dropdown to change status
   - ✅ Status updates and colors change

4. **View History**
   - Click "View History"
   - ✅ Shows map versions

### Method 3: Direct Data Model Testing

#### Python REPL
```python
# Start Python in project directory
python3

# Import models
from serving.models.process_map import ProcessMap, Activity, ActivityStatus

# Create process map
pm = ProcessMap(
    map_id="test-map-1",
    session_id="test-sess-1",
    business_goal="Test goal",
    created_by="test-user"
)

# Create activity
activity = Activity(
    activity_id="act-1",
    goal="Test activity",
    status=ActivityStatus.PROPOSED
)

# Add to map
pm.activities["act-1"] = activity

# Check progress
print(pm.get_progress())
```

## What You CAN Test Right Now

### 1. Data Model Validation
- ✅ ProcessMap creation
- ✅ Activity creation
- ✅ Status transitions
- ✅ Progress calculation
- ✅ History tracking

### 2. API Endpoints
- ✅ Session creation (empty maps)
- ✅ Process map CRUD
- ✅ Activity CRUD
- ✅ Status updates
- ✅ Progress retrieval
- ✅ History retrieval

### 3. UI Components
- ✅ ProcessMapViewer renders
- ✅ Session creation form works
- ✅ Activity grid displays
- ✅ Status indicators show correct colors
- ✅ Progress bar calculates correctly
- ✅ History modal displays

### 4. Manual Workflow
```bash
# 1. Create session
SESSION_ID=$(curl -s -X POST http://localhost:8002/api/v1/sessions/create-facilitated \
  -H "Content-Type: application/json" \
  -d '{"business_goal": "Test workflow"}' | jq -r '.session_id')

echo "Session: $SESSION_ID"

# 2. Add activities manually
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/$SESSION_ID/map/activities \
  -H "Content-Type: application/json" \
  -d '{"goal": "Activity 1", "depends_on": []}'

curl -X POST http://localhost:8002/api/v1/process-maps/sessions/$SESSION_ID/map/activities \
  -H "Content-Type: application/json" \
  -d '{"goal": "Activity 2", "depends_on": ["act-1"]}'

# 3. Check progress
curl http://localhost:8002/api/v1/process-maps/sessions/$SESSION_ID/map/progress | jq

# 4. Update status
curl -X PUT http://localhost:8002/api/v1/process-maps/sessions/$SESSION_ID/activities/act-1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'

# 5. View in UI
echo "View in browser: http://localhost:8002"
echo "Load session: $SESSION_ID"
```

## What CANNOT Be Tested Yet

### ❌ Process Mapper Integration
- Auto-generating activities from business goals
- Requires fixing ComputeRegistry.find_instances_with_agent()

### ❌ Agent Selector
- Querying marketplace for agents
- Requires Process Mapper to create activities first

### ❌ Activity Facilitator
- Starting facilitated conversations
- Requires assigned agents

### ❌ Monitoring Agents
- Consistency Manager
- Progress Reporter  
- Result Synthesizer
- All require activities with exchanges

## Next Steps to Enable Full Testing

### 1. Fix ComputeRegistry Method (Priority 1)
The CoordinatingTeamService expects:
```python
instances = self.compute_registry.find_instances_with_agent(agent_id)
```

But ComputeRegistry has:
```python
def find_instances_by_agent(self, agent_id: str, online_only: bool = True)
```

**Fix:** Update coordinating_team_service.py to use correct method name.

### 2. Verify Agent Loading (Priority 2)
Ensure coordinating agents are loaded by compute:
```bash
curl http://localhost:8003/agents | jq '.agents[] | select(.type=="coordinating")'
```

### 3. Test Process Mapper (Priority 3)
Once methods are fixed, test:
```bash
curl -X POST http://localhost:8002/api/v1/sessions/create-facilitated \
  -H "Content-Type: application/json" \
  -d '{"business_goal": "Increase customer retention by 20%"}'
```

Should return `initial_activities > 0`.

## Debugging Tips

### Check Logs
```bash
# All logs
tail -f logs/*.log

# Just serving
tail -f logs/serving.log | grep -i "facilitated\|process.map\|ERROR"

# Just compute
tail -f logs/compute.log | grep -i "agent\|mapper"
```

### Check Data Files
```bash
# Process maps
ls -la data/serving/process_maps/

# View a process map
cat data/serving/process_maps/sess-xxxxx_map.json | jq
```

### Check Agent Definitions
```bash
# List coordinating agents
ls compute/data/compute/agents/coordinating/

# View Process Mapper
cat compute/data/compute/agents/coordinating/process-mapper-agent.json | jq
```

## Success Criteria

### Phase 1 (Current - Partially Complete)
- ✅ Data models work
- ✅ API endpoints respond
- ✅ UI renders
- ✅ Manual workflow possible
- ⚠️ Process Mapper needs fixing

### Phase 2 (Next)
- ⏳ Process Mapper generates activities
- ⏳ Agent Selector recommends participants
- ⏳ Activities can be facilitated

### Phase 3 (Future)
- ⏳ Full end-to-end workflow
- ⏳ Monitoring agents functional
- ⏳ Result synthesis working

## Summary

**You CAN test:**
- Session creation
- Process map management
- Manual activity addition
- Status updates
- UI components
- Data models
- API endpoints

**You CANNOT test yet:**
- Automated activity generation (Process Mapper)
- Agent selection (requires activities)
- Facilitation (requires agents)
- Monitoring (requires exchanges)

**Next Fix:** Update coordinating_team_service.py to use correct ComputeRegistry method name.

