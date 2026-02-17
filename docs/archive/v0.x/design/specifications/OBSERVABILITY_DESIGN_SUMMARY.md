# Process Map Observability - Design Summary

**Date**: November 25, 2025  
**Status**: Design Proposal  
**Related**: [Full Observability Design](PROCESS_MAP_OBSERVABILITY.md)

## Executive Summary

This document summarizes the key design decisions for implementing comprehensive observability of running facilitated processes in ClaudeVN. The design addresses the unique challenges of monitoring **emergent, distributed workflows** where:

- Multiple sessions run concurrently
- Process maps evolve dynamically (reevaluations)
- Activities are facilitated across distributed compute resources
- Single process maps can have 10-100+ activities
- Conversations (exchanges) provide rich context but create data volume

---

## Core Design Principles

### 1. Progressive Disclosure Over Information Overload

**Decision**: Multi-level hierarchy with drill-down navigation.

**Rationale**: A process map with 100 activities cannot be displayed all at once. Users need:
- **System overview** → See all sessions at a glance
- **Session detail** → Focus on one process map
- **Activity detail** → Examine one conversation
- **Exchange detail** → Review specific interactions

**Implementation**: 
- Collapsible/expandable UI elements
- Modal dialogs for deep dives
- Breadcrumb navigation to maintain context

### 2. Real-Time Awareness Without Overwhelming Backend

**Decision**: Polling-based updates (3-5 second intervals) with caching.

**Rationale**: 
- WebSocket adds complexity (future enhancement)
- Facilitated processes operate on human timescales (minutes to hours)
- 5-second updates are "real-time enough" for observability
- Caching reduces database load

**Alternative Considered**: WebSocket push notifications
- **Pros**: Truly real-time, lower latency
- **Cons**: More complex infrastructure, connection management, testing overhead
- **Decision**: Defer to Phase 7+

### 3. Status-First, Detail-on-Demand

**Decision**: Show activity status prominently; hide conversation details until requested.

**Rationale**:
- Users typically want "what's the status?" not "what was said?"
- Conversation history is valuable for debugging but not continuous monitoring
- Status cards are scannable; full exchanges require reading

**Implementation**: Activity cards show status badges, duration, agent. Click for full conversation.

### 4. Resource Tracking as First-Class Concern

**Decision**: Explicitly track which compute instances and agents are involved per session.

**Rationale**:
- In distributed systems, "where is this running?" is critical
- Debugging requires knowing compute instance and agent assignments
- Resource contention (multiple sessions competing) is a operational concern
- Observability must answer: "Why is this session slow?" → Check compute utilization

**Implementation**: 
- Store `compute_instance_id` in Activity when facilitation starts
- Aggregate utilization in `ComputeUtilization` model
- Display resource panel in session detail view

---

## Key Design Decisions

### Decision 1: Hierarchical Activity Grouping

**For process maps with 30-100+ activities, use hierarchical collapse:**

```
▼ Phase 1: Data Collection (5 activities - 100% complete)
▼ Phase 2: Analysis (12 activities - 67% complete)
▶ Phase 3: Strategy Development (8 activities - 0%)
```

**Rationale**:
- **Cognitive Load**: Humans can track ~7±2 items; 100 activities exceed this
- **Emergence**: Hierarchies naturally emerge in complex process maps (parent/sub-activities)
- **Scanning**: Collapsed phases allow quick status assessment
- **Details Available**: Expand to see individual activities

**Implementation**:
- Detect parent/sub-activity relationships from ProcessMap model
- Auto-group activities by completion status or temporal phases
- Provide manual grouping controls (by agent, compute resource, etc.)

### Decision 2: Timeline View as Supplement to Workflow View

**Provide both workflow (graph) and timeline (chronological) views.**

**Rationale**:
- **Workflow view** answers: "What's the structure? What depends on what?"
- **Timeline view** answers: "What happened when? What's the sequence?"
- Different mental models for different questions
- Timeline is linear and scrollable (scales better for 100+ events)

**Implementation**:
- Tabs in Session Detail: [Overview] [Workflow] [Timeline] [Resources]
- Workflow view: Visual graph with status colors
- Timeline view: Chronological event stream with timestamps

### Decision 3: Activity-to-Compute Mapping

**Store compute instance ID directly in Activity model when facilitation starts.**

