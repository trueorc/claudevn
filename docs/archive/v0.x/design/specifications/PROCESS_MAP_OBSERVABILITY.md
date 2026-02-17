# Process Map Observability Design

**Version**: 1.0  
**Date**: November 25, 2025  
**Status**: Design Proposal

## Executive Summary

This document proposes a comprehensive observability system for monitoring running facilitated processes across distributed compute resources. The design addresses the challenge of visualizing emergent, dynamic workflows where multiple activities are facilitated simultaneously across different compute instances.

**Key Requirements**:
- Real-time visualization of process map execution
- Multi-session monitoring across distributed compute resources
- Activity-level tracking with conversation/exchange visibility
- Compute resource and agent utilization tracking
- Scalable design for process maps with 10-100+ activities
- Progressive disclosure to manage visual complexity

---

## Design Principles

### 1. **Progressive Disclosure**
Don't show everything at once. Provide overview → detail drill-down paths.

### 2. **Real-Time Updates**
Observability data should update in real-time via polling or WebSocket connections.

### 3. **Multi-Level Granularity**
- **System Level**: All active sessions
- **Session Level**: Process map overview for one session
- **Activity Level**: Detailed facilitation progress for one activity
- **Resource Level**: Compute instance and agent utilization

### 4. **Context Preservation**
When drilling down, maintain breadcrumbs and context about where the user is in the hierarchy.

### 5. **Performance First**
Design for process maps with 100+ activities without overwhelming the UI or backend.

---

## Architecture Overview

### Data Flow

```
Compute Instances → Serving (Storage) → Frontend (Visualization)
      ↓                   ↓                     ↓
  Agents Execute    Process Map        Real-time UI
  Activities        Service Stores      Updates
                    State Changes
```

### Components

1. **Backend Services** (Serving)
   - Process Map Service (existing - stores state)
   - Session Service (existing - manages sessions)
   - Compute Registry Service (existing - tracks instances)
   - **NEW: Observability Aggregation Service**

2. **Frontend Components**
   - **NEW: Multi-Session Dashboard** (system overview)
   - **Enhanced: Process Map Viewer** (session detail)
   - **NEW: Activity Detail Modal** (activity drill-down)
   - **NEW: Resource Utilization Panel** (compute tracking)

3. **Data Models**
   - **NEW: SessionSummary** (lightweight session overview)
   - **NEW: ActivitySnapshot** (real-time activity state)
   - **NEW: ComputeUtilization** (resource usage tracking)
   - **Enhanced: ProcessMap** (add observability metadata)

---

## Feature Design

### Feature 1: Multi-Session System Dashboard

**Purpose**: Overview of all active facilitated processes across the platform

**View Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ System Dashboard - Active Sessions                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📊 System Stats                                            │
│  ┌────────────┬────────────┬────────────┬─────────────┐    │
│  │ 12 Active  │ 45 Total   │ 8 Compute  │ 24 Active   │    │
│  │ Sessions   │ Activities │ Resources  │ Agents      │    │
│  └────────────┴────────────┴────────────┴─────────────┘    │
│                                                              │
│  🔄 Active Sessions                                         │
│  ┌──────────────────────────────────────────────────┐      │
│  │ Session: improve-retention-abc123                │      │
│  │ Goal: Increase customer retention by 20%         │      │
│  │ Status: In Progress  │  Progress: 45%            │      │
│  │ ├─ 12 activities (5 complete, 3 active, 4 pending)│     │
│  │ ├─ 3 compute resources in use                    │      │
│  │ └─ 5 agents actively working                     │      │
│  │ [View Details] [View Timeline] [Resource Usage]  │      │
│  └──────────────────────────────────────────────────┘      │
│                                                              │
│  ┌──────────────────────────────────────────────────┐      │
│  │ Session: analyze-sales-xyz789                    │      │
│  │ Goal: Analyze Q4 sales performance               │      │
│  │ Status: In Progress  │  Progress: 78%            │      │
│  │ ├─ 8 activities (6 complete, 1 active, 1 pending)│     │
│  │ ├─ 2 compute resources in use                    │      │
│  │ └─ 2 agents actively working                     │      │
│  │ [View Details] [View Timeline] [Resource Usage]  │      │
│  └──────────────────────────────────────────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Information**:
- Session ID and business goal
- Overall progress percentage
- Activity breakdown by status (proposed, in_progress, goal_met, blocked)
- Number of compute resources involved
- Number of active agents
- Quick actions: drill down to session details, view timeline, check resources

