# Planning System Specification

**Status:** Draft
**Date:** 2026-03-29
**Authors:** Matt Lyons, Claude
**Implements:** v2.0 Architecture Section 4.2 (Layer 1: Decomposition Intelligence)

---

## 1. Overview

The planning system is ClaudeVN's primary value driver. It transforms ambiguous goals into formally specified, independent work units with verification criteria, interface contracts, and acceptance criteria. The quality of this decomposition directly determines execution success.

The planning system runs entirely on serving — no compute instances needed. It uses Claude Code CLI (subscription-based) for LLM operations.

---

## 2. Pipeline

### 2.1 Pipeline Steps

The decomposition pipeline runs 7 steps sequentially. Each step emits events for real-time observability. Each step has a status (pending → running → completed/failed) with timing.

| Step | Name | Purpose | Inputs | Outputs |
|------|------|---------|--------|---------|
| 1 | `llm_decompose` | Break goal into structured units | Goal text, project context, conversation | Raw units with descriptions, files, deps, interfaces, criteria |
| 2 | `codebase_analysis` | Static analysis of the repository | Repo path | File tree, modules, test files, config files |
| 3 | `build_work_units` | Construct formal WorkUnit specs | Raw units + codebase analysis | WorkUnit objects with formal specs |
| 4 | `resolve_dependencies` | Map description-based deps to unit IDs | Work units + raw units | Resolved depends_on/depended_by |
| 5 | `validate` | Check independence, cycles, completeness | Work units | Validation issues (errors + warnings) |
| 6 | `score_quality` | Assess decomposition quality | Work units + validation | Per-unit scores + overall confidence |
| 7 | `analyze_environment` | Detect runtime requirements | Work units + codebase | ComputeEnvironmentSpec with Dockerfile |

Step 4 (resolve_dependencies) is currently embedded in step 3. It should be its own step for observability.

Step 6 (score_quality) is new — not yet implemented.

### 2.2 Pipeline Events

Each step emits:
- `decomposition.step_started` — step name, goal_id, project_id
- `decomposition.step_completed` — step name, duration_ms, detail
- `decomposition.step_failed` — step name, error

Overall:
- `decomposition.started` — goal entered pipeline
- `decomposition.completed` — all steps done, work units ready for review
- `decomposition.failed` — pipeline failed, error detail

### 2.3 Pipeline Storage

Results stored in Redis keyed by `project_id:goal_id`:
- `claudevn:v2:pipeline:{project_id}:{goal_id}` — full pipeline result (steps, work units, environment, scores)
- `claudevn:v2:work_units:{project_id}:{goal_id}` — work units only
- `claudevn:v2:environment:{project_id}:{goal_id}` — environment spec
- `claudevn:v2:goals:{project_id}` — set of goal IDs with pipeline data

---

## 3. LLM Decomposition

### 3.1 Prompt Structure

The LLM receives:
- **System prompt:** Decomposition instructions, output schema with examples, rules
- **User prompt:** Goal text + project context + existing backlog + conversation history

### 3.2 Output Schema Per Unit

```json
{
  "description": "Concise statement of what to build",
  "target_files": ["path/to/file.js", "path/to/file.test.js"],
  "depends_on": ["Description of dependency unit"],
  "interface_contracts": {
    "produces": [
      {"type": "exports", "definition": "function add(a: number, b: number): number"}
    ],
    "consumes": [
      {"type": "imports", "definition": "calculator module — add, subtract functions"}
    ]
  },
  "acceptance_criteria": [
    "POST /calculate returns correct result for valid operations",
    "Returns 400 with error message for invalid input",
    "Unit tests pass for all operations including edge cases"
  ],
  "estimated_complexity": "s"
}
```

### 3.3 Rules Enforced by Prompt