**Rationale**:
- **Observability**: Need to answer "where is Activity X running?"
- **Debugging**: If activity hangs, need to check that compute instance
- **Resource Allocation**: Know which activities are on which instances
- **Historical Analysis**: Track which compute resources handled which work

**Implementation**:
```python
class Activity(BaseModel):
    # ... existing fields ...
    
    # NEW: Track where this activity is executing
    compute_instance_id: Optional[str] = None  # Set when facilitation starts
    assigned_at: Optional[datetime] = None     # When assigned to compute
```

**Alternative Considered**: Query compute instance via agent assignment
- **Cons**: Requires joining through agent registry; agents can move between instances
- **Decision**: Direct reference is simpler and more reliable

### Decision 4: Exchange History Pagination

**Paginate exchanges when count > 50, but store all exchanges inline.**

**Rationale**:
- Most activities have < 50 exchanges (< 30 in practice)
- Storing exchanges in activity model (existing) is simple
- Pagination on retrieval (API level) handles outliers
- Keeps data model consistent (no separate exchange table)

**Implementation**:
- Store all exchanges in `activity.facilitation_exchanges` (existing)
- API endpoint returns first 20 exchanges by default
- "Load more" button fetches next 20
- Full history available for export

### Decision 5: SessionSummary for Dashboard Performance

**Create lightweight SessionSummary model separate from full ProcessMap.**

**Rationale**:
- **Performance**: Loading full ProcessMap for 50 sessions is expensive (100+ activities each)
- **Dashboard Needs**: Only need counts, status, resources (not full activity details)
- **Database Load**: Aggregated summaries can be cached longer

**Implementation**:
```python
class SessionSummary(BaseModel):
    session_id: str
    business_goal: str
    status: ProcessMapStatus
    total_activities: int
    completed_activities: int
    in_progress_activities: int
    # ... (lightweight fields only)
```

**API**:
- `GET /api/v1/observability/sessions` → List[SessionSummary]
- `GET /api/v1/sessions/{id}/map` → Full ProcessMap (existing)

---

## Challenges & Solutions

### Challenge 1: How to visualize 100+ activity process maps?

**Problem**: Can't show 100 activity cards in workflow view without overwhelming UI.

**Solutions Implemented**:

1. **Hierarchical Collapse** (Primary)
   - Group activities into phases (parent/child relationships)
   - Show phase summaries by default (e.g., "Phase 2: 12 activities - 67% complete")
   - Expand phase to see individual activities

2. **Filtering** (Secondary)
   - Filter by status: Show only "In Progress" or "Blocked"
   - Filter by compute resource: Show only activities on compute-001
   - Filter by agent: Show only activities using data-analyst-v1

3. **Search** (Tertiary)
   - Search by activity goal or description
   - Jump directly to matching activities

4. **Timeline Alternative**
   - Switch to Timeline view for chronological scrolling
   - Timeline scales better than graph for large counts

**Result**: Users can navigate large process maps without cognitive overload.

---

### Challenge 2: Tracking activities across distributed compute resources

**Problem**: Activities execute on different compute instances; need to know which instance is handling which activity in real-time.

**Solutions Implemented**:

1. **Activity Assignment Metadata**
   - Add `compute_instance_id` to Activity model
   - Set when Activity Facilitator starts facilitation
   - Persisted with process map

2. **Resource Utilization Aggregation**
   - Create `ComputeUtilization` model
   - API endpoint: `/api/v1/observability/sessions/{id}/compute-utilization`
   - Returns list of instances with active activities

3. **Resource Panel in UI**
   - Display all compute instances involved in session
   - Show which activities are running on each instance
   - Include heartbeat status (online/offline)

4. **Agent-to-Compute Mapping**
   - Agent Selector includes compute instance in assignment
   - ParticipantAssignment can optionally include instance_id
   - UI displays: "data-analyst-v1 (compute-001)"

**Result**: Full visibility into distributed execution.

---

### Challenge 3: Real-time updates without overloading backend

**Problem**: Need near-real-time status updates for multiple concurrent sessions without hammering database.

**Solutions Implemented**:

1. **Polling with Smart Intervals**
   - Active sessions: Poll every 3-5 seconds
   - Inactive/completed sessions: Poll every 30 seconds or on-demand
   - Frontend adjusts polling based on session status

2. **Caching Strategy**
   - Cache SessionSummary for 5 seconds (backend)
   - Cache ActivitySnapshot for 3 seconds (backend)
   - Use Last-Modified headers to avoid re-fetching unchanged data

