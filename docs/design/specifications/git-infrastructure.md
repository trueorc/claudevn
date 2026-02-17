# Git Infrastructure Design

**Version**: 1.0.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

ClaudeVN v1.0 uses Git as the primary mechanism for state management and file synchronization between Serving and Compute instances. This document specifies the Git infrastructure components.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SERVING GIT INFRASTRUCTURE                        │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ SSH Server      │  │ Bare Repository │  │ Redis               │  │
│  │                 │  │                 │  │                     │  │
│  │ Port: 22        │  │ /repos/         │  │ - Branch status     │  │
│  │ User: git       │  │   {project}.git │  │ - PR queue          │  │
│  │ Auth: SSH keys  │  │                 │  │ - Merge queue       │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘  │
│           │                    │                      │             │
│           └──────────┬─────────┴──────────────────────┘             │
│                      │                                              │
│           ┌──────────▼──────────┐  ┌───────────────────────────────┐  │
│           │ Git Hooks           │  │ Git REST API                  │  │
│           │                     │  │                               │  │
│           │ - pre-receive       │  │ POST /api/v1/git/prs          │  │
│           │ - post-receive      │  │ GET  /api/v1/git/prs/{project}│  │
│           │                     │  │ POST .../prs/{p}/{b}/merge    │  │
│           └─────────────────────┘  └───────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. SSH Server

**Purpose**: Secure Git transport for push/pull operations.

#### Configuration

```bash
# Dedicated git user
useradd -m -s /usr/bin/git-shell git

# Repository directory
mkdir -p /home/git/repos

# SSH directory
mkdir -p /home/git/.ssh
chmod 700 /home/git/.ssh
```

#### Authorized Keys Management

Each compute instance receives an SSH key pair. Serving manages `/home/git/.ssh/authorized_keys`:

```
# Format: restrict commands, identify compute
command="git-shell -c \"$SSH_ORIGINAL_COMMAND\"",no-port-forwarding,no-agent-forwarding ssh-ed25519 AAAA... compute-001
command="git-shell -c \"$SSH_ORIGINAL_COMMAND\"",no-port-forwarding,no-agent-forwarding ssh-ed25519 AAAA... compute-002
```

#### Security Constraints

- No shell access (git-shell only)
- No port forwarding
- No agent forwarding
- Key-based auth only (no passwords)

### 2. Bare Repository

**Purpose**: Canonical source of truth for project code.

#### Structure

```
/home/git/repos/
└── {project}.git/
    ├── HEAD                    # Points to main
    ├── config                  # Repository config
    ├── description             # Project description
    ├── hooks/
    │   ├── pre-receive         # Validation hook
    │   └── post-receive        # Notification hook
    ├── info/
    │   └── exclude             # Patterns to exclude
    ├── objects/                # Git objects
    │   ├── info/
    │   └── pack/
    └── refs/
        ├── heads/              # Branch refs
        │   ├── main
        │   ├── f/task-1/compute-001
        │   └── ...
        └── tags/               # Tag refs
```

#### Initialization

```bash
# Create bare repository
cd /home/git/repos
git init --bare {project}.git
chown -R git:git {project}.git

# Set default branch
cd {project}.git
git symbolic-ref HEAD refs/heads/main
```

### 3. Git Hooks

#### pre-receive Hook

**Purpose**: Validate pushes before accepting.

