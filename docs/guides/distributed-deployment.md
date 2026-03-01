# Distributed Deployment Guide

Deploy ClaudeVN Serving in the cloud with remote Compute instances on separate machines.

## Architecture

```
┌─────────────────────────────────────────────┐
│  Cloud VM                                   │
│  ┌───────────┐    ┌──────────────────────┐  │
│  │   Caddy   │───▶│    Serving (:8002)   │  │
│  │  (:443)   │    │  + Redis + Market.   │  │
│  └───────────┘    └──────────────────────┘  │
│        ▲                                    │
└────────┼────────────────────────────────────┘
         │ HTTPS (:443)
         │
    ┌────┴────┐      ┌──────────┐
    │Compute 1│      │Compute 2 │  (remote workstations)
    └─────────┘      └──────────┘
```

All traffic flows **outbound from Compute to Serving**. Compute nodes do not need
inbound ports open.

## Prerequisites

- A cloud VM with a public IP (AWS EC2, GCP CE, DigitalOcean, etc.)
- A DNS A record pointing to the VM (e.g., `claudevn.example.com`)
- Ports 80 and 443 open on the VM firewall
- Docker and Docker Compose installed on the VM
- Full ClaudeVN repository cloned on the VM

## 1. Deploy Serving with TLS

### Generate a registration token

```bash
python3 -c "import secrets; print(f'troc_{secrets.token_hex(24)}')"
# Example output: troc_a1b2c3d4e5f6...
```

### Configure environment

```bash
# On the cloud VM
cp deploy/cloud/.env.cloud.example deploy/cloud/.env.cloud
```

Edit `deploy/cloud/.env.cloud`:
```env
DOMAIN=claudevn.example.com
COMPUTE_REGISTRATION_TOKEN=troc_<your_generated_token>
```

Also set `SERVING_PUBLIC_URL` in your main `.env` or docker-compose override:
```env
SERVING_PUBLIC_URL=https://claudevn.example.com
```

### Start services

```bash
docker compose -f docker-compose.yml -f deploy/cloud/docker-compose.cloud.yml up -d
```

Caddy will automatically provision a Let's Encrypt TLS certificate on the first
request. Certificate renewal is automatic (~30 days before expiry).

### Verify

```bash
curl https://claudevn.example.com/api/v1/health
```

## 2. Configure Remote Compute Instances

On each remote machine:

```bash
cp .env.compute.example .env.compute
```

Edit `.env.compute`:
```env
# Point to your cloud Serving instance (HTTPS)
CLAUDEVN_SERVING_URL=https://claudevn.example.com

# Registration token (must match COMPUTE_REGISTRATION_TOKEN on Serving)
CLAUDEVN_API_KEY=troc_<same_token_as_serving>

# Unique ID for this compute instance
CLAUDEVN_COMPUTE_ID=compute-remote-001
CLAUDEVN_COMPUTE_NAME=My-Workstation

# Skills and capabilities
CLAUDEVN_SKILLS=code-writer,test-automator
CLAUDEVN_CAPABILITIES=python,javascript,typescript
```

### Start the compute instance

```bash
docker compose -f docker-compose.compute.yml up -d
```

The compute instance will:
1. Connect to Serving via SSE over HTTPS
2. Authenticate with the registration token
3. Register itself in the compute pool
4. Wait for work assignments

### Verify registration

Check the Serving UI at `https://claudevn.example.com` or:
```bash
curl https://claudevn.example.com/api/v1/compute
```

## 3. Firewall Rules

### Serving VM (cloud)

| Port | Direction | Purpose |
|------|-----------|---------|
| 443 | Inbound | HTTPS (Caddy TLS termination) |
| 80 | Inbound | HTTP → HTTPS redirect + ACME challenge |

All other ports should be blocked from public access. Redis (6379), Marketplace
(8003), and Serving (8002) only need to be reachable within the Docker network.

### Compute machines (remote)

| Port | Direction | Purpose |
|------|-----------|---------|
| — | Outbound | HTTPS to Serving (:443) |

No inbound ports are required. All communication is initiated by Compute.

## 4. Environment Variable Reference

### Serving (cloud)

| Variable | Required | Description |
|----------|----------|-------------|
| `DOMAIN` | Yes | Public domain for TLS (in `.env.cloud`) |
| `SERVING_PUBLIC_URL` | Yes | `https://<domain>` — used in Git URLs sent to compute |
| `COMPUTE_REGISTRATION_TOKEN` | Recommended | Pre-shared token for compute auth |

### Compute (remote)

| Variable | Required | Description |
|----------|----------|-------------|
| `CLAUDEVN_SERVING_URL` | Yes | `https://<domain>` of cloud Serving |
| `CLAUDEVN_API_KEY` | If token set on Serving | Registration token |
| `CLAUDEVN_COMPUTE_ID` | Yes | Unique instance identifier |
| `CLAUDEVN_COMPUTE_NAME` | No | Human-readable name (auto-generated if not set) |
| `CLAUDEVN_SERVING_AUTH_URL` | No | Auto-derived from `CLAUDEVN_SERVING_URL` |
| `COMPUTE_AUTH_MODE` | No | `serving` (default) or `external` |

## 5. SSE Proxy Compatibility

If you use a reverse proxy other than Caddy, ensure SSE connections are not buffered:

| Proxy | Configuration |
|-------|---------------|
| **Caddy** | Works out of the box (no buffering by default) |
| **nginx** | Add `proxy_buffering off;` and `X-Accel-Buffering: no` |
| **AWS ALB** | Set idle timeout ≥ 300s; ALB supports SSE natively |
| **Cloudflare** | Disable "Rocket Loader" and "Auto Minify" for the SSE path |
| **HAProxy** | Use `option http-server-close` and `no option httpclose` |

## 6. Troubleshooting

### Compute cannot connect

```bash
# Test HTTPS connectivity
curl -v https://claudevn.example.com/api/v1/health

# Check compute logs
docker compose -f docker-compose.compute.yml logs -f
```

Common causes:
- DNS not resolving → check A record
- Firewall blocking 443 → open port
- Wrong registration token → compare `CLAUDEVN_API_KEY` with `COMPUTE_REGISTRATION_TOKEN`

### Git clone fails on compute

The `repository` URL in work assignments should use `SERVING_PUBLIC_URL`.
Verify it's set correctly:

```bash
# On Serving VM
echo $SERVING_PUBLIC_URL  # Should be https://claudevn.example.com
```

### SSE connection drops frequently

- Increase keepalive interval: set `SSE_KEEPALIVE_INTERVAL=15` on Serving
- Check proxy timeouts (idle timeout should be > keepalive interval)
- If behind NAT, reduce keepalive interval to survive NAT timeout (typically 30-60s)

### Compute shows "SECURITY: plain HTTP" warning

You're using `http://` instead of `https://` for `CLAUDEVN_SERVING_URL`.
Update to use HTTPS with the domain configured in Caddy.
