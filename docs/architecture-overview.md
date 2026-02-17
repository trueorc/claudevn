# ClaudeVN Architecture Overview

**Version:** 1.0.0
**Last Updated:** February 2026

---

## What is ClaudeVN?

ClaudeVN is a platform for coordinating AI agents to accomplish complex work. It enables teams to define high-level goals and watch specialized AI workers collaborate to achieve them. Each worker is a Claude Code instance with specific skills, working autonomously while staying synchronized through Git and structured communication.

Think of it as a project management system where the workers are AI agents, communication happens through APIs and version control, and progress is tracked in real-time.

---

## System Architecture

ClaudeVN uses a two-tier architecture: a central coordination hub (Serving) and distributed compute workers (Claude Code instances).

```
┌─────────────────────────────────────────────────────────────────────┐
│                           SERVING                                    │
│                      (Central Coordination Hub)                      │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ Skill          │  │ MCP Server     │  │ Slim Claude Code       │ │
│  │ Marketplace    │  │ (External)     │  │ (Intent Orchestration) │ │
│  │                │  │                │  │                        │ │
│  │ - Skill defs   │  │ - Task assign  │  │ - Parse user intent    │ │
│  │ - Composition  │  │ - Progress rpt │  │ - Route to workers     │ │
│  │ - Selection    │  │ - Git ops      │  │ - Synthesize results   │ │
│  └────────────────┘  └────────────────┘  └────────────────────────┘ │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐ │
│  │ Work Map       │  │ Compute        │  │ Monitoring UI          │ │
│  │ (Dynamic)      │  │ Registry       │  │ (WebSocket)            │ │
│  │                │  │                │  │                        │ │
│  │ - Task queue   │  │ - Instance     │  │ - Real-time status     │ │
│  │ - Assignments  │  │   tracking     │  │ - Branch activity      │ │
│  │ - Dependencies │  │ - Health check │  │ - Work progress        │ │
│  └────────────────┘  └────────────────┘  └────────────────────────┘ │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   Git Infrastructure                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │   │
│  │  │ SSH Server  │  │ Bare Repos  │  │ Redis PR Queue      │   │   │
│  │  │ (Auth)      │  │ (Truth)     │  │ (Merge Mgmt)        │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
         │ Spawn + Context        │ MCP Calls           │ Git (SSH)
         ▼                        ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        COMPUTE INSTANCES                             │
│                       (Claude Code Workers)                          │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ Compute 1       │  │ Compute 2       │  │ Compute N       │      │
│  │                 │  │                 │  │                 │      │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │      │
│  │ │Claude Code  │ │  │ │Claude Code  │ │  │ │Claude Code  │ │      │
│  │ │+ Composed   │ │  │ │+ Composed   │ │  │ │+ Composed   │ │      │
│  │ │  Agent      │ │  │ │  Agent      │ │  │ │  Agent      │ │      │
│  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │      │
│  │                 │  │                 │  │                 │      │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │      │
│  │ │ MCP Client  │ │  │ │ MCP Client  │ │  │ │ MCP Client  │ │      │
│  │ │ (to Serving)│ │  │ │ (to Serving)│ │  │ │ (to Serving)│ │      │
│  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │      │
│  │                 │  │                 │  │                 │      │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │      │
│  │ │ Git Repo    │ │  │ │ Git Repo    │ │  │ │ Git Repo    │ │      │
│  │ │ (Clone)     │ │  │ │ (Clone)     │ │  │ │ (Clone)     │ │      │
│  │ │ - branch    │ │  │ │ - branch    │ │  │ │ - branch    │ │      │
│  │ │             │ │  │ │             │ │  │ │             │ │      │
│  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │      │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Coordination Hub (Serving)

**Port:** 8002

The central server that coordinates all work. One Serving instance runs per project and handles:

- **Goal Decomposition**: Breaks user goals into actionable tasks
- **Work Distribution**: Assigns tasks to available compute instances
- **State Management**: Hosts the source-of-truth Git repository
- **Agent Composition**: Selects and combines skills into specialized agents
- **Progress Monitoring**: Real-time tracking via WebSocket dashboard
- **Code Review**: Manages pull request queue and merges approved work

**Key principle:** Only Serving can merge to the main branch. This ensures all work goes through proper review and conflict resolution.

### 2. Compute Instances (Workers)

Claude Code instances that execute assigned work autonomously. Each instance:

- Runs the full Claude Code CLI environment
- Has a Git clone of the project repository
- Works on a dedicated feature branch
- Communicates progress via MCP (Model Context Protocol) tools
- Handles one primary task at a time

**Example workflow:**
1. Receives task assignment notification
2. Fetches full assignment details (task description, composed agent, context)
3. Creates feature branch from main
4. Works autonomously using Claude Code's capabilities
5. Reports progress periodically
6. Pushes completed work and requests review
7. Serving reviews, approves, and merges to main

### 3. Skill Marketplace

**Port:** 8003

A separate service that manages the skill catalog. Skills are atomic capability units that define what an agent can do.

**Skill structure:**
```markdown
# {Skill Name}

