# ClaudeVN Technical Specifications

## Component Specifications

### 1. Marketplace Service

**Technology:** Python + FastAPI + SQLite

**Database Schema:**

```sql
-- Agents table
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    capabilities TEXT,  -- JSON array
    agent_type TEXT,    -- 'coordinating' or 'specialized'
    endpoint_url TEXT,
    auth_requirements TEXT,  -- JSON object
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Tools table
CREATE TABLE tools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tool_type TEXT,     -- 'mcp' or 'ecosystem'
    parameters TEXT,    -- JSON schema
    requirements TEXT,  -- JSON object
    created_at TIMESTAMP
);

-- Access control table
CREATE TABLE access_control (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT,
    resource_type TEXT,  -- 'agent' or 'tool'
    resource_id TEXT,
    access_level TEXT,   -- 'allow' or 'deny'
    created_at TIMESTAMP
);
```

**API Endpoints:**

```
POST   /api/agents              Create agent
GET    /api/agents              List agents (with filters)
GET    /api/agents/{id}         Get agent details
PUT    /api/agents/{id}         Update agent
DELETE /api/agents/{id}         Delete agent
GET    /api/agents/{id}/card    Get A2A Agent Card

POST   /api/tools               Create tool
GET    /api/tools               List tools
GET    /api/tools/{id}          Get tool details

POST   /api/access              Set access control
GET    /api/access/{instance}   Get access rules for instance
```

**Agent Card Format (A2A):**

```json
{
  "name": "ProjectManagerAgent",
  "version": "1.0.0",
  "description": "Decomposes business goals into execution plans",
  "capabilities": [
    "goal_decomposition",
    "team_assembly",
    "progress_tracking"
  ],
  "serviceEndpoint": "http://localhost:8003/a2a",
  "authentication": {
    "type": "bearer",
    "required": false
  },
  "inputTypes": ["text/plain", "application/json"],
  "outputTypes": ["application/json"]
}
```

---

### 2. Serving Component (A2A Broker)

**Technology:** Python + FastAPI + Redis (optional) + Blob Storage

**Responsibilities:**
- Instance registry
- A2A message routing
- Session coordination
- Agent Card serving
- Blob storage for data sharing
- Session context management

**Storage Backend:**

```python
# Filesystem backend (default)
STORAGE_BACKEND=filesystem
STORAGE_PATH=./data/blobs
STORAGE_TTL=3600  # 1 hour
STORAGE_MAX_SIZE=104857600  # 100MB

# S3-compatible backend (Phase 3)
STORAGE_BACKEND=s3
S3_BUCKET=claudevn-blobs
S3_ENDPOINT=https://s3.amazonaws.com
```

**Session Database Schema:**

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    context TEXT,  -- JSON: execution_plan, task_results, data_refs, metadata
    status TEXT,   -- 'pending', 'in_progress', 'completed', 'failed', 'cancelled'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**API Endpoints:**

```
# Instance Management
POST   /api/instances/register     Register compute engine
DELETE /api/instances/{id}         Unregister instance
GET    /api/instances              List registered instances

# A2A Protocol Endpoints
GET    /a2a/agents                 List available agents (Agent Cards)
GET    /a2a/agents/{id}            Get specific Agent Card
POST   /a2a/agents/{id}/tasks      Submit task to agent
GET    /a2a/tasks/{task_id}        Get task status
GET    /a2a/tasks/{task_id}/stream Server-Sent Events for task updates

# Session Management
POST   /api/sessions               Create session
GET    /api/sessions               List sessions
GET    /api/sessions/{id}          Get session details
DELETE /api/sessions/{id}          Cancel session
PATCH  /api/sessions/{id}/status   Update session status
POST   /api/sessions/{id}/task_results  Add task result
POST   /api/sessions/{id}/data_refs     Add data reference
PUT    /api/sessions/{id}/execution_plan Set execution plan

# Blob Storage
POST   /api/storage/upload         Upload blob
GET    /api/storage/{blob_id}      Download blob
GET    /api/storage/{blob_id}/metadata  Get blob metadata
DELETE /api/storage/{blob_id}      Delete blob
GET    /api/storage/session/{id}/blobs  List session blobs
POST   /api/storage/cleanup        Clean up expired blobs
GET    /api/storage/stats          Get storage statistics
```

