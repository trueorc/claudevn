# Serving Component - Quick Reference

**Version:** 0.2.0 (Planned)  
**Status:** Design Phase  

---

## What is the Serving Component?

The **Serving Component** is the central orchestration hub of ClaudeVN that:
- Acts as a **registry** for compute engines (creates virtual compute pool)
- Acts as a **proxy** for marketplace connections (agent discovery)
- Acts as a **router** for A2A protocol messages (inter-instance communication)
- Acts as a **coordinator** for session management (execution tracking)

---

## Key Concepts

### Compute Registration
Multiple compute engines register with serving to form a **virtual compute resource**:
```
Compute A (laptop)  ─┐
Compute B (cloud)   ─┼─> Serving Component (Registry)
Compute C (edge)    ─┘     │
                           └─> "Virtual Compute Pool"
                               Combined capabilities
```

### Marketplace Proxy
Serving connects to one or more marketplaces and proxies agent discovery:
```
User Request ─> Serving ─┬─> Marketplace 1
                         ├─> Marketplace 2
                         └─> Marketplace 3
                         
Serving ─> [Merge, Deduplicate] ─> User
```

### A2A Protocol
Serving routes messages between compute instances using A2A protocol:
```
Compute A: "Need help from data-analyst agent"
    │
    ▼
Serving: "data-analyst is on Compute B"
    │
    ▼
Compute B: "Task received, executing..."
    │
    ▼
Serving: "Store result in session"
    │
    ▼
Compute A: "Task completed, got result"
```

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────┐
│                    SERVING COMPONENT                    │
│                      (Port 8002)                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Compute    │  │  Marketplace │  │     A2A      │ │
│  │   Registry   │  │    Proxy     │  │    Router    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │          Session Coordinator                     │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │          Storage Layer (Filesystem/DB)           │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
           │                │                │
           ▼                ▼                ▼
    Compute Engines    Marketplaces      Frontend UI
```

---

## API Overview

### Compute Registry API
```
POST   /api/v1/compute/register         Register compute instance
GET    /api/v1/compute                  List all registered instances
GET    /api/v1/compute/{id}             Get instance details
DELETE /api/v1/compute/{id}             Deregister instance
GET    /api/v1/compute/capabilities     Get aggregated capabilities
```

### Marketplace API
```
POST   /api/v1/marketplaces/connect     Connect to marketplace
GET    /api/v1/marketplaces             List connected marketplaces
GET    /api/v1/marketplaces/{id}/agents Search agents in marketplace
```

### A2A Protocol API
```
GET    /a2a/agents                      List all available agents
POST   /a2a/tasks                       Submit task to agent
GET    /a2a/tasks/{id}                  Get task status
GET    /a2a/tasks/{id}/stream           Stream task updates (SSE)
```

### Session Management API
```
POST   /api/v1/sessions                 Create session
GET    /api/v1/sessions                 List sessions
GET    /api/v1/sessions/{id}            Get session details
```

---

## Data Flow Examples

### Example 1: Register Compute Instance

```
1. Compute Instance starts up
   ↓
2. POST /api/v1/compute/register
   {
     "instance_id": "compute-laptop-001",
     "endpoint": "http://localhost:8003",
     "capabilities": ["python-agent", "data-analysis"]
   }
   ↓
3. Serving validates and stores
   ↓
4. Serving starts health monitoring
   ↓
5. Response: 201 Created
   {
     "status": "registered",
     "instance_id": "compute-laptop-001",
     "heartbeat_interval": 30
   }
   ↓
6. Compute sends heartbeat every 30s
```

### Example 2: Search for Agent Across Marketplaces

```
1. User searches for "data analyst"
   ↓
2. POST /a2a/agents/search
   { "query": "data analyst" }
   ↓
3. Serving queries all connected marketplaces
   ├─> Marketplace A: 3 results
   ├─> Marketplace B: 2 results
   └─> Marketplace C: (timeout, skip)
   ↓
4. Serving merges and deduplicates
   ↓
5. Response: 4 unique agents
   [
     { agent_id: "data-analyst-pro", source: "marketplace-a" },
     { agent_id: "data-scientist", source: "marketplace-a" },
     { agent_id: "analyst-expert", source: "marketplace-b" },
     { agent_id: "data-viz-agent", source: "marketplace-b" }
   ]
```

### Example 3: Route Task to Compute Instance

```
1. Coordinating agent needs specialized agent
   ↓
2. POST /a2a/tasks
   {
     "agent_id": "data-analyst-pro",
     "input": { "dataset": "sales_q4.csv", "goal": "analyze" }
   }
   ↓
3. Serving finds which compute has "data-analyst-pro"
   └─> compute-laptop-001
   ↓
4. Serving forwards task to compute-laptop-001
   ↓
5. Serving returns task_id: "task-abc123"
   ↓
6. Compute executes task
   ↓
7. Compute sends updates via callback
   ↓
8. Serving stores updates in session
   ↓
9. Client can GET /a2a/tasks/task-abc123
   or stream GET /a2a/tasks/task-abc123/stream
```

---

## Storage Structure

```
data/serving/
├── registry/
│   ├── compute/
│   │   ├── compute-laptop-001.json
│   │   ├── compute-cloud-002.json
│   │   └── index.json
│   └── marketplaces/
│       ├── marketplace-corp.json
│       ├── marketplace-public.json
│       └── index.json
├── sessions/
│   ├── session-001.json
│   └── session-002.json
├── tasks/
│   ├── task-abc123.json
│   └── task-def456.json
└── blobs/
    └── {session_id}/
        └── {blob_id}
```

---

## Configuration

```bash
# Server
SERVING_HOST=0.0.0.0
SERVING_PORT=8002

