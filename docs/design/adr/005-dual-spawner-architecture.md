# ADR-005: Dual Spawner Architecture for Claude Code Orchestration

## Status
Accepted

## Date
2026-01-31

## Context

ClaudeVN v1.0 contains two distinct implementations for spawning Claude Code instances:

1. **Serving-side Spawner**: `serving/services/compute_spawner.py` (775 lines)
2. **Compute-side Spawner**: `compute/services/claude_code_spawner.py` (625 lines)

This raised questions about architectural intent, duplication, and when each should be used.

### The Two Spawners

#### Serving-side Spawner (`ComputeSpawner`)
- Runs within the Serving component
- Spawns Claude Code processes directly on the Serving host
- Full integration with marketplace for skill composition
- Issues and manages API keys for instances
- Tracks instance lifecycle and metrics
- Creates workspaces and Git worktrees locally

#### Compute-side Spawner (`ClaudeCodeSpawner`)
- Runs within Compute Infrastructure (Docker container)
- Spawns Claude Code in response to SSE `work_assigned` events
- Receives pre-composed skills via MCP `claudevn_get_assignment`
- Lightweight, event-driven design
- Reports lifecycle events back to Serving via HTTP
- Creates workspaces and Git worktrees within container

### Deployment Models

The two spawners support different deployment models:

**Model A: Centralized (Serving-side)**
```
Serving (with ComputeSpawner)
    │
    └── Spawns Claude Code directly on Serving host
        │
        └── Claude Code uses MCP to communicate with Serving
```

**Model B: Distributed (Compute-side)**
```
Serving (no spawning, SSE push only)
    │
    └── SSE: work_assigned
        │
        ▼
Compute Infrastructure (Docker container)
    │
    └── ClaudeCodeSpawner spawns Claude Code
        │
        └── Claude Code uses MCP to communicate with Serving
```

## Decision

**Retain both spawners as they serve distinct deployment models.**

| Aspect | Serving-side | Compute-side |
|--------|--------------|--------------|
| **Location** | Serving component | Compute container |
| **Trigger** | API call to `/api/v1/spawner/spawn` | SSE `work_assigned` event |
| **Skill Composition** | Direct marketplace integration | Via MCP `claudevn_get_assignment` |
| **API Keys** | Issues keys | Receives key in assignment |
| **Use Case** | Development, single-host | Production, distributed |
| **Scaling** | Limited to Serving host | Scale-out compute fleet |

### Recommended Use Cases

#### Use Serving-side Spawner When:
- **Development/Testing**: Running everything on a single machine
- **Quick Prototyping**: No container infrastructure needed
- **Direct Control**: Serving needs to spawn and manage instances directly
- **Simple Deployments**: All-in-one installation

#### Use Compute-side Spawner When:
- **Production Deployment**: Distributed compute fleet
- **Scale-out**: Multiple compute containers across hosts
- **Resource Isolation**: Claude Code runs in isolated containers
- **SSE-based Registration**: Using the v1.0 event-driven model

### Integration with v1.0 Architecture

The v1.0 SSE-based registration model (see `compute-registration.md`) is designed around the **Compute-side Spawner**:

1. Compute container connects to Serving via SSE
2. Serving pushes `work_assigned` event with task ID
3. Compute fetches full assignment via MCP `claudevn_get_assignment`
4. `ClaudeCodeSpawner` spawns Claude Code with skills and context
5. Claude Code executes, reports progress, completes
6. Compute sends lifecycle events to Serving via HTTP

The **Serving-side Spawner** is an alternative for simpler deployments where Serving directly manages Claude Code instances without the container layer.

## Rationale

### Why Not Consolidate?

The spawners have different responsibilities and dependencies:

1. **Different Triggers**: One responds to API calls, the other to SSE events
2. **Different Contexts**: One has marketplace access, the other receives composed skills
3. **Different Lifecycles**: One manages long-running instances, the other per-task instances
4. **Different Environments**: One runs on Serving host, the other in containers

Consolidation would require either:
- Making Serving aware of container internals (breaks abstraction)
- Making Compute aware of marketplace (adds coupling)

### Why Keep Both?

1. **Flexibility**: Support both centralized and distributed deployment
2. **Development Experience**: Serving-side spawner simplifies local dev
3. **Production Scale**: Compute-side spawner enables fleet scaling
4. **Clean Separation**: Each spawner operates in its own context

## Consequences

### Documentation Updates

1. Add spawner architecture section to `compute-registration.md`
2. Add code comments referencing this ADR in both spawner files
3. Create deployment guide distinguishing the two models

### Code Comments

Each spawner file should include a header comment explaining:
- Which deployment model it serves
- When to use this vs. the other spawner
- Reference to this ADR

### Operational Clarity

Operators must understand which model they're deploying:
- All-in-one/dev → Serving-side spawner
- Distributed/prod → Compute-side spawner with SSE registration

### Future Considerations

If consolidation is desired in future versions:
- Consider a shared base class for common functionality
- Keep deployment-specific logic in separate implementations
- Maintain clear separation of triggering mechanisms

## Alternatives Considered

### Consolidate into Single Spawner
Rejected - different deployment models require different integration points and dependencies.

### Remove Serving-side Spawner
Rejected - valuable for development and simple deployments without container infrastructure.

### Remove Compute-side Spawner
Rejected - required for production distributed deployment model.

### Abstract Common Code Only
Considered for future - would reduce code duplication while maintaining separate spawner classes.

## References

- Issue: #180
- Related: ADR-003 (Notification + Fetch pattern)
- Related: ADR-004 (Slim Claude Code Orchestration)
- Specification: `docs/design/specifications/compute-registration.md`
