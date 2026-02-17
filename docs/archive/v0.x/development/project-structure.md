# ClaudeVN Project Structure

## Design Principle: Independent Deployable Components

Each component (Marketplace, Serving, Compute) is a standalone service that can be deployed independently. This supports various deployment topologies:

- **Cloud Marketplace** + **Local Compute Instances**
- **Multiple Marketplaces** (global + private) + **Single Serving Component**
- **Distributed Serving** + **Edge Compute Instances**
- **All-in-one local** for development/testing

## Repository Structure

```
claudevn/
├── docs/                           # All documentation
│   ├── agent-marketplace-orchestration-design.md
│   ├── platform-overview.md
│   ├── project-plan.md
│   ├── technical-specifications.md
│   └── project-structure.md
│
├── marketplace/                    # Marketplace Service (Independent)
│   ├── README.md
│   ├── requirements.txt
│   ├── .env.example
│   ├── start.sh
│   ├── main.py
│   ├── api/
│   │   ├── agents.py
│   │   ├── tools.py
│   │   └── access.py
│   ├── db/
│   │   ├── models.py
│   │   ├── migrations/
│   │   └── seed.py
│   ├── frontend/                   # Optional marketplace UI
│   │   ├── package.json
│   │   ├── public/
│   │   └── src/
│   └── tests/
│
├── serving/                        # Serving Component (Independent)
│   ├── README.md
│   ├── requirements.txt
│   ├── .env.example
│   ├── start.sh
│   ├── main.py
│   ├── api/
│   │   ├── sessions/              # Modular sessions API
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── dependencies.py
│   │   │   ├── utils.py
│   │   │   ├── crud.py
│   │   │   ├── status.py
│   │   │   ├── results.py
│   │   │   ├── data_refs.py
│   │   │   ├── execution_plan.py
│   │   │   └── stats.py
│   │   ├── storage_api/           # Modular storage API
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── dependencies.py
│   │   │   ├── upload.py
│   │   │   ├── download.py
│   │   │   ├── metadata.py
│   │   │   ├── session.py
│   │   │   └── management.py
│   │   ├── instances.py           # Instance management (future)
│   │   └── a2a.py                 # A2A protocol (future)
│   ├── broker/
│   │   ├── router.py
│   │   ├── registry.py
│   │   ├── state.py
│   │   └── session_context.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── backend.py
│   │   └── filesystem.py
│   ├── frontend/                   # Optional monitoring UI
│   │   ├── package.json
│   │   ├── public/
│   │   └── src/
│   └── tests/
│
├── compute/                        # Compute Engine (Independent)
│   ├── README.md
│   ├── requirements.txt
│   ├── .env.example
│   ├── start.sh
│   ├── main.py
│   ├── config.json.example
│   ├── runtime/
│   │   ├── agent_runtime.py
│   │   ├── tool_runtime.py
│   │   ├── state_manager.py
│   │   ├── llm_client.py          # Main LLM client
│   │   └── providers/              # LLM provider implementations
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── registry.py         # Provider auto-discovery
│   │       ├── openai_provider.py
│   │       ├── _template.py        # Template for new providers
│   │       ├── anthropic_provider.py  # (future)
│   │       └── ollama_provider.py     # (future)
│   ├── agents/
│   │   ├── base.py
│   │   ├── coordinating/
│   │   │   ├── goal_decomposer.py
│   │   │   ├── team_assembler.py
│   │   │   ├── execution_coordinator.py
│   │   │   ├── progress_tracker.py
│   │   │   └── result_synthesizer.py
│   │   └── specialized/
│   │       ├── data_analyst.py
│   │       ├── writer.py
│   │       ├── researcher.py
│   │       └── coder.py
│   ├── tools/
│   │   ├── base.py
│   │   ├── file_ops.py
│   │   ├── web_search.py
│   │   ├── calculator.py
│   │   └── data_processor.py
│   ├── a2a/
│   │   ├── client.py
│   │   └── protocol.py
│   └── tests/
│
├── shared/                         # Shared utilities (library)
│   ├── README.md
│   ├── setup.py
│   ├── claudevn_shared/
│   │   ├── __init__.py
│   │   ├── models.py           # Common data models
│   │   ├── a2a_types.py        # A2A protocol types
│   │   ├── config.py           # Configuration helpers
│   │   └── utils.py
│   └── tests/
│
├── examples/                       # Deployment examples
│   ├── all-in-one/
│   │   ├── docker-compose.yml
│   │   ├── .env.example
│   │   └── start.sh
│   ├── cloud-marketplace/
│   │   ├── docker-compose.yml
│   │   └── README.md
│   ├── local-compute/
│   │   ├── config.json
│   │   └── start.sh
│   └── hybrid/
│       ├── docker-compose.yml
│       └── README.md
│
├── scripts/                        # Utility scripts
│   ├── setup-dev.sh               # Set up local development
│   ├── seed-marketplace.py        # Seed marketplace with agents
│   └── test-deployment.sh         # Test a deployment
│
├── .gitignore
├── README.md
└── LICENSE
```

