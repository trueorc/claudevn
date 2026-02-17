# Marketplace Service Design

## Overview

The Marketplace Service is an independent, deployable component that serves as the discovery and registry system for AI agents and tools in the ClaudeVN platform. It enables coordinating agents to find and select specialized agents based on their capabilities, while providing a flexible storage backend that can be swapped between different implementations.

This design follows the established ClaudeVN architecture principles:
- Independent deployability
- Clean API boundaries
- Storage backend abstraction
- A2A protocol compliance
- Simple local development with production scalability

---

## Architecture

### Component Structure

The Marketplace is organized into distinct layers:

**API Layer**
- RESTful endpoints for agent and tool management
- Agent Card generation in A2A format
- Search and filtering capabilities
- Access control enforcement
- Health and status monitoring

**Business Logic Layer**
- Agent capability matching
- Overlap detection and differentiation
- Search relevance ranking
- Validation and sanitization
- Agent Card transformation

**Storage Abstraction Layer**
- Generic storage interface (StorageBackend)
- Document-style operations (CRUD)
- Query and filtering capabilities
- Transaction support where applicable
- Backend-agnostic data access

**Storage Implementation Layer**
- Filesystem backend (JSON documents)
- Future: DynamoDB backend
- Future: S3 backend
- Future: PostgreSQL/SQLite backend

### Data Flow

```
External Request
    ↓
API Endpoints (FastAPI)
    ↓
Request Validation & Auth
    ↓
Business Logic (Service Layer)
    ↓
Storage Abstraction (Interface)
    ↓
Concrete Storage Backend
    ↓
Physical Storage (Filesystem/DynamoDB/S3)
```

---

## Storage Architecture

### Storage Abstraction Design

The storage system uses an abstract interface pattern that allows complete backend swapping without changing business logic. This design supports:

- Multiple backend technologies
- Easy testing with mock backends
- Gradual migration between storage systems
- Environment-specific configurations
- Zero coupling between business logic and storage implementation

### Storage Interface Contract

The abstract storage interface defines standard operations for all backends:

**Document Operations**
- Create document with unique ID
- Read document by ID
- Update document (full or partial)
- Delete document
- Check document existence

**Query Operations**
- List documents with pagination
- Filter by field values (exact match)
- Filter by field patterns (contains, starts with)
- Filter by array membership (has capability)
- Sort results
- Count matching documents

**Batch Operations**
- Create multiple documents atomically
- Read multiple documents by ID list
- Delete multiple documents

**Collection Management**
- List collections
- Initialize collection schema
- Clear collection (for testing)
- Get collection statistics

### Document Model

All data is stored as documents (JSON-serializable dictionaries) within collections. Each document has:

**Standard Fields**
- id: Unique identifier (string)
- created_at: ISO 8601 timestamp
- updated_at: ISO 8601 timestamp

**Custom Fields**
- Arbitrary JSON-serializable data specific to document type

### Backend Configuration

Backends are configured via environment variables and a configuration object:

**Environment Variables**
- STORAGE_BACKEND: Backend type identifier (filesystem, dynamodb, s3, etc.)
- STORAGE_PATH: Path for filesystem backend
- Backend-specific credentials and endpoints

**Configuration Object**
- Backend selection
- Connection parameters
- Performance tuning
- Retry and timeout settings

---

## Data Model

### Agent Documents

**Collection: agents**

Each agent document represents a registered AI agent with its metadata and capabilities.

**Document Structure**

Core Fields:
- id: Unique agent identifier
- name: Human-readable agent name
- description: Detailed description of agent purpose and behavior
- agent_type: Either "coordinating" or "specialized"
- version: Semantic version string
- created_at: Registration timestamp
- updated_at: Last modification timestamp

Capabilities:
- capabilities: Array of capability strings (tags)
- capability_descriptions: Map of capability to detailed description
- supported_input_types: Array of MIME types or format identifiers
- supported_output_types: Array of MIME types or format identifiers

Technical:
- endpoint_url: Base URL for A2A invocation (if remote)
- instance_id: Compute instance where agent runs (optional)
- authentication: Authentication requirements object

Metadata:
- publisher_id: Who registered this agent
- tags: Additional categorization tags
- complexity_level: Estimated resource requirements (low/medium/high)
- estimated_duration: Typical execution time in seconds
- language_model: LLM model used (if applicable)

