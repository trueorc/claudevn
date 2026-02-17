# Conflict Identification Taxonomy and Surfacing Protocol

**Status:** Implemented
**Issue:** #510
**Reference:** `docs/work_management_framework.md` — Sections 10.1, 11, 12

## Overview

This document defines the conflict identification taxonomy, surfacing protocol, authority boundary rules, and user response mechanisms for the planner system. It covers how the system detects, classifies, and surfaces conflicts that arise when the planner absorbs multiple influence sources (goals, worker feedback, dependencies, resources).

## Conflict Type Taxonomy

### 1. Goal-to-Goal (`goal_to_goal`)

**Definition:** Two active goals create competing demands or push the planner profile in opposing directions.

**Detection criteria:**
- Intent conflict: Goals have conflicting primary intents (e.g., `expansion` vs `consolidation`). Uses existing `GoalConflict` objects from `GoalIntentService.detect_conflicts()`.
- Resource competition: Goals compete for the same domain clusters or worker capabilities.

**Severity calculation:**
- Base severity from average intent strengths of both goals
- Recency boost: both goals within 48h = 1.2x, one within 48h = 1.1x
- Severity >= 0.7 marked as irreconcilable

**Example:** "Build new reporting feature" competes with "Harden current functionality" — one pushes expansion, the other consolidation.

### 2. Goal-to-Reality (`goal_to_reality`)

**Definition:** A goal's intent is undermined by ground-truth conditions revealed through worker feedback patterns.

**Detection criteria:**
- Maps goal intent types to contradicting feedback pattern types:
  - `quality_focused` contradicted by `blocker` patterns (can't test when core is unstable)
  - `expansion` contradicted by `blocker` and `challenge` patterns (can't build new when existing is broken)
  - `consolidation` contradicted by `requirement` patterns (scope expanding despite stability goal)
  - `targeted_investment` contradicted by `challenge` patterns (target area is harder than expected)

**Severity calculation:**
- Base from pattern signal count: `min(1.0, (signal_count / 5) * 0.5)`
- Plus goal intent strength contribution: `+ intent_strength * 0.3`

**Example:** Goal says "Focus on testing" but workers report systemic blockers requiring bug fixes first.

### 3. Dependency (`dependency`)

**Definition:** Work items have circular, contradictory, or unresolvable dependency chains.

**Detection criteria:**
- Circular dependency detection via DFS cycle finding
- Each cycle is reported as a separate conflict

**Severity calculation:**
- Base severity: `0.6 + cycle_length * 0.05`
- All circular dependencies require user intervention (override authority rules)

**Example:** Task A requires Task B's output, Task B requires Task C, Task C requires Task A.

### 4. Resource (`resource`)

**Definition:** Plan requires capabilities or compute that exceed what's available.

**Detection criteria:**
- Capability gap: Tasks require capabilities no available worker provides
- Worker contention: More tasks need a capability than workers can provide

**Severity calculation:**
- Capability gap: base severity 0.8
- Worker contention: `0.4 + (excess_demand) * 0.15`

**Example:** Three high-priority tasks all need GPU compute, but only one GPU worker is available.

## Surfacing Protocol

Each conflict is surfaced as a `ConflictReport` containing:

### What is in tension

`tension_elements` — list of specific goals, tasks, resources, or dependencies involved, each with:
- `element_type`: goal, task, resource, dependency, feedback_pattern
- `element_id`: unique identifier
- `label`: human-readable name
- `detail`: role in the conflict

### How the planner is currently handling it

`planner_handling` — includes:
- `approach`: description of current handling strategy
- `favored_side`: which side the planner favored (if applicable)
- `reasoning`: why this approach was chosen
- `profile_impact`: how this affected the planner profile

### What the user could do

`suggested_resolutions` — list of actionable options, each with:
- `response_type`: adjust_goal, accept_tradeoff, clarify_intent, set_priority
- `description`: what the user would do
- `expected_impact`: what would change

### Decision trace reference

`decision_trace_ids` — links to `DecisionTraceEntry` records showing how the conflict was identified.

## Authority Boundary Rules

Authority boundaries determine which conflicts the planner resolves autonomously vs. surfaces to the user.

| Conflict Type | Threshold | Below Threshold | At/Above Threshold |
|---|---|---|---|
| Goal-to-Goal | HIGH (0.6) | User required | User required |
| Goal-to-Reality | MEDIUM (0.3) | User required | User required |
| Dependency | HIGH (0.6) | Autonomous (non-circular) | User required |
| Resource | MEDIUM (0.3) | Autonomous | User required |

**Design rationale:**
- **Goal-to-goal** always surfaces because both goals came from the user — only the user can decide priority
- **Goal-to-reality** surfaces at medium because the user's stated intent is being undermined by conditions they may not be aware of
- **Dependency** resolves autonomously for non-circular chains (resequencing) but surfaces circular dependencies
- **Resource** resolves autonomously when alternatives exist (resequencing, substitution) but surfaces capability gaps

## User Response Mechanisms

Users can respond to surfaced conflicts in four ways:

| Response Type | Description | Effect |
|---|---|---|
| `adjust_goal` | Modify goal language or scope | Triggers intent reclassification and profile rebuild |
| `accept_tradeoff` | Accept the planner's current approach | Conflict marked as resolved, planner continues |
| `clarify_intent` | Clarify that current intent should be maintained | Increases confidence on current profile weights |
| `set_priority` | Set explicit reconciliation weights on competing goals | Profile reconciliation uses user-specified weights |

All user responses feed back into the planner profile via `ProfileTrigger` events.

## Integration Points

### With Planner Profile (`PlannerProfileService`)

- Goal-to-goal conflicts use profile weights, reconciliation weights, and intent strengths
- Conflict resolution triggers profile updates via `ProfileTriggerType.MANUAL_ADJUSTMENT`

### With Decision Traceability (`DecisionTraceEntry`)

- Each conflict references trace entries via `decision_trace_ids`
- Conflict identification is a traced decision point (Section 11.1)
- Conflict resolution is a traced decision point

### With Worker Feedback (`FeedbackAggregationService`)

- Goal-to-reality detection uses detected `FeedbackPattern` objects
- Feedback patterns with contradicting intent types trigger conflict creation

### With Goal Intent (`GoalIntentService`)

- Goal-to-goal detection wraps `GoalConflict` objects into `ConflictReport`
- Intent classification provides the basis for contradiction detection

## File Locations

| File | Purpose |
|---|---|
| `serving/models/conflict.py` | Conflict taxonomy models, authority rules, detection criteria |
| `serving/services/conflict_detection_service.py` | Detection logic for all four conflict types |
| `serving/tests/unit/test_conflict_models.py` | Model tests (31 tests) |
| `serving/tests/unit/test_conflict_detection_service.py` | Service tests (44 tests) |