**Filters**:
- Status: All / In Progress / Blocked / Completed
- Time: Last hour / Last 24h / Last 7 days / All
- Compute Resource: All / Specific instance
- Sort: Recent activity / Progress / Duration

---

### Feature 2: Enhanced Session Detail View

**Purpose**: Deep dive into one session's process map with workflow visualization

**View Layout - Overview Mode**:
```
┌─────────────────────────────────────────────────────────────┐
│ Session: improve-retention-abc123                           │
│ Goal: Increase customer retention by 20%                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ [Overview] [Workflow] [Timeline] [Resources] [Events]      │
│                                                              │
│ 📊 Progress Summary                                         │
│ ━━━━━━━━━━━━━━━━━━░░░░░░░░░░░░░ 45% (5/12 complete)       │
│                                                              │
│ ⏱️  Duration: 2h 34m  │  🔄 Map Version: 3  │  ⚠️ 1 Blocker│
│                                                              │
│ 🎯 Activity Status                                          │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ 🟢 Completed (5)  🔵 In Progress (3)                │    │
│ │ 🟡 Proposed (3)   🔴 Blocked (1)                    │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ 🤖 Active Agents (5)                                        │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ • data-analyst-v1      [Activity: analyze-retention] │    │
│ │ • customer-insights-v2 [Activity: segment-analysis]  │    │
│ │ • strategy-agent-v1    [Activity: develop-plan]      │    │
│ │ • consistency-manager  [Monitoring: all activities]  │    │
│ │ • progress-reporter    [Monitoring: all activities]  │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ 💻 Compute Resources (3 instances)                         │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ compute-001 [Online] - 2 activities                  │    │
│ │ compute-003 [Online] - 1 activity                    │    │
│ │ compute-004 [Online] - Coordinating agents           │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**View Layout - Workflow Mode**:

For process maps with **10-30 activities**:
```
┌─────────────────────────────────────────────────────────────┐
│ Workflow View - Process Map v3                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Show: All | Proposed | In Progress | Completed | Blocked] │
│  [Group By: None | Compute Resource | Agent | Timeline]     │
│                                                              │
│    Activity 0: Obtain Database Access                       │
│    ┌──────────────────────────────────────┐                │
│    │ Status: 🟢 Completed (12m ago)       │                │
│    │ Agent: IT-Access-Agent (compute-004) │                │
│    │ [View Conversation] [View Outputs]   │                │
│    └──────────────────────────────────────┘                │
│              │                                               │
│              ↓                                               │
│    Activity 1: Understand Current Retention                 │
│    ┌──────────────────────────────────────┐                │
│    │ Status: 🟢 Completed (8m ago)        │                │
│    │ Agent: DataAnalyst (compute-001)     │                │
│    │ Duration: 23m | 18 exchanges         │                │
│    │ [View Conversation] [View Outputs]   │                │
│    └──────────────────────────────────────┘                │
│              │                                               │
│         ┌────┴────┐                                         │
│         ↓         ↓                                          │
│   Activity 2a   Activity 2b                                 │
│   High-Value    SMB Segment                                 │
│   ┌─────────┐   ┌─────────┐                               │
│   │ 🔵 Active│   │ 🔵 Active│                              │
│   │ 45% done │   │ 30% done │                              │
│   │ 8 exch.  │   │ 5 exch.  │                              │
│   └─────────┘   └─────────┘                               │
│         │         │                                          │
│         └────┬────┘                                         │
│              ↓                                               │
│    Activity 3: Synthesize Findings                          │
│    ┌──────────────────────────────────────┐                │
│    │ Status: 🟡 Proposed (waiting)        │                │
│    │ Agent: Not yet assigned              │                │
│    └──────────────────────────────────────┘                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

