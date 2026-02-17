# Process Map Observability - Quick Reference

**Related Documents**:
- [Full Design Specification](PROCESS_MAP_OBSERVABILITY.md) - Complete technical design
- [Design Summary & Rationale](OBSERVABILITY_DESIGN_SUMMARY.md) - Key decisions and trade-offs

---

## At a Glance

### What We're Building

A comprehensive observability system for monitoring running facilitated processes across distributed compute resources.

### Key Features

1. **Multi-Session Dashboard** - See all active sessions at once
2. **Session Detail View** - Deep dive into one process map
3. **Activity Detail Modal** - Examine conversation history
4. **Resource Tracking Panel** - Monitor compute and agent utilization
5. **Timeline View** - Chronological event stream

---

## Design Philosophy

### Progressive Disclosure
Don't show everything at once. Provide **overview → detail** drill-down paths.

```
System Dashboard (all sessions)
  ↓ Click session
Session Detail (process map overview)
  ↓ Click activity
Activity Detail (conversation + outputs)
  ↓ Click exchange
Exchange Detail (full message)
```

### Key Innovation: Hierarchical Collapse

For process maps with 100+ activities, **group into phases**:

```
▼ Phase 1: Data Collection (5 activities - 100% complete)
▼ Phase 2: Analysis (12 activities - 67% complete)
  ├─ 🟢 Activity 2, 3, 4, 5, 6, 7, 8, 9 (completed)
  ├─ 🔵 Activity 10, 11, 12 (in progress)
  └─ 🟡 Activity 13 (proposed)
▶ Phase 3: Strategy (8 activities - 0%)
```

This allows users to scan large process maps without cognitive overload.

---

## Architecture

### Data Flow

```
Compute Instances → Serving (Storage) → Frontend (Visualization)
     ↓                   ↓                     ↓
 Execute Agents    Process Map         Real-time UI
 on Activities     Service Stores       (Polls every 5s)
                   State Changes
```

### New Components

**Backend**:
- `ObservabilityService` - Aggregates data for APIs
- `SessionSummary` - Lightweight session overview
- `ActivitySnapshot` - Real-time activity state
- `ComputeUtilization` - Resource usage tracking
- New API endpoints: `/api/v1/observability/*`

**Frontend**:
- Multi-Session Dashboard (system overview)
- Enhanced ProcessMapViewer (session detail)
- Activity Detail Modal (drill-down)
- Resource Utilization Panel (compute tracking)
- Timeline View (chronological events)

---

## Key Design Decisions

### 1. Polling vs. WebSocket

**Decision**: Start with polling (3-5 second intervals).

**Why**: 
- Facilitated processes operate on human timescales (minutes to hours)
- 5-second updates are "real-time enough"
- Simpler to implement and test
- WebSocket deferred to Phase 7+ (future enhancement)

---

### 2. Activity-to-Compute Mapping

**Decision**: Store `compute_instance_id` directly in Activity model.

**Why**:
- Need to answer "where is this activity running?"
- Critical for debugging hung activities
- Enables resource utilization tracking
- Historical analysis of compute usage

**Implementation**:
```python
class Activity(BaseModel):
    # ... existing fields ...
    compute_instance_id: Optional[str] = None  # NEW
```

---

### 3. Hierarchical Grouping for Large Process Maps

**Decision**: Auto-group activities into collapsible phases.

**Why**:
- Can't display 100 activity cards at once
- Parent/sub-activity relationships provide natural grouping
- Users can expand phases to see details
- Filtering by status, agent, compute provides alternative views

**Alternatives Considered**:
- Show all activities (rejected - overwhelming)
- Manual grouping (rejected - too much user effort)
- Timeline-only view (retained as alternative, not replacement)

---

### 4. SessionSummary for Dashboard Performance

**Decision**: Create lightweight SessionSummary model separate from full ProcessMap.

**Why**:
- Dashboard shows 10-50 sessions
- Loading full ProcessMap for each (with 100+ activities) is expensive
- SessionSummary contains only counts and status (fast to query)
- Can cache summaries for 5-10 seconds

**Trade-off**: Added model complexity vs. significant performance improvement.

---

### 5. Exchange History Pagination

**Decision**: Store all exchanges inline in Activity; paginate on retrieval.

**Why**:
- Most activities have < 50 exchanges (manageable)
- Existing data model stores exchanges in activity.facilitation_exchanges
- Pagination on API level handles outliers (100+ exchanges)
- Keeps data model simple

**API**: 
```
GET /api/v1/process-maps/.../activities/{id}/exchanges?offset=0&limit=20
```

---

## Handling Challenges

### Challenge: Visualizing 100+ Activities

**Solutions**:
1. **Hierarchical Collapse** (primary) - Group into phases
2. **Filtering** (secondary) - Show only "In Progress" or "Blocked"
3. **Search** (tertiary) - Find by activity goal
4. **Timeline View** (alternative) - Chronological scrolling

