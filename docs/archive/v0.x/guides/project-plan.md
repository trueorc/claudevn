# ClaudeVN Project Plan

## Project Goals

Build a functional local version of the ClaudeVN platform that demonstrates:
- Agent marketplace for discovery
- Orchestration engine for agent coordination
- A2A protocol integration for inter-instance communication
- Simple UI for submitting goals and monitoring execution

## Technology Stack

### Backend
- **Python** - Core orchestration engine and serving component
- **FastAPI** - REST APIs and A2A protocol endpoints
- **SQLite** - Local marketplace database and session state storage
- **Redis** (optional) - Message queue for async task handling

### Frontend
- **React** - UI for marketplace browsing and session monitoring
- **Node.js** - Development server and build tools
- **No TypeScript** - Keep it simple with JavaScript

### Infrastructure
- **Docker Compose** (optional) - For multi-instance testing
- **Single startup script** - `./start.sh` to launch entire system

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
│  - Marketplace browser                                   │
│  - Goal submission                                       │
│  - Session monitoring                                    │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP/WebSocket
┌─────────────────▼───────────────────────────────────────┐
│              Serving Component (Python/FastAPI)          │
│  - A2A broker                                            │
│  - Instance registry                                     │
│  - Marketplace API                                       │
│  - Session coordination                                  │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼────────┐  ┌──────▼─────────┐
│ Compute Engine │  │ Compute Engine │
│   Instance 1   │  │   Instance 2   │
│  (Python)      │  │  (Python)      │
│                │  │                │
│ - Coordinating │  │ - Specialized  │
│   Agents       │  │   Agents       │
│ - Tools        │  │ - Tools        │
└────────────────┘  └────────────────┘
```

## Core Components to Build

### 1. Marketplace Service
**Purpose:** Registry for agent and tool metadata

**Features:**
- CRUD operations for agents and tools
- Search and filtering by capabilities
- Agent Card generation (A2A format)
- Access control (whitelist/blacklist)

**Storage:** SQLite database with tables:
- `agents` - agent metadata, capabilities, endpoints
- `tools` - tool definitions and requirements
- `access_control` - instance permissions

### 2. Serving Component (A2A Broker)
**Purpose:** Central coordination and A2A message routing

**Features:**
- Compute engine instance registration
- A2A protocol endpoints (task submission, status, results)
- Agent Card serving
- Message routing between instances
- Session state management

**APIs:**
- `/register` - Instance registration
- `/a2a/agents` - Agent Card discovery
- `/a2a/tasks` - Task submission and status
- `/sessions` - Session CRUD and monitoring

### 3. Compute Engine
**Purpose:** Execute agent workloads locally

**Features:**
- Agent process management
- Tool invocation
- Local session state
- A2A client for cross-instance calls

**Components:**
- Agent runtime (LLM integration)
- Tool registry and executor
- State manager
- A2A client

### 4. Agents (Initial Set)

**Coordinating Agents:** (See `docs/coordinating-agents-spec.md` for details)
- `GoalDecomposerAgent` - Analyzes goals and creates execution plans
- `TeamAssemblerAgent` - Selects optimal agents from marketplace
- `ExecutionCoordinatorAgent` - Manages task execution and agent invocation
- `ProgressTrackerAgent` - Monitors progress and identifies issues
- `ResultSynthesizerAgent` - Assembles final deliverables

**Specialized Agents:**
- `DataAnalystAgent` - Analyzes data and generates insights
- `WriterAgent` - Creates documents and summaries
- `ResearcherAgent` - Gathers information from external sources
- `CoderAgent` - Writes and modifies code

### 5. Tools (Initial Set)
- `FileReader` - Read local files
- `FileWriter` - Write local files
- `WebSearch` - Search the internet (mock initially)
- `Calculator` - Basic calculations
- `DataProcessor` - CSV/JSON manipulation

### 6. Frontend UI
**Pages:**
- **Marketplace** - Browse and search agents/tools
- **Submit Goal** - Text input for business process goals
- **Sessions** - List of active and completed sessions
- **Session Detail** - Execution plan visualization, agent activity, results

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
**Goal:** Basic infrastructure running locally

- [ ] Project structure and dependencies
- [ ] Marketplace service with SQLite
- [ ] Serving component with basic APIs
- [ ] Single compute engine instance
- [ ] Startup script (`./start.sh`)

**Deliverable:** Can register agents in marketplace and query via API

### Phase 2: Agent Runtime (Week 3-4)
**Goal:** Execute simple agent workflows

- [ ] Agent runtime with LLM integration (OpenAI API)
- [ ] Tool registry and execution framework
- [ ] Basic coordinating agent (goal decomposition)
- [ ] Basic specialized agent (simple task execution)
- [ ] Session state management

**Deliverable:** Submit a simple goal, watch agent execute and return result

### Phase 3: A2A Protocol (Week 5-6)
**Goal:** Multi-instance communication

- [ ] A2A protocol implementation (task submission, status, completion)
- [ ] Agent Card generation and serving
- [ ] A2A client in compute engine
- [ ] Message routing in serving component
- [ ] Second compute engine instance

**Deliverable:** Coordinating agent on Instance 1 invokes specialized agent on Instance 2

### Phase 4: Frontend UI (Week 7-8)
**Goal:** Visual interface for interaction

- [ ] React app setup
- [ ] Marketplace browser page
- [ ] Goal submission form
- [ ] Session list and detail pages
- [ ] WebSocket for real-time updates

**Deliverable:** Full UI for submitting goals and monitoring execution

### Phase 5: Polish & Integration (Week 9-10)
**Goal:** End-to-end workflows

- [ ] Add more agents and tools
- [ ] Improve execution plan visualization
- [ ] Error handling and recovery
- [ ] Logging and observability
- [ ] Documentation updates

**Deliverable:** Demo-ready system with multiple working scenarios

## Development Principles

### Keep It Simple
- Start with in-memory state, add persistence later
- Mock external services initially
- Single-file modules until complexity demands splitting
- Avoid premature optimization

### Stay Functional
- Prioritize working features over perfect code
- Hardcode reasonable defaults
- Skip edge cases initially
- Focus on happy path

### No Tests (Initially)
- Manual testing only during rapid development
- Document test scenarios for future
- Add tests once architecture stabilizes

### Single Startup (for all-in-one development)
- `examples/all-in-one/start.sh` launches all components
- Each component has its own `start.sh` for independent deployment
- Environment variables in component-specific `.env` files
- Clear console output showing what's running
- Graceful shutdown with Ctrl+C

## File Structure

**Note:** See `docs/project-structure.md` for detailed structure. Components are independently deployable.

```
claudevn/
├── docs/                       # All documentation
├── marketplace/                # Marketplace service (independent)
│   ├── start.sh
│   ├── requirements.txt
│   ├── main.py
│   └── frontend/              # Optional UI
├── serving/                    # Serving component (independent)
│   ├── start.sh
│   ├── requirements.txt
│   ├── main.py
│   └── frontend/              # Optional monitoring UI
├── compute/                    # Compute engine (independent)
│   ├── start.sh
│   ├── requirements.txt
│   ├── config.json.example
│   ├── main.py
│   ├── agents/
│   │   ├── coordinating/      # 5 coordinating agents
│   │   └── specialized/       # Specialized agents
│   └── tools/
├── shared/                     # Shared library
│   └── claudevn_shared/
├── examples/                   # Deployment examples
│   ├── all-in-one/
│   ├── cloud-marketplace/
│   └── hybrid/
└── scripts/                    # Utility scripts
```

## Configuration

### Environment Variables (.env)
```bash
# LLM Configuration
OPENAI_API_KEY=your_key_here
LLM_MODEL=gpt-4

# Service Ports
MARKETPLACE_PORT=8001
SERVING_PORT=8002
COMPUTE_PORT_1=8003
COMPUTE_PORT_2=8004
FRONTEND_PORT=3000

# Database
DATABASE_PATH=./data/marketplace.db

# Logging
LOG_LEVEL=INFO
```

## Success Criteria

**Phase 1 Complete:** Can add agents to marketplace and retrieve them via API  
**Phase 2 Complete:** Can submit "Analyze this CSV file" and get results  
**Phase 3 Complete:** Agent on one instance calls agent on another instance  
**Phase 4 Complete:** Can do everything through the UI  
**Phase 5 Complete:** Can demo 3+ real business process scenarios  

## Next Steps

1. Create detailed technical specifications for each component
2. Set up project structure and dependencies
3. Implement Phase 1 foundation
4. Iterate based on learnings

## Notes

- Focus on local development; cloud deployment comes later
- A2A protocol compliance is important but start with minimal implementation
- Agent intelligence can be simple initially; focus on orchestration mechanics
- Keep documentation updated as we build