**Instance Registration:**

```json
{
  "instance_id": "compute-1",
  "host": "localhost",
  "port": 8003,
  "capabilities": ["coordinating_agents"],
  "agents": ["ProjectManagerAgent", "TeamCoordinatorAgent"],
  "status": "online"
}
```

**A2A Task Submission:**

```json
{
  "input": {
    "type": "text/plain",
    "content": "Analyze quarterly sales data and create summary"
  },
  "context": {
    "session_id": "session-123",
    "parent_task_id": "task-456"
  }
}
```

**A2A Task Response:**

```json
{
  "task_id": "task-789",
  "status": "submitted",
  "agent_id": "DataAnalysisAgent",
  "created_at": "2025-11-21T10:30:00Z",
  "status_url": "/a2a/tasks/task-789",
  "stream_url": "/a2a/tasks/task-789/stream"
}
```

**A2A Task States:**
- `submitted` - Task received, queued
- `working` - Agent actively processing
- `input_required` - Agent needs additional input
- `completed` - Task finished successfully
- `failed` - Task failed with error
- `canceled` - Task was canceled

---

### 3. Compute Engine

**Technology:** Python

**Components:**

1. **Agent Runtime**
   - LLM integration with provider abstraction
   - Multi-provider support (OpenAI, Anthropic, Ollama)
   - Automatic fallback and retry logic
   - Prompt management
   - Response parsing
   - Token usage tracking

2. **Tool Registry**
   - Tool discovery
   - Parameter validation
   - Execution wrapper

3. **State Manager**
   - Session state storage
   - Context management
   - Result caching

4. **A2A Client**
   - Task submission to other instances
   - Status polling
   - Result retrieval

5. **LLM Client** (see detailed spec below)
   - Provider abstraction layer
   - Multi-provider configuration
   - Fallback and retry logic
   - Cost estimation and tracking

**Configuration:**

```json
{
  "instance_id": "compute-1",
  "serving_url": "http://localhost:8002",
  "agents": [
    {
      "class": "ProjectManagerAgent",
      "enabled": true,
      "config": {
        "model": "gpt-4",
        "temperature": 0.7
      }
    }
  ],
  "tools": [
    "FileReader",
    "FileWriter",
    "Calculator"
  ]
}
```

**Agent Interface:**

```python
class BaseAgent:
    def __init__(self, agent_id, config):
        self.agent_id = agent_id
        self.config = config
        self.llm = LLMClient(config)
        
    async def execute(self, task_input, context):
        """Execute agent task"""
        pass
        
    def get_capabilities(self):
        """Return agent capabilities"""
        pass
        
    def get_agent_card(self):
        """Generate A2A Agent Card"""
        pass
```

**Tool Interface:**

```python
class BaseTool:
    def __init__(self, tool_id, config):
        self.tool_id = tool_id
        self.config = config
        
    def get_schema(self):
        """Return tool parameter schema"""
        pass
        
    async def execute(self, parameters):
        """Execute tool with parameters"""
        pass
```

---

### 4. LLM Client Specification

**Technology:** Python with provider-specific libraries (openai, anthropic, etc.)

**Architecture:**

```
LLMClient
    ├── Provider 1 (OpenAI)
    │   ├── generate()
    │   ├── stream()
    │   ├── estimate_tokens()
    │   └── estimate_cost()
    ├── Provider 2 (Anthropic)
    └── Provider 3 (Ollama)
```

**Configuration:**

```json
{
  "agents": {
    "GoalDecomposerAgent": {
      "llm_providers": [
        {
          "provider": "openai",
          "model": "gpt-4",
          "temperature": 0.7,
          "max_tokens": 2000,
          "priority": 1
        },
        {
          "provider": "anthropic",
          "model": "claude-3-sonnet",
          "temperature": 0.7,
          "priority": 2
        }
      ],
      "fallback_strategy": "next_priority",
      "max_retries": 3,
      "retry_delay": 1.0
    }
  }
}
```

