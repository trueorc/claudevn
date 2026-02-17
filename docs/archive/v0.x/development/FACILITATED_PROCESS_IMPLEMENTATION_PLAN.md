# Facilitated Process Implementation Plan
## Iterative, UI-Testable Approach

**Version:** 0.2.0  
**Date:** November 24, 2024  
**Status:** Implementation Plan

---

## Executive Summary

This plan implements the **Facilitated Process Architecture** (goal-oriented, emergent workflows) on top of the existing v0.1.8 traditional pipeline system. The approach is:

1. **Incremental** - Build in 6 phases, each delivering testable value
2. **UI-First Testing** - Every phase includes UI components for visual testing
3. **Reuses 80%** - Leverages existing infrastructure (marketplace, compute, storage)
4. **No Throw-Away** - Each phase builds toward the complete v0.2.0 vision
5. **Dual-Mode** - Keeps traditional pipeline (v0.1.8) alongside new facilitated process

---

## Current State (v0.1.8)

### What We Have ✅

**Marketplace Component:**
- Agent catalog and search ✅
- Capability-based filtering ✅
- Access control system ✅
- React UI ✅

**Serving Component:**
- Session management (CRUD, storage) ✅
- Compute registry service ✅
- Task routing to compute ✅
- Basic ExecutionPipeline model ✅
- React dashboard UI ✅

**Compute Component:**
- Agent execution engine ✅
- LLM integration (OpenAI, Anthropic, Mock) ✅
- Agent executor service ✅
- 4 specialized agents ✅
- Registration with serving ✅

### What's Missing ❌

- ProcessMap model (evolution of pipeline)
- Coordinating agent definitions (6 agents)
- Activity facilitation system
- Event bus for coordination
- Process map evolution tracking
- Consistency monitoring
- UI for viewing facilitated sessions

---

## Architecture Principles

### Key Insight: Compute Executes, Serving Routes

```
┌─────────────┐
│   SERVING   │ ← Lightweight routing & storage
│ (Broker)    │ ← NO agent execution
└──────┬──────┘
       │ Routes all agent messages
       ▼
┌─────────────┐
│   COMPUTE   │ ← Heavy LLM calls
│ (Execution) │ ← ALL agents run here (coordinating + specialized)
└─────────────┘
```

**This means:**
- Coordinating agents are JSON definitions in `compute/data/compute/agents/coordinating/`
- They execute via existing agent executor (already works)
- Serving adds routing logic (event bus) to coordinate them
- No heavy lifting in serving - it's just a message broker

---

## Implementation Phases

## Phase 1: Foundation - Process Map Models & Storage
**Duration:** 1 week  
**Focus:** Data layer, no agent execution yet

### Goals
- Extend data models to support Activities (not just Steps)
- Add ProcessMap storage service
- Create API endpoints for process maps
- Build UI component to visualize process maps

### What We Build

#### 1. New Data Models (Serving)

**Location:** `serving/models/process_map.py`

```python
class ActivityStatus(str, Enum):
    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    GOAL_MET = "goal_met"
    BLOCKED = "blocked"
    REVISIT = "revisit"

class Activity(BaseModel):
    """Goal-oriented work unit (not a predetermined step)"""
    activity_id: str
    goal: str  # What we're trying to accomplish
    description: Optional[str]
    status: ActivityStatus
    
    # Participants (can change during facilitation)
    assigned_agents: List[ParticipantAssignment]
    
    # Dependencies (discovered, not predetermined)
    depends_on: List[str]
    enables: List[str]
    
    # Facilitation history
    facilitation_exchanges: List[Exchange]
    outputs: Dict[str, Any]
    
    # Timestamps
    proposed_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

class ProcessMap(BaseModel):
    """Living document that evolves (not a fixed pipeline)"""
    map_id: str
    session_id: str
    business_goal: str
    
    # Evolution
    map_version: int  # Increments when restructured
    activities: Dict[str, Activity]  # By activity_id
    activity_graph: Dict[str, List[str]]  # Dependencies
    
    # Current state
    proposed_activities: List[str]
    in_progress_activities: List[str]
    completed_activities: List[str]
    blocked_activities: List[str]
    
    # Evolution tracking
    reevaluations: List[ReevaluationEvent]
    
    created_at: datetime
    updated_at: datetime
```

#### 2. Process Map Service (Serving)

**Location:** `serving/services/process_map_service.py`

