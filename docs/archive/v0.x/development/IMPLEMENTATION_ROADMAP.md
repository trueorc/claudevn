# Facilitated Process Implementation - Roadmap

**Version:** 0.2.0  
**Date:** November 24, 2024  
**Status:** Ready to Begin

---

## What We're Building

Transform ClaudeVN from **traditional pipelines** (predetermined steps) to **facilitated processes** (goal-oriented, emergent workflows).

### The Shift

```
FROM: "Here's the plan. Execute these steps."
TO:   "Here's the goal. Let's figure it out together."
```

---

## Current State vs Future State

### v0.1.8 - Traditional Pipeline (Current) ✅

```python
pipeline = ExecutionPipeline(
    steps=[
        PipelineStep(order=1, agent="data-analyst", ...),
        PipelineStep(order=2, agent="content-writer", ...),
        PipelineStep(order=3, agent="report-formatter", ...)
    ]
)
```

**Characteristics:**
- Fixed sequence
- Predetermined steps
- Upfront planning required
- Good for well-defined workflows

### v0.2.0 - Facilitated Process (Target) 🎯

```python
process_map = ProcessMap(
    business_goal="Increase customer retention by 20%",
    activities=[
        Activity(goal="Understand current retention", status="proposed"),
        Activity(goal="Identify retention drivers", status="proposed"),
        Activity(goal="Develop improvement strategies", status="proposed")
    ]
)
# Activities emerge and evolve as work progresses
```

**Characteristics:**
- Goal-oriented activities
- Emergent structure
- Evolves as understanding deepens
- Good for ambiguous, complex problems

---

## Implementation Approach

### 6 Phases, 6-7 Weeks

```
Phase 1: Foundation            [█████████░] Week 1
  └─ Models, Storage, API, UI

Phase 2: Process Mapper        [░░░░░░░░░░] Week 2
  └─ First coordinating agent

Phase 3: Agent Selector        [░░░░░░░░░░] Week 3
  └─ Participant matching

Phase 4: Activity Facilitator  [░░░░░░░░░░] Weeks 4-5
  └─ Conversation management

Phase 5: Support Agents        [░░░░░░░░░░] Week 6
  └─ Consistency, Progress, Synthesis

Phase 6: Integration           [░░░░░░░░░░] Week 7
  └─ Event bus, complete flow
```

### Key Principle: UI-Testable Progress

Every phase delivers working functionality you can test via UI:
- **Phase 1:** View process map graph
- **Phase 2:** See Process Mapper generate activities
- **Phase 3:** Watch Agent Selector recommend participants
- **Phase 4:** Watch facilitation conversations
- **Phase 5:** See all coordinating agents work
- **Phase 6:** Complete end-to-end facilitated session

---

## Architecture Overview

### Where Everything Lives

```
┌─────────────────────────────────────────────────────────┐
│  MARKETPLACE (Port 8001) - UNCHANGED                    │
│  ✅ Agent catalog                                       │
│  ✅ Search API                                          │
│  ✅ Access control                                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  SERVING (Port 8002) - LIGHTWEIGHT ROUTING ADDED        │
│                                                          │
│  EXISTING (v0.1.8):                                     │
│  ✅ Session management                                  │
│  ✅ Compute registry                                    │
│  ✅ Task routing                                        │
│  ✅ Storage API                                         │
│  ✅ React UI                                            │
│                                                          │
│  NEW (v0.2.0):                                          │
│  ❌ ProcessMapService (storage only)                    │
│  ❌ FacilitationService (conversation management)       │
│  ❌ CoordinatingTeamService (route to agents)           │
│  ❌ EventBus (coordinate agents)                        │
│  ❌ Process map APIs                                    │
│  ❌ Process map UI components                           │
│                                                          │
│  KEY: Routes messages, stores data - NO agent execution │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  COMPUTE (Port 8003+) - AGENT DEFINITIONS ADDED         │
│                                                          │
│  EXISTING (v0.1.8):                                     │
│  ✅ Agent executor                                      │
│  ✅ LLM integration                                     │
│  ✅ Specialized agents (4)                              │
│  ✅ Registration                                        │
│                                                          │
│  NEW (v0.2.0):                                          │
│  ❌ 6 coordinating agent JSON definitions               │
│     • process-mapper-agent.json                         │
│     • agent-selector-agent.json                         │
│     • activity-facilitator-agent.json                   │
│     • consistency-manager-agent.json                    │
│     • progress-reporter-agent.json                      │
│     • result-synthesizer-agent.json                     │
│                                                          │
│  KEY: ALL agents execute here (coordinating + specialized) │
└─────────────────────────────────────────────────────────┘
```

