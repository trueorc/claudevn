# ClaudeVN Documentation

Welcome to the ClaudeVN platform documentation. This directory contains all design documents, guides, specifications, and release notes.

---

## v1.0 Architecture Redesign

**ClaudeVN v1.0 represents a fundamental architecture change.** The platform now uses:

- **Claude Code** as the compute execution engine (replacing custom Python runtime)
- **Git** for state management (branches = work units)
- **MCP tools** for compute-serving communication
- **Personas** instead of agents (CLAUDE.md templates)

### Primary v1.0 Documentation

| Document | Purpose |
|----------|---------|
| [design/architecture/v1.0-architecture.md](design/architecture/v1.0-architecture.md) | Complete architecture overview |
| [design/specifications/git-infrastructure.md](design/specifications/git-infrastructure.md) | Git server, SSH, hooks, Redis PR queue |
| [design/specifications/mcp-tools.md](design/specifications/mcp-tools.md) | MCP tool specifications for compute |
| [design/specifications/persona-marketplace.md](design/specifications/persona-marketplace.md) | Persona registry and definitions |
| [guides/core-use-cases.md](guides/core-use-cases.md) | Core use cases and platform workflows |
| [guides/serving-ui-guide.md](guides/serving-ui-guide.md) | Guide to each tab in the Serving UI |
| [guides/worktree-workflow.md](guides/worktree-workflow.md) | Git worktree guide for compute instances |

---

## Documentation Organization

### 🏗️ [design/](design/)
Architectural designs and technical specifications.

#### [design/architecture/](design/architecture/)
- **[v1.0-architecture.md](design/architecture/v1.0-architecture.md)** - v1.0 system architecture (NEW)
- [platform-overview.md](design/architecture/platform-overview.md) - Platform concepts (v0.x)
- [diagrams.md](design/architecture/diagrams.md) - Architecture diagrams (v0.x)

#### [design/specifications/](design/specifications/)
**v1.0 Specifications:**
- **[git-infrastructure.md](design/specifications/git-infrastructure.md)** - Git server design
- **[mcp-tools.md](design/specifications/mcp-tools.md)** - MCP tool specifications
- **[persona-marketplace.md](design/specifications/persona-marketplace.md)** - Persona management

**Legacy (v0.x):**
- [marketplace-spec.md](design/specifications/marketplace-spec.md) - Marketplace service design
- [serving-implementation-plan.md](design/specifications/serving-implementation-plan.md) - Serving implementation
- [coordinating-agents-spec.md](design/specifications/coordinating-agents-spec.md) - Coordinating agents

### 📚 [guides/](guides/)
User guides and tutorials.

**v1.0 Guides:**
- **[core-use-cases.md](guides/core-use-cases.md)** - Core use cases and workflows
- **[serving-ui-guide.md](guides/serving-ui-guide.md)** - Guide to each Serving UI tab
- **[worktree-workflow.md](guides/worktree-workflow.md)** - Git worktree workflow for compute

**General Guides:**
- [QUICK_REFERENCE.md](guides/QUICK_REFERENCE.md) - Common commands
- [TESTING_GUIDE.md](guides/TESTING_GUIDE.md) - Testing guide
- [CONFIGURATION_GUIDE.md](guides/CONFIGURATION_GUIDE.md) - Configuration reference

### 🛠️ [development/](development/)
Developer documentation and implementation details.

- [project-structure.md](development/project-structure.md) - Project organization
- [llm-integration.md](development/llm-integration.md) - LLM integration guide (v0.x)

### 📦 [releases/](releases/)
Version-specific change documentation.

- [0.2.1/](releases/0.2.1/) - Process Map Observability
- [0.2.0/](releases/0.2.0/) - Facilitated Process Architecture
- [0.1.x/](releases/) - Earlier releases

### 📁 [archive/v0.x/](archive/v0.x/)
**153 documents** from v0.x architecture (three-microservice model). Essential reference for v1.0 design.

Key reference documents:
- `root/FUNCTIONAL_REQUIREMENTS.md` - FR-1 to FR-15 requirements
- `root/TECHNICAL_DECISIONS.md` - All design decisions with rationale
- `design/specifications/coordinating-agents-spec.md` - Persona design reference
- `design/specifications/PROCESS_MAP_OBSERVABILITY.md` - Work Map concepts

---

## Quick Reference

### Architecture Summary (v1.0)

```
┌──────────────────────────────────────────────────────────────┐
│                         SERVING                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ Persona     │  │ MCP Server  │  │ Slim Claude Code    │   │
│  │ Marketplace │  │             │  │ (orchestration)     │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ Work Map    │  │ Compute     │  │ Monitoring UI       │   │
│  │             │  │ Registry    │  │                     │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ Git Infrastructure (SSH + Bare Repos + Redis Queue)   │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
         │ MCP                    │ Git (SSH)
         ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    COMPUTE INSTANCES                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │Claude Code  │  │Claude Code  │  │Claude Code  │  ...      │
│  │+ Persona    │  │+ Persona    │  │+ Persona    │           │
│  │+ Worktrees  │  │+ Worktrees  │  │+ Worktrees  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└──────────────────────────────────────────────────────────────┘
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Persona** | Role definition (CLAUDE.md) for Claude Code instances |
| **Work Map** | Dynamic task allocation and dependency tracking |
| **Git Worktrees** | Parallel branch access: `/workspace/main` + `/workspace/active` |
| **MCP Tools** | Communication protocol (get_assignment, report_progress, etc.) |
| **PR Queue** | Redis-backed branch status and merge management |

### Branch Naming

```
{type}/{task-slug}/{compute-id}

Examples:
  f/implement-auth/compute-001     (feature)
  x/fix-login-bug/compute-023      (fix)
  r/cleanup-api/compute-007        (refactor)
```

---

## Version History

| Version | Architecture | Status |
|---------|--------------|--------|
| **1.0.0** | Claude Code compute, Git-based state, MCP tools | In Development |
| 0.3.0 | Three microservices (Marketplace, Serving, Compute) | Archived |
| 0.2.x | Process maps, coordinating agents | Archived |
| 0.1.x | Basic agent execution | Archived |

---

## Contributing to Documentation

### Adding New Documentation

1. Determine category: design/, guides/, development/, or releases/
2. Create markdown file with clear structure
3. Update this README with link
4. Link related documents

### Documentation Standards

- Use Markdown format (.md)
- Include table of contents for long documents
- Use code blocks with language tags
- Include examples where appropriate
- Link between related documents

---

**ClaudeVN Platform Documentation** - Version 1.0.0 (Architecture Redesign)
