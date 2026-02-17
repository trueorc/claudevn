# Emergent Workflow Quick Start

**Start Here**: 6-week plan to close the architectural gap

---

## The Problem in One Sentence

We built a great foundation for task routing and pipelines, but we're missing the **conversation-driven facilitation layer** that makes processes truly emergent.

---

## The Solution in One Sentence

Implement 4 coordinating agents (Activity Facilitator, Consistency Manager, Progress Reporter, Result Synthesizer) that enable conversation loops, blocker detection, and dynamic process evolution.

---

## Week-by-Week Checklist

### Week 1: Conversation Loop Foundation

**Goal**: Activity Facilitator can have multi-turn conversation with participant agent

#### Tasks
- [ ] Design conversation data models (`Exchange`, `FacilitationConversation`)
- [ ] Implement basic conversation loop in `ActivityFacilitator.facilitate_activity()`
- [ ] Add conversation persistence to process map
- [ ] Create test: Single activity facilitation with 3+ exchanges

**Files to Create/Modify**:
- `serving/models/facilitation.py` - NEW (conversation models)
- `compute/services/coordinating_team_service.py` - MODIFY ActivityFacilitator class
- `serving/services/process_map_service.py` - ADD record_facilitation()
- `tests/test_conversation_loop.py` - NEW

**Success Criteria**:
✅ Facilitator asks agent what it needs  
✅ Agent responds with requirements  
✅ Facilitator asks if agent has everything  
✅ Agent confirms or reports blocker  
✅ Conversation recorded to process map

---

### Week 2: Blocker Detection & Dynamic Activities

**Goal**: Blockers automatically create prerequisite activities

#### Tasks
- [ ] Implement blocker detection in `_detect_blocker()`
- [ ] Create `handle_blocker()` to generate new activities
- [ ] Add `insert_activity_before()` to process map service
- [ ] Add dependency tracking between activities
- [ ] Create test: Blocker creates new activity

**Files to Create/Modify**:
- `compute/services/coordinating_team_service.py` - ADD blocker detection
- `serving/services/process_map_service.py` - ADD insert_activity_before(), add_dependency()
- `serving/models/process_map.py` - ADD Blocker model
- `tests/test_blocker_creates_activity.py` - NEW

**Success Criteria**:
✅ Agent says "I need database access"  
✅ Facilitator detects blocker  
✅ New activity "Obtain database access" created  
✅ Original activity depends on new activity  
✅ Process map version incremented

---

### Week 3: Consistency Manager

**Goal**: Contradictions detected and reconciliation activities created

#### Tasks
- [ ] Create consistency manager agent definition JSON
- [ ] Implement `ConsistencyService.check_consistency()`
- [ ] Add automatic consistency check after each activity completes
- [ ] Implement contradiction handling (mark for revisit, create reconciliation)
- [ ] Create test: Contradiction detection

**Files to Create/Modify**:
- `compute/data/compute/agents/coordinating/consistency-manager-agent.json` - NEW
- `serving/services/consistency_service.py` - NEW
- `serving/services/coordinating_team_service.py` - ADD invoke_consistency_manager()
- `tests/test_consistency_detection.py` - NEW

**Success Criteria**:
✅ Activity A outputs "retention: 65%"  
✅ Activity B outputs "based on 70% retention"  
✅ Consistency Manager detects contradiction  
✅ Both activities marked "revisit"  
✅ Reconciliation activity created

---

### Week 4: Process Map Evolution

**Goal**: Process maps restructure based on triggers

#### Tasks
- [ ] Implement `reevaluate_process_map()` in coordinating team service
- [ ] Add reevaluation triggers (blocker, contradiction, insight)
- [ ] Implement activity splitting logic
- [ ] Implement dependency reordering
- [ ] Create test: Map evolution

**Files to Create/Modify**:
- `serving/services/coordinating_team_service.py` - ADD reevaluate_process_map()
- `serving/services/process_map_service.py` - ADD split_activity(), reorder_activities()
- `tests/test_map_evolution.py` - NEW

**Success Criteria**:
✅ Blocker triggers reevaluation  
✅ Process Mapper recommends restructuring  
✅ Activities reordered or split  
✅ Map version history shows evolution  
✅ All activities still have valid dependencies

---

