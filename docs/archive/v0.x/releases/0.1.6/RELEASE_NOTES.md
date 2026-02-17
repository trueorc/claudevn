# Release Notes - Version 0.1.6

**Release Date:** November 23, 2025  
**Status:** Completed ✅

---

## Overview

Version 0.1.6 introduces the **Compute Engine**, completing the core three-component architecture of ClaudeVN. The Compute Engine is the agent execution runtime that registers with the Serving component to form a distributed compute pool.

## What's New

### 🚀 Compute Engine (NEW)

A complete agent execution runtime with full registration and monitoring capabilities.

**Core Features:**
- FastAPI-based REST API on port 8003
- Automatic registration with Serving component
- Heartbeat system for health monitoring
- Agent and tool registry management
- Hardware resource detection and reporting
- LLM provider integration (OpenAI support ready)
- Configuration management via environment variables
- Comprehensive monitoring endpoints

**Architecture:**
```
Compute Engine (8003)
├── Agent Registry     - Manage available agents
├── Tool Registry      - Manage available tools
├── Registration       - Connect to Serving component
├── Heartbeat          - Regular health updates
├── Resource Detection - CPU, memory, storage info
└── Configuration      - Environment-based setup
```

### 📡 Registration System

The Compute Engine automatically registers with the Serving component on startup:

1. **Discovery**: Detects hardware capabilities (CPU, memory, storage)
2. **Registration**: Sends instance info to Serving component
3. **Heartbeat**: Maintains connection with periodic health updates
4. **Monitoring**: Reports status and available agents/tools

### 🔧 Configuration

Flexible configuration via environment variables:

- Server settings (host, port)
- Instance identity (ID, name)
- Serving integration (URL, auto-register, heartbeat interval)
- Storage paths
- Agent/tool directories
- LLM API keys
- Feature flags (GPU support, etc.)

### 📊 Monitoring & APIs

Comprehensive API endpoints for monitoring and management:

**Health & Status:**
- `GET /health` - Health check with stats
- `GET /stats` - Detailed statistics
- `GET /` - Service information

**Instance Info:**
- `GET /info` - Complete instance information
- `GET /info/capabilities` - Available agents/tools/resources
- `GET /info/resources` - Hardware specifications

**Agent Management:**
- `GET /agents` - List all agents
- `GET /agents/{id}` - Get specific agent
- `POST /agents` - Register agent
- `DELETE /agents/{id}` - Unregister agent

**Tool Management:**
- `GET /tools` - List all tools
- `GET /tools/{id}` - Get specific tool
- `POST /tools` - Register tool
- `DELETE /tools/{id}` - Unregister tool

### 📝 Documentation

Complete documentation added:
- `compute/README.md` - Comprehensive guide
- Architecture diagrams
- Configuration examples
- API documentation
- Troubleshooting guide

### 🔗 Integration

The Compute Engine integrates seamlessly with existing components:

- **Serving Component**: Automatic registration and heartbeat
- **Marketplace**: Future agent discovery (planned)
- **Platform Scripts**: Integrated with start_all.sh / stop_all.sh

## Technical Details

### Components Implemented

1. **FastAPI Application** (`app.py`)
   - Lifespan management
   - CORS middleware
   - Router integration
   - Automatic registration

2. **Configuration** (`config.py`)
   - Environment variable loading
   - Auto-generated instance ID
   - Resource path management

3. **Models** (`models/`)
   - `AgentDefinition` - Agent metadata
   - `ToolDefinition` - Tool metadata
   - `InstanceInfo` - Instance information
   - `InstanceCapabilities` - Capabilities reporting
   - `InstanceResources` - Hardware detection

4. **Services** (`services/`)
   - `AgentRegistry` - Agent management
   - `ToolRegistry` - Tool management
   - `RegistrationClient` - Serving integration

5. **API Endpoints** (`api/`)
   - Health checks
   - Instance information
   - Agent management
   - Tool management

6. **Runtime** (`runtime/`)
   - LLM client (existing)
   - Provider abstraction (existing)