Performance:
- usage_count: Total invocations
- success_rate: Percentage of successful executions
- average_duration: Mean execution time
- last_used_at: Most recent invocation

**Example Document**

```
{
  "id": "agent-data-analyst-v1",
  "name": "Data Analyst Agent",
  "description": "Analyzes structured data (CSV, JSON, SQL) to generate statistical insights, identify trends, and create visualizations. Specializes in exploratory data analysis, correlation detection, and anomaly identification.",
  "agent_type": "specialized",
  "version": "1.0.0",
  "capabilities": [
    "data_analysis",
    "statistical_analysis",
    "data_visualization",
    "trend_identification",
    "anomaly_detection"
  ],
  "capability_descriptions": {
    "data_analysis": "Parse and analyze structured datasets",
    "statistical_analysis": "Calculate descriptive and inferential statistics",
    "data_visualization": "Generate charts and graphs",
    "trend_identification": "Detect patterns and trends in time-series",
    "anomaly_detection": "Identify outliers and unusual patterns"
  },
  "supported_input_types": [
    "text/csv",
    "application/json",
    "application/sql"
  ],
  "supported_output_types": [
    "application/json",
    "text/markdown"
  ],
  "endpoint_url": null,
  "instance_id": "compute-1",
  "authentication": {
    "required": false
  },
  "publisher_id": "system",
  "tags": [
    "analytics",
    "business-intelligence",
    "data-science"
  ],
  "complexity_level": "medium",
  "estimated_duration": 120,
  "language_model": "gpt-4",
  "usage_count": 0,
  "success_rate": 0.0,
  "average_duration": 0,
  "last_used_at": null,
  "created_at": "2025-11-21T10:00:00Z",
  "updated_at": "2025-11-21T10:00:00Z"
}
```

### Tool Documents

**Collection: tools**

Tool documents represent deterministic utilities available to agents.

**Document Structure**

Core Fields:
- id: Unique tool identifier
- name: Human-readable tool name
- description: What the tool does
- tool_type: Either "mcp" (external) or "ecosystem" (internal)
- version: Semantic version string

Specification:
- parameters: JSON schema defining input parameters
- return_type: JSON schema or description of output
- side_effects: Description of any external changes made

Technical:
- implementation: For MCP tools, connection details
- requirements: Dependencies or prerequisites

Metadata:
- publisher_id: Who registered this tool
- tags: Categorization tags
- is_stateful: Whether tool maintains state between calls
- is_idempotent: Whether repeated calls with same input produce same result

Access Control:
- restricted: Whether tool has usage restrictions
- allowed_agents: List of agent IDs that can use this tool (if restricted)

**Example Document**

```
{
  "id": "tool-data-processor-v1",
  "name": "Data Processor",
  "description": "Processes structured data files (CSV, JSON) with operations like filtering, sorting, grouping, aggregation, and transformation.",
  "tool_type": "ecosystem",
  "version": "1.0.0",
  "parameters": {
    "type": "object",
    "properties": {
      "operation": {
        "type": "string",
        "enum": ["filter", "sort", "group", "aggregate", "transform"]
      },
      "data": {
        "type": "object"
      },
      "config": {
        "type": "object"
      }
    },
    "required": ["operation", "data"]
  },
  "return_type": {
    "type": "object",
    "description": "Processed data in same format as input"
  },
  "side_effects": "None - pure data transformation",
  "implementation": {
    "type": "internal",
    "module": "tools.data_processor"
  },
  "requirements": [],
  "publisher_id": "system",
  "tags": ["data", "transformation", "etl"],
  "is_stateful": false,
  "is_idempotent": true,
  "restricted": false,
  "allowed_agents": [],
  "created_at": "2025-11-21T10:00:00Z",
  "updated_at": "2025-11-21T10:00:00Z"
}
```

### Access Control Documents

**Collection: access_control**

Access control documents define permissions for compute instances and agents.

**Document Structure**
- id: Auto-generated unique ID
- instance_id: Compute instance identifier (or wildcard)
- resource_type: Either "agent" or "tool"
- resource_id: Specific agent/tool ID (or wildcard)
- access_level: Either "allow" or "deny"
- priority: Rule priority (higher number = higher priority)
- created_at: When rule was created
- created_by: Who created the rule
- reason: Optional justification

