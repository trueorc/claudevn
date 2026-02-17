# Marketplace Design - Executive Summary

## Overview

The Marketplace Service is the discovery and registry system for ClaudeVN, enabling coordinating agents to find and select specialized agents and tools based on their capabilities. This summary provides a high-level view of the design for review before implementation.

---

## Key Design Principles

**Independent Deployability**
The Marketplace runs as a completely standalone service with its own storage, API, and optional frontend. It has no dependencies on Serving or Compute components, allowing flexible deployment topologies.

**Storage Abstraction**
All storage operations go through an abstract interface that can be swapped for different backend technologies without changing business logic. This enables starting with simple filesystem storage and migrating to DynamoDB, S3, or other backends as needs evolve.

**A2A Protocol Compliance**
Agent metadata is stored internally but can be transformed into A2A-compliant Agent Cards on demand, ensuring interoperability with external systems.

**Simple First, Scale Later**
Initial implementation uses filesystem-based storage and no authentication, perfect for development. Design supports scaling to cloud backends and full auth when needed.

---

## Architecture Layers

### API Layer (FastAPI)
Exposes RESTful endpoints for:
- Agent CRUD operations
- Tool CRUD operations  
- Access control management
- Search and filtering
- Agent Card generation
- Health monitoring

### Business Logic Layer
Handles:
- Capability matching and ranking
- Overlap detection
- Search relevance scoring
- Validation and sanitization
- Agent Card transformation

### Storage Abstraction Layer
Defines generic interface for:
- Document CRUD operations
- Query and filtering
- Batch operations
- Collection management
- Backend-agnostic data access

### Storage Implementation Layer
Concrete backends:
- **Filesystem** (Phase 1): JSON documents in directory structure
- **DynamoDB** (Future): Serverless, scalable NoSQL
- **S3** (Future): Object storage for distributed access
- **PostgreSQL/SQLite** (Future): Relational option

---

## Data Model

### Agent Documents

Each agent is stored as a JSON document containing:

**Identity**
- Unique ID and human-readable name
- Type (coordinating or specialized)
- Version and description

**Capabilities**
- Array of capability tags
- Detailed capability descriptions
- Supported input/output types

**Technical Details**
- Endpoint URL for remote agents
- Instance ID for local agents
- Authentication requirements
- Complexity level and estimated duration
- Language model used

**Metadata**
- Publisher information
- Tags for categorization
- Registration and update timestamps

**Performance Tracking**
- Usage count
- Success rate
- Average execution duration
- Last used timestamp

### Tool Documents

Tools are represented as documents with:
- Identity and type (MCP external vs ecosystem internal)
- Parameter JSON schema
- Return type specification
- Side effects description
- Implementation details
- Access restrictions

### Access Control Documents

Define permissions with:
- Instance or agent identifiers
- Resource type and ID (with wildcard support)
- Access level (allow or deny)
- Priority for rule evaluation

---

## Mock Agents Included

### 1. Content Writer Agent

**Purpose**: Generates written content including summaries, reports, articles, and documentation.

**Key Capabilities**
- Content generation
- Summarization
- Report writing
- Documentation creation
- Tone adaptation for different audiences

**Characteristics**
- Specialized agent
- Medium complexity
- 60-180 second typical duration
- Handles multiple input formats
- Outputs markdown or plain text

**Use Cases**
- Executive summaries from data analysis
- Technical documentation
- Report generation
- Meeting notes summarization
- Audience-appropriate content adaptation

**Differentiation**: Specializes in structured business and technical writing with emphasis on clarity and audience-appropriate tone, rather than generic text generation.

---

### 2. Research Agent

**Purpose**: Gathers, synthesizes, and analyzes information from various sources to answer questions and compile research summaries.

**Key Capabilities**
- Information gathering
- Source synthesis
- Fact verification
- Topic investigation
- Citation management

**Characteristics**
- Specialized agent
- Medium-high complexity
- 120-300 second typical duration
- Structured JSON output with sources
- Non-deterministic results based on available information

**Use Cases**
- Business intelligence research
- Competitive analysis
- Technical topic investigation
- Fact-checking for reports
- Background information compilation

**Differentiation**: Focuses on research methodology, source evaluation, and synthesis rather than just information retrieval. Emphasizes accuracy and comprehensive coverage.

---

## Storage Architecture

### Swappable Backend Design

All storage backends implement the same interface, providing:

**Core Operations**
- Create, read, update, delete documents
- Exists check for document presence

**Query Operations**
- List with pagination
- Filter by exact match or patterns
- Filter by array membership (capabilities)
- Sort and count results

**Batch Operations**
- Multi-document create
- Multi-document read by ID list
- Multi-document delete

**Management Operations**
- List collections
- Initialize collection schema
- Clear collection (for testing)
- Get statistics

### Filesystem Backend (Phase 1)

**Structure**: One JSON file per document in collection directories
**Path**: data/marketplace/agents/, data/marketplace/tools/, etc.
**Benefits**: Simple, no external dependencies, human-readable, easy debugging
**Characteristics**: Atomic writes, file-based locking, suitable for development

