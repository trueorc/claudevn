# Facilitated Process - Quick Start Guide

**Goal:** Implement v0.2.0 facilitated process architecture incrementally with UI testing at each phase.

---

## Architecture at a Glance

```
┌──────────────────────────────────────────────────────────┐
│  USER: "Increase customer retention by 20%"              │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  SERVING (Lightweight Broker)                           │
│  • Routes messages to agents on compute                 │
│  • Stores process maps                                  │
│  • Manages event bus                                    │
│  • NO agent execution                                   │
└────────────┬────────────────────────────────────────────┘
             │
             ├──► Marketplace (search agents)
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  COMPUTE (Heavy Execution)                              │
│                                                          │
│  Coordinating Agents (NEW):                             │
│  • Process Mapper    - Creates/evolves process maps     │
│  • Agent Selector    - Picks participants               │
│  • Activity Facilitator - Guides conversations          │
│  • Consistency Manager - Detects contradictions         │
│  • Progress Reporter  - Tracks status                   │
│  • Result Synthesizer - Assembles deliverables          │
│                                                          │
│  Specialized Agents (EXISTING):                         │
│  • DataAnalyst, ContentWriter, CodeReviewer, etc.       │
│                                                          │
│  ALL agents execute here using existing agent executor  │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Phases - Summary

| Phase | Focus | Duration | Key Deliverable | UI Test |
|-------|-------|----------|-----------------|---------|
| **1** | Models & Storage | 1 week | ProcessMap viewer | View process map graph |
| **2** | Process Mapper | 1 week | Initial map creation | Business goal → activities |
| **3** | Agent Selector | 1 week | Participant matching | Activity → recommendations |
| **4** | Activity Facilitator | 1-2 weeks | Conversation management | Watch facilitation thread |
| **5** | Support Agents | 1 week | Consistency/Progress/Synthesis | View all features |
| **6** | Event Bus | 1 week | Complete integration | End-to-end flow |

**Total:** 6-7 weeks

---

## Phase 1: Foundation (Week 1)

### What We Build
- `ProcessMap` and `Activity` models (vs `ExecutionPipeline` and `PipelineStep`)
- `ProcessMapService` for storage
- API endpoints: `/process-maps/sessions/{id}/map`
- UI: `ProcessMapViewer` component

### Key Differences: ProcessMap vs Pipeline

| Aspect | Pipeline (v0.1.8) | ProcessMap (v0.2.0) |
|--------|------------------|---------------------|
| Structure | Steps with order numbers | Activities with goals |
| Planning | Predetermined upfront | Emergent through facilitation |
| Dependencies | Fixed | Discovered |
| Changes | Deviation from plan | Natural evolution |
| Versioning | Single version | Multiple versions (evolution) |

### UI Test
```
1. Start services: ./start_all.sh
2. Navigate to: http://localhost:8002
3. Create test process map via API
4. Open session → View process map
5. See activities as nodes, dependencies as arrows
6. Activities colored by status:
   - Blue: proposed
   - Yellow: in_progress
   - Green: goal_met
   - Red: blocked
```

### Code Locations
```
serving/models/process_map.py          # NEW models
serving/services/process_map_service.py # NEW service
serving/api/process_maps.py            # NEW endpoints
serving/frontend/src/components/
  ProcessMapViewer.jsx                 # NEW component
```

---

## Phase 2: Process Mapper (Week 2)

### What We Build
- `process-mapper-agent.json` in compute
- `CoordinatingTeamService` in serving (routes to coordinating agents)
- `/sessions/create-facilitated` endpoint
- UI mode selector (Pipeline vs Facilitated)

### How It Works
```
User: "Increase customer retention by 20%"
  ↓
Serving: Creates facilitated session
  ↓
Serving → Compute: "Process Mapper, analyze this goal"
  ↓
Process Mapper (on Compute): Uses LLM to propose activities
  Output: [
    Activity 1: "Understand current retention"
    Activity 2: "Identify retention drivers"
    Activity 3: "Develop improvement strategies"
  ]
  ↓
Serving: Stores activities in process map
  ↓
UI: Shows initial process map with 3 activities
```

### UI Test
```
1. Click "Create New Session"
2. Enter goal: "Increase customer retention by 20%"
3. Select mode: "Facilitated Process (v0.2.0)"
4. Submit
5. See Process Mapper generate 3-5 activities
6. View process map showing proposed activities
7. Note: Activities are goal-oriented, not implementation steps
```

### Code Locations
```
compute/data/compute/agents/coordinating/
  process-mapper-agent.json            # NEW agent definition