**Access Control Logic**
- Rules evaluated from highest to lowest priority
- First matching rule determines access
- Deny rules can override allow rules if higher priority
- No matching rule defaults to allow (open marketplace)
- Wildcard support for bulk rules

---

## Mock Agent Specifications

### Mock Agent 1: Content Writer Agent

**Purpose**
A specialized agent that generates written content including summaries, reports, articles, and documentation based on provided inputs and requirements.

**Identity**
- ID: agent-content-writer-v1
- Name: Content Writer Agent
- Type: specialized
- Version: 1.0.0

**Capabilities**
- content_generation: Create original written content
- summarization: Condense long text into concise summaries
- report_writing: Generate structured business reports
- documentation: Create technical documentation
- tone_adaptation: Adjust writing style and tone for different audiences

**Input Handling**
- Accepts text/plain instructions
- Accepts application/json with structured requirements
- Can reference data from previous task outputs
- Supports tone specifications (formal, casual, technical, executive)
- Handles content length requirements (short, medium, long)

**Output Format**
- Primary: text/markdown for formatted documents
- Alternate: text/plain for simple text
- Alternate: application/json for structured content with metadata

**Characteristics**
- Complexity Level: medium
- Estimated Duration: 60-180 seconds depending on content length
- Language Model: gpt-4
- Non-deterministic: Output varies with same input
- Stateless: No memory between invocations

**Use Cases**
- Generating executive summaries from data analysis results
- Creating documentation for code or processes
- Writing reports based on research findings
- Summarizing meeting notes or long documents
- Adapting technical content for different audiences

**Differentiation from Similar Agents**
Unlike generic text generation, this agent specializes in structured business and technical writing with emphasis on clarity, accuracy, and audience-appropriate tone.

---

### Mock Agent 2: Research Agent

**Purpose**
A specialized agent that gathers, synthesizes, and analyzes information from various sources to answer questions, investigate topics, and compile comprehensive research summaries.

**Identity**
- ID: agent-researcher-v1
- Name: Research Agent
- Type: specialized
- Version: 1.0.0

**Capabilities**
- information_gathering: Collect relevant information on topics
- source_synthesis: Combine information from multiple sources
- fact_verification: Cross-reference claims for accuracy
- topic_investigation: Deep dive into specific subjects
- citation_management: Track and format source references

**Input Handling**
- Accepts text/plain research questions
- Accepts application/json with structured research parameters
- Supports search scope definitions (broad vs narrow)
- Handles source type preferences (academic, news, technical)
- Accepts existing context to build upon

**Output Format**
- Primary: application/json with structured findings
- Includes: summary, key findings, sources, confidence levels
- References formatted in standard citation style
- Metadata includes search strategy and source quality assessment

**Characteristics**
- Complexity Level: medium-high
- Estimated Duration: 120-300 seconds depending on research depth
- Language Model: gpt-4
- Non-deterministic: Results vary based on available information
- Stateless: Each research request is independent

**Use Cases**
- Investigating business questions requiring external information
- Gathering competitive intelligence on markets or companies
- Researching technical topics for solution design
- Fact-checking and verification for report accuracy
- Compiling background information for decision-making

**Differentiation from Similar Agents**
Focused on research methodology, source evaluation, and synthesis rather than just information retrieval. Emphasizes accuracy, source quality, and comprehensive coverage over speed.

**Tool Dependencies**
- Requires access to web search tools (when available)
- Can operate with LLM knowledge when tools unavailable
- Benefits from citation formatting tools

---

## API Design

### API Architecture Principles

**RESTful Design**
- Resource-oriented URLs
- Standard HTTP methods (GET, POST, PUT, DELETE)
- Appropriate status codes
- JSON request and response bodies

**Consistency**
- Uniform URL patterns
- Consistent error response format
- Standard pagination approach
- Common filtering and sorting syntax

**Versioning**
- API version in URL path (/api/v1/)
- Backwards compatibility within major version
- Clear deprecation warnings

### Endpoint Specifications

#### Agent Management

