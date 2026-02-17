# Agent Selection from Marketplace - Test Plan

## Current Architecture Understanding

### How It Works Today

1. **Session Creation** → User submits business problem via Serving API (`/facilitated-sessions/create-facilitated`)
2. **Process Mapper** → Serving invokes Process Mapper (coordinating agent on Compute) to decompose goal into activities
3. **Process Map Storage** → Activities stored in Serving's process map
4. **Activity Selection** → For each activity, Agent Selector can be invoked
5. **Agent Selector** → Queries Marketplace for candidates, then uses Agent Selector coordinating agent (on Compute) to recommend best matches
6. **Team Assembly** → Selected agents are assigned to activities
7. **Execution** → Compute executes assigned agents using agent executor

### Component Locations

- **Marketplace** (port 8001): Agent registry, search, capabilities catalog
- **Serving** (port 8002): Process maps, session management, routes messages to compute
- **Compute** (port 8003+): Executes ALL agents (coordinating + specialized)

### Key Files

- **Marketplace:** `marketplace/api/agents.py` - Agent search/filtering
- **Serving:** `serving/services/coordinating_team_service.py` - Routes to Agent Selector
- **Serving:** `serving/api/process_maps.py` - `/select-participants` endpoint
- **Compute:** `compute/services/agent_executor.py` - Executes agents
- **Compute:** `compute/services/serving_client.py` - Fetches agents from marketplace via Serving
- **Compute:** `compute/data/compute/agents/coordinating/agent-selector-agent.json` - Agent Selector definition

---

## Test Plan: Agent Selection Functionality

### Prerequisites
- [ ] All services running (marketplace, serving, compute)
- [ ] Marketplace has agents registered
- [ ] Agent Selector coordinating agent exists on Compute

### Test 1: Verify Agent Selector Agent Exists
**Goal:** Confirm Agent Selector coordinating agent is available

**Steps:**
1. Check if `agent-selector-v1` exists in compute
2. Verify agent definition has proper capabilities

**Expected:**
- Agent Selector agent JSON file exists
- Agent is registered on compute instance

**Verification Command:**
```bash
curl http://localhost:8003/agents | jq '.agents[] | select(.agent_id == "agent-selector-v1")'
```

---

### Test 2: Verify Marketplace Has Agents
**Goal:** Confirm marketplace has specialized agents available for selection

**Steps:**
1. Query marketplace for all agents
2. Verify agents have capabilities defined
3. Check agent types (specialized vs coordinating)

**Expected:**
- Multiple specialized agents available
- Each agent has capabilities array
- Agents have descriptive names and descriptions

**Verification Command:**
```bash
curl http://localhost:8001/agents | jq '.items[] | {agent_id, name, type, capabilities}'
```

---

### Test 3: Create Facilitated Session
**Goal:** Start a session with a business problem

**Steps:**
1. POST to `/facilitated-sessions/create-facilitated`
2. Submit a test business goal
3. Verify session created
4. Verify Process Mapper created initial activities

**Test Business Goal:**
"Analyze customer churn data and create a retention improvement strategy"

**Expected:**
- Session created successfully
- Process map has 3-5 activities
- Activities have clear goals

**Verification Command:**
```bash
curl -X POST http://localhost:8002/facilitated-sessions/create-facilitated \
  -H "Content-Type: application/json" \
  -d '{
    "business_goal": "Analyze customer churn data and create a retention improvement strategy",
    "session_id": "test-selection-001"
  }' | jq .
```

---

### Test 4: Query Marketplace for Agent Candidates
**Goal:** Search marketplace for agents matching activity requirements

**Steps:**
1. Choose an activity from the process map (e.g., "Analyze churn data")
2. Identify required capabilities (e.g., `data_analysis`, `customer_insights`)
3. Query marketplace with those capabilities
4. Verify matching agents returned

**Expected:**
- Marketplace returns agents with matching capabilities
- Results include agent metadata (capabilities, description, type)
- At least 2-3 candidates returned