### Future Backend Options

**DynamoDB**: Serverless, auto-scaling, perfect for cloud deployments
**S3**: Distributed object storage, excellent for multi-region access
**PostgreSQL/SQLite**: Relational option with SQL query capabilities

**Key Point**: Switching backends requires only configuration changes, no code modifications.

---

## API Design

### RESTful Endpoints

**Agent Management**
- POST /api/v1/agents - Create new agent
- GET /api/v1/agents - List with filtering, sorting, pagination
- GET /api/v1/agents/{id} - Get specific agent
- PUT /api/v1/agents/{id} - Update agent
- DELETE /api/v1/agents/{id} - Delete agent
- GET /api/v1/agents/{id}/card - Get A2A Agent Card
- POST /api/v1/agents/search - Advanced capability matching

**Tool Management**
- POST /api/v1/tools - Create tool
- GET /api/v1/tools - List tools
- GET /api/v1/tools/{id} - Get tool
- PUT /api/v1/tools/{id} - Update tool
- DELETE /api/v1/tools/{id} - Delete tool

**Access Control**
- POST /api/v1/access - Create access rule
- GET /api/v1/access - List rules
- GET /api/v1/access/instances/{id} - Get instance permissions
- DELETE /api/v1/access/{id} - Delete rule

**Health and Status**
- GET /api/v1/health - Service health check
- GET /api/v1/stats - Marketplace statistics

### Query Parameters

Consistent across list endpoints:
- Filtering: agent_type, capabilities, tags, search text
- Sorting: sort field and order (asc/desc)
- Pagination: limit and offset
- All filters can be combined

---

## Frontend Design

### Single Page React Application

**Technology**
- React with JavaScript (no TypeScript)
- React Router for navigation
- Axios for API calls
- Responsive design for desktop and tablet

### Page Structure

**1. Browse Marketplace**
- Primary landing page
- Search bar with real-time results
- Multi-select filters (type, capabilities, tags, complexity)
- Grid or list view toggle
- Agent/tool cards with key information
- Detail panel or modal for full information
- Pagination with page size selector

**2. Agent Detail Page**
- Comprehensive agent information
- Full capability list with descriptions
- Technical specifications
- Performance metrics and charts
- A2A Agent Card display and download
- Related agents and tools
- Breadcrumb navigation

**3. Tools List Page**
- Similar to browse but filtered to tools
- Tool-specific information
- Parameter schema display
- Usage restrictions shown

**4. Admin/Publishing Page (Future)**
- Agent registration wizard
- Capability selection
- Parameter schema builder
- Overlap detection warnings
- Form validation

### User Experience

**Discovery Flow**
1. User lands on browse page
2. Applies filters or searches for capabilities
3. Views agent cards in grid/list
4. Clicks for detailed view
5. Reviews full specifications
6. Downloads Agent Card if needed

**Key Features**
- Instant search feedback
- Filter without page reload
- Deep linking to specific agents
- Visual capability indicators
- Performance metric visualizations
- Mobile-friendly responsive design

---

## Business Logic

### Capability Matching

When a coordinating agent searches for capabilities, the marketplace:
1. Queries for agents with any matching capabilities
2. Scores each agent based on:
   - Exact capability matches (highest weight)
   - Related capabilities
   - Specialization level (fewer capabilities = more specialized)
   - Success rate and performance metrics
   - Usage popularity
   - Instance locality (prefer same instance)
3. Returns ranked list with scores

### Overlap Detection

When registering a new agent:
1. Compare capabilities to existing agents of same type
2. Calculate capability overlap percentage
3. Compute description similarity
4. Flag if overlap >70% and similarity >60%
5. Require publisher to clarify differentiation

This prevents marketplace pollution with redundant agents.

### Search Ranking

Text searches are ranked by:
- Exact name matches (highest priority)
- Name contains search term
- Description contains term
- Capability names match
- Tag matches
- Popularity boost
- Performance boost

Results are sorted by relevance score.

---

## Configuration

### Environment Variables

**Core Service**
- MARKETPLACE_PORT: Service port (default 8001)
- MARKETPLACE_HOST: Bind address (default 0.0.0.0)
- LOG_LEVEL: Logging verbosity (INFO, DEBUG, WARNING, ERROR)

**Storage Backend**
- STORAGE_BACKEND: Backend type (filesystem, dynamodb, s3)
- STORAGE_PATH: Path for filesystem backend
- STORAGE_CONFIG: JSON configuration for backend-specific settings

**API Configuration**
- CORS_ORIGINS: Allowed CORS origins (default *)
- API_VERSION: API version prefix (default v1)
- MAX_PAGE_SIZE: Maximum results per page (default 100)

**Future Authentication**
- AUTH_ENABLED: Enable authentication (default false)
- JWT_SECRET: JWT token validation secret
- ADMIN_API_KEY: Admin operations API key

---

## Deployment

### Standalone Service

The marketplace runs independently:
- Single start.sh script launches service
- No dependencies on other ClaudeVN components
- Can run on different machine than Serving or Compute
- Optional frontend served from same port or separate