For process maps with **30-100+ activities** (hierarchical collapse):
```
┌─────────────────────────────────────────────────────────────┐
│ Workflow View - Process Map v3 (Collapsed)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ▼ Phase 1: Data Collection (5 activities - 100% complete)  │
│     ├─ 🟢 Activity 0, 1, 1a, 1b, 1c                        │
│     └─ [Expand to see details]                              │
│                                                              │
│  ▼ Phase 2: Analysis (12 activities - 67% complete)         │
│     ├─ 🟢 Activity 2, 3, 4, 5, 6, 7, 8, 9                  │
│     ├─ 🔵 Activity 10 (In Progress)                        │
│     ├─ 🔵 Activity 11 (In Progress)                        │
│     ├─ 🔵 Activity 12 (In Progress)                        │
│     └─ 🟡 Activity 13 (Proposed)                           │
│     [Expand] [View Timeline] [View Resources]               │
│                                                              │
│  ▶ Phase 3: Strategy Development (8 activities - 0%)        │
│     └─ All activities pending (dependencies not met)        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Interactive Features**:
- Click activity card → open Activity Detail Modal
- Hover activity → show tooltip (status, duration, agent, last update)
- Drag to pan workflow (for large maps)
- Zoom controls (for dense layouts)
- Filter/Group controls to reduce visual complexity

---

### Feature 3: Activity Detail Modal

**Purpose**: Drill into a single activity to see facilitation conversation and progress

**View Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ Activity Detail: Understand Current Retention               │
│ Session: improve-retention-abc123                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ [Overview] [Conversation] [Outputs] [Metadata]             │
│                                                              │
│ 📋 Overview                                                 │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Goal: Analyze historical customer retention data    │    │
│ │ Status: 🟢 Completed                                │    │
│ │ Duration: 23 minutes                                 │    │
│ │ Started: 2:15 PM  │  Completed: 2:38 PM             │    │
│ │                                                       │    │
│ │ 👤 Participants:                                     │    │
│ │  • data-analyst-v1 (Primary) - compute-001          │    │
│ │  • customer-insights-v2 (Backup) - Not used         │    │
│ │                                                       │    │
│ │ 🔗 Dependencies:                                     │    │
│ │  • Activity 0: Obtain Database Access ✓             │    │
│ │                                                       │    │
│ │ ⚠️ Blockers: None                                   │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ 💬 Conversation Timeline (18 exchanges)                    │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ [2:15 PM] 🎯 FRAME - Facilitator                    │    │
│ │ "We need to understand current retention metrics.   │    │
│ │  What data sources do you need?"                     │    │
│ │                                                       │    │
│ │ [2:16 PM] 💬 ANSWER - data-analyst-v1               │    │
│ │ "I need access to customer database for last 12     │    │
│ │  months. Specifically: user_id, signup_date,        │    │
│ │  last_activity_date, subscription_status."           │    │
│ │                                                       │    │
│ │ [2:17 PM] ❓ QUESTION - Facilitator                 │    │
│ │ "Do you have the necessary credentials?"             │    │
│ │                                                       │    │
│ │ [2:17 PM] 💬 ANSWER - data-analyst-v1               │    │
│ │ "Yes, credentials were provided in Activity 0."      │    │
│ │                                                       │    │
│ │ [2:19 PM] 🔍 CLARIFY - Facilitator                  │    │
│ │ "Should we segment by customer type or cohort?"      │    │
│ │                                                       │    │
│ │ [2:20 PM] 💬 ANSWER - data-analyst-v1               │    │
│ │ "Initial analysis shows significant variance.        │    │
│ │  Recommend segmentation by: high-value (78%          │    │
│ │  retention) vs SMB (55% retention)."                 │    │
│ │ 📊 [View full analysis]                              │    │
│ │                                                       │    │
│ │ ... [12 more exchanges]                              │    │
│ │                                                       │    │
│ │ [2:38 PM] ✅ CONCLUDE - Facilitator                 │    │
│ │ "Activity goal achieved. Key finding: Retention      │    │
│ │  varies significantly by segment. Recommend          │    │
│ │  separate analysis paths."                           │    │
│ │ Outcome: Goal Met | New Understanding: Segmentation  │    │
│ │          is critical                                 │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ [Close] [View Process Map] [View Next Activity]            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Features**:
- Conversation timeline with exchange intents color-coded
- Timestamps for each exchange
- Speaker identification (facilitator vs agents)
- Outcome and understanding captured
- Link to view full outputs (large artifacts)
- Navigation to related activities

---

### Feature 4: Resource Utilization Panel

**Purpose**: Track which compute resources and agents are actively working

**View Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ Resource Utilization - Session: improve-retention-abc123    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ 💻 Compute Instances (3 active)                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ 🟢 compute-001 - Data Processing Node               │    │
│ │    Active: 2 activities                              │    │
│ │    ├─ Activity 2a: High-value segment (data-analyst)│    │
│ │    └─ Activity 4: Verify metrics (metric-reporter)  │    │
│ │    Resources: CPU 45% | Memory 12GB/32GB            │    │
│ │    Last heartbeat: 5s ago                            │    │
│ │    [View Details] [View Logs]                        │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ 🟢 compute-003 - ML/AI Node                         │    │
│ │    Active: 1 activity                                │    │
│ │    └─ Activity 2b: SMB segment (customer-insights)  │    │
│ │    Resources: CPU 67% | Memory 18GB/64GB            │    │
│ │    Last heartbeat: 3s ago                            │    │
│ │    [View Details] [View Logs]                        │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ 🟢 compute-004 - Coordination Node                  │    │
│ │    Active: 2 coordinating agents                     │    │
│ │    ├─ consistency-manager-v1 (monitoring)            │    │
│ │    └─ progress-reporter-v1 (monitoring)              │    │
│ │    Resources: CPU 12% | Memory 4GB/16GB             │    │
│ │    Last heartbeat: 8s ago                            │    │
│ │    [View Details] [View Logs]                        │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ 🤖 Agent Activity Summary                                   │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Agent                  │ Status      │ Activity      │    │
│ ├────────────────────────┼─────────────┼──────────────┤    │
│ │ data-analyst-v1        │ 🔵 Active   │ Activity 2a  │    │
│ │ customer-insights-v2   │ 🔵 Active   │ Activity 2b  │    │
│ │ metric-reporter-v1     │ 🔵 Active   │ Activity 4   │    │
│ │ strategy-agent-v1      │ 🟡 Idle     │ -            │    │
│ │ consistency-manager-v1 │ 👁️ Monitor  │ All          │    │
│ │ progress-reporter-v1   │ 👁️ Monitor  │ All          │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
│ 📊 Utilization Over Time (Last Hour)                       │
│ ┌─────────────────────────────────────────────────────┐    │
│ │     Compute-001 ████████████░░░░░░░░░░              │    │
│ │     Compute-003 ██████████████░░░░░░                │    │
│ │     Compute-004 ████░░░░░░░░░░░░░░░░░░              │    │
│ │     ├────────┬────────┬────────┬────────┬────────┤  │    │
│ │    3:00     3:15     3:30     3:45     4:00       │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Information**:
- Which compute instances are involved in this session
- Active activities per instance
- Resource utilization (CPU, memory if available)
- Agent-to-activity mappings
- Heartbeat status
- Historical utilization chart

---

### Feature 5: Timeline View

**Purpose**: Chronological view of all activity events for a session

**View Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ Timeline - Session: improve-retention-abc123                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ [Filter: All | Activities | Reevaluations | Blockers]      │
│ [Time Range: Last Hour | Last 4 Hours | All]               │
│                                                              │
│ 2:00 PM ─────────────────────────────────────────────────   │
│         📋 Session Created                                   │
│         Goal: Increase customer retention by 20%             │
│                                                              │
│ 2:02 PM │ 🗺️  Process Map v1 Created                       │
│         │    3 initial activities proposed                   │
│                                                              │
│ 2:03 PM │ 🎯 Activity 0: Obtain Database Access            │
│         │    Status: In Progress                             │
│                                                              │
│ 2:15 PM │ ✅ Activity 0: Completed                         │
│         │    Duration: 12 minutes                            │
│                                                              │
│ 2:15 PM │ 🎯 Activity 1: Understand Current Retention      │
│         │    Status: In Progress                             │
│         │    Agent: data-analyst-v1 (compute-001)           │
│                                                              │
│ 2:30 PM │ 🔄 Process Map v2 (Reevaluation)                 │
│         │    Triggered by: Segmentation discovered           │
│         │    Changes: Split Activity 2 → 2a, 2b             │
│                                                              │
│ 2:38 PM │ ✅ Activity 1: Completed                         │
│         │    Duration: 23 minutes | 18 exchanges            │
│         │    Key Finding: Retention varies by segment        │
│                                                              │
│ 2:40 PM │ 🎯 Activity 2a: Analyze High-Value Segment       │
│         │    Status: In Progress                             │
│         │    Agent: data-analyst-v1 (compute-001)           │
│                                                              │
│ 2:41 PM │ 🎯 Activity 2b: Analyze SMB Segment              │
│         │    Status: In Progress                             │
│         │    Agent: customer-insights-v2 (compute-003)      │
│                                                              │
│ 3:05 PM │ ⚠️  Blocker Identified - Activity 2b             │
│         │    Issue: Need historical pricing data             │
│         │    Action: Creating Activity 2b-1                  │
│                                                              │
│ 3:07 PM │ 🔄 Process Map v3 (Reevaluation)                 │
│         │    Triggered by: Blocker in Activity 2b            │
│         │    Changes: Added Activity 2b-1 as dependency      │
│                                                              │
│ 3:10 PM │ 🎯 Activity 2b-1: Obtain Pricing Data            │
│         │ └─ Now ─────────────────────────────────────────  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Features**:
- Chronological event stream
- Event types: activities start/complete, reevaluations, blockers, agent assignments
- Visual timeline with timestamps
- Filtering by event type
- Quick navigation to activity details

---

## Data Models

### SessionSummary (New)

```python
class SessionSummary(BaseModel):
    """Lightweight session overview for dashboard."""
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
    compute_instances: List[str]  # Instance IDs in use
    active_agents: List[str]       # Agent IDs actively working
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    duration_seconds: int
    
    # Map evolution
    map_version: int
    reevaluation_count: int
