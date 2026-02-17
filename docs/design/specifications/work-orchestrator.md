# Work Orchestrator Specification

**Version**: 1.0.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

The Work Orchestrator is the **execution engine** of ClaudeVN v1.0, bridging the gap between work creation (UI/Slim Claude Code) and actual execution by Claude Code compute instances. It is a background service that continuously monitors pending work, orchestrates compute spawning, assigns tasks, and monitors execution health.

**Key Principle**: The orchestrator is the "brain" that ensures work doesn't sit idle - it actively matches tasks with capable compute instances and ensures progress continues until completion.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WORK ORCHESTRATOR                             │
│                      (Background Service)                            │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                     Orchestration Loop                      │    │
│  │                     (5-10s interval)                        │    │
│  │                                                             │    │
│  │  1. Poll PENDING work from Redis                           │    │
│  │  2. Check dependencies are satisfied                       │    │
│  │  3. Select persona via capability matching                 │    │
│  │  4. Spawn Claude Code with persona + git config            │    │
│  │  5. Assign work to spawned compute                         │    │
│  │  6. Monitor health, detect failures                        │    │
│  │  7. Reassign work if compute fails                         │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ WorkMap      │  │ Persona      │  │ Compute                  │  │
│  │ Service      │  │ Service      │  │ Spawner                  │  │
│  │              │  │              │  │                          │  │
│  │ - Query      │  │ - Capability │  │ - Spawn process          │  │
│  │   PENDING    │  │   matching   │  │ - Configure git remote   │  │
│  │ - Assign     │  │ - Load       │  │ - Inject CLAUDE.md       │  │
│  │ - Update     │  │   CLAUDE.md  │  │ - Monitor lifecycle      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         ▲                      ▲                     │
         │                      │                     │
         │ Status               │ Persona             │ Spawn + Context
         │ Updates              │ Definitions         │
         │                      │                     ▼
┌────────┴──────────────────────┴─────────────────────────────────────┐
│                        SUPPORTING SERVICES                           │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Redis        │  │ Git Server   │  │ MCP Server               │  │
│  │              │  │              │  │                          │  │
│  │ - Work queue │  │ - git@serve  │  │ - claudevn_* tools        │  │
│  │ - Compute    │  │   remote     │  │ - Compute reports        │  │
│  │   registry   │  │              │  │   back to Serving        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Purpose

The Work Orchestrator solves a critical coordination problem:

### Problem
- User creates goals/tasks in the UI
- Work sits in PENDING state in Redis
- No mechanism exists to automatically execute this work
- Compute instances need to be spawned with the right context and persona

### Solution
The orchestrator provides:
1. **Active work distribution** - polls PENDING work and ensures execution begins
2. **Intelligent matching** - selects appropriate personas based on required capabilities
3. **Compute lifecycle management** - spawns, configures, monitors Claude Code instances
4. **Resilience** - detects failures and reassigns work automatically
5. **Git topology enforcement** - ensures compute pushes to Serving, not upstream

---

## Git Architecture (CRITICAL)

The orchestrator enforces a **hub-and-spoke Git topology** where Serving is the exclusive bridge to upstream repositories.

### Git Flow

```
┌────────────────────────────────────────────────────────────────────┐
│                      GIT TOPOLOGY                                   │
│                                                                     │
│  Upstream/GitHub                                                    │
│       (Original Repo)                                               │
│            │                                                        │
│            │ fetch/push                                             │
│            ▼                                                        │
│  ┌──────────────────────┐                                          │
│  │  SERVING GIT SERVER  │                                          │
│  │  (Source of Truth)   │                                          │
│  │                      │                                          │
│  │  - Bare repo         │                                          │
│  │  - SSH daemon        │                                          │
│  │  - PR management     │                                          │
│  └──────────────────────┘                                          │
│    ▲        ▲        ▲                                             │
│    │        │        │                                             │
│    │ push   │ push   │ push                                        │
│    │        │        │                                             │
│  ┌─────┐  ┌─────┐  ┌─────┐                                        │
│  │ C-1 │  │ C-2 │  │ C-N │  Compute Instances                     │
│  └─────┘  └─────┘  └─────┘  (Claude Code)                         │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘

Flow:
1. Compute pushes branches to Serving Git Server (NOT upstream)
2. Serving's PR Manager reviews, approves, merges to main
3. Serving (only) pushes merged changes to upstream/GitHub
4. Compute pulls latest main from Serving
```

