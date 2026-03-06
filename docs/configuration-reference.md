# Configuration Reference

This document provides a comprehensive reference for all configuration settings in ClaudeVN v1.0. All components are configured via environment variables.

## Table of Contents

- [Serving Component](#serving-component)
- [Compute Component](#compute-component)
- [Marketplace Component](#marketplace-component)
- [Docker Compose Examples](#docker-compose-examples)
- [Common Configuration Patterns](#common-configuration-patterns)

---

## Serving Component

The Serving component is the central coordination hub. Configuration is loaded via `serving/config.py` using `ServingConfig.from_env()`.

### Server Settings

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SERVING_HOST` | `0.0.0.0` | string | Server bind host |
| `SERVING_PORT` | `8002` | int | Server bind port |
| `API_VERSION` | `v1` | string | API version prefix for routes |
| `LOG_LEVEL` | `INFO` | string | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CORS_ORIGINS` | `*` | string | CORS allowed origins (comma-separated or `*`) |

### Storage Settings

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `STORAGE_PATH` | `./data/serving` | string | Base storage path for all data |
| `CACHE_PATH` | `{STORAGE_PATH}/cache` | string | Cache directory (auto-derived if not set) |
| `DATASTORE_PATH` | `{STORAGE_PATH}/datastore` | string | Datastore directory (auto-derived if not set) |
| `CACHE_DEFAULT_TTL` | `300` | int | Default cache TTL in seconds |

### Health Monitoring

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `HEALTH_CHECK_INTERVAL` | `30` | int | Seconds between compute instance health checks |
| `DEGRADED_THRESHOLD` | `60` | int | Seconds without heartbeat before marking degraded |
| `OFFLINE_THRESHOLD` | `90` | int | Seconds without heartbeat before marking offline |
| `MAX_FAILED_CHECKS` | `3` | int | Consecutive failed checks before taking action |
| `AUTO_DEREGISTER` | `false` | bool | Auto-deregister failed instances (disabled by default) |

### Work Timeout

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `WORK_TIMEOUT_MINUTES` | `30` | int | Minutes before work item considered stuck |
| `WORK_TIMEOUT_CHECK_INTERVAL` | `60` | int | Seconds between stuck-work detection scans |
| `WORK_TIMEOUT_MAX_RETRIES` | `3` | int | Max retries before marking work item FAILED |
| `WORK_TIMEOUT_ENABLED` | `true` | bool | Enable stuck-work detection system |

### Session

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SESSION_PERSISTENCE` | `true` | bool | Enable session state persistence |
| `SESSION_TIMEOUT` | `3600` | int | Session timeout in seconds (1 hour) |

### Redis

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `REDIS_HOST` | `localhost` | string | Redis server host |
| `REDIS_PORT` | `6379` | int | Redis server port |
| `REDIS_DB` | `0` | int | Redis database number |
| `REDIS_PASSWORD` | (none) | string | Redis password (optional) |
| `REDIS_KEY_PREFIX` | `claudevn:` | string | Key prefix for all Redis keys |

### Git Infrastructure

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `GIT_REPOS_PATH` | `{STORAGE_PATH}/repos` | string | Path to bare Git repositories |
| `GIT_SSH_KEYS_PATH` | `{STORAGE_PATH}/ssh_keys` | string | SSH authorized keys directory |
| `GIT_USER` | `git` | string | Git user for SSH access |
| `GIT_ENABLE_SSH` | `true` | bool | Enable SSH-based Git access |
| `GIT_HOOK_REDIS_NOTIFY` | `true` | bool | Enable Redis notifications from Git hooks |
| `SSH_GIT_PORT` | `2222` | int | SSH server port for Git access |
| `SSH_HOST_KEY_PATH` | `{SSH_KEYS_PATH}/ssh_host_ed25519_key` | string | SSH host key path (auto-generated) |

### Marketplace Connection

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `MARKETPLACE_URL` | `http://localhost:8003` | string | Marketplace service URL |
| `MARKETPLACE_API_KEY` | (none) | string | API key for marketplace authentication |
| `MARKETPLACE_CACHE_TTL` | `300` | int | Cache TTL for skill data in seconds |
| `MARKETPLACE_FALLBACK_SKILLS` | `code-implementation,bug-investigation` | string | Fallback skills when marketplace unavailable |

### Rate Limiting

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `RATE_LIMIT_ENABLED` | `true` (auto-disabled in tests) | bool | Enable rate limiting middleware |
| `RATE_LIMIT_DEFAULT_RPM` | `60` | int | Default requests per minute |
| `RATE_LIMIT_COMPUTE_RPM` | `120` | int | Requests per minute for `/compute/*` endpoints |
| `RATE_LIMIT_WORK_RPM` | `60` | int | Requests per minute for `/work/*` endpoints |
| `RATE_LIMIT_PR_RPM` | `30` | int | Requests per minute for `/pr/*` endpoints |
| `RATE_LIMIT_BURST_MULTIPLIER` | `1.5` | float | Burst capacity multiplier above rate limit |

### Claude Authentication

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `CLAUDE_CREDENTIALS_PATH` | `{STORAGE_PATH}/claude-credentials` | string | Credentials storage path |

### Authentication (Cognito)

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `AUTH_MODE` | `bypass` | string | Auth mode: `bypass` (no login, dev user) or `cognito` (Cognito JWT required) |
| `COGNITO_USER_POOL_ID` | (none) | string | AWS Cognito User Pool ID (required when AUTH_MODE=cognito) |
| `COGNITO_APP_CLIENT_ID` | (none) | string | Cognito App Client ID (required when AUTH_MODE=cognito) |
| `COGNITO_REGION` | `us-east-1` | string | AWS region for Cognito User Pool |
| `COGNITO_ADMIN_ENABLED` | `false` | bool | Enable admin user management endpoints (invite, list, remove) |

### Compute Registration

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `COMPUTE_REGISTRATION_TOKEN` | (none) | string | Pre-shared token compute instances must present to register. Open registration if not set. |

### Network Capacity

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `MAX_COMPUTE_INSTANCES` | `0` | int | Maximum compute instances allowed (0 = unlimited) |

### Compute Spawner

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `WORKSPACES_PATH` | `/app/data/workspaces` | string | Workspace path for spawned compute instances |
| `SERVING_PUBLIC_URL` | `http://serving:8002` | string | URL compute instances use to reach Serving |

---

## Compute Component

Compute instances execute work using Claude Code CLI. Configuration is loaded via `compute/config.py` using `load_config()`.

**Note**: Supports both `CLAUDEVN_*` and `COMPUTE_*` prefixes for backwards compatibility.

### Server

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `COMPUTE_HOST` / `CLAUDEVN_HOST` | `0.0.0.0` | string | Bind host |
| `COMPUTE_PORT` / `CLAUDEVN_PORT` | `8003` | int | Bind port |

### Identity

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `COMPUTE_INSTANCE_ID` / `CLAUDEVN_COMPUTE_ID` | `compute-{hostname}-{port}` | string | Unique instance ID (auto-generated) |
| `COMPUTE_INSTANCE_NAME` / `CLAUDEVN_COMPUTE_NAME` | `Compute on {hostname}` | string | Human-readable instance name (auto-generated) |

### Connection

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SERVING_URL` / `CLAUDEVN_SERVING_URL` | `http://localhost:8002` | string | Serving component URL |
| `CLAUDEVN_API_KEY` | (none) | string | API key for Serving authentication |
| `COMPUTE_REGISTER_ON_STARTUP` | `true` | bool | Auto-register with Serving on startup |
| `COMPUTE_HEARTBEAT_INTERVAL` | `30` | int | Heartbeat interval in seconds |
| `COMPUTE_PUBLIC_URL` | (none) | string | Public URL for this compute instance |

### Capabilities

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `CLAUDEVN_CAPABILITIES` | `coding,testing,documentation` | string | Comma-separated capabilities |
| `COMPUTE_SKILLS` | (none) | string | Skill tags for work assignment matching |
| `CLAUDEVN_RESOURCES_CPU` | `4` | int | Advertised CPU cores available |
| `CLAUDEVN_RESOURCES_MEMORY` | `16gb` | string | Advertised memory available |

### Workspace

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `CLAUDEVN_WORKSPACE_PATH` / `WORKSPACE_PATH` | `./data/workspace` | string | Workspace directory for Claude Code instances |
| `CLAUDEVN_CLAUDE_CLI_PATH` | (auto-detected) | string | Path to claude CLI binary |

### Credentials

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `COMPUTE_AUTH_MODE` | `serving` | string | Auth mode: `serving`, `local`, or `external` |
| `CLAUDEVN_SERVING_AUTH_URL` | `http://serving:8002/api/v1/auth` | string | Serving auth API URL for credential fetching |
| `CLAUDEVN_CREDENTIALS_PATH` | `~/.claude/.credentials.json` | string | Claude OAuth credentials path (local mode) |
| `CLAUDEVN_CREDENTIAL_CHECK_INTERVAL` | `3600` | int | Seconds between credential health checks |
| `CLAUDEVN_CREDENTIAL_EXPIRY_WARNING_DAYS` | `7` | int | Days before expiry to emit warning |

**Auth Modes**:
- `serving`: Fetch credentials from Serving's `/api/v1/auth/credentials` endpoint
- `local`: Mount local credentials file into container
- `external`: Use compute's own OAuth credentials

### SSE Client

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `CLAUDEVN_SSE_RECONNECT_DELAY` | `5` | int | Initial SSE reconnect delay in seconds |
| `CLAUDEVN_SSE_MAX_RECONNECT_DELAY` | `60` | int | Maximum SSE reconnect delay in seconds |

### TLS

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `TLS_VERIFY` | `true` | bool | Verify TLS certificates when connecting to Serving over HTTPS. Set to `false` only for local development with self-signed certificates (e.g., Caddy on a `.local` domain). Affects entrypoint `curl` calls and all Python `httpx` clients (SSE, credential monitor, spawner). |

### Logging

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `LOG_LEVEL` | `INFO` | string | Log level (DEBUG, INFO, WARNING, ERROR) |
| `COMPUTE_LOG_FILE` | `./logs/compute.log` | string | Log file path |

---

## Marketplace Component

The Marketplace manages skill definitions and composition. Configuration is loaded via `marketplace/config.py` using `Config()`.

### Server

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `MARKETPLACE_HOST` | `0.0.0.0` | string | Bind host |
| `MARKETPLACE_PORT` | `8003` | int | Bind port |
| `API_VERSION` | `v1` | string | API version prefix |
| `LOG_LEVEL` | `INFO` | string | Logging level |
| `CORS_ORIGINS` | `*` | string | CORS origins (comma-separated or `*`) |

### Skills

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SKILLS_PATH` | `/app/skills` | string | Path to skill YAML definition files |

### Authentication

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `MARKETPLACE_REQUIRE_AUTH` | `false` | bool | Require authentication for API access |
| `MARKETPLACE_API_KEY` | (none) | string | Primary API key for authentication |
| `SERVING_API_KEY` | (none) | string | API key for Serving component |
| `ADMIN_API_KEY` | (none) | string | API key for admin operations |

### Serving Registration

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `SERVING_URL` | (none) | string | Serving URL (e.g., `http://serving:8002`) |
| `REGISTER_ON_STARTUP` | `true` | bool | Auto-register with Serving on startup |
| `HEARTBEAT_INTERVAL` | `60` | int | Heartbeat interval in seconds |
| `MARKETPLACE_NAME` | `ClaudeVN Marketplace` | string | Marketplace display name |
| `MARKETPLACE_ID` | `marketplace-{uuid}` | string | Unique marketplace ID (auto-generated) |

### Caching

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `AGENT_CACHE_MAX_SIZE` | `10000` | int | Maximum agent composition cache entries |
| `AGENT_CACHE_TTL` | `86400` | int | Agent cache TTL in seconds (24 hours) |

### Git-Backed Storage

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `GIT_STORAGE_ENABLED` | `true` | bool | Enable Git-backed skill storage |
| `GIT_REPOS_PATH` | `/var/lib/claudevn/marketplace/repos` | string | Git repositories path |
| `GIT_WORKTREE_PATH` | `/tmp/marketplace-worktree` | string | Git worktree path |

### Redis (Optional)

| Variable | Default | Type | Description |
|----------|---------|------|-------------|
| `REDIS_HOST` | `localhost` | string | Redis host for indexing |
| `REDIS_PORT` | `6379` | int | Redis port |
| `REDIS_DB` | `0` | int | Redis database number |
| `REDIS_KEY_PREFIX` | `claudevn:` | string | Redis key prefix |

---

## Compute Drain and Deregistration

Compute instances support a graceful drain lifecycle for safe removal or maintenance.

### Status Transitions

```
ONLINE → DRAINING → OFFLINE → (deregistered)
                        │
                        └──→ ONLINE  (when projects re-assigned with active SSE)
```

### Drain Behavior

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTO_DEREGISTER` | `false` | When set on Serving, automatically deregister instances that fail health checks |
| `auto_deregister` (drain param) | `false` | Per-drain option: auto-remove instance when drain completes |

**Drain** stops new work assignment while allowing in-flight work to complete. The health
monitor periodically checks draining instances and transitions them to OFFLINE once all
work completes. If `auto_deregister` was requested, the instance is removed from the
registry instead.

**Deregister** removes the instance from the registry and revokes its MCP API key. In the
UI, the deregister button is only enabled when the instance is in DRAINING or OFFLINE status.

**Recovery**: Assigning projects to an OFFLINE instance with an active SSE connection
transitions it back to ONLINE, allowing it to receive work again.

See the [Remote Compute Guide](guides/remote-compute.md#drain-and-deregister) for
operational procedures and API examples.

---

## Docker Compose Examples

### Development Environment

Minimal setup for local development:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  serving:
    build: ./serving
    ports:
      - "8002:8002"
      - "2222:2222"
    environment:
      - SERVING_HOST=0.0.0.0
      - SERVING_PORT=8002
      - LOG_LEVEL=DEBUG
      - REDIS_HOST=redis
      - RATE_LIMIT_ENABLED=false  # Disable for development
      - STORAGE_PATH=/app/data/serving
      - AUTH_MODE=bypass
    volumes:
      - ./data/serving:/app/data/serving
    depends_on:
      - redis

  marketplace:
    build: ./marketplace
    ports:
      - "8003:8003"
    environment:
      - MARKETPLACE_PORT=8003
      - SKILLS_PATH=/app/skills
      - MARKETPLACE_REQUIRE_AUTH=false
      - SERVING_URL=http://serving:8002
    volumes:
      - ./marketplace/skills:/app/skills

  compute:
    build: ./compute
    ports:
      - "8010:8010"
    environment:
      - COMPUTE_PORT=8010
      - SERVING_URL=http://serving:8002
      - COMPUTE_AUTH_MODE=serving
      - LOG_LEVEL=DEBUG
    depends_on:
      - serving
```

### Deployment Modes

ClaudeVN provides three Docker Compose files for different deployment scenarios:

| File | Purpose | Auth Mode |
|------|---------|-----------|
| `docker-compose.yml` | Full local stack (serving + marketplace + redis + computes) | bypass (default), cognito via `.env` |
| `docker-compose.serving.yml` | Remote serving hub (serving + marketplace + redis, no computes) | cognito (always) |
| `docker-compose.compute.yml` | Remote compute instance (connects to remote serving) | N/A (uses serving's auth) |

**Configuration templates:**
- `.env.serving.example` — Cognito + registration token for remote serving
- `.env.compute.example` — Serving URL + registration token for remote compute

For remote deployments, use `docker-compose.serving.yml` on the hub host and `docker-compose.compute.yml` on each compute host. See [Remote Compute Guide](guides/remote-compute.md) for step-by-step instructions.

### Multi-Compute Scaling

Scale compute instances with different specializations:

```yaml
services:
  # ... serving, redis, marketplace ...

  compute-coder:
    build: ./compute
    environment:
      - COMPUTE_INSTANCE_ID=compute-coder-001
      - COMPUTE_INSTANCE_NAME=Compute-CodeWriter
      - COMPUTE_SKILLS=code-writer,refactorer
      - COMPUTE_CAPABILITIES=python,javascript,typescript
      - SERVING_URL=http://serving:8002
    deploy:
      replicas: 2

  compute-debugger:
    build: ./compute
    environment:
      - COMPUTE_INSTANCE_ID=compute-debugger-001
      - COMPUTE_INSTANCE_NAME=Compute-Debugger
      - COMPUTE_SKILLS=debugger,security-reviewer
      - COMPUTE_CAPABILITIES=debugging,security,python
      - SERVING_URL=http://serving:8002
    deploy:
      replicas: 1

  compute-docs:
    build: ./compute
    environment:
      - COMPUTE_INSTANCE_ID=compute-docs-001
      - COMPUTE_INSTANCE_NAME=Compute-DocWriter
      - COMPUTE_SKILLS=doc-writer
      - COMPUTE_CAPABILITIES=documentation,markdown
      - SERVING_URL=http://serving:8002
    deploy:
      replicas: 1
```

---

## Common Configuration Patterns

### Pattern: External Compute Node

Join a remote Serving instance from an external host:

```bash
# .env file for external compute
SERVING_URL=https://serving.example.com:8002
COMPUTE_AUTH_MODE=serving
CLAUDEVN_SERVING_AUTH_URL=https://serving.example.com:8002/api/v1/auth
COMPUTE_INSTANCE_ID=compute-external-aws-001
COMPUTE_SKILLS=code-writer,test-automator
COMPUTE_PUBLIC_URL=https://compute-external.example.com:8010
```

### Pattern: Credential Management Modes

**Serving-Centric (Recommended)**:
```yaml
# Serving owns credentials
serving:
  environment:
    - CLAUDE_CREDENTIALS_PATH=/app/data/claude-credentials

compute:
  environment:
    - COMPUTE_AUTH_MODE=serving
    - CLAUDEVN_SERVING_AUTH_URL=http://serving:8002/api/v1/auth
```

**Local Mount**:
```yaml
compute:
  environment:
    - COMPUTE_AUTH_MODE=local
    - CLAUDEVN_CREDENTIALS_PATH=/app/.claude/.credentials.json
  volumes:
    - ~/.claude/.credentials.json:/app/.claude/.credentials.json:ro
```

**External (Own Credentials)**:
```yaml
compute:
  environment:
    - COMPUTE_AUTH_MODE=external
    - CLAUDEVN_CREDENTIALS_PATH=/app/data/credentials/.credentials.json
  volumes:
    - ./credentials:/app/data/credentials
```

### Pattern: High-Availability Setup

```yaml
services:
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    deploy:
      replicas: 1
      restart_policy:
        condition: any

  serving:
    build: ./serving
    environment:
      - AUTO_DEREGISTER=true
      - HEALTH_CHECK_INTERVAL=15
      - DEGRADED_THRESHOLD=30
      - OFFLINE_THRESHOLD=60
      - MAX_FAILED_CHECKS=3
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: any

  compute:
    build: ./compute
    environment:
      - COMPUTE_HEARTBEAT_INTERVAL=15
    deploy:
      replicas: 5
      restart_policy:
        condition: any
```

### Pattern: Resource Constraints

Limit container resources:

```yaml
services:
  compute:
    build: ./compute
    environment:
      - CLAUDEVN_RESOURCES_CPU=2
      - CLAUDEVN_RESOURCES_MEMORY=8gb
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 8G
        reservations:
          cpus: '1'
          memory: 4G
```

### Pattern: Environment-Specific Overrides

Use docker-compose.override.yml for local development:

```yaml
# docker-compose.override.yml (local dev)
services:
  serving:
    environment:
      - LOG_LEVEL=DEBUG
      - RATE_LIMIT_ENABLED=false
    volumes:
      - ./serving:/app/serving:ro  # Mount source for hot reload

  compute:
    environment:
      - LOG_LEVEL=DEBUG
```

---

## Configuration Validation

### Serving Health Check

```bash
curl http://localhost:8002/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "redis": "connected",
    "marketplace": "connected"
  }
}
```

### Compute Registration Check

```bash
curl http://localhost:8002/api/v1/compute/instances
```

Verify your compute instances appear in the list.

### Marketplace Skills Check

```bash
curl http://localhost:8003/api/v1/skills
```

Should return available skills.

---

## Troubleshooting

### Common Issues

**Compute won't register**:
- Check `SERVING_URL` is correct and reachable
- Verify Redis is running and connected
- Check logs: `docker logs claudevn-compute-1`

**Rate limiting errors**:
- Set `RATE_LIMIT_ENABLED=false` for development
- Adjust `*_RPM` variables for production

**Auth failures**:
- Verify `COMPUTE_AUTH_MODE` matches credential setup
- Check credential file exists at `CLAUDE_CREDENTIALS_PATH`
- Test auth endpoint: `curl http://serving:8002/api/v1/auth/status`

**Git SSH errors**:
- Verify `SSH_GIT_PORT=2222` is exposed
- Check SSH keys generated: `ls -la /app/data/ssh_keys/`
- Test SSH: `ssh -p 2222 git@localhost`

**TLS/Certificate errors** (remote compute):
- `CERTIFICATE_VERIFY_FAILED`: Set `TLS_VERIFY=false` in `.env.compute` (local dev only)
- `tlsv1 alert internal error`: Using IP address instead of hostname. Caddy issues certs per domain — use the domain name in `CLAUDEVN_SERVING_URL`
- Container can't resolve hostname: Add `extra_hosts` in `docker-compose.compute.yml`

**Drain issues**:
- Instance stuck in DRAINING: Check for in-flight work via `GET /api/v1/compute/<id>/drain`
- Auto-deregister not working: Verify `auto_deregister: true` was passed in the drain request
- OFFLINE after drain, won't come back: Assign projects to the instance via the UI — it transitions back to ONLINE if SSE is connected

---

## Related Documentation

- [Architecture Overview](design/architecture/v1.0-architecture.md)
- [Git Infrastructure](design/specifications/git-infrastructure.md)
- [Distributed Deployment Guide](guides/distributed-deployment.md)
