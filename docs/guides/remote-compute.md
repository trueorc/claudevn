# Remote Compute Setup Guide

**Version**: 1.0.0
**Last Updated**: February 2026
**Audience**: Platform Administrators, VCN Node Operators

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [Authentication Modes](#authentication-modes)
- [Networking](#networking)
- [Security Considerations](#security-considerations)
- [Advanced Deployments](#advanced-deployments)
- [Troubleshooting](#troubleshooting)

---

## Overview

Remote compute instances allow you to scale ClaudeVN across multiple machines, either in your local network or distributed geographically. Each remote compute instance connects to a central Serving component for work coordination.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Central Serving Host                        │
│                                                                   │
│  ┌─────────────┐    ┌─────────┐    ┌────────────┐               │
│  │  Serving    │───▶│  Redis  │    │   Git      │               │
│  │  (port 8002)│    │         │    │   Repos    │               │
│  └──────┬──────┘    └─────────┘    └────────────┘               │
│         │                                                         │
└─────────┼─────────────────────────────────────────────────────────┘
          │
          │ SSE Events (work_assigned, credentials_refresh)
          │ HTTP Registration + Heartbeats
          │
    ┌─────┴─────┬──────────────┬──────────────┐
    │           │              │              │
┌───▼────┐  ┌──▼─────┐    ┌───▼────┐    ┌───▼────┐
│Compute1│  │Compute2│    │Compute3│    │Compute4│
│Local   │  │Local   │    │Remote  │    │Remote  │
│(Docker)│  │(Docker)│    │(VM)    │    │(Cloud) │
└────────┘  └────────┘    └────────┘    └────────┘
```

### Use Cases

| Scenario | Configuration |
|----------|---------------|
| **Single Machine** | All services in `docker-compose.yml` |
| **Multi-Machine LAN** | Serving on one host, compute on others |
| **Hybrid Cloud** | Serving on-premises, compute in cloud VMs |
| **Distributed Team** | Serving in shared VPN, compute on team machines |
| **GPU Workloads** | Serving on standard host, GPU compute on accelerated instance |

---

## Prerequisites

### Remote Host Requirements

1. **Docker Engine** 20.10+ (or Docker Desktop)
2. **Network Access** to Serving host on port 8002
3. **Operating System**: Linux, macOS, or Windows (WSL2)
4. **Resources**:
   - 2+ CPU cores
   - 4+ GB RAM
   - 10+ GB disk space

### Serving Host Requirements

1. **Serving component** running and accessible
2. **Firewall** configured to allow inbound port 8002
3. **DNS/IP address** that remote hosts can resolve

### Verification

On the remote host, test connectivity:

```bash
# Test Serving reachability
curl http://<serving-host>:8002/api/v1/health

# Expected response:
# {"status":"healthy","version":"1.0.0"}
```

---

## Quick Start

### Step 1: Clone Repository on Remote Host

```bash
# SSH into remote machine
ssh user@remote-host

# Clone the ClaudeVN repository
git clone https://github.com/Guarrdon/trueorc.git
cd trueorc
```

### Step 2: Create Compute Configuration

Create a `.env.compute` file:

```bash
cp .env.example .env.compute
```

Edit `.env.compute` with your configuration:

```bash
# .env.compute

# === Serving Integration ===
SERVING_URL=http://<serving-host-ip>:8002
CLAUDEVN_SERVING_AUTH_URL=http://<serving-host-ip>:8002/api/v1/auth

# === Compute Identity ===
COMPUTE_INSTANCE_ID=compute-remote-001
COMPUTE_INSTANCE_NAME=Remote-Compute-GPU
COMPUTE_PUBLIC_URL=http://<remote-host-ip>:8010

# === Registration ===
COMPUTE_REGISTER_ON_STARTUP=true
COMPUTE_HEARTBEAT_INTERVAL=30

# === Auth Mode ===
# "serving" - Fetch credentials from Serving (recommended)
# "external" - Use own credentials
COMPUTE_AUTH_MODE=serving

# === Skills/Capabilities ===
COMPUTE_SKILLS=code-writer,test-automator
COMPUTE_CAPABILITIES=python,javascript,typescript

# === MCP ===
MCP_ENABLED=true
CLAUDEVN_SERVING_URL=http://<serving-host-ip>:8002

# === Ports ===
COMPUTE_HOST=0.0.0.0
COMPUTE_PORT=8010

# === Storage ===
COMPUTE_STORAGE_PATH=/app/data/compute
COMPUTE_LOG_FILE=/app/logs/compute.log
LOG_LEVEL=INFO
```

**Replace**:
- `<serving-host-ip>`: IP address or hostname of your Serving machine
- `<remote-host-ip>`: IP address of the remote machine (for callbacks)

### Step 3: Create Docker Compose Override

Create `docker-compose.remote.yml`:

```yaml
# docker-compose.remote.yml
# Minimal compose file for remote compute instance

services:
  compute-remote:
    build:
      context: .
      dockerfile: compute/Dockerfile
    container_name: claudevn-compute-remote
    ports:
      - "8010:8010"
    env_file:
      - .env.compute
    volumes:
      - compute_data:/app/data
      - compute_logs:/app/logs
    restart: unless-stopped

volumes:
  compute_data:
    driver: local
  compute_logs:
    driver: local
```

### Step 4: Start Remote Compute

```bash
docker compose -f docker-compose.remote.yml up -d
```

### Step 5: Verify Registration

Check logs on the remote host:

```bash
# View registration logs
docker compose -f docker-compose.remote.yml logs compute-remote

# Expected output:
# [compute] Registering with serving at http://<serving-host>:8002
# [compute] Registration successful
# [entrypoint] Credentials fetched and written to /home/compute/.claude/.credentials.json
```

Check Serving host:

```bash
# View registered compute instances
curl http://<serving-host>:8002/api/v1/compute/instances

# Expected: Your remote instance in the list
```

---

## Configuration Reference

### Environment Variables

#### Core Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SERVING_URL` | Yes | `http://serving:8002` | Base URL of Serving component |
| `COMPUTE_INSTANCE_ID` | Yes | (auto-generated) | Unique identifier for this instance |
| `COMPUTE_INSTANCE_NAME` | No | `Compute-001` | Human-readable name |
| `COMPUTE_PUBLIC_URL` | No | Auto-detected | Public URL for callbacks |

#### Registration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COMPUTE_REGISTER_ON_STARTUP` | No | `true` | Auto-register with Serving on startup |
| `COMPUTE_HEARTBEAT_INTERVAL` | No | `30` | Heartbeat interval in seconds |

#### Authentication

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COMPUTE_AUTH_MODE` | No | `serving` | Auth mode: `serving` or `external` |
| `CLAUDEVN_SERVING_AUTH_URL` | No | `{SERVING_URL}/api/v1/auth` | Auth endpoint URL |

#### Skills and Capabilities

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COMPUTE_SKILLS` | No | `code-writer` | Comma-separated skill tags |
| `COMPUTE_CAPABILITIES` | No | `python` | Comma-separated capability tags |

#### MCP Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_ENABLED` | No | `true` | Enable MCP tools |
| `CLAUDEVN_SERVING_URL` | No | `{SERVING_URL}` | Serving URL for MCP connections |

#### Server Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COMPUTE_HOST` | No | `0.0.0.0` | Bind address |
| `COMPUTE_PORT` | No | `8010` | HTTP port |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

---

## Authentication Modes

Remote compute instances support two authentication modes:

### Mode 1: Serving (Recommended)

Fetch credentials from the central Serving component.

**Configuration**:
```bash
COMPUTE_AUTH_MODE=serving
CLAUDEVN_SERVING_AUTH_URL=http://<serving-host>:8002/api/v1/auth
```

**How It Works**:
1. User pastes token into Serving UI (`claude setup-token`)
2. Serving stores token in Redis
3. Remote compute fetches token at startup via `GET /auth/credentials`
4. Serving broadcasts `credentials_refresh` events via SSE
5. Remote compute auto-refreshes when token changes

**Advantages**:
- Single token for entire fleet
- Auto-distribution to all compute instances
- No manual credential management on remote hosts

**Requirements**:
- Network access to Serving port 8002
- Token configured in Serving UI

---

### Mode 2: External

Use credentials pre-provisioned on the remote host.

**Configuration**:
```bash
COMPUTE_AUTH_MODE=external
```

**How It Works**:
1. Manually create `~/.claude/.credentials.json` on remote host
2. Mount credentials into container:
   ```yaml
   volumes:
     - ~/.claude:/home/compute/.claude:ro
   ```
3. Compute uses local credentials

**Advantages**:
- Independent Claude subscriptions per compute instance
- Works without network access to Serving auth endpoint
- Useful for air-gapped or highly restricted environments

**Disadvantages**:
- Manual credential management
- Must update each host individually when tokens expire
- No centralized monitoring

---

## Networking

### Required Connectivity

Remote compute instances must reach Serving on:

| Port | Protocol | Purpose |
|------|----------|---------|
| 8002 | HTTP | Registration, heartbeats, API calls |
| 8002 | SSE | Work assignment events, credential refresh |

**Direction**: Remote compute → Serving (outbound only)

Serving **does not** initiate connections to compute instances.

### Network Topologies

#### Local Area Network (LAN)

Direct IP connectivity on private network.

**Pros**: Simple, low latency, no encryption needed
**Cons**: Limited to single physical location

**Example**:
```bash
# Serving at 192.168.1.100
SERVING_URL=http://192.168.1.100:8002
```

#### VPN/Overlay Network

Secure tunnel using Tailscale, WireGuard, or similar.

**Pros**: Secure, works across WAN, auto-discovery
**Cons**: Requires VPN setup and maintenance

**Example with Tailscale**:
```bash
# Serving at tailscale hostname
SERVING_URL=http://serving-node.tailscale.net:8002
```

**Setup**:
1. Install Tailscale on all hosts
2. Use Tailscale hostnames for `SERVING_URL`
3. Firewall rules not needed (Tailscale handles it)

#### Public Internet

Expose Serving via reverse proxy with TLS.

**Pros**: Accessible from anywhere
**Cons**: Security critical, requires TLS and auth hardening

**Example with Nginx**:
```nginx
# /etc/nginx/sites-available/claudevn
server {
    listen 443 ssl http2;
    server_name claudevn.example.com;

    ssl_certificate /etc/letsencrypt/live/claudevn.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/claudevn.example.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Remote compute config**:
```bash
SERVING_URL=https://claudevn.example.com
```

#### Docker Swarm Overlay

Multi-host Docker deployment with overlay network.

**Pros**: Native Docker networking, auto-discovery, encryption
**Cons**: Requires Swarm mode, adds complexity

**Example**:
```bash
# Initialize swarm on Serving host
docker swarm init

# Join worker nodes
docker swarm join --token <token> <serving-ip>:2377

# Deploy stack with overlay network
docker stack deploy -c docker-compose.swarm.yml claudevn
```

---

## Security Considerations

### Network Security

| Best Practice | Implementation |
|---------------|----------------|
| **Use TLS** | Reverse proxy with Let's Encrypt |
| **Restrict IPs** | Firewall rules to allow only known compute hosts |
| **VPN** | Tailscale/WireGuard for encrypted overlay |
| **Auth tokens** | Rotate compute API keys regularly |
| **Private networks** | Use RFC1918 addresses when possible |

### Firewall Configuration

#### Serving Host (Ubuntu/Debian)

```bash
# Allow Serving port from specific IPs
sudo ufw allow from 192.168.1.0/24 to any port 8002 proto tcp

# Or allow from everywhere (less secure)
sudo ufw allow 8002/tcp

# Enable firewall
sudo ufw enable
```

#### Compute Host

No inbound ports required (compute initiates all connections).

Outbound port 8002 must be allowed.

### Credential Protection

**DO**:
- Use `COMPUTE_AUTH_MODE=serving` to centralize credentials
- Rotate tokens regularly (365-day expiry)
- Use separate Claude subscriptions for production vs development

**DON'T**:
- Commit `.env.compute` files with credentials to Git
- Use writable volume mounts for credentials
- Expose credentials in logs (ClaudeVN auto-redacts tokens)

### Compute API Keys

Each registered compute instance receives a unique API key. This key:
- Authenticates requests to `GET /auth/credentials`
- Cannot be reused by other instances
- Is revoked if the instance is deregistered

**Key Rotation**:
```bash
# Deregister old instance
curl -X DELETE http://<serving>:8002/api/v1/compute/instances/compute-001

# Re-register to get new key
# (Compute does this automatically on next startup)
```

---

## Advanced Deployments

### Multi-Region Setup

Deploy compute instances in multiple geographic regions.

**Architecture**:
```
Serving (us-east-1)
    ├── Compute-1 (us-east-1) - Low latency
    ├── Compute-2 (eu-west-1) - Higher latency
    └── Compute-3 (ap-southeast-1) - High latency
```

**Considerations**:
- Network latency affects heartbeat reliability
- Set `COMPUTE_HEARTBEAT_INTERVAL=60` for high-latency regions
- Use regional Redis replicas if performance is critical

**Example**:
```bash
# EU compute instance
SERVING_URL=https://claudevn-us-east.example.com
COMPUTE_HEARTBEAT_INTERVAL=60
```

---

### Heterogeneous Fleet

Deploy compute instances with different capabilities.

**Example Fleet**:

| Instance | Skills | Capabilities | Hardware |
|----------|--------|--------------|----------|
| `compute-cpu-001` | code-writer | python, javascript | 8 CPU, 16GB RAM |
| `compute-gpu-001` | ml-trainer | python, pytorch, cuda | 4 CPU, 32GB RAM, A100 GPU |
| `compute-db-001` | db-engineer | postgresql, mongodb | 2 CPU, 8GB RAM |

**Configuration**:
```bash
# GPU instance
COMPUTE_INSTANCE_ID=compute-gpu-001
COMPUTE_SKILLS=ml-trainer,data-scientist
COMPUTE_CAPABILITIES=python,pytorch,tensorflow,cuda
```

---

### High Availability

Run multiple compute instances as a redundant pool.

**Setup**:
```bash
# Compute instance 1
COMPUTE_INSTANCE_ID=compute-pool-001
COMPUTE_SKILLS=code-writer
COMPUTE_CAPABILITIES=python,javascript

# Compute instance 2 (identical)
COMPUTE_INSTANCE_ID=compute-pool-002
COMPUTE_SKILLS=code-writer
COMPUTE_CAPABILITIES=python,javascript
```

**Behavior**:
- Serving assigns work to any available instance with matching skills
- If one instance fails, others continue serving requests
- Use Docker Swarm or Kubernetes for automatic restarts

---

### Kubernetes Deployment

Deploy remote compute as a Kubernetes StatefulSet.

**Example**:
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: claudevn-compute
spec:
  serviceName: claudevn-compute
  replicas: 3
  selector:
    matchLabels:
      app: claudevn-compute
  template:
    metadata:
      labels:
        app: claudevn-compute
    spec:
      containers:
      - name: compute
        image: claudevn/compute:latest
        env:
        - name: SERVING_URL
          value: "http://claudevn-serving.default.svc.cluster.local:8002"
        - name: COMPUTE_INSTANCE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: COMPUTE_AUTH_MODE
          value: "serving"
        - name: COMPUTE_SKILLS
          value: "code-writer,test-automator"
        volumeMounts:
        - name: data
          mountPath: /app/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi
```

---

## Troubleshooting

### Remote Compute Won't Register

**Symptom**: No registration logs, instance not visible in Serving UI.

**Diagnosis**:
```bash
# Check compute logs
docker compose -f docker-compose.remote.yml logs compute-remote

# Test connectivity
curl http://<serving-host>:8002/api/v1/health
```

**Common Causes**:

| Issue | Fix |
|-------|-----|
| **Firewall blocking** | Allow port 8002 on Serving host |
| **Wrong SERVING_URL** | Verify URL is correct and reachable |
| **DNS resolution failure** | Use IP address instead of hostname |
| **Auto-register disabled** | Set `COMPUTE_REGISTER_ON_STARTUP=true` |

---

### Credentials Not Fetched

**Symptom**: Compute logs show "credentials not ready" errors.

**Diagnosis**:
```bash
# Check auth status on Serving
curl http://<serving-host>:8002/api/v1/auth/status

# Check compute auth mode
docker compose -f docker-compose.remote.yml exec compute-remote env | grep AUTH
```

**Fixes**:

1. **If auth status is `not_configured`**:
   - Complete token setup in Serving UI
   - Restart compute: `docker compose -f docker-compose.remote.yml restart`

2. **If auth mode is `external`**:
   - Either switch to `serving` mode, or
   - Provision credentials manually on remote host

3. **If network issue**:
   - Test endpoint: `curl http://<serving-host>:8002/api/v1/auth/status`
   - Check firewall rules

---

### Heartbeat Timeouts

**Symptom**: Compute shows as "offline" in Serving UI despite running.

**Diagnosis**:
```bash
# Check heartbeat interval
docker compose -f docker-compose.remote.yml exec compute-remote env | grep HEARTBEAT

# Check network latency
ping <serving-host>
```

**Fix**:

Increase heartbeat interval for high-latency connections:
```bash
# In .env.compute
COMPUTE_HEARTBEAT_INTERVAL=60
```

Or adjust thresholds on Serving:
```bash
# In Serving .env
DEGRADED_THRESHOLD=120
OFFLINE_THRESHOLD=180
```

---

### SSE Connection Drops

**Symptom**: Compute logs show repeated SSE reconnections.

**Diagnosis**:
```bash
# Check compute SSE client logs
docker compose -f docker-compose.remote.yml logs compute-remote | grep SSE
```

**Causes**:
- Network instability
- Reverse proxy timeout (default 60s for many proxies)
- Serving restart

**Fix for Nginx proxy**:
```nginx
location / {
    proxy_read_timeout 300s;  # Increase SSE timeout
    proxy_send_timeout 300s;
}
```

**Fix for compute**:
```bash
# Tune reconnect backoff
# (No config needed - built-in exponential backoff)
```

---

### Port Conflicts

**Symptom**: Container fails to start with "address already in use".

**Diagnosis**:
```bash
# Check what's using port 8010
sudo lsof -i :8010
```

**Fix**:

Change port in `.env.compute`:
```bash
COMPUTE_PORT=8011
```

And in `docker-compose.remote.yml`:
```yaml
ports:
  - "8011:8011"
```

---

## Related Documents

- [Authentication Setup Guide](auth-setup.md) - Token-based auth system
- [Docker Authentication Guide](docker-authentication.md) - Legacy OAuth-based auth
- [v1.0 Architecture](../design/architecture/v1.0-architecture.md) - System architecture
- [MCP Tools Specification](../design/specifications/mcp-tools.md) - SSE event protocol
- [Compute Spawner Design](../design/specifications/compute-spawner.md) - Compute lifecycle