### Why This Topology?

| Reason | Benefit |
|--------|---------|
| **Centralized control** | Serving enforces PR workflow, prevents direct main pushes |
| **Isolation** | Compute instances can't accidentally push to production |
| **Observability** | All Git activity flows through Serving for monitoring |
| **Security** | Upstream credentials only exist on Serving, not compute |
| **Conflict resolution** | Serving detects conflicts before they reach upstream |

### Orchestrator's Git Configuration Responsibilities

When spawning compute, the orchestrator must:

1. **Set git remote to Serving**
   ```bash
   git remote set-url origin git@serving:/home/git/repos/{project}.git
   ```

2. **Provide SSH key for authentication**
   ```bash
   ssh-keyscan -H serving >> ~/.ssh/known_hosts
   cp /config/compute-001.key ~/.ssh/id_ed25519
   chmod 600 ~/.ssh/id_ed25519
   ```

3. **Configure git user identity**
   ```bash
   git config user.name "Compute-001"
   git config user.email "compute-001@claudevn.local"
   ```

4. **Enforce branch workflow**
   - Compute works on feature branches only
   - Never commits directly to main
   - Pushes to Serving, requests review via MCP

---

## Orchestration Flow

### Main Loop

```python
async def orchestration_loop():
    """
    Main orchestration loop - runs continuously.
    """
    while True:
        try:
            # 1. Query pending work
            pending_tasks = await work_map_service.get_pending_tasks()

            # 2. Filter for ready tasks (dependencies met)
            ready_tasks = [
                task for task in pending_tasks
                if await are_dependencies_satisfied(task)
            ]

            # 3. Process each ready task
            for task in ready_tasks:
                await process_task(task)

            # 4. Monitor active compute instances
            await monitor_active_compute()

            # 5. Check for stale work (no progress in X minutes)
            await detect_and_reassign_stale_work()

        except Exception as e:
            logger.error(f"Orchestration loop error: {e}")
            await alert_on_critical_error(e)

        # 6. Sleep before next iteration
        await asyncio.sleep(10)  # 10 second interval


async def process_task(task: Task):
    """
    Process a single ready task.
    """
    # 1. Select persona based on required capabilities
    persona = await persona_service.select_persona(
        required_capabilities=task.required_capabilities,
        preferred_persona=task.preferred_persona
    )

    if not persona:
        logger.warning(f"No persona found for task {task.id}")
        await work_map_service.update_task_status(
            task.id,
            status="blocked",
            reason="No suitable persona available"
        )
        return

    # 2. Check available compute capacity
    available_compute = await compute_registry.get_available_compute()

    # 3. Spawn new compute instance or reuse idle one
    if available_compute:
        compute = available_compute[0]
        logger.info(f"Reusing idle compute {compute.id}")
    else:
        compute = await compute_spawner.spawn_compute(
            persona=persona,
            project=task.project
        )
        logger.info(f"Spawned new compute {compute.id}")

    # 4. Assign task to compute
    await work_map_service.assign_task(
        task_id=task.id,
        compute_id=compute.id,
        persona_id=persona.id
    )

    # 5. Send context to compute via MCP
    await send_task_context(compute.id, task, persona)

    logger.info(f"Task {task.id} assigned to {compute.id} with persona {persona.id}")
```

### Dependency Resolution

```python
async def are_dependencies_satisfied(task: Task) -> bool:
    """
    Check if all task dependencies are satisfied.
    """
    if not task.depends_on:
        return True  # No dependencies

    for dep_task_id in task.depends_on:
        dep_task = await work_map_service.get_task(dep_task_id)

        if not dep_task:
            logger.warning(f"Dependency task {dep_task_id} not found")
            return False

        if dep_task.status != "completed":
            logger.debug(f"Task {task.id} blocked by {dep_task_id} ({dep_task.status})")
            return False

    return True  # All dependencies completed
```

