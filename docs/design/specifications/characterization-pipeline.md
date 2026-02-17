# Characterization Stage Pipeline — Design Specification

**Status:** Implemented
**Issue:** #506
**Depends on:** #505 (Ontology System)
**Reference:** `docs/work_management_framework.md` — Section 5

## Overview

The characterization stage is the critical translation layer between raw decomposed tasks and plannable work. Every task passes through characterization before entering the planner's backlog. The framework identifies characterization quality as "the single biggest risk."

## Pipeline Architecture

```
Decomposition → [Characterization Pipeline] → Planner Backlog
                       │
                       ├── 1. Create PENDING entries
                       ├── 2. Evaluate in isolation (Frame 1)
                       ├── 3. Evaluate in project context (Frame 2)
                       └── 4. Store COMPLETED results
```

### Trigger Points

1. **Post-decomposition** — When `GoalDecomposerService` produces a batch of `DecomposedIssue` items, they are registered as PENDING via `create_pending_batch()`
2. **Manual work creation** — When issues are created directly, they can be submitted for characterization individually
3. **Re-characterization** — When the work topology changes significantly, existing items can be re-evaluated

### Pipeline States

| Status | Description |
|--------|-------------|
| `pending` | Registered, awaiting characterization |
| `in_progress` | Compute instance is characterizing |
| `completed` | Successfully characterized with all four outputs |
| `failed` | Characterization failed (LLM error, timeout, etc.) |

## Characterization Output (Four Components)

### A. Ontology Tags

Uses the two-layer ontology from #505:

```python
OntologyTags(
    universal=UniversalTags(
        work_type=WorkType.FEATURE,
        lifecycle_stage=LifecycleStage.BUILD,
        technical_domains=[TechnicalDomain.BACKEND, TechnicalDomain.API],
    ),
    project_specific=ProjectSpecificTags(
        cluster_ids=["cluster-abc123"],
    ),
)
```

### B. Meaning Assessments

Three dimensions, each producing a structured assessment:

**Business Meaning** — Product/UX/business contribution independent of other tasks:
- `summary` — Brief description of business value
- `user_impact` — How this affects end users
- `business_value` — Revenue, retention, compliance, or strategic value

**Technical Meaning** — Engineering accomplishment:
- `summary` — What it builds, fixes, validates, or enables
- `components_affected` — System components touched
- `technical_risk` — Complexity and unknowns assessment

**Contextual Meaning** — Role in the broader project (requires topology access):
- `summary` — How this fits into the project
- `role` — One of: `foundational`, `incremental`, `enabling`, `blocking`
- `related_work_summary` — Relationship to other active work

### C. Contextual Dependencies

Beyond explicit parent/child relationships from decomposition, characterization discovers semantic relationships:

| Relation | Description |
|----------|-------------|
| `blocks` | Target cannot start until source completes |
| `enables` | Completing source makes target easier/possible |
| `related_to` | Shared domain context, beneficial to co-schedule |
| `extends` | Builds on work done by the related item |
| `conflicts_with` | May have merge conflicts or design tension |

Each dependency is classified as:
- **Structural** — Hard prerequisite, must complete first
- **Contextual** — Soft relationship, beneficial to consider for sequencing

Each carries a confidence score (0.0-1.0).

## Evaluation Frames

### Frame 1: In Isolation
Evaluates the work item on its own merits:
- Assigns ontology tags based on title, description, and decomposer hints
- Produces business and technical meaning assessments
- No project context needed

### Frame 2: In Project Context
Evaluates the work item against the existing work topology:
- Discovers contextual dependencies against characterized work
- Assigns contextual role (foundational, incremental, enabling, blocking)
- May create new domain clusters if work doesn't fit existing ones
- Requires read access to `WorkTopology`

## Work Topology

The `WorkTopology` model provides the characterized work context:

```python
WorkTopology(
    project_id="proj-1",
    items=[
        TopologyItem(
            item_id="item-001",
            title="Add user settings endpoint",
            ontology_tags=...,
            contextual_role=ContextualRole.FOUNDATIONAL,
            cluster_ids=["cluster-abc"],
        ),
        ...
    ],
    cluster_names=["payment processing", "user management"],
)
```

Populated by `CharacterizationService.get_work_topology()` from completed results.

## Integration Points

### With Decomposition (upstream)
- **Input:** `DecomposedIssue` items from `GoalDecomposerService`
- **Trigger:** After decomposition completes, call `create_pending_batch()`
- **Hints:** Decomposer provides `issue_type_hint` and `area_hint` for characterization

### With Ontology Service (Layer 2)
- **Reads:** Active domain clusters for a project
- **Writes:** May create new clusters when work doesn't fit existing ones
- **Updates:** Increments `work_item_count` when tagging work to a cluster

### With Planner (downstream)
- **Output:** `CharacterizationResult` with ontology tags, meanings, dependencies
- **Query:** Planner reads completed results to build priority bucket tree
- **Weights:** Planner uses `OntologyWeights` to score against characterization tags

## AI Prompt Strategy

Characterization is performed by compute instances (Claude Code), not by serving directly. The strategy for quality:

1. **Structured output** — Use JSON schema to ensure consistent format
2. **Two-pass evaluation** — Isolation first, then context (prevents anchoring)
3. **Ontology-constrained** — Provide valid enum values in prompt to ensure valid tags
4. **Topology-aware** — Include summarized topology in context window for Frame 2
5. **Confidence scoring** — LLM self-reports confidence, used for quality gating
6. **Hint integration** — Decomposer hints are inputs but not binding

## Storage Strategy

### Redis Key Structure

```
claudevn:characterization:{project_id}:{item_id}  — JSON string (CharacterizationResult)
claudevn:characterization:{project_id}:index       — Set of characterized item IDs
```

### Design Decisions

- **JSON string per item** (not hash) because CharacterizationResult is deeply nested
- **Index set** enables efficient project-level queries without key scanning
- **In-memory cache** (`_results` dict) for fast reads during planning cycles
- **No TTL** — characterization results persist until explicitly removed

## File Locations

| File | Purpose |
|------|---------|
| `serving/models/characterization.py` | All characterization data models |
| `serving/services/characterization_service.py` | Pipeline management service |
| `serving/tests/unit/test_characterization_models.py` | Model unit tests (25 tests) |
| `serving/tests/unit/test_characterization_service.py` | Service unit tests (22 tests) |

## Future Work

- **Compute integration** — Wire characterization requests to compute instances
- **Quality gating** — Reject low-confidence results and retry
- **Re-characterization triggers** — Detect topology changes that warrant re-evaluation
- **Cluster evolution** — Auto-create clusters when characterization encounters unknown domains
- **API endpoints** — REST API for characterization status and manual triggers