**Create Agent**
- Method: POST
- Path: /api/v1/agents
- Auth: Required (future)
- Body: Agent document (without id, timestamps)
- Returns: Created agent document with id and timestamps
- Status: 201 Created on success
- Validation: Required fields, capability format, version format
- Side Effects: Triggers overlap detection, generates Agent Card

**List Agents**
- Method: GET
- Path: /api/v1/agents
- Query Parameters:
  - agent_type: Filter by coordinating or specialized
  - capabilities: Comma-separated capability list (AND logic)
  - tags: Comma-separated tag list (OR logic)
  - search: Text search in name and description
  - sort: Field to sort by (name, created_at, usage_count)
  - order: Sort order (asc, desc)
  - limit: Results per page (default 20, max 100)
  - offset: Pagination offset
- Returns: Array of agent documents plus pagination metadata
- Status: 200 OK

**Get Agent**
- Method: GET
- Path: /api/v1/agents/{agent_id}
- Returns: Full agent document
- Status: 200 OK if found, 404 Not Found otherwise

**Update Agent**
- Method: PUT
- Path: /api/v1/agents/{agent_id}
- Body: Partial agent document (only fields to update)
- Returns: Updated agent document
- Status: 200 OK if found, 404 Not Found otherwise
- Validation: Cannot change id, created_at
- Side Effects: Updates updated_at timestamp, regenerates Agent Card

**Delete Agent**
- Method: DELETE
- Path: /api/v1/agents/{agent_id}
- Returns: Success message
- Status: 200 OK if found, 404 Not Found otherwise
- Side Effects: Archives agent (soft delete), removes from active listings

**Get Agent Card**
- Method: GET
- Path: /api/v1/agents/{agent_id}/card
- Returns: A2A-compliant Agent Card (JSON)
- Status: 200 OK if found, 404 Not Found otherwise
- Purpose: A2A protocol compatibility

**Search Agents by Capabilities**
- Method: POST
- Path: /api/v1/agents/search
- Body: Search criteria with capability matching logic
- Returns: Ranked list of matching agents
- Status: 200 OK
- Logic: Relevance scoring based on capability overlap, specialization, performance

#### Tool Management

**Create Tool**
- Method: POST
- Path: /api/v1/tools
- Body: Tool document (without id, timestamps)
- Returns: Created tool document
- Status: 201 Created

**List Tools**
- Method: GET
- Path: /api/v1/tools
- Query Parameters: Similar to agents (tool_type, tags, search, pagination)
- Returns: Array of tool documents plus pagination

**Get Tool**
- Method: GET
- Path: /api/v1/tools/{tool_id}
- Returns: Full tool document
- Status: 200 OK or 404

**Update Tool**
- Method: PUT
- Path: /api/v1/tools/{tool_id}
- Body: Partial tool document
- Returns: Updated tool document
- Status: 200 OK or 404

**Delete Tool**
- Method: DELETE
- Path: /api/v1/tools/{tool_id}
- Returns: Success message
- Status: 200 OK or 404

#### Access Control

**Set Access Rule**
- Method: POST
- Path: /api/v1/access
- Body: Access control document
- Returns: Created rule with id
- Status: 201 Created

**List Access Rules**
- Method: GET
- Path: /api/v1/access
- Query Parameters: instance_id, resource_type, resource_id
- Returns: Array of access rules
- Status: 200 OK

**Get Access Rules for Instance**
- Method: GET
- Path: /api/v1/access/instances/{instance_id}
- Returns: All rules applicable to this instance
- Status: 200 OK
- Purpose: Compute instances query their permissions

**Delete Access Rule**
- Method: DELETE
- Path: /api/v1/access/{rule_id}
- Returns: Success message
- Status: 200 OK or 404

#### Health and Status

**Health Check**
- Method: GET
- Path: /api/v1/health
- Returns: Service health status, storage backend status
- Status: 200 OK if healthy, 503 Service Unavailable otherwise

**Statistics**
- Method: GET
- Path: /api/v1/stats
- Returns: Marketplace statistics (agent count, tool count, popular capabilities)
- Status: 200 OK

---

## Frontend Design

### Frontend Architecture

**Technology Stack**
- React (JavaScript, no TypeScript)
- React Router for navigation
- Axios for API calls
- CSS Modules or styled-components for styling
- Optional: UI component library (Material-UI, Ant Design, or custom)