serving/services/coordinating_team_service.py # NEW service
serving/api/sessions.py                # EXTEND with create-facilitated
serving/frontend/src/components/
  CreateSessionModal.jsx               # EXTEND with mode selector
```

---

## Phase 3: Agent Selector (Week 3)

### What We Build
- `agent-selector-agent.json` in compute
- Agent Selector service integration
- Marketplace query integration
- `/activities/{id}/select-participants` endpoint
- `ActivityParticipants` UI component

### How It Works
```
Activity: "Understand current retention"
  ↓
Serving → Compute: "Agent Selector, analyze requirements"
  ↓
Agent Selector: "Needs data_analysis, customer_metrics, customer_retention domain"
  ↓
Serving → Marketplace: Search for matching agents
  ↓
Marketplace: Returns 8 candidates
  ↓
Serving → Compute: "Agent Selector, score these candidates"
  ↓
Agent Selector: 
  Primary: DataAnalystAgent (score 85)
  Backup: CustomerInsightsAgent (score 75)
  Reasoning: "DataAnalyst has complete capability coverage..."
  ↓
Serving → Compute Registry: "Which compute has DataAnalyst?"
  ↓
Compute Registry: "compute-002 has DataAnalystAgent"
  ↓
UI: Shows recommendations with reasoning
```

### UI Test
```
1. Open facilitated session
2. Click on Activity 1 in process map
3. Click "Select Participants"
4. See Agent Selector analysis:
   - Required capabilities
   - Domain expertise
   - Marketplace search results (candidates)
5. See scoring and recommendations:
   - Primary agent with score
   - Backup agent
   - Reasoning explanation
6. Click "Assign Participants"
7. See agents assigned to activity
```

### Code Locations
```
compute/data/compute/agents/coordinating/
  agent-selector-agent.json            # NEW agent definition
serving/services/coordinating_team_service.py # EXTEND
serving/api/process_maps.py            # EXTEND
serving/frontend/src/components/
  ActivityParticipants.jsx             # NEW component
```

---

## Phase 4: Activity Facilitator (Weeks 4-5)

### What We Build
- `activity-facilitator-agent.json` in compute
- `Exchange` and `FacilitationResult` models
- `FacilitationService` with conversation loop
- `/activities/{id}/facilitate` endpoint
- `ActivityConversation` UI component

### How It Works
```
Activity: "Understand current retention"
Participants: DataAnalystAgent

Facilitation Loop:
  Exchange 1:
    Facilitator: "We need to understand retention. What data do you need?"
  
  Exchange 2:
    DataAnalyst: "I need customer database access and timeframe."
  
  Exchange 3:
    Facilitator: "Timeframe is last 12 months. Do you have database access?"
  
  Exchange 4:
    DataAnalyst: "No, I need credentials."
  
  Exchange 5:
    Facilitator: "We're blocked on database access."
  
  Result: BLOCKED - "Database access needed"
```

### UI Test
```
1. Select activity with assigned participants
2. Click "Start Facilitation"
3. Watch real-time conversation thread:
   - Facilitator messages (blue)
   - Agent responses (green)
4. See status change: proposed → in_progress
5. See blocker identified: "Database access needed"
6. Activity status: in_progress → blocked
7. View outputs JSON panel
8. See duration: 2m 34s
```

### Code Locations
```
compute/data/compute/agents/coordinating/
  activity-facilitator-agent.json      # NEW agent definition
serving/models/process_map.py          # EXTEND with Exchange model
serving/services/facilitation_service.py # NEW service
serving/api/process_maps.py            # EXTEND
serving/frontend/src/components/
  ActivityConversation.jsx             # NEW component
```

---

## Phase 5: Support Agents (Week 6)

### Three Agents to Add

#### 1. Consistency Manager
**Purpose:** Detect contradictions across activities

**Example:**
```
Activity 3: "Current retention = 65%"
Activity 7: "Based on 70% retention..."
  ↓
Consistency Manager: "⚠️ INCONSISTENCY DETECTED"
  ↓
