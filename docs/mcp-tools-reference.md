# ClaudeVN MCP Tools Reference

**Audience:** Developers working with ClaudeVN compute instances
**Last Updated:** February 2026
**Version:** 1.1.0

---

## Quick Start

ClaudeVN uses MCP (Model Context Protocol) for communication between Claude Code instances and the central Serving hub. This reference provides practical examples of each tool.

### How It Works

```
┌─────────────┐                           ┌─────────────┐
│   Serving   │ ─ SSE event ────────────> │   Compute   │
│             │   work_assigned           │   Instance  │
│             │   {task_id: "456"}        │             │
│             │                           │             │
│             │ <─ claudevn_get_assignment│             │
│   Port 8002 │   {task_id, compute_id}   │             │
│             │                           │             │
│             │ ─ Full assignment ──────> │             │
│  MCP Server │   {skills, context,...}   │ MCP Client  │
│             │                           │             │
│             │ <─ claudevn_report_progress             │
│             │ <─ claudevn_complete_task │             │
│             │                           │             │
└─────────────┘                           └─────────────┘
```

**Key Concept:** Serving pushes lightweight notifications, Compute fetches full details.

---

## Connection Setup

Claude Code instances connect to the MCP server with configuration provided at spawn:

```json
{
  "mcpServers": {
    "claudevn": {
      "url": "http://serving:8002/mcp",
      "headers": {
        "Authorization": "Bearer task-abc123-xyz789",
        "X-Task-ID": "task-456"
      }
    }
  }
}
```

**Authentication:**
- Each task gets a unique API key
- Key only works for that specific task
- Key expires when task completes or times out
- Never share keys between tasks

---

## Infrastructure Tools

### claudevn_get_assignment

**Who uses it:** Compute infrastructure (not Claude Code directly)
**When:** After receiving `work_assigned` SSE notification
**Purpose:** Fetch full work assignment details

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✓ | Task ID from SSE event |
| `compute_id` | string | ✓ | Your compute instance ID |

#### Request Example

```json
{
  "task_id": "task-456",
  "compute_id": "compute-001"
}
```

#### Response Example

```json
{
  "task_id": "task-456",
  "title": "Implement user authentication",
  "description": "Add login/logout endpoints with JWT token support. Use bcrypt for password hashing.",
  "branch_name": "f/implement-auth/compute-001",
  "skills": {
    "ids": ["code-writer", "test-automator"],
    "merged_instructions": "# Code Writer\nYou are an expert developer...\n\n# Test Automator\nWrite comprehensive tests..."
  },
  "context": {
    "repository": "git@serving:project.git",
    "base_branch": "main",
    "relevant_files": [
      "src/api/routes.py",
      "src/models/user.py"
    ],
    "requirements": "Use bcrypt for passwords, JWT tokens expire in 1 hour"
  },
  "mcp_config": {
    "server_url": "http://serving:8002/mcp",
    "api_key": "task-scoped-key-xyz789"
  }
}
```

#### What Happens Next

The Compute infrastructure:
1. Writes merged skills to `CLAUDE.md`
2. Checks out the git branch
3. Spawns Claude Code with task context
4. Configures MCP client with the provided credentials

---

## Worker Tools (Claude Code)

These tools are used by Claude Code during task execution.

### claudevn_report_progress

**When to use:** Periodically during work to show you're making progress

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✓ | Your current task |
| `status` | string | ✓ | `in_progress`, `blocked`, `review_requested` |
| `progress_percent` | integer | | 0-100 completion estimate |
| `message` | string | | What you're working on |
| `commits` | array | | Git commit SHAs you've made |

#### Request Example

```json
{
  "task_id": "task-456",
  "status": "in_progress",
  "progress_percent": 60,
  "message": "Implemented login endpoint with JWT tokens. Working on logout endpoint.",
  "commits": ["a1b2c3d", "e4f5g6h"]
}
```

#### Response Example

```json
{
  "acknowledged": true,
  "task_id": "task-456",
  "updated_at": "2026-02-14T10:30:00Z"
}
```

#### Best Practices