```python
class ProcessMapService:
    """Storage and versioning for process maps (no execution)"""
    
    def __init__(self, storage_backend):
        self.storage = storage_backend
    
    async def create_map(self, session_id: str, business_goal: str) -> ProcessMap:
        """Create initial process map for session"""
        
    async def get_map(self, session_id: str) -> ProcessMap:
        """Get current process map for session"""
        
    async def update_map_version(self, session_id: str, changes: Dict) -> ProcessMap:
        """Create new version of process map (evolution)"""
        
    async def add_activity(self, session_id: str, activity: Activity) -> Activity:
        """Add activity to map"""
        
    async def update_activity_status(self, session_id: str, activity_id: str, status: ActivityStatus):
        """Update activity status"""
        
    async def get_map_history(self, session_id: str) -> List[ProcessMap]:
        """Get all versions of process map (evolution history)"""
```

**Key Point:** This service only stores data. Process Mapper agent (Phase 2) does the actual work.

#### 3. API Endpoints (Serving)

**Location:** `serving/api/process_maps.py`

```python
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/process-maps", tags=["process-maps"])

@router.get("/sessions/{session_id}/map")
async def get_process_map(session_id: str):
    """Get current process map for session"""
    
@router.get("/sessions/{session_id}/map/history")
async def get_map_history(session_id: str):
    """Get evolution history of process map"""
    
@router.get("/sessions/{session_id}/activities/{activity_id}")
async def get_activity(session_id: str, activity_id: str):
    """Get activity details including facilitation history"""
    
@router.post("/sessions/{session_id}/map/activities")
async def add_activity(session_id: str, activity: ActivityCreate):
    """Add activity to process map (for testing only in Phase 1)"""
```

#### 4. UI Component (Serving Frontend)

**Location:** `serving/frontend/src/components/ProcessMapViewer.jsx`

**Features:**
- Visualize process map as a graph
- Show activities with status colors (proposed, in-progress, completed, blocked)
- Display dependencies as arrows
- Show current map version
- View evolution history (versions 1 → 2 → 3...)
- Click activity to see details

**Testing in Phase 1:**
```bash
# Start services
./start_all.sh

# Open UI
http://localhost:8002

# Create test process map via API
curl -X POST http://localhost:8002/api/v1/sessions/create \
  -H "Content-Type: application/json" \
  -d '{"goal": "Test process map"}'

# Add test activities via API
curl -X POST http://localhost:8002/api/v1/process-maps/sessions/{session_id}/map/activities \
  -d '{"goal": "Test activity 1", "status": "proposed"}'

# View in UI
Navigate to Sessions → Select session → View Process Map
```

### Deliverables
- ✅ ProcessMap and Activity models
- ✅ ProcessMapService with storage
- ✅ API endpoints for process maps
- ✅ ProcessMapViewer UI component
- ✅ Manual test via UI (create activities, view map)

### Success Criteria
- Can create process maps via API
- Can view process map in UI as a graph
- Can see activity statuses and dependencies
- Can track map version changes

---

## Phase 2: Process Mapper - First Coordinating Agent
**Duration:** 1 week  
**Focus:** First agent that creates/evolves process maps

### Goals
- Create Process Mapper coordinating agent
- Integrate with existing agent executor
- Test via UI: "Give business goal → See initial process map"

### What We Build

#### 1. Process Mapper Agent Definition (Compute)

**Location:** `compute/data/compute/agents/coordinating/process-mapper-agent.json`

```json
{
  "agent_id": "process-mapper-v1",
  "name": "Process Mapper",
  "type": "coordinating",
  "description": "Analyzes business goals and creates/evolves process maps",
  "capabilities": [
    "process_mapping",
    "activity_decomposition",
    "dependency_analysis",
    "process_evolution"
  ],
  "system_prompt": "You are a Process Mapper agent. Your role is to analyze business goals and propose activities to achieve them.\n\nWhen given a business goal, you should:\n1. Understand the high-level objective\n2. Propose 3-5 initial activities (high-level, goal-oriented)\n3. Identify basic dependencies\n4. Output as structured JSON\n\nYou are NOT creating a fixed plan - activities will evolve as work progresses.\n\nOutput format:\n{\n  \"activities\": [\n    {\n      \"activity_id\": \"act-1\",\n      \"goal\": \"What this activity aims to accomplish\",\n      \"description\": \"Additional context\",\n      \"depends_on\": []\n    }\n  ]\n}",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2000,
  "provider": "openai"
}
```

**Key Point:** This is just a JSON file. It executes via existing agent executor in compute.

#### 2. Process Mapper Service Integration (Serving)

**Location:** `serving/services/coordinating_team_service.py`