```bash
#!/bin/bash
# /home/git/repos/{project}.git/hooks/pre-receive

while read oldrev newrev refname; do
  branch=$(echo $refname | sed 's|refs/heads/||')

  # STRICTLY block direct pushes to main/master
  # Compute instances can NEVER push to main - only Serving (via merge process)
  if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    echo "ERROR: Direct push to $branch is FORBIDDEN."
    echo "       Only Serving can merge to main."
    exit 1
  fi

  # Validate branch naming convention: {type}/issue-{id}/{compute-id}
  # Types: f (feature), b (bugfix), r (refactor), d (docs)
  if ! [[ "$branch" =~ ^[fbrd]/issue-[0-9]+/compute-[0-9]+$ ]]; then
    echo "ERROR: Invalid branch name: $branch"
    echo "       Format: {type}/issue-{id}/{compute-id}"
    echo "       Types: f (feature), b (bugfix), r (refactor), d (docs)"
    echo "       Example: f/issue-100/compute-001"
    exit 1
  fi

  # Extract compute ID from branch name
  compute_id=$(echo "$branch" | grep -oP 'compute-[0-9]+$')

  # Verify compute ID matches SSH key identity (from SSH_ORIGINAL_COMMAND env)
  # This prevents compute-001 from pushing to compute-002's branches
  if [ -n "$GIT_PUSH_COMPUTE_ID" ] && [ "$compute_id" != "$GIT_PUSH_COMPUTE_ID" ]; then
    echo "ERROR: $GIT_PUSH_COMPUTE_ID cannot push to $compute_id's branch"
    exit 1
  fi
done

exit 0
```

#### post-receive Hook

**Purpose**: Notify Redis of new pushes.

```bash
#!/bin/bash
# /home/git/repos/{project}.git/hooks/post-receive

# Load Redis connection from environment
REDIS_HOST=${REDIS_HOST:-localhost}
REDIS_PORT=${REDIS_PORT:-6379}

while read oldrev newrev refname; do
  branch=$(echo $refname | sed 's|refs/heads/||')
  project=$(basename $(pwd) .git)
  timestamp=$(date -Iseconds)

  # Skip main branch (shouldn't happen due to pre-receive, but be safe)
  if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
    continue
  fi

  # Publish push event
  redis-cli -h $REDIS_HOST -p $REDIS_PORT PUBLISH "git:${project}:push" \
    "{\"branch\":\"$branch\",\"commit\":\"$newrev\",\"timestamp\":\"$timestamp\"}"

  # Update or create branch metadata
  redis-cli -h $REDIS_HOST -p $REDIS_PORT HSETNX "branch:${project}:${branch}" status "pending"
  redis-cli -h $REDIS_HOST -p $REDIS_PORT HSET "branch:${project}:${branch}" \
    last_commit "$newrev" \
    updated_at "$timestamp"

  # Log the push
  echo "Branch $branch updated to $newrev"
done

exit 0
```

### 4. Redis Schema

#### Branch Metadata

```
# Key: branch:{project}:{branch_name}
# Type: Hash

HSET branch:myproject:f/auth/compute-001
  status         "pending"           # pending|in_review|approved|rejected|merged|conflict
  compute_id     "compute-001"       # Owning compute instance
  task_id        "task-456"          # Associated task ID
  created_at     "2026-01-25T10:00:00Z"
  updated_at     "2026-01-25T14:30:00Z"
  last_commit    "abc123def456"      # Latest commit SHA
  reviewer       ""                  # Reviewer compute ID (if in review)
  rejection_reason ""                # Reason if rejected
```

#### PR Queue

```
# Key: pr_queue:{project}
# Type: Sorted Set (score = timestamp)

ZADD pr_queue:myproject 1706180400 "f/auth/compute-001"
ZADD pr_queue:myproject 1706180500 "f/api/compute-002"

# Get oldest PRs first
ZRANGE pr_queue:myproject 0 9
```

#### Merge Queue

```
# Key: merge_queue:{project}
# Type: List (FIFO)

LPUSH merge_queue:myproject "f/auth/compute-001"  # Add to queue
RPOP merge_queue:myproject                         # Get next to merge
```

#### Compute Branch Tracking

```
# Key: compute:{compute_id}:branches
# Type: Set

SADD compute:compute-001:branches "f/auth/compute-001" "f/tests/compute-001"
SMEMBERS compute:compute-001:branches
```

#### Pub/Sub Channels