### Persona Selection Algorithm

```python
async def select_persona(
    required_capabilities: list[str],
    preferred_persona: str = None
) -> Persona:
    """
    Select the best persona for a task.

    Priority:
    1. Preferred persona (if specified and capable)
    2. Exact capability match
    3. Superset capability match (persona has more than required)
    4. None (if no match)
    """
    # Load all personas
    personas = await persona_service.list_personas()

    # Priority 1: Preferred persona
    if preferred_persona:
        persona = next((p for p in personas if p.id == preferred_persona), None)
        if persona and has_capabilities(persona, required_capabilities):
            return persona

    # Priority 2: Exact match
    for persona in personas:
        if set(persona.capabilities) == set(required_capabilities):
            return persona

    # Priority 3: Superset match (persona can do more than required)
    for persona in personas:
        if has_capabilities(persona, required_capabilities):
            return persona

    # No match found
    return None


def has_capabilities(persona: Persona, required: list[str]) -> bool:
    """Check if persona has all required capabilities."""
    return all(cap in persona.capabilities for cap in required)
```

---

## Integration Points

### 1. WorkMapService

**Interface:**
```python
class WorkMapService:
    async def get_pending_tasks(self) -> list[Task]:
        """Get all tasks with status=PENDING."""

    async def assign_task(self, task_id: str, compute_id: str, persona_id: str):
        """Mark task as assigned and update metadata."""

    async def update_task_status(self, task_id: str, status: str, **kwargs):
        """Update task status and metadata."""

    async def get_task(self, task_id: str) -> Task:
        """Get task details."""
```

**Redis Schema:**
```
# Task metadata
task:{project}:{task_id} = {
  id: task-456,
  status: pending|assigned|in_progress|completed|blocked,
  title: "Implement authentication",
  description: "...",
  required_capabilities: ["code_writing", "testing"],
  depends_on: ["task-123", "task-234"],
  assigned_to: null|compute-001,
  persona_used: null|code-writer,
  created_at: "2026-01-25T10:00:00Z",
  assigned_at: null,
  completed_at: null
}

# Task queue (sorted by priority/creation time)
task_queue:{project} = sorted set { task-456: priority_score }

# Dependency tracking
task_deps:{task_id} = set {dep1, dep2, dep3}
```

### 2. PersonaService

**Interface:**
```python
class PersonaService:
    async def list_personas(self) -> list[Persona]:
        """Get all available personas."""

    async def get_persona(self, persona_id: str) -> Persona:
        """Get persona definition."""

    async def select_persona(
        self,
        required_capabilities: list[str],
        preferred_persona: str = None
    ) -> Persona:
        """Select best persona for capabilities."""
```

**Persona Structure:**
```python
@dataclass
class Persona:
    id: str
    name: str
    capabilities: list[str]
    claude_md_content: str
    metadata: dict
```

### 3. ComputeSpawner

**Interface:**
```python
class ComputeSpawner:
    async def spawn_compute(
        self,
        persona: Persona,
        project: str
    ) -> ComputeInstance:
        """
        Spawn a new Claude Code instance.

        Steps:
        1. Generate unique compute ID
        2. Create SSH key pair for Git authentication
        3. Register key with Serving Git server
        4. Create workspace directory
        5. Clone repository with Serving as remote
        6. Configure git user identity
        7. Create worktrees (main + active)
        8. Write persona CLAUDE.md to workspace
        9. Configure MCP client with Serving URL
        10. Start Claude Code process
        11. Register compute in registry
        """

    async def terminate_compute(self, compute_id: str):
        """Gracefully shutdown compute instance."""

    async def get_compute_status(self, compute_id: str) -> ComputeStatus:
        """Query compute health and current work."""
```