```

### ActivitySnapshot (New)

```python
class ActivitySnapshot(BaseModel):
    """Real-time activity state for observability."""
    activity_id: str
    session_id: str
    goal: str
    status: ActivityStatus
    
    # Execution
    assigned_agents: List[ParticipantAssignment]
    compute_instance: Optional[str]  # Where it's executing
    
    # Progress
    exchange_count: int
    duration_seconds: Optional[int]
    last_exchange_at: Optional[datetime]
    
    # Relationships
    depends_on: List[str]
    blocked_by: Optional[str]  # Blocker ID if blocked
    
    # Timestamps
    proposed_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

### ComputeUtilization (New)

```python
class ComputeUtilization(BaseModel):
    """Compute resource usage tracking."""
    instance_id: str
    session_id: str
    
    # Active work
    active_activities: List[str]  # Activity IDs
    active_agents: List[str]       # Agent IDs
    
    # Resource metrics (if available)
    cpu_percent: Optional[float]
    memory_used_gb: Optional[float]
    memory_total_gb: Optional[float]
    
    # Status
    status: InstanceStatus
    last_heartbeat: datetime
    
    # Historical
    activity_count_1h: int         # Activities in last hour
    activity_count_total: int      # Total activities handled
```

### Enhanced ProcessMap

Add observability metadata to existing ProcessMap:

```python
class ProcessMap(BaseModel):
    # ... existing fields ...
    
    # NEW: Observability metadata
    compute_instances_used: Dict[str, List[str]]  # instance_id -> [activity_ids]
    agent_assignments: Dict[str, List[str]]        # agent_id -> [activity_ids]
    total_exchange_count: int
    total_duration_seconds: int
```

---

## API Endpoints

### New Observability Endpoints

```python
# System-wide observability
GET  /api/v1/observability/sessions
     → Returns List[SessionSummary] for all active sessions

GET  /api/v1/observability/sessions/{session_id}/summary
     → Returns SessionSummary for specific session

GET  /api/v1/observability/sessions/{session_id}/activities/snapshots
     → Returns List[ActivitySnapshot] for all activities in session

GET  /api/v1/observability/sessions/{session_id}/compute-utilization
     → Returns List[ComputeUtilization] for all compute instances used

GET  /api/v1/observability/sessions/{session_id}/timeline
     → Returns chronological event stream (activities, reevaluations, etc.)

# Activity-specific observability
GET  /api/v1/observability/activities/{activity_id}/snapshot
     → Returns ActivitySnapshot for one activity

GET  /api/v1/observability/activities/{activity_id}/exchanges
     → Returns List[Exchange] (already exists in process_maps.py)

# Resource-specific observability
GET  /api/v1/observability/compute/{instance_id}/utilization
     → Returns ComputeUtilization for one instance

GET  /api/v1/observability/compute/{instance_id}/sessions
     → Returns List[SessionSummary] for sessions using this instance
```