**Application Structure**
- Single Page Application (SPA)
- Component-based architecture
- Client-side routing
- Responsive design for desktop and tablet
- RESTful API consumption

### Page Structure

#### 1. Browse Marketplace Page

**Purpose**
Primary landing page for discovering and exploring available agents and tools.

**Layout**
- Header with navigation and search
- Sidebar with filters and categories
- Main content area with grid or list view
- Detail panel or modal for selected items

**Features**

Search and Discovery:
- Global search box in header (searches name and description)
- Real-time search results as user types
- Search suggestions based on capabilities
- Clear/reset search functionality

Filtering:
- Filter by agent type (coordinating, specialized)
- Filter by capabilities (multi-select)
- Filter by tags (multi-select)
- Filter by complexity level
- Active filter indicators with remove option
- Clear all filters button

Sorting:
- Sort by name (A-Z, Z-A)
- Sort by popularity (usage count)
- Sort by recency (newest first)
- Sort by success rate (performance)

View Modes:
- Grid view: Cards with icon, name, brief description
- List view: Table with key fields (name, type, capabilities, success rate)
- Toggle between views

Agent/Tool Cards:
- Visual icon or avatar
- Name and version
- Agent type or tool type badge
- Short description (truncated)
- Top 3 capabilities as tags
- Success rate indicator (if available)
- Click to view details

Detail View:
- Full description
- Complete capability list with descriptions
- Technical specifications (input/output types, complexity)
- Performance metrics (usage count, success rate, avg duration)
- Publisher information
- Registration date
- Agent Card download link (JSON)
- Related agents/tools

Pagination:
- Show N results per page (20 default)
- Page numbers with first/last/next/prev
- Total result count
- Results per page selector

**User Interactions**
- Click card to view details
- Apply filters without page reload
- Sort without page reload
- Navigate between pages
- Share links to specific agents (deep linking)

#### 2. Agent Detail Page

**Purpose**
Comprehensive information about a specific agent.

**Route**: /agents/{agent_id}

**Layout**
- Hero section with agent identity
- Tabbed or sectioned content area
- Sidebar with quick stats
- Breadcrumb navigation back to browse

**Content Sections**

Overview:
- Full description
- Agent type and version
- Publisher and registration date
- Current status (active, deprecated)

Capabilities:
- Complete list of capabilities
- Each capability with detailed description
- Visual capability grouping (if applicable)

Technical Specifications:
- Supported input types with examples
- Supported output types with format
- Endpoint URL (if remote)
- Authentication requirements
- Estimated duration and complexity

Performance Metrics:
- Usage statistics chart (if data available)
- Success rate over time
- Average execution duration
- Last used timestamp
- Total invocation count

Agent Card:
- Display formatted Agent Card (A2A protocol)
- Download button for JSON file
- Copy to clipboard option

Related Items:
- Agents with similar capabilities
- Tools commonly used by this agent
- Agents frequently used together

**User Interactions**
- View and download Agent Card
- Navigate to related agents
- Return to marketplace browse
- Report issues or feedback (future)

#### 3. Tools List Page

**Purpose**
Browse and discover available tools.

**Layout and Features**
Similar to Browse Marketplace but filtered to tools only:
- Tool-specific filters (tool_type: mcp vs ecosystem)
- Display parameter schemas
- Show which agents use each tool
- Indicate if tool has restrictions

#### 4. Admin/Publishing Page

**Purpose**
Register new agents and tools (future authenticated feature).

**Layout**
- Form for entering agent/tool information
- Field validation and help text
- Preview before submission
- Success/error feedback

**Features**
- Guided agent registration wizard
- Capability selection from predefined list or custom
- Schema builder for tool parameters
- Overlap detection warnings
- Draft save functionality

---

## Business Logic

### Agent Capability Matching

**Purpose**
Match agents to required capabilities with relevance scoring.

**Algorithm**

Input: Required capabilities array

Steps:
1. Query storage for agents with any matching capability
2. Score each agent:
   - Exact capability matches: +10 points each
   - Capability in same category: +3 points each
   - High specialization bonus (few capabilities): +5 points
   - Success rate bonus: +10 points if >80%, +5 if >60%
   - Popularity bonus: +2 points if used >50 times
   - Instance locality bonus: +20 points if on same instance
