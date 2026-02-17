# Marketplace Architecture Diagrams

This document provides visual representations of the Marketplace Service architecture, data flows, and integration patterns.

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MARKETPLACE SERVICE                          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                   API LAYER (FastAPI)                   │    │
│  │                                                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│    │
│  │  │ Agents   │  │  Tools   │  │  Access  │  │ Health ││    │
│  │  │ Endpoint │  │ Endpoint │  │ Endpoint │  │ Check  ││    │
│  │  └─────┬────┘  └────┬─────┘  └────┬─────┘  └───┬────┘│    │
│  └────────┼────────────┼─────────────┼────────────┼──────┘    │
│           │            │             │            │            │
│  ┌────────▼────────────▼─────────────▼────────────▼──────┐    │
│  │              BUSINESS LOGIC LAYER                      │    │
│  │                                                         │    │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐      │    │
│  │  │   Agent    │  │    Tool    │  │   Access   │      │    │
│  │  │  Service   │  │  Service   │  │  Service   │      │    │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘      │    │
│  │        │               │               │              │    │
│  │  ┌─────▼───────┐  ┌───▼────────┐  ┌───▼──────┐      │    │
│  │  │   Search    │  │    A2A     │  │Validation│      │    │
│  │  │   Service   │  │Card Builder│  │ Service  │      │    │
│  │  └─────┬───────┘  └────────────┘  └──────────┘      │    │
│  └────────┼───────────────────────────────────────────────┘    │
│           │                                                     │
│  ┌────────▼──────────────────────────────────────────────┐    │
│  │          STORAGE ABSTRACTION LAYER                     │    │
│  │                                                         │    │
│  │         ┌──────────────────────────────┐              │    │
│  │         │  StorageBackend Interface    │              │    │
│  │         │  (Abstract Base Class)       │              │    │
│  │         └──────────┬───────────────────┘              │    │
│  └────────────────────┼─────────────────────────────────────┘    │
│                       │                                          │
│  ┌────────────────────▼─────────────────────────────────────┐    │
│  │      STORAGE IMPLEMENTATION LAYER                        │    │
│  │                                                           │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │    │
│  │  │ Filesystem   │  │  DynamoDB    │  │     S3       │  │    │
│  │  │   Backend    │  │   Backend    │  │   Backend    │  │    │
│  │  │  (Phase 1)   │  │   (Future)   │  │   (Future)   │  │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │    │
│  └─────────┼──────────────────┼──────────────────┼──────────┘    │
└────────────┼──────────────────┼──────────────────┼───────────────┘
             │                  │                  │
             ▼                  ▼                  ▼
    ┌────────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Local Files   │  │  AWS Table   │  │  S3 Bucket   │
    │  (JSON Docs)   │  │              │  │              │
    └────────────────┘  └──────────────┘  └──────────────┘
```

---

## Storage Backend Abstraction

```
┌──────────────────────────────────────────────────────────┐
│          StorageBackend Abstract Interface               │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Document Operations:                                    │
│    • create(collection, document)                       │
│    • read(collection, document_id)                      │
│    • update(collection, document_id, updates)           │
│    • delete(collection, document_id)                    │
│    • exists(collection, document_id)                    │
│                                                          │
│  Query Operations:                                       │
│    • list(collection, filters, sort, limit, offset)     │
│    • count(collection, filters)                         │
│    • filter_by_field(field, value)                      │
│    • filter_by_array_contains(field, value)             │
│                                                          │
│  Batch Operations:                                       │
│    • create_many(collection, documents)                 │
│    • read_many(collection, document_ids)                │
│    • delete_many(collection, document_ids)              │
│                                                          │
│  Management Operations:                                  │
│    • list_collections()                                 │
│    • initialize_collection(collection, schema)          │
│    • clear_collection(collection)                       │
│    • get_stats(collection)                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
                          ▲
                          │ implements
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────▼─────┐    ┌────▼──────┐    ┌───▼────┐
    │Filesystem│    │ DynamoDB  │    │   S3   │
    │ Backend  │    │  Backend  │    │Backend │
    └──────────┘    └───────────┘    └────────┘
```

---

## Data Flow: Agent Registration

```
┌──────────────┐
│   Client     │
│  (Frontend   │
│  or API)     │
└──────┬───────┘
       │ 1. POST /api/v1/agents
       │    {agent document}
       ▼
