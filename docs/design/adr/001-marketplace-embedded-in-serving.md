# ADR-001: Embed Marketplace in Serving Component

## Status
Superseded by ADR-002

## Date
2026-01-29

## Context

The marketplace component manages skills (CLAUDE.md templates) for compute instances. In v0.x, marketplace ran as a separate microservice on port 8003. The v1.0 architecture specification calls for marketplace to be embedded within the Serving component.

### Current State
- Marketplace runs as standalone service on port 8003
- Serving communicates with marketplace via HTTP client
- Embedded code exists in `/serving/marketplace/` but is not integrated
- Two separate processes to manage and deploy

### v1.0 Architecture Specification
From `docs/design/architecture/v1.0-architecture.md`:
> "Persona Marketplace: Registry of available personas (CLAUDE.md templates) for different roles"

The architecture diagram shows Persona Marketplace as a component within Serving, not a separate service.

## Decision

**Embed the marketplace component within Serving.**

The marketplace will be integrated as an internal module of Serving rather than running as a separate microservice. All skill-related endpoints will be served from port 8002 under `/api/v1/skills`.

## Rationale

### Advantages of Embedding
1. **Simpler deployment**: Single process, single port (8002)
2. **Lower latency**: No HTTP roundtrip for skill operations
3. **Easier configuration**: No cross-service authentication needed
4. **Reduced complexity**: One service to monitor and maintain
5. **Alignment with spec**: Implements v1.0 architecture as designed

### Disadvantages Considered
1. **Cannot scale independently**: Marketplace scales with Serving
2. **Coupled updates**: Skill updates require Serving restart
3. **Larger process**: More code in one service

These disadvantages are acceptable because:
- ClaudeVN is designed for single-instance deployment
- Skills rarely change at runtime
- The additional code is minimal (~30KB)

## Consequences

### Changes Required
1. Register embedded marketplace router in `serving/app.py`
2. Initialize skill registry at Serving startup
3. Remove marketplace HTTP client initialization
4. Update health check to use embedded registry
5. Archive standalone marketplace directory

### API Changes
- Skills endpoints move from `localhost:8003/api/v1/skills` to `localhost:8002/api/v1/skills`
- No changes to endpoint paths or payloads
- Backward compatible for API consumers (same routes, different port)

### Migration Path
1. Update any clients using port 8003 to use port 8002
2. Remove `MARKETPLACE_URL` environment variable
3. Remove standalone marketplace from deployment

## Alternatives Considered

### Keep as Microservice
Rejected because it contradicts the v1.0 architecture specification and adds unnecessary operational complexity for ClaudeVN's deployment model.

### Hybrid Approach (support both)
Rejected because maintaining two integration paths increases complexity without clear benefit.

## References
- Issue: #81
- v1.0 Architecture: `docs/design/architecture/v1.0-architecture.md`
- Persona Marketplace Spec: `docs/design/specifications/persona-marketplace.md`
