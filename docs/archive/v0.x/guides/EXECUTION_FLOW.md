# ClaudeVN Execution Flow - Quick Summary

## 📋 Current Situation

You're seeing **5 registered compute instances** when you expected 1. This happens because:

1. Each time compute starts, it generates a new `instance_id` (includes hostname + port)
2. Old registrations aren't automatically cleaned up
3. Serving persists registrations across restarts

## 🧹 Clean Up Old Registrations

```bash
# Option 1: Use cleanup script
./scripts/cleanup_registrations.sh

# Option 2: Manual cleanup
curl -X DELETE http://localhost:8002/api/v1/compute/{instance-id}

# Option 3: Reset serving data
rm -rf data/serving/data/registry/compute/*.json
cd serving && ./stop.sh && ./start.sh
```

## 🎯 Component Roles (What Does What?)

### Marketplace 🏪
**Purpose**: Source of truth for agent definitions

**What it does:**
- Stores agent metadata (capabilities, requirements, description)
- Provides agent search/discovery
- Manages agent access control
- Serves agent definitions to other components

**What it DOESN'T do:**
- Execute agents ❌
- Route tasks ❌
- Track compute instances ❌

### Compute 🔧
**Purpose**: Execute agents

**What it does:**
- Runs agents with LLM integration
- Has agent definitions (local JSON files)
- Executes tasks assigned by serving
- Reports capabilities to serving

**What it DOESN'T do:**
- Discover agents for users ❌ (marketplace does this)
- Route tasks ❌ (serving does this)
- Store canonical agent definitions ❌ (marketplace does this)

### Serving 🎯
**Purpose**: Orchestrate everything

**What it does:**
- Tracks available compute instances
- Routes tasks to appropriate compute
- Queries marketplace for agent discovery
- Coordinates multi-agent workflows
- Manages sessions and state

**What it DOESN'T do:**
- Execute agents ❌ (compute does this)
- Store agent definitions ❌ (marketplace does this)

## 🔄 Proper Execution Flow

### Flow 1: Simple Task Execution

```
┌──────────┐
│   USER   │  "Analyze my Q4 sales data"
└────┬─────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING COMPONENT                              │
│  1. Receive task request                        │
│  2. Find agent "data-analyst-v1" in registry   │
│  3. Select compute instance with that agent     │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  COMPUTE INSTANCE                               │
│  4. Load agent definition (from local JSON)     │
│  5. Build prompt from task + agent template     │
│  6. Call LLM (Mock or Real)                     │
│  7. Format result                               │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING COMPONENT                              │
│  8. Receive result from compute                 │
│  9. Add metadata (which instance, timing, etc)  │
│  10. Return to user                             │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌──────────┐
│   USER   │  Receives: Analysis with insights
└──────────┘
```

### Flow 2: With Marketplace Integration (Future)

```
┌──────────┐
│   USER   │  "What agents can analyze data?"
└────┬─────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING COMPONENT                              │
│  1. Query marketplace for agents                │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  MARKETPLACE COMPONENT                          │
│  2. Search agent catalog                        │
│  3. Return matching agents with metadata        │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING COMPONENT                              │
│  4. Check which compute instances have agents   │
│  5. Return agents + availability to user        │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌──────────┐
│   USER   │  "I'll use data-analyst-v1"
└────┬─────┘
     │
     ▼
   (Continue with execution flow from Flow 1)
```

### Flow 3: Multi-Agent Process

```
┌──────────┐
│   USER   │  "Analyze Q4 and create report"
└────┬─────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING - Step 1: Coordinator Agent            │
│  • Find coordinator agent                       │
│  • Route to compute                             │
│  • Get execution plan                           │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING - Step 2: Data Analyst Agent           │
│  • Find data analyst agent                      │
│  • Route to compute (may be different instance) │
│  • Pass context from Step 1                     │
│  • Get analysis results                         │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────┐
│  SERVING - Step 3: Content Writer Agent         │
│  • Find content writer agent                    │
│  • Route to compute                             │
│  • Pass context from Steps 1 & 2                │
│  • Get final report                             │
└────┬────────────────────────────────────────────┘
     │
     ▼
┌──────────┐
│   USER   │  Receives: Complete report
└──────────┘
```

## 📊 Current Implementation vs Ideal

### What We Built (Current)

