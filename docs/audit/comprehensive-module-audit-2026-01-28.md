# ClaudeVN Comprehensive Module Audit

**Date:** 2026-01-28
**Version:** v1.0 Architecture vs Current Implementation
**Type:** Deep Audit (Functional + Architecture)
**Status:** Complete

---

## Executive Summary

ClaudeVN is in a transitional state between v0.x (Python runtime) and v1.0 (Claude Code-powered) architectures. This audit examines all three modules (Serving, Compute, Marketplace) to identify what works, what doesn't, and what blocks end-to-end testing.

**Key Findings:**
- **Serving:** 63% of capabilities working (17/27)
- **Compute:** Wrong architecture entirely (v0.x Python, not Claude Code)
- **Marketplace:** 100% working but wrong architecture (standalone vs embedded)

**Primary E2E Blockers:**
1. Compute module is v0.x Python runtime, not Claude Code CLI
2. No SSH Git server for branch push/pull
3. Git worktrees not implemented

---

## 1. Module Capability Matrix

### 1.1 SERVING (Port 8002)

| Capability | Status | Notes |
|------------|--------|-------|
| **Work Map Service** | ✅ Working | Full CRUD, assignment algorithm, dependency tracking, blocker management |
| **Work Orchestrator** | ✅ Working | Background polling, automatic work assignment to compute instances |
| **Compute Spawner** | ⚠️ Partial | Spawns processes, creates CLAUDE.md, MCP config - but for wrong compute type |
| **Compute Registry** | ✅ Working | Instance registration, heartbeat tracking, health monitoring |
| **MCP Server** | ⚠️ Partial | 7 tools registered, HTTP endpoint working, auth implemented |
| **MCP: claudevn_get_assignment** | ✅ Working | Queries Work Map, returns assignments |
| **MCP: claudevn_report_progress** | ✅ Working | Updates work status, validates transitions |
| **MCP: claudevn_request_review** | ✅ Working | Creates PR in Redis queue |
| **MCP: claudevn_get_context** | ⚠️ Partial | Returns work details but limited context gathering |
| **MCP: claudevn_signal_blocker** | ✅ Working | Adds blockers to work items |
| **MCP: claudevn_complete_task** | ✅ Working | Marks work complete, unblocks dependents |
| **MCP: claudevn_get_persona** | ⚠️ Partial | Calls external Marketplace HTTP API |
| **PR Service** | ✅ Working | Redis-backed queue, status transitions, conflict detection |
| **PR Merge** | ✅ Working | Merges branches via Git commands, updates Redis |
| **Git Repository Manager** | ✅ Working | Creates bare repos, manages refs |
| **SSH Git Server** | ❌ Missing | CRITICAL: No SSH daemon for compute git push/pull |
| **SSH Key Manager** | ⚠️ Partial | Manages authorized_keys file but no daemon uses it |
| **Git Hooks** | ❌ Missing | Templates exist in docs, not deployed |
| **Persona/Skill API** | ❌ Missing | No `/api/v1/personas` endpoints (uses Marketplace client) |
| **Project Service** | ⚠️ Partial | API exists but git clone/worktree setup incomplete |
| **Frontend UI** | ✅ Working | React app with Network, Work, Projects pages |
| **WebSocket Monitoring** | ❌ Missing | Real-time updates not implemented |
| **Marketplace Client** | ✅ Working | HTTP client to external Marketplace service |
| **Health Monitoring** | ✅ Working | Background service monitoring compute health |
| **Event Bus** | ✅ Working | Observability events from compute instances |
| **Cache Backend** | ✅ Working | Filesystem-based caching |
| **Data Provider** | ✅ Working | Filesystem-based data persistence |

**Score:** 17/27 (63%)

---

### 1.2 COMPUTE (Port 8001)