3. **Incremental Updates** (Future)
   - API returns only changed activities since last fetch
   - "If-Modified-Since" header support
   - Reduces payload size

4. **WebSocket Alternative** (Phase 7+)
   - Implement WebSocket connections for true push updates
   - Reduces latency from 5 seconds to < 1 second
   - More complex but better UX

**Result**: Reasonable real-time feel (5s update) without backend overload.

---

### Challenge 4: Exchange history data volume

**Problem**: Long-running activities can have 100+ exchanges. Storing and retrieving efficiently without slowing down UI.

**Solutions Implemented**:

1. **Inline Storage** (Existing)
   - Exchanges stored in `activity.facilitation_exchanges` list
   - ProcessMap service saves entire map (including exchanges)
   - Simple, works for < 1000 exchanges per activity

2. **Pagination on Retrieval**
   - API endpoint: `GET /api/v1/process-maps/.../activities/{id}/exchanges?offset=0&limit=20`
   - UI shows first 20 exchanges by default
   - "Load more" button fetches next batch
   - Full history available but not loaded upfront

3. **Lazy Loading**
   - Activity Detail Modal fetches exchanges only when opened
   - Not fetched for activity cards in workflow view
   - Reduces data transfer for inactive activities

4. **Compression** (Future)
   - Compress exchange history for completed activities
   - Decompress on-demand when viewing
   - Reduces storage footprint

**Result**: Exchange history doesn't impact dashboard/workflow view performance.

---

### Challenge 5: Distinguishing coordinating agents from specialist agents

**Problem**: Coordinating agents (Process Mapper, Consistency Manager, etc.) run continuously but aren't tied to specific activities. How to display them in observability?

**Solutions Implemented**:

1. **Agent Role Classification**
   - Specialist agents: Assigned to specific activities (Activity.assigned_agents)
   - Coordinating agents: Listed separately in Resource Utilization Panel

2. **Coordinating Agents Display**
   ```
   🤖 Agent Activity Summary
   ├─ data-analyst-v1        │ 🔵 Active   │ Activity 2a
   ├─ customer-insights-v2   │ 🔵 Active   │ Activity 2b
   ├─ consistency-manager-v1 │ 👁️ Monitor  │ All activities
   └─ progress-reporter-v1   │ 👁️ Monitor  │ All activities
   ```

3. **Compute Instance Tracking**
   - Coordinating agents tracked as separate category
   - Show which compute instance runs coordinating team
   - Display coordinating agent events in Timeline view

**Result**: Clear distinction between specialist and coordinating agents.

---

## Conflicts & Trade-offs

### Conflict 1: Real-Time vs. Scalability

**Trade-off**: Polling (5s updates) vs. WebSocket (instant updates)

**Decision**: Start with polling, add WebSocket later.

**Rationale**:
- Facilitated processes operate on minute/hour timescales (not milliseconds)
- 5-second updates are sufficient for human monitoring
- Polling is simpler to implement and test
- WebSocket adds infrastructure complexity (connection management, reconnection, scaling)

**Future Path**: Add WebSocket in Phase 7+ when usage patterns are understood.

---

### Conflict 2: Workflow Graph vs. Timeline List

**Trade-off**: Graph visualization (shows dependencies) vs. List/Timeline (shows chronology)

**Decision**: Provide both views via tabs.

**Rationale**:
- Graph is better for understanding structure ("what depends on what?")
- Timeline is better for understanding sequence ("what happened when?")
- Different users prefer different views
- Timeline scales better for 100+ activities

**Implementation Cost**: ~2x frontend development but better UX.

---

### Conflict 3: Full ProcessMap vs. Lightweight Summary

**Trade-off**: Always load full ProcessMap (simple) vs. Create SessionSummary model (efficient)

**Decision**: Create SessionSummary for dashboard; full ProcessMap for session detail.

**Rationale**:
- Dashboard shows 10-50 sessions → Loading full maps is expensive
- Session detail shows 1 session → Full map is acceptable
- SessionSummary can be cached longer (less volatile)

**Complexity**: Introduces second model but significantly improves performance.

---

### Conflict 4: Auto-Grouping vs. Manual Grouping

**Trade-off**: Automatically group activities into phases vs. let user define groups

**Decision**: Auto-group by parent/sub-activity relationships; allow manual filters.

