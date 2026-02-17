# ServingClient Implementation - Phase 2

## Overview

This document describes the implementation of the `ServingClient` in the Compute module, which enables agent definitions to be fetched from Marketplace via Serving with caching support.

**Implementation Date**: December 2024  
**Component**: Compute  
**Related**: [Agent Proxy Implementation](./AGENT_PROXY_IMPLEMENTATION.md)

## Architecture

```
┌──────────┐     ServingClient      ┌──────────┐     MarketplaceClient    ┌─────────────┐
│ Compute  │────────────────────────→│ Serving  │─────────────────────────→│ Marketplace │
│          │   GET /api/v1/agents/  │  (Proxy) │   GET /api/v1/agents/   │             │
└──────────┘   {agent_id}            └──────────┘   {agent_id}             └─────────────┘
     ↓
  ┌──────┐
  │ Cache│  (5-minute TTL)
  └──────┘
     ↓
  ┌──────────────┐
  │ Local JSON   │  (Fallback)
  └──────────────┘
```

## Components

### 1. AgentCache

**File**: `compute/services/serving_client.py`

Simple in-memory TTL cache for agent definitions.

**Features**:
- Configurable TTL (default 300 seconds / 5 minutes)
- Thread-safe async operations
- Automatic expiration

**Usage**:
```python
cache = AgentCache(ttl_seconds=300)
await cache.set("agent-id", agent_definition)
agent = await cache.get("agent-id")  # None if expired or not found
```

### 2. ServingClient

**File**: `compute/services/serving_client.py`

Client for fetching agent definitions from Serving component.

**Features**:
- Fetch individual agents by ID
- Search agents by capabilities/tags
- Automatic caching with TTL
- Graceful error handling
- Connection failure handling

**Initialization**:
```python
client = ServingClient(
    serving_url="http://localhost:8002",
    cache_ttl_seconds=300,
    timeout_seconds=10.0
)
```

**Methods**:
- `fetch_agent(agent_id, use_cache=True)` - Get single agent
- `search_agents(capabilities, tags, search_text, limit)` - Search agents

### 3. AgentExecutor Integration

**File**: `compute/services/agent_executor.py`

Modified to use ServingClient as primary agent source.

**Fetch Order**:
1. Check ServingClient cache
2. Fetch from Serving/Marketplace via ServingClient
3. Fallback to local JSON registry
4. Fail if not found

**Code**:
```python
# Try serving/marketplace first
if self.serving_client:
    logger.debug(f"Fetching agent {agent_id} from serving/marketplace")
    agent = await self.serving_client.fetch_agent(agent_id)

# Fallback to local
if not agent:
    logger.debug(f"Fetching agent {agent_id} from local registry")
    agent = self.agent_registry.get_agent(agent_id)
    if agent:
        logger.info(f"Using agent {agent_id} from local registry")
else:
    logger.info(f"Using agent {agent_id} from marketplace")
```

## Data Conversion

The marketplace agent format differs from compute's internal format. The conversion handles:

### Field Mappings

| Marketplace | Compute AgentDefinition |
|------------|------------------------|
| `id` | `agent_id` |
| `name` | `name` |
| `description` | `description` |
| `capabilities` | `capabilities` |
| `tools` | `tools` |
| `language_model` (string or dict) | `llm_providers` (list of dicts) |

### Language Model Handling

Marketplace stores `language_model` in two formats:

**String format** (simple):
```json
{
  "language_model": "gpt-4"
}
```

**Dict format** (full config):
```json
{
  "language_model": {
    "provider": "openai",
    "model": "gpt-4",
    "temperature": 0.7
  }
}
```

Both are converted to compute's `llm_providers` format:
```python
llm_providers = [{
    "provider": "openai",  # inferred from model name if string
    "model": "gpt-4",
    "temperature": 0.7,
    "priority": 1
}]
```

### Metadata Fields

Optional marketplace fields added to metadata:
- `version`
- `agent_type`
- `complexity_level`
- `estimated_duration`
- `publisher_id`
- `organization_id`
- `source_marketplace` (added by serving proxy)

## Configuration

### Environment Variables

**In compute/app.py**:
```bash
SERVING_URL=http://localhost:8002  # Serving endpoint
AGENT_CACHE_TTL=300                # Cache TTL in seconds (5 minutes)
```

### Initialization

**File**: `compute/app.py` (lifespan function)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... other initialization ...
    
    import os as os_module  # Must be in lifespan scope
    cache_ttl = int(os_module.getenv('AGENT_CACHE_TTL', '300'))
    serving_client = initialize_serving_client(
        serving_url=config.serving_url,
        cache_ttl_seconds=cache_ttl
    )
    
    # Pass to AgentExecutor
    app.state.agent_executor = AgentExecutor(
        tool_registry=tool_registry,
        agent_registry=agent_registry,
        serving_client=serving_client,  # NEW
        observability_client=observability_client
    )
```

## Testing

### Test Marketplace Fetch

```bash
# Execute agent that exists in marketplace
curl -X POST http://localhost:8003/agents/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "process-mapper-v1",
    "prompt": "Map the employee onboarding process"
  }'
```

Expected logs:
```
INFO - Fetching agent process-mapper-v1 from serving/marketplace
INFO - HTTP Request: GET http://localhost:8002/api/v1/agents/process-mapper-v1 "HTTP/1.1 200 OK"
INFO - Fetched agent process-mapper-v1 from serving
INFO - Using agent process-mapper-v1 from marketplace
```

### Test Cache

Execute the same agent twice within 5 minutes:

**First execution**:
```
INFO - HTTP Request: GET http://localhost:8002/api/v1/agents/process-mapper-v1
INFO - Fetched agent process-mapper-v1 from serving
```

**Second execution** (within TTL):
```
INFO - Using agent process-mapper-v1 from marketplace
```
No HTTP request = cache hit!

### Test Local Fallback

```bash
# Execute agent that only exists in local JSON
curl -X POST http://localhost:8003/agents/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data-analyst-v1",
    "prompt": "Analyze sales data"
  }'
