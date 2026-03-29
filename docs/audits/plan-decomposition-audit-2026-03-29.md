# Plan / Decomposition Feature Audit Report

**Date:** 2026-03-29
**Auditor:** Claude Code
**Scope:** All v2.0 planning, decomposition, dispatch, verification, and event infrastructure

## Executive Summary

The v2.0 three-layer architecture is structurally complete — 45+ files across backend models, services, API routes, and frontend components. The decomposition pipeline runs end-to-end (LLM → analyze → build → validate → environment → Redis → Plan page). However, **Layer 2 (dispatch) and Layer 3 (verification) API endpoints are entirely stubbed**, coherence analysis is unimplemented, and several integration gaps exist between the pipeline and the frontend display.

## Inventory

| Area | Files | Lines | Status |
|------|-------|-------|--------|
| Backend Models (`models/work_unit/`) | 8 | ~560 | Complete |
| Decomposition Services | 9 | ~1,900 | Working, some gaps |
| Event System | 4 | ~500 | Complete |
| Dispatch Services | 3 | ~380 | Built, not wired |
| Verification Services | 4 | ~720 | Built, not wired |
| API Routes (v2_*) | 4 | ~370 | Partially stubbed |
| Frontend Pages | 2 | ~530 | Working |
| Frontend Components | 10 | ~960 | Working |
| Frontend Hooks/API | 3 | ~220 | Working |

**Total: ~45 files, ~6,140 lines**

## Findings

### Critical (P0)

**None found.** No security vulnerabilities, data loss risks, or breaking functionality in the working paths.

### High Priority (P1)

1. **Dispatch and Verification APIs are 100% stubbed**
   - `v2_dispatch.py`: `/dispatch/queue` and `/dispatch/active` return hardcoded `[]`
   - `v2_verification.py`: All 5 endpoints return empty structures
   - Impact: Execute and Verify pages show no data even after work is dispatched
   - Fix: Wire to actual DispatchQueue and verification result storage

2. **Coherence analysis is unimplemented**
   - `v2_decomposition.py:152`: Returns `{"insights": [], "goals_analyzed": 0}`
   - Impact: CoherencePanel on Plan page is always empty — no cross-goal consistency checking
   - Fix: Implement LLM-based coherence analyzer that compares goals

3. **Dependency queue unblocking is incomplete**
   - `queue.py:99`: `mark_completed()` comment says "We need the actual unit — caller should re-enqueue" but callers don't
   - Impact: Dependent work units may never dispatch after their dependencies complete
   - Fix: Store pending units in the queue and re-enqueue when dependencies clear

4. **Frontend API calls to undefined endpoints**
   - `workUnits.js`: Calls `getDecomposition()`, `updateWorkUnit()`, `splitWorkUnit()`, `mergeWorkUnits()` — none of these endpoints exist
   - Impact: Any future UI that calls these will get 404s
   - Fix: Either implement the endpoints or remove the dead API functions

5. **work_unit_builder.py crashes on empty file_tree**
   - Line 212: `self._codebase.file_tree[0].path` — IndexError if file_tree is empty
   - Impact: Pipeline step 3 fails for repos with no recognized code files
   - Fix: Guard with `if self._codebase.file_tree else False`

### Medium Priority (P2)

6. **Silent error suppression in environment_analyzer.py**
   - Multiple `except Exception: pass` blocks (lines 228, 309, 318, 332)
   - Impact: Config file parsing failures are invisible — bad requirements detection
   - Fix: Log warnings instead of silently passing

7. **Legacy interface_contracts displayed alongside new produces/consumes**
   - `WorkUnitCard.jsx:134-145`: Shows old `formal_spec.interface_contracts` section AND new `interface_produces`/`interface_consumes`
   - Impact: Redundant/confusing display
   - Fix: Remove the legacy section

