# Facilitated Process Integration with Existing Platform

## Overview

This document explains how the **Facilitated Process Architecture** (v0.2.0) integrates with the existing **Marketplace**, **Serving**, and **Compute** components built in v0.1.x.

**Key Insight**: The coordinating agents (Process Mapper, Agent Selector, Activity Facilitator, etc.) and domain agents (DataAnalyst, ContentWriter, etc.) **ALL run in Compute instances**. Serving is a **lightweight routing broker** that coordinates them through message passing. All heavy work (LLM calls, memory) happens in Compute.

---

## Current Platform Architecture (v0.1.8)

### What's Already Built

```
┌─────────────────────────────────────────────────────────┐
│  MARKETPLACE COMPONENT (Port 8001) - ✅ COMPLETE        │
│  • Agent catalog and discovery                          │
│  • Capability-based search                              │
│  • Access control system                                │
│  • User/Organization management                         │
│  • Agent metadata storage                               │
│  • React frontend                                       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  SERVING COMPONENT (Port 8002) - ⚠️ PARTIAL             │
│  ✅ Session management (CRUD, context, storage)         │
│  ✅ Compute instance registry (v0.1.4)                  │
│  ✅ Basic pipeline execution (v0.1.8)                   │
│  ✅ Task routing to compute                             │
│  ❌ Message routing for coordinating agents (v0.2.0)    │
│  ❌ Event bus for agent coordination                    │
│  ❌ Process map storage                                 │
│                                                          │
│  KEY: Serving does NOT execute agents - it routes!      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  COMPUTE COMPONENT (Port 8003+) - ✅ MOSTLY COMPLETE    │
│  ✅ Agent execution engine (for ALL agents)             │
│  ✅ LLM integration (OpenAI, Anthropic, Mock)           │
│  ✅ Local agent definitions (specialized)               │
│  ✅ Registration with Serving                           │
│  ✅ Heartbeat maintenance                               │
│  ❌ Coordinating agent definitions (v0.2.0)             │
│                                                          │
│  KEY: ALL agents run here (coordinating + specialized)  │
└─────────────────────────────────────────────────────────┘
```

---

## Where Coordinating Agents Live

### ALL Agents → Compute Components

**CRITICAL**: Both coordinating and specialized agents run in Compute instances. Serving is a lightweight broker that routes messages between them.

```python
# compute/data/compute/agents/

# Coordinating agents (NEW in v0.2.0)
├── coordinating/
│   ├── process-mapper-agent.json
│   ├── agent-selector-agent.json
│   ├── activity-facilitator-agent.json
│   ├── consistency-manager-agent.json
│   ├── progress-reporter-agent.json
│   └── result-synthesizer-agent.json

# Specialized agents (EXISTING)
├── specialized/
    ├── data-analyst-agent.json
    ├── content-writer-agent.json
    ├── code-reviewer-agent.json
    └── ... (domain agents)
```

**Why ALL agents in Compute?**
- **Heavy LLM use**: Coordinating agents use LLMs extensively for planning, reasoning, synthesis
- **Memory intensive**: Process maps, facilitation history, consistency checking
- **Resource isolation**: Serving stays lightweight - just routing and storage
- **Scalability**: Can dedicate compute instances to coordinating vs specialized work
- **Consistent model**: All agents execute the same way, just different definitions

**Deployment Options:**

**Option 1: Dedicated Coordinating Instance**
```
Compute-001 (Coordinating)     Compute-002 (Specialized)
├── Process Mapper             ├── DataAnalyst
├── Agent Selector             ├── ContentWriter
├── Activity Facilitator       ├── CodeReviewer
├── Consistency Manager        └── ...
├── Progress Reporter
└── Result Synthesizer
```

**Option 2: Distributed (All-in-One)**
```
Compute-001 (Mixed)
├── Process Mapper (coordinating)
├── Activity Facilitator (coordinating)
├── DataAnalyst (specialized)
└── ContentWriter (specialized)
```

**Option 3: Fully Distributed**
```
Compute-001: Process Mapper + Agent Selector
Compute-002: Activity Facilitator + Consistency Manager  
Compute-003: Progress Reporter + Result Synthesizer
Compute-004: DataAnalyst, ContentWriter, etc.
```

---

## Integration Architecture

### Complete System View