**Spawn Process Details:**
```python
async def spawn_compute(self, persona: Persona, project: str) -> ComputeInstance:
    compute_id = f"compute-{uuid4().hex[:8]}"

    # 1. Generate SSH key for Git
    ssh_key_path = f"/keys/{compute_id}"
    subprocess.run([
        "ssh-keygen", "-t", "ed25519",
        "-f", ssh_key_path, "-N", "",
        "-C", compute_id
    ])

    # 2. Register key with Git server
    await git_server.register_compute_key(
        compute_id=compute_id,
        public_key=Path(f"{ssh_key_path}.pub").read_text()
    )

    # 3. Create workspace
    workspace = f"/workspaces/{compute_id}"
    os.makedirs(workspace, exist_ok=True)

    # 4. Clone repository (Serving as origin)
    subprocess.run([
        "git", "clone",
        f"git@serving:/home/git/repos/{project}.git",
        f"{workspace}/repo"
    ], check=True)

    # 5. Configure Git
    subprocess.run([
        "git", "-C", f"{workspace}/repo",
        "config", "user.name", f"Compute-{compute_id}"
    ])
    subprocess.run([
        "git", "-C", f"{workspace}/repo",
        "config", "user.email", f"{compute_id}@claudevn.local"
    ])

    # 6. Create worktrees
    subprocess.run([
        "git", "-C", f"{workspace}/repo",
        "worktree", "add", f"{workspace}/main", "main"
    ])
    subprocess.run([
        "git", "-C", f"{workspace}/repo",
        "worktree", "add", f"{workspace}/active", "-b", f"init-{compute_id}"
    ])

    # 7. Write persona CLAUDE.md
    Path(f"{workspace}/active/CLAUDE.md").write_text(persona.claude_md_content)

    # 8. Configure MCP client
    mcp_config = {
        "mcpServers": {
            "claudevn": {
                "url": f"{SERVING_URL}/mcp",
                "headers": {
                    "Authorization": f"Bearer {generate_api_key(compute_id)}",
                    "X-Compute-ID": compute_id
                }
            }
        }
    }
    Path(f"{workspace}/.claude/config.json").write_text(json.dumps(mcp_config))

    # 9. Start Claude Code process
    process = subprocess.Popen([
        "claude-code",
        "--workspace", f"{workspace}/active",
        "--config", f"{workspace}/.claude/config.json"
    ], env={
        "SSH_KEY_PATH": ssh_key_path,
        "CLAUDEVN_COMPUTE_ID": compute_id
    })

    # 10. Register compute
    compute = ComputeInstance(
        id=compute_id,
        persona_id=persona.id,
        project=project,
        workspace=workspace,
        process_id=process.pid,
        status="idle",
        spawned_at=datetime.utcnow()
    )
    await compute_registry.register(compute)

    return compute
```

### 4. MCP Communication

The orchestrator doesn't directly call MCP tools - compute instances do. However, the orchestrator receives updates:

```python
# Compute calls claudevn_report_progress()
# Orchestrator receives update via Redis pub/sub

async def handle_progress_update(message: dict):
    """
    Handle progress updates from compute instances.
    """
    task_id = message["task_id"]
    status = message["status"]
    progress = message.get("progress_percent", 0)

    # Update work map
    await work_map_service.update_task_status(
        task_id=task_id,
        status=status,
        progress=progress,
        updated_at=datetime.utcnow()
    )

    # If completed, check for newly unblocked tasks
    if status == "completed":
        await check_unblocked_tasks(task_id)
```

---

## Key Design Decisions

### 1. Pull-Based vs Event-Driven

**Decision**: Pull-based (polling)

| Approach | Pros | Cons | Chosen? |
|----------|------|------|---------|
| **Pull-based** | Simple, reliable, predictable load | Slight latency (10s), wastes cycles | ✅ Yes |
| **Event-driven** | Instant response, efficient | Complex, harder to debug, backpressure issues | ❌ No |

**Rationale**: Pull-based is simpler and more reliable. 10-second latency is acceptable for task orchestration. Can always optimize later if needed.

### 2. One Task = One Compute Instance

**Decision**: One-to-one mapping

**Rationale**:
- **Isolation**: Failures in one task don't affect others
- **Parallelism**: Naturally scales by spawning more instances
- **Simplicity**: No complex task queue management per compute
- **Resource usage**: Claude Code instances are lightweight containers

**Alternative considered**: Task queue per compute (rejected due to complexity)

### 3. Stateless Orchestrator

**Decision**: All state in Redis, orchestrator is stateless