3. Sort by score descending
4. Return ranked list with scores

Output: Ordered agent list with match scores

### Overlap Detection

**Purpose**
Identify when new agents are too similar to existing agents.

**Algorithm**

Input: New agent capabilities and description

Steps:
1. Query existing agents of same type
2. For each existing agent:
   - Calculate capability overlap percentage
   - Calculate description similarity (basic text comparison)
   - If capability overlap >70% and description similarity >60%: flag as potential overlap
3. If flagged, return list of similar agents
4. Require publisher to clarify differentiation

Output: Overlap warnings with similar agent suggestions

### Search Relevance Ranking

**Purpose**
Order search results by relevance to query.

**Algorithm**

Input: Search query string

Steps:
1. Tokenize and normalize query
2. Query storage for agents matching query
3. Score each result:
   - Exact name match: +50 points
   - Name contains term: +20 points per term
   - Description contains term: +5 points per term
   - Capability name matches: +15 points per term
   - Tag matches: +10 points per term
   - Boost popular agents: +usage_count/10 points
   - Boost high performers: +success_rate*10 points
4. Sort by score descending
5. Apply pagination

Output: Ranked search results

---

## Configuration

### Environment Variables

**Core Settings**
- MARKETPLACE_PORT: Service port (default 8001)
- MARKETPLACE_HOST: Bind address (default 0.0.0.0)
- LOG_LEVEL: Logging verbosity (INFO, DEBUG, WARNING, ERROR)

**Storage Backend**
- STORAGE_BACKEND: Backend type (filesystem, dynamodb, s3)
- STORAGE_PATH: Path for filesystem backend (default ./data/marketplace)
- STORAGE_CONFIG: JSON string with backend-specific configuration

**API Settings**
- CORS_ORIGINS: Allowed CORS origins (comma-separated, default *)
- API_VERSION: API version prefix (default v1)
- MAX_PAGE_SIZE: Maximum results per page (default 100)

**Authentication (future)**
- AUTH_ENABLED: Enable authentication (default false)
- JWT_SECRET: Secret for JWT token validation
- ADMIN_API_KEY: API key for admin operations

### Storage Backend Configuration

**Filesystem Backend**

Environment:
- STORAGE_BACKEND=filesystem
- STORAGE_PATH=./data/marketplace

Structure:
```
data/marketplace/
  agents/
    agent-id-1.json
    agent-id-2.json
  tools/
    tool-id-1.json
  access_control/
    rule-id-1.json
  _metadata/
    collections.json
```

Characteristics:
- Simple, no external dependencies
- Good for development and single-machine deployments
- File per document for easy inspection
- Human-readable JSON files
- Atomic writes using temp files and rename

**Future: DynamoDB Backend**

Environment:
- STORAGE_BACKEND=dynamodb
- AWS_REGION: AWS region
- DYNAMODB_TABLE_PREFIX: Prefix for table names

Configuration:
- Use AWS credentials from environment or IAM role
- Single table design with collection as partition key prefix
- GSIs for common query patterns
- On-demand or provisioned throughput

**Future: S3 Backend**

Environment:
- STORAGE_BACKEND=s3
- S3_BUCKET: Bucket name
- S3_PREFIX: Prefix for all marketplace objects

Configuration:
- Object per document (key = collection/id)
- JSON content with appropriate content-type
- Metadata in object tags or separate manifest
- Eventual consistency considerations

---

## Deployment

### Standalone Deployment

The Marketplace runs as an independent service:

**Directory Structure**
```
marketplace/
  main.py          # FastAPI application entry point
  requirements.txt # Python dependencies
  start.sh        # Startup script
  .env.example    # Environment template
  api/            # API endpoint modules
    __init__.py
    agents.py
    tools.py
    access.py
    health.py
  storage/        # Storage abstraction
    __init__.py
    backend.py      # Abstract interface
    filesystem.py   # Filesystem implementation
    config.py       # Backend selection and config
  services/       # Business logic
    __init__.py
    agent_service.py
    tool_service.py
    access_service.py
    search_service.py
  models/         # Data models (Pydantic)
    __init__.py
    agent.py
    tool.py
    access.py
  utils/          # Utilities
    __init__.py
    validation.py
    a2a_card.py
  data/           # Default storage path (gitignored)
    marketplace/
      agents/
      tools/
      access_control/
```