### Critical Insight: Compute Executes, Serving Routes

```
                Serving (Broker)
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
   Compute-1     Compute-2     Compute-3
   Process       Activity      Specialized
   Mapper        Facilitator   Agents
```

**All agents are JSON definitions that execute via existing agent executor.**

---

## What We're Reusing vs Building

### Reusing (80%)

| Component | What We Have | How We Use It |
|-----------|--------------|---------------|
| **Marketplace** | Agent catalog, search | Agent Selector queries it |
| **Serving - Sessions** | Session CRUD, storage | Extend for facilitated mode |
| **Serving - Registry** | Compute instance tracking | Agent Selector checks availability |
| **Serving - Task Router** | Route tasks to compute | Activity Facilitator uses it |
| **Serving - Storage** | Storage API | Store process maps |
| **Serving - UI** | React dashboard | Extend with new components |
| **Compute - Executor** | Agent execution engine | Execute coordinating agents |
| **Compute - LLM** | OpenAI/Anthropic/Mock | Coordinating agents use same |

### Building New (20%)

| Component | What's New | Why |
|-----------|------------|-----|
| **Serving - Models** | ProcessMap, Activity, Exchange | Represent facilitated process |
| **Serving - ProcessMapService** | Storage & versioning | Track evolving maps |
| **Serving - FacilitationService** | Conversation loops | Facilitate activities |
| **Serving - EventBus** | Event routing | Coordinate agents |
| **Serving - APIs** | Process map endpoints | Expose features |
| **Serving - UI** | Process map viewer, conversation viewer | Visualize facilitation |
| **Compute - Agents** | 6 coordinating agent definitions | Define coordinating agents |

---

## Phase Breakdown - What You'll Build

### Phase 1: Foundation (Week 1)

**Goal:** Data layer for process maps

**Build:**
```
serving/models/process_map.py
serving/services/process_map_service.py
serving/api/process_maps.py
serving/frontend/src/components/ProcessMapViewer.jsx
```

**Test via UI:**
1. Create process map via API
2. Open UI at http://localhost:8002
3. View process map as graph
4. See activities with status colors
5. See dependencies as arrows

**Success:** Process map visible in UI

---

### Phase 2: Process Mapper (Week 2)

**Goal:** First coordinating agent - creates initial maps

**Build:**
```
compute/data/compute/agents/coordinating/process-mapper-agent.json
serving/services/coordinating_team_service.py
serving/api/sessions.py (extend with create-facilitated)
serving/frontend/src/components/CreateSessionModal.jsx (extend)
```

**Test via UI:**
1. Click "Create New Session"
2. Enter: "Increase customer retention by 20%"
3. Select: "Facilitated Process (v0.2.0)"
4. See Process Mapper generate 3-5 activities
5. View process map with proposed activities

**Success:** Business goal → Initial process map works

---

### Phase 3: Agent Selector (Week 3)

**Goal:** Match agents to activities

**Build:**
```
compute/data/compute/agents/coordinating/agent-selector-agent.json
serving/services/coordinating_team_service.py (extend)
serving/api/process_maps.py (extend)
serving/frontend/src/components/ActivityParticipants.jsx
```

**Test via UI:**
1. Click activity in process map
2. Click "Select Participants"
3. See Agent Selector analysis
4. See marketplace search results
5. See recommendations with reasoning
6. Click "Assign Participants"

**Success:** Activity → Participant recommendations works

---

### Phase 4: Activity Facilitator (Weeks 4-5)

**Goal:** Guide activity conversations