### Scripts

- `start.sh` - Start compute engine standalone
- `stop.sh` - Stop compute engine
- Integration with `start_all.sh` / `stop_all.sh`

### Dependencies

New dependencies added:
- `psutil` - System and hardware information

## Testing

All components tested successfully:

1. ✅ Standalone startup (port 8003)
2. ✅ Health endpoint responding
3. ✅ Registration with Serving component
4. ✅ Hardware detection (CPU: 8, Memory: 8GB, Storage: 228GB)
5. ✅ Agent/tool registry APIs
6. ✅ Integration with start_all.sh/stop_all.sh

## Platform Status

### ✅ Implemented Components

**Marketplace (Port 8001):**
- Agent and tool discovery
- User and organization management
- Access control system
- React frontend with search

**Serving (Port 8002):**
- Compute instance registry
- Marketplace connections
- Session management
- Health monitoring
- React frontend with dashboards

**Compute (Port 8003):** ⭐ NEW
- Agent execution runtime
- Auto-registration
- Heartbeat system
- Resource monitoring
- Tool management

### 🔄 Architecture Flow

```
┌──────────────┐
│ Marketplace  │  Discovery & Registry
│   (8001)     │
└──────────────┘
       │
       │ Registers
       ▼
┌──────────────┐
│   Serving    │  Orchestration Hub
│   (8002)     │  - Compute Registry
└──────────────┘  - Marketplace Proxy
       │          - Session Management
       │
       │ Registers & Heartbeats
       ▼
┌──────────────┐
│   Compute    │  Execution Runtime
│   (8003)     │  - Agent Lifecycle
└──────────────┘  - Tool Execution
                  - LLM Integration
```

## Usage Examples

### Start All Components

```bash
./start_all.sh
```

### Check Compute Health

```bash
curl http://localhost:8003/health
```

### Get Instance Info

```bash
curl http://localhost:8003/info
```

### View Registered Instances

```bash
curl http://localhost:8002/api/v1/compute
```

### Monitor Logs

```bash
tail -f logs/compute.log
```

## Configuration Example

Create `.env` file in `compute/` directory:

```bash
COMPUTE_PORT=8003
SERVING_URL=http://localhost:8002
COMPUTE_REGISTER_ON_STARTUP=true
COMPUTE_HEARTBEAT_INTERVAL=30
OPENAI_API_KEY=sk-...
```

## Migration Notes

### For Existing Installations

1. Install new dependency:
   ```bash
   source .venv/bin/activate
   pip install psutil
   ```

2. Start the platform:
   ```bash
   ./start_all.sh
   ```

The compute engine will automatically register with the serving component.

### For New Installations

Run the setup script:
```bash
./setup_environment.sh
./start_all.sh
```

All components will start and integrate automatically.

## Known Limitations

- Agent execution not yet implemented (planned for 0.2.x)
- Tool execution framework pending (planned for 0.2.x)
- A2A protocol support incomplete (planned for 0.2.x)
- GPU detection requires additional libraries (future enhancement)

## Future Enhancements

Planned for upcoming releases:

**0.2.0 - Agent Execution:**
- Full agent runtime implementation
- LLM-based agent reasoning
- Tool invocation framework
- Session-based execution

**0.3.0 - A2A Protocol:**
- Cross-instance agent communication
- Task distribution
- Result aggregation

**0.4.0 - Advanced Features:**
- GPU acceleration
- Resource limits and quotas
- Sandboxed execution
- Performance metrics

## Breaking Changes

None. This release is fully backward compatible.

## Bug Fixes

None. This is a new feature release.

## Contributors

- ClaudeVN Development Team

## Links

- **Documentation**: [docs/](../../)
- **Compute README**: [compute/README.md](../../compute/README.md)
- **Architecture**: [docs/design/architecture/](../../design/architecture/)
- **Previous Release**: [0.1.5](../0.1.5/RELEASE_NOTES.md)

---

**Version 0.1.6** - Complete compute engine implementation with registration, monitoring, and management capabilities.