**LLM Provider Interface:**

```python
class BaseLLMProvider(ABC):
    async def generate(self, prompt: str, **kwargs) -> LLMResponse
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]
    def estimate_tokens(self, text: str) -> int
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float
    def update_stats(self, response: LLMResponse, failed: bool = False)
    def get_stats(self) -> LLMUsageStats
```

**LLM Response Format:**

```python
@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    cost_estimate: Optional[float] = None
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**Supported Providers:**

| Provider | Status | Models | Streaming | Token Estimation | Cost Tracking |
|----------|--------|--------|-----------|------------------|---------------|
| OpenAI | ✅ Implemented | GPT-4, GPT-3.5-turbo | ✅ Yes | ✅ tiktoken | ✅ Yes |
| Anthropic | 🚧 Phase 2 | Claude 3 | 🚧 Planned | 🚧 Planned | 🚧 Planned |
| Ollama | 🚧 Phase 3 | Local models | 🚧 Planned | 🚧 Planned | N/A |

**Fallback Behavior:**

1. Try primary provider with exponential backoff (up to max_retries)
2. On failure, move to next provider by priority
3. Retryable errors: 429, 500, 502, 503, 504, timeouts
4. Non-retryable errors: 401, 400, 404

**Usage Statistics:**

```python
@dataclass
class LLMUsageStats:
    provider: LLMProvider
    model: str
    total_requests: int = 0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    failed_requests: int = 0
```

**Environment Variables:**

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic (Phase 2)
ANTHROPIC_API_KEY=sk-ant-...

# Ollama (Phase 3)
OLLAMA_BASE_URL=http://localhost:11434
```

---

### 5. Data Sharing & Storage

**Tiered Storage Strategy:**

**Tier 1: Message-Embedded (< 1MB)**
- Data embedded directly in A2A task messages
- Base64 encoding for binary data
- No external storage needed

**Tier 2: Serving Component Blob Storage (1MB - 100MB)**
- Temporary blob storage with TTL
- Upload/download via HTTP API
- Filesystem or S3-compatible backend
- Automatic cleanup

**Tier 3: External Storage URLs (> 100MB)**
- Reference external URLs (S3, GCS, etc.)
- Compute instances fetch directly
- Requires credentials management

**Blob Storage Implementation:**

```python
class StorageBackend(ABC):
    async def upload(data: bytes, blob_id: str, ...) -> BlobMetadata
    async def download(blob_id: str) -> bytes
    async def get_metadata(blob_id: str) -> BlobMetadata
    async def delete(blob_id: str) -> bool
    async def list_by_session(session_id: str) -> list[BlobMetadata]
    async def cleanup_expired() -> int
```

**Blob Metadata:**

```python
@dataclass
class BlobMetadata:
    blob_id: str
    size: int
    mime_type: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    session_id: Optional[str] = None
    filename: Optional[str] = None
```

**Session Context Format:**

```json
{
  "session_id": "session-123",
  "status": "in_progress",
  "execution_plan": {
    "plan_id": "plan-456",
    "tasks": [...]
  },
  "task_results": {
    "task-1": {"status": "completed", "output": {...}},
    "task-2": {"status": "in_progress", "output": null}
  },
  "data_refs": {
    "uploaded_file": {
      "type": "blob",
      "url": "http://serving:8002/api/storage/blob-789",
      "size": 1048576,
      "mime_type": "text/csv"
    },
    "intermediate_data": {
      "type": "inline",
      "content": {...}
    }
  },
  "metadata": {
    "started_at": "2025-11-21T10:00:00Z",
    "user_id": "user-123",
    "total_cost": 0.0
  }
}
```

---

### 6. Agent Implementations

**Coordinating Agent Example:**

