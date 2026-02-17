# ClaudeVN Troubleshooting Guide

This guide provides solutions to common problems in ClaudeVN. Issues are organized by category with symptoms, diagnosis steps, and solutions.

## Startup Issues

### Services Fail to Start

**Symptoms:**
- Docker containers exit immediately
- `docker compose up` shows unhealthy containers
- Services crash during initialization

**Diagnosis:**

```bash
# Check all service logs
docker compose logs -f

# Check specific service
docker compose logs serving
docker compose logs marketplace
docker compose logs redis

# Check container status
docker compose ps
```

**Common Causes and Solutions:**

**1. Dependency Services Not Ready**

ClaudeVN services have strict startup dependencies:
- Serving depends on Redis (health check: healthy)
- Serving depends on Marketplace (health check: healthy)

If services crash immediately, check dependency health:

```bash
# Check Redis health
docker compose logs redis

# Check Marketplace health
curl http://localhost:8003/api/v1/health
```

Solution: Wait for dependencies to become healthy. Docker Compose should handle this automatically, but if services repeatedly fail, restart the stack:

```bash
docker compose down
docker compose up -d
```

**2. Port Conflicts**

ClaudeVN uses these ports:
- `8002` - Serving API
- `8003` - Marketplace API
- `2222` - Git SSH server
- `6379` - Redis

Check for conflicts:

```bash
# macOS/Linux
lsof -i :8002
lsof -i :8003
lsof -i :2222
lsof -i :6379

# Or using netstat
netstat -an | grep LISTEN | grep -E "8002|8003|2222|6379"
```

Solution: Stop conflicting services or change ClaudeVN ports in `docker-compose.yml`.

**3. Docker Not Running**

Verify Docker Desktop is running and accessible:

```bash
docker info
docker compose version
```

**4. Permission Issues**

Check STORAGE_PATH permissions:

```bash
# Serving needs write access to storage
ls -la /path/to/storage

# Fix permissions if needed
chmod -R 755 /path/to/storage
```

### Serving Won't Start

**Symptoms:**
- Serving container exits with error
- Health endpoint unreachable
- Logs show initialization failures

**Diagnosis:**

```bash
# Check serving logs
docker compose logs serving

# Test health endpoint
curl http://localhost:8002/api/v1/health
```

**Solutions:**

**1. Storage Path Issues**

Verify STORAGE_PATH configuration:

```bash
# Check environment variable
docker compose exec serving env | grep STORAGE_PATH

# Verify directory exists and is writable
docker compose exec serving ls -la /app/storage
```

**2. Redis Connection Failed**

Check Redis connectivity:

```bash
# Verify Redis is running
docker compose ps redis

# Test connection
docker compose exec serving ping redis

# Check Redis environment variables
docker compose exec serving env | grep REDIS
```

Default values:
- `REDIS_HOST=redis`
- `REDIS_PORT=6379`

**3. Marketplace Unavailable**

Serving depends on Marketplace being healthy:

```bash
# Check Marketplace health
curl http://localhost:8003/api/v1/health

# Verify Marketplace URL
docker compose exec serving env | grep MARKETPLACE_URL
```

## Authentication Issues

### Claude Credentials Expired

**Symptoms:**
- Compute instances fail to execute work
- Logs show authentication errors from Claude API
- Work gets stuck in ASSIGNED state

**Diagnosis:**

```bash
# Check serving logs for auth errors
docker compose logs serving | grep -i "auth\|credentials\|expired"

# Check compute logs
docker compose logs compute-1 | grep -i "auth\|401\|403"
```

**Solution:**

Re-authenticate with Claude:

```bash
# Interactive re-authentication
docker exec -it claudevn-serving /app/scripts/claude-reauth.sh

# Or via API
curl -X POST http://localhost:8002/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{}'
```

Follow the browser authentication flow. Credentials are stored in Serving and distributed to compute instances.

### Compute Can't Fetch Credentials

**Symptoms:**
- Compute starts but can't execute Claude Code operations
- Logs show credential fetch failures
- Authentication endpoint unreachable

**Diagnosis:**

```bash
# Check compute auth mode
docker compose exec compute-1 env | grep COMPUTE_AUTH_MODE

# Test Serving auth URL
curl http://serving:8002/api/v1/auth/credentials
```

**Solutions:**

**1. Wrong Auth Mode**

Verify `COMPUTE_AUTH_MODE`:
- `serving` - Fetch from Serving (recommended)
- `external` - Use external Claude auth

For Docker deployments, use `serving` mode.

**2. Network Connectivity**

