# ClaudeVN Compute Infrastructure

The Compute Infrastructure is the agent execution runtime for the ClaudeVN platform. It runs agent processes, manages their lifecycle, handles tool invocations, and integrates with LLM providers.

## Overview

The Compute Engine:
- **Executes agents** locally with full lifecycle management
- **Registers with Serving** component to join the virtual compute pool
- **Sends heartbeats** to maintain registration status
- **Manages tools** available for agent execution
- **Integrates with LLMs** (OpenAI, Anthropic, etc.) for agent reasoning
- **Provides monitoring** APIs for configuration and activity tracking

## Quick Start

### Standalone Mode

Start the compute engine by itself:

```bash
cd compute
./start.sh
```

The engine will start and connect outbound to Serving via SSE.

### Integrated Mode

Start as part of the complete ClaudeVN platform:

```bash
# From project root
./start_all.sh
```

This starts Marketplace (8003), Serving (8002), and Compute together.

### Stop the Engine

```bash
cd compute
./stop.sh

# Or stop all services
cd ..
./stop_all.sh
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│           ClaudeVN Compute Engine                    │
│           (no HTTP server, no ports)                 │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────────────────────────────┐      │
│  │       SSE Event Client (outbound)         │      │
│  │  - Connects to Serving SSE endpoint      │      │
│  │  - Receives work_assigned events         │      │
│  │  - Receives keepalive (heartbeat file)   │      │
│  └──────────────────────────────────────────┘      │
│                                                      │
│  ┌──────────────────────────────────────────┐      │
│  │       Claude Code Spawner                 │      │
│  │  - Spawns Claude Code CLI instances      │      │
│  │  - Manages work execution lifecycle      │      │
│  └──────────────────────────────────────────┘      │
│                                                      │
│  ┌──────────────────────────────────────────┐      │
│  │       Credential Monitor                  │      │
│  │  - Fetches credentials from Serving      │      │
│  │  - Monitors expiry and refreshes         │      │
│  └──────────────────────────────────────────┘      │
│                                                      │
└─────────────────────────────────────────────────────┘
         │
         │ Outbound SSE connection
         │ GET /api/v1/compute/connect
         ▼
┌─────────────────────────────────────────────────────┐
│        Serving Component (Port 8002)                │
│         - Compute Registry                          │
│         - SSE Connection Manager                    │
│         - Work Orchestrator                         │
└─────────────────────────────────────────────────────┘
```

## Configuration

The compute engine is configured through environment variables:

### Instance Identity

```bash
COMPUTE_INSTANCE_ID=compute-001    # Unique instance ID (auto-generated if not set)
COMPUTE_INSTANCE_NAME="My Compute" # Human-readable name
```

### Serving Integration

```bash
SERVING_URL=http://localhost:8002  # Serving component URL
COMPUTE_REGISTER_ON_STARTUP=true   # Auto-register on startup
COMPUTE_HEARTBEAT_INTERVAL=30      # Heartbeat interval in seconds
```

### Storage

```bash
COMPUTE_STORAGE_PATH=./data/compute  # Data storage directory
```

### Agents and Tools

```bash
COMPUTE_AGENTS_DIR=./agents          # Directory with agent JSON definitions
COMPUTE_TOOLS_DIR=./tools            # Directory with tool JSON definitions
```

### LLM Providers

```bash
OPENAI_API_KEY=sk-...                # OpenAI API key
ANTHROPIC_API_KEY=sk-ant-...         # Anthropic API key
```

### Features

```bash
COMPUTE_ENABLE_GPU=false             # Enable GPU support
LOG_LEVEL=INFO                       # Logging level
```

## Health Check

Compute has no HTTP server. Docker healthcheck uses a **heartbeat file** mechanism:

1. SSE keepalive events from Serving touch `/tmp/compute-heartbeat` every ~15 seconds
2. Docker healthcheck verifies the file was updated within the last 60 seconds
3. If the file is stale or missing, the container is marked unhealthy

For manual health checking:
```bash
# Check heartbeat file freshness
docker exec claudevn-compute-1 find /tmp/compute-heartbeat -newermt '-60 seconds'

# Check logs
docker logs claudevn-compute-1
```

## Agent Definitions

Agents are defined in JSON files with the following structure:

```json
{
  "agent_id": "data-analyst",
  "name": "Data Analyst Agent",
  "description": "Analyzes data and creates insights",
  "capabilities": ["data-analysis", "statistics", "visualization"],
  "llm_providers": [
    {
      "provider": "openai",
      "model": "gpt-4",
      "temperature": 0.7,
      "priority": 1
    }
  ],
  "tools": ["python-executor", "pandas-tool"],
  "metadata": {
    "author": "ClaudeVN Team",
    "version": "1.0.0"
  }
}
```

Place agent JSON files in the directory specified by `COMPUTE_AGENTS_DIR`.

## Tool Definitions

Tools are defined in JSON files:

```json
{
  "tool_id": "python-executor",
  "name": "Python Code Executor",
  "description": "Executes Python code safely",
  "function_name": "execute_python",
  "parameters": {
    "type": "object",
    "properties": {
      "code": {
        "type": "string",
        "description": "Python code to execute"
      }
    },
    "required": ["code"]
  },
  "metadata": {
    "timeout": 30,
    "memory_limit": "512MB"
  }
}
```

Place tool JSON files in the directory specified by `COMPUTE_TOOLS_DIR`.

## Registration Flow

When `COMPUTE_REGISTER_ON_STARTUP=true`, the compute engine:

1. **Starts up** and initializes registries
2. **Detects capabilities** (agents, tools, hardware resources)
3. **Registers with Serving** component at `SERVING_URL/api/v1/compute/register`
4. **Starts heartbeat** task to send periodic health updates
5. **Reports status** and capabilities to Serving

If registration fails (e.g., Serving not available), the engine operates in **standalone mode**.

## Heartbeat System

The heartbeat system keeps the Serving component informed of this instance's health:

- **Interval**: Configurable (default 30 seconds)
- **Endpoint**: `POST /api/v1/compute/{instance_id}/health`
- **Payload**: Current status and optional metadata
- **Purpose**: Health monitoring and auto-deregistration on failure

## Hardware Detection

The compute engine automatically detects and reports:

- **CPU cores** (physical and logical)
- **Memory** (total RAM in GB)
- **Storage** (available disk space)
- **GPU** (if enabled and available)
- **Platform** (OS, version, Python version)

This information is sent during registration and available via the `/info/resources` endpoint.

## Development

### Project Structure

```
compute/
├── api/                      # API endpoints
│   ├── health.py            # Health checks
│   ├── info.py              # Instance information
│   ├── agents.py            # Agent management
│   └── tools.py             # Tool management
├── models/                   # Data models
│   └── instance.py          # Instance info models
├── runtime/                  # Execution runtime
│   ├── llm_client.py        # LLM client
│   └── providers/           # LLM provider implementations
├── services/                 # Business logic
│   ├── agent_registry.py    # Agent registry
│   ├── tool_registry.py     # Tool registry
│   └── registration_client.py  # Serving registration
├── app.py                    # Standalone asyncio application (no HTTP server)
├── main.py                   # Entry point
├── config.py                 # Configuration
├── requirements.txt          # Python dependencies
├── start.sh                  # Start script
├── stop.sh                   # Stop script
└── README.md                 # This file
```

### Adding Dependencies

Add to `requirements.txt` and reinstall:

```bash
pip install -r requirements.txt
```

### Testing

#### Unit Tests (Tier 1)

Run fast, mocked unit tests:

```bash
./scripts/run_unit_tests.sh compute/tests/
```

#### Integration Tests (Tier 2)

Run integration tests against running services (requires docker-compose):

```bash
# Start services
docker-compose up -d

# Run integration tests
pytest compute/tests/integration/ -v --run-integration

# Or use the script
./scripts/run_integration_tests.sh
```

The integration tests cover:
- **SSE Connection Flow**: Compute connecting to serving's SSE endpoint
- **Work Assignment Flow**: Receiving work_assigned and spawning Claude Code
- **Event Reporting Flow**: Sending claude_code_started/completed/failed events
- **Conflict Resolution Flow**: Receiving merge_conflict and handling resolution
- **Graceful Shutdown Flow**: Shutdown event handling with active work

See `compute/tests/integration/test_compute_serving_integration.py` for details.

#### Manual Testing

Check the heartbeat file (inside container):

```bash
docker exec claudevn-compute-1 ls -la /tmp/compute-heartbeat
```

Check logs:

```bash
docker logs claudevn-compute-1
```

## Integration with Serving

The compute engine integrates with the Serving component through:

1. **Registration API**: Compute registers itself and its capabilities
2. **Heartbeat API**: Regular health check updates
3. **Capability Discovery**: Serving can query available agents/tools
4. **Task Routing**: (Future) Serving routes tasks to appropriate instances

## Standalone vs. Integrated Mode

### Standalone Mode

- Runs independently without Serving component
- Provides APIs for direct interaction
- Useful for development and testing
- Manual agent/tool management

### Integrated Mode

- Registers with Serving component
- Part of virtual compute pool
- Automatic health monitoring
- Coordinated task execution (future)

## Monitoring and Debugging

### View Logs

```bash
tail -f ../logs/compute.log
```

### Check Status

```bash
# Check heartbeat
docker exec claudevn-compute-1 find /tmp/compute-heartbeat -newermt '-60 seconds'

# Check container health
docker inspect --format='{{.State.Health.Status}}' claudevn-compute-1
```

### Registration Status

Check if registered with Serving:

```bash
curl http://localhost:8002/api/v1/compute
```

## Troubleshooting

### Registration Fails

- Verify Serving component is running: `curl http://localhost:8002/health`
- Check `SERVING_URL` environment variable
- Review logs for connection errors
- Engine will operate in standalone mode if registration fails

### No Agents or Tools Found

- Check `COMPUTE_AGENTS_DIR` and `COMPUTE_TOOLS_DIR` paths
- Verify JSON files are valid and in correct format
- Review startup logs for loading errors

### Dependencies Not Found

```bash
# Reinstall all dependencies
pip install -r requirements.txt

# Install shared library
pip install -e ../shared/
```

## Future Enhancements

- **Agent Execution**: Full agent runtime with LLM integration
- **Tool Execution**: Dynamic tool loading and execution
- **Session Management**: Task execution tracking
- **A2A Protocol**: Cross-instance agent communication
- **Resource Limits**: CPU, memory, and time limits per task
- **Sandboxing**: Secure execution environments
- **Metrics**: Detailed performance and usage metrics

## Version

Current version: 0.1.5

See [VERSION](../VERSION) file and release notes in [docs/releases/](../docs/releases/).

## License

See LICENSE file in repository root.

## Support

- **Documentation**: See [docs/](../docs/) directory
- **Logs**: Check `../logs/compute.log`
- **Health**: Use `/health` and `/stats` endpoints
- **Issues**: Review logs and serving component status

---

**ClaudeVN Compute Engine** - Agent execution runtime for the ClaudeVN platform

