# MCP Tools Specification

**Version**: 1.1.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

MCP (Model Context Protocol) enables communication between running Claude Code instances and Serving during task execution. Claude Code uses MCP tools to report progress, signal blockers, add requirements, and complete tasks.

**Key principle:** Work assignment uses a **notification + fetch** pattern. Serving pushes a lightweight `work_assigned` SSE event; Compute then calls `claudevn_get_assignment` to fetch full details. Skills are composed by Serving and included in the assignment response.

---

## Architecture

```
Work Assignment (Notification + Fetch):
  1. Serving pushes SSE event: work_assigned { task_id }
  2. Compute Infra receives notification
  3. Compute calls claudevn_get_assignment(task_id) via MCP
  4. Serving returns: skills, context, branch, MCP config
  5. Compute Infra spawns Claude Code with full assignment

Claude Code uses MCP tools to:
  - Report progress
  - Signal blockers
  - Add new requirements to work map
  - Request review
  - Complete task
```

---

## What Claude Code Receives at Spawn

Compute Infra fetches full assignment via `claudevn_get_assignment`, then spawns Claude Code with:

| Injected At Spawn | Description |
|-------------------|-------------|
| `CLAUDE.md` | Merged skill instructions (from assignment) |
| `task_id` | Assigned task identifier |
| `task_description` | What to do |
| `branch_name` | Git branch to work on |
| `context` | Relevant files, requirements |
| `mcp_config` | Server URL, task-scoped API key |

**Note:** Claude Code itself does not call `claudevn_get_assignment`. The Compute Infra layer handles work assignment before spawning Claude Code.

---

## MCP Server Configuration

### Claude Code MCP Config (injected at spawn)

```json
{
  "mcpServers": {
    "claudevn": {
      "url": "http://serving:8002/mcp",
      "headers": {
        "Authorization": "Bearer <task-scoped-key>",
        "X-Task-ID": "task-456"
      }
    }
  }
}
```

---

## MCP Tools

### claudevn_report_progress

**Purpose:** Update task status and progress during execution.

**When to use:** Periodically during work to indicate progress.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Task being updated |
| `status` | string | yes | `in_progress`, `blocked`, `review_requested` |
| `progress_percent` | integer | no | 0-100 completion estimate |
| `message` | string | no | Status message |
| `commits` | array | no | Commit SHAs made |

#### Example

```json
{
  "task_id": "task-456",
  "status": "in_progress",
  "progress_percent": 60,
  "message": "Implemented login endpoint, working on logout",
  "commits": ["abc123", "def456"]
}
```

#### Response

```json
{
  "acknowledged": true,
  "task_id": "task-456",
  "updated_at": "2026-01-30T14:30:00Z"
}
```

---

### claudevn_signal_blocker

**Purpose:** Report a blocker preventing task completion.

**When to use:** When work cannot proceed due to external dependencies, missing information, or technical issues.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Task that is blocked |
| `blocker_type` | string | yes | `dependency`, `clarification`, `access`, `technical`, `other` |
| `description` | string | yes | What is blocking |
| `suggested_resolution` | string | no | How to resolve |
| `blocking_task_id` | string | no | If blocked by another task |

#### Example

```json
{
  "task_id": "task-456",
  "blocker_type": "dependency",
  "description": "Need database schema for users table before implementing authentication",
  "suggested_resolution": "Create database migration for users table"
}
```

#### Response

```json
{
  "acknowledged": true,
  "blocker_id": "blocker-123",
  "status": "blocker_recorded"
}
```

---

### claudevn_add_requirement

**Purpose:** Add new work items to the process map discovered during execution.

**When to use:** When Claude Code identifies additional work needed that wasn't in the original task. Serving decides when and where to assign these new requirements.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Brief title for new work |
| `description` | string | yes | Detailed description |
| `parent_task_id` | string | yes | Task that spawned this requirement |
| `suggested_skills` | array | no | Skills that might be needed |
| `dependencies` | array | no | Task IDs this depends on |
| `priority` | string | no | `critical`, `high`, `normal`, `low` |