```
┌──────────────────────────────────────────────────────────────┐
│                        USER / API                            │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│       SERVING COMPONENT (Port 8002) - Lightweight Broker   │
├─────────────────────────────────────────────────────────────┤
│  EXISTING (v0.1.8):                                         │
│  • Session Management API         ✅                        │
│  • Compute Registry Service       ✅                        │
│  • Task Routing                   ✅                        │
│  • Storage API                    ✅                        │
├─────────────────────────────────────────────────────────────┤
│  NEW (v0.2.0 - Facilitated Process):                        │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  COORDINATING TEAM BROKER (Lightweight)            │    │
│  │  • Route messages to coordinating agents           │    │
│  │    (agents run in Compute, not here)               │    │
│  │  • Manage event bus (message routing)              │    │
│  │  • Track which compute has which agents            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  PROCESS MAP SERVICE (Storage Only)                │    │
│  │  • Store and version process maps                  │    │
│  │  • Track activities and dependencies               │    │
│  │  • Manage facilitation history                     │    │
│  │  (No agent execution - just storage)               │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  KEY: No agents execute here - all routing & storage       │
└────────┬──────────────────────────┬──────────────────┬─────┘
         │                          │                  │
         │ Query agents             │ Route ALL agent  │
         │ (via proxy)              │ messages         │
         ▼                          ▼                  ▼
┌─────────────────┐   ┌──────────────────────────────────────┐
│   MARKETPLACE   │   │   COMPUTE INSTANCES (8003+)          │
│   (Port 8001)   │   │   ALL AGENTS EXECUTE HERE            │
├─────────────────┤   ├──────────────────────────────────────┤
│  ✅ EXISTING    │   │  COMPUTE-001 (Coordinating)          │
│                 │   │  ┌─ Coordinating Agents ─────────┐   │
│  • Agent        │   │  │ • Process Mapper              │   │
│    catalog      │   │  │ • Agent Selector              │   │
│  • Search API   │   │  │ • Activity Facilitator        │   │
│  • Capability   │   │  │ • Consistency Manager         │   │
│    filtering    │   │  │ • Progress Reporter           │   │
│  • Access       │   │  │ • Result Synthesizer          │   │
│    control      │   │  └───────────────────────────────┘   │
└─────────────────┘   │  • LLM Integration (Heavy LLM use)   │
                       │  • Memory for process maps           │
                       ├──────────────────────────────────────┤
                       │  COMPUTE-002 (Specialized)           │
                       │  ┌─ Specialized Agents ──────────┐   │
                       │  │ • DataAnalystAgent            │   │
                       │  │ • ContentWriterAgent          │   │
                       │  │ • CodeReviewerAgent           │   │
                       │  │ • WebSearchAgent              │   │
                       │  └───────────────────────────────┘   │
                       │  • LLM Integration                   │
                       │  • Tool execution                    │
                       └──────────────────────────────────────┘
```

---

## Data Flow: Complete Facilitated Process

Let's trace a complete request through the system:

### Step 1: User Submits Business Goal

```
USER → POST /api/v1/sessions/create-facilitated
Body: {
  "business_goal": "Increase customer retention by 20%",
  "user_id": "user-123"
}

↓

SERVING: Session API (EXISTING v0.1.8)
• Creates session record
• Stores in session database
• Returns session_id

↓

SERVING: Coordinating Team Service (NEW v0.2.0)
• Instantiates coordinating agents for this session
• Creates event bus
• Initializes Process Mapper
```

### Step 2: Process Mapper Creates Initial Map

```
SERVING: Routes request to Process Mapper agent (NEW)
• Determines compute-001 has process-mapper-agent
• Routes message to compute-001

↓

COMPUTE-001: Process Mapper Agent (NEW)
• Receives business goal
• Uses LLM to propose initial activities:
  - Activity 1: "Understand current retention"
  - Activity 2: "Identify retention drivers"
  - Activity 3: "Develop improvement strategies"
• Creates ProcessMap v1
• Returns to Serving

↓

SERVING: Process Map Service (NEW v0.2.0)
• Stores process map (storage only - no execution)
• Tracks version history
• Makes available to other agents
• Emits event: ACTIVITY_PROPOSED
```

### Step 3: Agent Selector Chooses Participants

