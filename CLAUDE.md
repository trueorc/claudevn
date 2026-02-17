# ClaudeVN - AI Agent Orchestration Platform

## Project Overview

ClaudeVN enables emergent, conversation-driven coordination between specialized AI agents. Claude Code instances serve as compute workers, with Git-based state management and MCP tools for communication.

**Version:** 1.0.0 (Architecture Redesign)
**Status:** Major architecture redesign in progress

## Architecture (v1.0)

Two-tier architecture: Serving (central hub) + Compute (Claude Code instances)

| Component | Purpose |
|-----------|---------|
| **Serving** | Central coordination hub - work distribution, Git server, MCP server, monitoring UI |
| **Marketplace** | Skill marketplace service - skill definitions, registry, composition (port 8003) |
| **Compute** | Claude Code instances - execute work using skills, communicate via MCP and Git |

**Key Changes from v0.x:**
- Compute is now **Claude Code** (not custom Python runtime)
- Communication via **MCP tools** and **Git** (not REST APIs)
- State managed in **Git branches** (1 branch = 1 work unit)
- Skills replace agents (CLAUDE.md templates)
- Marketplace is a separate service (communicates via HTTP)

## Tech Stack

- **Serving:** FastAPI, Python 3.10+, Redis, Git (bare repos), MCP server (port 8002)
- **Marketplace:** FastAPI, Python 3.10+, skill registry, composition service (port 8003)
- **Compute:** Claude Code CLI with MCP client
- **State:** Git repositories with worktree workflow
- **Frontend:** React, TailwindCSS, WebSocket for real-time updates

## Key Directories

```
serving/              # Central coordination hub (v1.0) - port 8002
  ├── services/       # Core services including ComputeSpawner
  ├── git/            # Git infrastructure (SSH, hooks, PR management)
  ├── mcp/            # MCP server for compute communication
  └── frontend/       # React monitoring UI
marketplace/          # Skill marketplace service (v1.0) - port 8003
  ├── skills/         # Skill definitions (YAML)
  ├── api.py          # FastAPI router
  └── skill_registry.py  # Skill catalog service
compute/              # Compute infrastructure containers - register with Serving
docs/                 # Comprehensive documentation
  ├── design/architecture/v1.0-architecture.md  # New architecture
  ├── design/specifications/                     # Component specs
  ├── design/adr/                                # Architecture decisions
  └── archive/v0.x/                              # Legacy docs
```

## Authoritative Documentation (v1.0)

- `docs/design/architecture/v1.0-architecture.md` - System architecture
- `docs/design/specifications/git-infrastructure.md` - Git server design
- `docs/design/specifications/mcp-tools.md` - MCP tool specifications
- `docs/design/specifications/skill-marketplace.md` - Skill marketplace management
- `docs/guides/worktree-workflow.md` - Git worktree guide for compute

## Key Concepts (v1.0)

- **Goals:** User-defined high-level objectives. The AI interprets goals dynamically - decomposing them into backlog items, influencing execution priority, or both. This enables emergent, context-aware behavior.
- **Backlog Items:** Specific units of work that users can modify (priority, labels, assignments). The user's explicit influence point for specific work items. Accessible via `/backlog` in the UI.
- **Execution Plan:** System-managed view of active and queued work (`/plan`). Shows currently running items, ready queue, dependencies, and blocked items. Users can view but not directly modify the arrangement - the system arranges based on goal interpretation, backlog priorities, and dependencies.
- **Skills:** Atomic capability units (CLAUDE.md fragments) composed into agents for Claude Code instances
- **Git Worktrees:** Compute instances use worktrees for parallel branch access
- **MCP Tools:** Communication protocol between compute and serving
- **PR Queue:** Redis-backed branch status and merge management

## Development Rules

1. All code changes go through Pull Requests (never push directly to main)
2. Compute instances work on branches: `{type}/{task}/{compute-id}`
3. Only Serving can merge to main
4. Use Git worktrees: `/workspace/main` (reference) + `/workspace/active` (work)

## GitHub Project Board

```yaml
github_project:
  owner: Guarrdon
  number: 2
  project_id: PVT_kwHOAP6mx84BNtCx
  fields:
    status:
      id: PVTSSF_lAHOAP6mx84BNtCxzg8nxFg
      options:
        backlog: f75ad846
        ready: 08afe404
        in_progress: 47fc9ee4
        in_review: 4cc61d42
        done: 98236657
    priority:
      id: PVTSSF_lAHOAP6mx84BNtCxzg8nxLg
      options:
        P0: 79628723
        P1: 0a877460
        P2: da944a9c
        P3: f55ea659
    size:
      id: PVTSSF_lAHOAP6mx84BNtCxzg8nxLk
      options:
        XS: eff732af
        S: 9592a5a3
        M: 9728cbdc
        L: c53df028
        XL: 7b141a16
```

## Issue Creation Requirements

All issues MUST include:
1. **Title**: `[PRIORITY] Brief description` (e.g., `[P0] Implement SSH Git Server`)
2. **Labels**:
   - Priority: `P0`, `P1`, `P2`, or `P3`
   - Type: `bug`, `enhancement`, or `documentation`
   - Area: `area:serving`, `area:compute`, `area:marketplace`, `area:git`, `area:mcp`, `area:frontend`
   - Special: `test` (if test-related), `architecture` (if design change)
3. **Project Board Fields**: Set Priority and Status via GraphQL API

See `docs/guides/issue-creation-guide.md` for complete instructions.

## Legacy Documentation

v0.x documentation is preserved in `docs/archive/v0.x/` for reference.