1. Each unit touches SEPARATE files (true independence)
2. Test files included alongside implementation in the same unit
3. File paths are specific and realistic
4. Interface contracts define how units connect (produces/consumes)
5. Acceptance criteria are testable — not vague
6. Complexity estimates: xs=trivial, s=single module, m=multiple files, l=cross-cutting, xl=architectural
7. Dependencies ordered correctly (no cycles)

### 3.4 Model Selection

- Decomposition: **Sonnet** (quality matters, ~20-60s acceptable)
- Chat: **Haiku** (speed matters)
- Coherence analysis: **Sonnet** (cross-goal reasoning needs depth)

---

## 4. Work Unit Specification

### 4.1 Core Fields

| Field | Type | Purpose |
|-------|------|---------|
| `id` | string | Unique identifier (wu-{uuid12}) |
| `project_id` | string | Project isolation |
| `goal_ref` | string | Parent goal |
| `description` | string | Natural language for human review |
| `status` | enum | draft → ready → queued → executing → submitted → verifying → verified → completed |

### 4.2 Formal Spec

| Field | Type | Purpose |
|-------|------|---------|
| `target_files` | string[] | Exact files to modify/create |
| `input_state` | string | Git ref to start from |
| `expected_outputs` | Output[] | file_modified / file_created / file_deleted with constraints |
| `interface_contracts` | Contract[] | Interface boundaries (legacy format — see 4.4) |

### 4.3 Quality Metadata

| Field | Type | Purpose |
|-------|------|---------|
| `acceptance_criteria` | string[] | Testable done conditions |
| `estimated_complexity` | string | xs/s/m/l/xl |
| `interface_produces` | {type, definition}[] | What this unit outputs for others |
| `interface_consumes` | {type, definition}[] | What this unit expects from dependencies |

### 4.4 Interface Contracts

Interface contracts are the **chain connections** — they define how units relate at the code level.

**Produces:** What a unit creates that downstream units depend on.
- Type: `exports` | `api` | `schema` | `event` | `config`
- Definition: The actual interface (function signature, endpoint spec, schema shape)

**Consumes:** What a unit expects from its upstream dependencies.
- Type: Same as produces
- Definition: What it imports/calls/expects

**Example chain:**
```
Unit A (Calculator Logic)
  produces: {type: "exports", definition: "functions: add, subtract, multiply, divide"}

Unit B (API Endpoint)
  consumes: {type: "imports", definition: "calculator module functions"}
  produces: {type: "api", definition: "POST /calculate → {result} or {error}"}

Unit C (Frontend UI)
  consumes: {type: "api", definition: "POST /calculate endpoint"}
```

### 4.5 Independence Assertion

| Field | Type | Purpose |
|-------|------|---------|
| `shares_files_with` | string[] | Other unit IDs touching same files (should be empty) |
| `depends_on` | string[] | Unit IDs that must complete first |
| `depended_by` | string[] | Unit IDs waiting on this |

### 4.6 Verification Criteria

| Field | Type | Purpose |
|-------|------|---------|
| `automated` | Check[] | build_success, test_pass, lint_clean, type_check |
| `integration` | Check[] | interface_compatible, merge_clean, combined_tests_pass |

---

## 5. Quality Scoring

### 5.1 Per-Unit Score

Each work unit receives a quality score (0-100) based on:

| Factor | Weight | Scoring |
|--------|--------|---------|
| **Independence** | 25% | 100 if shares_files_with is empty; -50 per shared file |
| **Acceptance criteria quality** | 25% | 20 points per testable criterion (max 100); 0 if vague ("works correctly") |
| **Interface completeness** | 20% | 100 if both produces and consumes defined for dependent units; 0 if missing |
| **Complexity appropriateness** | 15% | 100 for xs/s; 80 for m; 50 for l; 20 for xl (large units should be split) |
| **Target file specificity** | 15% | 100 if all files have extensions and paths; penalize for vague paths |