```
# Push notifications
SUBSCRIBE git:{project}:push
# Message: {"branch": "f/auth/compute-001", "commit": "abc123", "timestamp": "..."}

# Status changes
SUBSCRIBE git:{project}:status
# Message: {"branch": "f/auth/compute-001", "status": "approved", "reviewer": "compute-002"}

# Merge completions
SUBSCRIBE git:{project}:merged
# Message: {"branch": "f/auth/compute-001", "merge_commit": "def456"}
```

---

## Git REST API

All Git-related endpoints are prefixed with `/api/v1/git`. The API is project-scoped, meaning most PR and queue operations require a `{project}` path parameter.

### Repository Endpoints

#### Create Repository

```
POST /api/v1/git/repos
Content-Type: application/json

{
  "project": "myproject",
  "install_hooks": true
}

Response:
{
  "project": "myproject",
  "ssh_url": "git@serving:/repos/myproject.git",
  "exists": true
}
```

#### List Repositories

```
GET /api/v1/git/repos

Response:
["myproject", "another-project"]
```

#### Get Repository

```
GET /api/v1/git/repos/{project}

Response:
{
  "project": "myproject",
  "ssh_url": "git@serving:/repos/myproject.git",
  "exists": true
}
```

#### Delete Repository

```
DELETE /api/v1/git/repos/{project}

Response:
{
  "status": "deleted",
  "project": "myproject"
}
```

#### List Branches

```
GET /api/v1/git/repos/{project}/branches

Response:
["main", "f/auth/compute-001", "f/api/compute-002"]
```

#### Get Repository Status

```
GET /api/v1/git/repos/{project}/status

Response:
{
  "project": "myproject",
  "path": "/repos/myproject.git",
  "ssh_url": "git@serving:/repos/myproject.git",
  "origin_url": null,
  "default_branch": "main",
  "branches": ["main", "f/auth/compute-001"],
  "branch_count": 2,
  "is_mirror": false,
  "exists": true,
  "hooks_installed": true,
  "hooks": {
    "project": "myproject",
    "hooks_installed": true,
    "pre_receive": {"exists": true, "executable": true, "path": "/repos/myproject.git/hooks/pre-receive"},
    "post_receive": {"exists": true, "executable": true, "path": "/repos/myproject.git/hooks/post-receive"}
  }
}
```

#### Get Hook Status

```
GET /api/v1/git/repos/{project}/hooks

Response:
{
  "project": "myproject",
  "hooks_installed": true,
  "pre_receive": {"exists": true, "executable": true, "path": "..."},
  "post_receive": {"exists": true, "executable": true, "path": "..."}
}
```

#### Install Hooks

```
POST /api/v1/git/repos/{project}/hooks

Response:
{
  "project": "myproject",
  "success": true,
  "message": "Hooks successfully installed for myproject"
}
```

#### Migrate Hooks (All Repositories)

```
POST /api/v1/git/repos/hooks/migrate

Response:
{
  "total": 5,
  "success": 5,
  "failed": 0,
  "results": {"myproject": "success", "another": "success", ...}
}
```

### SSH Key Endpoints

#### Register SSH Key

```
POST /api/v1/git/ssh/keys
Content-Type: application/json

{
  "compute_id": "compute-001",
  "public_key": "ssh-ed25519 AAAA... compute-001"
}

Response:
{
  "status": "registered",
  "compute_id": "compute-001",
  "message": "SSH key registered"
}
```

#### Revoke SSH Key

```
DELETE /api/v1/git/ssh/keys/{compute_id}

Response:
{
  "status": "revoked",
  "compute_id": "compute-001"
}
```

#### List Registered Keys

```
GET /api/v1/git/ssh/keys

Response:
["compute-001", "compute-002", "compute-003"]
```

#### Generate Key Pair

```
POST /api/v1/git/ssh/keys/{compute_id}/generate

Response:
{
  "compute_id": "compute-001",
  "public_key": "ssh-ed25519 AAAA... compute-001",
  "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
}
```

### SSH Server Endpoints

#### Get Server Status