**Build:**
```
compute/data/compute/agents/coordinating/activity-facilitator-agent.json
serving/models/process_map.py (extend with Exchange)
serving/services/facilitation_service.py
serving/api/process_maps.py (extend)
serving/frontend/src/components/ActivityConversation.jsx
```

**Test via UI:**
1. Select activity with participants
2. Click "Start Facilitation"
3. Watch conversation thread:
   - Facilitator: Blue messages
   - Agent: Green responses
4. See status: proposed → in_progress
5. See blocker identified
6. Status: in_progress → blocked

**Success:** Watch facilitation conversations in real-time

---

### Phase 5: Support Agents (Week 6)

**Goal:** Add remaining coordinating agents

**Build:**
```
compute/data/compute/agents/coordinating/consistency-manager-agent.json
compute/data/compute/agents/coordinating/progress-reporter-agent.json
compute/data/compute/agents/coordinating/result-synthesizer-agent.json
serving/services/... (extend)
serving/api/... (extend)
serving/frontend/src/components/... (new)
```

**Test via UI:**
1. Complete multiple activities
2. See Progress Reporter update metrics
3. See Consistency Manager flag issues
4. Click "Generate Results"
5. See Result Synthesizer create deliverable

**Success:** All 6 coordinating agents working

---

### Phase 6: Integration (Week 7)

**Goal:** Complete end-to-end flow

**Build:**
```
serving/services/event_bus.py
serving/api/... (complete integration)
serving/frontend/src/components/FacilitatedSessionDashboard.jsx
```

**Test via UI:**
1. Create facilitated session
2. Watch Process Mapper create activities
3. Assign participants
4. Start facilitation
5. See blocker → Process Mapper creates new activity
6. Complete Activity 0 → Activity 1 unblocks
7. Continue until all activities complete
8. Watch process map evolve (v1 → v2 → v3)
9. See Consistency Manager flag issue
10. See Result Synthesizer create deliverable

**Success:** Complete end-to-end facilitated session

---

## Dual-Mode Support

Both v0.1.8 (pipeline) and v0.2.0 (facilitated) will work:

### When to Use Each

**Traditional Pipeline (v0.1.8):**
- ✅ Well-defined workflows
- ✅ Clear steps upfront
- ✅ Speed/cost priorities
- ✅ Repeated processes

**Examples:** Data ETL, report generation, API integrations

**Facilitated Process (v0.2.0):**
- ✅ Ambiguous problems
- ✅ Requirements emerge during work
- ✅ Quality is paramount
- ✅ Complex problem-solving

**Examples:** Strategic planning, research, exploratory analysis

---

## Development Workflow

### Per Phase

```bash
# 1. Create feature branch
git checkout -b feature/facilitated-process-phase1

# 2. Implement
# - Models
# - Services
# - APIs
# - UI components

# 3. Test via UI
./start_all.sh
# Open http://localhost:8002
# Test new features visually

# 4. Commit
git add .
git commit -m "Phase 1: ProcessMap foundation"

# 5. Move to next phase
git checkout -b feature/facilitated-process-phase2
```

### Testing Commands

```bash
# Start all services
./start_all.sh

# Check status
./status.sh

# View logs
tail -f logs/serving.log
tail -f logs/compute.log

# Access UI
open http://localhost:8002  # Serving UI
open http://localhost:8001  # Marketplace UI

# Stop services
./stop_all.sh
```

---

## Documentation

### Core Docs (Read These)

1. **FACILITATED_PROCESS_ARCHITECTURE.md** (2145 lines)
   - Complete architectural vision
   - All 6 coordinating agents explained
   - Data models defined
   - Flow examples

2. **FACILITATED_PROCESS_IMPLEMENTATION_PLAN.md** (this doc)
   - Phase-by-phase implementation
   - Code snippets for each phase
   - Testing instructions
   - Success criteria

3. **FACILITATED_PROCESS_QUICK_START.md**
   - Quick reference
   - Testing commands
   - Phase summaries
   - Key files to know

4. **FACILITATED_PROCESS_INTEGRATION.md**
   - How it integrates with existing components
   - Reuse vs new breakdown
   - Complete data flow examples