```python
class CoordinatingTeamService:
    """Routes messages to coordinating agents on compute"""
    
    def __init__(self, compute_registry: ComputeRegistry):
        self.compute_registry = compute_registry
        self.task_router = TaskRouter(compute_registry)
    
    async def invoke_process_mapper(
        self, 
        session_id: str, 
        action: str,  # "create_initial_map" or "evolve_map"
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Route request to Process Mapper agent on compute"""
        
        # Find compute instance with process-mapper-v1
        compute_instance = self.compute_registry.find_instance_with_agent("process-mapper-v1")
        if not compute_instance:
            raise HTTPException(404, "Process Mapper agent not available")
        
        # Build prompt for Process Mapper
        if action == "create_initial_map":
            prompt = f"""Business Goal: {data['business_goal']}

Create an initial process map with 3-5 high-level activities to achieve this goal.
Output as JSON with activities list."""
        
        elif action == "evolve_map":
            prompt = f"""Current Process Map: {data['current_map']}

New Information: {data['new_information']}

Evolve the process map based on this new information. Output updated activities."""
        
        # Execute agent via task router (existing infrastructure)
        result = await self.task_router.execute_agent(
            agent_id="process-mapper-v1",
            compute_url=compute_instance.url,
            input_data={
                "prompt": prompt,
                "session_id": session_id,
                "action": action
            }
        )
        
        return result
```

**Key Point:** We're routing to agent via existing task router. No new execution logic needed.

#### 3. API Endpoint for Creating Facilitated Sessions

**Location:** `serving/api/sessions.py` (extend existing)

```python
@router.post("/sessions/create-facilitated")
async def create_facilitated_session(request: FacilitatedSessionRequest):
    """Create session with facilitated process (v0.2.0 mode)"""
    
    # Create session (existing infrastructure)
    session = await session_service.create_session(
        goal=request.business_goal,
        mode="facilitated"  # vs "pipeline" for v0.1.8 mode
    )
    
    # Create initial process map (storage only)
    process_map = await process_map_service.create_map(
        session_id=session.session_id,
        business_goal=request.business_goal
    )
    
    # Invoke Process Mapper agent to populate initial activities
    result = await coordinating_team_service.invoke_process_mapper(
        session_id=session.session_id,
        action="create_initial_map",
        data={"business_goal": request.business_goal}
    )
    
    # Parse Process Mapper output and add activities to map
    activities = parse_process_mapper_output(result)
    for activity in activities:
        await process_map_service.add_activity(session.session_id, activity)
    
    return {
        "session_id": session.session_id,
        "process_map_id": process_map.map_id,
        "initial_activities": len(activities),
        "message": "Facilitated session created with initial process map"
    }
```

#### 4. UI Enhancement (Serving Frontend)

**Location:** `serving/frontend/src/components/CreateSessionModal.jsx`

Add mode selection:
```jsx
<select name="mode">
  <option value="pipeline">Traditional Pipeline (v0.1.8)</option>
  <option value="facilitated">Facilitated Process (v0.2.0)</option>
</select>
```

**Testing in Phase 2:**
```bash
# Via UI:
1. Navigate to http://localhost:8002
2. Click "Create New Session"
3. Enter business goal: "Increase customer retention by 20%"
4. Select mode: "Facilitated Process (v0.2.0)"
5. Submit
6. See initial process map with 3-5 activities created by Process Mapper
7. View process map graph showing proposed activities
```

### Deliverables
- ✅ process-mapper-agent.json definition
- ✅ CoordinatingTeamService for routing to agents
- ✅ /sessions/create-facilitated endpoint
- ✅ UI mode selection for facilitated vs pipeline
- ✅ End-to-end test: Business goal → Initial process map

### Success Criteria
- Can create facilitated session via UI
- Process Mapper agent generates 3-5 initial activities
- Process map appears in UI with proposed activities
- Activities are goal-oriented (not implementation steps)

---

## Phase 3: Agent Selector - Participant Matching
**Duration:** 1 week  
**Focus:** Select which agents should work on each activity

### Goals
- Create Agent Selector coordinating agent
- Integrate with marketplace search
- Test via UI: Select activity → See recommended participants

### What We Build

#### 1. Agent Selector Agent Definition (Compute)

**Location:** `compute/data/compute/agents/coordinating/agent-selector-agent.json`

```json
{
  "agent_id": "agent-selector-v1",
  "name": "Agent Selector",
  "type": "coordinating",
  "description": "Analyzes activities and recommends which agents should participate",
  "capabilities": [
    "activity_analysis",
    "agent_matching",
    "capability_assessment",
    "participant_recommendation"
  ],
  "system_prompt": "You are an Agent Selector. Your role is to analyze an activity's goal and determine which agents would be best suited to accomplish it.\n\nWhen given an activity, you should:\n1. Identify required capabilities\n2. Assess domain expertise needed\n3. Consider technical requirements\n4. Recommend primary and backup participants\n\nOutput format:\n{\n  \"required_capabilities\": [\"capability1\", \"capability2\"],\n  \"domain_expertise\": \"domain_name\",\n  \"recommended_primary\": \"agent-id\",\n  \"recommended_backup\": \"agent-id\",\n  \"reasoning\": \"Why these agents were selected\"\n}",
  "model": "gpt-4",
  "temperature": 0.3,
  "max_tokens": 1500,
  "provider": "openai"
}
```

