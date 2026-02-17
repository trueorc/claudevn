# Compute Infrastructure Registration

**Version**: 1.0.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

This document specifies how Compute Infrastructure (Docker containers) register with and communicate with the Serving component. The registration model uses Server-Sent Events (SSE) for persistent, event-driven communication.

---

## Component Lifetimes

| Component | Lifetime | Started By |
|-----------|----------|------------|
| **Serving** | Long-lived | Operator (central hub) |
| **Marketplace** | Long-lived | Operator (skill catalog) |
| **Compute Infra** | Long-lived | Anyone, anywhere (Docker container) |
| **Claude Code Instance** | Short-lived (per task) | Serving (spawned on Compute Infra) |

**Key distinction:**
- **Compute Infra** = Docker container with resources, no knowledge of work
- **Claude Code Instance** = Task executor spawned by Serving with skills and assignment

---

## Registration Flow

### 1. Compute Infra Startup

```
Operator/User : starts Docker container : Compute Infra
Compute Infra : reads configuration (Serving URL, capabilities) : itself
Compute Infra : opens SSE connection to /api/v1/compute/connect : Serving
Serving : validates connection, stores in ComputeRegistry : itself
```

### 2. Connection as Health Signal

The SSE connection itself indicates health:
- **Connection open** = Compute Infra is alive and registered
- **Connection closed** = Compute Infra is offline, remove from registry

No polling or heartbeat requests needed. A 30-second keepalive pulse maintains the connection through proxies/firewalls.

### 3. Work Assignment (Notification + Fetch)

```
Serving : receives work request : WorkMapService
Serving : pushes lightweight work_assigned SSE event : Compute Infra
Compute Infra : calls claudevn_get_assignment(task_id) : Serving
Serving : selects skills from Marketplace, composes CLAUDE.md : itself
Serving : returns full assignment (skills, context, branch) : Compute Infra
Compute Infra : spawns Claude Code with skills + assignment : Claude Code
Claude Code : executes task using MCP tools : itself
Claude Code : completes and exits : itself
Compute Infra : sends claude_code_completed via HTTP : Serving
```

**Why Notification + Fetch?**
- SSE payloads stay lightweight and reliable
- Compute Infra fetches details when ready to work
- Skills can be large; better to fetch on-demand
- Decouples SSE event schema from assignment schema

### 4. Disconnection

```
Compute Infra : closes SSE connection (graceful shutdown) : Serving
  OR
SSE connection : drops unexpectedly : Serving detects
Serving : removes from ComputeRegistry : itself
Serving : reassigns incomplete work if needed : WorkMapService
```

---

## SSE Connection

### Endpoint

```
GET /api/v1/compute/connect
```

### Headers

```http
Authorization: Bearer <compute_api_key>
X-Compute-ID: compute-001
X-Capabilities: coding,testing,documentation
X-Resources: cpu=4,memory=16gb
```

### Connection Response

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

---

## Events (Serving → Compute Infra)

Events are pushed from Serving to Compute Infra over the SSE connection.

### work_assigned

Serving notifies Compute Infra that work is available. This is a **lightweight notification** - Compute Infra must call `claudevn_get_assignment` via MCP to fetch full details.

```json
event: work_assigned
data: {
  "task_id": "task-456",
  "title": "Implement user authentication",
  "priority": "normal"
}
```

**Notification + Fetch Pattern:**
1. Compute Infra receives this lightweight SSE event
2. Compute Infra calls `claudevn_get_assignment(task_id="task-456")` via MCP
3. Serving returns full assignment: skills, context, branch, MCP config
4. Compute Infra spawns Claude Code with complete assignment

See [MCP Tools Specification](./mcp-tools.md) for `claudevn_get_assignment` details.

### work_cancelled

Serving cancels currently assigned work.

```json
event: work_cancelled
data: {
  "task_id": "task-456",
  "reason": "Higher priority work assigned",
  "action": "stop_gracefully"
}
```

### shutdown

Serving requests graceful shutdown.

```json
event: shutdown
data: {
  "reason": "Maintenance window",
  "grace_period_seconds": 60
}
```

### merge_conflict

Serving detected conflicts when attempting to merge branch to main. Compute must resolve and re-push.

```json
event: merge_conflict
data: {
  "issue_id": "issue-100",
  "branch": "f/issue-100/compute-001",
  "conflicting_files": [
    "src/models/user.py",
    "src/api/auth.py"
  ],
  "main_head": "abc123def",
  "message": "Resolve conflicts with main and push again"
}
```

**Compute response:**
1. Fetch latest main
2. Rebase branch onto main
3. Resolve conflicts in indicated files
4. Force push branch
5. Call `claudevn_report_progress(status="conflicts_resolved")`

### work_completed

Serving confirms work was merged successfully.

```json
event: work_completed
data: {
  "issue_id": "issue-100",
  "branch": "f/issue-100/compute-001",
  "merge_commit": "def456abc",
  "merged_at": "2026-01-30T10:30:00Z"
}
```

### keepalive

Periodic pulse to maintain connection (every 30 seconds).

```json
event: keepalive
data: {"timestamp": "2026-01-30T10:00:00Z"}
```

---

## Events (Compute Infra → Serving)

Compute Infra sends events to Serving via HTTP POST (not over SSE).

### Endpoint

```
POST /api/v1/compute/events
```

### claude_code_started

Claude Code instance has been spawned.

```json
{
  "event": "claude_code_started",
  "compute_id": "compute-001",
  "task_id": "task-456",
  "instance_id": "cc-789",
  "timestamp": "2026-01-30T10:01:00Z"
}
```