- Report progress every 15-30 minutes during long tasks
- Include meaningful messages about what you're doing
- Don't over-report (every few minutes is excessive)
- Always include commit SHAs so Serving can track your work

---

### claudevn_signal_blocker

**When to use:** When you can't proceed due to external issues

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✓ | Task that's blocked |
| `blocker_type` | string | ✓ | See types below |
| `description` | string | ✓ | What's blocking you |
| `suggested_resolution` | string | | How to fix it |
| `blocking_task_id` | string | | If blocked by another task |

**Blocker Types:**
- `dependency` - Waiting for another task
- `clarification` - Need more information
- `access` - Missing credentials or permissions
- `technical` - Technical issue (API down, build broken)
- `other` - Something else

#### Request Example

```json
{
  "task_id": "task-456",
  "blocker_type": "dependency",
  "description": "Cannot implement authentication endpoints without the database schema for users table. The schema migration hasn't been created yet.",
  "suggested_resolution": "Create database migration for users table with email, password_hash, created_at fields",
  "blocking_task_id": "task-400"
}
```

#### Response Example

```json
{
  "acknowledged": true,
  "blocker_id": "blocker-123",
  "status": "blocker_recorded"
}
```

#### What Happens Next

- Serving records the blocker
- The blocking task (if specified) gets flagged
- Serving may reassign you to other work
- When resolved, you'll be notified to resume

---

### claudevn_add_requirement

**When to use:** When you discover new work that wasn't in the original plan

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | ✓ | Brief title (50 chars) |
| `description` | string | ✓ | Detailed explanation |
| `parent_task_id` | string | ✓ | Task that discovered this |
| `suggested_skills` | array | | Skills needed |
| `dependencies` | array | | Task IDs this depends on |
| `priority` | string | | `critical`, `high`, `normal`, `low` |

#### Request Example

```json
{
  "title": "Add password reset endpoint",
  "description": "While implementing login/logout, realized we need a password reset flow. Users need a way to reset forgotten passwords via email. Should:\n- Generate secure reset tokens\n- Send reset email\n- Validate token and update password\n- Expire tokens after 1 hour",
  "parent_task_id": "task-456",
  "suggested_skills": ["code-writer", "email-integration"],
  "dependencies": ["task-456"],
  "priority": "normal"
}
```

#### Response Example

```json
{
  "acknowledged": true,
  "new_task_id": "task-789",
  "status": "added_to_backlog"
}
```

#### Best Practices

- Only add requirements that are truly necessary
- Provide detailed descriptions so others understand the context
- Suggest realistic priorities (not everything is critical)
- Link dependencies correctly

---

### claudevn_request_review

**When to use:** Code is done and you want review before marking complete

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✓ | Your task |
| `branch` | string | ✓ | Git branch name |
| `title` | string | | Review title |
| `description` | string | | Summary of changes |
| `test_results` | object | | Test execution stats |

**Test Results Object:**
```json
{
  "passed": 15,
  "failed": 0,
  "skipped": 2
}
```

#### Request Example

```json
{
  "task_id": "task-456",
  "branch": "f/implement-auth/compute-001",
  "title": "Implement user authentication",
  "description": "Added JWT-based authentication system:\n\n**Changes:**\n- Login endpoint (POST /api/auth/login)\n- Logout endpoint (POST /api/auth/logout)\n- JWT token generation and validation\n- Password hashing with bcrypt\n- User session management\n\n**Testing:**\n- All 15 tests passing\n- Coverage: 87%\n\n**Files Changed:**\n- src/api/auth.py (new)\n- src/models/user.py (modified)\n- tests/test_auth.py (new)",
  "test_results": {
    "passed": 15,
    "failed": 0,
    "skipped": 0
  }
}
```

#### Response Example

```json
{
  "pr_id": "pr-789",
  "branch": "f/implement-auth/compute-001",
  "status": "review_requested",
  "queue_position": 3
}
```

#### What Happens Next

- Your work enters the review queue
- A reviewer (human or AI) will check your code
- You may get feedback to address
- Once approved, you can complete the task

---

### claudevn_complete_task