Check compute can reach Serving:

```bash
# From compute container
docker compose exec compute-1 ping serving
docker compose exec compute-1 curl http://serving:8002/api/v1/health
```

**3. Serving Auth URL**

Verify `CLAUDEVN_SERVING_AUTH_URL`:

```bash
docker compose exec compute-1 env | grep CLAUDEVN_SERVING_AUTH_URL
```

Should be: `http://serving:8002/api/v1/auth/credentials` for Docker networks.

## Compute Connection Issues

### Compute Instances Not Registering

**Symptoms:**
- Compute containers running but not showing in Serving
- No work being assigned
- SSE connection not established

**Diagnosis:**

```bash
# Check compute logs
docker compose logs compute-1

# Check serving logs for registration
docker compose logs serving | grep -i "register\|compute"

# Verify compute health
docker compose exec compute-1 curl http://localhost:8000/health
```

**Solutions:**

**1. Registration Disabled**

Verify auto-registration is enabled:

```bash
docker compose exec compute-1 env | grep COMPUTE_REGISTER_ON_STARTUP
```

Should be `true`.

**2. Serving URL Incorrect**

Check SERVING_URL points to correct host:

```bash
docker compose exec compute-1 env | grep SERVING_URL
```

For Docker Compose: `http://serving:8002`

**3. Network Connectivity**

Verify compute is on the correct network:

```bash
# List networks
docker network ls

# Inspect claudevn-network
docker network inspect claudevn-network
```

All services should be on `claudevn-network`.

**4. Health Check Failing**

Test Serving health endpoint:

```bash
docker compose exec compute-1 curl http://serving:8002/api/v1/health
```

### SSE Connection Drops

**Symptoms:**
- Compute disconnects frequently
- Logs show reconnection attempts
- Work assignment delayed

**Diagnosis:**

```bash
# Check compute logs for SSE errors
docker compose logs compute-1 | grep -i "sse\|connection\|keepalive"

# Check serving logs
docker compose logs serving | grep -i "sse\|disconnect"
```

**Solutions:**

**1. Network Instability**

SSE connections use keepalive to detect drops. Adjust reconnection settings:

```yaml
# docker-compose.yml compute service
environment:
  CLAUDEVN_SSE_RECONNECT_DELAY: 5
  CLAUDEVN_SSE_MAX_RECONNECT_DELAY: 60
```

**2. Serving Restart**

When Serving restarts, compute instances reconnect automatically. Check serving uptime:

```bash
docker compose ps serving
```

### Compute Marked as DEGRADED or OFFLINE

**Symptoms:**
- Compute status shows DEGRADED or OFFLINE in UI
- Work not assigned to degraded instances
- Heartbeat failures in logs

**Diagnosis:**

```bash
# Check compute status via API
curl http://localhost:8002/api/v1/compute/instances

# Check heartbeat logs
docker compose logs compute-1 | grep -i "heartbeat"
docker compose logs serving | grep -i "heartbeat"
```

**Solutions:**

**1. Heartbeat Timing Mismatch**

Verify heartbeat interval matches serving expectations:

```yaml
# Compute service
COMPUTE_HEARTBEAT_INTERVAL: 30  # seconds

# Serving service
HEALTH_CHECK_INTERVAL: 60       # seconds
DEGRADED_THRESHOLD: 90          # seconds (1.5x check interval)
OFFLINE_THRESHOLD: 180          # seconds (3x check interval)
```

**2. Compute Under Heavy Load**

If compute is overloaded, heartbeats may be delayed. Check resource usage:

```bash
docker stats compute-1
```

## Git Issues

### Git Push/Pull Fails

**Symptoms:**
- Compute can't push work to Serving
- Authentication errors
- Connection refused errors

**Diagnosis:**

```bash
# Check SSH server status
docker compose logs serving | grep -i "ssh\|git"

# Test SSH connection from compute
docker compose exec compute-1 ssh -p 2222 git@serving
```

**Solutions:**

**1. SSH Server Not Running**

Verify SSH is enabled:

```bash
docker compose exec serving env | grep GIT_ENABLE_SSH
```

Should be `true`. Check SSH port:

```bash
docker compose exec serving env | grep SSH_GIT_PORT
```

Default is `2222`.

**2. SSH Key Not Authorized**

Compute SSH keys must be registered with Serving. Check authorized keys:

```bash
docker compose exec serving cat /app/storage/git/ssh/authorized_keys
```

**3. Repository Not Initialized**

Verify Git repository exists:

```bash
docker compose exec serving ls -la /app/storage/git/repos/
```