### claude_code_completed

Claude Code instance finished and exited.

```json
{
  "event": "claude_code_completed",
  "compute_id": "compute-001",
  "task_id": "task-456",
  "instance_id": "cc-789",
  "exit_code": 0,
  "duration_seconds": 300,
  "timestamp": "2026-01-30T10:06:00Z"
}
```

### claude_code_failed

Claude Code instance encountered an error.

```json
{
  "event": "claude_code_failed",
  "compute_id": "compute-001",
  "task_id": "task-456",
  "instance_id": "cc-789",
  "error": "Process killed - out of memory",
  "exit_code": 137,
  "timestamp": "2026-01-30T10:05:00Z"
}
```

---

## Compute Infra Configuration

### Environment Variables

```bash
CLAUDEVN_SERVING_URL=http://serving:8002
CLAUDEVN_COMPUTE_ID=compute-001
CLAUDEVN_API_KEY=troc_abc123...
CLAUDEVN_CAPABILITIES=coding,testing,documentation
CLAUDEVN_RESOURCES_CPU=4
CLAUDEVN_RESOURCES_MEMORY=16gb
```

### Docker Compose Example

```yaml
services:
  compute:
    image: claudevn/compute-infra:1.0
    environment:
      - CLAUDEVN_SERVING_URL=http://serving:8002
      - CLAUDEVN_COMPUTE_ID=compute-${HOSTNAME}
      - CLAUDEVN_API_KEY=${COMPUTE_API_KEY}
      - CLAUDEVN_CAPABILITIES=coding,testing
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 16G
```

---

## ComputeRegistry (Serving Side)

Serving maintains a registry of connected Compute Infra instances.

### Registry Entry

```python
@dataclass
class ComputeEntry:
    compute_id: str
    capabilities: list[str]
    resources: dict[str, Any]
    connected_at: datetime
    sse_connection: SSEConnection
    current_task_id: Optional[str] = None
    status: str = "idle"  # idle, busy, draining
```

### Operations

| Operation | Trigger |
|-----------|---------|
| **Add** | SSE connection opened |
| **Update** | Work assigned/completed |
| **Remove** | SSE connection closed |

---

## Failure Handling

### Connection Drop

```
SSE connection drops : Serving detects immediately
Serving : removes Compute from registry : ComputeRegistry
Serving : checks if Compute had active work : WorkMapService
Serving : marks work as FAILED or reassigns : WorkMapService
```

### Claude Code Crash

```
Claude Code : crashes unexpectedly : Compute Infra detects
Compute Infra : sends claude_code_failed event : Serving
Serving : marks task as FAILED : WorkMapService
Serving : may reassign to another Compute : WorkOrchestrator
```

### Graceful Shutdown

```
Compute Infra : receives SIGTERM : itself
Compute Infra : waits for Claude Code to finish (grace period) : itself
Compute Infra : closes SSE connection : Serving
Serving : removes from registry : ComputeRegistry
```

---

## Security

### Authentication

- Compute Infra authenticates with API key on SSE connection
- API key scoped to specific compute_id
- Serving validates key before accepting connection

### Authorization

- Compute Infra can only receive work matching its capabilities
- Task-scoped MCP keys issued per work assignment
- Compute cannot access other compute's work

---

## Spawner Architecture

ClaudeVN provides two Claude Code spawner implementations for different deployment models.

### Deployment Models

| Model | Spawner Location | Use Case |
|-------|------------------|----------|
| **Centralized** | Serving (`serving/services/compute_spawner.py`) | Development, single-host |
| **Distributed** | Compute Container (`compute/services/claude_code_spawner.py`) | Production, scale-out fleet |

### Centralized Model (Serving-side Spawner)

```
Serving (with ComputeSpawner)
    │
    ├── API: POST /api/v1/spawner/spawn
    │
    └── Spawns Claude Code directly on Serving host
        │
        └── Claude Code uses MCP to communicate with Serving
```

**Characteristics:**
- Spawning triggered by API call
- Direct marketplace access for skill composition
- Issues API keys for instances
- Manages instance lifecycle locally
- Best for: development, testing, simple deployments

### Distributed Model (Compute-side Spawner)

```
Serving (SSE push only)
    │
    └── SSE: work_assigned event
        │
        ▼
Compute Infrastructure (Docker container)
    │
    └── ClaudeCodeSpawner spawns Claude Code
        │
        └── Claude Code uses MCP to communicate with Serving
```

**Characteristics:**
- Spawning triggered by SSE `work_assigned` event
- Skills fetched via MCP `claudevn_get_assignment`
- API key received in assignment
- Reports lifecycle events to Serving via HTTP
- Best for: production, distributed compute fleet, scale-out

### Choosing a Model

| Consideration | Centralized | Distributed |
|---------------|-------------|-------------|
| Container infra needed | No | Yes |
| Horizontal scaling | Limited | Yes |
| Resource isolation | No | Yes |
| Network complexity | Simple | SSE + HTTP |
| Development setup | Easy | Requires containers |

See [ADR-005](../adr/005-dual-spawner-architecture.md) for architectural rationale.

---

## Related Documents

- [MCP Tools Specification](./mcp-tools.md) - Claude Code ↔ Serving communication
- [v1.0 Architecture](../architecture/v1.0-architecture.md) - System overview
- [WorkMap Specification](./workmap.md) - Work distribution and dependency tracking
- [ADR-005: Dual Spawner Architecture](../adr/005-dual-spawner-architecture.md) - Spawner design decision