**Benefits**:
- Can restart orchestrator without losing work
- Can run multiple orchestrators for redundancy (future)
- Simplifies deployment and recovery

**Implementation**:
```python
# No in-memory state - all state queries go to Redis
pending_tasks = await work_map_service.get_pending_tasks()  # Redis query
compute_status = await compute_registry.get_all()           # Redis query
```

### 4. Graceful Degradation

**Decision**: Continue with degraded service on failures

**Scenarios**:

| Failure | Orchestrator Response |
|---------|----------------------|
| **Compute spawn fails** | Log error, leave task in PENDING, retry next cycle |
| **Persona not found** | Mark task as blocked, alert user |
| **Redis connection lost** | Retry with exponential backoff, alert on extended outage |
| **Git server unreachable** | Queue spawns, resume when available |

---

## Configuration

### Orchestrator Configuration

```yaml
# config/orchestrator.yaml

orchestration:
  poll_interval_seconds: 10          # How often to poll for PENDING work
  max_concurrent_spawns: 5           # Max compute instances to spawn per cycle
  task_timeout_minutes: 60           # Mark task stale after this time
  compute_idle_timeout_minutes: 30   # Terminate idle compute after this time

spawner:
  workspace_root: /workspaces
  ssh_key_dir: /keys
  max_compute_instances: 50          # Hard limit on compute instances
  claude_code_binary: /usr/local/bin/claude-code

git:
  serving_git_host: serving          # Hostname of Serving Git server
  serving_git_port: 22
  serving_git_user: git
  repo_path_template: /home/git/repos/{project}.git

redis:
  host: localhost
  port: 6379
  db: 0
  task_queue_key_template: task_queue:{project}
  compute_registry_key: compute:registry

monitoring:
  health_check_interval_seconds: 30  # How often to check compute health
  stale_work_check_interval_seconds: 60
  alert_webhook_url: https://...      # Webhook for critical alerts
```

### Environment Variables

```bash
# Serving connection
CLAUDEVN_SERVING_URL=http://localhost:8002
CLAUDEVN_GIT_SERVER=serving

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Compute spawning
WORKSPACE_ROOT=/workspaces
SSH_KEY_DIR=/keys
CLAUDE_CODE_BINARY=/usr/local/bin/claude-code

# Monitoring
LOG_LEVEL=INFO
ALERT_WEBHOOK_URL=https://monitoring.example.com/alerts
```

---

## Error Handling Strategy

### Error Categories

| Category | Examples | Response |
|----------|----------|----------|
| **Transient** | Network timeout, temporary resource exhaustion | Retry with exponential backoff |
| **Permanent** | Invalid persona, missing dependencies | Mark task as blocked, alert user |
| **Critical** | Redis down, Git server unreachable | Alert immediately, pause orchestration |

### Retry Logic

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(TransientError)
)
async def spawn_compute_with_retry(persona, project):
    """Spawn compute with automatic retry on transient failures."""
    return await compute_spawner.spawn_compute(persona, project)
```

### Dead Letter Queue

Tasks that repeatedly fail move to a dead letter queue:

```python
async def handle_persistent_failure(task: Task):
    """Handle tasks that fail repeatedly."""
    # Move to DLQ
    await redis.sadd(f"dlq:{task.project}", task.id)
    await redis.hset(f"task:{task.project}:{task.id}", "status", "failed_permanently")

    # Alert
    await send_alert({
        "level": "warning",
        "message": f"Task {task.id} moved to DLQ after {task.retry_count} failures",
        "task": task.dict()
    })
```

---

## Monitoring and Observability

### Metrics

```python
# Prometheus metrics

# Orchestration loop metrics
orchestration_loop_iterations = Counter("orchestration_loop_iterations_total")
orchestration_loop_duration = Histogram("orchestration_loop_duration_seconds")
orchestration_loop_errors = Counter("orchestration_loop_errors_total")

# Task metrics
tasks_processed = Counter("tasks_processed_total", ["status"])
tasks_pending = Gauge("tasks_pending")
tasks_assigned = Gauge("tasks_assigned")
tasks_completed = Counter("tasks_completed_total")
task_duration = Histogram("task_duration_seconds")