Process Mapper: Creates reconciliation activity
```

#### 2. Progress Reporter
**Purpose:** Track session progress

**Example:**
```
Session Dashboard:
- Total activities: 7
- Completed: 3 (43%)
- In progress: 2
- Blocked: 1
- Proposed: 1

Current focus: Activity 5
Blockers: Activity 4 (needs data export)
```

#### 3. Result Synthesizer
**Purpose:** Assemble final deliverable

**Example:**
```
All activities complete
  ↓
Result Synthesizer collects outputs:
- Activity 1 output
- Activity 2 output
- ...
  ↓
Generates:
- Executive Summary
- Key Findings (1, 2, 3...)
- Recommendations
- Supporting Data
```

### UI Test
```
1. Complete multiple activities
2. See Progress Reporter metrics update
3. View Inconsistencies tab → See flagged issues
4. All activities complete → Click "Generate Results"
5. See Result Synthesizer assemble deliverable
6. View final report in UI
```

---

## Phase 6: Event Bus & Integration (Week 7)

### What We Build
- `EventBus` for coordinating agent communication
- Complete end-to-end facilitated session flow
- Comprehensive session dashboard

### Event Flow Example
```
Event 1: ACTIVITY_PROPOSED
  Process Mapper → "Activity 1 proposed"
  ↓
  Agent Selector receives → Analyzes requirements

Event 2: PARTICIPANTS_RECOMMENDED
  Agent Selector → "Recommend DataAnalyst"
  ↓
  Activity Facilitator receives → Begins facilitation

Event 3: BLOCKER_IDENTIFIED
  Activity Facilitator → "Database access needed"
  ↓
  Process Mapper receives → Creates Activity 0

Event 4: MAP_UPDATED
  Process Mapper → "Map evolved v1 → v2"
  ↓
  Progress Reporter receives → Updates metrics
```

### Complete UI Test
```
End-to-End Facilitated Session:

1. Create session: "Increase customer retention by 20%"
2. Process Mapper: Creates Activities 1, 2, 3
3. Select Activity 1 → Assign participants
4. Start facilitation
5. Blocker: "Database access needed"
6. Process Mapper: Creates Activity 0
7. Facilitate Activity 0 → Goal met
8. Return to Activity 1 → Unblocked
9. Complete Activity 1
10. Process map evolves: v1 → v2 → v3
11. Consistency Manager: Flags issue
12. Process Mapper: Creates reconciliation activity
13. Continue until all activities complete
14. Result Synthesizer: Generates deliverable
15. View complete session report

Watch process map evolve in real-time!
```

---

## Testing via UI - Quick Commands

### Start Services
```bash
./start_all.sh

# Verify all running:
# - Marketplace: http://localhost:8001
# - Serving:     http://localhost:8002
# - Compute:     http://localhost:8003
```

### Access UI
```bash
# Serving UI (main dashboard):
http://localhost:8002