**When to use:** All work done, tests pass, ready to merge

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✓ | Your task |
| `branch` | string | ✓ | Git branch name |
| `summary` | string | ✓ | Work summary |
| `deliverables` | array | | Files/features delivered |
| `test_results` | object | | Final test stats |

**Test Results Object:**
```json
{
  "passed": 15,
  "failed": 0,
  "coverage": "87%"
}
```

#### Request Example

```json
{
  "task_id": "task-456",
  "branch": "f/implement-auth/compute-001",
  "summary": "Implemented complete JWT-based authentication system with login/logout endpoints. All tests passing with 87% coverage. Password hashing uses bcrypt with salt rounds = 12. JWT tokens expire after 1 hour and are stored in HTTP-only cookies for security.",
  "deliverables": [
    "src/api/auth.py",
    "src/models/user.py",
    "src/utils/jwt.py",
    "tests/test_auth.py",
    "tests/test_jwt.py"
  ],
  "test_results": {
    "passed": 15,
    "failed": 0,
    "coverage": "87%"
  }
}
```

#### Response Example

```json
{
  "task_id": "task-456",
  "status": "completed",
  "merge_status": "queued"
}
```

#### What Happens Next

- Task marked as complete
- Branch queued for merge to main
- Serving handles merge conflicts
- Once merged, your compute instance gets new work

---

### claudevn_get_context

**When to use:** Need additional context not provided at spawn

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | ✓ | Your current task |
| `context_types` | array | | See types below |
| `file_patterns` | array | | Glob patterns |

**Context Types:**
- `files` - File contents
- `history` - Recent commits
- `related_tasks` - Related work items
- `dependencies` - Dependency information

#### Request Example

```json
{
  "task_id": "task-456",
  "context_types": ["related_tasks", "history"],
  "file_patterns": ["src/models/*.py", "src/api/auth*.py"]
}
```

#### Response Example

```json
{
  "related_tasks": [
    {
      "task_id": "task-400",
      "title": "Setup database models",
      "status": "completed",
      "relationship": "dependency",
      "completed_at": "2026-02-10T15:00:00Z"
    },
    {
      "task_id": "task-450",
      "title": "Setup JWT utilities",
      "status": "completed",
      "relationship": "dependency",
      "completed_at": "2026-02-12T09:00:00Z"
    }
  ],
  "recent_commits": [
    {
      "sha": "abc123def",
      "message": "Add base model classes",
      "author": "compute-002",
      "date": "2026-02-10T14:30:00Z",
      "files": ["src/models/base.py"]
    },
    {
      "sha": "456ghi789",
      "message": "Implement JWT token generation",
      "author": "compute-003",
      "date": "2026-02-12T08:45:00Z",
      "files": ["src/utils/jwt.py"]
    }
  ],
  "files": {
    "src/models/user.py": "class User(BaseModel):\n    email: str\n    password_hash: str\n    ...",
    "src/api/auth_base.py": "from fastapi import APIRouter\n..."
  }
}
```

#### Best Practices

- Request context only when needed (not upfront)
- Use specific file patterns to reduce response size
- Prefer `related_tasks` over `history` for understanding dependencies

---

## Planner Tools

These tools are only available to Planner compute instances.

### claudevn_add_issues

**When to use:** Submitting a batch of issues for a goal

#### Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `goal_id` | string | ✓ | Goal being planned |
| `issues` | array | ✓ | List of issues |

**Issue Object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | ✓ | Issue title |
| `description` | string | ✓ | Detailed description |
| `type` | string | | `feature`, `bug`, `refactor`, `docs`, `test` |
| `area` | string | | `api`, `database`, `frontend`, `infra` |
| `priority` | string | | `P0`, `P1`, `P2`, `P3` |
| `required_skills` | array | | Skills needed |
| `depends_on` | array | | Array indices of dependencies |

**Important:** Use array indices (0, 1, 2...) in `depends_on` to reference other issues in the same batch.

#### Request Example