┌──────────────────────────┐
│  API Layer               │
│  (/api/agents.py)        │
│                          │
│  • Validate request      │
│  • Parse JSON body       │
└──────┬───────────────────┘
       │ 2. Create agent
       ▼
┌──────────────────────────┐
│  Business Logic          │
│  (AgentService)          │
│                          │
│  • Validate schema       │
│  • Check for duplicates  │
│  • Detect overlap        │
│  • Add timestamps        │
│  • Generate ID if needed │
└──────┬───────────────────┘
       │ 3. Store document
       ▼
┌──────────────────────────┐
│  Storage Abstraction     │
│  (StorageBackend)        │
│                          │
│  • Route to backend      │
└──────┬───────────────────┘
       │ 4. Persist
       ▼
┌──────────────────────────┐
│  Filesystem Backend      │
│                          │
│  • Generate filename     │
│  • Write JSON to disk    │
│  • Atomic rename         │
└──────┬───────────────────┘
       │ 5. Success
       ▼
┌──────────────────────────┐
│  Response                │
│                          │
│  201 Created             │
│  {agent with id}         │
└──────────────────────────┘
```

---

## Data Flow: Agent Search by Capabilities

```
┌─────────────────┐
│ Coordinating    │
│    Agent        │
│ (Team Assembler)│
└────────┬────────┘
         │ 1. POST /api/v1/agents/search
         │    {required_capabilities: [...]}
         ▼
┌────────────────────────────┐
│  API Layer                 │
│  (/api/agents.py)          │
└────────┬───────────────────┘
         │ 2. Search request
         ▼
┌────────────────────────────┐
│  Search Service            │
│                            │
│  • Parse capabilities      │
│  • Query storage           │
│  • Score results           │
│  • Rank by relevance       │
└────────┬───────────────────┘
         │ 3. Query with filters
         ▼
┌────────────────────────────┐
│  Storage Backend           │
│                            │
│  • Filter by capabilities  │
│  • Return matching agents  │
└────────┬───────────────────┘
         │ 4. Agent documents
         ▼
┌────────────────────────────┐
│  Search Service            │
│                            │
│  Scoring Logic:            │
│  ┌──────────────────────┐ │
│  │ For each agent:      │ │
│  │  Score = 0           │ │
│  │  + Capability match  │ │
│  │  + Specialization    │ │
│  │  + Success rate      │ │
│  │  + Popularity        │ │
│  │  + Locality          │ │
│  └──────────────────────┘ │
│                            │
│  • Sort by score DESC      │
└────────┬───────────────────┘
         │ 5. Ranked results
         ▼
┌────────────────────────────┐
│  Response                  │
│                            │
│  [{agent, score}, ...]     │
└────────────────────────────┘
```

---

## Integration: Marketplace with Serving Component

```
┌──────────────────────────────────────────────────────────────┐
│                   SERVING COMPONENT                          │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Session Coordinator                        │    │
│  │                                                     │    │
│  │  "Need to find agents for this execution plan"    │    │
│  └─────────────────┬───────────────────────────────────┘    │
│                    │                                         │
│                    │ Query marketplace                       │
│                    │                                         │
└────────────────────┼─────────────────────────────────────────┘
                     │
                     │ HTTP GET
                     │ /api/v1/agents?capabilities=...
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                  MARKETPLACE SERVICE                         │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Agent Search API                            │    │
│  │                                                     │    │
│  │  • Receive capability query                        │    │
│  │  • Search local storage                            │    │
│  │  • Rank and filter results                         │    │
│  │  • Return agent list                               │    │
│  └─────────────────┬───────────────────────────────────┘    │
│                    │                                         │
└────────────────────┼─────────────────────────────────────────┘
                     │
                     │ HTTP 200 OK
                     │ [{agent1}, {agent2}, ...]
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                   SERVING COMPONENT                          │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Session Coordinator                        │    │
│  │                                                     │    │
│  │  • Cache agent list locally (optional, TTL)        │    │
│  │  • Use agents for task routing                     │    │
│  │  • Track which agents are selected                 │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘

Note: Read-only relationship. Marketplace doesn't know about Serving.
Serving can cache but must respect TTL for updates.
```

---

## Integration: Coordinating Agent Queries Marketplace

```
┌──────────────────────────────────────────────────────────────┐
│                   COMPUTE INSTANCE                           │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │     Team Assembler Agent (Coordinating)            │    │
│  │                                                     │    │
│  │  1. Receive execution plan                         │    │
│  │  2. Extract required capabilities                  │    │
│  │     ["data_analysis", "visualization"]             │    │
│  │                                                     │    │
│  └─────────────────┬───────────────────────────────────┘    │
│                    │                                         │
│                    │ 3. Query marketplace                    │
│                    │                                         │
└────────────────────┼─────────────────────────────────────────┘
                     │
                     │ HTTP POST
                     │ /api/v1/agents/search
                     │ {required_capabilities: [...]}
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                  MARKETPLACE SERVICE                         │
│                                                              │
│  • Search agents by capabilities                            │
│  • Score and rank results                                   │
│  • Return ranked list with scores                           │
│                                                              │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ HTTP 200 OK
                     │ [{agent, score}, ...]
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                   COMPUTE INSTANCE                           │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │     Team Assembler Agent                            │    │
│  │                                                     │    │
│  │  4. Receive ranked agent list                      │    │
│  │  5. Select best agents for each task               │    │
│  │  6. Create agent assignments                       │    │
│  │  7. Pass to Execution Coordinator                  │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## A2A Agent Card Generation

```
┌────────────────┐
│  External      │
│  System or     │
│  Client        │
└───────┬────────┘
        │ GET /api/v1/agents/{id}/card
        ▼
┌────────────────────────────┐
│  API Endpoint              │
│  (/api/agents.py)          │
└───────┬────────────────────┘
        │ Get agent
        ▼
┌────────────────────────────┐
│  Agent Service             │
│                            │
│  • Fetch agent document    │
└───────┬────────────────────┘
        │ Agent document
        ▼
┌────────────────────────────┐
│  A2A Card Builder          │
│  (utils/a2a_card.py)       │
│                            │
│  Transform internal format │
│  to A2A protocol:          │
│                            │
│  Internal → A2A            │
│  ─────────────────         │
│  name → name               │
│  version → version         │
│  description → description │
│  capabilities → capability│
│  endpoint_url → endpoint   │
│  authentication → auth     │
│  supported_input_types     │
│    → inputTypes            │
│  supported_output_types    │
│    → outputTypes           │
│                            │
└───────┬────────────────────┘
        │ A2A Agent Card
        ▼
┌────────────────────────────┐
│  Response                  │
│                            │
│  {                         │
│    "name": "...",          │
│    "version": "1.0.0",     │
│    "description": "...",   │
│    "capabilities": [...],  │
│    "serviceEndpoint": "",  │
│    "authentication": {},   │
│    "inputTypes": [...],    │
│    "outputTypes": [...]    │
│  }                         │
└────────────────────────────┘
```

---

## Filesystem Storage Structure

```
data/
└── marketplace/
    ├── agents/
    │   ├── agent-data-analyst-v1.json
    │   ├── agent-content-writer-v1.json
    │   ├── agent-researcher-v1.json
    │   ├── agent-goal-decomposer-v1.json
    │   ├── agent-team-assembler-v1.json
    │   ├── agent-execution-coordinator-v1.json
    │   ├── agent-progress-tracker-v1.json
    │   └── agent-result-synthesizer-v1.json
    │
    ├── tools/
    │   └── (empty in Phase 1)
    │
    ├── access_control/
    │   └── (empty initially - open marketplace)
    │
    └── _metadata/
        └── collections.json
            {
              "collections": {
                "agents": {
                  "count": 8,
                  "last_updated": "2025-11-21T10:00:00Z"
                },
                "tools": {
                  "count": 0,
                  "last_updated": "2025-11-21T10:00:00Z"
                },
                "access_control": {
                  "count": 0,
                  "last_updated": "2025-11-21T10:00:00Z"
                }
              }
            }
```

Each JSON file contains a complete document:
```
agent-data-analyst-v1.json:
{
  "id": "agent-data-analyst-v1",
  "name": "Data Analyst Agent",
  "description": "...",
  "capabilities": [...],
  ...
}
```

---

## Frontend Component Structure