## Component Independence

### Marketplace Service

**Can run standalone with:**
- SQLite database (or PostgreSQL for production)
- Optional frontend for browsing
- No dependencies on Serving or Compute

**Configuration:**
```bash
# marketplace/.env
DATABASE_URL=sqlite:///./data/marketplace.db
PORT=8001
CORS_ORIGINS=*
AUTH_ENABLED=false
```

**Startup:**
```bash
cd marketplace
pip install -r requirements.txt
./start.sh
```

**Access:**
- API: `http://localhost:8001`
- UI: `http://localhost:8001/ui` (if frontend enabled)

---

### Serving Component

**Can run standalone with:**
- Configuration pointing to one or more Marketplaces
- No Compute instances initially (they register dynamically)
- Optional monitoring UI

**Configuration:**
```bash
# serving/.env
PORT=8002
MARKETPLACE_URLS=http://localhost:8001,https://global-marketplace.claudevn.io
SESSION_STORE=sqlite:///./data/sessions.db
REDIS_URL=redis://localhost:6379  # Optional for distributed setups
AUTH_ENABLED=false
```

**Startup:**
```bash
cd serving
pip install -r requirements.txt
./start.sh
```

**Access:**
- API: `http://localhost:8002`
- A2A Endpoint: `http://localhost:8002/a2a`
- UI: `http://localhost:8002/ui` (if frontend enabled)

---

### Compute Engine

**Can run standalone with:**
- Configuration pointing to Serving Component(s)
- Configuration pointing to Marketplace(s)
- Agent and tool implementations
- Multiple instances can run on same machine (different ports)

**Configuration:**
```json
// compute/config.json
{
  "instance_id": "compute-local-1",
  "port": 8003,
  "serving_urls": [
    "http://localhost:8002",
    "https://cloud-serving.claudevn.io"
  ],
  "marketplace_urls": [
    "http://localhost:8001",
    "https://global-marketplace.claudevn.io"
  ],
  "marketplace_priority": "local_first",
  "agents": {
    "enabled": [
      "GoalDecomposerAgent",
      "TeamAssemblerAgent",
      "DataAnalystAgent"
    ],
    "config": {
      "llm_provider": "openai",
      "model": "gpt-4",
      "temperature": 0.7
    }
  },
  "tools": {
    "enabled": [
      "FileReader",
      "FileWriter",
      "Calculator",
      "DataProcessor"
    ]
  }
}
```

**Startup:**
```bash
cd compute
pip install -r requirements.txt
./start.sh --config config.json
```

**Multiple instances:**
```bash
# Instance 1 - Coordinating agents
./start.sh --config config-coordinator.json --port 8003

# Instance 2 - Specialized agents
./start.sh --config config-specialized.json --port 8004
```

---

## Deployment Scenarios

### Scenario 1: All-in-One Local (Development)

```
┌─────────────────────────────────────┐
│         Your Laptop                 │
│                                     │
│  Marketplace:8001                   │
│  Serving:8002                       │
│  Compute-1:8003 (coordinating)      │
│  Compute-2:8004 (specialized)       │
└─────────────────────────────────────┘
```

**Setup:**
```bash
cd examples/all-in-one
docker-compose up
# OR
./start.sh
```

---

### Scenario 2: Cloud Marketplace + Local Compute

```
┌──────────────────────┐
│   Cloud              │
│                      │
│  Global Marketplace  │
│  :8001               │
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼────┐   ┌───▼────┐
│ Your   │   │ Buddy  │
│ Laptop │   │ Laptop │
│        │   │        │
│ Serv   │   │ Serv   │
│ Comp-1 │   │ Comp-1 │
│ Comp-2 │   │ Comp-2 │
└────────┘   └────────┘
```

**Your laptop:**
```bash
# serving/.env
MARKETPLACE_URLS=https://global-marketplace.claudevn.io

# compute/config.json
{
  "serving_urls": ["http://localhost:8002"],
  "marketplace_urls": ["https://global-marketplace.claudevn.io"]
}
```

**Buddy's laptop:**
```bash
# Same config, different instance_id
{
  "instance_id": "buddy-compute-1",
  "serving_urls": ["http://localhost:8002"],
  "marketplace_urls": ["https://global-marketplace.claudevn.io"]
}
```

---

### Scenario 3: Hybrid (Cloud Serving + Local Marketplaces + Local Compute)

```
┌──────────────────────┐
│   Cloud              │
│                      │
│  Serving Component   │
│  :8002               │
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼────────┐   ┌▼──────────┐
│ Your       │   │ Buddy     │
│ Laptop     │   │ Laptop    │
│            │   │           │
│ Market:8001│   │Market:8001│
│ Comp-1     │   │Comp-1     │
│ Comp-2     │   │Comp-2     │
└────────────┘   └───────────┘
```