5. **FACILITATED_PROCESS_SUMMARY.md**
   - Executive summary
   - Key concepts
   - Design principles
   - Benefits

### Location

```
docs/
├── design/architecture/
│   ├── EXECUTION_PIPELINE_ARCHITECTURE.md  (Full spec)
│   ├── FACILITATED_PROCESS_INTEGRATION.md  (Integration)
│   └── FACILITATED_PROCESS_SUMMARY.md      (Summary)
│
└── development/
    ├── FACILITATED_PROCESS_IMPLEMENTATION_PLAN.md  (This doc)
    └── FACILITATED_PROCESS_QUICK_START.md          (Quick ref)
```

---

## Questions to Resolve Before Starting

### 1. LLM Provider
- [ ] OpenAI GPT-4 for production?
- [ ] Mock provider for development/testing?
- [ ] Budget for LLM API calls during development?

### 2. Real-time UI Updates
- [ ] Polling for now, SSE later?
- [ ] Or SSE from start?

### 3. Storage Backend
- [ ] Extend current filesystem storage?
- [ ] Add PostgreSQL for structured queries?
- [ ] Keep it simple for now?

### 4. Graph Visualization Library
- [ ] React Flow (popular)?
- [ ] D3.js (custom)?
- [ ] Cytoscape.js (graph-focused)?

### 5. Development Approach
- [ ] Build all 6 phases sequentially?
- [ ] Prioritize certain coordinating agents?
- [ ] Parallel development possible?

---

## Success Criteria

### Phase Completion
- [ ] Phase 1: Can view process map in UI
- [ ] Phase 2: Business goal → Initial map works
- [ ] Phase 3: Activity → Participants works
- [ ] Phase 4: Can watch facilitation conversations
- [ ] Phase 5: All 6 coordinating agents work
- [ ] Phase 6: Complete end-to-end flow works

### Overall Success
- [ ] Can demo facilitated session via UI
- [ ] Process maps evolve based on facilitation
- [ ] Activities are goal-oriented (not steps)
- [ ] Coordinating agents coordinate via events
- [ ] Both pipeline and facilitated modes work
- [ ] Documentation complete and up-to-date

---

## Timeline

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1 | Foundation | Process map viewer |
| 2 | Process Mapper | Initial map creation |
| 3 | Agent Selector | Participant selection |
| 4-5 | Activity Facilitator | Conversation management |
| 6 | Support Agents | All coordinating agents |
| 7 | Integration | Complete end-to-end flow |

**Total: 6-7 weeks to v0.2.0 release**

---

## Next Steps

### Immediate Actions

1. **Review Documentation**
   - [ ] Read FACILITATED_PROCESS_ARCHITECTURE.md
   - [ ] Review FACILITATED_PROCESS_QUICK_START.md
   - [ ] Understand architecture diagrams

2. **Resolve Questions**
   - [ ] Decide on LLM provider
   - [ ] Choose graph visualization library
   - [ ] Decide on storage approach

3. **Set Up Branch**
   ```bash
   git checkout -b feature/facilitated-process-phase1
   ```

4. **Start Phase 1**
   - [ ] Create ProcessMap models
   - [ ] Build ProcessMapService
   - [ ] Add API endpoints
   - [ ] Build UI component
   - [ ] Test via UI

5. **Iterate**
   - [ ] Complete Phase 1
   - [ ] Demo progress
   - [ ] Move to Phase 2
   - [ ] Repeat

---

## Getting Help

**Questions?** Refer to:
- Architecture: `FACILITATED_PROCESS_ARCHITECTURE.md`
- Integration: `FACILITATED_PROCESS_INTEGRATION.md`
- Quick Start: `FACILITATED_PROCESS_QUICK_START.md`
- Summary: `FACILITATED_PROCESS_SUMMARY.md`

**Code Examples:**
- Existing pipeline: `serving/models/pipeline.py`
- Agent executor: `compute/services/agent_executor.py`
- UI components: `serving/frontend/src/components/`

---

## Let's Build! 🚀

This is a significant evolution of ClaudeVN - from predetermined workflows to emergent, goal-oriented processes.

**The journey of 1000 lines of code begins with a single model...**

Ready to start Phase 1?

