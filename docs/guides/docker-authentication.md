# Docker Authentication Guide

**Version**: 1.1.0
**Last Updated**: February 2026
**Audience**: Platform Administrators, VCN Node Operators

---

## Overview

ClaudeVN uses **serving-centric authentication**: the Serving container owns and manages Claude OAuth credentials. Compute instances fetch credentials from Serving via HTTP rather than mounting host files.

This guide covers:

- How the serving-centric auth flow works
- First-time setup via the browser UI
- Re-authentication when credentials expire
- CLI re-auth for headless environments
- External VCN nodes joining with their own credentials
- Security architecture and best practices

**Key Principle**: Serving manages the Claude OAuth lifecycle. Compute instances authenticate to Serving (via API key) and fetch credentials on demand. No host volume mounts for `~/.claude` are needed.

---

## Authentication Architecture

### Serving-Centric Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                        Docker Environment                         │
│                                                                    │
│  ┌────────────────────────────────────────────┐                   │
│  │              Serving Container              │                   │
│  │                                             │                   │
│  │  ClaudeAuthService                          │                   │
│  │  ├── runs `claude login` headless           │                   │
│  │  ├── stores credentials on persistent vol   │                   │
│  │  ├── serves /auth/status, /auth/login       │                   │
│  │  ├── serves /auth/credentials (authed)      │                   │
│  │  └── broadcasts SSE on credential update    │                   │
│  │                                             │                   │
│  │  Persistent Volume:                         │                   │
│  │  /app/data/serving/claude-credentials/      │                   │
│  │  └── .credentials.json                      │                   │
│  └──────────────┬──────────────────────────────┘                   │
│                 │                                                    │
│       HTTP /auth/credentials                                        │
│       (requires compute API key)                                    │
│                 │                                                    │
│    ┌────────────┼────────────┐                                     │
│    ▼            ▼            ▼                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
│  │Compute-1 │ │Compute-2 │ │Compute-3 │                           │
│  │          │ │          │ │          │                           │
│  │entrypoint│ │entrypoint│ │entrypoint│                           │
│  │fetches → │ │fetches → │ │fetches → │                           │
│  │~/.claude │ │~/.claude │ │~/.claude │                           │
│  └──────────┘ └──────────┘ └──────────┘                           │
│                                                                    │
│  Frontend UI (port 8002)                                           │
│  └── AuthSetupPage → OAuth URL → browser → credentials saved      │
└──────────────────────────────────────────────────────────────────┘

                              ↓ HTTPS

                    ┌──────────────────┐
                    │  Anthropic API   │
                    │  (Claude OAuth)  │
                    └──────────────────┘
```

### How It Works

1. **First launch**: Serving starts with no credentials. The frontend shows the AuthSetupPage.
2. **User clicks "Login"**: Frontend calls `POST /auth/login`. Serving runs `claude login` headless and returns an OAuth URL.
3. **User completes OAuth**: Opens the URL in a browser and authenticates with Anthropic. Serving captures the credentials.
4. **Credentials stored**: Saved to Serving's persistent volume at `/app/data/serving/claude-credentials/.credentials.json`.
5. **Compute fetches**: Each compute container's `entrypoint.sh` calls `GET /auth/credentials` (with API key auth) to get credentials.
6. **SSE refresh**: When credentials change, Serving broadcasts an `auth_credentials_updated` SSE event. Compute containers re-fetch automatically.

### Authentication Modes

ClaudeVN supports three authentication modes for compute instances:

| Mode | Description | Use Case |
|------|-------------|----------|
| **serving** | Fetches credentials from Serving's `/auth/credentials` endpoint | Default for Docker deployments |
| **local** | Copies from host-mounted `/host-claude` staging directory | Legacy/testing |
| **external** | Credentials pre-provisioned or managed externally | VCN nodes with own subscriptions |

Set via `COMPUTE_AUTH_MODE` environment variable in `docker-compose.yml`.

---

## Quick Start

### Prerequisites

1. **Docker Desktop** running
2. **No Claude CLI required on host** (Serving handles auth internally)

### Step 1: Start Services

```bash
cd /path/to/claudevn
docker compose up -d
```

### Step 2: Authenticate via Browser

1. Open `http://localhost:8002` in your browser
2. The **AuthSetupPage** appears with a "Login with Claude" button
3. Click the button — an OAuth URL is generated
4. Copy the URL and open it in your browser (or click the link)
5. Complete the Anthropic OAuth flow
6. The frontend automatically detects authentication and loads the main app

