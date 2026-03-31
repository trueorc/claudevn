# State Machine Engine Specification

**Status:** Draft
**Date:** 2026-03-31
**Authors:** Matt Lyons, Claude
**Implements:** v2.0 Architecture — Unified execution lifecycle across Layers 2 and 3

---

## 1. Overview

The state machine engine is the single mechanism that drives all work unit lifecycle transitions in ClaudeVN v2.0. Every phase — dispatch, execution, merge, conflict resolution, verification — is a state. Every action is a transition. Every failure is a state. There is ONE evaluate function, ONE pattern, ONE way things move forward.

This replaces the current ad-hoc collection of handlers (dispatcher, merge handler, conflict resolution dispatcher, verification trigger) with a unified engine where the transition table IS the system definition.

---

## 2. Core Principles

### 2.1 Everything is a state
Not just "executing" and "completed." Merging is a state. Conflict resolution is a state. Waiting for a compute is a state. Retrying after an error is a state. If something can happen to a work unit, there's a state for it.

### 2.2 Everything is a transition
Moving from one state to another is a transition. Each transition has conditions. When conditions are met, the transition fires. There are no side-effects, no fire-and-forget tasks, no implicit behavior. If it's not in the transition table, it doesn't happen.

### 2.3 Errors are states
When something fails, the unit enters an error state. The error state has its own transitions (retry, escalate, fail permanently). Error handling is not try/catch bolted onto each function — it's the same state machine processing errors as it processes success.

### 2.4 One evaluate function
`evaluate()` is called whenever any state changes. It walks all units that could potentially transition and fires any transition whose conditions are met. This is the ONLY function that advances state. Nothing else moves units forward.

### 2.5 Observable by default
Every state transition emits an event. The event carries: unit ID, old state, new state, reason, timestamp. The frontend, activity log, and any observer subscribes to these events. No silent transitions.

---

## 3. State Definitions

### 3.1 Work Unit States

| State | Description | Phase |
|-------|-------------|-------|
| `draft` | Created by decomposition, awaiting approval | Planning |
| `ready` | Approved, eligible for dispatch | Planning |
| `queued` | In dispatch queue, dependencies satisfied | Dispatch |
| `waiting_compute` | In queue but no compute available | Dispatch |
| `executing` | Compute is running Claude Code | Execution |
| `submitted` | Code complete, branch pushed, awaiting merge | Merge |
| `merging` | Merge to main in progress | Merge |
| `merge_conflict` | Merge failed, conflict resolution dispatched | Merge |
| `verifying` | Post-merge verification running | Verification |
| `completed` | Merged, verified, done | Terminal |
| `failed` | Permanently failed (retries exhausted) | Terminal |
| `needs_review` | Ambiguous failure, human decision needed | Terminal |
| `cancelled` | Cancelled by user | Terminal |
| `superseded` | Replaced by newer directive | Terminal |

### 3.2 Error Sub-States

Errors are NOT separate states. They are captured as metadata on the current state with a retry counter. When an error occurs during a transition:

```
unit.error = { message, code, attempt, max_attempts, first_at, last_at }
```

The evaluate function checks: if unit has an error AND retry conditions met → retry the transition. If retries exhausted → transition to `failed` or `needs_review`.

This avoids state explosion (no `error_executing`, `error_merging`, etc.). The state stays the same; the error metadata tells evaluate what to do.

---

## 4. Transition Table

The complete definition of every valid state transition:

| From | To | Conditions | Action |
|------|----|------------|--------|
| `draft` | `ready` | User approves decomposition | Update Redis, rebuild index |
| `ready` | `queued` | Dependencies satisfied (all deps in `completed`) | Add to dispatch queue |
| `queued` | `waiting_compute` | No idle compute available | Mark waiting (evaluation will retry) |
| `waiting_compute` | `queued` | Compute becomes available | Re-enter queue |
| `queued` | `executing` | Idle compute found for this project | Send work_assigned via SSE |
| `executing` | `submitted` | Compute reports success (claude_code_completed, exit=0) | Branch pushed |
| `executing` | `failed` | Compute reports failure (exit≠0) + retries exhausted | Emit failure event |
| `executing` | `executing` | Compute reports failure + retries remaining | Re-dispatch to compute (retry) |
| `submitted` | `merging` | Merge slot available (no other unit merging for this project) | Create PR, approve, merge |
| `merging` | `completed` | Merge succeeds | Unblock dependents, release compute |
| `merging` | `merge_conflict` | Merge detects conflicts | Send conflict to compute |
| `merging` | `failed` | Merge infrastructure error + retries exhausted | Emit failure, release compute |
| `merge_conflict` | `submitted` | Compute resolves conflict and pushes | Re-enter merge queue |
| `merge_conflict` | `failed` | Resolution fails + retries exhausted | Emit failure |
| `verifying` | `completed` | All verification checks pass | Final done state |
| `verifying` | `failed` | Verification fails + retries exhausted | Emit failure |
| `completed` | — | Terminal. Triggers dependent re-evaluation | — |
| `failed` | `needs_review` | Auto-escalation after failure | Human must decide |
| `needs_review` | `ready` | Human chooses retry | Re-enter pipeline |
| `needs_review` | `cancelled` | Human chooses cancel | Done |

### 4.1 Retry Policy

Each transition has a retry policy:

| Transition | Max Retries | Backoff | Transient Errors |
|-----------|-------------|---------|------------------|
| queued → executing | 3 | 10s | Compute disconnect, SSE failure |
| executing → submitted | 1 | 0 | — (compute handles internal retries) |
| submitted → merging | 3 | 5s | Redis lock timeout, git transient |
| merging → completed | 3 | 10s | Push failure, upstream sync |
| merge_conflict → submitted | 5 | 0 | — (compute resolves iteratively) |

Retries are tracked in `unit.error.attempt`. When `attempt >= max_attempts`, the transition goes to `failed` instead of retrying.

---

## 5. The Evaluate Function

### 5.1 Signature

```python
async def evaluate(self, unit_ids: Optional[Set[str]] = None) -> None:
    """Evaluate units for possible state transitions.

    Args:
        unit_ids: Specific units to evaluate. If None, evaluates all
                  non-terminal units. Pass specific IDs for efficiency
                  when you know which units were affected by a state change.
    """
```

### 5.2 Algorithm

```
for each unit in units_to_evaluate:
    if unit.state is terminal:
        continue

    for each transition in TRANSITIONS where transition.from == unit.state:
        if transition.conditions_met(unit, context):
            # Check error/retry
            if unit.error and unit.error.attempt >= transition.max_retries:
                transition_to(unit, 'failed', reason=unit.error.message)
                continue

            # Execute transition
            try:
                old_state = unit.state
                await transition.action(unit, context)
                unit.state = transition.to
                unit.error = None  # Clear error on success
                emit(StateTransition(unit_id, old_state, unit.state, reason))
            except TransientError as e:
                unit.error = increment_retry(unit.error, e)
                emit(StateTransitionError(unit_id, unit.state, str(e), unit.error.attempt))
            except PermanentError as e:
                transition_to(unit, 'failed', reason=str(e))

            break  # One transition per evaluate per unit
```

### 5.3 Triggers

evaluate() is called when ANY of these happen:

| Trigger | Units Affected |
|---------|---------------|
| Decomposition approved | All units in that goal |
| Compute connected | All `waiting_compute` units |
| Compute approved | All `waiting_compute` units |
| Execution complete | The unit + its dependents |
| Execution failed | The unit |
| Merge complete | The unit + its dependents |
| Merge conflict | The unit |
| Conflict resolved | The unit |
| Verification complete | The unit |
| Compute idle (after any task) | All `queued` and `waiting_compute` units |
| Resume after pause | All non-terminal units |

Each trigger passes the specific unit_ids affected for efficiency. evaluate() doesn't re-scan the entire project on every trigger.

### 5.4 Concurrency

evaluate() has a re-entrancy guard (existing pattern). Only one evaluate runs at a time. If a trigger fires while evaluate is running, it queues a re-evaluation after the current one completes.

For scale: evaluate() should be O(affected units), not O(all units). The trigger tells it which units to check.

---

## 6. Context Object

The evaluate function needs context to check conditions:

```python
@dataclass
class EvaluationContext:
    # Compute availability
    idle_computes: List[str]          # Instance IDs of idle computes
    busy_computes: Set[str]           # Instance IDs currently assigned

    # Merge coordination
    merging_project_ids: Set[str]     # Projects with a merge in progress

    # Dependency graph
    completed_unit_ids: Set[str]      # Units that are done (for dep checking)

    # System state
    paused: bool

    # Per-unit state
    units: Dict[str, WorkUnit]        # All non-terminal units
```

The context is built once per evaluate() call from live system state. Transitions check conditions against this context.

---

## 7. Scopes

### 7.1 Unit-Level State Machine
Each work unit has its own state. Transitions are per-unit. This is the primary machine described above.

### 7.2 Chain-Level Derived State
A chain's state is derived from its units:
- All units completed → chain complete
- Any unit executing/merging → chain in progress
- Any unit failed → chain blocked
- All units queued → chain ready

Chain state is NOT stored — it's computed from unit states. This avoids state synchronization issues.

### 7.3 Project-Level Derived State
A project's state is derived from its chains:
- All chains complete → project complete
- Any chain in progress → project in progress
- Any chain failed → project has failures

Also derived, not stored.

### 7.4 Merge Coordination (Project-Level)
One merge at a time per project (Redis lock in PRService). The context tracks `merging_project_ids`. A unit can only transition `submitted → merging` if its project is NOT in `merging_project_ids`.

---

## 8. Error Handling

### 8.1 Error Metadata

```python
@dataclass
class TransitionError:
    message: str
    code: str           # "transient", "permanent", "timeout"
    transition: str     # "queued→executing", "merging→completed", etc.
    attempt: int        # Current retry count
    max_attempts: int   # From retry policy
    first_at: datetime  # When error first occurred
    last_at: datetime   # Most recent attempt
    backoff_until: Optional[datetime]  # Don't retry before this time
```

### 8.2 Error Classification

| Error Type | Examples | Behavior |
|-----------|----------|----------|
| Transient | SSE disconnect, Redis timeout, git push 500 | Retry with backoff |
| Permanent | Invalid branch name, auth revoked, code error | Transition to `failed` |
| Timeout | Execution >30min, merge >5min | Retry once, then `failed` |
| Ambiguous | Merge conflict (needs human OR compute resolution) | Transition to specific state (`merge_conflict`) |

### 8.3 Error Flow

```
Unit in state X → attempt transition → error occurs
  → Is it transient? → increment attempt, set backoff, stay in state X
    → evaluate() called later → backoff expired? → retry transition
    → retries exhausted? → transition to failed
  → Is it permanent? → transition to failed immediately
  → Is it ambiguous? → transition to appropriate resolution state
```

---

## 9. Events

Every state transition emits a single event type:

```python
class WorkUnitStateTransition(BaseModel):
    event: str = "work_unit.state_transition"
    project_id: str
    unit_id: str
    old_state: str
    new_state: str
    reason: str = ""
    error: Optional[dict] = None  # Error metadata if transition was to error/failed
    timestamp: datetime
```

One event type. All state changes. The frontend subscribes to `work_unit.state_transition` and updates the graph.

Additional detail events can supplement (execution timing, merge commit SHA, etc.) but the state transition event is the canonical lifecycle event.

---

## 10. Implementation Approach

### 10.1 The Engine

```python
class WorkUnitEngine:
    """Unified state machine engine for work unit lifecycle."""

    def __init__(self):
        self._transitions = self._build_transition_table()
        self._evaluating = False
        self._pending_eval: Set[str] = set()  # Unit IDs to re-evaluate

    async def evaluate(self, unit_ids: Optional[Set[str]] = None):
        """Evaluate units for state transitions."""
        ...

    async def on_event(self, event_type: str, **kwargs):
        """Handle an external event by identifying affected units and evaluating."""
        affected = self._get_affected_units(event_type, **kwargs)
        await self.evaluate(affected)

    def _build_transition_table(self) -> List[Transition]:
        """Define all valid transitions with conditions and actions."""
        return [
            Transition(from='ready', to='queued', condition=deps_satisfied, action=add_to_queue),
            Transition(from='queued', to='executing', condition=compute_available, action=dispatch_to_compute),
            Transition(from='executing', to='submitted', condition=code_complete, action=mark_submitted),
            Transition(from='submitted', to='merging', condition=merge_slot_available, action=start_merge),
            Transition(from='merging', to='completed', condition=merge_succeeded, action=finalize),
            Transition(from='merging', to='merge_conflict', condition=conflicts_detected, action=dispatch_resolution),
            ...
        ]
```