**Cloud serving config:**
```bash
# serving/.env
MARKETPLACE_URLS=http://your-ip:8001,http://buddy-ip:8001
PORT=8002
PUBLIC_URL=https://serving.claudevn.io
```

**Your laptop:**
```bash
# marketplace/.env
PORT=8001
PUBLIC_URL=http://your-ip:8001

# compute/config.json
{
  "serving_urls": ["https://serving.claudevn.io"],
  "marketplace_urls": [
    "http://localhost:8001",
    "https://serving.claudevn.io/marketplace"
  ],
  "marketplace_priority": "local_first"
}
```

---

### Scenario 4: Enterprise (Multiple Everything)

```
┌────────────────────────────────────────┐
│   Cloud                                │
│                                        │
│  Global Marketplace:8001               │
│  Serving-Primary:8002                  │
│  Serving-Secondary:8003 (failover)     │
└────────────┬───────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
┌───▼────────┐   ┌───▼────────┐
│ Office     │   │ Home       │
│            │   │            │
│ Private    │   │ Compute-1  │
│ Market     │   │ Compute-2  │
│ Compute-1  │   │            │
│ Compute-2  │   │            │
│ Compute-3  │   │            │
└────────────┘   └────────────┘
```

---

## Shared Library

The `shared/` directory contains common code used by all components:

**Installation:**
```bash
cd shared
pip install -e .  # Editable install for development
```

**Usage in components:**
```python
from claudevn_shared.models import AgentCard, Task, ExecutionPlan
from claudevn_shared.a2a_types import TaskStatus, TaskInput
from claudevn_shared.config import load_config
```

**Benefits:**
- Consistent data models across components
- A2A protocol types shared
- Common utilities (logging, config, etc.)
- Version compatibility checking

---

## Development Workflow

### Initial Setup

```bash
# Clone repo
git clone git@github.com:Guarrdon/claudevn.git
cd claudevn

# Install shared library
cd shared && pip install -e . && cd ..

# Set up each component you want to run
cd marketplace
pip install -r requirements.txt
cp .env.example .env
# Edit .env
cd ..

cd serving
pip install -r requirements.txt
cp .env.example .env
# Edit .env
cd ..

cd compute
pip install -r requirements.txt
cp config.json.example config.json
# Edit config.json
cd ..
```

### Running All-in-One for Development

```bash
# Use the example deployment
cd examples/all-in-one
./start.sh
```

### Running Individual Components

```bash
# Terminal 1 - Marketplace
cd marketplace && ./start.sh

# Terminal 2 - Serving
cd serving && ./start.sh

# Terminal 3 - Compute Instance 1
cd compute && ./start.sh --config config-coord.json

# Terminal 4 - Compute Instance 2
cd compute && ./start.sh --config config-spec.json
```

### Testing Cross-Machine Setup

**Machine 1 (Marketplace + Serving):**
```bash
cd marketplace && ./start.sh &
cd serving && ./start.sh &
```

**Machine 2 (Compute):**
```bash
cd compute
# Edit config.json to point to Machine 1's IP
./start.sh
```

---

## Component Communication

### Marketplace ↔ Serving
- **Registration (Marketplace → Serving):**
  - Marketplace registers with Serving on startup ("phone home" pattern)
  - Marketplace sends periodic heartbeats to maintain registration
  - Serving tracks registered marketplaces dynamically
- **Discovery (Serving → Marketplace):**
  - Serving queries registered Marketplaces for agent/tool discovery
  - Serving can cache Agent Cards locally
  - Multiple marketplaces can be registered with priority

### Serving ← Compute
- Compute registers with Serving on startup ("phone home" pattern)
- Compute sends heartbeats to maintain registration
- Serving routes A2A messages to Compute instances

### Compute → Marketplace
- Compute queries Marketplace for agent/tool metadata
- Used by coordinating agents for team assembly
- Can be direct or proxied through Serving

### Compute ↔ Compute (via Serving)
- No direct communication
- All cross-instance messages go through Serving
- A2A protocol for task submission and results

---

## Configuration Management

Each component has its own `.env` file and/or `config.json`:

**Marketplace:**
- Database connection
- Port
- CORS settings
- Authentication

**Serving:**
- Port
- Session storage
- Message queue (Redis for distributed)
- Authentication
- Health monitoring settings
- Note: Marketplaces register themselves with Serving ("phone home" pattern)

**Compute:**
- Instance ID (unique)
- Port
- Serving URLs (can be multiple for failover)
- Enabled agents and tools
- LLM configuration
- Note: Registers with Serving on startup ("phone home" pattern)

---

## Next Steps

1. Create directory structure
2. Set up shared library
3. Implement Marketplace as standalone service
4. Implement Serving as standalone service
5. Implement Compute as standalone service
6. Create example deployments
7. Test various deployment scenarios

This structure allows maximum flexibility while maintaining clean separation of concerns.

