# SSH Server Architecture

**Version**: 1.0.0
**Status**: Design Specification
**Related**: Issue #40, git-infrastructure.md

---

## Overview

The SSH server is the **bridge** between Serving and Compute components, enabling Git-based code synchronization. This document explains how the SSH server supports both components.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SERVING                                         │
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐   │
│  │ SSH Server       │    │ SSHKeyManager    │    │ Bare Repositories    │   │
│  │ (Port 2222)      │◄───│                  │    │ /repos/{project}.git │   │
│  │                  │    │ - Generate keys  │    │                      │   │
│  │ - git-shell only │    │ - Register keys  │    │ ┌────────────────┐   │   │
│  │ - Key auth       │    │ - Revoke keys    │    │ │ hooks/         │   │   │
│  │ - No shell       │    │ - authorized_keys│    │ │ - pre-receive  │   │   │
│  └────────┬─────────┘    └──────────────────┘    │ │ - post-receive │   │   │
│           │                                       │ └────────────────┘   │   │
│           │              ┌──────────────────┐    └──────────────────────┘   │
│           │              │ PRService        │              │                │
│           │              │                  │◄─────────────┘                │
│           │              │ - Branch status  │    (post-receive publishes)   │
│           │              │ - PR queue       │                               │
│           │              │ - Merge queue    │    ┌──────────────────────┐   │
│           │              └──────────────────┘    │ Redis                │   │
│           │                      │               │                      │   │
│           │                      └──────────────►│ - branch:{proj}:{br} │   │
│           │                                      │ - pr_queue:{proj}    │   │
│           │                                      │ - Pub/Sub channels   │   │
│           │                                      └──────────────────────┘   │
└───────────┼─────────────────────────────────────────────────────────────────┘
            │
            │ SSH/Git Protocol
            │ git push / git pull
            │
┌───────────┼─────────────────────────────────────────────────────────────────┐
│           ▼                        COMPUTE                                   │
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐   │
│  │ SSH Client       │    │ Git Repository   │    │ MCP Client           │   │
│  │                  │    │                  │    │                      │   │
│  │ - Private key    │    │ /workspace/      │    │ - claudevn_report_    │   │
│  │ - Known hosts    │    │   (clone)        │    │   progress           │   │
│  │ - Git remote     │    │   feature branch │    │ - claudevn_complete_  │   │
│  └──────────────────┘    └──────────────────┘    │   task               │   │
│                                                   │ - claudevn_signal_    │   │
│                                                   │   blocker            │   │
│  ┌─────────────────────────────────────────────┐ └──────────────────────┘   │
│  │ Claude Code Instance                         │                           │
│  │                                              │                           │
│  │ CLAUDE.md defines:                           │                           │
│  │ - Persona/skills                             │                           │
│  │ - Git workflow instructions                  │                           │
│  │ - MCP tools available                        │                           │
│  └──────────────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## How Serving Uses the SSH Server

### 1. Repository Hosting

Serving hosts **bare Git repositories** that compute instances push to and pull from:

```
/repos/
├── project-alpha.git/
│   ├── HEAD
│   ├── config
│   ├── hooks/
│   │   ├── pre-receive    # Validation
│   │   └── post-receive   # Redis notifications
│   ├── objects/
│   └── refs/
│       └── heads/
│           ├── main
│           ├── f/task-1/compute-001
│           └── f/task-2/compute-002
└── project-beta.git/
    └── ...
```

### 2. Access Control (pre-receive hook)

The SSH server ensures only valid operations occur:

```bash
# pre-receive hook responsibilities:
1. Block direct pushes to main/master
2. Validate branch naming: {type}/{task-slug}/{compute-id}
3. Verify compute can only push to its own branches
4. Reject invalid commits (optional: signing verification)
```

### 3. Event Publishing (post-receive hook)

After accepting a push, Serving notifies the system:

```bash
# post-receive hook actions:
1. Publish to Redis: git:{project}:push
2. Update branch metadata: branch:{project}:{branch}
3. Log push for audit trail
```

### 4. Key Management

SSHKeyManager maintains the authorized_keys file:

```python
# When compute spawns:
ssh_manager.register_key(compute_id, public_key)

# When compute stops:
ssh_manager.revoke_key(compute_id)
```

---

## How Compute Uses the SSH Server

### 1. Initial Setup (at spawn time)

When ComputeSpawner creates a new instance:

```python
async def spawn(self, request: SpawnRequest):
    # 1. Generate SSH key pair
    private_key, public_key = ssh_manager.generate_key_pair(compute_id)

    # 2. Register public key with Serving
    ssh_manager.register_key(compute_id, public_key)

    # 3. Provision private key to workspace
    workspace = Path(f"/workspaces/{compute_id}")
    (workspace / ".ssh" / "id_ed25519").write_text(private_key)

    # 4. Configure git remote
    git_config = f"""
    [remote "origin"]
        url = git@serving:{project}.git
        fetch = +refs/heads/*:refs/remotes/origin/*
    """
```

### 2. Simple Branch Workflow

Each Compute handles one task at a time using a simple branch workflow (no worktrees):

```bash
# Initial clone (done once per compute)
git clone git@serving:/repos/{project}.git /workspace
cd /workspace
```

### 3. Task Execution Flow