### Directory Structure

```
marketplace/
  main.py              # FastAPI entry point
  requirements.txt     # Python dependencies
  start.sh            # Startup script
  .env.example        # Environment template
  api/                # API endpoints
  storage/            # Storage backends
  services/           # Business logic
  models/             # Data models
  utils/              # Utilities
  data/               # Storage directory (gitignored)
  seed_data/          # Initial agents and tools
```

### Integration Points

**With Serving Component**
- Serving queries marketplace for agent discovery
- Read-only relationship
- May cache Agent Cards locally

**With Compute Instances**
- Coordinating agents query for team assembly
- Direct HTTP calls to marketplace API
- No registration required

---

## Seed Data

On first startup, marketplace populates with:

**Coordinating Agents** (5)
- Goal Decomposer Agent
- Team Assembler Agent
- Execution Coordinator Agent
- Progress Tracker Agent
- Result Synthesizer Agent

**Specialized Agents** (2 initially)
- Content Writer Agent (detailed in this document)
- Research Agent (detailed in this document)

**Tools**
None in Phase 1 per requirements.

Seed data is idempotent - safe to run multiple times without duplication.

---

## Security and Performance

### Security

**Phase 1**
- No authentication (development/trusted environments)
- Input validation on all endpoints
- Schema enforcement
- File system permissions restricted

**Future Phases**
- API key authentication for writes
- JWT tokens for user operations
- Role-based access control
- Rate limiting
- Audit logging

### Performance

**Optimization Strategies**
- Pagination limits result sizes
- Storage layer filtering (not in-memory)
- Response compression
- Efficient indexing on query fields

**Scalability**
- Stateless API design enables horizontal scaling
- Load balancer with multiple instances
- Shared storage backend (DynamoDB, S3)
- Cache layer for hot data (future)

---

## Error Handling

All errors return consistent JSON format:
- Error code
- Human-readable message
- Optional details object
- Timestamp and request ID

Error categories:
- 400 Bad Request: Validation failures
- 404 Not Found: Resource doesn't exist
- 409 Conflict: Duplicate ID, overlap detected
- 500 Internal Server Error: Unexpected failures
- 503 Service Unavailable: Backend issues

Graceful degradation with helpful error messages.

---

## Testing Strategy

Per project guidelines, manual testing initially with documented scenarios:

**Test Coverage**
- Agent CRUD operations with valid and invalid data
- Search and filtering combinations
- Pagination boundaries
- Storage backend swapping
- Concurrent operations
- Error conditions
- Agent Card generation accuracy
- Access control rule evaluation

Test scenarios documented for future automation when architecture stabilizes.

---

## Future Enhancements

### Phase 2
- Authentication and authorization
- Agent versioning with deprecation
- Enhanced fuzzy search
- Webhook notifications
- Batch operations API

### Phase 3
- Performance analytics dashboard
- Agent testing framework
- Automated overlap detection
- Agent recommendation engine
- Marketplace federation

### Phase 4
- Monetization support (pricing, billing)
- Agent reputation and reviews
- Certification program
- Multi-language support

---

## Success Criteria

**Phase 1 Complete When:**
- Marketplace runs standalone on port 8001
- Can create and list agents via API
- Frontend displays agents with search and filters
- Two mock agents seeded and browsable
- Five coordinating agents seeded
- Storage backend can be swapped via config
- Agent Cards generated in A2A format
- Health check endpoint operational

**Integration Success:**
- Serving component can query marketplace
- Coordinating agents can search for capabilities
- Agent Card transformation is accurate

---

## Questions for Review

Before proceeding with implementation, please confirm:

1. **Storage Design**: Is the storage abstraction approach clear? The interface allows complete backend swapping.

2. **Mock Agents**: Do the Content Writer and Research Agent specifications meet requirements? They provide realistic examples of specialized agents with clear capabilities and differentiation.

3. **Frontend Scope**: Is the planned React frontend appropriate for Phase 1? It covers browsing, search, and detail views without admin features initially.

4. **API Design**: Are the RESTful endpoints comprehensive? They cover all CRUD operations plus search, filtering, and A2A Card generation.

5. **No Tools Yet**: Confirmed that tools are not included in Phase 1 implementation, only the structure to support them.

6. **File Organization**: The directory structure follows the existing ClaudeVN patterns in project-structure.md.

---

## Next Steps After Approval

Once design is approved:

1. Create marketplace directory structure
2. Set up Python dependencies and environment
3. Implement storage abstraction interface
4. Implement filesystem storage backend
5. Implement data models (Pydantic)
6. Implement API endpoints
7. Implement business logic services
8. Create seed data files
9. Set up React frontend
10. Implement frontend pages and components
11. Create startup script
12. Test end-to-end flow
13. Document usage and configuration
14. Update main project documentation

Estimated implementation time: Multiple sessions given the comprehensive scope.

---

## Design Documentation Location

Full detailed design available in:
- `/docs/marketplace-design.md` - Complete technical specification

This summary in:
- `/docs/marketplace-design-summary.md` - Executive overview for review

Ready for your review and approval before implementation begins.