```

Expected logs:
```
WARNING - Agent data-analyst-v1 not found in marketplace
INFO - Using agent data-analyst-v1 from local registry
```

## Error Handling

### Connection Errors

If Serving is unreachable:
```
ERROR - Cannot connect to serving at http://localhost:8002: ...
```
→ Falls back to local registry

### Timeout

If request takes too long (>10s default):
```
ERROR - Timeout fetching agent {agent_id} from serving
```
→ Falls back to local registry

### HTTP Errors

If Serving returns error (5xx, etc.):
```
ERROR - HTTP error fetching agent {agent_id}: 503 - No marketplace available
```
→ Falls back to local registry

### Conversion Errors

If agent data format is invalid:
```
WARNING - Failed to convert agent: ...
```
→ Skips that agent in search results

## Benefits

### 1. Centralized Agent Management
- Agents managed in Marketplace
- Compute instances automatically get updates
- No manual sync needed

### 2. Performance
- 5-minute cache reduces network calls
- Sub-millisecond cache hits
- Configurable TTL for tuning

### 3. Resilience
- Graceful fallback to local agents
- Continues working if Serving/Marketplace down
- No hard dependencies

### 4. Multi-Marketplace Support
- Serving can aggregate from multiple marketplaces
- Compute doesn't need to know about marketplace topology
- Transparent to execution logic

## Monitoring

### Key Metrics

Watch for these in logs:

**Cache Performance**:
```bash
grep "Fetched agent.*from serving" logs/compute.log | wc -l  # Cache misses
grep "Using agent.*from marketplace" logs/compute.log | wc -l  # Total marketplace usage
```

**Fallback Rate**:
```bash
grep "Using agent.*from local registry" logs/compute.log | wc -l
```

**Error Rate**:
```bash
grep "Error fetching agent" logs/compute.log | wc -l
```

### Health Indicators

**Healthy**:
- First request: HTTP 200 from serving
- Subsequent requests: No HTTP (cache hit)
- Marketplace agents execute successfully

**Degraded**:
- High fallback rate (>50%)
- Frequent timeouts or connection errors
- Cache misses even within TTL

**Unhealthy**:
- All agents failing to execute
- Continuous connection errors
- No agents found (marketplace + local)

## Future Enhancements

### Planned Improvements

1. **Cache Warming**: Pre-fetch popular agents on startup
2. **Metrics**: Expose cache hit rate, fetch latency via /metrics
3. **Background Refresh**: Update cache before expiry
4. **Distributed Cache**: Redis/Memcached for multi-compute deployments
5. **Smart Fallback**: Use cached version if serving unavailable (even if expired)

### Configuration Extensions

```python
# Future config options
AGENT_CACHE_TTL=300              # Current
AGENT_CACHE_MAX_SIZE=1000        # Planned
AGENT_CACHE_PRELOAD=true         # Planned
AGENT_CACHE_BACKEND=redis        # Planned
```

## Related Documentation

- [Agent Proxy Implementation](./AGENT_PROXY_IMPLEMENTATION.md) - Phase 1 (Serving side)
- [Compute Architecture](../design/architecture/compute.md)
- [Agent Registry](../guides/agent-registry.md)

## Troubleshooting

### Problem: All agents using local fallback

**Symptom**: Logs show "Using agent X from local registry" for all agents

**Check**:
```bash
# 1. Is marketplace registered?
curl http://localhost:8002/api/v1/marketplaces

# 2. Can serving reach marketplace?
curl http://localhost:8002/api/v1/agents/process-mapper-v1

# 3. Is SERVING_URL correct?
grep SERVING_URL compute/.env
```

### Problem: Cache not working

**Symptom**: Every execution shows HTTP request in logs

**Check**:
```bash
# 1. Is AGENT_CACHE_TTL set?
grep AGENT_CACHE_TTL compute/.env

# 2. Are requests within TTL?
tail -100 logs/compute.log | grep "process-mapper-v1"
# Check timestamps

# 3. Is use_cache=True?
# Check AgentExecutor.execute_agent() call
```

### Problem: Conversion errors

**Symptom**: `'str' object has no attribute 'get'` or similar

**Cause**: Marketplace agent format incompatible

**Fix**: Update `_convert_to_agent_definition()` to handle new fields

## Implementation Checklist

- [x] Create AgentCache class with TTL
- [x] Create ServingClient class
- [x] Add fetch_agent() method
- [x] Add search_agents() method
- [x] Implement data conversion (_convert_to_agent_definition)
- [x] Handle language_model string format
- [x] Handle language_model dict format
- [x] Initialize ServingClient in app.py
- [x] Pass ServingClient to AgentExecutor
- [x] Update AgentExecutor to use ServingClient first
- [x] Add local registry fallback
- [x] Add error handling (connection, timeout, HTTP)
- [x] Test marketplace fetch
- [x] Test cache behavior
- [x] Test local fallback
- [x] Write documentation
- [x] Commit and push changes

## Summary

The ServingClient implementation enables Compute to fetch agents from Marketplace via Serving with:
- **Caching**: 5-minute TTL reduces network overhead
- **Resilience**: Graceful fallback to local agents
- **Transparency**: Minimal changes to execution logic
- **Flexibility**: Supports multiple marketplaces via Serving

This completes the agent fetching architecture: Compute → Serving (proxy) → Marketplace(s).