```
SERVING: Routes event to Agent Selector agent (NEW)
• Event: ACTIVITY_PROPOSED (Activity 1)
• Routes to compute-001 (has agent-selector-agent)

↓

COMPUTE-001: Agent Selector Agent (NEW)
• Analyzes activity needs:
  - Capabilities: [data_analysis, customer_metrics]
  - Domain: customer_retention
• Requests marketplace query from Serving

↓

SERVING → MARKETPLACE: Proxy marketplace query (EXISTING integration)
GET /api/v1/agents/search
Body: {
  "capabilities": ["data_analysis", "customer_metrics"],
  "domain": "customer_retention"
}

↓

MARKETPLACE → SERVING → COMPUTE-001: Returns matching agents
Response: [
  {
    "agent_id": "data-analyst-v1",
    "capabilities": [...],
    "score": 85
  },
  ...
]

↓

COMPUTE-001: Agent Selector Agent
• Uses LLM to score and rank candidates
• Selects: DataAnalystAgent (primary)
• Requests compute registry lookup from Serving

↓

SERVING: Compute Registry Service (EXISTING v0.1.4)
• Queries registry for instances with data-analyst-v1
• Finds: compute-002 has this agent
• Returns to Agent Selector on compute-001

↓

COMPUTE-001: Agent Selector
• Creates recommendation
• Returns to Serving

↓

SERVING: Routes event
• Emits event: PARTICIPANTS_RECOMMENDED
  - Activity: act-1
  - Primary: data-analyst-v1 @ compute-002
```

### Step 4: Activity Facilitator Guides Conversation

```
SERVING: Routes event to Activity Facilitator (NEW)
• Event: PARTICIPANTS_RECOMMENDED
• Routes to compute-001 (has activity-facilitator-agent)

↓

COMPUTE-001: Activity Facilitator Agent (NEW)
• Begins facilitation of Activity 1
• Creates Exchange 1: "What do you need?"
• Requests Serving to route message to DataAnalyst

↓ (This is where specialized agent execution happens)

SERVING → COMPUTE-002: Route to specialized agent (EXISTING v0.1.8)
POST /api/v1/agents/execute
Body: {
  "agent_id": "data-analyst-v1",
  "prompt": "[Facilitator's question + activity context]",
  "session_id": "sess-42",
  "activity_id": "act-1"
}

↓

COMPUTE-002: Agent Executor (EXISTING v0.1.8)
• Loads data-analyst-v1 agent definition
• Builds prompt from template + facilitator input
• Calls LLM (OpenAI/Anthropic/Mock)
• Returns result

↓

COMPUTE-002 → SERVING → COMPUTE-001: Route result back (EXISTING)
Response: {
  "result": "I need customer database access and timeframe",
  "metadata": {...}
}

↓

COMPUTE-001: Activity Facilitator Agent (NEW)
• Receives response from DataAnalyst
• Uses LLM to analyze response
• Detects blocker: "database access needed"
• Returns facilitation result to Serving

↓

SERVING: Routes result
• Stores facilitation history
• Emits event: BLOCKER_IDENTIFIED
```

### Step 5: Process Mapper Adapts Map

```
SERVING: Routes event to Process Mapper (NEW)
• Event: BLOCKER_IDENTIFIED
• Routes to compute-001

↓

COMPUTE-001: Process Mapper Agent (NEW)
• Receives blocker information
• Uses LLM to determine resolution
• Creates new Activity 0: "Obtain database access"
• Updates Activity 1 dependency: depends_on = [act-0]
• Updates ProcessMap v1 → v2
• Returns to Serving

↓

SERVING: Process Map Service (NEW)
• Stores new version (storage only)
• Emits event: MAP_UPDATED

↓

SERVING: Routes event to Progress Reporter (NEW)
• Routes to compute-001

↓

COMPUTE-001: Progress Reporter Agent (NEW)
• Receives MAP_UPDATED event
• Calculates progress:
  - Total activities: 4 (1 emergent)
  - Activity 1: blocked
  - Activity 0: proposed
• Returns progress report to Serving

↓

SERVING: Stores progress report
• Available via API: GET /api/v1/sessions/{id}/progress
```

### Step 6: Facilitate New Activity (Activity 0)