# Compute metrics
compute_spawned = Counter("compute_spawned_total")
compute_terminated = Counter("compute_terminated_total")
compute_active = Gauge("compute_active")
compute_spawn_failures = Counter("compute_spawn_failures_total")
compute_spawn_duration = Histogram("compute_spawn_duration_seconds")

# Persona metrics
persona_selection_duration = Histogram("persona_selection_duration_seconds")
persona_not_found = Counter("persona_not_found_total", ["required_capabilities"])
```

### Logging

```python
# Structured logging with context

logger.info(
    "Task assigned",
    extra={
        "task_id": task.id,
        "compute_id": compute.id,
        "persona_id": persona.id,
        "required_capabilities": task.required_capabilities,
        "orchestration_cycle": cycle_id
    }
)

logger.error(
    "Compute spawn failed",
    extra={
        "persona_id": persona.id,
        "project": project,
        "error": str(e),
        "retry_count": retry_count
    },
    exc_info=True
)
```

### Health Checks

```python
async def health_check() -> HealthStatus:
    """
    Check orchestrator health.
    """
    checks = {
        "redis": await check_redis_connection(),
        "git_server": await check_git_server(),
        "mcp_server": await check_mcp_server(),
        "compute_capacity": await check_compute_capacity()
    }

    healthy = all(checks.values())

    return HealthStatus(
        healthy=healthy,
        checks=checks,
        timestamp=datetime.utcnow()
    )
```

### Dashboard Widgets

```
┌─────────────────────────────────────────────────────────────┐
│ Work Orchestrator Dashboard                                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Status: ✅ Healthy                                          │
│  Uptime: 3d 4h 12m                                           │
│                                                              │
│  Tasks                                                       │
│  ├─ Pending:     12                                          │
│  ├─ Assigned:    8                                           │
│  ├─ In Progress: 8                                           │
│  └─ Completed:   142 (last 24h)                              │
│                                                              │
│  Compute Instances                                           │
│  ├─ Active:      8 / 50                                      │
│  ├─ Idle:        2                                           │
│  └─ Spawning:    1                                           │
│                                                              │
│  Recent Activity                                             │
│  ├─ 10:32:15  compute-7a3f assigned task-789 (code-writer)  │
│  ├─ 10:32:08  compute-2b1c completed task-756               │
│  └─ 10:31:59  compute-9d4e spawned (debugger)               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Failure Scenarios and Recovery

### Scenario 1: Compute Instance Crashes

**Detection**:
```python
async def monitor_active_compute():
    """Check health of active compute instances."""
    active_compute = await compute_registry.get_active()

    for compute in active_compute:
        # Check if process is still running
        if not is_process_alive(compute.process_id):
            await handle_compute_crash(compute)
```

**Recovery**:
```python
async def handle_compute_crash(compute: ComputeInstance):
    logger.error(f"Compute {compute.id} crashed")

    # 1. Mark compute as failed
    await compute_registry.update_status(compute.id, "crashed")

    # 2. Get task assigned to this compute
    task = await work_map_service.get_task_by_compute(compute.id)

    if task:
        # 3. Unassign task, mark as PENDING
        await work_map_service.unassign_task(task.id)

        # 4. Task will be picked up in next orchestration cycle
        logger.info(f"Task {task.id} reassigned after compute crash")
```

### Scenario 2: Git Server Unreachable

**Detection**: Spawn failures with Git connection errors

**Recovery**:
```python
async def handle_git_server_unreachable():
    logger.error("Git server unreachable, pausing spawns")

    # 1. Set orchestrator to degraded mode
    orchestrator_state.git_server_available = False

    # 2. Stop spawning new compute
    # (existing compute may continue working)

    # 3. Retry Git server connection every 30 seconds
    while not orchestrator_state.git_server_available:
        await asyncio.sleep(30)
        if await check_git_server():
            orchestrator_state.git_server_available = True
            logger.info("Git server recovered, resuming spawns")
```

### Scenario 3: Stale Work (No Progress)