```
GET /api/v1/git/ssh/server/status

Response:
{
  "running": true,
  "port": 2222,
  "host_key_fingerprint": "SHA256:...",
  "authorized_keys_count": 5
}
```

#### Get Clone URL

```
GET /api/v1/git/ssh/server/clone-url/{project}

Response:
{
  "project": "myproject",
  "clone_url": "ssh://git@serving:2222/repos/myproject.git"
}
```

### Pull Request Endpoints

All PR endpoints are project-scoped with the format `/api/v1/git/prs/{project}/...`.

#### Create PR

```
POST /api/v1/git/prs
Content-Type: application/json

{
  "project": "myproject",
  "branch": "f/auth/compute-001",
  "compute_id": "compute-001",
  "task_id": "task-456",
  "title": "Implement user authentication",
  "description": "Added login/logout endpoints with JWT support"
}

Response:
{
  "project": "myproject",
  "branch": "f/auth/compute-001",
  "status": "pending",
  "compute_id": "compute-001",
  "task_id": "task-456",
  "title": "Implement user authentication",
  "description": "Added login/logout endpoints with JWT support",
  "head_commit": "abc123def",
  "base_branch": "main",
  "queue_position": 3,
  "created_at": "2026-01-25T14:30:00Z",
  "updated_at": "2026-01-25T14:30:00Z",
  "reviewed_by": null,
  "merged_at": null
}
```

#### List PRs for Project

```
GET /api/v1/git/prs/{project}?status=in_review&compute_id=compute-001

Query parameters (optional):
- status: Filter by status (pending, in_review, approved, rejected, merged, conflict)
- compute_id: Filter by compute instance

Response:
[
  {
    "project": "myproject",
    "branch": "f/auth/compute-001",
    "status": "in_review",
    "compute_id": "compute-001",
    "task_id": "task-456",
    "title": "Implement user authentication",
    "description": "Added login/logout endpoints",
    "head_commit": "abc123def",
    "base_branch": "main",
    "queue_position": 1,
    "created_at": "2026-01-25T10:00:00Z",
    "updated_at": "2026-01-25T14:30:00Z",
    "reviewed_by": null,
    "merged_at": null
  }
]
```

#### Get PR Details

```
GET /api/v1/git/prs/{project}/{branch}

Response:
{
  "project": "myproject",
  "branch": "f/auth/compute-001",
  "status": "in_review",
  "compute_id": "compute-001",
  "task_id": "task-456",
  "title": "Implement user authentication",
  "description": "Added login/logout endpoints",
  "head_commit": "abc123def",
  "base_branch": "main",
  "queue_position": 1,
  "created_at": "2026-01-25T10:00:00Z",
  "updated_at": "2026-01-25T14:30:00Z",
  "reviewed_by": null,
  "merged_at": null
}
```

#### Update PR Status

```
PATCH /api/v1/git/prs/{project}/{branch}
Content-Type: application/json

{
  "status": "in_review",
  "reviewed_by": "compute-002"
}

Response:
{
  "project": "myproject",
  "branch": "f/auth/compute-001",
  "status": "in_review",
  ...
}
```

#### Approve PR

```
POST /api/v1/git/prs/{project}/{branch}/approve?reviewed_by=compute-002

Response:
{
  "project": "myproject",
  "branch": "f/auth/compute-001",
  "status": "approved",
  "reviewed_by": "compute-002",
  ...
}
```

#### Reject PR

```
POST /api/v1/git/prs/{project}/{branch}/reject?reviewed_by=compute-002

Response:
{
  "project": "myproject",
  "branch": "f/auth/compute-001",
  "status": "rejected",
  "reviewed_by": "compute-002",
  ...
}
```

#### Merge PR

```
POST /api/v1/git/prs/{project}/{branch}/merge
Content-Type: application/json

{
  "delete_branch": true
}

Response (success):
{
  "success": true,
  "merged_commit": "def456789abc",
  "branch": "f/auth/compute-001",
  "deleted": true,
  "error": null
}

Response (failure):
{
  "success": false,
  "merged_commit": null,
  "branch": "f/auth/compute-001",
  "deleted": false,
  "error": "Merge conflict with main"
}
```