#### 2. Agent Selector Service (Serving)

**Location:** `serving/services/coordinating_team_service.py` (extend)

```python
async def select_participants_for_activity(
    self,
    session_id: str,
    activity_id: str
) -> Dict[str, Any]:
    """Select participants for an activity"""
    
    # Get activity from process map
    activity = await process_map_service.get_activity(session_id, activity_id)
    
    # Step 1: Invoke Agent Selector to analyze requirements
    analysis_result = await self.invoke_agent_selector(
        session_id=session_id,
        activity=activity,
        action="analyze_requirements"
    )
    
    requirements = analysis_result["required_capabilities"]
    domain = analysis_result.get("domain_expertise")
    
    # Step 2: Query marketplace for matching agents
    marketplace_results = await marketplace_client.search_agents(
        capabilities=requirements,
        domain=domain,
        status="active"
    )
    
    # Step 3: Invoke Agent Selector again to score candidates
    recommendation_result = await self.invoke_agent_selector(
        session_id=session_id,
        activity=activity,
        action="recommend_participants",
        data={
            "candidates": marketplace_results,
            "requirements": requirements
        }
    )
    
    # Step 4: Check compute registry for availability
    primary_agent_id = recommendation_result["recommended_primary"]
    compute_instance = self.compute_registry.find_instance_with_agent(primary_agent_id)
    
    if not compute_instance:
        # Try backup
        backup_agent_id = recommendation_result["recommended_backup"]
        compute_instance = self.compute_registry.find_instance_with_agent(backup_agent_id)
        if compute_instance:
            primary_agent_id = backup_agent_id
    
    return {
        "activity_id": activity_id,
        "primary_agent": primary_agent_id,
        "backup_agent": recommendation_result.get("recommended_backup"),
        "reasoning": recommendation_result["reasoning"],
        "compute_instance": compute_instance.instance_id if compute_instance else None
    }
```

#### 3. API Endpoint

**Location:** `serving/api/process_maps.py` (extend)

```python
@router.post("/sessions/{session_id}/activities/{activity_id}/select-participants")
async def select_participants(session_id: str, activity_id: str):
    """Select participants for an activity"""
    
    result = await coordinating_team_service.select_participants_for_activity(
        session_id=session_id,
        activity_id=activity_id
    )
    
    # Update activity with assigned agents
    await process_map_service.assign_agents_to_activity(
        session_id=session_id,
        activity_id=activity_id,
        primary_agent=result["primary_agent"],
        backup_agent=result.get("backup_agent")
    )
    
    return result
```

#### 4. UI Component

**Location:** `serving/frontend/src/components/ActivityParticipants.jsx`

**Features:**
- Show activity goal
- Display analysis: required capabilities, domain expertise
- List marketplace search results (candidates)
- Show scoring and reasoning
- Display recommended primary and backup agents
- Button: "Assign Participants"

**Testing in Phase 3:**
```bash
# Via UI:
1. Navigate to http://localhost:8002
2. Open existing facilitated session
3. Click on an activity in process map
4. Click "Select Participants" button
5. See Agent Selector analysis:
   - Required capabilities: [data_analysis, customer_metrics]
   - Domain: customer_retention
6. See marketplace search results (8 candidates)
7. See Agent Selector recommendations:
   - Primary: DataAnalystAgent (score: 85)
   - Backup: CustomerInsightsAgent (score: 75)
   - Reasoning: "DataAnalyst has complete capability coverage..."
8. Click "Assign Participants"
9. See agents assigned to activity in process map
```

### Deliverables
- ✅ agent-selector-agent.json definition
- ✅ Agent Selector service integration
- ✅ Marketplace query integration
- ✅ /activities/{id}/select-participants endpoint
- ✅ ActivityParticipants UI component
- ✅ End-to-end test: Activity → Participant selection

### Success Criteria
- Agent Selector analyzes activity requirements
- Marketplace query returns candidates
- Agent Selector scores and recommends participants
- Compute registry checked for availability
- Participants assigned and visible in UI

---

## Phase 4: Activity Facilitator - Conversation Management
**Duration:** 1-2 weeks  
**Focus:** Guide activity conversations to goal completion

### Goals
- Create Activity Facilitator coordinating agent
- Implement facilitation exchange system
- Test via UI: Start activity → See conversation → Goal met

### What We Build

#### 1. Activity Facilitator Agent Definition (Compute)

**Location:** `compute/data/compute/agents/coordinating/activity-facilitator-agent.json`