**Startup Process**
1. Load environment variables
2. Initialize storage backend based on configuration
3. Create/validate storage collections
4. Initialize FastAPI application
5. Register API routes
6. Start uvicorn server
7. Log startup information and endpoint URLs

**Health Monitoring**
- /api/v1/health endpoint
- Check storage backend connectivity
- Report agent/tool counts
- Service uptime
- Version information

### Integration with Serving Component

**Registration**
Marketplace registers with Serving using "phone home" pattern (as of v0.1.4+):
- Marketplace initiates registration on startup
- Sends POST /api/v1/marketplaces/register to Serving
- Maintains connection via periodic heartbeats
- Serving tracks registered marketplaces dynamically

**Query Pattern**
- Serving Component accepts marketplace registrations (no pre-configuration needed)
- Compute instances register with Serving (configured with SERVING_URL)
- Coordinating agents query via Serving (which routes to registered marketplaces)
- Marketplace provides discovery APIs to Serving

See: `docs/design/specifications/REGISTRATION_ARCHITECTURE.md` for full details

**Caching**
- Serving Component may cache Agent Cards locally
- Cache TTL configurable (default 5 minutes)
- Invalidation on updates via webhooks (future)

---

## Seed Data

### Initial Dataset

When marketplace starts, it can be seeded with initial agents and tools:

**Seeding Process**
- Check if marketplace is empty (no agents)
- Load seed data from JSON files
- Create documents via storage backend
- Log seeded items

**Seed Agents**
1. Data Analyst Agent (specialized)
2. Content Writer Agent (specialized)
3. Research Agent (specialized)
4. Goal Decomposer Agent (coordinating)
5. Team Assembler Agent (coordinating)
6. Execution Coordinator Agent (coordinating)
7. Progress Tracker Agent (coordinating)
8. Result Synthesizer Agent (coordinating)

**Seed Tools**
Initially no tools in this phase (per requirements).

**Seed Location**
- marketplace/seed_data/ directory
- JSON files: agents.json, tools.json
- Imported on first run or manual trigger
- Idempotent: safe to run multiple times

---

## Error Handling

### API Error Response Format

All error responses follow consistent structure:

```
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {...},  // Optional additional context
    "timestamp": "2025-11-21T10:00:00Z",
    "request_id": "uuid"
  }
}
```

### Error Categories

**Validation Errors (400 Bad Request)**
- Missing required fields
- Invalid field formats
- Constraint violations
- Schema validation failures

**Not Found Errors (404 Not Found)**
- Agent ID does not exist
- Tool ID does not exist
- Collection does not exist

**Conflict Errors (409 Conflict)**
- ID already exists (duplicate)
- Version conflict
- Overlap detection failure (agent too similar)

**Server Errors (500 Internal Server Error)**
- Storage backend unavailable
- Unexpected exceptions
- Data corruption

**Service Unavailable (503)**
- Marketplace starting up
- Storage backend maintenance

### Error Handling Strategy

**Graceful Degradation**
- Return partial results when possible
- Provide helpful error messages
- Include suggestions for fixing issues

**Logging**
- Log all errors with context
- Include request ID for tracing
- Separate error logs by severity

**Retry Logic**
- Transient storage errors: retry with backoff
- Network timeouts: retry up to N times
- Non-retryable errors: fail fast

---

## Testing Strategy

### Testing Approach

Manual testing initially per project guidelines, with clear test scenarios documented for future automation.

### Test Scenarios

**Agent CRUD Operations**
1. Create agent with valid data → Success
2. Create agent with missing required field → 400 Error
3. Create agent with duplicate ID → 409 Error
4. List agents with no filters → Returns all agents
5. List agents filtered by capability → Returns matching agents
6. Get agent by ID → Returns full document
7. Get non-existent agent → 404 Error
8. Update agent → Changes persisted
9. Delete agent → Removed from listings

**Search and Filtering**
1. Search by name → Relevance-ranked results
2. Filter by agent_type → Only matching types
3. Filter by multiple capabilities → AND logic applied
4. Sort by usage_count → Ordered correctly
5. Pagination → Correct page boundaries