**Detection**:
```python
async def detect_and_reassign_stale_work():
    """Find tasks with no progress updates in N minutes."""
    stale_threshold = datetime.utcnow() - timedelta(minutes=60)

    stale_tasks = await work_map_service.get_tasks_updated_before(stale_threshold)

    for task in stale_tasks:
        if task.status == "in_progress":
            logger.warning(f"Task {task.id} is stale (no updates since {task.updated_at})")
            await handle_stale_task(task)
```

**Recovery**:
```python
async def handle_stale_task(task: Task):
    compute = await compute_registry.get(task.assigned_to)

    # 1. Check if compute is still alive
    if not is_process_alive(compute.process_id):
        # Compute crashed but we didn't detect it
        await handle_compute_crash(compute)
        return

    # 2. Try to ping compute via MCP
    try:
        status = await mcp_client.get_compute_status(compute.id)
        logger.info(f"Compute {compute.id} is alive but making no progress")
        # Could send a nudge or request cancellation
    except Exception:
        # Compute is unresponsive
        logger.error(f"Compute {compute.id} unresponsive, terminating")
        await compute_spawner.terminate_compute(compute.id)
        await work_map_service.unassign_task(task.id)
```

---

## Future Considerations

### 1. Priority Queues

Currently tasks are processed FIFO. Future enhancement:

```python
# Add priority field to tasks
task = {
    "id": "task-123",
    "priority": 10,  # Higher = more important
    ...
}

# Use sorted set for priority queue
await redis.zadd(f"task_queue:{project}", {task.id: -task.priority})
```

### 2. Compute Pooling

Reuse idle compute instances instead of terminating:

```python
async def get_or_spawn_compute(persona: Persona) -> ComputeInstance:
    # Check for idle compute with matching persona
    idle = await compute_registry.get_idle_by_persona(persona.id)

    if idle:
        logger.info(f"Reusing idle compute {idle.id}")
        return idle

    # Spawn new if none available
    return await compute_spawner.spawn_compute(persona)
```

### 3. Multi-Orchestrator (HA)

Run multiple orchestrators with leader election:

```python
# Use Redis for leader election
leader_key = "orchestrator:leader"
leader = await redis.set(leader_key, orchestrator_id, nx=True, ex=30)

if leader:
    # This orchestrator is the leader
    await orchestration_loop()
else:
    # Standby mode - only monitor, don't spawn
    await standby_mode()
```

### 4. Smart Scheduling

Consider compute load when assigning:

```python
async def select_compute(task: Task) -> ComputeInstance:
    candidates = await compute_registry.get_idle_or_low_load()

    # Prefer compute with:
    # 1. Same persona (avoid context switch)
    # 2. Recent activity on related files
    # 3. Lower memory usage

    return best_candidate
```

### 5. Batch Assignment

Assign multiple related tasks to same compute:

```python
async def batch_assign_tasks(tasks: list[Task]) -> dict:
    # Group by similarity (same files, same persona)
    task_groups = group_related_tasks(tasks)

    assignments = {}
    for group in task_groups:
        compute = await get_or_spawn_compute(group.persona)
        for task in group.tasks:
            assignments[task.id] = compute.id

    return assignments
```

---

## File Structure

```
serving/
├── orchestration/
│   ├── __init__.py
│   ├── orchestrator.py           # Main orchestration loop
│   ├── config.py                 # Configuration
│   ├── work_map_service.py       # WorkMap interface
│   ├── persona_service.py        # Persona selection
│   ├── compute_spawner.py        # Spawn Claude Code instances
│   ├── compute_registry.py       # Track active compute
│   ├── health_monitor.py         # Health checks and monitoring
│   ├── failure_handler.py        # Error handling and recovery
│   └── metrics.py                # Prometheus metrics
├── models/
│   ├── task.py                   # Task data models
│   ├── compute.py                # Compute instance models
│   └── persona.py                # Persona models
└── tests/
    ├── test_orchestrator.py
    ├── test_spawner.py
    └── test_recovery.py
```

---

## Related Documents

- [v1.0 Architecture](../architecture/v1.0-architecture.md)
- [Git Infrastructure Design](./git-infrastructure.md)
- [MCP Tools Specification](./mcp-tools.md)
- [Persona Marketplace Specification](./persona-marketplace.md)
- [Worktree Workflow Guide](../../guides/worktree-workflow.md)
