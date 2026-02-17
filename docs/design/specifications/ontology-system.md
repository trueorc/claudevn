# Two-Layer Ontology System — Design Specification

**Status:** Implemented
**Issue:** #505
**Reference:** `docs/work_management_framework.md` — Section 6

## Overview

The ontology system provides a structured vocabulary that enables deterministic filtering and semantic reasoning across the work management pipeline. It consists of two layers:

- **Layer 1 — Universal**: Fixed categories that apply to any software project
- **Layer 2 — Project-Specific**: Adaptive domain clusters that describe what a particular project is about

## Layer 1 — Universal Ontology

Defined as Python enums in `serving/models/ontology.py`. These are static and never change per project.

### Work Type
Classifies the nature of work being performed.

| Value | Description |
|-------|-------------|
| `feature` | New capability development |
| `bug_fix` | Fixing defective behavior |
| `refactor` | Structural improvement without behavior change |
| `test` | Test creation or maintenance |
| `documentation` | Documentation work |
| `infrastructure` | Build, deploy, CI/CD infrastructure |
| `integration` | Connecting systems or components |

### Lifecycle Stage
Tracks where work is in the development lifecycle.

| Value | Description |
|-------|-------------|
| `design` | Architecture and design phase |
| `build` | Active implementation |
| `test` | Testing phase |
| `validate` | Review and validation |
| `deploy` | Deployment and release |

### Technical Domain
Identifies the technical area(s) involved.

| Value | Description |
|-------|-------------|
| `frontend` | UI and client-side |
| `backend` | Server-side logic |
| `data` | Database and data layer |
| `api` | API design and implementation |
| `security` | Security and authentication |
| `devops` | Infrastructure and operations |
| `testing` | Test infrastructure |
| `documentation` | Documentation systems |

### Usage

Every work item receives a `UniversalTags` struct containing:
- One `WorkType`
- One `LifecycleStage`
- One or more `TechnicalDomain` values

The planner uses these for broad decisions like "prioritize all testing" or "deprioritize new feature development" without needing project-specific knowledge.

## Layer 2 — Project-Specific Ontology

Managed by `OntologyService` in `serving/services/ontology_service.py`. These are dynamic and stored per-project in Redis.

### Domain Clusters

A domain cluster represents a capability area specific to a project (e.g., "payment processing", "user authentication", "reporting dashboard").

**Fields:**
- `cluster_id` — Unique identifier (format: `cluster-{hex8}`)
- `name` — Human-readable name
- `description` — What this cluster covers
- `status` — `active`, `consolidated`, or `archived`
- `created_from` — Goal or work item that seeded this cluster
- `consolidated_into` — Target cluster if this one was merged
- `work_item_count` — Number of work items tagged with this cluster

### Lifecycle

1. **Seeded** during initial goal decomposition via `seed_clusters()`
2. **Grows** when characterization encounters unclassifiable work via `create_cluster()`
3. **Consolidates** when clusters converge via `consolidate_clusters()`
4. **Archives** when a cluster is no longer relevant

### Evolution Rules

- New clusters are created when work doesn't fit existing active clusters
- Cluster names are matched case-insensitively to avoid duplicates
- Source clusters merged into a target retain their history (status = `consolidated`)
- The planner can reference cluster IDs by weight in its operating profile

## Data Models

### OntologyTags (applied to work items)

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

### OntologyWeights (used by planner profile)

```python
OntologyWeights(
    work_type_weights={"feature": 0.15, "bug_fix": 0.85, "test": 0.9},
    lifecycle_stage_weights={"test": 0.95, "validate": 0.8},
    cluster_weights={"cluster-abc123": 0.9, "cluster-def456": 0.1},
)
```

Default weight for any unspecified category is 0.5. Weights are validated to be in [0.0, 1.0].

## Storage Strategy

### Redis Key Structure

```
claudevn:ontology:{project_id}:clusters  — Hash: cluster_id → JSON(DomainCluster)
claudevn:ontology:{project_id}:meta      — Hash: project metadata (created_at, updated_at)
```

### Design Decisions

- **Hash per project** for clusters enables O(1) lookup by cluster_id and efficient full-project scans
- **JSON serialization** for cluster values allows schema evolution without migration
- **In-memory cache** (`_projects` dict) avoids repeated Redis reads during planning cycles
- **Metadata stored separately** from cluster data for clean key organization

## Migration Path

Legacy enums (`IssueType`, `IssueArea`) map to Layer 1 values via dictionaries:

| Legacy `IssueType` | `WorkType` |
|---------------------|------------|
| `feature` | `feature` |
| `bug` | `bug_fix` |
| `refactor` | `refactor` |
| `docs` | `documentation` |
| `test` | `test` |

| Legacy `IssueArea` | `TechnicalDomain` |
|---------------------|-------------------|
| `api` | `api` |
| `database` | `data` |
| `frontend` | `frontend` |
| `infra` | `devops` |
| `other` | `backend` (default) |

The legacy enums remain in `models/work_map.py` and `models/issue.py` for backward compatibility. New work items created through the characterization pipeline will use `OntologyTags` instead.

## File Locations

| File | Purpose |
|------|---------|
| `serving/models/ontology.py` | All ontology data models (both layers) |
| `serving/services/ontology_service.py` | Layer 2 management service |
| `serving/tests/unit/test_ontology_models.py` | Model unit tests |
| `serving/tests/unit/test_ontology_service.py` | Service unit tests |

## Future Work

- **Characterization Agent** — Applies ontology tags to raw tasks from decomposition
- **Planner Profile Integration** — Uses `OntologyWeights` to construct priority bucket trees
- **Cluster Auto-Evolution** — Automatic consolidation suggestions based on usage patterns
- **API Endpoints** — REST API for cluster management (admin use)