```json
{
  "agent_id": "activity-facilitator-v1",
  "name": "Activity Facilitator",
  "type": "coordinating",
  "description": "Guides activity conversations between agents to achieve goals",
  "capabilities": [
    "conversation_facilitation",
    "goal_assessment",
    "blocker_identification",
    "exchange_management"
  ],
  "system_prompt": "You are an Activity Facilitator. Your role is to guide a conversation to accomplish a specific activity goal.\n\nYou will:\n1. Frame the activity for participants\n2. Ask clarifying questions\n3. Guide the conversation forward\n4. Determine if the activity goal is met\n5. Identify blockers\n\nYou focus ONLY on THIS activity - you don't worry about the overall process.\n\nOutput format:\n{\n  \"next_action\": \"question|assess|conclude|identify_blocker\",\n  \"message\": \"Your message or question\",\n  \"goal_met\": true|false,\n  \"blocker\": \"Description if blocked\"\n}",
  "model": "gpt-4",
  "temperature": 0.6,
  "max_tokens": 1500,
  "provider": "openai"
}
```

#### 2. Facilitation Exchange Models

**Location:** `serving/models/process_map.py` (extend)

```python
class ExchangeIntent(str, Enum):
    FRAME = "frame"
    QUESTION = "question"
    ANSWER = "answer"
    CLARIFY = "clarify"
    ASSESS = "assess"
    CONCLUDE = "conclude"
    IDENTIFY_BLOCKER = "identify_blocker"

class Exchange(BaseModel):
    """One interaction in activity facilitation"""
    exchange_id: str
    activity_id: str
    timestamp: datetime
    speaker: str  # "facilitator" or agent_id
    message: str
    intent: ExchangeIntent
    
class FacilitationResult(BaseModel):
    """Outcome of facilitating an activity"""
    activity_id: str
    status: ActivityStatus  # goal_met, blocked, in_progress
    exchanges: List[Exchange]
    outputs: Dict[str, Any]
    blocker: Optional[str]
    duration: timedelta
```

#### 3. Facilitation Service (Serving)

**Location:** `serving/services/facilitation_service.py`

```python
class FacilitationService:
    """Manages activity facilitation conversations"""
    
    async def start_facilitation(
        self,
        session_id: str,
        activity_id: str
    ) -> FacilitationResult:
        """Begin facilitating an activity"""
        
        activity = await process_map_service.get_activity(session_id, activity_id)
        primary_agent = activity.assigned_agents[0]
        
        exchanges = []
        goal_met = False
        max_exchanges = 10  # Safety limit
        
        # Exchange 1: Facilitator frames the activity
        frame_message = await self.invoke_activity_facilitator(
            session_id=session_id,
            activity=activity,
            action="frame",
            conversation_history=[]
        )
        
        exchanges.append(Exchange(
            exchange_id=generate_id(),
            activity_id=activity_id,
            timestamp=datetime.utcnow(),
            speaker="facilitator",
            message=frame_message,
            intent=ExchangeIntent.FRAME
        ))
        
        # Facilitation loop
        for i in range(max_exchanges):
            # Invoke specialized agent (via existing task router)
            agent_response = await self.task_router.execute_agent(
                agent_id=primary_agent.agent_id,
                input_data={
                    "prompt": self.build_agent_prompt(activity, exchanges),
                    "session_id": session_id,
                    "activity_id": activity_id
                }
            )
            
            exchanges.append(Exchange(
                exchange_id=generate_id(),
                activity_id=activity_id,
                timestamp=datetime.utcnow(),
                speaker=primary_agent.agent_id,
                message=agent_response["result"],
                intent=ExchangeIntent.ANSWER
            ))
            
            # Facilitator assesses
            assessment = await self.invoke_activity_facilitator(
                session_id=session_id,
                activity=activity,
                action="assess",
                conversation_history=exchanges
            )
            
            if assessment["goal_met"]:
                goal_met = True
                break
            
            if assessment.get("blocker"):
                # Blocker identified
                return FacilitationResult(
                    activity_id=activity_id,
                    status=ActivityStatus.BLOCKED,
                    exchanges=exchanges,
                    outputs={},
                    blocker=assessment["blocker"],
                    duration=timedelta(seconds=(datetime.utcnow() - exchanges[0].timestamp).seconds)
                )
            
            # Continue conversation
            facilitator_message = assessment["message"]
            exchanges.append(Exchange(
                exchange_id=generate_id(),
                activity_id=activity_id,
                timestamp=datetime.utcnow(),
                speaker="facilitator",
                message=facilitator_message,
                intent=ExchangeIntent.QUESTION
            ))
        
        # Extract outputs from conversation
        outputs = self.extract_outputs(exchanges)
        
        return FacilitationResult(
            activity_id=activity_id,
            status=ActivityStatus.GOAL_MET if goal_met else ActivityStatus.IN_PROGRESS,
            exchanges=exchanges,
            outputs=outputs,
            blocker=None,
            duration=timedelta(seconds=(datetime.utcnow() - exchanges[0].timestamp).seconds)
        )
```