```
[Repeat Steps 3-4 for Activity 0]

SERVING: Agent Selector
• Recommends: ITAccessAgent @ compute-002

SERVING: Activity Facilitator
• Facilitates conversation with ITAccessAgent

SERVING → COMPUTE-002: Execute ITAccessAgent (EXISTING)
POST /api/v1/agents/execute
Body: {
  "agent_id": "it-access-agent-v1",
  "prompt": "[Get DB credentials for DataAnalyst]"
}

↓

COMPUTE-002: Returns credentials

↓

SERVING: Activity Facilitator
• Activity 0 goal met
• Credentials stored in session context
• Activity 1 now unblocked
```

### Step 7: Consistency Manager Monitors

```
SERVING: Consistency Manager Agent (NEW)
• Subscribes to all FACILITATION_COMPLETED events
• Receives outputs from Activity 3 and Activity 7
• Detects inconsistency:
  - Activity 3 output: "retention = 65%"
  - Activity 7 output: "based on 70% retention"
• Emits event: INCONSISTENCY_DETECTED

↓

SERVING: Process Mapper
• Receives inconsistency event
• Creates reconciliation Activity 1b
• Updates map
```

### Step 8: Result Synthesizer Assembles Deliverable

```
[When all activities complete]

SERVING: Result Synthesizer Agent (NEW)
• Collects outputs from all activities
• Queries session context for all activity results:
  GET /api/v1/sessions/{id}/activities → all outputs

• Uses LLM to synthesize:
  - Executive summary
  - Key findings
  - Recommendations
  - Supporting data

• Stores final deliverable:
  POST /api/v1/sessions/{id}/results

↓

USER: Retrieves results
GET /api/v1/sessions/{id}/results
```

---

## What's Already There (Reusable)

### From Marketplace (v0.1.5)

✅ **Agent Discovery**
```python
# Agent Selector can use this directly
async def query_marketplace(capabilities, domain):
    response = await http_client.post(
        f"{marketplace_url}/api/v1/agents/search",
        json={
            "capabilities": capabilities,
            "domain": domain,
            "status": "active"
        }
    )
    return response.json()
```

✅ **Access Control**
- User/Organization management
- Agent access permissions
- Marketplace API keys

### From Serving (v0.1.4-0.1.8)

✅ **Session Management**
```python
# Facilitated process builds on this
class Session:
    session_id: str
    goal: str  # Can use as business_goal
    status: str
    context: Dict  # Store activity outputs here
    created_at: datetime
```

✅ **Compute Registry**
```python
# Agent Selector uses this to find agents
class ComputeRegistry:
    def get_instance_by_capability(self, agent_id):
        # Returns compute instance that has this agent
        
    def get_all_instances(self):
        # Returns all registered compute instances
```

✅ **Task Routing**
```python
# Activity Facilitator uses this to execute specialized agents
async def route_task_to_compute(
    agent_id: str,
    input_data: dict,
    session_id: str
):
    # Find compute instance
    instance = registry.get_instance_with_agent(agent_id)
    
    # Route task
    response = await http_client.post(
        f"{instance.url}/api/v1/agents/execute",
        json={
            "agent_id": agent_id,
            "prompt": input_data["prompt"],
            "session_id": session_id
        }
    )
    return response.json()
```

✅ **Storage API**
```python
# For storing process maps, facilitation history, etc.
# Already exists: serving/api/storage_api/
```

### From Compute (v0.1.8)

✅ **Agent Execution**
```python
# Activity Facilitator calls this via Serving routing
POST /api/v1/agents/execute
{
  "agent_id": "data-analyst-v1",
  "prompt": "...",
  "session_id": "sess-42",
  "context": {...}
}
```

✅ **LLM Integration**
```python
# Coordinating agents will also use LLM
# Can reuse the same providers:
from runtime.llm_client import LLMClient
from runtime.providers import MockProvider, OpenAIProvider

client = LLMClient(provider="mock")  # or "openai"
response = await client.complete(prompt)
```

✅ **Agent Registration**
```python
# Compute instances already register with Serving
# They'll just need to advertise coordinating agents too
```

---

## What Needs to Be Added (v0.2.0)

### In Compute Component

#### 1. Coordinating Agent Definitions (NEW)