---

### Challenge: Distributed Compute Tracking

**Solutions**:
1. Store `compute_instance_id` in Activity when facilitation starts
2. Create ComputeUtilization model to aggregate usage
3. Resource Utilization Panel shows which activities run where
4. Display heartbeat status to detect offline instances

---

### Challenge: Real-Time Updates Without Overload

**Solutions**:
1. **Polling with Smart Intervals** - 3-5s for active sessions, 30s for inactive
2. **Caching** - SessionSummary (5s), ActivitySnapshot (3s)
3. **Incremental Updates** - Only fetch changed data (future)
4. **WebSocket** - True push notifications (Phase 7+)

---

### Challenge: Exchange History Data Volume

**Solutions**:
1. **Inline Storage** - Exchanges in activity.facilitation_exchanges (existing)
2. **Pagination** - Return first 20 exchanges, "load more" for rest
3. **Lazy Loading** - Only fetch exchanges when activity detail opened
4. **Compression** - Compress completed activities (future)

---

## Views & Navigation

### 1. Multi-Session Dashboard

**Purpose**: See all active sessions at a glance.

**Key Info**:
- Session ID and business goal
- Overall progress (X% complete)
- Activity breakdown (completed, in progress, blocked)
- Compute resources in use
- Active agents

**Actions**: Click session → Open Session Detail

---

### 2. Session Detail View (Enhanced ProcessMapViewer)

**Tabs**:
- **Overview** - Summary stats, progress, active agents, compute resources
- **Workflow** - Graph visualization with activity cards
- **Timeline** - Chronological event stream
- **Resources** - Compute utilization and agent activity
- **Events** - Coordinating agent events (consistency checks, progress reports)

**Actions**: Click activity → Open Activity Detail Modal

---

### 3. Activity Detail Modal

**Tabs**:
- **Overview** - Goal, status, duration, participants, dependencies, blockers
- **Conversation** - Full exchange history with intent badges
- **Outputs** - Activity results and key findings (Phase 6+)
- **Metadata** - Raw activity data

**Actions**: Close modal → Return to Session Detail

---

### 4. Resource Utilization Panel

**Shows**:
- All compute instances involved in session
- Active activities per instance
- Agent assignments (which agent, which activity, which instance)
- Heartbeat status (online/offline)
- Resource metrics (CPU, memory if available)
- Utilization over time chart

---

### 5. Timeline View

**Shows**:
- Chronological event stream
- Event types: session created, activities started/completed, reevaluations, blockers
- Timestamps for all events
- Filters: All events, Activities only, Reevaluations only, Blockers only

**Use Cases**:
- "What happened when?"
- "Why did the process map change?"
- "When was this blocker identified?"

---

## API Endpoints

### System-Wide Observability

```
GET  /api/v1/observability/sessions
     Returns: List[SessionSummary] for all active sessions

GET  /api/v1/observability/sessions/{session_id}/summary
     Returns: SessionSummary for specific session

GET  /api/v1/observability/sessions/{session_id}/activities/snapshots
     Returns: List[ActivitySnapshot] for all activities

GET  /api/v1/observability/sessions/{session_id}/compute-utilization
     Returns: List[ComputeUtilization] for compute instances

GET  /api/v1/observability/sessions/{session_id}/timeline
     Returns: Chronological event stream
```

### Activity-Specific

```
GET  /api/v1/observability/activities/{activity_id}/snapshot
     Returns: ActivitySnapshot for one activity

GET  /api/v1/observability/activities/{activity_id}/exchanges
     Returns: List[Exchange] with pagination
```

### Resource-Specific

```
GET  /api/v1/observability/compute/{instance_id}/utilization
     Returns: ComputeUtilization for one instance

GET  /api/v1/observability/compute/{instance_id}/sessions
     Returns: List[SessionSummary] using this instance
```

---

## Data Models

### SessionSummary (New)

```python
class SessionSummary(BaseModel):
    session_id: str
    business_goal: str
    status: ProcessMapStatus
    
    # Progress
    total_activities: int
    completed_activities: int
    in_progress_activities: int
    blocked_activities: int
    progress_percent: float
    
    # Resources
    compute_instances: List[str]
    active_agents: List[str]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    duration_seconds: int
    
    # Evolution
    map_version: int
    reevaluation_count: int
```

### ActivitySnapshot (New)