#### Example

```json
{
  "title": "Add password reset endpoint",
  "description": "During auth implementation, identified need for password reset flow. Should send email with reset token.",
  "parent_task_id": "task-456",
  "suggested_skills": ["code-writer", "email-integration"],
  "dependencies": ["task-456"],
  "priority": "normal"
}
```

#### Response

```json
{
  "acknowledged": true,
  "new_task_id": "task-789",
  "status": "added_to_backlog"
}
```

---

### claudevn_request_review

**Purpose:** Signal that work is ready for review before completion.

**When to use:** When code is complete and Claude Code wants review before final merge.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Task requesting review |
| `branch` | string | yes | Branch with changes |
| `title` | string | no | PR/review title |
| `description` | string | no | What changed and why |
| `test_results` | object | no | Test execution results |

#### Example

```json
{
  "task_id": "task-456",
  "branch": "f/implement-auth/compute-001",
  "title": "Implement user authentication",
  "description": "Added:\n- Login endpoint with JWT\n- Logout endpoint\n- Password hashing with bcrypt",
  "test_results": {
    "passed": 12,
    "failed": 0,
    "skipped": 0
  }
}
```

#### Response

```json
{
  "pr_id": "pr-789",
  "branch": "f/implement-auth/compute-001",
  "status": "review_requested",
  "queue_position": 3
}
```

---

### claudevn_complete_task

**Purpose:** Mark task as complete and submit work.

**When to use:** When all work is done, tests pass, and ready to merge.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Task being completed |
| `branch` | string | yes | Branch with final work |
| `summary` | string | yes | Summary of work done |
| `deliverables` | array | no | List of files/features delivered |
| `test_results` | object | no | Final test results |

#### Example

```json
{
  "task_id": "task-456",
  "branch": "f/implement-auth/compute-001",
  "summary": "Implemented JWT-based authentication with login/logout endpoints",
  "deliverables": [
    "src/api/auth.py",
    "src/models/user.py",
    "tests/test_auth.py"
  ],
  "test_results": {
    "passed": 15,
    "failed": 0,
    "coverage": "87%"
  }
}
```

#### Response

```json
{
  "task_id": "task-456",
  "status": "completed",
  "merge_status": "queued"
}
```

---

### claudevn_get_context

**Purpose:** Fetch additional context during execution.

**When to use:** When Claude Code needs more information about related work, files, or history not provided at spawn.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Current task |
| `context_types` | array | no | `files`, `history`, `related_tasks`, `dependencies` |
| `file_patterns` | array | no | Glob patterns for files |

#### Example

```json
{
  "task_id": "task-456",
  "context_types": ["related_tasks", "history"],
  "file_patterns": ["src/models/*.py"]
}
```

#### Response

```json
{
  "related_tasks": [
    {
      "task_id": "task-400",
      "title": "Setup database models",
      "status": "completed",
      "relationship": "dependency"
    }
  ],
  "recent_commits": [
    {
      "sha": "abc123",
      "message": "Add base model classes",
      "author": "compute-002",
      "date": "2026-01-29T10:00:00Z"
    }
  ]
}
```

---

## Planner-Specific Tools

These tools are available to Planner Compute instances.

### claudevn_add_issues

**Purpose:** Submit a batch of issues created during planning.

**When to use:** Planner Compute uses this to submit the breakdown of a Goal into implementable issues.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `goal_id` | string | yes | Goal being planned |
| `issues` | array | yes | List of issues to create |

Each issue in the array:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | yes | Issue title |
| `description` | string | yes | Detailed description |
| `type` | string | no | feature, bug, refactor, docs, test |
| `area` | string | no | api, database, frontend, infra |
| `priority` | string | no | P0, P1, P2, P3 |
| `required_skills` | array | no | Skills needed |
| `depends_on` | array | no | Array indices of dependencies in this batch |