```
┌───────────────────────────────────────────────────────┐
│                     App.js                            │
│                  (Main Router)                        │
└───────────────┬───────────────────────────────────────┘
                │
    ┌───────────┴───────────┬─────────────┬──────────────┐
    │                       │             │              │
    ▼                       ▼             ▼              ▼
┌─────────┐         ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Browse  │         │  Agent   │   │  Tools   │   │  Admin   │
│  Page   │         │  Detail  │   │   Page   │   │  (Future)│
└────┬────┘         │   Page   │   └──────────┘   └──────────┘
     │              └──────────┘
     │
     │ Components
     │
     ├─── SearchBar
     │
     ├─── FilterPanel
     │      ├─ TypeFilter
     │      ├─ CapabilityFilter
     │      ├─ TagFilter
     │      └─ ComplexityFilter
     │
     ├─── AgentGrid
     │      └─ AgentCard (repeated)
     │           ├─ Avatar
     │           ├─ CapabilityTags
     │           └─ MetricsDisplay
     │
     ├─── AgentList
     │      └─ AgentRow (repeated)
     │
     ├─── ViewToggle
     │
     ├─── SortSelector
     │
     └─── Pagination
```

---

## API Request/Response Flow Example

### Create Agent

**Request:**
```
POST /api/v1/agents HTTP/1.1
Host: localhost:8001
Content-Type: application/json

{
  "name": "Custom Analysis Agent",
  "description": "Performs custom data analysis",
  "agent_type": "specialized",
  "version": "1.0.0",
  "capabilities": ["data_analysis", "custom_logic"],
  "supported_input_types": ["application/json"],
  "supported_output_types": ["application/json"],
  "complexity_level": "medium",
  "estimated_duration": 120,
  "language_model": "gpt-4"
}
```

**Processing:**
```
1. API Layer validates JSON schema
2. AgentService checks for duplicate ID
3. AgentService runs overlap detection
4. AgentService adds timestamps and generates ID
5. Storage backend persists document
6. A2A Card Builder generates Agent Card
7. Response assembled
```

**Response:**
```
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/agents/agent-custom-analysis-v1

{
  "id": "agent-custom-analysis-v1",
  "name": "Custom Analysis Agent",
  "description": "Performs custom data analysis",
  "agent_type": "specialized",
  "version": "1.0.0",
  "capabilities": ["data_analysis", "custom_logic"],
  "supported_input_types": ["application/json"],
  "supported_output_types": ["application/json"],
  "complexity_level": "medium",
  "estimated_duration": 120,
  "language_model": "gpt-4",
  "created_at": "2025-11-21T10:30:00Z",
  "updated_at": "2025-11-21T10:30:00Z",
  "usage_count": 0,
  "success_rate": 0.0
}
```

---

## Deployment Topology

### Scenario 1: All Local (Development)

```
┌──────────────────────────────────────────┐
│           Developer Machine              │
│                                          │
│  ┌────────────────┐                     │
│  │  Marketplace   │  Port 8001          │
│  │   + Frontend   │  (React Dev Server) │
│  └────────────────┘                     │
│         │                                │
│         │ Uses local filesystem          │
│         ▼                                │
│  ┌────────────────┐                     │
│  │  data/         │                     │
│  │  marketplace/  │                     │
│  └────────────────┘                     │
│                                          │
│  Access:                                 │
│  - API: http://localhost:8001/api/v1    │
│  - UI: http://localhost:8001            │
│                                          │
└──────────────────────────────────────────┘
```

### Scenario 2: Cloud Marketplace + Local Compute

```
┌──────────────────────────────┐
│          Cloud (AWS)         │
│                              │
│  ┌────────────────────────┐ │
│  │    Marketplace         │ │
│  │    (EC2 instance)      │ │
│  │    Port 8001           │ │
│  └──────────┬─────────────┘ │
│             │                │
│             │ Uses S3 or     │
│             │ DynamoDB       │
│             ▼                │
│  ┌────────────────────────┐ │
│  │   Storage Backend      │ │
│  │   (S3 bucket or        │ │
│  │    DynamoDB tables)    │ │
│  └────────────────────────┘ │
│                              │
│  Public URL:                 │
│  https://marketplace.        │
│        claudevn.io           │
└──────────────────────────────┘
         ▲
         │
         │ HTTP queries
         │
┌────────┴────────────────────┐
│    Local Machine            │
│                             │
│  ┌───────────────────────┐ │
│  │  Compute Instance     │ │
│  │  (with coordinating   │ │
│  │   agents)             │ │
│  │                       │ │
│  │  Config:              │ │
│  │  marketplace_urls:    │ │
│  │  - https://...        │ │
│  └───────────────────────┘ │
└─────────────────────────────┘
```