### 10.2 Transition Definition

```python
@dataclass
class Transition:
    from_state: str
    to_state: str
    condition: Callable[[WorkUnit, EvaluationContext], bool]
    action: Callable[[WorkUnit, EvaluationContext], Awaitable[None]]
    retry_policy: RetryPolicy = RetryPolicy()
```

### 10.3 Integration Points

The engine replaces:
- `Dispatcher.evaluate()` → `WorkUnitEngine.evaluate()`
- `Dispatcher.on_code_complete()` → `engine.on_event("code_complete", ...)`
- `Dispatcher.on_merge_success()` → engine transition table handles it
- `_v2_merge_and_finalize()` → engine transition `submitted → merging`
- `finalize_work()` v2.0 call → engine transition `merging → completed`

External systems (compute events, SSE, user actions) call `engine.on_event()`. The engine translates events to affected units and evaluates.

---

## 11. Scale Considerations

### 11.1 Evaluation Efficiency
- evaluate() receives specific unit_ids, not "evaluate everything"
- Each trigger knows which units are affected
- Non-terminal units are indexed by state for fast lookup
- O(affected units × transitions per state), not O(all units × all transitions)

### 11.2 Concurrent Computes
- Multiple computes completing simultaneously → multiple on_event calls
- Re-entrancy guard ensures one evaluate at a time
- Queued re-evaluations are merged (unit_ids accumulated)
- Merge lock (Redis) prevents concurrent git merges per project

### 11.3 Many Projects
- Engine is per-project (or the context filters by project)
- Projects are independent — one project's state changes don't affect another
- Shared compute pool means `compute_available` condition checks across projects

### 11.4 Many Units (50-200 per project)
- Transition table is small (< 20 transitions)
- Per-evaluate: check affected units against their current state's transitions
- Fast condition checks (set membership, status comparison)
- No full graph traversal on each evaluate

### 11.5 Error Storms
- If a compute keeps failing, retries are rate-limited by backoff
- After max retries, unit goes to `failed` — stops retrying
- `failed` is terminal — no more evaluation cycles for that unit
- Escalation to `needs_review` puts it in human hands

---

## 12. Open Questions

1. **Verification integration** — Should verification states (`verifying`, `verified`) be in this same machine, or a separate pass? Recommendation: same machine, states between `merging→completed` become `merged→verifying→completed`.

2. **Compute affinity** — Should the engine track which compute executed a unit for conflict resolution routing? Yes — store `assigned_compute` on the unit.

3. **State persistence** — Should unit state transitions be persisted to Redis immediately? Yes — the engine updates Redis on every transition so state survives restarts.

4. **Chain ordering** — With multiple idle computes and multiple chains, which chain gets priority? Options: longest chain first, critical path first, round-robin. Recommendation: critical path first (maximizes parallelism).

5. **Merge order** — With multiple units submitted from different chains, which merges first? Options: FIFO, dependency order, chain priority. Recommendation: FIFO (first submitted, first merged).

---

## 13. Relationship to Existing Specs

- **Planning System Specification** (Layer 1) produces work units in `draft` state
- **v2.0 Architecture Document** defines the three-layer model
- This spec defines how units flow through Layers 2 and 3
- The reactive evaluation pattern documented in memory is the implementation principle
- The "done means merged" strategy documented in memory is encoded in the transition table

---

## 14. Implementation Phases

### Phase 1: Engine Core
- WorkUnitEngine class with transition table
- evaluate() function
- State transition events
- Error metadata model
- Retry policy

### Phase 2: Replace Dispatcher
- Wire engine to compute events
- Wire engine to decomposition approval
- Wire engine to compute connect/approve
- Remove current Dispatcher.evaluate() and merge handler

### Phase 3: Merge as State
- Add MERGING, MERGE_CONFLICT states
- Implement merge action (calls PRService)
- Implement conflict resolution dispatch
- Merge lock coordination

### Phase 4: Frontend
- Graph colors for all states
- Activity log shows state_transition events
- Error states visible with retry count

### Phase 5: Verification as State
- Add VERIFYING state
- Implement verification checks as transition action
- Wire to existing verification infrastructure
