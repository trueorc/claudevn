# Compute Authorization Audit

**Date**: 2026-02-13
**Type**: Standard Functional Audit
**Feature**: Claude Code Authorization for Compute Modules
**Result**: FAIL - Critical Multi-User Authorization Gaps

---

## Executive Summary

The ClaudeVN platform has **no multi-user credential support** for compute modules. The authentication architecture is fundamentally single-user by design. All local compute containers share one host user's Claude credentials via a hardcoded Docker volume mount. When a different user authenticates Claude CLI on the same host, their credentials are never forwarded to compute instances.

Additionally, several security gaps were identified: MCP auth bypass enabled in production config, missing read-only flags on credential mounts, in-memory API key storage, and no credential validation before work assignment.

---

## Findings

### F-001: No Multi-User Credential Support [Critical]

**Category**: Security / Design
**Files**: `docker-compose.yml`, `serving/services/compute_spawner.py`, `compute/services/claude_code_spawner.py`

**Finding**: The system assumes a single subscription owner. All compute containers mount the host user's `~/.claude` directory. When User B logs into Claude CLI, their credentials at `/home/userB/.claude/` are never mounted or accessed. Work assignment carries no user identity, so the system cannot route to the correct credentials.

**Impact**: Multi-user deployments are non-functional. All work executes under the host user's subscription regardless of who created the goal/task.

**Recommendation**: Implement per-user credential delegation with user_id propagation through the work assignment pipeline.

### F-002: Hardcoded Credential Mount Path [Critical]

**Category**: Functionality
**Files**: `docker-compose.yml:189,235,281`

**Finding**: Volume mounts use `~/.claude:/home/compute/.claude` which expands to the current host user's home directory at `docker compose up` time. This is static and cannot change without restarting containers.

**Impact**: Credentials from any user other than the one who started Docker are inaccessible.

**Recommendation**: Add user context to work assignment; implement dynamic credential mounting or credential injection per task.

### F-003: Missing Read-Only Flag on Credential Mounts [High]

**Category**: Security
**Files**: `docker-compose.yml:189,235,281`

**Finding**: Documentation (`docs/guides/docker-authentication.md`) states `:ro` flag is used, but actual mounts lack it. Containers have write access to the host's credential directory.

**Impact**: A compromised container could modify or delete host credentials.

**Recommendation**: Add `:ro` flag to all credential mounts: `~/.claude:/home/compute/.claude:ro`

### F-004: No User Identity in Work Assignment Flow [High]

**Category**: Design
**Files**: Work models, SSE events

**Finding**: Goal, Issue, WorkItem, and work_assigned SSE events contain no `user_id` or `owner_id` field. The system cannot determine which user's credentials to use for a given task.

**Impact**: Blocks multi-user support. No audit trail of which user owns which work.

**Recommendation**: Add user_id to Goal, Issue, and WorkItem models; propagate through SSE events.

### F-005: MCP Auth Bypass Enabled in Production Config [High]

**Category**: Security
**Files**: `docker-compose.yml:135`

**Finding**: `MCP_AUTH_BYPASS=true` is set in the main docker-compose.yml (not a test-only override). This allows any Bearer token to authenticate, bypassing all API key validation.

**Impact**: Any actor on the Docker network can register as a compute instance and receive work assignments.

**Recommendation**: Remove bypass from production config; create separate `docker-compose.test.yml` for integration tests.

### F-006: Fallback "Accept Any Key" When No Keys Registered [High]

**Category**: Security
**Files**: `serving/mcp/auth.py:77-79`

**Finding**: If `_compute_api_keys` dict is empty (e.g., after Serving restart), any Bearer token is accepted. The system fails open.

**Impact**: Window of vulnerability after every Serving restart until keys are re-registered.

**Recommendation**: Remove fallback; fail closed when no keys are registered. Require compute re-registration with proper key exchange.

### F-007: In-Memory API Key Storage [High]

**Category**: Functionality
**Files**: `serving/mcp/auth.py:22`

**Finding**: Compute API keys stored in Python dict `_compute_api_keys`. Lost on Serving restart.

**Impact**: All compute instances lose authentication after Serving restart. Requires full re-registration.

**Recommendation**: Persist keys to Redis with TTL (pattern: `claudevn:compute:apikey:{compute_id}`).

### F-008: No Credential Validation Before Spawning [Medium]

**Category**: Functionality
**Files**: `serving/services/compute_spawner.py:184`, `compute/services/claude_code_spawner.py:364`