# Marketplace UI (agent catalog):
http://localhost:8001
```

### View Logs
```bash
# Follow all logs:
tail -f logs/*.log

# Specific service:
tail -f logs/serving.log
tail -f logs/compute.log
```

### Check Status
```bash
./status.sh

# Should show:
# ✅ Marketplace running
# ✅ Serving running
# ✅ Compute running
# ✅ All agents registered
```

---

## Key Files to Know

### Models
```
serving/models/process_map.py          # ProcessMap, Activity, Exchange
serving/models/pipeline.py             # ExecutionPipeline (v0.1.8)
```

### Services
```
serving/services/process_map_service.py      # Process map storage
serving/services/facilitation_service.py     # Facilitation management
serving/services/coordinating_team_service.py # Route to coordinating agents
serving/services/registry_service.py         # Compute registry (existing)
```

### APIs
```
serving/api/process_maps.py            # Process map endpoints
serving/api/sessions.py                # Session endpoints (extend)
serving/api/pipelines.py               # Pipeline endpoints (v0.1.8)
```

### UI Components
```
serving/frontend/src/components/
  ProcessMapViewer.jsx                 # Visualize process map
  ActivityParticipants.jsx             # Participant selection
  ActivityConversation.jsx             # Facilitation thread
  FacilitatedSessionDashboard.jsx      # Complete dashboard
```

### Coordinating Agents
```
compute/data/compute/agents/coordinating/
  process-mapper-agent.json            # Creates/evolves maps
  agent-selector-agent.json            # Selects participants
  activity-facilitator-agent.json      # Guides conversations
  consistency-manager-agent.json       # Detects contradictions
  progress-reporter-agent.json         # Tracks progress
  result-synthesizer-agent.json        # Assembles results
```

---

## Dual-Mode Support

### Traditional Pipeline (v0.1.8)
```bash
# Create pipeline session:
POST /api/v1/sessions/create
{
  "goal": "Generate Q4 report",
  "mode": "pipeline"
}

# Use ExecutionPipeline model
# Predetermined steps
# Fixed sequence
# Good for well-defined workflows
```

### Facilitated Process (v0.2.0)
```bash
# Create facilitated session:
POST /api/v1/sessions/create-facilitated
{
  "business_goal": "Increase retention by 20%",
  "mode": "facilitated"
}

# Use ProcessMap model
# Emergent activities
# Goal-oriented
# Good for ambiguous problems
```

**Both modes work side-by-side!**

---

## Questions & Decisions

### 1. LLM Provider
**Options:**
- OpenAI GPT-4 (production)
- Anthropic Claude (production)
- Mock provider (testing, zero cost)

**Recommendation:** Use Mock for development, OpenAI for demos

### 2. Real-time Updates
**Options:**
- SSE (Server-Sent Events) - simpler
- WebSocket - bi-directional

**Recommendation:** Start with polling, add SSE in Phase 6

### 3. Storage Backend
**Options:**
- Filesystem (current)
- PostgreSQL (structured queries)
- Redis (fast, ephemeral)

**Recommendation:** Extend filesystem storage for now

### 4. Graph Visualization
**Options:**
- React Flow (popular library)
- D3.js (custom, flexible)
- Cytoscape.js (graph-focused)

**Recommendation:** React Flow (easy integration)

---

## Success Checklist

### Phase 1 ✅
- [ ] Can create ProcessMap via API
- [ ] Can view process map in UI
- [ ] Activities show colored status
- [ ] Dependencies visible as arrows
- [ ] Can see map version number

### Phase 2 ✅
- [ ] Business goal → Initial activities works
- [ ] Process Mapper generates 3-5 activities
- [ ] Activities are goal-oriented
- [ ] Process map appears in UI

### Phase 3 ✅
- [ ] Activity → Participant recommendations works
- [ ] Marketplace search returns candidates
- [ ] Agent Selector scores and recommends
- [ ] Participants assigned to activity

### Phase 4 ✅
- [ ] Facilitation conversation visible
- [ ] Facilitator and agent exchange messages
- [ ] Goal assessment works
- [ ] Blockers identified
- [ ] Activity status updates

### Phase 5 ✅
- [ ] Consistency Manager flags contradictions
- [ ] Progress Reporter shows metrics
- [ ] Result Synthesizer creates deliverable

### Phase 6 ✅
- [ ] Event bus routes messages
- [ ] Complete end-to-end flow works
- [ ] Process map evolves
- [ ] All coordinating agents coordinate
- [ ] UI dashboard shows everything

---

## Next Steps

1. **Review implementation plan**
   - Read: `FACILITATED_PROCESS_IMPLEMENTATION_PLAN.md`
   - Understand architecture: `FACILITATED_PROCESS_ARCHITECTURE.md`

2. **Set up development branch**
   ```bash
   git checkout -b feature/facilitated-process
   ```

3. **Start Phase 1**
   - Create ProcessMap models
   - Build ProcessMapService
   - Add API endpoints
   - Build UI component

4. **Test via UI**
   - Manual testing after each phase
   - Visual verification
   - Interactive debugging

5. **Iterate**
   - Phase by phase
   - Test incrementally
   - Demo progress
   - Adjust as needed

---

## Getting Help

**Documentation:**
- Implementation Plan: `FACILITATED_PROCESS_IMPLEMENTATION_PLAN.md`
- Architecture: `FACILITATED_PROCESS_ARCHITECTURE.md`
- Integration: `FACILITATED_PROCESS_INTEGRATION.md`
- Summary: `FACILITATED_PROCESS_SUMMARY.md`

**Code Examples:**
- Existing pipeline: `serving/models/pipeline.py`
- Agent execution: `compute/services/agent_executor.py`
- UI components: `serving/frontend/src/components/`

---

**Ready to build the future of AI orchestration? Let's start with Phase 1!** 🚀