### Merge Conflicts

**Symptoms:**
- PR merge fails
- Serving logs show conflict detection
- Compute receives merge_conflict event

**Diagnosis:**

```bash
# Check serving logs for conflicts
docker compose logs serving | grep -i "conflict\|merge"

# Check PR status in Redis
docker exec -it claudevn-redis redis-cli
> HGETALL claudevn:branch:project:branch-name
```

**Solution:**

Serving detects conflicts and notifies compute via SSE `merge_conflict` event. Compute should:
1. Fetch latest main branch
2. Rebase work on top of main
3. Resolve conflicts
4. Force push updated branch

This is handled automatically by compute instances.

### PR Queue Stuck

**Symptoms:**
- Branches not merging
- PR queue not processing
- Work marked complete but not merged

**Diagnosis:**

```bash
# Check Redis PR queue
docker exec -it claudevn-redis redis-cli

# Check PR queue for project
> LRANGE claudevn:pr_queue:project 0 -1

# Check merge queue
> LRANGE claudevn:merge_queue:project 0 -1

# Check individual branch status
> HGETALL claudevn:branch:project:branch-name
```

**Solution:**

If queue is stuck, check Serving PR processor logs:

```bash
docker compose logs serving | grep -i "pr\|merge\|queue"
```

Manual intervention may be required to clear stuck branches from Redis.

## Work Assignment Issues

### Work Not Being Assigned

**Symptoms:**
- Backlog items in READY status but not ASSIGNED
- No work running
- Compute instances idle

**Diagnosis:**

```bash
# Check work map status
curl http://localhost:8002/api/v1/work/map

# Check compute instances
curl http://localhost:8002/api/v1/compute/instances

# Check backlog
curl http://localhost:8002/api/v1/backlog
```

**Common Causes:**

**1. No Compute Instances Online**

Verify at least one compute instance is registered and HEALTHY:

```bash
curl http://localhost:8002/api/v1/compute/instances | jq '.[] | {id, status}'
```

**2. No Matching Capabilities**

Work requires capabilities that no compute instance has. Check task requirements:

```bash
curl http://localhost:8002/api/v1/backlog/{item_id}
```

Verify compute capabilities match:

```bash
curl http://localhost:8002/api/v1/compute/instances/{compute_id}
```

**3. Dependencies Not Met**

Work may be blocked by unmet dependencies. Check dependency graph:

```bash
curl http://localhost:8002/api/v1/work/dependencies/{item_id}
```

### Work Stuck in ASSIGNED State

**Symptoms:**
- Work assigned but no progress
- Compute logs show no activity
- Work timeout approaching

**Diagnosis:**

```bash
# Check work status
curl http://localhost:8002/api/v1/work/map

# Check compute instance status
curl http://localhost:8002/api/v1/compute/instances/{compute_id}

# Check serving logs for timeout detection
docker compose logs serving | grep -i "timeout\|stuck"
```

**Solutions:**

**1. Compute Crashed**

If compute crashed after assignment, work becomes stuck. Serving's stuck-work detection will retry:

```yaml
# Serving configuration
WORK_TIMEOUT_MINUTES: 30
WORK_TIMEOUT_MAX_RETRIES: 3
```

After timeout, work is reassigned to another compute instance.

**2. Manual Intervention**

Force reassignment via API:

```bash
curl -X POST http://localhost:8002/api/v1/work/{item_id}/reassign
```

## Marketplace Issues

### Skills Not Loading

**Symptoms:**
- Marketplace returns empty skill list
- Skill composition fails
- Marketplace errors in logs

**Diagnosis:**

```bash
# Check Marketplace health
curl http://localhost:8003/api/v1/health

# List available skills
curl http://localhost:8003/api/v1/skills

# Check Marketplace logs
docker compose logs marketplace | grep -i "skill\|error"
```

**Solutions:**

**1. Skills Path Incorrect**

Verify SKILLS_PATH:

```bash
docker compose exec marketplace env | grep SKILLS_PATH

# Check directory contents
docker compose exec marketplace ls -la /app/skills
```

**2. Invalid YAML Syntax**

Check skill file syntax:

```bash
docker compose exec marketplace cat /app/skills/example-skill.yaml
```

Validate YAML structure matches specification.

### Marketplace Unreachable

**Symptoms:**
- Serving can't connect to Marketplace
- Skill composition requests fail
- Fallback skills used

**Diagnosis:**

