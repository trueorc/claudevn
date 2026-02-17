# WorkMap Specification

**Version**: 1.0.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

The WorkMap is ClaudeVN's internal issue and work management system. It manages a prioritized backlog of issues, tracks dependencies, and coordinates parallel execution across multiple Compute instances.

**Key principles:**
- Issues are persistent with history (Git-backed)
- Work Items are ephemeral (Redis)
- Dependencies unlock automatically on completion
- Multiple Compute instances work in parallel
- Planner Compute breaks goals into issues

---

## Concepts

| Concept | Persistence | Purpose |
|---------|-------------|---------|
| **Goal** | Persistent | High-level objective, input to Planner |
| **Issue** | Persistent (Git) | Unit of work with history |
| **Work Item** | Ephemeral (Redis) | Active assignment to a Compute |

---

## Data Model

### Goal

High-level objective submitted by user. Planner Compute breaks this into Issues.

```yaml
id: goal-001
title: Build user authentication system
description: |
  Implement complete auth flow including:
  - User registration
  - Login/logout with JWT
  - Password reset via email
  - Session management

priority: P1
status: planning  # planning, in_progress, done

created_at: 2026-01-30T10:00:00Z
created_by: user

# Populated after planning
issue_ids: [issue-100, issue-101, issue-102, ...]
```

### Issue

Unit of work. Persistent with full history.

```yaml
id: issue-100
title: Design database schema for users
description: |
  Create database schema including:
  - users table with id, email, password_hash, created_at
  - sessions table for JWT refresh tokens

type: feature        # feature, bug, refactor, docs, test
area: database       # api, database, frontend, infra
priority: P1         # P0, P1, P2, P3
status: ready        # backlog, ready, in_progress, blocked, done, failed

required_skills: [code-writer, db-engineer]

# Dependencies
depends_on: []                    # Issue IDs this depends on
blocks: [issue-101, issue-102]    # Issue IDs waiting on this (computed)

# Lineage
goal_id: goal-001                 # Parent goal
parent_issue_id: null             # If subtask of another issue

# Timestamps
created_at: 2026-01-30T10:00:00Z
started_at: null
completed_at: null

# Result (populated on completion)
result:
  branch: f/issue-100/compute-001
  summary: Created users and sessions tables with migrations
  commits: [abc123, def456]
```

### Work Item

Ephemeral assignment. Exists only while work is in progress.

```yaml
id: work-item-xyz
issue_id: issue-100
compute_id: compute-001

assigned_at: 2026-01-30T10:05:00Z
status: in_progress    # assigned, in_progress

# Progress tracking
progress_percent: 60
last_activity_at: 2026-01-30T10:15:00Z
progress_notes: "Created users table, working on sessions"
```

---

## Storage Architecture

### Git Repository (Issues)

Issues stored as YAML files in a Git repository for history and durability.

```
workmap-repo/
├── goals/
│   ├── goal-001.yaml
│   └── goal-002.yaml
├── issues/
│   ├── issue-100.yaml
│   ├── issue-101.yaml
│   └── issue-102.yaml
└── archive/
    └── done/
        └── issue-050.yaml
```

**Why Git:**
- Full history of changes
- Audit trail
- Familiar tooling
- Can inspect/debug manually

### Redis (Work Items + Indexes)

Redis for ephemeral state and fast querying.

**Work Items:**
```
work_item:{work-item-xyz} → JSON hash of work item
```

**Indexes:**
```
# Issues by status
issues:status:backlog → Set of issue IDs
issues:status:ready → Set of issue IDs
issues:status:in_progress → Set of issue IDs

# Ready queue by priority (sorted set, score = priority)
issues:ready:queue → Sorted set (issue-100: 1, issue-105: 2, ...)

# Dependencies
issues:depends_on:{issue-101} → Set [issue-100]  # 101 depends on 100
issues:blocks:{issue-100} → Set [issue-101, issue-102]  # 100 blocks these

# Skills index
issues:skill:{code-writer} → Set of issue IDs requiring this skill

# Compute assignments
compute:{compute-001}:current → work-item-xyz
```

---

## Status Flow

```
         ┌────────────────────────────┐
         │                            │
         ▼                            │
     backlog ──────► ready ──────► in_progress ──────► done
         │            ▲                │
         │            │                │
         │            └────────────────┤ (failure/timeout)
         │                             │
         └─────────────────────────────┘
                   (deps unmet)
```

