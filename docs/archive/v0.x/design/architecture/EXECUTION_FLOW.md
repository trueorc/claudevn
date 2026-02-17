# ClaudeVN Execution Flow Architecture

## Overview

This document defines the proper execution flow for ClaudeVN, clarifying the roles of each component and how they interact.

## Component Responsibilities

### 🏪 Marketplace Component
**Role**: Source of truth for agent definitions and discovery

**Responsibilities:**
- Store and catalog agent definitions (capabilities, requirements, metadata)
- Provide agent search and discovery APIs
- Manage agent versioning and updates
- Handle agent access control (who can use which agents)
- Serve agent metadata to compute instances

**Does NOT:**
- Execute agents
- Route tasks
- Manage compute instances

### 🔧 Compute Component
**Role**: Agent execution runtime

**Responsibilities:**
- Execute agents with LLM integration
- Load agent definitions (from local config or marketplace)
- Manage local resources (CPU, memory, GPU)
- Report capabilities to serving component
- Execute tasks assigned by serving

**Does NOT:**
- Discover agents for users (marketplace does this)
- Route tasks to other compute instances (serving does this)
- Store the canonical agent definitions (marketplace does this)

### 🎯 Serving Component
**Role**: Orchestration and coordination hub

**Responsibilities:**
- Register and track compute instances
- Route tasks to appropriate compute instances
- Query marketplace for agent discovery
- Coordinate multi-agent workflows
- Manage session state
- Handle inter-instance communication

**Does NOT:**
- Execute agents (compute does this)
- Store agent definitions (marketplace does this)

## Proper Execution Flow

### Flow 1: Agent Discovery (User finds agents)

```
┌─────────────────────────────────────────────────────────┐
│  1. USER: "What agents can analyze data?"              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  2. SERVING: Query Marketplace                          │
│     GET /api/v1/agents/search                          │
│     { "capabilities": ["data_analysis"] }              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  3. MARKETPLACE: Search catalog                         │
│     • Finds agents with data_analysis capability        │
│     • Returns agent metadata                            │
│     • Includes: description, capabilities, requirements │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  4. SERVING: Check availability                         │
│     • Queries compute registry                          │
│     • Finds which compute instances have these agents   │
│     • Returns agents + availability status              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  5. USER: Receives list of available agents             │
│     • Agent metadata from marketplace                   │
│     • Availability status from serving                  │
│     • Ready to execute                                  │
└─────────────────────────────────────────────────────────┘
```

### Flow 2: Task Execution (User runs an agent)

```
┌─────────────────────────────────────────────────────────┐
│  1. USER: Submit task                                   │
│     POST /api/v1/tasks/submit                          │
│     {                                                   │
│       "agent_id": "data-analyst-v1",                   │
│       "prompt": "Analyze Q4 sales",                    │
│       "context": {...}                                  │
│     }                                                   │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  2. SERVING: Resolve agent                              │
│     A. Query marketplace for agent definition           │
│        • Get full agent metadata                        │
│        • Verify agent exists and is accessible          │
│     B. Find compute instance with this agent            │
│        • Query compute registry                         │
│        • Select instance (load balancing, health)       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  3. SERVING: Route task to compute                      │
│     POST http://compute-instance/agents/execute         │
│     {                                                   │
│       "agent_id": "data-analyst-v1",                   │
│       "prompt": "...",                                  │
│       "context": {...},                                 │
│       "agent_metadata": {                               │
│         "from_marketplace": true,                       │
│         "marketplace_url": "...",                       │
│         "version": "1.0"                                │
│       }                                                 │
│     }                                                   │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  4. COMPUTE: Execute agent                              │
│     A. Load agent definition                            │
│        • Use local config if available                  │
│        • OR fetch from marketplace URL                  │
│     B. Build prompt from task + agent template          │
│     C. Call LLM provider                                │
│     D. Format and return result                         │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  5. SERVING: Return result to user                      │
│     {                                                   │
│       "task_id": "...",                                 │
│       "status": "completed",                            │
│       "output": {...},                                  │
│       "metadata": {                                     │
│         "compute_instance": "compute-001",              │
│         "agent_version": "1.0",                         │
│         "marketplace_source": "..."                     │
│       }                                                 │
│     }                                                   │
└─────────────────────────────────────────────────────────┘
```

### Flow 3: Multi-Agent Business Process

```
┌─────────────────────────────────────────────────────────┐
│  1. USER: Submit business process                       │
│     "Analyze Q4 sales and generate report"             │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  2. SERVING: Plan execution                             │
│     A. Query marketplace for coordinating agent         │
│     B. Execute coordinator to create plan               │
│     Plan returned:                                      │
│       Step 1: Use task-coordinator-v1                   │
│       Step 2: Use data-analyst-v1                       │
│       Step 3: Use content-writer-v1                     │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  3. SERVING: Execute Step 1 (Coordinator)               │
│     • Query marketplace for task-coordinator-v1         │
│     • Find compute instance with this agent             │
│     • Route task to compute                             │
│     • Get execution plan                                │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  4. SERVING: Execute Step 2 (Data Analyst)              │
│     • Query marketplace for data-analyst-v1             │
│     • Find compute instance (may be different)          │
│     • Route task with context from Step 1               │
│     • Get analysis results                              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  5. SERVING: Execute Step 3 (Content Writer)            │
│     • Query marketplace for content-writer-v1           │
│     • Find compute instance                             │
│     • Route task with context from Steps 1 & 2          │
│     • Get final report                                  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  6. SERVING: Aggregate and return results               │
│     • Collect outputs from all steps                    │
│     • Store in session                                  │
│     • Return complete workflow results                  │
└─────────────────────────────────────────────────────────┘
```

