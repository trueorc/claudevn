# Serving Component - Architecture Diagrams

**Version:** 0.2.0 (Planned)  
**Last Updated:** November 23, 2025

This document provides detailed architectural diagrams for the Serving Component.

---

## System Context Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                         ClaudeVN Platform                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────┐         ┌──────────────┐                   │
│  │  Marketplace │         │   Compute    │                   │
│  │   (8001)     │◄────────┤   Engines    │                   │
│  │              │         │   (8003+)    │                   │
│  └──────┬───────┘         └──────┬───────┘                   │
│         │                        │                            │
│         │                        │                            │
│         │     ┌──────────────────┼──────────────┐            │
│         │     │                  │              │            │
│         └─────►   SERVING COMPONENT (8002)      │            │
│               │                                 │            │
│               │  • Compute Registry             │            │
│               │  • Marketplace Proxy            │            │
│               │  • A2A Message Router           │            │
│               │  • Session Coordinator          │            │
│               │  • Management UI                │            │
│               │                                 │            │
│               └─────────────────────────────────┘            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Serving Component (Port 8002)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────── UI Layer ─────────────────────┐ │
│  │                                                            │ │
│  │  React Frontend (Served by FastAPI)                       │ │
│  │  • Dashboard          • Session Monitor                   │ │
│  │  • Compute Registry   • Marketplace Connections           │ │
│  │                                                            │ │
│  └─────────────────────────┬──────────────────────────────────┘ │
│                            │ HTTP/REST                          │
│  ┌─────────────────────────▼──────────────────────────────────┐ │
│  │                      API Layer                             │ │
│  │                                                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │  │ Compute  │  │Marketplace│  │   A2A    │  │ Sessions │ │ │
│  │  │   API    │  │   API     │  │  Protocol│  │   API    │ │ │
│  │  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘ │ │
│  │        │             │              │             │       │ │
│  └────────┼─────────────┼──────────────┼─────────────┼───────┘ │
│           │             │              │             │         │
│  ┌────────▼─────────────▼──────────────▼─────────────▼───────┐ │
│  │                   Business Logic Layer                     │ │
│  │                                                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │ │
│  │  │ Registry │  │Marketplace│  │   A2A    │  │ Session  │ │ │
│  │  │ Service  │  │  Manager  │  │  Router  │  │  Manager │ │ │
│  │  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘ │ │
│  │        │             │              │             │       │ │
│  │  ┌─────▼──────┐ ┌────▼────┐   ┌────▼────┐   ┌────▼────┐ │ │
│  │  │  Health    │ │  Cache  │   │ Message │   │  Task   │ │ │
│  │  │  Monitor   │ │ Manager │   │  Queue  │   │ Tracker │ │ │
│  │  └────────────┘ └─────────┘   └─────────┘   └─────────┘ │ │
│  │                                                            │ │
│  └─────────────────────────┬──────────────────────────────────┘ │
│                            │                                    │
│  ┌─────────────────────────▼──────────────────────────────────┐ │
│  │                   Storage Layer                            │ │
│  │                                                            │ │
│  │  ┌──────────────────┐  ┌──────────────────┐              │ │
│  │  │  Registry Store  │  │  Session Store   │              │ │
│  │  │  (Filesystem)    │  │  (Filesystem)    │              │ │
│  │  └──────────────────┘  └──────────────────┘              │ │
│  │                                                            │ │
│  │  ┌──────────────────┐  ┌──────────────────┐              │ │
│  │  │   Task Store     │  │   Blob Storage   │              │ │
│  │  │  (Filesystem)    │  │  (Filesystem)    │              │ │
│  │  └──────────────────┘  └──────────────────┘              │ │
│  │                                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Compute Registration

