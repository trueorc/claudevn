# ClaudeVN v0.x Documentation Archive

**153 documents preserved** from the v0.x architecture (three-microservice model).

This archive is **essential reference material** for building v1.0. The v0.x documentation contains detailed specifications for concepts that will inform the new architecture.

---

## Archive Structure

```
archive/v0.x/
├── root/                    # Root-level authoritative docs
│   ├── FUNCTIONAL_REQUIREMENTS.md   # What ClaudeVN does (FR-1 to FR-15)
│   └── TECHNICAL_DECISIONS.md       # How it was built (TD-xxx decisions)
│
├── docs-root/               # Implementation planning docs
│   ├── EMERGENT_WORKFLOW_IMPLEMENTATION.md  # Week-by-week implementation plan
│   ├── END_TO_END_AUDIT.md                  # Complete audit of 11 E2E processes
│   ├── E2E_GAPS_SUMMARY.md                  # Quick reference for gaps
│   ├── ARCHITECTURE_RESOLUTION_SUMMARY.md   # Gap analysis summary
│   ├── WEEK1-6_IMPLEMENTATION_COMPLETE.md   # Phase completion docs
│   └── ...
│
├── design/
│   ├── architecture/        # System architecture docs
│   │   ├── platform-overview.md             # Platform concepts
│   │   ├── diagrams.md                      # Architecture diagrams
│   │   ├── serving-architecture.md          # Serving component design
│   │   ├── EXECUTION_PIPELINE_ARCHITECTURE.md
│   │   └── FACILITATED_PROCESS_*.md
│   │
│   └── specifications/      # Detailed specs
│       ├── marketplace-spec.md              # Complete marketplace design
│       ├── coordinating-agents-spec.md      # Process Mapper, Facilitator, etc.
│       ├── OBSERVABILITY_*.md               # Event-driven observability
│       ├── serving-implementation-plan.md   # 6-phase implementation
│       └── ...
│
├── development/             # Implementation docs
│   ├── project-structure.md
│   ├── llm-integration.md                   # LLM provider patterns
│   ├── PIPELINE_*.md
│   ├── serving/                             # Serving-specific implementation
│   └── ...
│
├── guides/                  # User guides
│   ├── QUICK_REFERENCE.md
│   ├── TESTING_GUIDE.md
│   ├── CONFIGURATION_GUIDE.md
│   └── ...
│
├── testing/                 # Test documentation
│   ├── FUNCTIONAL_TEST_PLAN.md
│   └── ...
│
├── deployment/              # Deployment guides
│   ├── DOCKER_GUIDE.md
│   └── ...
│
├── releases/                # Version history
│   ├── 0.2.1/              # Process Map Observability
│   ├── 0.2.0/              # Facilitated Process Architecture
│   ├── 0.1.8/              # Execution Pipeline
│   └── ...
│
└── services/                # Service-specific READMEs
    ├── marketplace/
    ├── serving/
    ├── compute/
    └── shared/
```

---

## Key Documents for v1.0 Reference

### Understanding What We're Building

| Document | Why It Matters |
|----------|----------------|
| `root/FUNCTIONAL_REQUIREMENTS.md` | Defines FR-1 to FR-15 - most still apply to v1.0 |
| `root/TECHNICAL_DECISIONS.md` | Documents all design decisions with rationale |
| `docs-root/END_TO_END_AUDIT.md` | Audits 11 E2E processes - helps identify what v1.0 must support |

### Coordinating Agent Concepts

| Document | Relevance to v1.0 |
|----------|-------------------|
| `design/specifications/coordinating-agents-spec.md` | Defines Process Mapper, Facilitator, etc. - informs persona design |
| `design/architecture/FACILITATED_PROCESS_INTEGRATION.md` | Emergent workflow patterns |
| `docs-root/EMERGENT_WORKFLOW_IMPLEMENTATION.md` | Implementation approach for emergent coordination |

### Process Maps and Observability

| Document | Relevance to v1.0 |
|----------|-------------------|
| `design/specifications/PROCESS_MAP_OBSERVABILITY.md` | Process map concepts → Work Map in v1.0 |
| `design/specifications/OBSERVABILITY_EVENT_DRIVEN.md` | Event patterns for monitoring |
| `design/specifications/OBSERVABILITY_FINAL_DESIGN.md` | UI and real-time updates |

### Marketplace Concepts

| Document | Relevance to v1.0 |
|----------|-------------------|
| `design/specifications/marketplace-spec.md` | Agent registry → Persona Marketplace |
| `design/specifications/agent-approval-and-scope-system.md` | Organization/access patterns |

### LLM Integration Patterns

| Document | Relevance to v1.0 |
|----------|-------------------|
| `development/llm-integration.md` | Provider abstraction patterns |
| `root/TECHNICAL_DECISIONS.md` (TD-LLM*) | Prompt templates, structured output |

---

## v0.x Architecture Summary

### Three Microservices

| Service | Port | Purpose | v1.0 Status |
|---------|------|---------|-------------|
| **Marketplace** | 8001 | Agent registry, capability search | Absorbed into Serving |
| **Serving** | 8002 | Orchestration, sessions, process maps | Transformed (adds Git, MCP) |
| **Compute** | 8003+ | Agent execution, LLM integration | Replaced by Claude Code |

### Communication Patterns (v0.x)

- **REST APIs** between all components
- **WebSocket** for real-time UI updates
- **Event Bus** for observability
- **Phone-home registration** for compute instances

### Key Abstractions

| Concept | v0.x Implementation | v1.0 Equivalent |
|---------|--------------------|-----------------|
| Agent | JSON definition with prompts | Persona (CLAUDE.md) |
| Session | SQLite-stored execution context | Git branch + Work Map entry |
| Process Map | JSON with activities, dependencies | Work Map in Serving |
| Task Result | In-memory + event bus | Git commit + MCP report |

---

## Migration Checklist

When building v1.0 features, check these v0.x docs:

- [ ] **Persona design** → Review `coordinating-agents-spec.md` for role definitions
- [ ] **Work Map** → Review `PROCESS_MAP_OBSERVABILITY.md` for activity/dependency concepts
- [ ] **MCP tools** → Review `FUNCTIONAL_REQUIREMENTS.md` FR-4, FR-5, FR-6 for facilitation requirements
- [ ] **Git workflow** → Review `END_TO_END_AUDIT.md` for workflow patterns
- [ ] **Monitoring UI** → Review `OBSERVABILITY_*.md` for real-time update patterns

---

## Related Documents

Current v1.0 documentation:
- [docs/design/architecture/v1.0-architecture.md](../../design/architecture/v1.0-architecture.md)
- [docs/design/specifications/](../../design/specifications/)
- [docs/README.md](../../README.md)