### Scenario 3: Multiple Marketplaces

```
┌──────────────────┐        ┌──────────────────┐
│  Global          │        │  Company         │
│  Marketplace     │        │  Private         │
│  (Public agents) │        │  Marketplace     │
│  Port 8001       │        │  Port 8001       │
└────────┬─────────┘        └────────┬─────────┘
         │                           │
         └──────────┬────────────────┘
                    │
                    │ Both configured in
                    │ compute instances
                    │
         ┌──────────▼────────────┐
         │  Compute Instance     │
         │                       │
         │  Config:              │
         │  marketplace_urls:    │
         │  - http://global...   │
         │  - http://private...  │
         │                       │
         │  marketplace_priority:│
         │    private_first      │
         └───────────────────────┘

Queries try private marketplace first,
fall back to global marketplace.
```

---

## Error Flow Example

```
┌─────────┐
│ Client  │
└────┬────┘
     │ POST /api/v1/agents
     │ {invalid data}
     ▼
┌─────────────────────┐
│  API Layer          │
│                     │
│  Pydantic validation│
│  ❌ Missing field    │
└────┬────────────────┘
     │ ValidationError
     ▼
┌─────────────────────┐
│  Error Handler      │
│                     │
│  • Catch exception  │
│  • Format error     │
│  • Log request      │
│  • Add request ID   │
└────┬────────────────┘
     │ Error response
     ▼
┌─────────────────────┐
│  Response           │
│                     │
│  400 Bad Request    │
│  {                  │
│    "error": {       │
│      "code": "...", │
│      "message": "", │
│      "details": {}, │
│      "request_id":"│
│    }                │
│  }                  │
└─────────────────────┘
```

---

## Capability Matching Algorithm Visualization

```
Input: required_capabilities = ["data_analysis", "visualization"]

Step 1: Query storage
───────────────────────────────────────────────
Storage returns all agents with either capability:
  - Agent A: ["data_analysis", "statistical_analysis"]
  - Agent B: ["data_analysis", "visualization"]  
  - Agent C: ["visualization", "charting"]
  - Agent D: ["data_analysis", "visualization", "reporting"]

Step 2: Score each agent
───────────────────────────────────────────────
Agent A:
  + Exact match "data_analysis": +10
  + Specialization (2 capabilities): +5
  + Success rate 85%: +10
  = Total: 25 points

Agent B:
  + Exact match "data_analysis": +10
  + Exact match "visualization": +10
  + Specialization (2 capabilities): +5
  + Success rate 90%: +10
  + Popular (100 uses): +2
  = Total: 37 points ⭐ BEST

Agent C:
  + Exact match "visualization": +10
  + Specialization (2 capabilities): +5
  = Total: 15 points

Agent D:
  + Exact match "data_analysis": +10
  + Exact match "visualization": +10
  + Success rate 75%: +5
  = Total: 25 points

Step 3: Sort and return
───────────────────────────────────────────────
Ranked results:
1. Agent B (score: 37) ← Best match
2. Agent A (score: 25)
3. Agent D (score: 25)
4. Agent C (score: 15)
```

---

## Summary

These diagrams illustrate:

1. **Component Architecture**: Layered design with clear separation of concerns
2. **Storage Abstraction**: How backends are swappable via interface
3. **Data Flows**: How data moves through the system for key operations
4. **Integration Patterns**: How Marketplace connects with other ClaudeVN components
5. **Deployment Options**: Various topology scenarios supported
6. **Frontend Structure**: React component organization
7. **Request Processing**: End-to-end API request handling
8. **Error Handling**: Graceful error management and reporting
9. **Algorithms**: Visual representation of business logic

The architecture supports the design principles of independence, flexibility, and scalability while maintaining simplicity for Phase 1 implementation.

