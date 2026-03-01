# Compute Registration Audit

**Date:** 2026-02-28
**Type:** Standard Functional Audit
**Feature:** Compute module registration, deregistration, and distributed deployment
**Result:** Fail (critical gaps for target architecture)

## Executive Summary

The compute registration system is well-designed for same-host and Docker-network deployments. The SSE-based architecture correctly avoids inbound connections to Compute (all traffic is outbound from Compute to Serving), making it NAT-friendly in principle. However, **the system is not production-ready for cross-internet deployment** due to missing TLS, unauthenticated SSE registration, and internal Docker hostname leakage in URLs.

Register/unregister cycles are mostly clean, with proper state cleanup in both the SSE connection manager and registry. The main gap is MCP API key persistence after deregistration (24-hour stale window) and a 60+ second reconnect dead zone during network interruptions.

## Focus Area 1: Cross-Internet Registration from Disparate Networks

### Current State
- SSE connection is **outbound-only** from Compute to Serving — NAT-friendly
- MCP tool calls are **outbound HTTP** from Compute (Claude Code) to Serving
- Git operations use **Smart HTTP** (outbound from Compute to Serving `/git/` endpoint)
- SSE keepalive sent every 30 seconds; Compute uses exponential backoff (5s → 60s)
- `X-Accel-Buffering: no` header set for nginx compatibility
- `SERVING_PUBLIC_URL` configurable but defaults to Docker-internal hostname

### Gaps Found

| ID | Gap | Impact |
|----|-----|--------|
| GAP-1.1 | No TLS/HTTPS — all traffic (API keys, Git tokens, code) in plaintext | **Critical** |
| GAP-1.2 | `SERVING_PUBLIC_URL` defaults to `http://serving:8002` (unreachable externally) | High |
| GAP-1.3 | 30s keepalive may be insufficient for aggressive NAT timeouts (30-60s) | Medium |
| GAP-1.4 | SSE not documented for proxy compatibility (AWS ALB, Cloudflare, etc.) | Medium |
| GAP-1.5 | No deployment documentation for distributed network topology | High |

## Focus Area 2: Register/Unregister Cycles with Long-Running Serving

### Current State
- `register_connection` handles re-registration by calling `unregister_connection` first
- `finally` block in SSE generator cleans up registry and SSE manager state
- Event queues properly garbage-collected when SSE connection drops
- Same `compute_id` can re-register after deregistration
- Asyncio task lifecycle correctly managed (generator + keepalive task)

### Gaps Found

| ID | Gap | Impact |
|----|-----|--------|
| GAP-2.1 | MCP API keys not revoked on deregistration (24h stale window) | Medium |
| GAP-2.2 | 409 Conflict window during reconnect — up to 60+ seconds of lockout | Medium |
| GAP-2.3 | Registry health status can diverge from SSE connection state | Medium |
| GAP-2.4 | `_round_robin_indices` dict grows unboundedly (minor memory concern) | Low |

## Focus Area 3: Cloud Serving + Distributed Compute Architecture

### Current State
- `CLAUDEVN_SERVING_URL` properly configurable via env var
- Marketplace called only by Serving (not by Compute) — architecturally clean
- Work assignment entirely via SSE push — no inbound requirement to Compute
- Three auth modes supported: `serving`, `local`, `external`
- `auth_status` field prevents unauthorized instances from receiving work

### Gaps Found

| ID | Gap | Impact |
|----|-----|--------|
| GAP-3.1 | SSE registration endpoint has no authentication enforcement | **Critical** |
| GAP-3.2 | No TLS enforcement (same as GAP-1.1, architectural impact) | **Critical** |
| GAP-3.3 | `serving_auth_url` defaults to internal Docker hostname | High |
| GAP-3.4 | Git clone URLs in work assignments may contain internal hostnames | High |
| GAP-3.5 | No distributed deployment guide exists | High |
| GAP-3.6 | Compute container ports exposed without clear purpose in SSE model | Low |

## Priority Summary

| Priority | Count | Issues |
|----------|-------|--------|
| P0 | 2 | TLS, SSE auth |
| P1 | 5 | Key revocation, URL validation (x2), reconnect, deployment guide |
| P2 | 4 | Keepalive tuning, state reconciliation, proxy docs, cleanup |

## Positive Findings

- **NAT-friendly by design:** All communication is outbound from Compute
- **Clean state management:** SSE disconnect properly cleans up queues and registry
- **Marketplace isolation:** Compute never talks directly to Marketplace
- **Re-registration works:** Same compute_id can deregister and re-register cleanly
- **Auth gating exists:** `auth_status=AUTHORIZED` filter prevents unauthorized work assignment

## Issues Created

See GitHub issues with label `feature:compute-registration`.

## Files Examined

- `serving/api/compute.py` — SSE connect, event handling, deregister endpoints
- `serving/services/sse_connection_manager.py` — Connection lifecycle, keepalive, event queues
- `serving/services/registry_service.py` — Instance registry, health checks, capability index
- `serving/mcp/auth.py` — MCP authentication, API key management
- `serving/app.py` — Application startup, URL configuration
- `serving/git/http_backend.py` — Git Smart HTTP backend
- `compute/config.py` — Compute configuration, defaults
- `compute/services/sse_event_client.py` — SSE client, reconnect logic
- `docker-compose.yml` — Service definitions, environment variables
