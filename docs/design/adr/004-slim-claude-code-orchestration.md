# ADR-004: Implement Slim Claude Code Orchestration Layer for v1.0

## Status
Accepted

## Date
2026-01-31

## Context

ClaudeVN's v1.0 architecture specifies a "Slim Claude Code" component for intent-based orchestration. A business audit identified this as unimplemented, raising the question of whether to implement, descope, or simplify for v1.0.

### Current State

The existing implementation is a **task dispatch system**:
- Human creates issues/goals manually
- Work Orchestrator assigns issues to compute instances
- Compute executes and reports back

### Vision Gap

ClaudeVN's core differentiator is **Intent-Based Orchestration** - one of three pillars:

1. **AI Collaboration State**: Infrastructure for Users + AI working together on shared state
2. **Claude Virtual Network**: Distributed network of Claude Code instances
3. **Intent-Based Orchestration**: AI determines how to approach work at project/portfolio level

Without Intent-Based Orchestration, ClaudeVN is a sophisticated task queue, not an AI-native platform.

## Decision

**Implement Slim Claude Code for v1.0** with two core components:

### 1. Goal Decomposer

Takes a natural language goal from a Product Owner and uses Claude to break it into discrete issues with:
- Clear titles and descriptions
- Dependencies between issues
- Required skills/capabilities
- Priority assignments
- Area classifications

### 2. Work Planner

Analyzes the decomposed issues and determines:
- Execution ordering based on dependencies
- Parallelization opportunities
- Resource requirements
- Risk assessment

### Architecture

```
Product Owner (UI)
       │
       ▼ creates goal (natural language)
┌──────────────────────────────────────┐
│       SLIM CLAUDE CODE               │
│                                      │
│  ┌────────────────────────────────┐  │
│  │      Goal Decomposer           │  │
│  │   (Claude-powered service)     │  │
│  │                                │  │
│  │  - Parse intent               │  │
│  │  - Identify tasks              │  │
│  │  - Define dependencies         │  │
│  │  - Assign skills/priority      │  │
│  └────────────────────────────────┘  │
│               │                      │
│               ▼                      │
│  ┌────────────────────────────────┐  │
│  │       Work Planner             │  │
│  │   (Claude-powered service)     │  │
│  │                                │  │
│  │  - Determine approach          │  │
│  │  - Optimize ordering           │  │
│  │  - Identify parallelism        │  │
│  │  - Assess risks                │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
               │
               ▼ issues with dependencies
┌──────────────────────────────────────┐
│       Work Orchestrator              │  ← EXISTS
│   (assigns to compute instances)     │
└──────────────────────────────────────┘
               │
               ▼
        Compute Instances
```

### v1.0 Scope Boundaries

**In Scope:**
- Goal input via Serving UI (Product Owner role)
- AI-powered goal → issues decomposition
- AI-determined dependency ordering
- Integration with existing Work Orchestrator
- Human approval checkpoint before execution

**Deferred to v1.1+:**
- Result Synthesizer (combining completed work)
- Multi-source intent inputs (integrations, APIs)
- Fully autonomous execution (no approval checkpoint)
- Cross-project orchestration

## Rationale

### Why Not Descope?

Intent-Based Orchestration is a core differentiator. Without it, ClaudeVN competes with conventional task management tools rather than offering a novel AI-native approach.

### Why Not Simplify Further?

A simplified version (e.g., template-based decomposition) would not deliver the "AI determines approach" value proposition. The power is in Claude understanding intent and making planning decisions.

### Why Include Human Approval?

For v1.0, Product Owners need visibility and control over what the AI plans. This builds trust and allows learning. Fully autonomous execution can come in v1.1+ once patterns are established.

## Consequences

### Implementation Required

1. **Goal Decomposer Service**: New service using Claude API to parse goals
2. **Work Planner Service**: New service for execution planning
3. **UI Updates**: Goal input form, plan review/approval interface
4. **Issue Service Integration**: Batch creation of decomposed issues
5. **Work Orchestrator Integration**: Accept planned work from Slim Claude Code

### Existing Assets Leveraged

- `IssueService` already supports Goals and Issues with dependencies
- `IssueBatchCreateRequest` exists for bulk issue creation
- `WorkOrchestrator` handles assignment to compute
- `SkillSelectionService` matches capabilities to skills

### Testing Strategy

- Unit tests for decomposition logic
- Integration tests for end-to-end goal → execution flow
- Human evaluation of decomposition quality

## Alternatives Considered

### Descope to v1.1+
Rejected - removes core differentiator from v1.0 launch.

### Template-Based Decomposition
Rejected - doesn't deliver AI-native value; just another workflow tool.

### Full Autonomy from v1.0
Rejected - too risky without human oversight; trust needs to be built.

## References

- Issue: #209
- v1.0 Architecture: `docs/design/architecture/v1.0-architecture.md`
- Related: ADR-003 (Notification + Fetch pattern)