**Rationale**:
- Parent/sub-activity relationships are semantic (from process map)
- Auto-grouping provides instant value with no user effort
- Manual filters (by agent, compute, status) allow custom views
- Don't force users to define groups (cognitive overhead)

**Future Enhancement**: Allow users to save custom groupings.

---

## Design Validation

### Does this design meet requirements?

✅ **Workflow-style view of process map**: Yes - Workflow tab with graph visualization  
✅ **Handle many activities efficiently**: Yes - Hierarchical collapse + filtering  
✅ **See compute resources per session**: Yes - Resource Utilization Panel  
✅ **See active agents**: Yes - Agent Activity Summary table  
✅ **See completed activities**: Yes - Activity status tracking with filtering  
✅ **Eventually see outputs**: Yes - Outputs tab in Activity Detail Modal (Phase 6+)  

### Does this design scale?

✅ **50 concurrent sessions**: Yes - SessionSummary model, caching, pagination  
✅ **100+ activities per session**: Yes - Hierarchical collapse, filtering, search  
✅ **1000+ exchanges**: Yes - Pagination on retrieval, lazy loading  
✅ **20+ compute instances**: Yes - Resource Utilization aggregation  

### Does this design handle distributed execution?

✅ **Activity-to-compute mapping**: Yes - Store compute_instance_id in Activity  
✅ **Agent-to-compute mapping**: Yes - Track via compute instance registration  
✅ **Resource contention visibility**: Yes - Utilization panel shows active work per instance  

### Does this design support emergent workflows?

✅ **Reevaluation visibility**: Yes - Timeline view shows reevaluation events  
✅ **Blocker tracking**: Yes - Blocked activities highlighted, blockers shown  
✅ **Dynamic dependencies**: Yes - Workflow graph updates as dependencies change  
✅ **Conversation context**: Yes - Full exchange history available  

---

## Integration with Existing Architecture

### Compatibility with v0.2.0 Facilitated Process Architecture

**Existing Components Used**:
- `ProcessMap` model (serving/models/process_map.py) - Stores all state
- `Activity` model - Contains exchanges, status, assignments
- `ComputeInstance` model (serving/models/compute.py) - Tracks instances
- Process Map Service (serving/services/process_map_service.py) - Storage layer
- Coordinating Team Service - Event bus for coordinating agents

**New Components Added**:
- `ObservabilityService` - Aggregates data for observability APIs
- `SessionSummary`, `ActivitySnapshot`, `ComputeUtilization` models
- New API endpoints under `/api/v1/observability/`
- Frontend components: Multi-Session Dashboard, Activity Detail Modal, Resource Panel

**Integration Points**:
- Serving component stores process maps (existing) - Observability reads from same storage
- Compute instances register with Serving (existing) - Observability tracks registrations
- Activity status updates (existing) - Observability reflects changes in real-time
- Event bus (existing) - Observability can subscribe to coordinating events

**No Breaking Changes**: All new functionality; existing APIs and models unchanged.

---

## Implementation Roadmap

**Total Estimated Time**: 6 weeks (1 developer)

### Phase 1: Foundation (Week 1)
- Create observability data models
- Implement backend service (ObservabilityService)
- Build basic API endpoints
- Add compute_instance_id to Activity model

### Phase 2: Multi-Session Dashboard (Week 2)
- Build dashboard UI component
- Implement session filtering/sorting
- Add polling for real-time updates
- Create session summary cards

### Phase 3: Enhanced Session Detail (Week 3)
- Upgrade ProcessMapViewer with tabs
- Implement workflow visualization
- Add hierarchical collapse
- Build Activity Detail Modal

### Phase 4: Resource Tracking (Week 4)
- Build Resource Utilization Panel
- Implement agent status tracking
- Add utilization charts
- Create compute instance details

### Phase 5: Timeline & Events (Week 5)
- Build Timeline View component
- Implement event stream aggregation
- Add event filtering
- Create event detail panels

### Phase 6: Optimization (Week 6)
- Implement caching strategies
- Add pagination where needed
- Optimize database queries
- Performance testing with large process maps

### Phase 7+: Future Enhancements
- WebSocket real-time updates
- Advanced visualizations (Gantt, network graphs)
- Outputs & results viewer
- Alerting & notifications
- Historical analytics
- Export & reporting

---

## Risks & Mitigations