```
   Compute Instance                 Serving Component
   ───────────────                  ─────────────────
        
   1. Startup
      │
      ├─ POST /api/v1/compute/register
      │  {
      │    instance_id: "compute-001",
      │    endpoint: "http://localhost:8003",
      │    capabilities: ["agent-a", "agent-b"],
      │    health_endpoint: "http://localhost:8003/health"
      │  }
      │
      ▼
                                   2. Compute API
                                      │
                                      ├─ Validate request
                                      │
                                      ▼
                                   3. Registry Service
                                      │
                                      ├─ Add to registry
                                      ├─ Start health monitoring
                                      ├─ Aggregate capabilities
                                      │
                                      ▼
                                   4. Registry Store
                                      │
                                      ├─ Save instance metadata
                                      ├─ Update capability index
                                      │
                                      ▼
                                   5. Health Monitor
                                      │
                                      ├─ Schedule heartbeat checks
      ◄─────────────────────────────┤
      Response: 201 Created          │
      {
        status: "registered",
        heartbeat_interval: 30
      }
      
   6. Heartbeat Loop
      │
      ├─ (every 30s)
      │  POST /api/v1/compute/compute-001/health
      ├──────────────────────────────►
                                   7. Update last_heartbeat
                                      │
                                      ├─ Mark as online
                                      ▼
                                   8. If no heartbeat for 90s
                                      │
                                      ├─ Mark as offline
                                      ├─ Optional: deregister
```

---

## Data Flow: Agent Discovery via Marketplace Proxy

```
   User/Client              Serving Component           Marketplace(s)
   ───────────              ─────────────────           ──────────────
   
   1. Search agents
      │
      ├─ POST /a2a/agents/search
      │  { query: "data analyst" }
      │
      ▼
                           2. A2A API
                              │
                              ├─ Parse search request
                              │
                              ▼
                           3. Marketplace Manager
                              │
                              ├─ Get connected marketplaces
                              │   (Marketplace A, B, C)
                              │
                              ├─ Query in parallel ──────┐
                              │                          │
                              │                          ▼
                                                   GET /api/v1/agents/search
                                                   
                              ◄─────────────────── Results from A (3 agents)
                              │
                              ◄─────────────────── Results from B (2 agents)
                              │
                              ◄─────────────────── Timeout from C
                              │
                              ├─ Merge results
                              ├─ Deduplicate by agent_id
                              ├─ Sort by relevance
                              ├─ Add source info
                              ├─ Cache results (TTL: 5min)
                              │
                              ▼
                           4. Response
      ◄────────────────────┤
      [
        { agent_id: "data-analyst-pro", 
          source: "marketplace-a" },
        { agent_id: "data-scientist", 
          source: "marketplace-a" },
        ...
      ]
```

---

## Data Flow: A2A Task Routing

```
Compute Instance A        Serving Component        Compute Instance B
──────────────────        ─────────────────        ──────────────────

1. Submit task
   │
   ├─ POST /a2a/tasks
   │  {
   │    agent_id: "data-analyst",
   │    session_id: "session-001",
   │    input: { data: "..." }
   │  }
   │
   ▼
                        2. A2A API
                           │
                           ├─ Validate request
                           ├─ Generate task_id
                           │
                           ▼
                        3. A2A Router
                           │
                           ├─ Find which compute has agent
                           │   Query: "data-analyst"
                           │   Result: compute-instance-B
                           │
                           ├─ Check instance is online
                           │
                           ▼
                        4. Forward to Instance B
                           │
                           ├─ POST /a2a/tasks ──────►
                           │                         │
                           │                         ├─ Receive task
                           │                         ├─ Enqueue
                           │                         ├─ Start execution
                           │                         │
                           ◄─────────────────────────┤
                           │  202 Accepted           │
                           │                         │
                           ▼                         ▼
                        5. Store in session      6. Execute task
                           │                         │
                           ├─ Link task to session   ├─ Load agent
                           ├─ Update session context ├─ Process input
                           │                         ├─ Generate result
   ◄───────────────────────┤                         │
   Response: 202 Accepted  │                         │
   {                       │                         │
     task_id: "task-xyz",  │                         │
     status: "submitted"   │                         │
   }                       │                         │
                           │                         │
7. Stream updates         │                         │
   │                       │                         │
   ├─ GET /a2a/tasks/task-xyz/stream                │
   │  (SSE connection)     │                         │
   │                       │                         │
   ◄───────────────────────┤  Update callbacks       │
   event: status           ◄─────────────────────────┤
   data: {"status": "working"}                       │
                           │                         │
   ◄───────────────────────┤                         │
   event: status           ◄─────────────────────────┤
   data: {"status": "completed",                     │
          "result": {...}}                           │
                           │                         │
                        8. Update session            │
                           │                         │
                           ├─ Add task result        │
                           ├─ Update status          │
```

---

## Storage Structure