```python
# compute/data/compute/agents/coordinating/
├── process-mapper-agent.json           # Process Mapper definition
├── agent-selector-agent.json           # Agent Selector definition  
├── activity-facilitator-agent.json     # Activity Facilitator definition
├── consistency-manager-agent.json      # Consistency Manager definition
├── progress-reporter-agent.json        # Progress Reporter definition
└── result-synthesizer-agent.json       # Result Synthesizer definition
```

**Agent Definitions** (Example: process-mapper-agent.json):
```json
{
  "agent_id": "process-mapper-v1",
  "name": "Process Mapper",
  "type": "coordinating",
  "description": "Builds and evolves process maps from business goals",
  "capabilities": [
    "process_mapping",
    "activity_decomposition",
    "dependency_analysis",
    "process_evolution"
  ],
  "system_prompt": "You are a Process Mapper agent. Your role is to analyze business goals and propose activities...",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2000
}
```

**Implementation Notes**:
- Coordinating agents are agent definitions like specialized agents
- They use LLM extensively (already have LLMClient in compute)
- They execute on compute instances like any other agent
- Can be distributed across multiple compute instances

### In Serving Component

#### 1. Coordinating Team Broker (NEW - Lightweight)

```python
# serving/services/coordinating_team_broker.py

class CoordinatingTeamBroker:
    """Routes messages to coordinating agents (which run on compute)"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.event_bus = EventBus()  # Message routing
        self.compute_registry = ComputeRegistry()
        
    def get_coordinating_agent_location(self, agent_type: str) -> str:
        """Find which compute instance has this coordinating agent"""
        # Query registry for compute with this agent
        instance = self.compute_registry.find_instance_with_agent(
            f"{agent_type}-agent-v1"
        )
        return instance.url
        
    async def route_to_coordinating_agent(
        self, 
        agent_type: str, 
        message: dict
    ) -> dict:
        """Route message to coordinating agent on compute"""
        # Find compute instance
        compute_url = self.get_coordinating_agent_location(agent_type)
        
        # Route via existing task routing
        response = await self.task_router.execute_agent(
            agent_id=f"{agent_type}-agent-v1",
            input_data=message,
            session_id=self.session_id
        )
        return response
        
    async def start_facilitation(self, business_goal: str):
        """Begin facilitated process by routing to Process Mapper"""
        # Route to Process Mapper agent (runs on compute)
        result = await self.route_to_coordinating_agent(
            agent_type="process-mapper",
            message={"business_goal": business_goal}
        )
        return result
```

#### 2. Process Map Service (NEW - Storage Only)

```python
# serving/services/process_map_service.py

class ProcessMapService:
    """Storage and versioning for process maps (NO execution)"""
    
    def create_map(self, session_id, business_goal) -> ProcessMap
    def update_map(self, map_id, changes) -> ProcessMap
    def get_map(self, map_id) -> ProcessMap
    def get_map_history(self, map_id) -> List[ProcessMap]
    def add_activity(self, map_id, activity) -> Activity
    def update_activity_status(self, activity_id, status)
    
    # NOTE: This service ONLY stores data
    # Process Mapper agent (runs on compute) does the actual work
```

#### 3. Event Bus (NEW - Message Routing)

```python
# serving/services/event_bus.py

class EventBus:
    """Routes events to coordinating agents (which run on compute)"""
    
    def subscribe(self, agent_type: str, event_types: List[str]):
        """Register which events to route to which agent type"""
        # e.g., "process-mapper" subscribes to "BLOCKER_IDENTIFIED"
        
    async def publish(self, event: CoordinatingEvent):
        """Route event to subscribed agents on compute"""
        # Find which agent types are subscribed
        subscribers = self.get_subscribers(event.event_type)
        
        # Route to each subscriber's compute instance
        for agent_type in subscribers:
            await self.broker.route_to_coordinating_agent(
                agent_type=agent_type,
                message=event.dict()
            )
    
    # NOTE: Event bus routes messages, agents execute on compute
```

#### 4. New API Endpoints (NEW)