### Week 5: Result Synthesizer

**Goal**: System knows when business goal achieved

#### Tasks
- [ ] Create result synthesizer agent definition JSON
- [ ] Implement `synthesize_results()` service
- [ ] Add synthesis invocation after all activities complete
- [ ] Implement gap detection (what's still needed?)
- [ ] Create test: Goal achievement

**Files to Create/Modify**:
- `compute/data/compute/agents/coordinating/result-synthesizer-agent.json` - NEW
- `serving/services/synthesis_service.py` - NEW
- `serving/services/coordinating_team_service.py` - ADD invoke_result_synthesizer()
- `tests/test_result_synthesis.py` - NEW

**Success Criteria**:
✅ All activities marked "goal_met"  
✅ Result Synthesizer collects outputs  
✅ Coherent final deliverable generated  
✅ Goal achievement assessed  
✅ Session marked "completed" if goal met

---

### Week 6: Integration & E2E Testing

**Goal**: Complete emergent workflow works end-to-end

#### Tasks
- [ ] Create complete E2E test (goal → blocker → contradiction → synthesis)
- [ ] Build frontend session creation UI
- [ ] Add facilitation viewer to frontend
- [ ] Integrate WebSocket for real-time updates
- [ ] Test with multiple compute instances
- [ ] Performance testing (10+ activities)

**Files to Create/Modify**:
- `tests/test_complete_emergent_workflow.py` - NEW (the holy grail test)
- `serving/frontend/src/components/SessionCreator.jsx` - NEW
- `serving/frontend/src/components/FacilitationViewer.jsx` - NEW
- `serving/frontend/src/components/ProcessMapEvolution.jsx` - ENHANCE
- `tests/test_multi_compute_emergent.py` - NEW

**Success Criteria**:
✅ User submits business goal  
✅ Initial process map created (3 activities)  
✅ Facilitation detects blocker → new activity  
✅ Activities complete with different outputs  
✅ Contradiction detected → reconciliation  
✅ Final synthesis generated  
✅ Goal achieved, session complete  
✅ Map evolved from v1 to v4+  
✅ UI shows real-time updates throughout

---

## Daily Workflow

### Morning
1. Pull latest code
2. Check which week/task you're on
3. Review relevant files in checklist
4. Run existing tests to ensure baseline works

### During Development
1. Implement one checkbox at a time
2. Write test immediately after implementation
3. Run test until it passes
4. Commit with clear message referencing checkbox

### End of Day
1. Run full test suite
2. Update checklist (mark completed items)
3. Commit progress
4. Note any blockers for tomorrow

---

## Testing Strategy

### Unit Tests
Test each component in isolation:
- Conversation loop logic
- Blocker detection
- Consistency checking
- Synthesis logic

### Integration Tests
Test components working together:
- Facilitator + Process Map Service
- Consistency Manager + Process Map Service
- All coordinating agents + Serving

### E2E Tests
Test complete workflows:
- Week 1: Single activity facilitation
- Week 2: Blocker creates activity
- Week 3: Contradiction triggers reconciliation
- Week 4: Map evolution from trigger
- Week 5: Goal achievement
- Week 6: Complete emergent workflow

### Manual Testing
Use UI to visually verify:
- Real-time updates showing
- Conversations displaying
- Map evolution animating
- Final results presenting

---

## Success Metrics

Track these weekly to measure progress toward emergent behavior:

### Week 1
- **Conversations**: Avg exchanges per activity > 2
- **Tests Passing**: Conversation loop test passes

### Week 2
- **Emergence**: % of sessions creating new activities > 50%
- **Tests Passing**: Blocker detection test passes

### Week 3
- **Self-Correction**: Contradictions detected and handled
- **Tests Passing**: Consistency detection test passes

### Week 4
- **Evolution**: Map versions per session > 2
- **Tests Passing**: Map evolution test passes

### Week 5
- **Completion**: Sessions reaching goal achievement
- **Tests Passing**: Synthesis test passes

### Week 6
- **Integration**: Complete E2E test passes
- **Frontend**: Can create and monitor session via UI
- **Performance**: 10 activity session completes in < 5 min

---

## Key Files Reference

### Models
```
serving/models/
  process_map.py         - Activity, ProcessMap, Participant
  facilitation.py        - Exchange, FacilitationConversation (NEW)
  session.py             - SessionContext, SessionStatus
```

### Services
```
serving/services/
  coordinating_team_service.py  - Process Mapper, Agent Selector, invocation logic
  process_map_service.py        - Process map CRUD, versioning
  consistency_service.py        - Contradiction detection (NEW)
  synthesis_service.py          - Result synthesis (NEW)
```

### Coordinating Agents
```
compute/services/
  coordinating_team_service.py  - ActivityFacilitator, ProcessMapper (local)

compute/data/compute/agents/coordinating/
  process-mapper-agent.json           ✅ EXISTS
  agent-selector-agent.json           ✅ EXISTS
  activity-facilitator-agent.json     🔨 UPDATE
  consistency-manager-agent.json      ❌ CREATE
  progress-reporter-agent.json        ❌ CREATE
  result-synthesizer-agent.json       ❌ CREATE
```

### API Endpoints
```
serving/api/
  process_maps.py       - Process map CRUD, activity management
  facilitated_sessions.py - Session management
  observability.py      - WebSocket events
```

### Tests
```
tests/
  test_conversation_loop.py          - Week 1
  test_blocker_creates_activity.py   - Week 2
  test_consistency_detection.py      - Week 3
  test_map_evolution.py              - Week 4
  test_result_synthesis.py           - Week 5
  test_complete_emergent_workflow.py - Week 6
```

---

## Common Pitfalls to Avoid

### ❌ Don't
- Implement all 6 coordinating agents at once (too complex)
- Skip tests (you'll regret it later)
- Change multiple files without running tests
- Assume LLM will handle everything (guide it with clear prompts)
- Make process map changes without incrementing version

### ✅ Do
- Focus on one week at a time
- Write tests before implementation when possible
- Run tests frequently (after every file change)
- Use mock LLM provider for faster testing
- Commit small, working increments
- Update observability events so you can see what's happening

---

## When You Get Stuck

### Technical Issues
1. Check existing working code (Process Mapper, Agent Selector)
2. Review test examples in `tests/`
3. Read implementation plan: `docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md`
4. Look at architecture docs: `docs/design/architecture/`

### Conceptual Confusion
1. Read: `docs/design/architecture/FACILITATED_PROCESS_SUMMARY.md`
2. Review: "What Emergent Actually Means" section in implementation plan
3. Study: Test scenarios to understand expected behavior

### Coordination Questions
1. Which agent does what? See "Coordinating Team" section in docs
2. How do agents communicate? See "Integration Points" section
3. What's the data flow? See architecture diagrams

---

## Quick Command Reference

```bash
# Start development environment
./start_all.sh

# Run specific test
python -m pytest tests/test_conversation_loop.py -v

# Run all tests
python -m pytest tests/ -v

# Check service status
./status.sh

# View logs
tail -f logs/serving.log
tail -f logs/compute.log

# Test with mock LLM (fast, free)
MOCK_LLM=true python -m pytest tests/

# Clean restart
./stop_all.sh && ./start_all.sh

# Monitor real-time events
# Open http://localhost:8002 → Observability tab
```

---

## Progress Tracking

Update this weekly:

- [ ] Week 1: Conversation Loop - Target: Dec 18, 2025
- [ ] Week 2: Blocker Detection - Target: Dec 25, 2025
- [ ] Week 3: Consistency Manager - Target: Jan 1, 2026
- [ ] Week 4: Process Map Evolution - Target: Jan 8, 2026
- [ ] Week 5: Result Synthesizer - Target: Jan 15, 2026
- [ ] Week 6: Integration & Testing - Target: Jan 22, 2026

**Completion Date**: Jan 22, 2026 (6 weeks from Dec 11, 2025)

---

## The North Star

**Remember the goal**: Users provide a business objective, and the system figures out how to achieve it through emergent collaboration—not predetermined steps.

**We're building toward**:
- Conversations, not commands
- Emergence, not predetermination
- Adaptation, not rigid execution
- Goal achievement, not step completion

**We'll know we've succeeded when**:
- Process maps evolve during execution (not static)
- New activities emerge from blockers (not planned upfront)
- Contradictions self-correct (not ignored)
- Business goals drive work (not prescribed workflows)

Let's build it! 🚀