```
data/serving/
│
├── registry/
│   ├── compute/
│   │   ├── compute-001.json
│   │   │   {
│   │   │     "instance_id": "compute-001",
│   │   │     "endpoint": "http://localhost:8003",
│   │   │     "status": "online",
│   │   │     "capabilities": {
│   │   │       "agents": ["agent-a", "agent-b"],
│   │   │       "tools": ["tool-x"],
│   │   │       "resources": {"cpu": 4, "memory_gb": 16}
│   │   │     },
│   │   │     "registered_at": "2025-11-23T10:00:00Z",
│   │   │     "last_heartbeat": "2025-11-23T10:05:30Z"
│   │   │   }
│   │   │
│   │   ├── compute-002.json
│   │   │
│   │   └── index.json
│   │       {
│   │         "instances": ["compute-001", "compute-002"],
│   │         "capabilities": {
│   │           "agent-a": ["compute-001"],
│   │           "agent-b": ["compute-001"],
│   │           "agent-c": ["compute-002"]
│   │         }
│   │       }
│   │
│   └── marketplaces/
│       ├── marketplace-corp.json
│       │   {
│       │     "connection_id": "marketplace-corp",
│       │     "name": "Corporate Marketplace",
│       │     "url": "http://localhost:8001",
│       │     "status": "connected",
│       │     "priority": 1,
│       │     "agent_count": 25,
│       │     "last_sync": "2025-11-23T10:03:00Z"
│       │   }
│       │
│       └── index.json
│           {
│             "marketplaces": ["marketplace-corp", "marketplace-public"]
│           }
│
├── sessions/
│   ├── session-001.json
│   │   {
│   │     "session_id": "session-001",
│   │     "status": "in_progress",
│   │     "execution_plan": { ... },
│   │     "task_results": {
│   │       "task-xyz": { "status": "completed", "result": {...} }
│   │     },
│   │     "data_refs": {
│   │       "dataset-1": { "blob_id": "blob-abc", "type": "csv" }
│   │     },
│   │     "metadata": { "user_id": "user-001", "goal": "Analyze data" },
│   │     "created_at": "2025-11-23T09:00:00Z",
│   │     "updated_at": "2025-11-23T10:05:00Z"
│   │   }
│   │
│   └── session-002.json
│
├── tasks/
│   ├── task-xyz.json
│   │   {
│   │     "task_id": "task-xyz",
│   │     "agent_id": "data-analyst",
│   │     "session_id": "session-001",
│   │     "status": "completed",
│   │     "input": { "data": "..." },
│   │     "result": { "insights": [...] },
│   │     "routed_to": "compute-002",
│   │     "created_at": "2025-11-23T10:00:00Z",
│   │     "completed_at": "2025-11-23T10:05:00Z"
│   │   }
│   │
│   └── task-abc.json
│
└── blobs/
    └── session-001/
        ├── blob-abc
        └── blob-def
```

---

## Health Monitoring Flow

```
┌─────────────────────────────────────────────────────────┐
│              Health Monitor (Background Task)           │
└─────────────────────────────────────────────────────────┘
                         │
                         │ Every CHECK_INTERVAL (30s)
                         │
                         ▼
            ┌────────────────────────────┐
            │  Get all registered        │
            │  compute instances         │
            └──────────┬─────────────────┘
                       │
                       ▼
            ┌────────────────────────────┐
            │  For each instance:        │
            │                            │
            │  1. Check last_heartbeat   │
            │  2. Calculate elapsed time │
            └──────────┬─────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
    Healthy?      Degraded?      Dead?
    (< 60s)       (60-90s)       (> 90s)
        │              │              │
        ▼              ▼              ▼
   ┌────────┐    ┌────────┐     ┌────────┐
   │ Status:│    │ Status:│     │ Status:│
   │ online │    │degraded│     │ offline│
   └────────┘    └────────┘     └────┬───┘
                                     │
                                     ▼
                            ┌────────────────┐
                            │ Failed checks? │
                            └────────┬───────┘
                                     │
                      ┌──────────────┼──────────────┐
                      │                             │
                      ▼                             ▼
               < MAX_FAILED (3)            >= MAX_FAILED (3)
                      │                             │
                      ▼                             ▼
               Keep registered              Auto-deregister?
                                                    │
                                      ┌─────────────┼─────────────┐
                                      │                           │
                                      ▼                           ▼
                                   Enabled                    Disabled
                                      │                           │
                                      ▼                           ▼
                              Remove instance               Mark offline only
```