Score interpretation:
- **80-100:** Ready for execution
- **60-79:** Acceptable, minor improvements possible
- **40-59:** Needs attention — review acceptance criteria and interfaces
- **0-39:** Not ready — re-decompose or refine

### 5.2 Overall Decomposition Confidence

Aggregate confidence (0-100) based on:

| Factor | Weight | Scoring |
|--------|--------|---------|
| **Average unit score** | 30% | Mean of per-unit scores |
| **Independence rate** | 20% | Percentage of units with no file overlaps |
| **Dependency validity** | 15% | Percentage of dependencies that resolved to real unit IDs |
| **Acceptance criteria coverage** | 15% | Percentage of units with ≥2 testable criteria |
| **Interface chain completeness** | 10% | For each dependency, does the upstream unit produce what downstream consumes? |
| **Validation errors** | 10% | 100 if zero errors; -20 per error |

Traffic light:
- **Green (≥75):** Confident — ready for approval
- **Yellow (50-74):** Needs review — check flagged items
- **Red (<50):** Not ready — re-decompose

### 5.3 Split/Merge Recommendations

The scoring system flags:
- **Split candidates:** Units with complexity L or XL, or units touching >6 files, or units with >4 acceptance criteria (scope too broad)
- **Merge candidates:** Adjacent units with complexity XS that share the same module/directory and have no other dependents

These appear as suggestions, not automatic actions.

---

## 6. Coherence Analysis

### 6.1 What It Detects

| Type | Description | Example |
|------|-------------|---------|
| **Contradiction** | Conflicting statements across goals | "lightweight" vs "rich 3D visualization" |
| **Implicit requirement** | Something implied but not specified | "mobile" implies responsive design |
| **Scope drift** | Goals evolving in ways that change architecture | Started as web app, now includes native mobile |
| **Gap** | Combined goals imply something unstated | API layer needed but not mentioned |
| **Unstated dependency** | Infrastructure need that follows from goals | Database needed but not specified |

### 6.2 How It Works

1. On goal creation or update, collect all goals + their work units for the project
2. Send to Sonnet with a system prompt that asks for inconsistency analysis
3. Parse structured response into CoherenceInsight objects
4. Store insights, display on Plan page
5. Re-run when decomposition changes or new goals are added

### 6.3 Insight Structure

```json
{
  "id": "insight-{uuid}",
  "type": "implicit_requirement",
  "severity": "medium",
  "title": "Mobile responsiveness not specified",
  "description": "Goal 2 mentions 'on my phone' but no work unit addresses responsive design or viewport handling",
  "sources": [
    {"goal_id": "goal-123", "goal_title": "Build calculator", "excerpt": "use it on my phone"}
  ],
  "suggestion": "Add a work unit for responsive CSS and viewport meta tags, or add acceptance criteria to the frontend unit",
  "affected_units": ["wu-abc123"]
}
```

---

## 7. Compute Environment

### 7.1 Detection

The EnvironmentAnalyzer scans:
1. Target files in work units → infer runtimes from extensions
2. Config files in repo (package.json, pyproject.toml, go.mod) → detect tools and versions
3. DevDependencies → listed for visibility but not installed as separate build steps

### 7.2 Dockerfile Generation

The generated Dockerfile extends `claudevn-compute-base` which provides:
- Python runtime, compute SSE engine, Claude CLI (via agent SDK), MCP server, entrypoint

The generated layer adds:
- Project-specific runtimes (Node.js, Go, Rust, etc.)
- Global tools not in the base image

Project dependencies (npm install, pip install) are installed at runtime after the compute clones the repo — not baked into the image.

### 7.3 Approval Flow

1. Pipeline produces environment spec (status: `proposed`)
2. Displayed on Plan page with requirements, Dockerfile preview
3. User clicks "Approve Environment"
4. Serving writes Dockerfile + metadata.json to `compute-envs/{project}/`
5. Status changes to `approved`, copyable run command shown
6. User runs `./compute-envs/start.sh {project}` on host
7. Script builds image, attaches to network, starts container
8. Container registers with serving via SSE