## Instructions
{What this skill enables the agent to do}

## Capabilities
- {Capability 1}
- {Capability 2}

## Constraints
- {Constraint 1}
- {Constraint 2}
```

Skills are composed into agents on-demand based on task requirements. For example:

| Task Type | Skills Composed |
|-----------|----------------|
| Implement feature | `code-implementation`, `test-creation`, `documentation` |
| Fix bug | `bug-investigation`, `code-implementation`, `test-creation` |
| Write docs | `documentation`, `code-analysis` |

---

## Communication Patterns

### 1. Server-Sent Events (Serving → Compute)

Serving pushes lightweight notifications to compute instances:

```
Serving: "New task available: task-123"
Compute: (calls MCP to fetch full details)
```

**Why SSE?** Compute instances may be behind NAT or firewalls. Serving cannot directly call them, so it pushes notifications and compute pulls when ready.

### 2. MCP Tools (Compute → Serving)

Compute instances use MCP (Model Context Protocol) tools to communicate with Serving:

| Tool | Purpose |
|------|---------|
| `claudevn_get_assignment` | Fetch task details after SSE notification |
| `claudevn_report_progress` | Update task status (started, blocked, progress %) |
| `claudevn_request_review` | Signal work ready for review |
| `claudevn_get_context` | Fetch relevant project context |
| `claudevn_signal_blocker` | Report blockers or dependencies |
| `claudevn_complete_task` | Mark task complete, request merge |
| `claudevn_add_requirement` | Add discovered work items to backlog |

### 3. Git (Bidirectional)

All file-based state flows through Git:

- Compute pulls latest main before starting work
- Compute pushes feature branches when ready
- Serving merges approved branches to main
- Git hooks trigger events on push (update PR queue)

**SSH authentication:** Each compute instance has its own SSH key for secure Git access.

---

## Work Flow

Here's how work flows through the system:

```
1. User defines a goal
   "Implement user authentication with email/password"

2. Serving's Claude Code analyzes and decomposes goal
   - Task 1: Design auth schema
   - Task 2: Implement login endpoint
   - Task 3: Add password hashing
   - Task 4: Write tests
   - Task 5: Update documentation

3. Serving updates Work Map with tasks and dependencies
   Task 2 blocked by Task 1
   Task 3 blocked by Task 2
   Task 4 blocked by Tasks 2 & 3

4. Serving assigns Task 1 to available compute
   - Selects skills: code-implementation, documentation
   - Composes agent with those skills
   - Sends SSE notification

5. Compute 1 fetches assignment via MCP
   claudevn_get_assignment(task_id="task-1")

6. Compute 1 works on feature branch
   git checkout -b f/auth-schema/compute-001
   (writes code, commits)
   git push origin f/auth-schema/compute-001

7. Compute 1 reports progress
   claudevn_report_progress(status="in_progress", progress=50)
   claudevn_report_progress(status="in_progress", progress=100)

8. Compute 1 requests review
   claudevn_request_review()

9. Serving reviews changes
   (automated checks, human review if needed)

10. Serving merges to main
    git merge f/auth-schema/compute-001

11. Task 2 becomes unblocked
    Serving assigns to available compute
    (cycle repeats)
```

---

## Branch Naming Convention

All work happens on feature branches with a consistent naming scheme:

```
{type}/{task-slug}/{compute-id}

Types:
  f/   - feature
  x/   - fix
  r/   - refactor
  t/   - test
  d/   - docs

Examples:
  f/implement-user-auth/compute-001
  x/fix-login-bug/compute-023
  r/cleanup-api-routes/compute-007