---

## Session Lifecycle

```
1. Create Session
   │
   ├─ POST /api/v1/sessions
   │  { goal: "Analyze Q4 sales" }
   │
   ▼
┌────────────────────────┐
│ Session Created        │
│ Status: PENDING        │
│ ID: session-001        │
└───────┬────────────────┘
        │
        ▼
2. Set Execution Plan
   │
   ├─ PUT /api/v1/sessions/session-001/execution_plan
   │  { tasks: [...], dependencies: [...] }
   │
   ▼
┌────────────────────────┐
│ Status: IN_PROGRESS    │
│ Execution plan set     │
└───────┬────────────────┘
        │
        ▼
3. Execute Tasks (via A2A)
   │
   ├─ POST /a2a/tasks
   │  { agent_id: "...", session_id: "session-001" }
   │
   ├─ Task routed to compute
   │
   ├─ Task executes
   │
   ▼
4. Store Task Results
   │
   ├─ POST /api/v1/sessions/session-001/task_results
   │  { task_id: "task-1", result: {...} }
   │
   ├─ Repeat for each task
   │
   ▼
5. Add Data References
   │
   ├─ POST /api/v1/sessions/session-001/data_refs
   │  { ref_name: "dataset", ref_data: {...} }
   │
   ▼
6. Complete Session
   │
   ├─ PATCH /api/v1/sessions/session-001/status
   │  { status: "completed" }
   │
   ▼
┌────────────────────────┐
│ Status: COMPLETED      │
│ All tasks done         │
│ Results stored         │
└────────────────────────┘
```

---

## Frontend UI Structure

```
┌─────────────────────────────────────────────────────────────┐
│                      Serving Dashboard                      │
│                    http://localhost:8002                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  System Health Overview                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │   │
│  │  │ Serving  │  │ Compute  │  │Marketplace│         │   │
│  │  │  Status  │  │Instances │  │  Status   │         │   │
│  │  │  ● OK    │  │   3/3    │  │   2/2 ●  │         │   │
│  │  └──────────┘  └──────────┘  └──────────┘         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📊 Compute Registry                                │   │
│  │  ┌───────────┬────────┬──────────────┬────────────┐ │   │
│  │  │ Instance  │ Status │ Capabilities │ Last Seen  │ │   │
│  │  ├───────────┼────────┼──────────────┼────────────┤ │   │
│  │  │compute-001│ ● Online│ agent-a, b  │ 15s ago    │ │   │
│  │  │compute-002│ ● Online│ agent-c     │ 20s ago    │ │   │
│  │  │compute-003│ ⚠ Degraded│ agent-d   │ 75s ago    │ │   │
│  │  └───────────┴────────┴──────────────┴────────────┘ │   │
│  │  [Register New Instance]                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🏪 Marketplace Connections                         │   │
│  │  ┌─────────────────┐  ┌─────────────────┐          │   │
│  │  │ Corporate MP    │  │ Public MP       │          │   │
│  │  │ ● Connected     │  │ ● Connected     │          │   │
│  │  │ 25 agents       │  │ 150 agents      │          │   │
│  │  │ Priority: 1     │  │ Priority: 2     │          │   │
│  │  │ [Test] [Remove] │  │ [Test] [Remove] │          │   │
│  │  └─────────────────┘  └─────────────────┘          │   │
│  │  [Connect New Marketplace]                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📝 Recent Sessions                                 │   │
│  │  ┌──────────┬──────────┬────────────┬─────────────┐ │   │
│  │  │Session ID│  Status  │   Goal     │  Updated    │ │   │
│  │  ├──────────┼──────────┼────────────┼─────────────┤ │   │
│  │  │session-01│ Running  │Analyze data│ 2 min ago   │ │   │
│  │  │session-02│ Completed│Create doc  │ 15 min ago  │ │   │
│  │  │session-03│ Failed   │Process img │ 1 hour ago  │ │   │
│  │  └──────────┴──────────┴────────────┴─────────────┘ │   │
│  │  [View All Sessions]                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    ClaudeVN Full System                     │
└────────────────────────────────────────────────────────────┘

┌──────────────┐          ┌──────────────┐          ┌──────────────┐
│  Marketplace │          │   Serving    │          │   Compute    │
│   (8001)     │          │    (8002)    │          │   (8003+)    │
└──────┬───────┘          └──────┬───────┘          └──────┬───────┘
       │                         │                         │
       │                         │                         │
       │  1. Register Compute    │                         │
       │                         │◄────────────────────────┤
       │                         │  POST /compute/register │
       │                         │                         │
       │  2. Connect Marketplace │                         │
       │◄────────────────────────┤                         │
       │  GET /api/v1/agents     │                         │
       │                         │                         │
       │  3. Agent Discovery     │                         │
       ├────────────────────────►│                         │
       │  GET /api/v1/agents     │                         │
       │                         │                         │
       │                         │  4. Submit Task         │
       │                         │◄────────────────────────┤
       │                         │  POST /a2a/tasks        │
       │                         │                         │
       │                         │  5. Route Task          │
       │                         ├────────────────────────►│
       │                         │  POST /a2a/tasks        │
       │                         │                         │
       │                         │  6. Task Updates        │
       │                         │◄────────────────────────┤
       │                         │  Callbacks              │
       │                         │                         │
       │  7. Store Results       │                         │
       │                         │                         │
       │                         │  8. Get Results         │
       │                         │◄────────────────────────┤
       │                         │  GET /sessions/{id}     │
       │                         │                         │
```