#### 4. API Endpoint

**Location:** `serving/api/process_maps.py` (extend)

```python
@router.post("/sessions/{session_id}/activities/{activity_id}/facilitate")
async def facilitate_activity(session_id: str, activity_id: str):
    """Begin facilitating an activity"""
    
    result = await facilitation_service.start_facilitation(
        session_id=session_id,
        activity_id=activity_id
    )
    
    # Update activity status
    await process_map_service.update_activity_status(
        session_id=session_id,
        activity_id=activity_id,
        status=result.status
    )
    
    # Store facilitation result
    await process_map_service.store_facilitation_result(
        session_id=session_id,
        activity_id=activity_id,
        result=result
    )
    
    return result

@router.get("/sessions/{session_id}/activities/{activity_id}/exchanges")
async def get_facilitation_exchanges(session_id: str, activity_id: str):
    """Get facilitation conversation for an activity"""
    
    result = await process_map_service.get_facilitation_result(
        session_id=session_id,
        activity_id=activity_id
    )
    
    return {
        "activity_id": activity_id,
        "exchanges": result.exchanges,
        "status": result.status
    }
```

#### 5. UI Component

**Location:** `serving/frontend/src/components/ActivityConversation.jsx`

**Features:**
- Show activity goal at top
- Display conversation thread:
  - Facilitator messages (blue)
  - Agent responses (green)
- Real-time updates as facilitation progresses
- Show status: in_progress, goal_met, blocked
- If blocked: Show blocker description
- Show facilitation duration
- View outputs

**Testing in Phase 4:**
```bash
# Via UI:
1. Navigate to facilitated session
2. Select activity with assigned participants
3. Click "Start Facilitation" button
4. Watch real-time conversation:
   - Facilitator: "We need to understand current retention. What data do you need?"
   - DataAnalyst: "I need customer database access and timeframe."
   - Facilitator: "Timeframe is last 12 months. Do you have database access?"
   - DataAnalyst: "No, I need credentials."
   - Facilitator: "We're blocked on database access."
5. See status change: proposed → in_progress → blocked
6. See blocker: "Database access needed"
7. View outputs in JSON panel
```

### Deliverables
- ✅ activity-facilitator-agent.json definition
- ✅ Exchange and FacilitationResult models
- ✅ FacilitationService with conversation loop
- ✅ /activities/{id}/facilitate endpoint
- ✅ /activities/{id}/exchanges endpoint
- ✅ ActivityConversation UI component
- ✅ End-to-end test: Activity → Facilitation → Goal met or blocked

### Success Criteria
- Activity Facilitator frames activities
- Conversation loops between facilitator and specialized agent
- Facilitator assesses goal completion
- Blockers identified and reported
- Full conversation visible in UI
- Activity status updates based on facilitation result

---

## Phase 5: Support Agents - Consistency, Progress, Synthesis
**Duration:** 1 week  
**Focus:** Add remaining coordinating agents

### Goals
- Create Consistency Manager agent
- Create Progress Reporter agent
- Create Result Synthesizer agent
- Test each via UI

### What We Build

#### 1. Consistency Manager Agent

**Location:** `compute/data/compute/agents/coordinating/consistency-manager-agent.json`

Monitors activity outputs for contradictions.

**UI Test:**
```
1. Complete Activity 3: "Current retention = 65%"
2. Complete Activity 7: "Based on 70% retention..."
3. Consistency Manager flags inconsistency
4. View in UI: Inconsistencies tab shows mismatch
5. Process Mapper creates reconciliation activity
```

#### 2. Progress Reporter Agent

**Location:** `compute/data/compute/agents/coordinating/progress-reporter-agent.json`

Tracks session progress and generates reports.

**UI Test:**
```
1. View session dashboard
2. See progress report:
   - Total activities: 7
   - Completed: 3
   - In progress: 2
   - Blocked: 1
   - Progress: 43%
3. See current focus: Activity 5
4. See blockers list
```

#### 3. Result Synthesizer Agent

**Location:** `compute/data/compute/agents/coordinating/result-synthesizer-agent.json`

Assembles final deliverable from all activity outputs.

**UI Test:**
```
1. All activities complete
2. Click "Generate Final Results"
3. Result Synthesizer:
   - Collects outputs from all 7 activities
   - Creates executive summary
   - Organizes key findings
   - Adds supporting data
4. View final deliverable in UI
```

### Deliverables
- ✅ 3 new coordinating agent definitions
- ✅ Services for each agent
- ✅ API endpoints for each feature
- ✅ UI components for each feature
- ✅ End-to-end tests for each agent

---

## Phase 6: Event Bus & Complete Integration
**Duration:** 1 week  
**Focus:** Event-driven coordination, complete flow