---

## Performance Considerations

### Scalability Strategies

1. **Pagination**
   - Timeline events: Paginate by time window
   - Activity lists: Paginate when > 50 activities
   - Exchange history: Paginate when > 100 exchanges

2. **Caching**
   - Cache SessionSummary for 5-10 seconds
   - Cache ActivitySnapshot for 3-5 seconds
   - Invalidate on state changes

3. **Incremental Updates**
   - Use WebSocket for real-time updates (optional Phase 2)
   - Polling with Last-Modified headers
   - Only fetch changed activities

4. **Hierarchical Rendering**
   - Collapse completed phases in workflow view
   - Lazy load activity details on demand
   - Virtual scrolling for large lists

5. **Database Indexing**
   - Index on session_id, status, updated_at
   - Index on activity_id, session_id
   - Composite indexes for common queries

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create data models (SessionSummary, ActivitySnapshot, ComputeUtilization)
- [ ] Implement basic observability endpoints
- [ ] Create ObservabilityService in serving component
- [ ] Add compute instance tracking to activities

### Phase 2: Multi-Session Dashboard (Week 2)
- [ ] Build system dashboard component (React)
- [ ] Implement session filtering and sorting
- [ ] Add real-time updates via polling
- [ ] Create resource utilization summary cards

### Phase 3: Enhanced Session Detail (Week 3)
- [ ] Upgrade ProcessMapViewer with new tabs (Overview, Resources, Timeline)
- [ ] Implement workflow visualization with collapsible hierarchies
- [ ] Add filtering/grouping controls
- [ ] Create Activity Detail Modal

### Phase 4: Resource Tracking (Week 4)
- [ ] Build Resource Utilization Panel
- [ ] Implement compute-to-activity mappings
- [ ] Add agent status tracking
- [ ] Create utilization charts

### Phase 5: Timeline & Events (Week 5)
- [ ] Build Timeline View component
- [ ] Implement event stream aggregation
- [ ] Add event filtering
- [ ] Create event detail panels

### Phase 6: Optimization (Week 6)
- [ ] Implement caching strategies
- [ ] Add pagination where needed
- [ ] Optimize database queries
- [ ] Performance testing with 100+ activity process maps

---

## Challenges & Solutions

### Challenge 1: Visualizing 100+ Activities

**Problem**: Process maps can have many activities, overwhelming the UI.

**Solutions**:
- **Hierarchical Collapse**: Group related activities into phases/sub-processes
- **Progressive Disclosure**: Show summary → expand for details
- **Filtering**: Allow users to filter by status, agent, compute resource
- **Search**: Add search by activity goal/description
- **Zoom Controls**: Pan and zoom for large workflow diagrams

### Challenge 2: Real-Time Updates Across Distributed Compute

**Problem**: Activities run on different compute instances; state changes must propagate.

**Solutions**:
- **Centralized State**: Serving stores authoritative process map state
- **Heartbeat Updates**: Compute instances send activity state with heartbeats
- **Event Bus**: Use coordinating event bus (existing) for state changes
- **Polling Strategy**: Frontend polls every 3-5 seconds for active sessions
- **WebSocket (Future)**: Add WebSocket support for true real-time (Phase 7+)

### Challenge 3: Tracking Agent-to-Compute Mapping

**Problem**: Need to know which agents are running where.

**Solutions**:
- **Activity Metadata**: Store `compute_instance_id` in Activity when facilitation starts
- **Agent Registry**: Compute instances report available agents on registration
- **Assignment Tracking**: ParticipantAssignment includes compute instance
- **Utilization Service**: Aggregate agent usage across sessions

### Challenge 4: Exchange History Storage

**Problem**: Conversations can have 100+ exchanges; storing and retrieving efficiently.