---

## Deployment Architecture

```
Development (Single Machine)
────────────────────────────
┌─────────────────────────────────────┐
│          localhost                  │
│                                     │
│  ┌──────────┐  ┌──────────┐        │
│  │Marketplace│  │ Serving  │        │
│  │  :8001   │  │  :8002   │        │
│  └──────────┘  └──────────┘        │
│                                     │
│  ┌──────────┐  ┌──────────┐        │
│  │ Compute  │  │ Compute  │        │
│  │  :8003   │  │  :8004   │        │
│  └──────────┘  └──────────┘        │
│                                     │
│  data/                              │
│  ├── marketplace/                   │
│  ├── serving/                       │
│  └── compute/                       │
└─────────────────────────────────────┘


Production (Distributed)
────────────────────────
┌─────────────────┐
│ Cloud Instance  │
│  Marketplace    │
│    :8001        │
└────────┬────────┘
         │
         │
┌────────▼────────┐
│ Cloud Instance  │
│    Serving      │
│     :8002       │
│                 │
│  • Load Balanced│
│  • Database     │
│  • Redis Cache  │
└────────┬────────┘
         │
    ┌────┼────┬────────┬────────┐
    │         │        │        │
┌───▼───┐ ┌──▼───┐ ┌──▼───┐ ┌──▼───┐
│Compute│ │Compute│ │Compute│ │Compute│
│ Cloud │ │ Cloud │ │ Edge  │ │ Laptop│
│ :8003 │ │ :8004 │ │ :8005 │ │ :8006 │
└───────┘ └──────┘ └──────┘ └──────┘
```

---

## Scalability Considerations

### Phase 1 (MVP): Single Instance
```
Serving (Single Process)
├── In-memory registry
├── Filesystem storage
├── Direct routing
└── Supports: 10-50 compute instances
```

### Phase 2 (Production): Distributed
```
Serving (Multiple Instances)
├── Shared database (PostgreSQL)
├── Redis for cache/pub-sub
├── Load balancer
├── Session affinity
└── Supports: 100-1000 compute instances
```

### Phase 3 (Enterprise): Highly Scalable
```
Serving (Cluster)
├── Database cluster
├── Redis cluster
├── Message queue (RabbitMQ/Kafka)
├── Service mesh
└── Supports: 1000+ compute instances
```

---

## Security Architecture (Future v0.3.0)

```
┌────────────────────────────────────────┐
│         Authentication Layer           │
│  • API Keys                            │
│  • JWT Tokens                          │
│  • OAuth 2.0                           │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│         Authorization Layer            │
│  • Role-Based Access Control (RBAC)   │
│  • Resource-Based Permissions          │
│  • Org/User Scoping                    │
└───────────────┬────────────────────────┘
                │
┌───────────────▼────────────────────────┐
│              API Layer                 │
│  • Request validation                  │
│  • Rate limiting                       │
│  • Audit logging                       │
└────────────────────────────────────────┘
```

---

## Next Steps

See [SERVING_DESIGN_REVIEW.md](../specifications/SERVING_DESIGN_REVIEW.md) for detailed implementation plan and next steps.

---

**Document Version:** 1.0  
**Last Updated:** November 23, 2025