### Step 3: Verify

```bash
# Check serving logs for successful auth
docker compose logs serving | grep -i auth

# Check compute logs for credential fetch
docker compose logs compute-1 | grep entrypoint

# Verify via API
curl http://localhost:8002/api/v1/auth/status
```

Expected status response when authenticated:

```json
{
  "status": "authenticated",
  "authenticated": true,
  "expires_at": "2026-05-15T12:00:00Z"
}
```

---

## Re-Authentication

OAuth tokens expire periodically. ClaudeVN provides two re-auth methods.

### Method 1: In-App Re-Auth (Recommended)

When credentials expire, the frontend detects the change via polling (every 60 seconds) and shows an **AuthExpiredBanner** at the top of the app. The banner provides a "Re-authenticate" button.

1. Click "Re-authenticate" in the banner
2. A new OAuth URL is generated
3. Complete the OAuth flow in your browser
4. The banner disappears and compute instances refresh credentials automatically via SSE

The app remains usable during re-auth — the expired banner is non-blocking.

### Method 2: CLI Re-Auth (Headless/SSH)

For servers without browser access, use the re-auth script directly in the Serving container:

```bash
docker exec -it claudevn-serving /app/scripts/claude-reauth.sh
```

This runs `claude login` headless inside the container. It prints an OAuth URL to your terminal — copy it and open in any browser to complete the flow.

**Script location**: `serving/scripts/claude-reauth.sh`

### OAuth Flow Timeout

Login flows automatically timeout after **10 minutes** (600 seconds). If the OAuth flow is not completed within this window, it is cancelled and the status resets to `not_configured`. The user can start a new login attempt.

This prevents orphaned login flows from accumulating.

---

## Credential Lifecycle

### Polling and Expiration Detection

| State | Frontend Poll Interval | Behavior |
|-------|----------------------|----------|
| Not authenticated | 3 seconds | Fast polling for login detection |
| Authenticated | 60 seconds | Slow polling for expiration check |
| Expired | 3 seconds | Fast polling for re-auth detection |
| Error (server unreachable) | 3 seconds | Retries with error displayed |

### Compute Credential Refresh

Compute containers get credentials in two ways:

1. **At startup**: `entrypoint.sh` fetches from `GET /auth/credentials` with retry logic (up to 30 attempts, 5s between retries)
2. **Runtime refresh**: SSE event `auth_credentials_updated` triggers a re-fetch

The `/auth/credentials` endpoint requires compute authentication (`X-Compute-ID` header + `Authorization: Bearer` token).

---

## External VCN Nodes

External compute nodes run on different hosts. They can either fetch credentials from a remote Serving instance or bring their own.

### Option A: Fetch from Remote Serving

```yaml
# docker-compose.override.yml on external host
services:
  compute-external:
    build:
      context: .
      dockerfile: compute/Dockerfile
    container_name: claudevn-compute-external
    environment:
      - COMPUTE_INSTANCE_ID=compute-ext-001
      - COMPUTE_INSTANCE_NAME=Compute-External
      - SERVING_URL=http://<serving-host>:8002
      - COMPUTE_AUTH_MODE=serving
      - CLAUDEVN_SERVING_AUTH_URL=http://<serving-host>:8002/api/v1/auth
      - COMPUTE_SKILLS=code-writer
      - COMPUTE_CAPABILITIES=python
```

### Option B: Own Credentials (External Mode)

For nodes with their own Claude subscriptions:

```yaml
services:
  compute-external:
    build:
      context: .
      dockerfile: compute/Dockerfile
    environment:
      - COMPUTE_AUTH_MODE=external
      # Credentials pre-provisioned in image or volume
    volumes:
      - ~/.claude:/host-claude:ro  # Mount own credentials
```

### Network Connectivity

External nodes must reach the Serving component. Options:

- **LAN/VPN**: Direct network access (simplest)
- **Tailscale/WireGuard**: Private overlay network
- **Public endpoint with TLS**: Reverse proxy (nginx/Caddy) in front of Serving
- **Docker Swarm**: Overlay network for multi-host Docker deployments

---

## Security Considerations

### Credential Protection