```python
# serving/api/facilitated_process.py

@router.post("/sessions/create-facilitated")
async def create_facilitated_session(request: FacilitatedSessionRequest):
    """Create session with coordinating team"""
    
@router.get("/sessions/{session_id}/process-map")
async def get_process_map(session_id: str):
    """Get current process map"""
    
@router.get("/sessions/{session_id}/process-map/history")
async def get_map_history(session_id: str):
    """Get process map evolution"""
    
@router.get("/sessions/{session_id}/activities/{activity_id}/exchanges")
async def get_facilitation_history(session_id: str, activity_id: str):
    """Get facilitation conversation for activity"""
    
@router.get("/sessions/{session_id}/inconsistencies")
async def get_inconsistencies(session_id: str):
    """Get detected inconsistencies"""
```

#### 5. Data Models (NEW)

```python
# serving/models/facilitated_process.py

class ProcessMap(BaseModel): ...
class Activity(BaseModel): ...
class Exchange(BaseModel): ...
class FacilitationResult(BaseModel): ...
class Inconsistency(BaseModel): ...
class CoordinatingEvent(BaseModel): ...
```

### Compute Registration Updates

#### Coordinating Agents Registration

When a compute instance starts, it needs to register both specialized AND coordinating agents:

```python
# compute/services/registration_client.py

class RegistrationClient:
    async def register_with_serving(self):
        """Register this compute instance with serving"""
        
        # Load all agents (specialized + coordinating)
        agents = self.load_agents_from_directory([
            "data/compute/agents/specialized/",
            "data/compute/agents/coordinating/"  # NEW
        ])
        
        # Register with serving
        response = await self.http_client.post(
            f"{serving_url}/api/v1/compute/register",
            json={
                "instance_id": self.instance_id,
                "agents": agents,  # Includes coordinating agents
                "capabilities": self.extract_capabilities(agents),
                "resources": self.get_resource_info()
            }
        )
```

**Deployment Strategy**:
- Dedicated coordinating instance: Load only coordinating agents
- Mixed instance: Load both coordinating and specialized agents
- Serving routes messages based on agent location (via registry)

---

## Integration Points (Detailed)

### 1. Agent Selector ↔ Marketplace

```python
# serving/agents/coordinating/agent_selector.py

class AgentSelectorAgent:
    def __init__(self, marketplace_service):
        self.marketplace_service = marketplace_service
    
    async def select_agents_for_activity(self, activity: Activity):
        # 1. Analyze activity to extract requirements
        requirements = await self.analyze_activity(activity)
        
        # 2. Query marketplace (EXISTING API)
        candidates = await self.marketplace_service.search_agents(
            capabilities=requirements.capabilities,
            domain=requirements.domain
        )
        
        # 3. Score and rank
        scored = self.score_candidates(candidates, requirements)
        
        # 4. Check compute availability
        for candidate in scored:
            compute_instance = await self.compute_registry.find_instance_with_agent(
                candidate.agent_id
            )
            candidate.available = compute_instance is not None
        
        # 5. Return recommendation
        return self.create_recommendation(scored)
```

**Uses**:
- ✅ Marketplace search API (already exists)
- ✅ Compute registry (already exists)

### 2. Activity Facilitator ↔ Compute

```python
# serving/agents/coordinating/activity_facilitator.py

class ActivityFacilitatorAgent:
    def __init__(self, task_router):
        self.task_router = task_router  # EXISTING
    
    async def facilitate_activity(self, activity: Activity):
        # Engage assigned agent (specialized agent on compute)
        primary_agent = activity.assigned_agents[0]
        
        # Build facilitation prompt
        prompt = self.build_facilitation_prompt(activity)
        
        # Route to compute instance (EXISTING routing)
        result = await self.task_router.execute_agent(
            agent_id=primary_agent.agent_id,
            input_data={"prompt": prompt},
            session_id=self.session_id,
            context={
                "activity_id": activity.activity_id,
                "activity_goal": activity.goal
            }
        )
        
        # Analyze result to determine if goal met
        goal_met = await self.assess_goal_completion(activity, result)
        
        return FacilitationResult(
            activity_id=activity.activity_id,
            status="goal_met" if goal_met else "in_progress",
            outputs=result
        )
```

**Uses**:
- ✅ Task routing to compute (already exists)
- ✅ Agent execution on compute (already exists)

### 3. Coordinating Agents ↔ Session Storage