#### Check Mergeability

```
GET /api/v1/git/prs/{project}/{branch}/mergeable

Response:
{
  "mergeable": true,
  "reason": null
}
```

### Queue Endpoints

#### Get PR Queue

```
GET /api/v1/git/queues/{project}/prs

Response:
[
  {"project": "myproject", "branch": "f/auth/compute-001", "status": "approved", ...},
  {"project": "myproject", "branch": "f/api/compute-002", "status": "approved", ...}
]
```

#### Get Merge Queue

```
GET /api/v1/git/queues/{project}/merges

Response:
["f/auth/compute-001", "f/api/compute-002"]
```

#### Process Merge Queue

```
POST /api/v1/git/queues/{project}/process-merges

Response:
[
  {"branch": "f/auth/compute-001", "success": true, "merged_commit": "abc123"},
  {"branch": "f/api/compute-002", "success": false, "error": "Conflict"}
]
```

### Compute Integration Endpoints

#### Get Compute PRs

```
GET /api/v1/git/compute/{compute_id}/prs

Response:
[
  {"project": "myproject", "branch": "f/auth/compute-001", "status": "merged", ...},
  {"project": "another", "branch": "f/tests/compute-001", "status": "pending", ...}
]
```

#### Cleanup Compute

Called when a compute instance is deregistered to close all pending PRs.

```
POST /api/v1/git/compute/{compute_id}/cleanup

Response:
{
  "compute_id": "compute-001",
  "prs_closed": 2
}
```

---

## Merge Process

### Algorithm

```python
async def merge_branch(project: str, branch: str) -> MergeResult:
    repo_path = f"/home/git/repos/{project}.git"
    work_dir = f"/tmp/merge-work/{project}-{uuid4()}"

    try:
        # 1. Clone to temp work directory
        subprocess.run([
            "git", "clone", repo_path, work_dir
        ], check=True)

        # 2. Checkout main
        subprocess.run([
            "git", "-C", work_dir, "checkout", "main"
        ], check=True)

        # 3. Attempt merge
        result = subprocess.run([
            "git", "-C", work_dir,
            "merge", "--no-ff", f"origin/{branch}",
            "-m", f"Merge {branch} into main\n\nPR merged by ClaudeVN"
        ], capture_output=True)

        if result.returncode != 0:
            # Conflict detected
            subprocess.run(["git", "-C", work_dir, "merge", "--abort"])

            # Get conflicting files
            conflicts = parse_conflict_files(result.stderr)

            # Update Redis
            await redis.hset(f"branch:{project}:{branch}", mapping={
                "status": "conflict",
                "rejection_reason": f"Merge conflict: {', '.join(conflicts)}"
            })

            # Notify compute
            await redis.publish(f"git:{project}:status", json.dumps({
                "branch": branch,
                "status": "conflict",
                "message": "Rebase required",
                "conflicting_files": conflicts
            }))

            return MergeResult(success=False, reason="conflict", files=conflicts)

        # 4. Push merged main back to bare repo
        subprocess.run([
            "git", "-C", work_dir, "push", "origin", "main"
        ], check=True)

        # 5. Get merge commit
        merge_commit = subprocess.run([
            "git", "-C", work_dir, "rev-parse", "HEAD"
        ], capture_output=True, text=True).stdout.strip()

        # 6. Update Redis
        await redis.hset(f"branch:{project}:{branch}", mapping={
            "status": "merged",
            "merge_commit": merge_commit,
            "merged_at": datetime.utcnow().isoformat()
        })

        # 7. Notify
        await redis.publish(f"git:{project}:merged", json.dumps({
            "branch": branch,
            "merge_commit": merge_commit
        }))

        return MergeResult(success=True, merge_commit=merge_commit)

    finally:
        # Cleanup temp directory
        shutil.rmtree(work_dir, ignore_errors=True)
```