```python
from compute.runtime.llm_client import create_llm_client_from_config

class ProjectManagerAgent(BaseAgent):
    """
    Decomposes goals into execution plans and manages specialized agents
    """
    
    capabilities = [
        "goal_decomposition",
        "execution_planning",
        "team_assembly",
        "progress_tracking"
    ]
    
    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        
        # Initialize LLM client with multi-provider support
        self.llm = create_llm_client_from_config(
            agent_config=config,
            api_keys={
                "openai": os.getenv("OPENAI_API_KEY"),
                "anthropic": os.getenv("ANTHROPIC_API_KEY")
            }
        )
    
    async def execute(self, task_input, context):
        # 1. Analyze goal using LLM
        goal = task_input['content']
        
        # 2. Query marketplace for available agents
        available_agents = await self.query_marketplace()
        
        # 3. Create execution plan using LLM
        prompt = self.build_planning_prompt(goal, available_agents)
        response = await self.llm.generate(prompt)
        plan = self.parse_plan(response.content)
        
        # Track cost
        context['metadata']['llm_cost'] = context['metadata'].get('llm_cost', 0.0)
        context['metadata']['llm_cost'] += response.cost_estimate
        
        # 4. Execute plan steps
        results = await self.execute_plan(plan, context)
        
        # 5. Assemble final output
        return self.assemble_results(results)
```

**Specialized Agent Example:**

```python
class DataAnalysisAgent(BaseAgent):
    """
    Analyzes data and generates insights
    """
    
    capabilities = [
        "data_analysis",
        "statistical_analysis",
        "visualization"
    ]
    
    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        self.llm = create_llm_client_from_config(config, api_keys={...})
    
    async def execute(self, task_input, context):
        # 1. Download data from blob storage if needed
        data_ref = context.get('data_refs', {}).get('input_file')
        if data_ref and data_ref['type'] == 'blob':
            data_bytes = await self.download_blob(data_ref['url'])
            data = self.parse_csv(data_bytes)
        else:
            data = await self.load_data(task_input)
        
        # 2. Perform analysis using tools
        stats = await self.invoke_tool('DataProcessor', {
            'operation': 'statistics',
            'data': data
        })
        
        # 3. Generate insights using LLM with fallback
        prompt = self.build_analysis_prompt(stats)
        response = await self.llm.generate(prompt)
        
        # 4. Upload results to blob storage if large
        if len(response.content) > 1_000_000:  # > 1MB
            blob_url = await self.upload_blob(
                response.content.encode(),
                session_id=context['session_id']
            )
            output_ref = {
                'type': 'blob',
                'url': blob_url,
                'size': len(response.content)
            }
        else:
            output_ref = {
                'type': 'inline',
                'content': response.content
            }
        
        return {
            'statistics': stats,
            'insights': output_ref,
            'tokens_used': response.tokens_used,
            'cost': response.cost_estimate
        }
```

---

### 5. Execution Plan Format

**Structure:**

```json
{
  "plan_id": "plan-123",
  "session_id": "session-456",
  "goal": "Analyze quarterly sales and create presentation",
  "created_at": "2025-11-21T10:00:00Z",
  "status": "in_progress",
  "tasks": [
    {
      "task_id": "task-1",
      "name": "Load sales data",
      "agent": "DataAnalysisAgent",
      "status": "completed",
      "dependencies": [],
      "input": {"file": "sales_q4.csv"},
      "output": {"data": {...}},
      "started_at": "2025-11-21T10:01:00Z",
      "completed_at": "2025-11-21T10:02:00Z"
    },
    {
      "task_id": "task-2",
      "name": "Analyze trends",
      "agent": "DataAnalysisAgent",
      "status": "in_progress",
      "dependencies": ["task-1"],
      "input": {"data_ref": "task-1.output.data"},
      "started_at": "2025-11-21T10:02:30Z"
    },
    {
      "task_id": "task-3",
      "name": "Create presentation",
      "agent": "WriterAgent",
      "status": "pending",
      "dependencies": ["task-2"],
      "input": {"insights_ref": "task-2.output.insights"}
    }
  ]
}
```

---

### 6. Frontend Application

**Technology:** React + JavaScript

**Pages:**