**Solutions**:
- **Already Solved**: Exchanges stored in activity.facilitation_exchanges (list)
- **Pagination**: API returns paginated exchanges (first 20, expand for more)
- **Compression**: Consider compressing old exchange history for completed activities
- **Archiving**: Move completed session data to cold storage after 30 days

### Challenge 5: Multiple Sessions Competing for Same Compute

**Problem**: Limited compute resources, need to show contention/utilization.

**Solutions**:
- **Utilization Metrics**: Track active activities per compute instance
- **Queue Visibility**: Show pending activities waiting for compute
- **Resource Allocation UI**: Display which sessions are using which resources
- **Alerts**: Warn if compute resources are overutilized (>80% capacity)

---

## Future Enhancements (Post-MVP)

### WebSocket Real-Time Updates
- Replace polling with WebSocket connections
- Push state changes to UI immediately
- Reduce server load and improve responsiveness

### Advanced Visualizations
- Network graph view of activity dependencies
- Gantt chart for activity timelines
- Heatmap of compute resource utilization over time

### Outputs & Results Viewer
- Display activity outputs inline (text, tables, charts)
- Support rich media (images, PDFs, visualizations)
- Diff view for reevaluation changes

### Alerting & Notifications
- Notify users when activities complete or block
- Send alerts for process map reevaluations
- Threshold alerts for long-running activities

### Historical Analytics
- Compare session durations and efficiency
- Analyze common blocker patterns
- Identify frequently used agents/compute resources
- Optimize process map structures based on history

### Export & Reporting
- Export process map visualization as PDF/PNG
- Generate executive summary reports
- Download conversation transcripts
- Export activity outputs

---

## Design Mockup Notes

### Color Coding Standards

**Activity Status**:
- 🟢 Completed: Green (#10b981)
- 🔵 In Progress: Blue (#3b82f6)
- 🟡 Proposed: Yellow (#f59e0b)
- 🔴 Blocked: Red (#ef4444)
- 🟣 Revisit: Purple (#8b5cf6)

**Compute Status**:
- 🟢 Online: Green
- 🟠 Degraded: Orange
- 🔴 Offline: Red

**Exchange Intent**:
- 🎯 FRAME: Purple
- ❓ QUESTION: Blue
- 💬 ANSWER: Green
- 🔍 CLARIFY: Yellow
- 📊 ASSESS: Orange
- ✅ CONCLUDE: Green
- ⚠️  IDENTIFY_BLOCKER: Red

### Responsive Design

- Desktop (1400px+): Full dashboard with side-by-side panels
- Tablet (768-1399px): Stacked panels, collapsible sidebar
- Mobile (< 768px): Single column, bottom navigation, accordions

---

## Validation Criteria

✅ **Usability**:
- [ ] User can identify all active sessions at a glance
- [ ] User can drill down from session → activity → exchange in < 3 clicks
- [ ] User can identify blocked activities within 5 seconds
- [ ] User can see which compute resources are in use per session

✅ **Performance**:
- [ ] Dashboard loads < 2 seconds with 10 active sessions
- [ ] Workflow view renders < 3 seconds for 50 activity process map
- [ ] Activity detail modal opens < 1 second
- [ ] Real-time updates appear within 10 seconds of state change

✅ **Scalability**:
- [ ] System handles 50 concurrent sessions
- [ ] Process maps with 100+ activities render without lag
- [ ] 1000+ exchanges don't slow down activity detail view
- [ ] 20+ compute instances tracked simultaneously

---

## Summary

This observability design provides:

1. **Multi-level visibility**: System → Session → Activity → Exchange
2. **Resource awareness**: Track compute and agent utilization
3. **Scalability**: Handle large process maps (100+ activities)
4. **Real-time monitoring**: See progress as it happens
5. **Actionable insights**: Identify blockers, bottlenecks, resource contention

**Key Innovation**: Progressive disclosure with hierarchical collapse allows users to manage complexity while still having full visibility into any level of detail.

The design is compatible with the existing facilitated process architecture (v0.2.0) and can be implemented incrementally over 6 weeks without disrupting current functionality.

---

**Next Steps**:
1. Review this design with team
2. Validate UX mockups with users
3. Create implementation tickets
4. Begin Phase 1 development

---

**Document History**:
- v1.0 - November 25, 2025 - Initial design proposal