# Storage
STORAGE_BACKEND=filesystem
STORAGE_PATH=./data/serving

# Registry
HEALTH_CHECK_INTERVAL=30
MAX_FAILED_CHECKS=3

# Marketplace
MARKETPLACE_CACHE_TTL=300
MAX_MARKETPLACES=10

# A2A
A2A_TASK_TIMEOUT=300
SSE_KEEPALIVE=30

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/serving.log
```

---

## Common Workflows

### Workflow 1: Start Serving Component
```bash
cd serving
./start.sh

# Component will:
# 1. Check port 8002
# 2. Install dependencies
# 3. Build frontend
# 4. Start FastAPI server
# 5. Initialize storage
# 6. Start health monitor
# 7. Show UI at http://localhost:8002
```

### Workflow 2: Register Compute Instance (from Compute)
```python
import httpx

# Register with serving
response = httpx.post(
    "http://localhost:8002/api/v1/compute/register",
    json={
        "instance_id": "my-compute-001",
        "endpoint": "http://localhost:8003",
        "health_endpoint": "http://localhost:8003/health",
        "capabilities": {
            "agents": ["content-writer", "code-reviewer"],
            "tools": ["python-executor", "file-reader"],
            "resources": {"cpu": 4, "memory_gb": 16}
        },
        "metadata": {
            "name": "My Local Compute",
            "location": "laptop",
            "owner": "user@example.com"
        }
    }
)

# Start heartbeat loop
heartbeat_interval = response.json()["heartbeat_interval"]
while True:
    time.sleep(heartbeat_interval)
    httpx.post(f"http://localhost:8002/api/v1/compute/my-compute-001/health")
```

### Workflow 3: Connect to Marketplace (from UI)
```
1. Open http://localhost:8002
2. Navigate to "Marketplaces" tab
3. Click "Connect New Marketplace"
4. Fill in:
   - Name: Corporate Marketplace
   - URL: http://localhost:8001
   - Priority: 1 (higher = more priority)
5. Click "Test Connection"
6. Click "Connect"
7. Marketplace appears in list
8. Can now search agents from this marketplace
```

### Workflow 4: Monitor Sessions
```
1. Open http://localhost:8002
2. Navigate to "Sessions" tab
3. View list of active/completed sessions
4. Click on session to see:
   - Execution plan
   - Task results
   - Data references
   - Timeline
   - Status
5. Can filter by status, search by ID
```

---

## Integration Points

### With Marketplace
```
Serving ←→ Marketplace
  
Serving calls:
- GET /api/v1/agents (list agents)
- GET /api/v1/agents/{id} (get agent details)
- POST /api/v1/agents/search (search agents)
- GET /api/v1/users (future: sync users)
- GET /api/v1/organizations (future: sync orgs)
```

### With Compute
```
Serving ←→ Compute

Serving calls:
- POST /a2a/tasks (forward task)
- GET /health (health check)

Compute calls:
- POST /api/v1/compute/register (register)
- POST /api/v1/compute/{id}/health (heartbeat)
- POST /a2a/tasks (submit task)
- GET /a2a/agents (discover agents)
```

---

## UI Screens

### Dashboard
- System health overview
- Registered compute instances (count, status)
- Connected marketplaces (count, status)
- Active sessions (count, status)
- Quick actions

### Compute Registry
- Table of registered instances
- Columns: ID, Name, Status, Capabilities, Last Heartbeat
- Actions: View, Health Check, Deregister
- Register new instance form

### Marketplace Connections
- Cards for each marketplace
- Status indicators
- Agent count
- Test connection button
- Connect new marketplace form

### Session Monitor
- List of sessions
- Status breakdown
- Session details modal
- Execution plan visualization
- Task results

---

## Key Metrics

### Health Metrics
- Serving uptime
- API response time
- Storage usage
- Active connections

### Registry Metrics
- Total compute instances
- Online/offline count
- Total capabilities
- Failed health checks

### Marketplace Metrics
- Connected marketplaces
- Total agents available
- Search query count
- Cache hit rate

### Session Metrics
- Active sessions
- Completed sessions
- Failed sessions
- Average session duration

---

## Troubleshooting

### Compute instance not showing up
```
1. Check compute is running: ./compute/status.sh
2. Check compute can reach serving: curl http://localhost:8002/api/v1/health
3. Check registration request: curl http://localhost:8002/api/v1/compute
4. Check logs: tail -f logs/serving.log
5. Check heartbeat is being sent
```

### Marketplace connection fails
```
1. Check marketplace is running: curl http://localhost:8001/api/v1/health
2. Check URL in serving config
3. Test connection from serving host
4. Check firewall/network
5. Check logs: tail -f logs/serving.log
```

### Task not routing
```
1. Check agent exists: GET /a2a/agents
2. Check compute instance has agent: GET /api/v1/compute/{id}
3. Check compute instance is online
4. Check task submission format
5. Check logs: tail -f logs/serving.log
```

---

## Next Steps

1. **Review** [Implementation Plan](./serving-implementation-plan.md)
2. **Track Progress** with [Implementation Checklist](./serving-implementation-checklist.md)
3. **Understand Architecture** in [Platform Overview](../architecture/platform-overview.md)
4. **Start Building** Phase 1: Compute Registration

---

## Links

- [Full Implementation Plan](./serving-implementation-plan.md)
- [Implementation Checklist](./serving-implementation-checklist.md)
- [Platform Overview](../architecture/platform-overview.md)
- [Technical Specifications](./technical-specifications.md)
- [A2A Protocol Reference](https://github.com/google/A2A) (external)

---

**Quick Reference Version:** 1.0  
**Last Updated:** 2025-11-23