1. **Marketplace Page** (`/marketplace`)
   - Agent list with search/filter
   - Tool list
   - Agent detail modal

2. **Submit Goal Page** (`/submit`)
   - Text area for goal input
   - File upload (optional)
   - Agent selection (optional)
   - Submit button

3. **Sessions Page** (`/sessions`)
   - List of sessions (active, completed, failed)
   - Status indicators
   - Quick actions (view, cancel)

4. **Session Detail Page** (`/sessions/:id`)
   - Execution plan visualization (graph or timeline)
   - Task status list
   - Agent activity log
   - Results display

**API Client:**

```javascript
// api/client.js
const API_BASE = 'http://localhost:8002';

export const api = {
  // Marketplace
  getAgents: () => fetch(`${API_BASE}/api/agents`).then(r => r.json()),
  getTools: () => fetch(`${API_BASE}/api/tools`).then(r => r.json()),
  
  // Sessions
  createSession: (goal) => 
    fetch(`${API_BASE}/api/sessions`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({goal})
    }).then(r => r.json()),
    
  getSessions: () => 
    fetch(`${API_BASE}/api/sessions`).then(r => r.json()),
    
  getSession: (id) => 
    fetch(`${API_BASE}/api/sessions/${id}`).then(r => r.json()),
    
  // WebSocket for real-time updates
  connectSessionStream: (sessionId, onUpdate) => {
    const ws = new WebSocket(`ws://localhost:8002/ws/sessions/${sessionId}`);
    ws.onmessage = (event) => onUpdate(JSON.parse(event.data));
    return ws;
  }
};
```

---

## Startup Script

**`start.sh`:**

```bash
#!/bin/bash

echo "🚀 Starting ClaudeVN..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Create data directory
mkdir -p data

# Start backend services
echo "📦 Starting Marketplace Service..."
cd backend/marketplace && python main.py &
MARKETPLACE_PID=$!

echo "🔀 Starting Serving Component..."
cd ../serving && python main.py &
SERVING_PID=$!

echo "⚙️  Starting Compute Engine Instance 1..."
cd ../compute && python main.py --instance-id compute-1 --port 8003 &
COMPUTE1_PID=$!

echo "⚙️  Starting Compute Engine Instance 2..."
python main.py --instance-id compute-2 --port 8004 &
COMPUTE2_PID=$!

# Start frontend
echo "🎨 Starting Frontend..."
cd ../../frontend && npm start &
FRONTEND_PID=$!

echo ""
echo "✅ ClaudeVN is running!"
echo "   Marketplace:  http://localhost:8001"
echo "   Serving:      http://localhost:8002"
echo "   Compute 1:    http://localhost:8003"
echo "   Compute 2:    http://localhost:8004"
echo "   Frontend:     http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

# Trap Ctrl+C and cleanup
trap "echo '🛑 Stopping ClaudeVN...'; kill $MARKETPLACE_PID $SERVING_PID $COMPUTE1_PID $COMPUTE2_PID $FRONTEND_PID; exit" INT

# Wait for all processes
wait
```

---

## Development Workflow

### Initial Setup
```bash
# Clone repo
git clone git@github.com:Guarrdon/claudevn.git
cd claudevn

# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies
cd frontend && npm install && cd ..

# Create .env file
cp .env.example .env
# Edit .env with your OpenAI API key

# Start everything
./start.sh
```

### Daily Development
```bash
# Start system
./start.sh

# Make changes to code
# Services auto-reload (use --reload flag in FastAPI)

# Check logs in terminal
# Test via UI at http://localhost:3000
```

### Adding New Agents
1. Create agent class in `backend/agents/`
2. Register in compute engine config
3. Add to marketplace via API or seed script
4. Test via UI

### Adding New Tools
1. Create tool class in `backend/tools/`
2. Register in compute engine config
3. Add to marketplace via API or seed script
4. Test via agent invocation

---

## Next Steps

1. Set up project structure
2. Implement Phase 1 (Foundation)
3. Create seed data for marketplace
4. Build first coordinating agent
5. Build first specialized agent
6. Test end-to-end flow