**Verification Command:**
```bash
curl "http://localhost:8001/agents?capabilities=data_analysis,customer_insights" | jq .
```

---

### Test 5: Invoke Agent Selector for Activity
**Goal:** Use Agent Selector to recommend best agents for an activity

**Steps:**
1. Get session_id and activity_id from Test 3
2. POST to `/process-maps/sessions/{session_id}/activities/{activity_id}/select-participants`
3. Provide capabilities and domain requirements
4. Review Agent Selector's recommendations

**Expected:**
- Agent Selector analyzes candidates
- Returns scored recommendations
- Includes primary recommendation (highest score)
- Includes backup option
- Provides reasoning for selections

**Verification Command:**
```bash
# Replace {session_id} and {activity_id} with actual values from Test 3
curl -X POST "http://localhost:8002/process-maps/sessions/test-selection-001/activities/activity-1/select-participants" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": ["data_analysis", "customer_insights"],
    "domain": "customer_retention"
  }' | jq .
```

---

### Test 6: Verify Agent Selector Decision Quality
**Goal:** Confirm Agent Selector makes intelligent recommendations

**Test Cases:**
a) **Exact Capability Match** - Agent has all required capabilities
b) **Partial Match** - Agent has some capabilities but not all
c) **Domain Expertise** - Agent specializes in relevant domain
d) **No Match** - No agents have required capabilities

**Expected:**
- Agents with exact matches score higher
- Domain expertise weighted appropriately
- Backup recommendations make sense
- Clear reasoning provided for each recommendation

---

### Test 7: Assign Selected Agents to Activity
**Goal:** Assign recommended agents to activity in process map

**Steps:**
1. Take primary recommendation from Test 5
2. Assign agent to activity
3. Verify activity shows assigned agents
4. Check agent is ready for execution

**Expected:**
- Activity updated with assigned agents
- Process map reflects assignment
- Activity status progresses appropriately

---

### Test 8: Multi-Activity Agent Selection
**Goal:** Select agents for multiple activities in same session

**Steps:**
1. For each activity in process map (from Test 3)
2. Run agent selection (Test 5)
3. Verify different activities can have different agents
4. Verify same agent can be assigned to multiple activities if appropriate

**Expected:**
- Each activity gets suitable agent recommendations
- Agent Selector considers activity dependencies
- Team composition is coherent (not too many agents)
- Critical activities get strongest agents

---

### Test 9: Agent Selection with Constraints
**Goal:** Test edge cases and constraints

**Test Cases:**
a) **No agents available** - Required capability doesn't exist in marketplace
b) **Single agent** - Only one agent matches requirements
c) **Many agents** - 10+ agents match, need ranking
d) **Coordinating agents** - Should NOT be selected for specialized work

**Expected:**
- System handles "no matches" gracefully
- Single agent scenarios work
- Ranking prioritizes best agents when many matches
- Coordinating agents excluded from specialized agent selection

---

### Test 10: End-to-End Agent Selection Flow
**Goal:** Complete workflow from problem to team assembly

**Steps:**
1. Submit business problem
2. Process Mapper creates activities
3. For each activity, invoke Agent Selector
4. Review complete team composition
5. Verify coordinating agents collaborate appropriately

**Expected:**
- Full workflow completes successfully
- Appropriate team assembled for business problem
- Each activity has suitable agent(s) assigned
- Process map ready for execution

---

## Current Implementation Gaps

### ✅ Already Implemented
- Marketplace agent storage and search
- Agent Selector coordinating agent definition  
- Serving routes to Agent Selector on Compute
- Compute executes Agent Selector via agent executor
- Process map stores activities and assignments

### ❌ CRITICAL GAP FOUND