---

## Compute Workflow

**Key constraint:** One Claude Code instance per Compute Infra at a time. No worktrees needed - simple branch workflow.

**Golden rule:** Compute NEVER pushes to main. Only Serving merges to main.

### Setup (On Work Assignment)

```bash
# Clone repository (if not already cloned)
git clone git@serving:/home/git/repos/{project}.git /workspace

# Or if already cloned, ensure clean state
cd /workspace
git fetch origin
git checkout main
git reset --hard origin/main
```

### Task Execution

```bash
# 1. Create feature branch from main
cd /workspace
git checkout -b f/issue-100/compute-001

# 2. Work (Claude Code does its thing)
# ... make changes ...
git add -A
git commit -m "Implement feature X"

# 3. Self-review (before submitting)
# - Run tests
# - Check linting
# - Review own code for issues
# This is part of the skill instructions, not a separate tool

# 4. Push branch to Serving
git push -u origin f/issue-100/compute-001

# 5. Signal completion (via MCP)
claudevn_complete_task(task_id="issue-100", branch="f/issue-100/compute-001")
```

### Serving Validation

When Serving receives `claudevn_complete_task`:

1. **Conflict detection** - Attempt dry-run merge to main
2. **Basic checks** - Tests passed? (from payload)
3. **If clean** → Merge to main, mark issue done
4. **If conflicts** → Push `merge_conflict` event to Compute

### Conflict Resolution (Push-Back Model)

Serving pushes conflict notification to Compute via SSE:

```json
event: merge_conflict
data: {
  "issue_id": "issue-100",
  "branch": "f/issue-100/compute-001",
  "conflicting_files": ["src/models/user.py", "src/api/auth.py"],
  "main_head": "abc123",
  "message": "Resolve conflicts with main and push again"
}
```

Compute receives and resolves:

```bash
# 1. Fetch latest main
git fetch origin main

# 2. Rebase onto main
git rebase origin/main

# 3. Resolve conflicts
# ... fix conflicts in indicated files ...
git add -A
git rebase --continue

# 4. Force push (safe - it's our branch)
git push --force-with-lease origin f/issue-100/compute-001

# 5. Signal ready again (via MCP)
claudevn_report_progress(task_id="issue-100", status="conflicts_resolved")
```

Serving re-validates. Loop until clean merge.

### Flow Diagram

```
Compute                              Serving
   │                                    │
   │  work (branch)                     │
   │  self-review                       │
   │  push branch ──────────────────►   │
   │  claudevn_complete_task() ──────►   │
   │                                    │  conflict check
   │                                    │
   │  ◄────────── merge_conflict (SSE)  │  (if conflicts)
   │                                    │
   │  fetch, rebase, resolve            │
   │  push branch ──────────────────►   │
   │  claudevn_report_progress() ────►   │
   │                                    │  conflict check
   │                                    │
   │                                    │  merge to main (if clean)
   │  ◄────────── work_completed (SSE)  │
   │                                    │
```

---

## File Structure (Serving)

```
serving/
├── git/
│   ├── __init__.py
│   ├── config.py             # Git server configuration
│   ├── ssh_key_manager.py    # Manage compute SSH keys
│   ├── repo_manager.py       # Create/manage bare repos
│   ├── hooks/
│   │   ├── pre-receive       # Validation hook template
│   │   └── post-receive      # Notification hook template
│   ├── pr_service.py         # PR queue management
│   ├── merge_service.py      # Merge execution
│   └── redis_client.py       # Redis connection
├── api/
│   └── git.py                # Git/PR REST endpoints
└── ...
```

---

## Related Documents

- [v1.0 Architecture](../architecture/v1.0-architecture.md)
- [MCP Tools Specification](./mcp-tools.md)
- [Compute Registration](./compute-registration.md)
- [WorkMap Specification](./workmap.md)