### Goals
- Implement event bus for coordinating agents
- Complete end-to-end facilitated process flow
- Build comprehensive session dashboard UI

### What We Build

#### 1. Event Bus (Serving)

**Location:** `serving/services/event_bus.py`

```python
class CoordinatingEvent(BaseModel):
    event_id: str
    event_type: str  # "ACTIVITY_PROPOSED", "BLOCKER_IDENTIFIED", etc.
    source_role: str
    session_id: str
    activity_id: Optional[str]
    data: Dict[str, Any]
    timestamp: datetime

class EventBus:
    """Routes events to coordinating agents"""
    
    def __init__(self):
        self.subscriptions = {}  # event_type → [agent_roles]
    
    def subscribe(self, agent_role: str, event_types: List[str]):
        """Register which events to route to which agent"""
        
    async def publish(self, event: CoordinatingEvent):
        """Route event to subscribed agents"""
        
        subscribers = self.subscriptions.get(event.event_type, [])
        
        for agent_role in subscribers:
            await self.route_to_coordinating_agent(
                agent_role=agent_role,
                event=event
            )
```

#### 2. Complete Facilitated Session Flow

```
User submits business goal
    ↓
Process Mapper creates initial map (3-5 activities)
    ↓ (event: ACTIVITY_PROPOSED)
Agent Selector recommends participants
    ↓ (event: PARTICIPANTS_RECOMMENDED)
Activity Facilitator begins facilitation
    ↓ (event: BLOCKER_IDENTIFIED)
Process Mapper creates new activity to resolve blocker
    ↓ (event: MAP_UPDATED)
Continue until all activities goal_met
    ↓
Result Synthesizer assembles final deliverable
    ↓
Session complete
```

#### 3. Comprehensive Dashboard UI

**Location:** `serving/frontend/src/components/FacilitatedSessionDashboard.jsx`

**Features:**
- Process map visualization (graph view)
- Activity timeline (evolution history)
- Current focus indicator
- Progress metrics
- Inconsistencies panel
- Facilitation history for each activity
- Final results viewer

**Testing Phase 6:**
```bash
# Complete end-to-end test via UI:
1. Create facilitated session: "Increase customer retention by 20%"
2. See Process Mapper create initial activities
3. Select Activity 1, assign participants
4. Start facilitation
5. See blocker: "Database access needed"
6. Process Mapper creates Activity 0: "Obtain database access"
7. Facilitate Activity 0 (resolves blocker)
8. Return to Activity 1 (now unblocked)
9. Complete Activity 1
10. See process map evolve (v1 → v2 → v3)
11. Consistency Manager flags inconsistency
12. Process Mapper creates reconciliation activity
13. Continue until all activities complete
14. Result Synthesizer generates final deliverable
15. View complete session report
```

### Deliverables
- ✅ EventBus implementation
- ✅ Complete coordinating agent workflow
- ✅ Comprehensive dashboard UI
- ✅ End-to-end facilitated session test
- ✅ Documentation update

---

## Testing Strategy - UI First

### Why UI Testing?

1. **Visual Feedback** - See process maps, conversations, progress
2. **Interactive** - Click through facilitation steps
3. **Real-time** - Watch conversations unfold
4. **Debugging** - Easy to spot issues visually
5. **Demonstrable** - Show progress to stakeholders

### UI Test Scenarios by Phase

**Phase 1:**
- Create process map manually
- View in graph UI
- See activities and dependencies

**Phase 2:**
- Create facilitated session
- See Process Mapper generate activities
- View initial process map

**Phase 3:**
- Select activity
- Click "Assign Participants"
- See Agent Selector recommendations
- View assigned agents

**Phase 4:**
- Click "Start Facilitation"
- Watch conversation thread
- See goal met or blocker
- View outputs

**Phase 5:**
- See progress report
- View inconsistencies
- Generate final results

**Phase 6:**
- Complete end-to-end flow
- Watch process evolve
- See all coordinating agents in action

---

## Reuse vs. New

### Reusing (80%)

| Component | What We Reuse | How |
|-----------|---------------|-----|
| Marketplace | Agent catalog, search | Agent Selector queries existing API |
| Serving - Sessions | Session management | Facilitated sessions extend existing model |
| Serving - Compute Registry | Instance registry | Agent Selector checks availability |
| Serving - Task Routing | Route to compute | Activity Facilitator executes agents |
| Serving - Storage | Storage API | Store process maps, facilitation history |
| Serving - Frontend | React UI, components | Extend with new components |
| Compute - Execution | Agent executor | Execute coordinating agents same way |
| Compute - LLM Integration | OpenAI/Anthropic/Mock | Coordinating agents use same providers |
| Compute - Registration | Register with serving | Advertise coordinating agents |

### Net New (20%)