**DO:**
- Use the serving-centric model (credentials stay in one container)
- Require compute API key authentication for credential fetches
- Use Docker named volumes for credential persistence
- Rotate credentials periodically via the re-auth flow
- Use separate subscriptions for production vs development

**DON'T:**
- Expose the Serving port (8002) to the public internet without TLS and auth
- Commit credential files to version control
- Use writable host mounts for credentials
- Log credential contents

### Network Security

For production deployments:

1. **Use TLS**: Encrypt traffic between Serving and compute (especially external nodes)
2. **Compute API keys**: Each registered compute instance authenticates with a unique API key
3. **Firewall rules**: Restrict Serving access to known compute IPs
4. **VPN**: Use Tailscale/WireGuard for private networks
5. **Docker bridge isolation**: Local compute containers communicate via Docker's internal bridge network

### Compute Authentication

The `/auth/credentials` endpoint requires:

- `X-Compute-ID` header with the registered compute instance ID
- `Authorization: Bearer <api-key>` header with the compute's API key

Requests without valid credentials are rejected with 401/403.

---

## Troubleshooting

### AuthSetupPage Shows on Every Restart

**Cause**: Serving's credential volume is not persistent.

**Fix**: Ensure `serving_data` volume is a named volume (not anonymous):
```yaml
volumes:
  serving_data:
    driver: local
```

### Compute Can't Fetch Credentials

**Symptom**: Entrypoint logs show "credentials not ready" after 30 attempts.

```bash
# Check serving auth status
curl http://localhost:8002/api/v1/auth/status

# If not authenticated, complete OAuth via browser
# Then restart the compute container
docker compose restart compute-1
```

### "Cannot connect to server" in Frontend

**Symptom**: Error page shown instead of AuthSetupPage.

**Cause**: Serving is down or unreachable.

```bash
# Check serving container health
docker compose ps serving
docker compose logs serving

# Restart if needed
docker compose restart serving
```

### OAuth URL Expired

**Symptom**: Login flow starts but OAuth URL returns an error.

**Cause**: Login flow timed out (10-minute limit).

**Fix**: Click "Login" again to generate a fresh OAuth URL.

### External Node Can't Reach Serving

```bash
# Test network connectivity
curl http://<serving-host>:8002/api/v1/health

# Check firewall rules on Serving host
sudo ufw status
sudo ufw allow 8002/tcp

# Verify SERVING_URL in compute environment
docker compose exec compute-external env | grep SERVING
```

---

## Environment Variables

### Serving

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_CREDENTIALS_PATH` | `{STORAGE_PATH}/claude-credentials` | Path to store OAuth credentials |

### Compute

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPUTE_AUTH_MODE` | `serving` | Auth mode: `serving`, `local`, or `external` |
| `CLAUDEVN_SERVING_AUTH_URL` | `http://serving:8002/api/v1/auth` | Serving auth endpoint URL |
| `SERVING_URL` | `http://serving:8002` | Serving base URL for registration |
| `COMPUTE_INSTANCE_ID` | (required) | Unique ID for this compute instance |

### Clearing Credentials

To reset auth state (e.g., for testing the login flow), use the demo data script:

```bash
./scripts/demo_data.sh --delete
```

Or call the logout endpoint directly:

```bash
curl -X POST http://localhost:8002/api/v1/auth/logout
```

---

## API Reference

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/auth/status` | GET | No | Current auth status and metadata |
| `/auth/login` | POST | No | Initiate OAuth login flow |
| `/auth/login/cancel` | POST | No | Cancel pending login flow |
| `/auth/credentials` | GET | Compute API key | Fetch credentials for compute instances |

### Status Values

| Status | `authenticated` | Meaning |
|--------|-----------------|---------|
| `not_configured` | `false` | No credentials, login needed |
| `login_pending` | `false` | OAuth flow in progress |
| `authenticated` | `true` | Valid credentials available |
| `expired` | `false` | Credentials expired, re-auth needed |
| `disabled` | `true` | Auth feature disabled (404 → bypass) |

---

## Related Documents

- [v1.0 Architecture](../design/architecture/v1.0-architecture.md)
- [Git Worktree Workflow](worktree-workflow.md)
- [MCP Tools Specification](../design/specifications/mcp-tools.md)
- [Compute Spawner Design](../design/specifications/compute-spawner.md)