| Status | Meaning |
|--------|---------|
| **backlog** | Has unmet dependencies, not ready |
| **ready** | All dependencies met, waiting for assignment |
| **in_progress** | Assigned to a Compute, being worked |
| **blocked** | Compute reported a blocker |
| **done** | Completed successfully |
| **failed** | Failed after retries exhausted |

---

## Dependency Resolution

### On Issue Creation

When issues are created (individually or in batch):

```
For each new issue:
  1. Store issue in Git
  2. Add to Redis indexes
  3. Check depends_on list
  4. If all dependencies are done → status: ready
  5. Else → status: backlog
  6. Update blocks index for dependencies
```

### On Issue Completion

When an issue completes:

```
Issue-100 completes:
  1. Mark issue-100 as done (Git + Redis)
  2. Query: issues:blocks:issue-100 → [issue-101, issue-102]
  3. For each blocked issue:
     a. Check: are ALL its dependencies done?
     b. If yes → status: ready, add to ready queue
     c. If no → stays in backlog
```

### Example Cascade

```
Initial state:
  issue-100: ready (no deps)
  issue-101: backlog (depends on 100)
  issue-102: backlog (depends on 100)
  issue-103: backlog (depends on 101 AND 102)

issue-100 completes:
  → issue-101: ready (100 done)
  → issue-102: ready (100 done)
  → issue-103: backlog (still waiting on 101 and 102)

issue-101 completes:
  → issue-103: backlog (still waiting on 102)

issue-102 completes:
  → issue-103: ready (both 101 and 102 done)
```

---

## Assignment Logic

Serving continuously matches ready issues to available Compute instances.

### Algorithm

```python
def assign_work():
    # Get all ready issues, sorted by priority
    ready_issues = redis.zrange("issues:ready:queue", 0, -1)

    # Get all idle computes with their capabilities
    idle_computes = get_idle_computes()

    for issue in ready_issues:
        required_skills = issue.required_skills

        for compute in idle_computes:
            if compute.has_skills(required_skills):
                # Match found
                create_work_item(issue, compute)
                push_work_assigned(compute, issue)
                idle_computes.remove(compute)
                break
```

### Priority Scoring

Issues are scored for queue ordering:

```
Score = (Priority * 1000) + (Age in hours)

P0 = 0, P1 = 1, P2 = 2, P3 = 3

Example:
  P0 issue, 2 hours old: 0 * 1000 + 2 = 2
  P1 issue, 5 hours old: 1 * 1000 + 5 = 1005
  P1 issue, 1 hour old:  1 * 1000 + 1 = 1001

Lower score = higher priority
```

---

## Failure Handling

### Compute Disconnection

```
Compute SSE connection drops:
  1. Serving detects immediately
  2. Find work item: compute:{compute-id}:current
  3. Get issue from work item
  4. Check: was branch pushed to Serving Git?
     - No → Issue back to ready (no work done)
     - Yes → Issue stays in_progress, may need review
  5. Delete work item
  6. Remove compute from registry
```

### Timeout Detection

```
Work item last_activity_at > 30 minutes ago:
  1. Mark issue as ready (reassign)
  2. Delete stale work item
  3. Increment issue.retry_count
  4. If retry_count > 3 → status: failed
```

### Blocker Reported

```
Compute calls claudevn_signal_blocker():
  1. Issue status → blocked
  2. Store blocker details
  3. May create resolution issue
  4. Work item remains (Compute still assigned)
  5. Human or other process resolves blocker
  6. Issue status → in_progress (continues)
```

---

## Planner Integration

### Planner Skill

A specialized skill that breaks Goals into Issues.

```yaml
id: planner
name: Planner
description: Analyzes goals and creates implementation plans
instructions: |
  You are a technical planner. Given a high-level goal:
  1. Analyze requirements
  2. Break into discrete, implementable issues
  3. Identify dependencies between issues
  4. Assign appropriate skills to each issue
  5. Submit the plan via claudevn_add_issues()

  Keep issues small and focused. One issue = one PR.
```

### Planning Flow