```

**Branch lifecycle:**
1. Created from main
2. Compute works and commits
3. Pushed to Serving's Git server
4. PR created (Redis queue)
5. Reviewed and approved
6. Merged to main by Serving
7. Retained for history

---

## Data Flow

### State Storage

| Data Type | Storage | Purpose |
|-----------|---------|---------|
| **Source code** | Git (bare repository) | Single source of truth |
| **Work tasks** | Work Map (in-memory + Redis) | Task queue, dependencies |
| **PR queue** | Redis | Branches awaiting review |
| **Merge queue** | Redis | Approved branches waiting to merge |
| **Branch status** | Redis | Current state of each branch |
| **Compute registry** | Redis | Active instances, health status |

### Git Infrastructure

**Components:**
- **Bare Repository:** Authoritative storage at `/repos/{project}.git`
- **SSH Daemon:** Git transport with key-based authentication (port 2222)
- **Git Hooks:** Trigger events on push (update PR queue)
- **Redis:** PR management, branch tracking, merge coordination

**Redis schema:**
```
# Branch metadata
branch:{project}:{branch_name} = {
  status: pending | in_review | approved | rejected | merged | conflict,
  compute_id: compute-001,
  task_id: task-123,
  created_at: ISO timestamp,
  last_commit: SHA
}

# PR queue (branches ready for review)
pr_queue:{project} = sorted set { branch_name: timestamp }

# Merge queue (approved, waiting to merge)
merge_queue:{project} = list [branch1, branch2, ...]
```

---

## Conflict Resolution

When a branch conflicts with main:

```
1. Serving attempts merge
2. Conflict detected
3. Serving rejects PR with detailed reason
4. Original compute instance notified (status=conflict)
5. Compute rebases branch onto latest main
   git fetch origin main
   git rebase origin/main
6. Compute resolves conflicts
7. Compute pushes updated branch
   git push --force-with-lease