```python
class ActivitySnapshot(BaseModel):
    activity_id: str
    session_id: str
    goal: str
    status: ActivityStatus
    
    # Execution
    assigned_agents: List[ParticipantAssignment]
    compute_instance: Optional[str]  # NEW
    
    # Progress
    exchange_count: int
    duration_seconds: Optional[int]
    last_exchange_at: Optional[datetime]
    
    # Relationships
    depends_on: List[str]
    blocked_by: Optional[str]
    
    # Timestamps
    proposed_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

### ComputeUtilization (New)

```python
class ComputeUtilization(BaseModel):
    instance_id: str
    session_id: str
    
    # Active work
    active_activities: List[str]
    active_agents: List[str]
    
    # Resource metrics (if available)
    cpu_percent: Optional[float]
    memory_used_gb: Optional[float]
    memory_total_gb: Optional[float]
    
    # Status
    status: InstanceStatus
    last_heartbeat: datetime
    
    # Historical
    activity_count_1h: int
    activity_count_total: int
```

---

## Implementation Phases

| Phase | Focus | Duration |
|-------|-------|----------|
| **Phase 1** | Foundation - Data models, APIs, backend service | 1 week |
| **Phase 2** | Multi-Session Dashboard | 1 week |
| **Phase 3** | Enhanced Session Detail (workflow, tabs) | 1 week |
| **Phase 4** | Resource Tracking Panel | 1 week |
| **Phase 5** | Timeline & Events | 1 week |
| **Phase 6** | Optimization (caching, pagination, performance) | 1 week |
| **Phase 7+** | Future (WebSocket, advanced viz, exports) | TBD |

**Total: 6 weeks (1 developer)**

---

## Color Coding Standards

### Activity Status
- 🟢 **Completed**: Green (#10b981)
- 🔵 **In Progress**: Blue (#3b82f6)
- 🟡 **Proposed**: Yellow (#f59e0b)
- 🔴 **Blocked**: Red (#ef4444)
- 🟣 **Revisit**: Purple (#8b5cf6)

### Compute Status
- 🟢 **Online**: Green
- 🟠 **Degraded**: Orange
- 🔴 **Offline**: Red

### Exchange Intent
- 🎯 **FRAME**: Purple
- ❓ **QUESTION**: Blue
- 💬 **ANSWER**: Green
- 🔍 **CLARIFY**: Yellow
- 📊 **ASSESS**: Orange
- ✅ **CONCLUDE**: Green
- ⚠️  **IDENTIFY_BLOCKER**: Red

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Dashboard load (10 sessions) | < 2 seconds |
| Workflow view render (50 activities) | < 3 seconds |
| Activity detail modal open | < 1 second |
| Real-time update latency | 3-5 seconds |
| Timeline scroll smoothness | 60 FPS |
| Support 50 concurrent sessions | Yes |
| Support 100+ activities per session | Yes |
| Support 1000+ exchanges | Yes (with pagination) |

---

## Conflicts & Trade-offs

### Real-Time vs. Scalability
**Decision**: Polling (5s) over WebSocket  
**Rationale**: Simpler, sufficient for human timescales, WebSocket deferred

### Workflow Graph vs. Timeline
**Decision**: Provide both via tabs  
**Rationale**: Different mental models, both valuable, minimal cost

### Full Map vs. Lightweight Summary
**Decision**: SessionSummary for dashboard, full map for detail  
**Rationale**: Performance improvement outweighs model complexity

### Auto-Grouping vs. Manual Grouping
**Decision**: Auto-group by parent/child, allow manual filters  
**Rationale**: Instant value, no user effort, filters provide flexibility

---

## Open Questions

1. **Auto-refresh or manual?**  
   → **Recommendation**: Auto-refresh with pause button

2. **Show coordinating events in timeline?**  
   → **Recommendation**: Show major events (reevaluations, blockers), hide minor (routine checks)

3. **Handle very long-running sessions (days/weeks)?**  
   → **Recommendation**: Start with scrolling timeline, add time compression in Phase 6

4. **Track estimated completion time?**  
   → **Recommendation**: No - facilitated processes are unpredictable, show duration + progress only

---

## Success Metrics

**Usability**:
- Time to identify blocked sessions: < 10 seconds
- Time to drill down to activity detail: < 3 clicks
- User satisfaction: > 4/5

**Performance**:
- Dashboard load: < 2s
- Workflow render: < 3s
- Modal open: < 1s

**Adoption**:
- % sessions monitored via UI: > 80%
- Support tickets ("where is my session?"): -50%

---

## Next Steps

1. ✅ Design review (complete)
2. ⏭️ Create UX mockups (Figma)
3. ⏭️ User testing validation
4. ⏭️ Break into implementation tickets
5. ⏭️ Begin Phase 1 development

---

## Additional Resources

- **[Full Design](PROCESS_MAP_OBSERVABILITY.md)** - Complete technical specification
- **[Design Summary](OBSERVABILITY_DESIGN_SUMMARY.md)** - Key decisions and rationale
- **[Facilitated Process Architecture](EXECUTION_PIPELINE_ARCHITECTURE.md)** - Context for observability
- **[Coordinating Agents Spec](coordinating-agents-spec.md)** - Agent roles and responsibilities

---

**Version**: 1.0  
**Date**: November 25, 2025  
**Status**: Ready for Implementation