```bash
# Test Marketplace URL
curl http://localhost:8003/api/v1/health

# Check from Serving
docker compose exec serving curl http://marketplace:8003/api/v1/health

# Check Marketplace URL config
docker compose exec serving env | grep MARKETPLACE_URL
```

**Solution:**

Verify `MARKETPLACE_URL` in Serving configuration:

```yaml
# docker-compose.yml serving service
environment:
  MARKETPLACE_URL: http://marketplace:8003
```

If Marketplace is down, Serving uses fallback skills:

```yaml
MARKETPLACE_FALLBACK_SKILLS: "code-writer,debugger,test-automator"
```

## Performance Issues

### Slow API Responses

**Symptoms:**
- API requests take multiple seconds
- UI slow to load
- Timeouts in logs

**Diagnosis:**

```bash
# Check Redis latency
docker exec -it claudevn-redis redis-cli --latency

# Check serving resource usage
docker stats serving

# Test API response time
time curl http://localhost:8002/api/v1/health
```

**Solutions:**

**1. Rate Limiting**

Check if rate limiting is enabled:

```bash
docker compose exec serving env | grep RATE_LIMIT_ENABLED
```

If enabled, check limits in configuration.

**2. Redis Connection Latency**

If Redis is slow, check:

```bash
docker stats redis
```

Restart Redis if necessary:

```bash
docker compose restart redis
```

**3. Too Many Concurrent Compute Instances**

Reduce number of compute instances if system is overloaded.

## Multi-Host / External Node Issues

### External Compute Can't Reach Serving

**Symptoms:**
- External compute instances can't connect
- Network timeout errors
- Registration fails

**Diagnosis:**

```bash
# From external node, test connectivity
ping serving-host
curl http://serving-host:8002/api/v1/health

# Check firewall rules
# Verify VPN connectivity
```

**Solutions:**

**1. Network Configuration**

Ensure Serving is exposed on external interface:

```yaml
# docker-compose.yml
ports:
  - "0.0.0.0:8002:8002"
```

**2. Firewall Rules**

Open required ports:
- `8002` - Serving API
- `2222` - Git SSH (if external git access needed)

**3. SERVING_URL**

External compute must use routable address:

```yaml
# External compute configuration
SERVING_URL: http://public-ip-or-domain:8002
```

Not `http://localhost:8002` or `http://serving:8002`.

**4. TLS/SSL**

For public endpoints, use TLS:
- Configure reverse proxy (nginx, Traefik)
- Update SERVING_URL to use HTTPS
- Ensure certificates are valid

## Useful Commands

### Service Management

```bash
# View all service logs
docker compose logs -f

# View specific service logs
docker compose logs -f serving
docker compose logs -f marketplace
docker compose logs -f compute-1

# Check service health
curl http://localhost:8002/api/v1/health
curl http://localhost:8003/api/v1/health

# Restart a service
docker compose restart serving

# Rebuild and restart
docker compose up -d --build serving
```

### Redis Inspection

```bash
# Open Redis CLI
docker exec -it claudevn-redis redis-cli

# List all ClaudeVN keys
> KEYS claudevn:*

# Check branch status
> HGETALL claudevn:branch:project:branch-name

# Check PR queue
> LRANGE claudevn:pr_queue:project 0 -1

# Check compute instance data
> HGETALL claudevn:compute:instance-id

# Monitor Redis commands
> MONITOR
```

### Authentication

```bash
# Re-authenticate Claude (interactive)
docker exec -it claudevn-serving /app/scripts/claude-reauth.sh

# Or via API
curl -X POST http://localhost:8002/api/v1/auth/login \
  -H "Content-Type: application/json"
```

### Git Operations

```bash
# Check Git repositories
docker compose exec serving ls -la /app/storage/git/repos/

# Test SSH connection
ssh -p 2222 git@localhost

# View authorized SSH keys
docker compose exec serving cat /app/storage/git/ssh/authorized_keys
```

### System Status

```bash
# Container resource usage
docker stats

# Disk usage
docker compose exec serving df -h

# Network inspection
docker network inspect claudevn-network

# Check environment variables
docker compose exec serving env | grep CLAUDEVN
```

## Getting Help

If troubleshooting steps don't resolve your issue:

1. Collect diagnostic information:
   - Service logs: `docker compose logs > claudevn-logs.txt`
   - Container status: `docker compose ps`
   - System info: `docker info`

2. Check documentation:
   - Architecture: `docs/design/architecture/v1.0-architecture.md`
   - Configuration: `docs/guides/configuration-guide.md`

3. File an issue:
   - Include diagnostic information
   - Describe symptoms and steps to reproduce
   - Note any recent changes to configuration