```
Agents: Local JSON files in compute/data/compute/agents/
Flow:   USER → SERVING → COMPUTE → LLM → RESULT
✅ Fast and simple
✅ Works for testing
❌ Marketplace not integrated
❌ Agent discovery limited
```

### What We Should Have (Ideal)

```
Agents: Defined in MARKETPLACE
Flow:   USER → SERVING ⟷ MARKETPLACE → COMPUTE → LLM → RESULT
✅ Centralized agent management
✅ Full discovery capabilities
✅ Easy agent updates
✅ Proper separation of concerns
```

## 🛠️ Three Strategies for Agent Definitions

### Strategy 1: Pre-configured (Current) ✅

**Agents stored in**: `compute/data/compute/agents/*.json`

**Pros:**
- ✅ Fast - no fetching needed
- ✅ Works offline
- ✅ Simple for testing

**Cons:**
- ❌ Hard to update (restart needed)
- ❌ Inconsistent across instances
- ❌ Marketplace bypassed

**Use case:** Development, testing, specialized nodes

### Strategy 2: Marketplace-sourced (Future) 🎯

**Agents stored in**: Marketplace only

**How it works:**
1. Compute registers with serving (advertises capabilities, not specific agents)
2. When task arrives, compute fetches agent definition from marketplace
3. Compute caches agent definition locally
4. Execute with fetched definition

**Pros:**
- ✅ Centralized management
- ✅ Easy updates (no restart)
- ✅ Consistent definitions
- ✅ Access control

**Cons:**
- ❌ Requires connectivity
- ❌ Fetch overhead
- ❌ More complex

**Use case:** Production, multi-tenant, dynamic scaling

### Strategy 3: Hybrid (Recommended) 🌟

**Agents stored in**: Both compute (cache) and marketplace (source of truth)

**How it works:**
1. Compute has common agents pre-configured
2. Can fetch additional agents from marketplace
3. Falls back to local if marketplace unavailable

**Pros:**
- ✅ Fast for common agents
- ✅ Flexible for new agents
- ✅ Resilient (works offline)

**Cons:**
- ❌ Most complex
- ❌ Cache invalidation needed

**Use case:** Enterprise production

## 🎯 Recommended Next Steps

### Immediate (Fix your test environment)

1. **Clean up old registrations:**
   ```bash
   ./scripts/cleanup_registrations.sh
   ```

2. **Restart everything clean:**
   ```bash
   ./stop_all.sh
   rm -rf data/serving/data/registry/compute/*.json
   ./start_all.sh
   ```

3. **Verify single registration:**
   ```bash
   curl http://localhost:8002/api/v1/compute | python3 -m json.tool
   ```

### Short Term (Improve current flow)

1. **Add marketplace query to serving**
   - When task submitted, query marketplace for agent metadata
   - Return richer information to user
   - Still execute with local agent configs

2. **Improve test output**
   - Show which compute instance handled each task
   - Display agent source (local config)
   - Better error messages

### Medium Term (Marketplace integration)

1. **Agent discovery via marketplace**
   - Serving provides agent search
   - Queries marketplace for catalog
   - Cross-references with compute availability

2. **Optional: Marketplace-sourced execution**
   - Compute can fetch agent definitions
   - Centralized agent management
   - Dynamic agent loading

## 💡 Key Insights

1. **Multiple registrations are normal** if you restart compute multiple times. Clean them up periodically.

2. **Current architecture works** for testing but bypasses marketplace in execution flow.

3. **Marketplace should be** the source of truth for agent definitions, but compute can cache for performance.

4. **Serving is the hub** that coordinates everything - it should query marketplace for discovery and compute for execution.

5. **Each component has a clear role** - don't mix responsibilities:
   - Marketplace = Catalog
   - Compute = Execution
   - Serving = Orchestration

## 📖 Full Documentation

For complete architectural details, see:
- **docs/design/architecture/EXECUTION_FLOW.md** - Full architecture doc
- **MOCK_E2E_GUIDE.md** - Testing guide
- **IMPLEMENTATION_SUMMARY.md** - What was built

---

**Quick Actions:**
```bash
# Clean up old registrations
./scripts/cleanup_registrations.sh

# Restart clean
./stop_all.sh && rm -rf data/serving/data/registry/compute/*.json && ./start_all.sh

# Run test
./test_mock_e2e.sh
```

