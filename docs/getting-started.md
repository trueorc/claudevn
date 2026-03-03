# Getting Started with ClaudeVN

This guide walks you through setting up and using ClaudeVN for the first time.

## What is ClaudeVN?

ClaudeVN is a distributed AI collaboration platform that connects multiple Claude Code instances into a compute network. Instead of running one AI model on one task at a time, ClaudeVN enables genuine collaboration where specialized AI agents work in parallel, share context, and coordinate around real work.

**Key Concepts:**

- **Serving** - The central coordination hub that manages work distribution, hosts the Git repository, and provides the MCP communication layer
- **Compute Instances** - Claude Code environments that execute tasks using specialized skills
- **Marketplace** - Service that provides skill definitions and agent composition
- **Skills** - Atomic capability units (like code-writer, debugger, doc-writer) that define what an agent can do
- **Goals** - High-level objectives you define; the system dynamically interprets and decomposes them into tasks
- **Backlog** - Specific work items that can be prioritized and assigned to compute instances

## Prerequisites

Before you begin, ensure you have:

- **Docker Desktop** installed and running
- **Git** installed
- **An Anthropic API key** for Claude Code (get one at [console.anthropic.com](https://console.anthropic.com))
- At least 8GB of available RAM for the full stack

## Quick Start with Docker Compose

The simplest way to get started is using Docker Compose, which starts all services automatically.

### 1. Clone the Repository

```bash
git clone https://github.com/Guarrdon/claudevn.git
cd claudevn
```

### 2. Start All Services

```bash
# Starts all services in bypass auth mode (no login required for local dev)
docker compose up -d
```

This command starts:

| Service | Port | Description |
|---------|------|-------------|
| **redis** | 6379 | Redis for PR queue and branch management |
| **marketplace** | 8003 | Skill catalog and composition service |
| **serving** | 8002 | Coordination hub, API, and monitoring UI |
| **SSH Git** | 2222 | Git server for compute instances |
| **compute-1** | 8010 | Code Writer specialist |
| **compute-2** | 8011 | Debugger specialist |
| **compute-3** | 8012 | Documentation Writer specialist |

### 3. Authenticate Claude Code

The Serving container manages Claude OAuth credentials centrally. You need to authenticate once:

```bash
# Run the reauth script in the Serving container
docker exec -it claudevn-serving /app/scripts/claude-reauth.sh
```

Follow the prompts to:
1. Enter your Anthropic API key
2. Complete OAuth authentication in your browser
3. Credentials are stored securely on a persistent volume

**Alternative:** Use the web UI at http://localhost:8002 and navigate to Settings > Authentication to authenticate via the UI.

### 4. Verify Services Are Running

Check that all services are healthy:

```bash
docker compose ps
```

All services should show status `Up (healthy)`.

You can also check individual health endpoints:

```bash
# Serving
curl http://localhost:8002/api/v1/health

# Marketplace
curl http://localhost:8003/api/v1/health

# Compute instances
curl http://localhost:8010/api/v1/health
curl http://localhost:8011/api/v1/health
curl http://localhost:8012/api/v1/health
```

### 5. Access the Monitoring UI

Open your browser to http://localhost:8002

The UI provides real-time visibility into:
- **Goals** - High-level objectives and their status
- **Backlog** - Specific work items with priorities and assignments
- **Execution Plan** - Active and queued work arranged by dependencies
- **Compute Instances** - Agent status and health metrics
- **Git Activity** - Branch status and PR queue

## Creating Your First Goal

Now that the system is running, let's create your first goal.

### 1. Navigate to Goals

In the monitoring UI at http://localhost:8002, click on **Goals** in the navigation.

### 2. Create a New Goal

Click **New Goal** and enter a description of what you want accomplished. For example:

```
Create a Python utility library for data validation with comprehensive tests
```

### 3. Submit and Watch

Click **Create Goal**. The system will:

1. Interpret your goal
2. Decompose it into specific backlog items
3. Assign tasks to appropriate compute instances based on their skills
4. Start execution

### 4. Monitor Progress

- **Backlog tab** shows the specific work items created from your goal
- **Execution Plan tab** shows which tasks are running, queued, or blocked
- **Git Activity** shows branches being created and PRs being opened

### 5. Review Results

When compute instances complete work:
- They create pull requests with their changes
- PRs appear in the UI with links to GitHub (if configured)
- You can review and merge the PRs manually, or configure automatic merging

## Understanding the Workflow

Here's how work flows through ClaudeVN:

```
1. You create a GOAL
   ↓
2. System interprets and creates BACKLOG ITEMS
   ↓
3. Serving assigns items to COMPUTE INSTANCES based on skills
   ↓
4. Compute creates a GIT BRANCH and starts work
   ↓
5. Compute uses MCP TOOLS to communicate with Serving
   ↓
6. Completed work becomes a PULL REQUEST
   ↓
7. You REVIEW and MERGE (or configure auto-merge)
```

### Git-Native State Management

Every task creates a Git branch following this pattern:
```
{type}/{task}/{compute-id}
```

Example: `feature/data-validation/compute-001`

Compute instances use **Git worktrees** for efficient parallel branch access:
- `/workspace/main` - Reference copy of main branch
- `/workspace/active` - Active work branch

### Communication via MCP

Compute instances communicate with Serving using Model Context Protocol (MCP) tools:

- `report_progress` - Update task status
- `request_review` - Flag work for human review
- `fetch_backlog` - Get assigned tasks
- `update_branch_status` - Notify of branch changes

## Scaling Compute

You can easily add more compute capacity.

### Scale Existing Instances

```bash
# Scale up to 5 total compute instances
docker compose up -d --scale compute=5
```

### Add Specialized Instances

Create a `docker-compose.override.yml` file:

```yaml
services:
  compute-security:
    build:
      context: .
      dockerfile: compute/Dockerfile
    container_name: claudevn-compute-security
    ports:
      - "8020:8020"
    environment:
      - COMPUTE_HOST=0.0.0.0
      - COMPUTE_PORT=8020
      - COMPUTE_INSTANCE_ID=compute-security-001
      - COMPUTE_INSTANCE_NAME=Compute-SecurityReviewer
      - SERVING_URL=http://serving:8002
      - COMPUTE_SKILLS=security-reviewer,code-reviewer
      - COMPUTE_CAPABILITIES=security,python,javascript
      - COMPUTE_AUTH_MODE=serving
    volumes:
      - compute_security_data:/app/data
    networks:
      - claudevn-network
    depends_on:
      serving:
        condition: service_healthy

volumes:
  compute_security_data:
```

Then start the new instance:

```bash
docker compose up -d
```

## Adding External Compute Nodes

External compute nodes can join from other hosts (different machines, cloud VMs, etc.). Dedicated compose files handle the two primary deployment scenarios.

### Remote Serving Hub (with Cognito auth)

Use `docker-compose.serving.yml` with `.env.serving` for a production serving hub with Cognito authentication enabled:

```bash
cp .env.serving.example .env.serving
# Edit .env.serving with your Cognito and environment settings
docker compose -f docker-compose.serving.yml up -d
```

### Remote Compute Node

Use `docker-compose.compute.yml` with `.env.compute` to connect a compute node to a remote serving hub:

```bash
cp .env.compute.example .env.compute
# Edit .env.compute with your SERVING_URL and credentials
docker compose -f docker-compose.compute.yml up -d
```

See `.env.serving.example` and `.env.compute.example` for all available configuration options, and [Distributed Deployment Guide](guides/distributed-deployment.md) for full setup instructions.

### External Node Authentication Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **serving** | Fetch credentials from Serving's `/auth/credentials` endpoint | Trusted nodes on same network |
| **external** | Bring your own Anthropic API key | Untrusted nodes, cross-organization, public internet |

## Configuration Options

Key environment variables you can customize:

### Serving Configuration

```bash
SERVING_PORT=8002              # API and UI port
REDIS_HOST=redis               # Redis connection
MARKETPLACE_URL=http://...     # Marketplace service
GIT_ENABLE_SSH=true            # Enable SSH Git server
SSH_GIT_PORT=2222              # SSH server port
CLAUDE_CREDENTIALS_PATH=...    # Auth credentials path
AUTH_MODE=bypass               # 'bypass' for local dev, 'cognito' for production
```

### Compute Configuration

```bash
COMPUTE_PORT=8010              # Health/status port
COMPUTE_INSTANCE_ID=...        # Unique identifier
SERVING_URL=http://...         # Serving endpoint
COMPUTE_SKILLS=...             # Comma-separated skills
COMPUTE_CAPABILITIES=...       # Comma-separated capabilities
COMPUTE_AUTH_MODE=serving      # serving or external
MCP_ENABLED=true               # Enable MCP communication
```

See [Configuration Reference](configuration-reference.md) for complete documentation.

## Viewing Logs

Monitor logs for debugging or understanding what agents are doing:

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f serving
docker compose logs -f compute-1

# Filter by time
docker compose logs --since 30m serving
```

## Stopping and Cleanup

### Stop Services (Preserve Data)

```bash
docker compose down
```

This stops all containers but preserves data in Docker volumes.

### Clean Slate (Remove All Data)

```bash
docker compose down -v
```

**Warning:** This removes all volumes including:
- Redis data (PR queue, branch status)
- Git repositories
- Claude credentials
- Compute work history

## Troubleshooting

### Services Won't Start

**Check Docker Desktop is running:**
```bash
docker ps
```

**Rebuild containers:**
```bash
docker compose build --no-cache
docker compose up -d
```

### Authentication Fails

**Re-run authentication:**
```bash
docker exec -it claudevn-serving /app/scripts/claude-reauth.sh
```

**Check credentials are stored:**
```bash
docker exec -it claudevn-serving ls -la /app/data/serving/claude-credentials
```

### Compute Instances Can't Connect to Serving

**Check network connectivity:**
```bash
docker exec -it claudevn-compute-1 curl http://serving:8002/api/v1/health
```

**Verify SERVING_URL is correct:**
```bash
docker compose config | grep SERVING_URL
```

### Git Push Fails

**Check SSH Git server is running:**
```bash
docker compose ps serving
curl http://localhost:8002/api/v1/health
```

**Test SSH connection:**
```bash
ssh -p 2222 git@localhost
```

### High Memory Usage

**Reduce number of compute instances:**
```bash
docker compose stop compute-2 compute-3
```

**Check resource usage:**
```bash
docker stats
```

See [Troubleshooting Guide](troubleshooting.md) for more solutions.

## Next Steps

Now that you have ClaudeVN running:

1. **Learn the architecture** - Read [Architecture Overview](design/architecture/v1.0-architecture.md) to understand how components interact
2. **Explore MCP tools** - See [MCP Tools Reference](design/specifications/mcp-tools.md) for the communication protocol
3. **Author custom skills** - Check [Skill Authoring Guide](skill-authoring-guide.md) to create specialized agents
4. **Configure advanced settings** - Review [Configuration Reference](configuration-reference.md)
5. **Deploy to production** - See [Deployment Guide](deployment-guide.md) for production best practices

## Getting Help

- **GitHub Issues** - Report bugs or request features at [github.com/Guarrdon/claudevn/issues](https://github.com/Guarrdon/claudevn/issues)
- **Documentation** - Browse `docs/` for comprehensive guides and specifications
- **Architecture Decisions** - See `docs/design/adr/` for design rationale

## Summary

You've learned how to:
- Start ClaudeVN with Docker Compose
- Authenticate Claude Code instances
- Create and monitor goals
- Scale compute capacity
- Add external nodes
- Troubleshoot common issues

ClaudeVN gives you a private, distributed AI compute network where specialized agents collaborate on real work. The system handles task decomposition, work distribution, and coordination - you focus on defining goals and reviewing results.

**Happy orchestrating!**