### Risk 1: Database Performance with Many Sessions

**Risk**: Querying process maps for 50 sessions might be slow.

**Mitigation**:
- Implement SessionSummary lightweight model
- Cache summaries for 5-10 seconds
- Database indexes on session_id, status, updated_at
- Pagination on session list (show 20 at a time)

### Risk 2: Complex Workflow Visualizations

**Risk**: Graph layout for 100+ activities is computationally expensive.

**Mitigation**:
- Use hierarchical collapse (render 5-10 phase groups instead of 100 activities)
- Lazy rendering (render visible viewport only)
- Consider using established graph libraries (dagre, vis.js) for layout
- Fallback to Timeline view for very large maps

### Risk 3: Real-Time Updates May Miss Fast Changes

**Risk**: 5-second polling might miss rapid activity transitions.

**Mitigation**:
- This is acceptable for facilitated processes (activities take minutes/hours)
- If needed, reduce polling interval to 2-3 seconds for active sessions
- Future: Add WebSocket for instant updates
- Backend ensures atomic state changes (no race conditions)

### Risk 4: Exchange History Data Volume

**Risk**: 1000+ exchanges per activity could bloat storage and slow retrieval.

**Mitigation**:
- Pagination on API (return 20 exchanges at a time)
- Lazy loading in UI (only fetch when user opens activity detail)
- Future: Compress exchanges for completed activities
- Future: Archive old session data to cold storage

---

## Open Questions

### Question 1: Should we auto-refresh or require manual refresh?

**Options**:
- Auto-refresh every 5 seconds (recommended)
- Manual refresh button only
- Auto-refresh with pause/resume controls

**Recommendation**: Auto-refresh with pause button. Users monitoring active sessions want continuous updates; users reviewing completed sessions can pause.

### Question 2: Should we show coordinating agent events in Timeline?

**Options**:
- Show all coordinating events (consistency checks, progress reports, synthesis)
- Show only major coordinating events (reevaluations, blockers identified)
- Hide coordinating events by default, show via filter

**Recommendation**: Show major events by default, hide minor events (e.g., routine consistency checks). Provide filter to show all.

### Question 3: How to handle very long-running sessions (days/weeks)?

**Options**:
- Timeline view becomes very long
- Compress time axis (skip idle periods)
- Paginate timeline by time window (1 day chunks)

**Recommendation**: Start with simple scrolling timeline. Add time compression in Phase 6 if needed.

### Question 4: Should we track estimated completion time?

**Options**:
- Show "Estimated completion: 2h 15m" based on progress
- Don't estimate (facilitated processes are unpredictable)

**Recommendation**: Don't estimate. Facilitated processes are inherently emergent and unpredictable. Show duration elapsed and progress percentage only.

---

## Success Metrics

After implementation, measure:

1. **Usability**:
   - Time to identify blocked sessions: < 10 seconds
   - Time to drill down to activity detail: < 3 clicks
   - User satisfaction score: > 4/5

2. **Performance**:
   - Dashboard load time (10 sessions): < 2 seconds
   - Workflow view render time (50 activities): < 3 seconds
   - Activity detail modal open time: < 1 second

3. **Adoption**:
   - % of sessions monitored via observability UI: > 80%
   - Feature usage: Multi-session dashboard, workflow view, timeline view
   - Support tickets related to "where is my session?": Decrease by > 50%

---

## Conclusion

This observability design provides comprehensive monitoring of facilitated processes while managing the complexity of distributed, emergent workflows. Key innovations:

1. **Progressive disclosure** - Multi-level hierarchy prevents information overload
2. **Hierarchical collapse** - Handles 100+ activity process maps elegantly
3. **Resource tracking** - Full visibility into distributed compute execution
4. **Dual visualization** - Workflow graph + Timeline for different mental models
5. **Performance-first** - Lightweight summaries, caching, pagination

The design is compatible with the existing v0.2.0 architecture and can be implemented incrementally without breaking changes. It addresses all requirements while remaining scalable and performant.

---

**Next Steps**:
1. ✅ Design review (this document)
2. ⏭️ Create UX mockups (Figma/Sketch)
3. ⏭️ Validate with user testing
4. ⏭️ Break into implementation tickets
5. ⏭️ Begin Phase 1 development

---

**Author**: AI Design Assistant  
**Date**: November 25, 2025  
**Version**: 1.0  
**Status**: Ready for Review

