# ADR-003: Work Assignment via Notification + Fetch Pattern

## Status
Accepted

## Date
2026-01-31

## Context

There was inconsistency between documentation and implementation regarding how Compute receives work assignments:

- **mcp-tools.md** stated `claudevn_get_assignment` was "removed" because "work is PUSHED via SSE"
- **v1.0-architecture.md** listed `claudevn_get_assignment` as an available MCP tool
- **Implementation** has `claudevn_get_assignment` fully implemented and in use

This confusion stemmed from conflating two different approaches:
1. **Full Push**: Serving pushes complete work details via SSE (large payloads, coupling)
2. **Full Pull**: Compute polls for work (inefficient, no real-time awareness)

### Architectural Constraint

Serving can push events TO Compute via SSE, but Serving cannot directly call Compute's API. This is by design - Compute instances may be behind NAT, firewalls, or in different networks.

## Decision

**Adopt a Notification + Fetch pattern for work assignment.**

The flow is:

1. **Serving pushes lightweight SSE event**: `work_assigned` with just `task_id` and minimal metadata
2. **Compute calls MCP tool**: `claudevn_get_assignment(task_id=X)` to fetch full details
3. **Serving returns complete assignment**: Full task details, skills, context, etc.

```
Serving                          Compute
   │                                │
   │  SSE: work_assigned            │
   │  { task_id: "task-456" }       │
   │ ─────────────────────────────> │
   │                                │
   │        MCP: get_assignment     │
   │        { task_id: "task-456" } │
   │ <───────────────────────────── │
   │                                │
   │        Response: full details  │
   │        { task, skills, ctx }   │
   │ ─────────────────────────────> │
   │                                │
```

## Rationale

### Why Not Full Push?

- SSE payloads should be lightweight for reliability
- Merged skill instructions can be large (multiple KB)
- Compute might not be ready to accept work immediately
- Push couples SSE format tightly with assignment schema

### Why Not Full Pull (Polling)?

- Inefficient - requires periodic polling
- No real-time awareness of work availability
- Compute doesn't know when to poll

### Why Notification + Fetch?

1. **Lightweight SSE**: Events stay small and reliable
2. **Compute Controls Timing**: Fetch when ready to work
3. **Decoupled Schemas**: SSE event schema independent of assignment details
4. **Retry-Friendly**: If fetch fails, compute can retry without re-notification
5. **Standard Pattern**: Similar to how webhooks work (notify, then callback for details)

## Consequences

### MCP Tool Retention

`claudevn_get_assignment` is **retained** as a valid MCP tool with the following behavior:

- **Input**: `task_id` (required when responding to notification)
- **Behavior**: Returns full assignment details for the specified task
- **Usage**: Called by Compute after receiving `work_assigned` SSE event

### SSE Event Changes

The `work_assigned` SSE event should be lightweight:

```json
event: work_assigned
data: {
  "task_id": "task-456",
  "title": "Brief title for logging",
  "priority": "normal"
}
```

Full details (skills, context, branch, etc.) are fetched via MCP.

### Documentation Updates Required

1. **mcp-tools.md**: Remove `claudevn_get_assignment` from "Tools NOT Available" section; document its purpose in notification + fetch pattern
2. **v1.0-architecture.md**: Clarify that work assignment uses notification + fetch
3. **compute-registration.md**: Update `work_assigned` event to show lightweight payload

### Skill Fetching

`claudevn_get_skill` is **removed** per original spec - skills are composed and included in the assignment response from `claudevn_get_assignment`. Compute does not fetch skills individually.

## Alternatives Considered

### Full Push via SSE
Rejected - SSE payloads become large and tightly coupled.

### Polling-Based Pull
Rejected - Inefficient and no real-time awareness.

### WebSocket Bidirectional
Rejected - Adds complexity; SSE + MCP already provides bidirectional communication.

## References

- Issue: #190
- Resolves documentation inconsistency between mcp-tools.md and v1.0-architecture.md