## Agent Definition Strategy

### Strategy 1: Pre-configured Agents (Current Implementation)

**How it works:**
- Compute instances have agent definitions in local JSON files
- Agents are "baked in" to the compute instance
- Compute registers with serving, advertising which agents it has

**Pros:**
- Fast - no need to fetch agent definitions
- Works offline
- Simple deployment

**Cons:**
- Agent updates require compute restart
- Each compute instance has independent agent configs
- Marketplace is bypassed in execution

**Use case:** 
- Development/testing
- Specialized compute instances with fixed agents
- High-security environments (no external fetches)

### Strategy 2: Marketplace-sourced Agents (Recommended for Production)

**How it works:**
- Marketplace is source of truth for all agent definitions
- Compute instances fetch agent definitions from marketplace
- Compute can cache agents locally
- Compute registers capabilities based on what it CAN run (not what it HAS)

**Pros:**
- Centralized agent management
- Easy updates (no compute restart needed)
- Consistent agent definitions across all compute instances
- Marketplace access control applies

**Cons:**
- Requires marketplace connectivity
- Slight overhead to fetch definitions
- More complex deployment

**Use case:**
- Production deployments
- Multi-tenant environments
- Dynamic agent scaling

### Strategy 3: Hybrid (Best of Both)

**How it works:**
- Compute has some agents pre-configured (critical/common ones)
- Can fetch additional agents from marketplace on-demand
- Falls back to pre-configured if marketplace unavailable

**Pros:**
- Fast for common agents
- Flexible for new/specialized agents
- Works even if marketplace is down (degraded mode)

**Cons:**
- Most complex to implement
- Need cache invalidation strategy

**Use case:**
- Enterprise deployments
- High-availability requirements

## Current Implementation vs Ideal

### What We Built (Mock E2E)

```
USER
  ↓
SERVING (task routing only)
  ↓
COMPUTE (has local agent JSONs)
  ↓
MOCK LLM
  ↓
RESULT

❌ Marketplace not in flow
✅ Simple and fast for testing
✅ Works offline
```

### What We Should Build (Full Integration)

```
USER
  ↓
SERVING (orchestration)
  ↓ (query agent metadata)
MARKETPLACE (agent definitions)
  ↓ (return metadata)
SERVING (find compute + route task)
  ↓
COMPUTE (execute with LLM)
  ↓
MOCK or REAL LLM
  ↓
RESULT (via SERVING)

✅ Marketplace integrated
✅ Proper separation of concerns
✅ Production-ready architecture
```

## Migration Path

### Phase 1: Current (Mock Testing) ✅ DONE
- Agents defined locally in compute
- Serving routes to compute
- Marketplace separate
- Works for testing

### Phase 2: Marketplace Integration (NEXT)
- Serving queries marketplace for agent discovery
- User can search agents via serving → marketplace
- Still use local agent configs for execution
- Marketplace becomes discoverable catalog

### Phase 3: Marketplace-sourced Execution
- Compute fetches agent definitions from marketplace
- Centralized agent management
- Dynamic agent loading
- Full production architecture

### Phase 4: Advanced Features
- Agent versioning and updates
- Multi-marketplace support
- Agent marketplace (publish/subscribe)
- Dynamic agent deployment

## Recommendations

### For Development/Testing (Now)
Keep current architecture:
- ✅ Fast iteration
- ✅ No dependencies
- ✅ Simple debugging

### For Production (Future)
Implement marketplace integration:
- Marketplace as source of truth
- Serving queries marketplace for discovery
- Compute can fetch or use pre-configured agents
- Proper access control

### Implementation Priority

1. **High Priority**: Clean up old compute registrations
2. **High Priority**: Add marketplace query to serving's task submission
3. **Medium Priority**: Agent discovery via marketplace
4. **Medium Priority**: Compute fetch from marketplace (optional)
5. **Low Priority**: Dynamic agent deployment

## Decision Points

### Question 1: Where should agent definitions live?

**Options:**
A. **Local on compute** (current)
   - Pro: Fast, offline, simple
   - Con: Hard to update, inconsistent

B. **Marketplace only**
   - Pro: Centralized, consistent, easy updates
   - Con: Requires connectivity, fetch overhead

C. **Hybrid** (recommended)
   - Pro: Fast + flexible + resilient
   - Con: More complex

**Recommendation**: Start with A, migrate to C

### Question 2: Should compute register agents or capabilities?

**Options:**
A. **Register specific agents** (current)
   - "I have data-analyst-v1 and content-writer-v1"
   - Pro: Explicit, easy to route
   - Con: Rigid, requires re-registration for new agents

B. **Register capabilities**
   - "I can run Python agents with <4GB memory"
   - Pro: Flexible, dynamic agent loading
   - Con: More complex routing logic

**Recommendation**: A for now, B for advanced deployments

### Question 3: How should serving find agents?

**Options:**
A. **Query compute registry only** (current)
   - Ask: "Which compute has data-analyst-v1?"
   - Pro: Simple, fast
   - Con: Limited discovery, no metadata

B. **Query marketplace + compute**
   - Ask marketplace: "What data analysis agents exist?"
   - Ask compute: "Who can run data-analyst-v1?"
   - Pro: Full discovery, rich metadata
   - Con: Two queries

**Recommendation**: Implement B for better user experience

## Next Steps

1. **Clean up test data**: Remove old compute registrations
2. **Document current flow**: Update test script to explain what happens
3. **Design marketplace integration**: Spec out serving ↔ marketplace queries
4. **Implement discovery**: Add agent search via marketplace
5. **Optional**: Implement marketplace-sourced agent execution

---

**Status**: Architecture defined, ready for discussion
**Decision needed**: Which strategy to implement next?

