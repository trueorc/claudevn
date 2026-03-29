# ClaudeVN - Intelligence Layer for Project-Scale AI Development

## Project Overview

ClaudeVN is the intelligence layer that makes Claude Code work at project scale. It decomposes ambiguous goals into formally specified work units, prepares each unit for efficient execution, and verifies that independently-produced results integrate correctly.

**Version:** 2.0.0 (Three-Layer Architecture)
**Status:** Active development on `feat/v2.0-architecture` branch

## Architecture (v2.0)

Three-layer intelligence model: Decomposition → Execution → Verification

| Layer | Purpose |
|-------|---------|
| **Layer 1: Decomposition** | Transform goals into formally specified, independent work units with verification criteria |
| **Layer 2: Execution** | Simple priority queue dispatch — inject context, dispatch to Claude Code, get out of the way |
| **Layer 3: Verification** | Computational verification of per-unit output and cross-unit integration |

**Design principles:**
- Structured state over conversation
- Single-pass execution over iterative exploration
- Computational verification over AI-as-reviewer
- Independence by design — if units share state, they should be one unit
- Queue/event-driven everywhere — no polling

See `docs/design/architecture/v2.0-architecture.md` for full design rationale and research foundation.

## Tech Stack

- **Serving:** FastAPI, Python 3.10+, Redis, Git (bare repos), MCP server (port 8002)
- **Marketplace:** FastAPI, Python 3.10+, skill registry (port 8003) — retained, not actively invested
- **Compute:** Claude Code CLI with MCP client
- **State:** Git repositories, Redis for transient state
- **Frontend:** React 19, Vite, TailwindCSS, SSE for real-time updates (no polling)
- **Events:** Async pub/sub EventBus with project-scoped SSE delivery

## Key Directories

```
serving/
  ├── services/
  │   ├── decomposition/    # Layer 1: GoalAnalyzer, BoundaryDetector, WorkUnitBuilder, SpecValidator, ContextAssembler
  │   ├── dispatch/         # Layer 2: DispatchQueue, Dispatcher (priority queue, not orchestration)
  │   ├── verification/     # Layer 3: UnitVerifier, IntegrationVerifier, RetryHandler
  │   ├── events/           # EventBus, SSEBridge, typed event definitions (project-scoped)
  │   └── ...               # Existing services (goal_service, work_map_service, etc.)
  ├── models/
  │   └── work_unit/        # WorkUnit, FormalSpec, VerificationCriteria, ContextPackage, IndependenceAssertion, CoherenceInsight
  ├── api/
  │   ├── v2_events.py      # SSE stream endpoint
  │   ├── v2_decomposition.py  # Work units, approval, coherence
  │   ├── v2_verification.py   # Per-unit results, integration, retry/approve
  │   ├── v2_dispatch.py       # Queue and active execution visibility
  │   └── ...               # Existing API routes
  ├── git/                  # Git infrastructure (Smart HTTP, hooks, PR management)
  ├── mcp/                  # MCP server for compute communication
  └── frontend/
      └── src/
          ├── pages/
          │   ├── GoalsPage.jsx         # Decomposition workspace (not chat — ChatRail handles that)
          │   ├── ExecutionPlanPage.jsx  # Queue observability, pipeline health, activity log
          │   ├── VerificationPage.jsx   # Per-unit results, integration, retry/approve
          │   └── ...
          ├── components/
          │   ├── decomposition/  # DecompositionSummary, DependencyGraph, WorkUnitCard, WorkUnitList, CoherencePanel
          │   ├── plan/           # PipelineHealth, StuckWorkDetector, EventActivityLog, SummaryBar, ActiveWorkView
          │   └── dashboard/      # DecompositionPanel, VerificationPanel, ExecutionStrip (+ existing panels)
          ├── hooks/
          │   └── useEventStream.js  # SSE subscription hook (project-scoped, replaces polling)
          └── api/
              ├── events.js      # SSE connection
              └── workUnits.js   # Decomposition, verification, dispatch API calls
marketplace/              # Skill marketplace service - port 8003 (retained)
compute/                  # Compute infrastructure containers
docs/
  ├── design/architecture/v2.0-architecture.md  # Authoritative architecture document
  ├── design/architecture/v1.0-architecture.md  # Previous architecture (reference)
  └── ...
```

## Key Concepts (v2.0)

- **Goals:** User-defined objectives decomposed into formally specified work units
- **Work Units:** The atomic unit of work — has formal spec (target files, interface contracts, expected outputs), verification criteria, context package, and independence assertions
- **Formal Spec:** Structured specification replacing natural language task descriptions — target files, interface boundaries, expected outputs
- **Independence Assertion:** Declaration that a work unit shares no mutable state with others during execution. File overlaps are flagged.
- **Verification Criteria:** Computational checks (build, test, lint, type check, scope containment) — no LLM judgment
- **Context Package:** Pre-assembled files/tests/diffs injected into Claude Code instance — zero exploration needed
- **Coherence Analysis:** Cross-goal consistency checking — detects contradictions, implicit requirements, scope drift, gaps
- **EventBus:** Async pub/sub with project-scoped delivery — all inter-layer communication is event-driven

## v1.0 Services Removed

These v1.0 coordination overhead services have been deleted:
- ContextAffinityService, FeedbackAggregationService, PlannerProfileService
- PlannerFocusService, LeadComputeService, CoordinatingTeamService
- SpecializationService, BucketReorganizationService, BucketTreeStore

Rationale: Multi-agent coordination overhead replaced by the three-layer model.

## Development Rules

1. All code changes go through Pull Requests (never push directly to main)
2. All inter-service communication must be queue/event-based — no polling
3. Prefer small, composable Python files over large monolithic services
4. Every project-scoped model and event must carry `project_id` — projects are fully independent
5. Computational verification over AI-as-reviewer wherever possible
6. v2.0 work is on `feat/v2.0-architecture` branch (tagged `v1.0-final` on main)

## GitHub Project Board

```yaml
github_project:
  owner: trueorc
  number: 1
  project_id: PVT_kwDOD6FTDM4BQFhJ
  fields:
    status:
      id: PVTSSF_lADOD6FTDM4BQFhJzg-Tsck
      options:
        backlog: f75ad846
        ready: 08afe404
        in_progress: 47fc9ee4
        testing: 60064e37
        in_review: 4cc61d42
        done: 98236657
    priority:
      id: PVTSSF_lADOD6FTDM4BQFhJzg-Tsfw
      options:
        P0: 79628723
        P1: 0a877460
        P2: da944a9c
    size:
      id: PVTSSF_lADOD6FTDM4BQFhJzg-Tsf0
      options:
        XS: eff732af
        S: 9592a5a3
        M: 9728cbdc
        L: c53df028
        XL: 7b141a16
```

## Issue Creation Requirements

All issues MUST include:
1. **Title**: `[PRIORITY] Brief description` (e.g., `[P0] Implement Git Smart HTTP Server`)
2. **Labels**:
   - Priority: `P0`, `P1`, or `P2`
   - Type: `bug`, `enhancement`, or `documentation`
   - Area: `area:serving`, `area:compute`, `area:marketplace`, `area:git`, `area:mcp`, `area:frontend`
   - Special: `test` (if test-related), `architecture` (if design change)
3. **Project Board Fields**: Set Priority and Status via GraphQL API

See `docs/guides/issue-creation-guide.md` for complete instructions.

## Legacy Documentation

- v1.0 architecture: `docs/design/architecture/v1.0-architecture.md`
- Legacy docs preserved in `docs/archive/`