| Capability | Status | Notes |
|------------|--------|-------|
| **Architecture Match** | ❌ WRONG | v0.x Python runtime, NOT Claude Code CLI as v1.0 requires |
| **Agent Registry** | ✅ Working | Loads JSON agent definitions from disk |
| **Tool Registry** | ✅ Working | Loads tool definitions |
| **Agent Executor** | ✅ Working | Executes agents with OpenAI/Anthropic LLMs |
| **LLM Provider Integration** | ✅ Working | OpenAI, Anthropic (mock provider available) |
| **Tool Executor** | ✅ Working | Executes Python tool functions |
| **Registration Client** | ✅ Working | Registers with Serving, maintains heartbeat |
| **Observability Client** | ✅ Working | Emits events to Serving |
| **Health API** | ✅ Working | `/health`, `/info` endpoints |
| **MCP Client** | ❌ Missing | Code exists in `services/mcp_client.py` but NOT initialized |
| **Git Worktree Management** | ❌ Missing | No worktree setup for parallel work |
| **Claude Code Integration** | ❌ Missing | This is v0.x Python, not Claude Code |

**Score:** 8/12 (67%) - **BUT WRONG ARCHITECTURE**

---

### 1.3 MARKETPLACE (Port 8003)

| Capability | Status | Notes |
|------------|--------|-------|
| **Skill Registry** | ✅ Working | Loads YAML skills from `skills/system/` and `skills/user/` |
| **Composition Service** | ✅ Working | Merges skills into agent bundles |
| **GET /api/v1/skills** | ✅ Working | List all skills with filtering |
| **GET /api/v1/skills/{id}** | ✅ Working | Get specific skill |
| **POST /api/v1/skills** | ✅ Working | Create user skill |
| **PUT /api/v1/skills/{id}** | ✅ Working | Update user skill |
| **DELETE /api/v1/skills/{id}** | ✅ Working | Delete user skill |
| **POST /api/v1/skills/compose** | ✅ Working | Compose skills into agent bundle |
| **POST /api/v1/skills/conflicts/check** | ✅ Working | Detect conflicting skills |
| **System Skills** | ✅ Working | 6 built-in: code-writer, test-automator, debugger, security-reviewer, doc-writer, code-reviewer |
| **Health Endpoint** | ✅ Working | `/api/v1/health` |

**Score:** 11/11 (100%) - **BUT ARCHITECTURE MISMATCH**

**Issue:** Standalone service on port 8003, but v1.0 spec says Persona Marketplace should be embedded in Serving.

---

## 2. Integration Analysis

### 2.1 Serving ↔ Marketplace

| Path | Status | Implementation |
|------|--------|----------------|
| Serving calls Marketplace | ✅ Working | `MarketplaceClient` HTTP calls |
| Skill fetching for composition | ✅ Working | Compute Spawner uses Marketplace API |
| Persona definitions | ✅ Working | MCP `get_persona` calls Marketplace |

**Architecture Gap:** v1.0 says Marketplace should be embedded in Serving, not a separate microservice.

---

### 2.2 Serving ↔ Compute

| Path | Status | Implementation |
|------|--------|----------------|
| Compute spawning | ⚠️ Partial | Creates workspace but spawns wrong architecture |
| MCP server endpoint | ✅ Working | `/api/v1/mcp/tools/call` responds |
| Work assignment | ⚠️ Blocked | Compute doesn't call MCP tools |
| Progress reporting | ❌ Blocked | Compute doesn't call MCP tools |
| API key auth | ✅ Working | Keys generated and verified |

**Architecture Gap:** Compute is v0.x Python runtime, can't consume Claude Code MCP config.

---

### 2.3 Compute → Git (via Serving)

| Path | Status | Implementation |
|------|--------|----------------|
| SSH Git push | ❌ Blocked | No SSH server running |
| SSH Git pull | ❌ Blocked | No SSH server running |
| Branch creation | ❌ Blocked | No server to push to |
| PR submission | ❌ Blocked | Requires branch pushed |
| Git worktrees | ❌ Missing | Not implemented in Project Service |

**Architecture Gap:** Entire Git workflow non-functional. SSH daemon not implemented.

---

## 3. End-to-End Test Blockers

### P0 - Critical (Blocks All E2E Testing)

| # | Blocker | Impact | Issue |
|---|---------|--------|-------|
| 1 | **Compute is v0.x Python, not Claude Code** | MCP workflow broken, wrong architecture | **#39** |
| 2 | **No SSH Git Server** | Can't push/pull branches | **#40** |

### P1 - High (Blocks Key Workflows)

