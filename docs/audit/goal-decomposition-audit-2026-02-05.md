# Goal Decomposition Pipeline - Functional Audit

**Date:** 2026-02-05
**Type:** Standard Functional Audit
**Feature:** Goal Decomposition End-to-End Flow
**Test Run:** goal_98a37fd34f5d / decomp-e1a9123f70a3
**Result:** PASS with Critical Defects

---

## Executive Summary

The goal decomposition pipeline successfully completed its core function: a user-created goal was decomposed into 7 structured backlog issues with correct dependencies, execution phases, and goal state updates. However, critical data integrity issues and infrastructure gaps were identified that affect production readiness.

**What worked:**
- Full pipeline: goal creation -> compute delegation -> Claude Code execution -> JSON parsing -> result submission -> goal update
- 7 issues created with proper priorities, dependencies, and phase grouping
- Goal transitioned from `planning` to `in_progress` with all issue_ids populated

**What didn't:**
- Goal ID lost in transit (stored as "unknown" in Redis)
- Goal service not accessible from MCP tool handlers
- Project service Redis operations broken (missing smembers/sadd)
- Frontend hitting deprecated API routes (19 x 405 errors)

---

## Pipeline Timeline

| Timestamp | Component | Event | Status |
|-----------|-----------|-------|--------|
| 23:49:07.606 | Serving | Goal created (goal_98a37fd34f5d) | OK |
| 23:49:07.612 | Serving | Decomposer initialized, delegating to compute | OK |
| 23:49:07.626 | Marketplace | Skill fetched (goal-decomposer) | OK |
| 23:49:07.627 | Serving | Assigned decomp-e1a9123f70a3 to compute-002 | OK |
| 23:49:07.818 | Compute-002 | Received work_assigned | OK |
| 23:49:07.819 | Compute-002 | No repository URL, skipping Git setup | WARN |
| 23:49:07.823 | Compute-002 | Claude Code started (cc-2a73bce6, pid=43) | OK |
| 23:49:48.356 | Compute-002 | Claude Code exited (exit_code=0, 40.5s) | OK |
| 23:49:48.356 | Compute-002 | JSON result found in output | OK |
| 23:49:48.356 | Compute-002 | **No goal_id found for decomposition** | CRITICAL |
| 23:49:48.383 | Serving | Result received (goal_id="unknown", 7 issues) | WARN |
| 23:49:48.383 | Serving/MCP | **Goal service not initialized, cannot update goal** | CRITICAL |
| 23:49:48.383 | Serving | Decomposition stored in Redis | OK |
| 23:49:49.634 | Serving | Polling retrieved result, updated goal with 7 issues | OK |
| 23:49:49.640 | Serving | Goal auto-processed (ready=1, backlog=6) | OK |

---

## Findings

### Critical (P0)

| # | Issue | Description |
|---|-------|-------------|
| #430 | Goal ID lost during result submission | Compute submits with `goal_id: "unknown"` because work_assigned event doesn't include goal_id in context |
| #431 | Goal service not initialized in MCP handler | `decomposition.py` tool can't update goal atomically, relies on 1.25s polling fallback |

### High (P1)

| # | Issue | Description |
|---|-------|-------------|
| #432 | RegistryStorage.load_all_instances missing | Compute/marketplace registrations lost on serving restart |
| #433 | RedisClient missing set operations | ProjectService can't persist (smembers/sadd not implemented) |

### Medium (P2)

| # | Issue | Description |
|---|-------|-------------|
| #434 | Frontend hitting deprecated routes | 19 x 405 errors on /work-map/* endpoints |
| #435 | No timeout for goals stuck in planning | Orphaned goal_6b12cfd70388 stuck indefinitely |

---

## Data Integrity

| Entity | State | Assessment |
|--------|-------|------------|
| goal_98a37fd34f5d | in_progress, 7 issue_ids, decomposition_id set | Correct |
| goal_6b12cfd70388 | planning, no issues, no decomposition_id | Orphaned (pre-fix) |
| decomp-e1a9123f70a3 | Stored in Redis, 7 issues, confidence 0.90 | goal_id="unknown" |

---

## Recommendations

**Phase 1 (P0):** Fix goal_id propagation and MCP service initialization
**Phase 2 (P1):** Complete Redis client implementation and registry storage
**Phase 3 (P2):** Update frontend routes and add goal timeout/recovery