#### Example

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
    },
    {
      "title": "Implement auth endpoints",
      "description": "Login/logout with JWT...",
      "depends_on": [1]
    },
    {
      "title": "Write auth tests",
      "description": "Unit and integration tests...",
      "depends_on": [2]
    }
  ]
}
```

Note: `depends_on` uses array indices (0, 1, 2...) for batch-internal references.

#### Response

```json
{
  "success": true,
  "goal_id": "goal-001",
  "created_issues": [
    {"index": 0, "id": "issue-100"},
    {"index": 1, "id": "issue-101"},
    {"index": 2, "id": "issue-102"},
    {"index": 3, "id": "issue-103"}
  ],
  "ready_count": 1,
  "backlog_count": 3
}
```

---

### claudevn_get_assignment

**Purpose:** Fetch full work assignment details after receiving SSE notification.

**When to use:** After receiving a `work_assigned` SSE event from Serving. This is part of the **notification + fetch** pattern - Serving pushes a lightweight SSE event, then Compute fetches full details via MCP.

**Note:** Compute does NOT poll for work. It only calls this tool in response to a `work_assigned` SSE notification.

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Task ID from SSE notification |
| `compute_id` | string | yes | Compute instance requesting assignment |

#### Example

```json
{
  "task_id": "task-456",
  "compute_id": "compute-001"
}
```

#### Response

```json
{
  "task_id": "task-456",
  "title": "Implement user authentication",
  "description": "Add login/logout endpoints with JWT support...",
  "branch_name": "f/implement-auth/compute-001",
  "skills": {
    "ids": ["code-writer", "test-automator"],
    "merged_instructions": "# Code Writer\nYou are an expert developer...\n\n# Test Automator\n..."
  },
  "context": {
    "repository": "git@serving:project.git",
    "base_branch": "main",
    "relevant_files": ["src/api/routes.py", "src/models/user.py"],
    "requirements": "Use bcrypt for password hashing"
  },
  "mcp_config": {
    "server_url": "http://serving:8002/mcp",
    "api_key": "task-scoped-key-xyz"
  }
}
```

---

## Tools NOT Available

These were removed from earlier designs:

| Removed Tool | Reason |
|--------------|--------|
| `claudevn_get_skill` | Skills are composed and included in assignment response |

---

## Error Handling

### Error Response Format

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task task-999 does not exist",
    "details": {
      "task_id": "task-999"
    }
  }
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `TASK_NOT_FOUND` | Task does not exist |
| `INVALID_STATUS` | Invalid status transition |
| `PERMISSION_DENIED` | Not authorized for this task |
| `BRANCH_NOT_FOUND` | Git branch does not exist |
| `CONFLICT` | Operation conflicts with current state |

---

## Authentication

Every MCP request is authenticated with a task-scoped API key:

- Key issued when work is assigned
- Key only valid for the specific task
- Key expires when task completes or times out

---

## Summary

### Compute Infra Tools

| Tool | Direction | Purpose |
|------|-----------|---------|
| `claudevn_get_assignment` | Compute Infra → Serving | Fetch full assignment after SSE notification |

### Worker Tools (Claude Code)

| Tool | Direction | Purpose |
|------|-----------|---------|
| `claudevn_report_progress` | Claude Code → Serving | Status updates |
| `claudevn_signal_blocker` | Claude Code → Serving | Report blockers |
| `claudevn_add_requirement` | Claude Code → Serving | Suggest additional work |
| `claudevn_request_review` | Claude Code → Serving | Request code review |
| `claudevn_complete_task` | Claude Code → Serving | Submit completed work |
| `claudevn_get_context` | Claude Code → Serving | Fetch additional context |

### Planner Tools

| Tool | Direction | Purpose |
|------|-----------|---------|
| `claudevn_add_issues` | Planner → Serving | Submit batch of planned issues |

---

## Related Documents

- [Compute Registration](./compute-registration.md) - SSE connection and work assignment
- [v1.0 Architecture](../architecture/v1.0-architecture.md) - System overview
- [WorkMap Specification](./workmap.md) - Work distribution and dependency tracking