**Storage Backend**
1. Switch between filesystem backends → Same behavior
2. Storage failure simulation → Graceful error handling
3. Concurrent writes → No data corruption
4. Large dataset performance → Acceptable response times

**Agent Card Generation**
1. Get Agent Card → Valid A2A format
2. Agent Card reflects agent data → Accurate transformation

**Access Control**
1. Create access rule → Rule applied
2. Query rules for instance → Correct rules returned
3. Rule priority evaluation → Higher priority takes precedence

---

## Security Considerations

### Authentication and Authorization

**Phase 1 (Current)**
- No authentication (open marketplace)
- Suitable for development and trusted environments

**Future Phases**
- API key authentication for write operations
- JWT tokens for user-specific operations
- Role-based access control (admin, publisher, reader)
- Rate limiting per API key

### Data Validation

**Input Sanitization**
- Validate all input against Pydantic models
- Reject unexpected fields
- Sanitize text fields (no script injection)
- Validate URLs and endpoints

**Schema Enforcement**
- Agent documents must match schema
- Tool parameter schemas must be valid JSON Schema
- Version strings must follow semver

### Storage Security

**Filesystem Backend**
- Restrict file permissions (owner read/write only)
- Validate file paths (no directory traversal)
- Atomic writes to prevent corruption

**Future Cloud Backends**
- Encrypt at rest (KMS)
- Encrypt in transit (TLS)
- IAM role-based access
- Audit logging enabled

---

## Performance Considerations

### Optimization Strategies

**Caching**
- Cache popular search queries (future)
- Cache Agent Card generation (future)
- Cache frequently accessed agents (future)

**Database Optimization**
- Index common query fields (capability, agent_type, tags)
- Pagination to limit result set sizes
- Efficient filtering at storage layer

**API Performance**
- Response compression (gzip)
- Parallel storage queries where applicable
- Lazy loading of large fields
- ETags for conditional requests (future)

### Scalability

**Horizontal Scaling**
- Stateless API design
- Load balancer in front of multiple instances
- Shared storage backend (DynamoDB, S3)
- Consistent hashing for cache (if added)

**Vertical Scaling**
- Increase instance size for filesystem backend
- Tune storage backend connections
- Optimize query execution

---

## Monitoring and Observability

### Metrics to Track

**Usage Metrics**
- Total agents and tools registered
- API request rate (requests per second)
- Request distribution by endpoint
- Popular search queries
- Most accessed agents

**Performance Metrics**
- API response time (p50, p95, p99)
- Storage backend latency
- Error rate by endpoint
- Success rate for operations

**Business Metrics**
- New agents registered per day
- Agent usage trends
- Capability popularity
- Agent overlap detections

### Logging

**Structured Logging**
- JSON format for machine parsing
- Include request ID in all logs
- Timestamp and severity level
- Contextual information (user, agent, operation)

**Log Levels**
- DEBUG: Detailed execution flow
- INFO: Normal operations (agent created, query executed)
- WARNING: Potential issues (overlap detected, slow query)
- ERROR: Failures requiring attention

---

## Future Enhancements

### Phase 2 Features
- Authentication and authorization
- Agent versioning with deprecation
- Enhanced search with fuzzy matching
- Webhook notifications for agent updates
- Batch operations API

### Phase 3 Features
- Performance analytics dashboard
- Agent testing framework
- Automated overlap detection on publish
- Agent recommendation engine
- Marketplace federation (multiple marketplaces)

### Phase 4 Features
- Monetization support (pricing, billing)
- Agent reputation system
- User reviews and ratings
- Agent certification program
- Multi-language support

---

## Summary

The Marketplace Service provides the discovery foundation for the ClaudeVN platform. Its design emphasizes:

**Flexibility**
- Storage backend abstraction allows easy swapping
- Independent deployment supports various topologies
- Configuration-driven behavior

**Simplicity**
- Clear API boundaries
- Document-based data model
- RESTful conventions
- Minimal external dependencies

**Extensibility**
- Well-defined interfaces
- Modular architecture
- Future-proof design
- A2A protocol compliance

**Usability**
- Intuitive frontend for browsing
- Powerful search and filtering
- Comprehensive agent information
- Easy integration for compute instances

This design supports the immediate need for agent discovery while providing a solid foundation for future marketplace features like monetization, reviews, and federation.