**Issue:** Marketplace agents missing `agent_id` field
- All agents in marketplace seed data have `agent_id: null`
- Serving tries to fetch agents by ID: `GET /api/v1/agents/process-mapper-v1`
- This fails with 404 because no agent has that ID
- **Root Cause:** `marketplace/seed_data/agents.json` definitions lack `agent_id` field
- **Fix Required:** Add proper `agent_id` to all marketplace seed data agents

### ⚠️ Potential Gaps (To Verify During Testing)

1. **Agent Selector Prompt Quality**
   - Does the prompt to Agent Selector include enough context?
   - Are capability matching heuristics clear?
   - Is domain expertise properly weighted?

2. **Marketplace Query Optimization**
   - Can we search by multiple capabilities (AND vs OR)?
   - Are there filters for agent type (exclude coordinating agents)?
   - Can we limit results to top N candidates?

3. **Agent Assignment Persistence**
   - Where are agent assignments stored?
   - Can assignments be updated/changed?
   - Are assignments persisted if session crashes?

4. **Coordinating Agent Collaboration**
   - Does Process Mapper inform Agent Selector about dependencies?
   - Do multiple coordinating agents collaborate on team assembly?
   - Is there a "Team Assembler" coordinating agent, or does Agent Selector handle this alone?

5. **Execution Verification**
   - After agents selected, does execution actually use them?
   - Does Compute fetch assigned agents from marketplace correctly?
   - Are agent definitions cached appropriately?

---

## Testing Commands

### Quick Test Script
```bash
#!/bin/bash
# test_agent_selection.sh

# Test 1: Check Agent Selector exists
echo "=== Test 1: Agent Selector Exists ==="
curl -s http://localhost:8003/agents | jq '.agents[] | select(.agent_id == "agent-selector-v1")'

# Test 2: Check Marketplace Agents
echo -e "\n=== Test 2: Marketplace Agents ==="
curl -s http://localhost:8001/agents | jq '.items[] | {agent_id, name, type, capabilities}' | head -20

# Test 3: Create Session
echo -e "\n=== Test 3: Create Facilitated Session ==="
SESSION_ID="test-$(date +%s)"
curl -s -X POST http://localhost:8002/facilitated-sessions/create-facilitated \
  -H "Content-Type: application/json" \
  -d "{
    \"business_goal\": \"Analyze customer churn data and create a retention improvement strategy\",
    \"session_id\": \"$SESSION_ID\"
  }" | jq .

# Test 4: Query for Candidates
echo -e "\n=== Test 4: Query Marketplace for Candidates ==="
curl -s "http://localhost:8001/agents?capabilities=data_analysis,customer_insights" | jq '.items[] | {agent_id, name, capabilities}'

# Test 5: Invoke Agent Selector
# (Requires session_id and activity_id from Test 3 output)
echo -e "\n=== Test 5: Invoke Agent Selector ==="
echo "NOTE: Replace {session_id} and {activity_id} with actual values from Test 3"
```

---

## Success Criteria

### Minimum Viable Test
- [ ] Agent Selector coordinating agent exists and is executable
- [ ] Marketplace returns agents when queried by capabilities
- [ ] Agent Selector can be invoked via Serving API
- [ ] Agent Selector returns recommendations with reasoning
- [ ] Recommendations are appropriate for activity requirements

### Full Functionality
- [ ] Complete workflow works end-to-end
- [ ] Multiple coordinating agents collaborate on team assembly
- [ ] Selected agents are actually used during execution
- [ ] System handles edge cases (no matches, single match, many matches)
- [ ] Performance is acceptable (selection completes in <5 seconds)

---

## Notes for Testing

1. **Start Fresh**: Consider clearing data directories before testing to ensure clean state
2. **Log Monitoring**: Watch compute logs to see Agent Selector execution in real-time
3. **Marketplace Seeding**: May need to seed marketplace with sample agents if empty
4. **Agent Definitions**: Verify coordinating agents exist in `compute/data/compute/agents/coordinating/`
5. **Section 3 Note**: Remember to verify all execution happens in Compute module (user's reminder)
