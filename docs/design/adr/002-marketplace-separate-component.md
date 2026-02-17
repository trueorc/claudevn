# ADR-002: Extract Marketplace as Separate Component

## Status
Accepted (Supersedes ADR-001)

## Date
2026-01-29

## Context

ADR-001 decided to embed the marketplace within Serving for simplified deployment. However, operational requirements have changed:

### Problems with Embedded Approach
1. **Coupling**: Skill updates require Serving restart
2. **Scalability**: Cannot scale marketplace independently
3. **Testing**: Harder to test marketplace in isolation
4. **Deployment flexibility**: Cannot deploy marketplace separately

### Current State (after ADR-001)
- Marketplace code embedded in `/serving/marketplace/`
- Direct Python imports between serving and marketplace
- Single process, single port (8002)

### Architectural Goal
The v1.0 architecture should support flexible deployment models where components can be deployed together or separately based on operational needs.

## Decision

**Extract Marketplace as a separate component from Serving.**

The marketplace will run as an independent service that Serving communicates with via HTTP API. This reverses ADR-001.

## Rationale

### Advantages of Separation
1. **Independent scaling**: Marketplace can scale based on skill lookup load
2. **Independent deployment**: Update skills without restarting Serving
3. **Clear API boundaries**: HTTP API provides clean contract
4. **Better testability**: Can test marketplace in isolation
5. **Flexibility**: Deploy together (single host) or separately (multi-host)

### Acceptable Trade-offs
1. **Network latency**: HTTP calls add ~1-5ms latency (acceptable for skill lookups)
2. **Additional process**: One more service to monitor (mitigated by health checks)
3. **Configuration**: Need `MARKETPLACE_URL` env var (already exists in docker-compose)

## Consequences

### Changes Required
1. Remove embedded marketplace from Serving (`serving/marketplace/`)
2. Use `MarketplaceClient` HTTP client for all skill operations
3. Update health check to query marketplace via HTTP
4. Remove marketplace router from Serving app

### API Changes
- Skills endpoints remain at `http://marketplace:8003/api/v1/skills` (no change from docker-compose perspective)
- Serving no longer exposes `/api/v1/skills/*` endpoints directly

### Configuration
```yaml
# docker-compose.yml (already configured)
marketplace:
  ports: "8003:8003"

serving:
  environment:
    - MARKETPLACE_URL=http://marketplace:8003
```

### Graceful Degradation
- `MarketplaceClient` includes fallback personas when marketplace unavailable
- Serving continues operating in degraded mode if marketplace is down

## Migration Path
1. Serving already has `MarketplaceClient` - just need to use it
2. Docker-compose already has marketplace as separate service
3. Remove embedded marketplace code from Serving
4. Update documentation

## Alternatives Considered

### Keep Embedded (ADR-001)
Rejected because operational flexibility is more valuable than deployment simplicity for this project.

### Dual Support (both modes)
Rejected because maintaining two integration paths adds complexity without clear benefit.

## References
- Issue: #92
- Supersedes: ADR-001
- v1.0 Architecture: `docs/design/architecture/v1.0-architecture.md`