```python
# All coordinating agents use existing session storage

class ProcessMapperAgent:
    async def update_process_map(self, map_id, changes):
        # Store using EXISTING storage API
        await self.storage_service.save_object(
            f"process_maps/{self.session_id}/{map_id}.json",
            process_map.dict()
        )

class ActivityFacilitatorAgent:
    async def record_exchange(self, activity_id, exchange):
        # Store using EXISTING storage API
        await self.storage_service.append_to_file(
            f"activities/{self.session_id}/{activity_id}/exchanges.jsonl",
            json.dumps(exchange.dict())
        )
```

**Uses**:
- ✅ Storage API (already exists)
- ✅ Session context storage (already exists)

---

## Migration from v0.1.8 Pipeline to v0.2.0 Facilitated Process

### Backward Compatibility

Both can coexist:

```python
# serving/api/sessions.py

@router.post("/sessions/create")
async def create_session(request: SessionRequest):
    """Traditional session (v0.1.8 - pipeline mode)"""
    # Existing implementation
    
@router.post("/sessions/create-facilitated")
async def create_facilitated_session(request: FacilitatedSessionRequest):
    """Facilitated session (v0.2.0 - new mode)"""
    # New implementation with coordinating team
```

Users can choose which mode to use based on their needs.

### Data Model Compatibility

ProcessMap is an evolution of ExecutionPipeline:

```python
# v0.1.8 ExecutionPipeline
class PipelineStep:
    step_id: str
    order: int  # Fixed sequence
    dependencies: List[str]  # Predetermined

# v0.2.0 Activity
class Activity:
    activity_id: str
    goal: str  # Goal-oriented
    depends_on: List[str]  # Discovered
    # No order field - dependencies form natural order
```

Can convert between them for compatibility:

```python
def pipeline_to_process_map(pipeline: ExecutionPipeline) -> ProcessMap:
    """Convert v0.1.8 pipeline to v0.2.0 process map"""
    activities = []
    for step in pipeline.steps:
        activity = Activity(
            activity_id=step.step_id,
            goal=step.description,
            depends_on=step.dependencies,
            status="proposed",
            assigned_agents=[step.agent_id]
        )
        activities.append(activity)
    
    return ProcessMap(
        map_id=pipeline.pipeline_id,
        session_id=pipeline.session_id,
        activities={a.activity_id: a for a in activities}
    )
```

---

## Implementation Sequence

### Phase 1: Foundation (Week 1-2)
**Focus**: Data models and storage

**Builds On**:
- ✅ Existing session storage
- ✅ Existing storage API

**Adds**:
- ❌ ProcessMap, Activity models
- ❌ Process Map Service
- ❌ Storage schemas

**Integration**: Minimal - just data layer

### Phase 2: Process Mapper (Week 2)
**Focus**: First coordinating agent

**Builds On**:
- ✅ Existing LLM integration
- ✅ Existing session management

**Adds**:
- ❌ Process Mapper agent
- ❌ Initial map creation logic
- ❌ Map evolution logic

**Integration**: Process Mapper creates maps, stores via Process Map Service

### Phase 3: Agent Selector (Week 2-3)
**Focus**: Second coordinating agent

**Builds On**:
- ✅ Existing marketplace search API
- ✅ Existing compute registry

**Adds**:
- ❌ Agent Selector agent
- ❌ Scoring algorithm
- ❌ Recommendation logic

**Integration**: 
- Agent Selector → Marketplace (search agents)
- Agent Selector → Compute Registry (check availability)

### Phase 4: Activity Facilitator (Week 3-4)
**Focus**: Third coordinating agent

**Builds On**:
- ✅ Existing task routing
- ✅ Existing agent execution

**Adds**:
- ❌ Activity Facilitator agent
- ❌ Facilitation logic
- ❌ Goal assessment

**Integration**:
- Activity Facilitator → Task Router → Compute (execute specialized agents)
- Activity Facilitator → Process Map Service (record facilitation)

### Phase 5: Remaining Agents (Week 4)
**Focus**: Consistency Manager, Progress Reporter, Result Synthesizer

**Builds On**:
- ✅ Event bus from Phase 4
- ✅ Process maps and activities

**Adds**:
- ❌ Consistency Manager
- ❌ Progress Reporter
- ❌ Result Synthesizer

**Integration**: All agents coordinate via event bus

### Phase 6: Integration (Week 5-6)
**Focus**: End-to-end flows

**Connects**:
- Coordinating Team Service
- Event-driven coordination
- API endpoints
- Testing

---