**Finding**: Neither spawner checks credential validity before launching Claude Code. CredentialMonitor runs independently but doesn't gate work assignment.

**Impact**: Work assigned to compute with expired/missing credentials fails at execution time, wasting assignment cycles.

**Recommendation**: Add credential health check as a gate before work assignment.

### F-009: Documentation vs Implementation Mismatch [Medium]

**Category**: Documentation
**Files**: `docs/guides/docker-authentication.md`

**Finding**: Multiple mismatches:
- Docs say `:ro` flag is used; code doesn't have it
- Docs reference `/root/.claude` path; Dockerfile creates `/home/compute/.claude`
- MCP_AUTH_BYPASS described as "testing only" but enabled in production config

**Impact**: Operators following documentation get incorrect security posture.

**Recommendation**: Update documentation to match actual implementation, or fix implementation to match documented intent.

### F-010: External Node Credentials Isolated by Host, Not User [Medium]

**Category**: Design
**Files**: `docs/guides/docker-authentication.md`

**Finding**: External VCN nodes use their host's `~/.claude` credentials. There's no mechanism for multiple users on an external host to have their credentials routed correctly.

**Impact**: Same single-user limitation extends to external nodes.

**Recommendation**: Document limitation clearly; recommend dedicated external nodes per user/subscription.

### F-011: Credential Mount Path Inconsistency [Low]

**Category**: Documentation / Configuration
**Files**: `compute/Dockerfile:35`, `docker-compose.yml:189`, `docs/guides/docker-authentication.md`

**Finding**: Dockerfile creates `compute` user (uid 1000) with home at `/home/compute`. Docker-compose mounts to `/home/compute/.claude`. But documentation references `/root/.claude` in several places.

**Impact**: Confusion during troubleshooting; potential misconfiguration.

**Recommendation**: Standardize all references to `/home/compute/.claude`.

### F-012: Passive Credential Monitoring [Low]

**Category**: Observability
**Files**: `compute/services/credential_monitor.py`

**Finding**: CredentialMonitor checks health every 3600s and logs status, but Serving doesn't query this before assignment. Monitor is passive-only.

**Impact**: Degraded reliability; no proactive avoidance of credential-expired failures.

**Recommendation**: Expose credential status via API; Serving checks before assignment.

---

## Root Cause Analysis

### Why Another User's Credentials Aren't Picked Up

The bug flow:

1. **User A** authenticates: `claude /login` -> credentials at `/home/userA/.claude/`
2. **Docker Compose starts** (as User A): mounts `~/.claude:/home/compute/.claude`
3. **User B** logs into Claude CLI: credentials at `/home/userB/.claude/`
4. **User B creates a goal** via Serving UI
5. **Serving decomposes goal** -> creates issues -> assigns to Compute
6. **Work assignment event** (SSE) has NO user context
7. **Compute spawns Claude Code** using `/home/compute/.claude` (still User A's)
8. **Claude Code executes with User A's subscription**, NOT User B's
9. **User B's credentials are never accessed**

### Architecture Gap

```
[User A] --login--> /home/userA/.claude/.credentials.json
                              |
                              | (volume mount at docker startup)
                              v
                    Docker: ~/.claude -> /home/compute/.claude
                              ^
                              | (ALL compute instances use this)
                              |
[User B] --login--> /home/userB/.claude/.credentials.json  <-- NEVER MOUNTED
         --create goal-->  Serving
                           |
                           v (work assignment - no user_id)
                           Compute (uses User A's creds)
```

---

## Issues Created

Issues should be created for:

| Finding | Priority | Title |
|---------|----------|-------|
| F-001 | P0 | Implement per-user credential delegation for compute |
| F-005 | P0 | Remove MCP_AUTH_BYPASS from production docker-compose |
| F-003 | P1 | Add read-only flag to credential volume mounts |
| F-007 | P1 | Persist compute API keys to Redis |
| F-008 | P2 | Add credential validation gate before work assignment |
| F-011 | P2 | Fix credential mount path documentation inconsistencies |

---

## Recommendations

### Immediate (P0)
1. Remove `MCP_AUTH_BYPASS=true` from docker-compose.yml (security fix)
2. Design multi-user credential delegation architecture

### Short-term (P1)
3. Add `:ro` to credential mounts
4. Move API keys to Redis

### Medium-term (P2)
5. Credential validation before assignment
6. Fix documentation inconsistencies
7. Document multi-user limitations in README

### Long-term
8. Per-user compute pools with dedicated credential mounts
9. Credential rotation with zero-downtime handoff
10. Audit trail: log which user's credentials used for each task