| Component | What's New | Why |
|-----------|------------|-----|
| Serving - Models | ProcessMap, Activity, Exchange | Represent facilitated process |
| Serving - ProcessMapService | Storage and versioning | Track evolving maps |
| Serving - FacilitationService | Conversation management | Facilitate activities |
| Serving - EventBus | Event routing | Coordinate agents |
| Serving - CoordinatingTeamService | Agent routing | Route to coordinating agents |
| Serving - APIs | Process map endpoints | Expose facilitated process |
| Serving - UI | Process map viewer, conversation viewer | Visualize facilitation |
| Compute - Agents | 6 coordinating agent definitions | Define coordinating agents |

---

## Dual-Mode Support

Both v0.1.8 (pipeline) and v0.2.0 (facilitated) modes coexist:

```python
# Create traditional pipeline session (v0.1.8)
POST /api/v1/sessions/create
{
  "goal": "Generate report",
  "mode": "pipeline"
}
→ Uses ExecutionPipeline model
→ Predetermined steps
→ Fixed sequence

# Create facilitated session (v0.2.0)
POST /api/v1/sessions/create-facilitated
{
  "business_goal": "Increase retention",
  "mode": "facilitated"
}
→ Uses ProcessMap model
→ Emergent activities
→ Goal-oriented
```

**UI shows mode:**
```
Sessions List:
- Session 1: Generate Q4 report [Pipeline Mode]
- Session 2: Increase retention [Facilitated Mode] ← New
```

---

## Success Metrics

### Phase Completion Criteria

**Phase 1:**
- ✅ Can view process map in UI
- ✅ Activities show status colors
- ✅ Dependencies visible as arrows

**Phase 2:**
- ✅ Business goal → Initial process map works
- ✅ 3-5 activities generated
- ✅ Activities are goal-oriented

**Phase 3:**
- ✅ Activity → Participant recommendations works
- ✅ Marketplace search integrated
- ✅ Participants assigned

**Phase 4:**
- ✅ Facilitation conversation visible in UI
- ✅ Goal assessment works
- ✅ Blockers identified

**Phase 5:**
- ✅ Consistency Manager flags issues
- ✅ Progress Reporter shows metrics
- ✅ Result Synthesizer creates deliverable

**Phase 6:**
- ✅ Complete end-to-end flow works
- ✅ Process map evolves
- ✅ All coordinating agents coordinate

### Overall Success

- ✅ Can demonstrate facilitated session via UI
- ✅ Process maps evolve based on facilitation
- ✅ Activities are goal-oriented, not steps
- ✅ Coordinating agents work together
- ✅ Both pipeline and facilitated modes work
- ✅ Documentation complete

---

## Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Foundation | 1 week | 1 week |
| Phase 2: Process Mapper | 1 week | 2 weeks |
| Phase 3: Agent Selector | 1 week | 3 weeks |
| Phase 4: Activity Facilitator | 1-2 weeks | 4-5 weeks |
| Phase 5: Support Agents | 1 week | 5-6 weeks |
| Phase 6: Integration | 1 week | 6-7 weeks |

**Total: 6-7 weeks to complete v0.2.0**

Each phase delivers working, testable functionality via UI.

---

## Getting Started

### Immediate Next Steps

1. **Review this plan** - Adjust based on your preferences
2. **Set up development branch** - `git checkout -b feature/facilitated-process`
3. **Start Phase 1** - Models and storage foundation
4. **Test incrementally** - UI test after each phase

### Development Workflow

```bash
# For each phase:
1. Implement models/services/APIs
2. Build UI components
3. Test via UI
4. Commit
5. Demo progress
6. Move to next phase
```

### Documentation as We Go

Update these docs after each phase:
- `FACILITATED_PROCESS_ARCHITECTURE.md` - Implementation notes
- `EXECUTION_FLOW.md` - Flow examples
- Component READMEs - API changes
- UI guide - New components

---

## Questions to Resolve

1. **LLM Provider for Coordinating Agents:** Use OpenAI GPT-4, Anthropic Claude, or Mock for testing?
2. **Event Bus Implementation:** In-memory for now, or persistent queue (Redis, RabbitMQ)?
3. **Process Map Visualization:** Use existing graph library or custom SVG rendering?
4. **Facilitation Real-time Updates:** SSE (Server-Sent Events) or WebSocket for live conversation?
5. **Storage Backend:** Extend current filesystem storage or add database (PostgreSQL)?

---

## Conclusion

This plan:
- ✅ Builds incrementally on existing infrastructure
- ✅ Delivers testable value each phase
- ✅ UI-first testing approach
- ✅ Follows v0.2.0 architecture vision
- ✅ Avoids throw-away work
- ✅ Supports both pipeline and facilitated modes
- ✅ 6-7 weeks to complete implementation

**Ready to start with Phase 1?**