8. Re-review triggered automatically
```

---

## Scaling Strategy

| Component | Scaling Model | Details |
|-----------|---------------|---------|
| **Serving** | Vertical (single instance) | One per project, scale up resources |
| **Compute** | Horizontal (add workers) | Spawn more Claude Code instances as needed |
| **Git** | Vertical (single repo) | One bare repo per project |
| **Redis** | Horizontal (cluster) | For large deployments with many projects |
| **Marketplace** | Vertical | Single catalog service across all projects |

**Per-project isolation:**
- Each project has its own Serving instance
- Each project has its own Git repository
- Projects run independently side-by-side
- Compute instances can work on multiple projects

---

## Security Model

### Authentication

| Connection | Method |
|------------|--------|
| Compute → Serving (MCP) | API key per compute instance |
| Compute → Git (SSH) | SSH key per compute instance |
| User → Serving (UI) | Session-based authentication |
| Serving → Marketplace | HTTP API key |

### Authorization

| Action | Who Can Perform |
|--------|-----------------|
| Create task | Serving (Claude Code orchestrator) |
| Assign work | Serving only |
| Push branches | Compute instances (feature branches only) |
| Merge to main | Serving only |
| View status | Authenticated users |
| Edit goals | Authenticated users |

**Key security principles:**
1. **Task-scoped API keys:** Each compute instance has limited permissions
2. **SSH key isolation:** Separate keys prevent cross-instance access
3. **Branch restrictions:** Compute cannot push to main
4. **Merge authority:** Only Serving can merge, ensuring review process

---

## Use Cases

### 1. Feature Implementation

**Goal:** "Add export to CSV functionality"

**What happens:**
- Serving decomposes into: backend endpoint, frontend UI, tests, docs
- Multiple compute instances work in parallel
- Each pushes feature branch
- Serving coordinates merges in dependency order
- Result: Complete feature with tests and docs

### 2. Bug Investigation and Fix

**Goal:** "Login sometimes fails with 500 error"

**What happens:**
- Serving assigns to compute with bug-investigation skill
- Compute analyzes logs, traces code, identifies root cause
- Compute reports findings via MCP
- Serving creates fix task, assigns to code-implementation compute
- Fix reviewed and merged
- Result: Bug fixed with regression test

### 3. Codebase Refactoring

**Goal:** "Refactor authentication module for maintainability"

**What happens:**
- Serving creates refactor tasks with dependencies
- Compute instances work on isolated pieces
- Changes reviewed for consistency
- Merges coordinated to avoid conflicts
- Result: Improved codebase structure

### 4. Documentation Updates

**Goal:** "Update API documentation to reflect new endpoints"

**What happens:**
- Serving assigns to documentation-skilled compute
- Compute analyzes code, generates docs
- Docs pushed, reviewed for accuracy
- Merged to main
- Result: Up-to-date documentation

---

## Monitoring and Observability

### Real-Time UI (WebSocket)

**Dashboard shows:**
- Active compute instances and their status
- Current task assignments
- Work queue and dependencies
- Branch activity (pushes, PRs, merges)
- Progress indicators per task
- Blocker alerts

### Audit Trail

**Git provides:**
- Complete commit history
- Who worked on what (via branch names)
- When changes were made
- What was changed (diffs)

**Redis provides:**
- Task assignment history
- Progress reports over time
- Blocker events
- Review timestamps

---

## Technical Stack

| Layer | Technology |
|-------|-----------|
| **Coordination Hub** | FastAPI (Python 3.10+), Redis, Git (bare repos) |
| **MCP Server** | Python MCP library (port 8002) |
| **Marketplace** | FastAPI (Python 3.10+), YAML skill definitions (port 8003) |
| **Compute Runtime** | Claude Code CLI |
| **State Management** | Git repositories, Redis queues |
| **Frontend** | React, TailwindCSS, WebSocket |
| **Git Transport** | SSH (port 2222) |

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Claude Code CLI
- Git

### Quick Start

1. **Start Serving and Marketplace:**
   ```bash
   docker-compose up -d
   ```
   - Serving runs on port 8002
   - Marketplace runs on port 8003
   - Git SSH server on port 2222

2. **Register compute instance:**
   ```bash
   python scripts/register_compute.py --name compute-001
   ```

3. **Start compute worker:**
   ```bash
   python compute/start_worker.py --compute-id compute-001
   ```

4. **Access UI:**
   ```
   http://localhost:8002/
   ```

5. **Create a goal:**
   ```bash
   curl -X POST http://localhost:8002/goals \
     -H "Content-Type: application/json" \
     -d '{"description": "Implement user authentication"}'
   ```

6. **Watch the work happen:**
   - UI shows tasks being created
   - Compute instances pick up work
   - Branches appear in Git
   - PRs created and merged
   - Progress tracked in real-time

---

## FAQ

**Q: How does ClaudeVN differ from other AI agent frameworks?**

A: ClaudeVN uses Git as the state management layer and Claude Code as the compute engine. This provides native version control, familiar workflows, and powerful AI capabilities without building custom runtime infrastructure.

**Q: Can I use this for non-code projects?**

A: Yes. While optimized for software development, ClaudeVN can coordinate any work that benefits from version control and AI agents (documentation, research, analysis, etc.).

**Q: How do I create custom skills?**

A: Add YAML files to `marketplace/skills/`. Each skill defines instructions, capabilities, and constraints. Skills are automatically discovered and available for agent composition.

**Q: What happens if a compute instance crashes?**

A: Serving detects the failure (via health checks), marks the task as unassigned, and reassigns to another compute instance. Work already pushed to Git is preserved.

**Q: Can agents work on multiple tasks simultaneously?**

A: No. Each compute instance focuses on one primary task at a time for simplicity and clarity. Spawn more compute instances for parallel work.

**Q: How do I review AI-generated code?**

A: All work goes through the PR queue. You can configure automated checks (linting, tests) and/or human review before Serving merges to main.

**Q: What about merge conflicts?**

A: Serving detects conflicts, rejects the PR, and notifies the compute instance. The compute rebases onto latest main, resolves conflicts, and re-submits for review.

**Q: How do I monitor what agents are doing?**

A: The real-time UI shows all active work, progress, and events. Git commits provide detailed audit trails. MCP progress reports log to Redis for analysis.

---

## Next Steps

- Read the [Git Infrastructure Guide](../design/specifications/git-infrastructure.md) for deployment details
- Explore [MCP Tools Documentation](../design/specifications/mcp-tools.md) for API reference
- Review [Skill Marketplace Specification](../design/specifications/skill-marketplace.md) to create custom skills
- Check [Work Map Guide](../design/specifications/workmap.md) to understand task coordination

---

**ClaudeVN is under active development.** This architecture represents version 1.0. Feedback and contributions welcome.
