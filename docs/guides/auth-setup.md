# Authentication Setup Guide

**Version**: 1.0.0
**Last Updated**: February 2026
**Audience**: ClaudeVN Users, Platform Administrators

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Token Lifecycle](#token-lifecycle)
- [Managing Tokens](#managing-tokens)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

ClaudeVN uses **token-based authentication** for Claude API access. This system enables centralized credential management where the Serving component stores and distributes API tokens to compute instances.

### Key Benefits

- **Centralized management**: Store one token, distribute to all compute instances automatically
- **Simple setup**: Run `claude setup-token` once, paste the token into the UI
- **Automatic distribution**: New compute instances receive credentials automatically via SSE
- **Secure storage**: Tokens stored in Redis with encryption at rest
- **Long-lived tokens**: 365-day validity period reduces re-authentication frequency

### Authentication Flow

```
User Machine                ClaudeVN UI              Serving              Compute Instances
     │                           │                      │                         │
     │  1. claude setup-token    │                      │                         │
     ├──────────────────────────>│                      │                         │
     │                           │                      │                         │
     │  2. Token displayed       │                      │                         │
     │<──────────────────────────┤                      │                         │
     │                           │                      │                         │
     │  3. Paste into UI         │                      │                         │
     ├──────────────────────────>│                      │                         │
     │                           │                      │                         │
     │                           │  POST /auth/token    │                         │
     │                           ├─────────────────────>│                         │
     │                           │                      │                         │
     │                           │  Token stored        │                         │
     │                           │<─────────────────────┤                         │
     │                           │                      │                         │
     │                           │                      │  SSE: credentials_refresh
     │                           │                      ├────────────────────────>│
     │                           │                      │                         │
     │                           │                      │  GET /auth/credentials  │
     │                           │                      │<────────────────────────┤
     │                           │                      │                         │
     │                           │                      │  Token delivered        │
     │                           │                      ├────────────────────────>│
```

---

## How It Works

### User Perspective

1. **Generate Token**: Run `claude setup-token` on any machine with a browser
2. **Authenticate**: Complete the OAuth flow in your browser
3. **Copy Token**: Copy the generated token (starts with `sk-ant-oat01-`)
4. **Paste in UI**: Open the ClaudeVN UI and paste the token
5. **Done**: All compute instances receive the token automatically

### System Perspective

ClaudeVN's auth system has three components:

1. **Token Storage**: Serving stores tokens in Redis with metadata (component ID, expiry, status)
2. **Distribution**: Serving broadcasts credential updates via Server-Sent Events (SSE)
3. **Consumption**: Compute instances fetch credentials at startup and on refresh events

### Why Token-Based?

Previous versions used OAuth with `claude login`. This required:
- PTY (pseudo-terminal) for interactive login
- Browser access on the server
- Complex subprocess management

Token-based auth eliminates these requirements by separating token generation (user's machine) from token consumption (ClaudeVN platform).

---

## Quick Start

### Prerequisites

1. **Docker Desktop** running
2. **Claude CLI** installed on your local machine (for token generation)
   ```bash
   # Install Claude CLI if needed
   pip install claude-cli
   ```

### Step 1: Start ClaudeVN

```bash
cd /path/to/claudevn
docker compose up -d
```

### Step 2: Generate API Token

On your local machine (with browser access):

```bash
claude setup-token
```

This will:
1. Open your browser to Anthropic's OAuth page
2. Prompt you to authorize the CLI
3. Display a token starting with `sk-ant-oat01-`

**Important**: Copy the entire token immediately. It's only shown once.

### Step 3: Authenticate via UI

1. Open `http://localhost:8002` in your browser
2. The **AuthSetupPage** appears with a token input field
3. Paste your token (starts with `sk-ant-oat01-`)
4. Click **Submit**
5. The UI automatically transitions to the main application

### Step 4: Verify Authentication

Check that compute instances received credentials:

```bash
# Check serving logs for token storage
docker compose logs serving | grep -i "token stored"

# Check compute logs for credential fetch
docker compose logs compute-1 | grep -i "credentials fetched"

# Verify via API
curl http://localhost:8002/api/v1/auth/status
```

Expected response:

```json
{
  "status": "authenticated",
  "authenticated": true,
  "expires_at": "2027-02-14T12:00:00Z",
  "message": null
}
```

---

## Token Lifecycle

### Token Validity

| Property | Value |
|----------|-------|
| **Validity Period** | 365 days from creation |
| **Status States** | `active`, `expired`, `revoked` |
| **Renewal** | Manual (paste new token via UI) |
| **Auto-Distribution** | Yes (via SSE to all compute instances) |

### Status Monitoring

The frontend polls `/auth/status` to detect token expiration:

| State | Poll Interval | UI Behavior |
|-------|---------------|-------------|
| Not authenticated | 3 seconds | Shows AuthSetupPage |
| Authenticated | 60 seconds | Normal operation |
| Expired | 3 seconds | Shows expiration banner with re-auth prompt |

### Automatic Refresh

When a token is updated:

1. Serving broadcasts `credentials_refresh` SSE event
2. Compute instances receive the event
3. Compute instances call `GET /auth/credentials`
4. New token is written to `~/.claude/.credentials.json`
5. Claude Code picks up the new credentials automatically

**No restart required** for compute instances.

### Token Expiration

When a token expires (365 days after creation):

1. Serving's monitor detects expiration (runs every 60 seconds)
2. Token status changes to `expired` in Redis
3. Frontend shows **AuthExpiredBanner** with re-auth button
4. User pastes a new token to restore service

---

## Managing Tokens

### View Current Status

Via API:

```bash
curl http://localhost:8002/api/v1/auth/status
```

Via UI:
- Navigate to Settings → Authentication
- Shows current token status and expiration date

### Revoke Token

To immediately revoke the stored token:

```bash
curl -X POST http://localhost:8002/api/v1/auth/logout
```

This:
- Marks the token as `revoked` in Redis
- Removes it from storage
- Resets auth status to `not_configured`
- Does **not** revoke the token with Anthropic (still valid elsewhere)

### Update Token

To rotate tokens (e.g., for security):

1. Generate a new token: `claude setup-token`
2. Paste the new token in the UI
3. Old token is replaced immediately
4. All compute instances receive the new token via SSE

---

## API Reference

### GET /auth/status

Get current authentication status.

**Authentication**: None

**Response**:
```json
{
  "status": "authenticated",
  "authenticated": true,
  "expires_at": "2027-02-14T12:00:00Z",
  "message": null
}
```

**Status Values**:
| Status | `authenticated` | Description |
|--------|-----------------|-------------|
| `not_configured` | `false` | No token stored |
| `authenticated` | `true` | Valid token available |
| `expired` | `false` | Token expired, re-auth needed |
| `error` | `false` | System error (check `message`) |

---

### POST /auth/token

Submit an API token for storage.

**Authentication**: None (public endpoint for initial setup)

**Request Body**:
```json
{
  "token": "sk-ant-oat01-...",
  "component_id": "serving",
  "component_type": "serving"
}
```

**Validation**:
- Token must start with `sk-ant-oat01-`
- Token is stored with 365-day expiry

**Response**:
```json
{
  "status": "authenticated",
  "message": "Token stored successfully",
  "expires_at": "2027-02-14T12:00:00Z"
}
```

**Error Responses**:
- `400`: Invalid token format
- `503`: Auth service not enabled

---

### GET /auth/credentials

Get raw credentials for compute instances.

**Authentication**: Required (compute API key)

**Headers**:
```
X-Compute-ID: compute-001
Authorization: Bearer <compute-api-key>
```

**Response**:
```json
{
  "credentials": {
    "token": "sk-ant-oat01-..."
  },
  "expires_at": "2027-02-14T12:00:00Z"
}
```

**Error Responses**:
- `401`: Missing or invalid authentication
- `503`: No credentials available

---

### POST /auth/logout

Clear stored credentials and reset auth state.

**Authentication**: None (public endpoint)

**Response**:
```json
{
  "cleared": true,
  "message": "Credentials cleared"
}
```

---

## Troubleshooting

### Token Input Not Accepting Paste

**Symptom**: Cannot paste token into the UI input field.

**Cause**: Browser security settings blocking clipboard access.

**Fix**:
1. Type the token manually, or
2. Check browser console for security errors
3. Grant clipboard permissions if prompted

---

### "Token must start with 'sk-ant-oat01-'" Error

**Symptom**: Validation error when submitting token.

**Cause**: Incorrect token format or copied wrong text.

**Fix**:
1. Ensure you copied the entire token from `claude setup-token`
2. Token should start with `sk-ant-oat01-` (not `sk-ant-api01-`)
3. Remove any extra whitespace or newlines

---

### Compute Instances Not Receiving Credentials

**Symptom**: Compute logs show "credentials not ready" after many retries.

**Diagnosis**:
```bash
# Check serving auth status
curl http://localhost:8002/api/v1/auth/status

# Check compute logs
docker compose logs compute-1 | grep entrypoint
```

**Fix**:

If status shows `not_configured`:
1. Complete token setup via UI
2. Restart compute instances: `docker compose restart compute-1`

If status shows `authenticated` but compute can't fetch:
1. Check network connectivity between compute and serving
2. Verify compute auth headers are correct
3. Check serving logs for 401/403 errors

---

### Frontend Shows AuthSetupPage on Every Restart

**Symptom**: Token must be re-entered after restarting Docker.

**Cause**: Redis data not persisted.

**Fix**:

Ensure `redis_data` volume is persistent:
```yaml
# In docker-compose.yml
volumes:
  redis_data:
    driver: local
```

Check volume exists:
```bash
docker volume ls | grep redis_data
```

---

### Token Expired But No Notification

**Symptom**: Token expired but UI still shows authenticated.

**Cause**: Frontend polling disabled or failing.

**Fix**:
1. Refresh the browser page
2. Check browser console for API errors
3. Verify Serving is running: `docker compose ps serving`

---

### "Auth service not enabled" Error

**Symptom**: All `/auth/*` endpoints return 404 or 503.

**Cause**: ClaudeAuthService not initialized in Serving.

**Fix**:
1. Check Serving startup logs: `docker compose logs serving | grep -i auth`
2. Verify Redis is running: `docker compose ps redis`
3. Restart Serving: `docker compose restart serving`

---

## Related Documents

- [Docker Authentication Guide](docker-authentication.md) - Previous OAuth-based auth (legacy)
- [Remote Compute Setup](remote-compute.md) - Adding compute instances from other machines
- [v1.0 Architecture](../design/architecture/v1.0-architecture.md) - System architecture overview
- [MCP Tools Specification](../design/specifications/mcp-tools.md) - SSE event details
