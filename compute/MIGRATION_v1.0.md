# Compute v1.0 Migration Summary

**Date:** 2026-01-30
**Issue:** #152 - Redesign compute/ for Claude Code spawning

## Overview

Migrated compute/ from v0.x (Python agent execution runtime) to v1.0 (lightweight infrastructure that spawns Claude Code CLI instances).

## Architecture Changes

### v0.x (Old)
- Compute was a full execution runtime with:
  - Agent registry and definitions
  - Tool registry and execution
  - LLM provider integrations (OpenAI, Anthropic)
  - Direct REST API registration with Serving
  - Custom agent execution loop

### v1.0 (New)
- Compute is now lightweight infrastructure that:
  - Spawns Claude Code CLI processes for work
  - Connects to Serving via SSE for work assignments
  - Manages Claude Code instance lifecycle
  - Reports lifecycle events back to Serving

## Files Changed

### New Files
- `services/claude_code_spawner.py` - Spawns and manages Claude Code instances

### Modified Files
- `app.py` - Simplified to only initialize spawner, SSE client, and conflict handler
- `config.py` - Removed agent/tool/LLM config, added workspace_path and claude_cli_path
- `services/sse_event_client.py` - Added built-in handlers for work_assigned and work_cancelled
- `api/health.py` - Updated to report spawner status instead of agent/tool counts

### Deleted Files (v0.x runtime)
- `services/agent_executor.py`
- `services/agent_registry.py`
- `services/tool_registry.py`
- `services/registration_client.py`
- `services/serving_client.py`
- `services/observability_client.py`
- `runtime/` (entire directory - LLM providers)
- `api/agents.py`
- `api/tools.py`
- `api/info.py`
- `api/logs.py`

### Kept Files
- `services/conflict_handler.py` - Still needed for merge conflict resolution
- `services/mcp_client.py` - May be used by conflict handler
- `services/coordinating_team_service.py` - Legacy, can be removed later
- `services/tool_executor.py` - Legacy, can be removed later

## Configuration Changes

### Environment Variables (Old)
```bash
COMPUTE_INSTANCE_ID
COMPUTE_AGENTS_DIR
COMPUTE_TOOLS_DIR
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

### Environment Variables (New)
```bash
CLAUDEVN_COMPUTE_ID         # Compute infrastructure ID
CLAUDEVN_API_KEY            # API key for Serving authentication
CLAUDEVN_SERVING_URL        # Serving component URL
CLAUDEVN_CAPABILITIES       # Comma-separated capabilities
CLAUDEVN_RESOURCES_CPU      # CPU cores available
CLAUDEVN_RESOURCES_MEMORY   # Memory available
CLAUDEVN_WORKSPACE_PATH     # Workspace for Claude Code instances
CLAUDEVN_CLAUDE_CLI_PATH    # Path to claude CLI (optional)
```

## Event Flow

### Work Assignment
1. Serving sends `work_assigned` event via SSE
2. `SSEEventClient._handle_work_assigned()` receives it
3. `ClaudeCodeSpawner.spawn()` creates workspace and starts Claude CLI
4. Spawner sends `claude_code_started` event to Serving via HTTP POST

### Work Completion
1. Claude Code process exits
2. `ClaudeCodeSpawner._monitor_process()` detects exit
3. Spawner sends `claude_code_completed` or `claude_code_failed` to Serving

### Work Cancellation
1. Serving sends `work_cancelled` event via SSE
2. `SSEEventClient._handle_work_cancelled()` receives it
3. `ClaudeCodeSpawner.stop()` gracefully stops Claude Code instance

## API Endpoints

### Kept
- `GET /api/v1/health` - Health check (updated for v1.0)
- `GET /api/v1/stats` - Statistics (updated for v1.0)
- `GET /` - Root endpoint (updated to show spawner status)
- `GET /version` - Version info
- `GET /status` - Detailed status (new in v1.0)

### Removed
- All agent endpoints (`/api/v1/agents/*`)
- All tool endpoints (`/api/v1/tools/*`)
- Info endpoint (`/api/v1/info`)
- Logs endpoint (`/api/v1/logs`)

## Testing

To test the new architecture:

1. Start Serving component
2. Start Compute with environment variables:
   ```bash
   export CLAUDEVN_COMPUTE_ID=compute-001
   export CLAUDEVN_API_KEY=your-api-key
   export CLAUDEVN_SERVING_URL=http://localhost:8002
   export CLAUDEVN_WORKSPACE_PATH=./data/workspace
   python compute/app.py
   ```
3. Check health: `curl http://localhost:8003/api/v1/health`
4. Assign work from Serving (SSE will trigger Claude Code spawn)
5. Monitor status: `curl http://localhost:8003/status`

## Migration Path

For existing deployments:

1. **Update environment variables** - Use CLAUDEVN_* prefix
2. **Remove agent/tool directories** - No longer needed
3. **Remove LLM API keys from compute** - Claude Code handles LLM calls
4. **Update Docker compose** - Use new environment variable schema
5. **Verify SSE connection** - Compute must connect to Serving SSE endpoint

## Next Steps

1. Test with actual work assignments from Serving
2. Verify Claude Code spawning and lifecycle management
3. Test conflict resolution flow
4. Update Docker configuration
5. Remove remaining legacy files (coordinating_team_service, tool_executor)

## References

- `docs/design/specifications/compute-registration.md` - Event contracts
- `docs/design/architecture/v1.0-architecture.md` - System architecture
- `serving/services/compute_spawner.py` - Reference implementation