## Summary: What's Reused vs What's New

### ✅ Reusing from Existing Platform (80% of infrastructure)

| Component | What's Reused | How It's Used |
|-----------|---------------|---------------|
| **Marketplace** | Agent catalog, search API, access control | Agent Selector queries for agents |
| **Serving - Sessions** | Session management, storage | Session owns facilitated process |
| **Serving - Compute Registry** | Instance registry, capability tracking | Agent Selector finds which compute has agents |
| **Serving - Task Routing** | Route tasks to compute | Activity Facilitator executes specialized agents |
| **Serving - Storage** | Blob storage, session storage | Store process maps, facilitation history |
| **Compute - Execution** | Agent executor, LLM integration | Execute specialized agents |
| **Compute - Registration** | Register with serving, heartbeat | Advertise available agents |

### ❌ New for v0.2.0 (20% net new)

| Component | What's New | Why It's Needed | Where It Lives |
|-----------|------------|-----------------|----------------|
| **Coordinating Agent Definitions** | 6 agent JSON definitions | Define coordinating agents | **Compute** (agents/coordinating/) |
| **Coordinating Team Broker** | Lightweight message router | Route messages to agents on compute | **Serving** (services/) |
| **Process Map Service** | Store and version process maps | Track evolving process structure | **Serving** (services/) |
| **Event Bus** | Event-driven message routing | Route agent messages through serving | **Serving** (services/) |
| **Facilitation API** | New API endpoints | Expose facilitated process features | **Serving** (api/) |
| **Process Map Models** | Activity, ProcessMap, Exchange, etc. | Represent facilitated process concepts | **Serving** (models/) |

**Key Architectural Point**: 
- **Coordinating agents EXECUTE in Compute** (just like specialized agents)
- **Serving ROUTES messages** to them (lightweight broker)
- **All heavy work (LLM, memory) in Compute** - Serving stays lightweight

---

## Conclusion

The facilitated process architecture **integrates cleanly** with your existing platform:

1. **Marketplace remains unchanged** - Agent Selector queries existing search API
2. **Compute gets coordinating agents** - New agent definitions, same execution model
3. **Serving becomes lightweight broker** - Routes messages, stores state, NO agent execution

**The beauty of this design**:
- ✅ Leverages 80% of existing infrastructure
- ✅ Adds 20% new orchestration layer
- ✅ Backward compatible (pipeline mode still works)
- ✅ Clean separation of concerns
- ✅ Natural evolution of the platform
- ✅ **Serving stays lightweight** - all heavy work in Compute

---

## Critical Architectural Principle

### **ALL Agents Execute in Compute, Serving Routes**

```
❌ WRONG: Coordinating agents in Serving
┌──────────────┐
│   SERVING    │ ← Heavy LLM calls, memory intensive
│ (Heavyweight)│ ← Coordinating agents execute here
└──────────────┘

✅ CORRECT: Coordinating agents in Compute
┌──────────────┐
│   SERVING    │ ← Lightweight message routing
│ (Lightweight)│ ← NO agent execution, just routing
└──────┬───────┘
       │ Routes messages to...
       ▼
┌──────────────┐
│   COMPUTE    │ ← Heavy LLM calls, memory intensive
│ (Heavyweight)│ ← ALL agents execute here
└──────────────┘
```

### Why This Matters

1. **Resource Isolation**: Heavy compute stays in compute instances
2. **Scalability**: Can scale compute independently from routing
3. **Deployment Flexibility**: Serving can be lightweight/highly available
4. **Cost Efficiency**: Expensive resources (GPU, memory) only where needed
5. **Clear Boundaries**: Serving = infrastructure, Compute = execution

### What This Means for Implementation

**Coordinating agents are just agent definitions** (JSON files) that:
- Live in `compute/data/compute/agents/coordinating/`
- Execute via existing agent executor
- Use existing LLM integration
- Register with Serving like specialized agents
- Get routed to by Serving like specialized agents

**Serving just adds routing logic**:
- Event bus routes messages to agents on compute
- Process Map Service stores data (no execution)
- Coordinating Team Broker finds and routes to agents

---

**Document Version**: 2.0 (Updated for Compute-based execution)  
**Date**: November 24, 2024  
**Status**: Integration Design  
**Target Release**: ClaudeVN v0.2.0