8. **goalCommentCounts state never populated**
   - `GoalsPage.jsx:31`: Defined and passed to GoalHistoryPanel but never set
   - Impact: Comment counts show 0 for all goals in the history sidebar
   - Fix: Load comment counts when goals load, or remove the prop

9. **_resolve_project_id swallows all exceptions**
   - `v2_decomposition.py:27`: Returns empty string on any error
   - Impact: API calls with valid goal_ids may silently return empty results
   - Fix: Log the error, return 404 if goal not found

10. **Combined test verification is placeholder**
    - `integration_verifier.py:235`: Returns PENDING status with message instead of running tests
    - Impact: Cross-unit test integration is not functional
    - Fix: Implement temp worktree merge + test run

### Low Priority (P3)

11. **No test coverage for v2.0 code** — zero unit tests for any new service, model, or component
12. **DependencyGraph uses text layout** — design doc mentions "DAG visualization" but implementation is text-based layers
13. **No loading states on Plan page** — if API calls are slow, user sees nothing
14. **SSE connection doesn't show status** — no indicator that the event stream is connected/disconnected
15. **Unused response models in v2_dispatch.py and v2_verification.py** — comprehensive models defined but endpoints return raw dicts

## Gap Analysis: Design Doc Alignment

| Design Doc Feature | Section | Status | Gap |
|---|---|---|---|
| Codebase analysis | 4.2.1 | Working | Missing: dependency graph between modules, test coverage analysis |
| Independence boundary detection | 4.2.1 | Partial | File overlap only — no interface contract analysis or shared state detection |
| Work unit formal spec | 4.2.2 | Working | interface_contracts field is empty (produces/consumes is new separate field) |
| Interactive refinement | 4.2.3 | Partial | ChatRail context works, but no split/merge buttons, no scope challenge UI |
| Dependency graph visualization | 4.2.3 | Partial | Text-based layers, not interactive DAG. No bottleneck identification |
| Scope challenge ("15 files — split?") | 4.2.3 | Missing | No complexity threshold checking or split suggestions |
| Recomposition (merge/split) | 4.2.3 | Missing | No API endpoints, no UI controls |
| Context assembly | 4.3.1 | Built | Not wired — upstream outputs not injected |
| Priority queue dispatch | 4.3.2 | Built | Not wired to actual compute execution |
| Per-unit verification | 4.4.1 | Built | Not wired — API endpoints stubbed |
| Cross-unit integration | 4.4.2 | Built | Not wired — combined test run is placeholder |
| Verification-driven retry | 4.4.4 | Built | Not wired — no execution means no verification |
| Gap detection | 4.4.2.5 | Missing | Not implemented |
| Coherence analysis | Added | Stubbed | LLM analyzer not implemented |

## Recommendations

**Immediate (before next test cycle):**
1. Fix work_unit_builder crash on empty file_tree (P1 #5)
2. Remove legacy interface_contracts display from WorkUnitCard (P2 #7)
3. Add logging to silent except blocks in environment_analyzer (P2 #6)

**Next development phase:**
1. Implement coherence analysis with LLM (P1 #2) — highest user-visible impact
2. Wire dispatch queue API to actual DispatchQueue (P1 #1)
3. Add complexity scoring + confidence visualization to Plan page (planned task #19)
4. Add chain visualization with critical path (planned task #20)
5. Remove/implement dead API functions in workUnits.js (P1 #4)

**Before execution wiring:**
1. Fix dependency unblocking in queue (P1 #3)
2. Wire context assembly with upstream outputs
3. Implement combined test verification (P2 #10)

## Suggested Issues

- `[P1] Wire dispatch and verification API endpoints to actual services`
- `[P1] Implement coherence analysis LLM service`
- `[P1] Fix dependency queue unblocking — pending units never re-enqueue`
- `[P1] Fix work_unit_builder crash on empty codebase file_tree`
- `[P2] Remove legacy interface_contracts display from WorkUnitCard`
- `[P2] Add complexity scoring and decomposition confidence to Plan page`
- `[P2] Chain visualization with critical path highlighting`
