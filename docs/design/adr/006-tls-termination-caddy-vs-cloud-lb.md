# ADR-006: TLS Termination — Caddy vs Cloud Load Balancer

## Status
Proposed

## Date
2026-03-01

## Context

Issue #79 introduced Caddy as a reverse proxy for automatic TLS certificate provisioning via Let's Encrypt. This works well for single-VM deployments but raises questions about production readiness at scale.

ClaudeVN Serving uses Server-Sent Events (SSE) for real-time communication with Compute instances. SSE connections are long-lived HTTP streams, which imposes constraints on any proxy or load balancer in the path.

### Current Architecture (Caddy)

```
Internet → Caddy (:443, auto-TLS) → Serving (:8002, plain HTTP)
```

Caddy runs as a sidecar container alongside Serving in a single Docker Compose stack.

### Alternative: Cloud Load Balancer

```
Internet → Cloud LB (:443, managed TLS) → Serving VM(s) (:8002)
```

A managed cloud load balancer (AWS ALB/NLB, GCP LB, Azure AG) handles TLS termination.

## Evaluation

### Caddy

| Aspect | Assessment |
|--------|------------|
| **TLS management** | Automatic via Let's Encrypt ACME HTTP-01. Zero-touch cert provisioning and renewal. |
| **SSE compatibility** | Excellent. Native HTTP streaming support, no idle timeout issues. Flush-on-write by default. |
| **Deployment complexity** | Low. Single container, single config file (`Caddyfile`). |
| **High availability** | None built-in. Single container = single point of failure. |
| **Horizontal scaling** | Not applicable. Caddy proxies to one upstream; no multi-backend routing. |
| **Health checks** | None built-in at the proxy layer (Docker healthcheck is separate). |
| **Cost** | Free (open source). Only VM compute cost. |
| **Operational overhead** | Minimal. No cloud console, no IAM policies, no separate billing. |

### Cloud Load Balancer (AWS ALB as reference)

| Aspect | Assessment |
|--------|------------|
| **TLS management** | Managed via AWS ACM. Free public certificates, auto-renewal. |
| **SSE compatibility** | Requires tuning. ALB default idle timeout is 60s — must increase to ≥300s for SSE. NLB (L4) avoids this entirely but loses L7 features. |
| **Deployment complexity** | Medium-High. Requires VPC config, security groups, target groups, listener rules, ACM cert, Route53 or DNS validation. |
| **High availability** | Built-in. Multi-AZ, managed failover. |
| **Horizontal scaling** | Native. Multiple targets, connection draining, weighted routing. |
| **Health checks** | Built-in. HTTP health checks with configurable thresholds. |
| **Cost** | ~$20-30/month base (ALB) + per-connection charges. SSE long connections may increase LCU cost. |
| **Operational overhead** | Medium. CloudFormation/Terraform templates, IAM roles, monitoring. |

### SSE-Specific Considerations

SSE connections are long-lived (minutes to hours). Key concerns:

1. **Idle timeout**: ALB defaults to 60s idle timeout. SSE keepalives at 15s intervals (#87) prevent disconnection, but this creates a dependency between keepalive interval and LB config.
2. **Connection limits**: ALB has a 100 concurrent connections per target default. With many compute instances, this could become a bottleneck.
3. **NLB alternative**: AWS NLB (Layer 4) has no idle timeout and handles long connections natively, but loses HTTP-level features (path routing, headers, access logs).
4. **Caddy advantage**: No idle timeout, no connection limits, no SSE-specific tuning needed.

## Decision

**Recommendation: Keep Caddy for current and near-term deployments. Defer cloud LB to when horizontal scaling of Serving is required.**

### Rationale

1. **Current scale**: ClaudeVN Serving runs on a single VM. A cloud LB adds cost and complexity with no benefit until multi-instance Serving is needed.
2. **SSE simplicity**: Caddy handles SSE natively with no tuning. Cloud LBs require careful timeout configuration and testing.
3. **Incremental migration**: When horizontal scaling is needed, Caddy can be replaced with a cloud LB without changing Serving code. The TLS termination layer is external to the application.
4. **Cost efficiency**: Caddy is free; ALB costs $20-30+/month even at minimal scale.

### When to Migrate to Cloud LB

Trigger conditions for reconsidering this decision:

- Serving needs to run on multiple VMs (horizontal scaling)
- Multi-AZ redundancy becomes a hard requirement
- Compute instance count exceeds single-VM connection capacity (~1000+ SSE connections)
- Organization standardizes on cloud-native infrastructure (Terraform/CloudFormation managed)

### Migration Path

When the time comes:

1. **AWS**: Use NLB (Layer 4) for SSE path + ALB for REST API paths, or a single ALB with increased idle timeout (≥300s)
2. **GCP**: Cloud Load Balancer with SSE-compatible backend service config (timeout ≥300s)
3. **Any cloud**: The Serving application requires no changes — TLS termination is fully external

## Consequences

### Positive
- No additional infrastructure cost or complexity for current deployment
- SSE works without tuning or special configuration
- Simple operational model (single `docker compose` stack)

### Negative
- Single point of failure (Caddy container crash = service outage)
- No automatic multi-AZ failover
- Manual intervention needed if VM goes down

### Mitigations
- Docker `restart: unless-stopped` policy ensures Caddy auto-restarts on crash
- VM-level monitoring and alerting for availability
- Documented runbook for VM recovery
- Compute instances reconnect automatically via SSE force-reconnect (#85)

## Related
- #79 — TLS implementation via Caddy
- #85 — SSE force-reconnect (handles proxy/LB interruptions)
- #87 — SSE keepalive interval (must be shorter than any LB idle timeout)
- `deploy/cloud/Caddyfile` — Current Caddy configuration
- `deploy/cloud/docker-compose.cloud.yml` — Cloud deployment overlay