### 7.4 One Environment Per Goal

A goal produces one environment spec. If the goal's work units span multiple runtimes, the environment includes all of them. Multiple environments per goal is not supported — if runtimes are truly independent, they should be separate goals.

---

## 8. Plan Page User Experience

### 8.1 Layout

```
┌──────────────────────────────────────────────────┬──────────────┬───────────┐
│  Plan                                  [Refresh]  │ Goal History │ ChatRail  │
│                                                   │              │           │
│  ┌─ COHERENCE ────────────────────────────────┐  │  Goal 1      │  Goal-    │
│  │ Insights across all goals                  │  │  Goal 2 ◄──  │  context  │
│  └────────────────────────────────────────────┘  │  Goal 3      │  aware    │
│                                                   │              │           │
│  ┌─ COMPUTE ENVIRONMENT ── Proposed/Approved ─┐  │              │           │
│  │ Base, requirements, Dockerfile, run command │  │              │           │
│  └────────────────────────────────────────────┘  │              │           │
│                                                   │              │           │
│  ── When a goal is selected: ──                   │              │           │
│                                                   │              │           │
│  ┌─ PIPELINE STATUS ─────────────────── 7/7 ──┐  │              │           │
│  │ Steps with timing, status, details          │  │              │           │
│  └────────────────────────────────────────────┘  │              │           │
│                                                   │              │           │
│  ┌─ CONFIDENCE ──────────────── 82% GREEN ────┐  │              │           │
│  │ Independence | Criteria | Interfaces | ...  │  │              │           │
│  └────────────────────────────────────────────┘  │              │           │
│                                                   │              │           │
│  ┌─ DEPENDENCY CHAINS ───────────────────────┐   │              │           │
│  │ Chain 1: A → B → D (critical path, 3 units)│  │              │           │
│  │ Chain 2: C (independent, 1 unit)           │  │              │           │
│  │ Parallel: Chain 1 ∥ Chain 2                │  │              │           │
│  └────────────────────────────────────────────┘  │              │           │
│                                                   │              │           │
│  ┌─ WORK UNITS (5) ─────────────────────────┐   │              │           │
│  │ [S] wu-abc — Calculator logic      82/100 │   │              │           │
│  │ [S] wu-def — API endpoint          78/100 │   │              │           │
│  │ [M] wu-ghi — Frontend UI           65/100 │   │              │           │
│  │     ⚠ Missing acceptance criteria          │   │              │           │
│  │ [XS] wu-jkl — Config/scaffold      91/100│   │              │           │
│  │ [L] wu-mno — Integration tests     45/100 │   │              │           │
│  │     ⚠ Recommend splitting (6+ files)       │   │              │           │
│  └────────────────────────────────────────────┘  │              │           │
│                                                   │              │           │
│  [Approve Decomposition]  [Approve Environment]   │              │           │
└──────────────────────────────────────────────────┴──────────────┴───────────┘
```

### 8.2 Interactions

**View pipeline progress:** Pipeline status section shows each step with timing and pass/fail. Expandable for detail/error.

**Review confidence:** Traffic light with factor breakdown. Click a factor to see which units are bringing the score down.

**Examine chains:** Dependency chains show execution order. Critical path highlighted. Parallel chains identified. Click a unit in the chain to expand its card.

**Review work units:** Each card shows complexity badge, score, produces/consumes, acceptance criteria. Warnings for low-scoring units. Split/merge suggestions.

**Refine via chat:** ChatRail knows which goal is active. User can say "split the frontend unit into shell and calculator component" or "the API endpoint also needs CORS handling" — chat processes the refinement and re-runs the pipeline.

**Approve:** Two separate approvals:
1. Approve decomposition — transitions work units from draft to ready
2. Approve environment — writes Dockerfile to disk, shows run command