```json
{
  "goal_id": "goal-001",
  "issues": [
    {
      "title": "Design database schema for authentication",
      "description": "Create schema for users and sessions tables:\n\n**Users Table:**\n- id (UUID, primary key)\n- email (string, unique)\n- password_hash (string)\n- created_at (timestamp)\n\n**Sessions Table:**\n- id (UUID, primary key)\n- user_id (UUID, foreign key)\n- token (string)\n- expires_at (timestamp)",
      "type": "feature",
      "area": "database",
      "priority": "P1",
      "required_skills": ["db-engineer"],
      "depends_on": []
    },
    {
      "title": "Implement User model",
      "description": "Create User model with:\n- Email validation\n- Password hashing (bcrypt)\n- Session management methods",
      "type": "feature",
      "area": "api",
      "priority": "P1",
      "required_skills": ["code-writer"],
      "depends_on": [0]
    },
    {
      "title": "Implement authentication endpoints",
      "description": "Create login/logout endpoints:\n- POST /api/auth/login\n- POST /api/auth/logout\n- JWT token generation\n- HTTP-only cookie storage",
      "type": "feature",
      "area": "api",
      "priority": "P1",
      "required_skills": ["code-writer"],
      "depends_on": [1]
    },
    {
      "title": "Write authentication tests",
      "description": "Comprehensive test coverage:\n- Unit tests for User model\n- Integration tests for endpoints\n- Security tests (SQL injection, XSS)\n- Target: 85%+ coverage",
      "type": "test",
      "area": "api",
      "priority": "P2",
      "required_skills": ["test-automator"],
      "depends_on": [2]
    }
  ]
}
```

#### Response Example

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

The `ready_count` shows how many issues have no dependencies and are ready to start.

---

## Error Handling

All tools return errors in a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "additional": "context"
    }
  }
}
```

### Common Error Codes

| Code | Meaning | What To Do |
|------|---------|------------|
| `TASK_NOT_FOUND` | Task doesn't exist | Verify task_id is correct |
| `INVALID_STATUS` | Invalid status transition | Check current task status |
| `PERMISSION_DENIED` | Not authorized | Verify API key and task ownership |
| `BRANCH_NOT_FOUND` | Git branch doesn't exist | Ensure branch is pushed |
| `CONFLICT` | Operation conflicts with state | Retry or report blocker |

### Example Error Response

```json
{
  "error": {
    "code": "BRANCH_NOT_FOUND",
    "message": "Branch f/implement-auth/compute-001 does not exist in repository",
    "details": {
      "branch": "f/implement-auth/compute-001",
      "repository": "git@serving:project.git"
    }
  }
}
```

---

## Typical Workflow

Here's a typical task execution flow:

```
1. Compute receives SSE event: work_assigned
2. Compute calls claudevn_get_assignment
3. Claude Code spawned with CLAUDE.md + context
4. Claude Code starts work
5. claudevn_report_progress (25%)
6. claudevn_report_progress (50%)
7. claudevn_add_requirement (discovers new work)
8. claudevn_report_progress (75%)
9. claudevn_request_review
10. Review feedback received
11. Make changes
12. claudevn_complete_task
13. Serving merges branch
14. Compute gets new work assignment
```

---

## Tips and Best Practices

### Progress Reporting
- Report every 15-30 minutes on long tasks
- Include meaningful status messages
- Always include commit SHAs

### Blockers
- Signal blockers immediately (don't wait)
- Provide clear descriptions
- Suggest resolutions when possible

### New Requirements
- Only add truly necessary items
- Link dependencies correctly
- Be realistic about priority

### Task Completion
- Always run tests before completing
- Include comprehensive summaries
- List all deliverables

### Context Requests
- Request context as needed (not upfront)
- Use specific file patterns
- Prefer related_tasks over history for dependencies

---

## Related Documentation

- **[Compute Registration](../design/specifications/compute-registration.md)** - SSE and work assignment
- **[v1.0 Architecture](../design/architecture/v1.0-architecture.md)** - System overview
- **[Git Infrastructure](../design/specifications/git-infrastructure.md)** - Branch workflow
- **[Skill Marketplace](../design/specifications/skill-marketplace.md)** - Skills system