```
1. Goal submitted
   User : POST /api/v1/goals : Serving
   Serving : creates Goal (status: planning) : Git

2. Planner assigned
   Serving : creates special planning issue : WorkMap
   Serving : assigns to Planner Compute : SSE push

3. Planner executes
   Planner : analyzes goal : itself
   Planner : calls claudevn_add_issues() : Serving

4. Issues created
   Serving : creates all issues : Git + Redis
   Serving : resolves initial dependencies : some ready
   Serving : Goal status → in_progress : Git

5. Execution begins
   Serving : assigns ready issues : Worker Computes
```

---

## API Endpoints

### Goals

```
POST   /api/v1/goals                    Create goal
GET    /api/v1/goals                    List goals
GET    /api/v1/goals/{id}               Get goal
GET    /api/v1/goals/{id}/issues        Get goal's issues
```

### Issues

```
POST   /api/v1/issues                   Create issue
POST   /api/v1/issues/batch             Create multiple issues
GET    /api/v1/issues                   List issues (with filters)
GET    /api/v1/issues/{id}              Get issue
PATCH  /api/v1/issues/{id}              Update issue
GET    /api/v1/issues/{id}/history      Get issue history

# Query parameters for list
?status=ready,in_progress
?priority=P0,P1
?area=api,database
?skill=code-writer
```

### WorkMap View

```
GET    /api/v1/workmap                  Full workmap state
GET    /api/v1/workmap/ready            Ready queue
GET    /api/v1/workmap/in-progress      Active work
GET    /api/v1/workmap/blocked          Blocked issues
GET    /api/v1/workmap/stats            Statistics
```

### Work Items (internal)

```
GET    /api/v1/work-items               List active work items
GET    /api/v1/work-items/{id}          Get work item
```

---

## MCP Tools

### claudevn_add_issues

Planner Compute uses this to submit planned issues.

**Input:**
```json
{
  "goal_id": "goal-001",
  "issues": [
    {
      "title": "Design database schema",
      "description": "Create users and sessions tables...",
      "type": "feature",
      "area": "database",
      "priority": "P1",
      "required_skills": ["code-writer", "db-engineer"],
      "depends_on": []
    },
    {
      "title": "Implement user model",
      "description": "Create User model with validation...",
      "type": "feature",
      "area": "api",
      "priority": "P1",
      "required_skills": ["code-writer"],
      "depends_on": [0]
    }
  ]
}
```

Note: `depends_on` uses array indices for batch-internal references.

**Output:**
```json
{
  "success": true,
  "goal_id": "goal-001",
  "created_issues": [
    {"index": 0, "id": "issue-100"},
    {"index": 1, "id": "issue-101"}
  ],
  "ready_count": 1,
  "backlog_count": 1
}
```

### claudevn_add_requirement (updated)

Worker Compute can suggest additional issues discovered during work.

**Input:**
```json
{
  "task_id": "issue-100",
  "title": "Add database indexes for performance",
  "description": "During implementation, identified need for indexes...",
  "type": "feature",
  "priority": "P2",
  "depends_on": ["issue-100"],
  "suggested_skills": ["db-engineer"]
}
```

**Output:**
```json
{
  "acknowledged": true,
  "issue_id": "issue-150",
  "status": "backlog"
}
```

Note: This creates a suggestion. Serving decides when/if to schedule it.

---

## UI Requirements

The frontend must display:

### Backlog View
- All issues grouped by status
- Filter by priority, area, type, skill
- Drag-drop priority reordering
- Dependency visualization

### WorkMap View
- Visual graph of issues and dependencies
- Color-coded by status
- Real-time updates via WebSocket
- Show which Compute is working on what

### Goal Progress
- Goal with its issues
- Completion percentage
- Blocked issues highlighted
- Time tracking

### Active Work
- Currently executing issues
- Compute assignments
- Progress indicators
- Recent activity feed

---

## Implementation Notes

### Git Operations

Use Serving's existing Git infrastructure:
- WorkMap repo is a bare repo managed by RepoManager
- Issues are YAML files
- Commits for audit trail
- Can use branches for workspaces if needed

### Redis Schema

Prefix all keys with `workmap:` for namespacing:
```
workmap:issues:status:ready
workmap:issues:ready:queue
workmap:work_item:{id}
```

### Concurrency

- Use Redis transactions for atomic updates
- Optimistic locking on Git writes
- Work item assignment is atomic (check-and-set)

---

## Related Documents

- [Compute Registration](./compute-registration.md) - SSE connection and work push
- [MCP Tools](./mcp-tools.md) - Compute communication
- [v1.0 Architecture](../architecture/v1.0-architecture.md) - System overview