### 8.3 Recomposition

Recomposition is triggered by:
- User chat: "split this unit" / "merge these two"
- Scoring system: "recommend splitting — XL complexity"
- Coherence analysis: "missing unit for mobile responsiveness"

Recomposition re-runs the pipeline from step 1 (LLM) with additional context:
- The existing decomposition as reference
- The specific refinement request
- The scoring feedback

This is a supplemental decomposition pass — the LLM sees what exists and adjusts.

---

## 9. Validation Rules

### 9.1 Errors (Block Approval)

| Code | Rule |
|------|------|
| `duplicate_id` | Work unit IDs must be unique |
| `invalid_dependency` | depends_on must reference existing unit IDs |
| `self_dependency` | A unit cannot depend on itself |
| `circular_dependency` | No cycles in the dependency graph |

### 9.2 Warnings (Flag for Review)

| Code | Rule |
|------|------|
| `file_overlap` | Multiple units target the same file |
| `no_target_files` | Unit has no target files specified |
| `no_verification` | Unit has no automated verification criteria |
| `no_acceptance_criteria` | Unit has no acceptance criteria |
| `high_complexity` | Unit estimated as L or XL |
| `many_files` | Unit targets more than 6 files |
| `vague_criteria` | Acceptance criteria contain vague words ("works", "correct", "proper") |
| `missing_interface` | Dependent unit doesn't consume what upstream produces |

---

## 10. API Endpoints

### 10.1 Decomposition

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/decomposition/{goal_id}/work-units` | Get work units |
| GET | `/decomposition/{goal_id}/pipeline` | Get pipeline steps + status |
| GET | `/decomposition/{goal_id}/scores` | Get quality scores + confidence |
| POST | `/decomposition/{goal_id}/approve` | Approve decomposition |
| POST | `/decomposition/{goal_id}/recompose` | Trigger recomposition with refinement |
| GET | `/decomposition/{goal_id}/environment` | Get environment spec |
| POST | `/decomposition/{goal_id}/environment/approve` | Approve environment |
| GET | `/decomposition/coherence/{project_id}` | Get coherence insights |

### 10.2 Events (SSE)

| Event | When |
|-------|------|
| `decomposition.started` | Goal enters pipeline |
| `decomposition.step_completed` | Pipeline step finishes |
| `decomposition.step_failed` | Pipeline step fails |
| `decomposition.completed` | All steps done |
| `decomposition.scores_updated` | Quality scores recalculated |
| `decomposition.approved` | Decomposition approved |
| `decomposition.feedback` | Coherence or validation feedback |

---

## 11. Implementation Phases

### Phase 1: Scoring + Confidence (next)
- Implement quality scoring (Section 5)
- Confidence traffic light on Plan page
- Per-unit score display on WorkUnitCard
- Split/merge recommendations

### Phase 2: Coherence Analysis
- LLM-based cross-goal consistency (Section 6)
- Wire to CoherencePanel on Plan page
- Re-run on goal/decomposition changes

### Phase 3: Chain Visualization
- Dependency chain extraction from DAG
- Critical path calculation
- Parallel chain identification
- Interactive chain view on Plan page

### Phase 4: Recomposition
- Chat-driven refinement (supplemental decomposition pass)
- Split/merge API endpoints
- Re-score after recomposition

### Phase 5: Validation Enhancement
- Vague criteria detection
- Missing interface contract warnings
- Many-files split recommendations

---

## 12. Open Questions

1. **Scoring weights** — are the proposed weights right? Need tuning from real usage.
2. **Recomposition scope** — should recomposition replace all units or just the affected ones?
3. **Coherence frequency** — run on every goal change, or on-demand?
4. **Environment versioning** — when a recomposition changes runtime requirements, does the environment spec update automatically?
5. **Chain parallelism** — how do we communicate to the user that chains can run on separate computes vs must be sequential?