```bash
# 1. Receive assignment via SSE (work_assigned event)
# Assignment includes: task_id, branch_name, skills, context

# 2. Ensure clean state and create feature branch
cd /workspace
git fetch origin
git checkout main
git reset --hard origin/main
git checkout -b f/implement-auth/compute-001

# 3. Do work (Claude Code implements changes)
# ... make changes ...
git add -A
git commit -m "Implement user authentication"

# 4. Push to Serving
git push -u origin f/implement-auth/compute-001
# → SSH server accepts push
# → pre-receive validates branch name
# → post-receive publishes Redis event

# 5. Signal completion (via MCP)
claudevn_complete_task(task_id="...", branch="f/implement-auth/compute-001")
```

### 4. Conflict Resolution

When Serving detects a merge conflict, it pushes a `merge_conflict` SSE event:

```bash
# Compute receives merge_conflict event with conflicting_files list

# 1. Fetch latest main
git fetch origin main

# 2. Rebase feature branch
git rebase origin/main

# 3. Resolve conflicts (Claude Code handles this)
# ... fix conflicts in indicated files ...
git add -A
git rebase --continue

# 4. Force push (safe - it's our branch)
git push --force-with-lease origin f/implement-auth/compute-001

# 5. Signal resolution (via MCP)
claudevn_report_progress(task_id="...", status="conflicts_resolved")
```

---

## Security Model

### Authentication

| Method | Purpose |
|--------|---------|
| SSH Keys | Authenticate compute instances |
| No Passwords | Disable password auth entirely |
| Key Rotation | Revoke on compute stop/failure |

### Authorization

| Rule | Enforcement |
|------|-------------|
| No shell access | git-shell only |
| No port forwarding | SSH config restrictions |
| Branch ownership | pre-receive hook validates compute ID in branch name |
| Main protected | pre-receive blocks main/master pushes |

### Key Restrictions in authorized_keys

```
command="git-shell -c \"$SSH_ORIGINAL_COMMAND\"",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... compute-001
```

---

## Implementation Components

### Serving Side

| Component | Location | Status | Purpose |
|-----------|----------|--------|---------|
| SSHKeyManager | `serving/git/ssh_key_manager.py` | ✅ Complete | Key generation & registration |
| RepoManager | `serving/git/repo_manager.py` | ✅ Complete | Bare repo management |
| PRService | `serving/git/pr_service.py` | ✅ Complete | Branch/PR tracking in Redis |
| SSH Server | `serving/git/ssh_server.py` | ❌ TODO | SSH daemon wrapper |
| Git Hooks | `serving/git/hooks/` | ❌ TODO | pre-receive, post-receive |

### Compute Side

| Component | Location | Status | Purpose |
|-----------|----------|--------|---------|
| ComputeSpawner | `serving/services/compute_spawner.py` | ⚠️ Partial | Needs SSH key provisioning |
| MCP Tools | `serving/mcp/tools/` | ✅ Complete | request_review, etc. |
| Git Clone | (in compute workspace) | ✅ Simple | Clone repo, work on branch |

---

## Configuration

### Serving SSH Server Config

```yaml
# config.yaml
git:
  ssh:
    enabled: true
    port: 2222                    # Non-root port
    host_key: /etc/ssh/ssh_host_ed25519_key
    authorized_keys: /data/ssh/authorized_keys
    shell: /usr/bin/git-shell
    repos_path: /repos
```

### Compute Git Config

```ini
# .gitconfig in compute workspace
[core]
    sshCommand = ssh -i /workspace/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new

[remote "origin"]
    url = ssh://git@serving:2222/repos/{project}.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

---

## Data Flow Summary

### Push Flow (Compute → Serving)

```
1. Compute: git push origin f/task/compute-001
2. SSH Server: Authenticate via authorized_keys
3. git-shell: Execute git-receive-pack
4. pre-receive: Validate branch, block main
5. Git: Accept objects, update refs
6. post-receive: Publish to Redis
7. PRService: Update branch metadata
```

### Pull Flow (Compute ← Serving)

```
1. Compute: git pull origin main
2. SSH Server: Authenticate
3. git-shell: Execute git-upload-pack
4. Git: Send objects
5. Compute: Update local refs
```

### Review Flow (Hybrid)

```
1. Compute: git push (SSH)
2. Serving: post-receive updates Redis
3. Compute: claudevn_request_review (MCP/HTTP)
4. Serving: PRService adds to review queue
5. (Review happens)
6. Serving: Merge to main
7. Serving: Publish git:{project}:merged
8. Compute: Receives notification, can pull
```

---

## Implementation Recommendations

### Phase 1: SSH Server (This Issue)

1. **Approach**: Use system OpenSSH with custom config
   - Simpler than Paramiko
   - Battle-tested security
   - Easy to configure

2. **Key Files**:
   - `serving/git/ssh_server.py` - Start/stop/manage sshd
   - `serving/git/hooks/pre-receive` - Validation hook
   - `serving/git/hooks/post-receive` - Notification hook

3. **Integration**:
   - Add to `serving/app.py` startup
   - Sync authorized_keys on compute spawn/stop

### Phase 2: Compute Provisioning (Related)

1. Generate SSH key pair at spawn
2. Register public key
3. Provision private key to workspace
4. Configure git remote with SSH URL
5. Clone repository to workspace

---

## Testing Strategy

### Unit Tests

- SSHKeyManager key generation
- authorized_keys formatting
- Hook scripts (shell testing)

### Integration Tests

- SSH connection with valid key
- SSH rejection with invalid key
- Push with valid branch name
- Push rejection (main branch)
- post-receive Redis publication

### E2E Tests

- Full flow: spawn → push → review → merge
- Conflict detection and resolution

---

## Related Documents

- [Git Infrastructure](./git-infrastructure.md) - Overall Git design
- [MCP Tools](./mcp-tools.md) - MCP tools specification
- [Compute Registration](./compute-registration.md) - SSE connection and work push