| # | Blocker | Impact | Issue |
|---|---------|--------|-------|
| 3 | **Git Worktrees not implemented** | No parallel branch workspaces | **#41** |
| 4 | **Marketplace is external service** | Architecture mismatch | **#42** |
| 5 | **MCP Client not initialized in Compute** | v0.x can't call MCP tools | **#44** |

### P2 - Medium (Limits Functionality)

| # | Blocker | Impact | Issue |
|---|---------|--------|-------|
| 6 | **Git Hooks not deployed** | No validation, no events | **#43** |
| 7 | **Project Service incomplete** | Can't clone repos for compute | (Part of #41) |

### P3 - Low (Nice-to-Have)

| # | Blocker | Impact | Issue |
|---|---------|--------|-------|
| 8 | **WebSocket monitoring missing** | No real-time UI | #30 |
| 9 | **Get Context is stub** | Limited task context | (Future) |

---

## 4. Existing GitHub Issues Status

| # | Title | Status | Priority | Relevant |
|---|-------|--------|----------|----------|
| 31 | Add E2E Work Execution Test | Open | P1 | Yes - blocked by this audit |
| 30 | WebSocket Real-Time Updates | Open | P2 | Yes - P3 blocker |
| 29 | Work Timeout/Stuck Detection | Open | P1 | Yes - needed for production |
| 25 | Persona Selection in Work Flow | Open | P1 | Partially done |
| 17 | Regional Location Tracking | Open | P3 | No - nice-to-have |

---

## 5. Created GitHub Issues

All audit findings have been created as GitHub issues:

| Issue | Title | Priority | Type |
|-------|-------|----------|------|
| **#39** | Replace Compute Module with Claude Code CLI Architecture | P0 | Enhancement |
| **#40** | Implement SSH Git Server for Compute Branch Push/Pull | P0 | Enhancement |
| **#41** | Implement Git Worktree Workflow in Project Service | P1 | Enhancement |
| **#42** | Embed Marketplace in Serving (Architecture Consolidation) | P1 | Enhancement |
| **#43** | Deploy Git Hooks to Bare Repositories | P2 | Enhancement |
| **#44** | Initialize MCP Client in Compute Startup (v0.x Interim Fix) | P2 | Bug |

### Issue Dependencies

```
#39 (Compute Architecture) ─────────────┐
                                        ├──→ E2E Testing
#40 (SSH Git Server) ───────────────────┤
                                        │
#41 (Git Worktrees) ────────────────────┘
         ↓
#42 (Embed Marketplace) ──→ Architecture Alignment
         ↓
#43 (Git Hooks) ──────────→ Production Readiness
         ↓
#44 (MCP Client) ─────────→ Interim v0.x Testing (if needed)
```

---

## 6. Architecture Alignment Summary

### Matches v1.0 Spec

| Component | Status |
|-----------|--------|
| Work Map Service | ✅ |
| MCP Server (Serving) | ✅ |
| PR Service | ✅ |
| Compute Registry | ✅ |
| Frontend UI | ✅ |

### Mismatches v1.0 Spec

| Component | Implementation | Spec | Gap |
|-----------|----------------|------|-----|
| **Compute Runtime** | v0.x Python | Claude Code CLI | CRITICAL |
| **Marketplace** | Standalone port 8003 | Embedded in Serving | Architectural |
| **Git Transport** | None | SSH Server | CRITICAL |
| **Worktrees** | None | `/workspace/main + /active` | High |
| **Git Hooks** | Not deployed | pre-receive + post-receive | Medium |

---

## 7. Testing Readiness

### Can We Run E2E Tests Today?

**Answer: No**

**Blocking:**
1. Compute is wrong architecture
2. No Git server
3. No worktrees

### Minimum for E2E Testing

| Issue | Effort |
|-------|--------|
| Replace Compute with Claude Code | 2-3 days |
| SSH Git Server | 2-3 days |
| Git Worktrees | 1-2 days |
| **Total** | **5-8 days** |

---

## 8. Conclusion

ClaudeVN has strong foundations:
- Work Map service is production-ready
- MCP server tools are well-implemented
- PR service logic is sound
- Marketplace works (though externalized)

**Critical gaps:**
1. Compute module is wrong architecture
2. No SSH Git server

**Recommendation:** Prioritize Issues A and B to achieve v1.0 alignment and enable E2E testing.

---

**Audit Complete**
