# Pipeline Implementation - Build Plan

## ✅ What We've Built So Far

### 1. Architecture Design ✅
- **EXECUTION_PIPELINE_ARCHITECTURE.md** - Complete architectural specification
- Validated your concept - it's exactly right!

### 2. Data Models ✅
- **serving/models/pipeline.py** - Complete pipeline models:
  - `ExecutionPipeline` - Container for execution plan
  - `PipelineStep` - Individual step with dependencies
  - `PipelineStatus` and `StepStatus` enums
  - Helper methods for pipeline management

### 3. Pipeline Builder Agent ✅
- **compute/data/compute/agents/pipeline-builder-agent.json**
- Specialized agent that creates execution plans
- Returns structured JSON with steps and dependencies

### 4. Mock Provider Enhancement ✅
- Added "pipeline_building" response type
- Returns properly formatted pipeline JSON
- Detects pipeline-related prompts

## 🎯 What We Need to Build Next

### Phase 1: Coordinating Team Service

**File**: `serving/services/coordinating_team.py`

**Purpose**: Orchestrates the planning phase

**Key Methods**:
```python
class CoordinatingTeam:
    async def analyze_and_plan(goal: str, context: dict) -> ExecutionPipeline:
        # 1. Query available agents (from compute registry + marketplace)
        # 2. Invoke pipeline-builder agent
        # 3. Parse response into ExecutionPipeline
        # 4. Validate pipeline structure
        # 5. Return complete pipeline
```

### Phase 2: Pipeline Execution Engine

**File**: `serving/services/pipeline_executor.py`

**Purpose**: Executes pipeline steps in order

**Key Methods**:
```python
class PipelineExecutor:
    async def execute_pipeline(pipeline: ExecutionPipeline) -> ExecutionPipeline:
        # For each step (in order):
        #   1. Check dependencies satisfied
        #   2. Find compute instance with agent
        #   3. Route task to compute
        #   4. Store result in session
        #   5. Mark step complete
        #   6. Move to next step
```

### Phase 3: API Endpoints

**File**: `serving/api/pipelines.py`

**Endpoints**:
```python
POST /api/v1/pipelines/create          # Create pipeline from goal
POST /api/v1/pipelines/{id}/execute    # Execute a pipeline
GET  /api/v1/pipelines/{id}            # Get pipeline status
GET  /api/v1/pipelines/{id}/progress   # Get execution progress
```

### Phase 4: Session Integration

**Update**: `serving/api/sessions.py`

**Add**:
```python
POST /api/v1/sessions/create-with-pipeline  # Create session + pipeline
GET  /api/v1/sessions/{id}/pipeline         # Get session's pipeline
```

### Phase 5: Enhanced E2E Test

**File**: `test_pipeline_e2e.sh`

**Tests**:
1. Create pipeline from business request
2. Validate pipeline structure
3. Execute pipeline
4. Monitor progress
5. Verify results

## 🚀 Implementation Order

Given time constraints, let's build a **streamlined version** first:

### Minimal Viable Pipeline (MVP)

**Goal**: Demonstrate the full concept with working code

**What to build**:

1. **Simple coordinating team** in serving/api/pipelines.py:
   - Take business goal
   - Call pipeline-builder agent
   - Parse JSON response
   - Create ExecutionPipeline object

2. **Simple pipeline executor** in same file:
   - Loop through steps
   - Call compute for each step
   - Store results
   - Update status

3. **One endpoint** to test it all:
   - `POST /api/v1/pipelines/execute-from-goal`
   - Takes goal, builds pipeline, executes it
   - Returns complete results

4. **Updated E2E test**:
   - Call the endpoint
   - Show pipeline structure
   - Show execution progress
   - Show final results

### This MVP Demonstrates:
✅ Business request → Pipeline building
✅ Coordinating team with pipeline-builder agent
✅ Structured execution plan
✅ Step-by-step execution
✅ Dependency management
✅ Result aggregation

## 📝 Code Skeleton

### Minimal Pipeline API (`serving/api/pipelines.py`)

```python
from fastapi import APIRouter, HTTPException, Depends
from models.pipeline import *
from services.registry_service import ComputeRegistry, get_compute_registry
import httpx
import json

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

@router.post("/execute-from-goal")
async def execute_from_goal(
    request: PipelineRequest,
    registry: ComputeRegistry = Depends(get_compute_registry)
):
    """
    End-to-end pipeline execution:
    1. Build pipeline from goal
    2. Execute pipeline
    3. Return results
    """
    
    # Phase 1: Build pipeline
    pipeline_json = await build_pipeline_from_goal(
        goal=request.goal,
        context=request.context or {},
        registry=registry
    )
    
    # Phase 2: Execute pipeline
    results = await execute_pipeline_steps(
        pipeline=pipeline_json,
        registry=registry
    )
    
    return results

async def build_pipeline_from_goal(goal: str, context: dict, registry):
    """Use pipeline-builder agent to create execution plan."""
    # Find compute with pipeline-builder-v1
    # Call agent with goal + available agents
    # Parse JSON response
    # Return ExecutionPipeline
    pass

async def execute_pipeline_steps(pipeline: ExecutionPipeline, registry):
    """Execute each step in order."""
    # For each step:
    #   - Check dependencies
    #   - Find compute with agent
    #   - Execute
    #   - Store result
    #   - Update status
    pass
```

## 🎯 Decision Point

**Option A: Build Full Implementation**
- All services, proper separation
- ~2-3 hours of work
- Production-ready architecture

**Option B: Build MVP First**
- One file with everything
- ~30-45 minutes
- Proves the concept
- Can refactor later

**Recommendation**: Start with **Option B** (MVP), then refactor to **Option A** if needed.

## 📋 Next Steps

1. **Confirm approach** - MVP first or full implementation?
2. **Build coordinating team + executor** - In one file or separate services?
3. **Create API endpoint** - Simple or comprehensive?
4. **Update E2E test** - Show the full pipeline flow
5. **Test and iterate** - Make sure it works end-to-end

## 🎬 Ready to Code?

I can build either:

**A. MVP (Quick)** - One endpoint that does everything, proves concept
**B. Full (Proper)** - Separate services, clean architecture, production-ready

Which would you prefer? Or should I just build the MVP to get it working, then we can enhance it?

