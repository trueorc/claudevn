# ClaudeVN Technical Decisions

**Version**: 0.3.0  
**Last Updated**: December 18, 2025  
**Status**: Living Document - Source of Truth  
**Purpose**: Document all technical implementation decisions and their rationale

---

## Document Purpose

This document records **all significant technical decisions** made in the ClaudeVN project. Each decision is linked back to functional requirements (see [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md)) or marked as a technical necessity.

**Target Audience**: Developers, architects, testers, AI agents, and anyone implementing or modifying the system.

**Decision Format**: Each section follows the pattern:
- **Decision**: What was chosen
- **Rationale**: Why this choice was made
- **Alternatives Considered**: What else was evaluated
- **Linked Requirements**: Which FRs this supports
- **Status**: Current state and any planned changes

---

## Table of Contents

1. [Architecture Decisions](#architecture-decisions)
2. [Technology Stack](#technology-stack)
3. [Data Storage](#data-storage)
4. [Communication Patterns](#communication-patterns)
5. [Security and Authentication](#security-and-authentication)
6. [Infrastructure](#infrastructure)
7. [Design Patterns](#design-patterns)
8. [LLM Integration](#llm-integration)
9. [Testing Strategy](#testing-strategy)
10. [Deployment and Operations](#deployment-and-operations)

---

## Architecture Decisions

### TD-A1: Microservices Architecture with Communication Broker Pattern

**Decision**: Split system into three independent microservices (Marketplace, Serving, Compute) where Serving acts as the central communication broker with the only publicly accessible API.

**Rationale**:
- **Separation of concerns**: Each component has distinct responsibility
  - Marketplace: Agent definitions and metadata (source of truth)
  - Serving: Orchestration, coordination, and communication brokering
  - Compute: Agent execution and LLM integration
- **Security via isolation**: Marketplace and Compute are private, minimizing attack surface
- **Single point of entry**: Serving is the only public API, simplifying security and monitoring
- **Event-driven coordination**: Serving uses event bus and messaging (SSE, WebSocket) rather than direct API calls between components
- **Independent scaling**: Can run multiple compute instances without scaling serving
- **Deployment flexibility**: Components can be deployed separately (on-premise compute, cloud serving/marketplace)

**Communication Pattern**:
```
External Clients ──REST──> Serving (PUBLIC API)
                             │
                             ├──REST──> Marketplace (PRIVATE)
                             │             - Agent definitions
                             │             - User/org data
                             │
                             └──REST──> Compute (PRIVATE)
                                          - Task execution
                                          - Heartbeats

Compute ──registration/heartbeat──> Serving
Marketplace: No outbound calls, only responds to Serving
```

**Key Principle**: Marketplace and Compute do NOT communicate directly with each other or expose public APIs. All communication flows through Serving as the broker.

**Alternatives Considered**:
- **All components with public APIs**: Increases attack surface, complicates security and coordination
- **Direct Compute ↔ Marketplace communication**: Tighter coupling, harder to secure and monitor
- **Monolith**: Simpler to deploy initially, but limits scale and flexibility. Rejected because distributed execution is core requirement.
- **Serverless functions**: Could work for compute, but state management and long-running processes (facilitated sessions) difficult. Serving needs persistent connections (WebSocket).

**Linked Requirements**: FR-9 (Compute Registration), FR-10 (Task Routing), FR-11 (Marketplace Proxy), NFR-2 (Scalability), NFR-7 (Security)

**Trade-offs**:
- ✅ Pros: Security isolation, centralized control, clear boundaries, event-driven coordination
- ❌ Cons: Serving is single point of failure (mitigated by event-driven design), network latency through broker

**Status**: ✅ Implemented and validated

---

### TD-A2: Coordinating Agents Run in Compute, Not Serving

**Decision**: Coordinating agents (Process Mapper, Agent Selector, Activity Facilitator, etc.) are agents that run in compute engines, not hardcoded logic in serving.

**Rationale**:
- **Consistency**: All agents use same execution model (LLM-powered reasoning)
- **Flexibility**: Coordinating agents can be updated without serving code changes
- **Testability**: Coordinating agents testable like any other agent
- **Substitutability**: Organizations could create custom coordinating agents
- **LLM-native**: Complex reasoning tasks (goal decomposition, consistency detection) benefit from LLM capabilities

**Alternatives Considered**:
- **Hardcoded orchestration logic**: Faster execution, no LLM costs, but inflexible and requires code changes for logic updates
- **Hybrid approach**: Some logic in serving, some in agents. Rejected as inconsistent and confusing.

**Linked Requirements**: FR-3 (Process Map Creation), FR-4 (Activity Facilitation), FR-6 (Consistency Detection)

**Trade-offs**:
- ✅ Pros: Flexibility, consistency, LLM reasoning
- ❌ Cons: LLM latency, token costs, non-deterministic output

**Status**: ✅ Implemented and Tested

**Coordinating Agents Deployed**:
- `process-mapper-v1`: Creates initial activity structures from business goals (tested, working)
- `agent-selector-v1`: Recommends agents for activities with structured JSON output (tested, working)
- `activity-facilitator-v1`: Orchestrates multi-turn conversations, detects blockers, synthesizes outputs (created, ready for testing)
- `agent-result-synthesizer-v1`: Aggregates outputs into final deliverables
- `agent-goal-decomposer-v1`: Breaks down complex goals
- `agent-team-assembler-v1`: Optimizes team composition

**Note**: Services in serving (like `process_map_service.py`) handle data management and API coordination. Coordinating agents handle reasoning and decision-making.

---

### TD-A3: Event-Driven Observability

**Decision**: Use event-driven architecture with pub/sub pattern for real-time observability updates.

**Rationale**:
- **Real-time updates**: UI sees state changes immediately without polling
- **Decoupling**: Event emitters don't need to know about subscribers
- **Extensibility**: New subscribers (monitoring, analytics) can be added without code changes
- **Audit trail**: Events naturally create chronological history
- **Performance**: More efficient than polling for clients

**Alternatives Considered**:
- **Polling**: Simple but wasteful (constant requests) and delayed updates
- **Direct WebSocket messages**: Works but tightly couples components and doesn't preserve event history

**Linked Requirements**: FR-12 (Real-Time Observability), NFR-4 (Observability)

**Implementation**:
- Event broker in serving (`serving/broker/event_bus.py`)
- WebSocket connections for UI clients
- Events persisted to session history
- Event types: activity_state_changed, exchange_added, map_evolved, etc.

**Status**: ✅ Implemented

---

### TD-A4: Process Maps as First-Class Entities

**Decision**: Process maps are versioned, persistent data structures stored independently of sessions.

**Rationale**:
- **Evolution tracking**: Each structural change increments version with reasoning

**Verification (Dec 2025)**:
- Process map creation tested via `/api/v1/sessions/create-facilitated` endpoint
- Process Mapper agent successfully decomposes business goals into 4-5 activities
- Dependencies properly captured in activity_graph
- Activities include: goal, description, status, assigned_agents, depends_on, enables
- Maps stored as JSON: `serving/data/serving/process_maps/{session_id}_map.json`
- Example: "customer feedback dashboard" goal → 5 activities with sequential dependencies
- **Auditability**: Can see how process evolved over time
- **Debugging**: Can inspect map state at any point in history
- **Persistence**: Map survives serving restart
- **Reusability**: Future: could reuse successful process maps as templates

**Alternatives Considered**:
- **Implicit state in session**: Simple but loses evolution history and makes debugging difficult
- **Event sourcing only**: Could reconstruct map from events but expensive and complex

**Linked Requirements**: FR-3 (Process Map Creation), FR-7 (Process Map Evolution), NFR-3 (Reliability)

**Data Model**: `serving/models/process_map.py` - includes activities, dependencies, version history, conversation exchanges

**Status**: ✅ Implemented

---

### TD-A5: Virtual Compute Pool Model

**Decision**: Serving aggregates capabilities from all registered compute instances and routes tasks based on capability matching.

**Rationale**:
- **Horizontal scaling**: Add more compute instances to increase capacity
- **Geographic distribution**: Compute instances can be in different locations
- **Specialization**: Some computes can have specialized agents (e.g., GPU-enabled)
- **Fault tolerance**: Task can be routed to different instance if one fails
- **Resource optimization**: Balance load across available compute

**Alternatives Considered**:
- **Static assignment**: Pre-assign tasks to specific computes. Rejected as inflexible and doesn't handle failures.
- **Client-side routing**: Clients choose compute. Rejected as it exposes internal topology and prevents optimization.

**Linked Requirements**: FR-9 (Compute Registration), FR-10 (Task Routing), NFR-2 (Scalability), NFR-3 (Reliability)

**Routing Strategy**: Currently simple capability matching. Future: load-based, locality-aware, cost-optimized routing.

**Status**: ✅ Implemented

---

## Technology Stack

### TD-T1: Python 3.10+ for All Components

**Decision**: Use Python 3.10 or higher for all backend services.

**Rationale**:
- **LLM ecosystem**: Best library support (OpenAI, Anthropic SDKs native Python)
- **Rapid development**: High productivity language for AI/ML work
- **Type hints**: Modern Python has strong typing for maintainability (≥3.10 for improved syntax)
- **Async/await**: Native support for async I/O (FastAPI, httpx)
- **Team familiarity**: Common language for AI projects

**Alternatives Considered**:
- **JavaScript/TypeScript**: Good for full-stack but weaker LLM ecosystem
- **Go**: Excellent performance but steeper learning curve and fewer LLM libraries
- **Java**: Enterprise-grade but verbose and slower development velocity

**Linked Requirements**: NFR-1 (Performance), NFR-5 (Maintainability)

**Version Constraint**: `>=3.10` for match statements, improved type hints, better error messages

**Status**: ✅ Implemented across all components

---

### TD-T2: FastAPI for REST APIs

**Decision**: Use FastAPI framework for all REST API services (Marketplace, Serving, Compute).

**Rationale**:
- **Performance**: One of fastest Python frameworks (Starlette + Pydantic)
- **Async native**: Built on async/await for non-blocking I/O
- **Auto-generated docs**: OpenAPI/Swagger docs generated from code
- **Type validation**: Pydantic models for request/response validation
- **WebSocket support**: Native WebSocket for real-time updates
- **Modern**: Standard for new Python APIs (2020s best practice)

**Alternatives Considered**:
- **Flask**: Simpler but no async native, manual validation, slower
- **Django**: Full-featured but heavyweight for APIs, not async-first
- **aiohttp**: Lower-level, more control but more boilerplate

**Linked Requirements**: FR-1 (Agent Discovery), FR-10 (Task Routing), NFR-1 (Performance)

**OpenAPI Docs**: Auto-generated at `/docs` on each service (http://localhost:8001/docs, etc.)

**Status**: ✅ Implemented

---

### TD-T3: React for Frontend UIs

**Decision**: Use React with functional components and hooks for all web UIs.

**Rationale**:
- **Component model**: Reusable UI components match our microservices architecture
- **Ecosystem**: Massive library ecosystem for UI components, state management
- **Developer availability**: Most common frontend framework, easy to hire for
- **TailwindCSS integration**: Works seamlessly for utility-first CSS
- **WebSocket integration**: Easy to integrate real-time updates

**Alternatives Considered**:
- **Vue.js**: Similar capabilities but smaller ecosystem
- **Angular**: More opinionated, steeper learning curve
- **Svelte**: Smaller bundle size but less mature ecosystem

**Linked Requirements**: FR-1 (Agent Discovery), FR-12 (Real-Time Observability)

**Build Process**: Vite for fast builds, bundled into static assets served by FastAPI

**Component Locations**:
- Marketplace UI: `marketplace/frontend/`
- Serving UI: `serving/frontend/`

**Status**: ✅ Implemented

---

### TD-T4: TailwindCSS for Styling

**Decision**: Use TailwindCSS utility-first framework for all UI styling.

**Rationale**:
- **Utility-first**: Rapid UI development without leaving HTML
- **Consistency**: Design system built-in (spacing, colors, typography)
- **Tree-shaking**: Unused styles removed from production builds
- **Responsive**: Mobile-first responsive design built-in
- **Customization**: Easy to theme and customize

**Alternatives Considered**:
- **Plain CSS**: More control but inconsistent and slower
- **Bootstrap**: Component library but opinionated and heavier
- **Material-UI**: Good components but React-specific and opinionated

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-T5: Pydantic for Data Validation

**Decision**: Use Pydantic models for all data validation and serialization.

**Rationale**:
- **Type safety**: Runtime validation of data types
- **FastAPI integration**: Native support in FastAPI
- **Auto-documentation**: Models generate OpenAPI schemas
- **Serialization**: JSON serialization handled automatically
- **Settings management**: Environment variable loading with validation

**Alternatives Considered**:
- **Marshmallow**: Older validation library, less type-safe
- **Dataclasses**: Built-in but no validation
- **Manual validation**: Error-prone and inconsistent

**Linked Requirements**: NFR-3 (Reliability), NFR-5 (Maintainability)

**Usage**: All API request/response models, configuration classes, data models

**Status**: ✅ Implemented

---

## Data Storage

### TD-S1: Filesystem Storage for Agents and Tools

**Decision**: Store agent and tool definitions as JSON files in filesystem directories.

**Rationale**:
- **Git-friendly**: Definitions version-controlled alongside code
- **Human-readable**: Easy to inspect and edit
- **No database dependency**: Simplifies deployment
- **Directory structure**: Natural organization (agents/coordinating/, agents/specialized/)
- **Fast reads**: No network latency or database overhead

**Directory Structure**:
```
compute/data/compute/
  agents/
    coordinating/
      process-mapper-agent.json
      agent-selector-agent.json
      ...
    specialized/
      content-writer-agent.json
      data-analyst-agent.json
      ...
  tools/
    python-executor-tool.json
    web-search-tool.json
    ...
```

**Alternatives Considered**:
- **Database storage**: More flexible queries but adds dependency and complexity for static data
- **Embedded in code**: Fastest but not editable without redeployment

**Linked Requirements**: FR-1 (Agent Discovery), FR-2 (Agent Execution)

**Status**: ✅ Implemented

**Migration Path**: For large-scale deployments, could cache in database while keeping filesystem as source of truth.

---

### TD-S1B: Marketplace Owns Agent Definitions, Compute Caches

**Decision**: Marketplace is the single source of truth for all agent and tool definitions. Compute instances USE definitions but do not OWN them. Short-lived caching in Compute is allowed for performance.

**Rationale**:
- **Single source of truth**: Prevents definition drift and conflicts
- **Centralized updates**: Agent definitions updated once in Marketplace, propagate to all compute instances
- **Version control**: Marketplace tracks definition versions
- **Discovery**: Marketplace provides search and filtering across all agents
- **Access control**: Organization-based visibility enforced at Marketplace level
- **Performance**: Compute can cache definitions to avoid repeated fetches, but cache is short-lived and disposable

**Data Flow**:
```
1. Agent definition stored in Marketplace
2. Serving queries Marketplace for agent metadata (discovery)
3. Serving routes task to Compute
4. Compute fetches agent definition from Marketplace (via Serving proxy)
5. Compute caches definition in memory (short-lived, e.g., 5 minutes)
6. Compute executes agent using cached definition
7. Cache expires, next execution fetches fresh definition
```

**Cache Strategy**:
- **In-memory only**: No persistent storage of agent definitions in Compute
- **TTL-based**: Cache expires after configurable time (default 5 minutes)
- **Invalidation**: Cache cleared on Compute restart
- **Fallback**: If cache miss, fetch from Marketplace via Serving

**What Marketplace OWNS**:
- ✅ Agent definitions (JSON files with capabilities, prompts, model settings)
- ✅ Tool definitions (JSON files with tool specifications)
- ✅ User and organization data
- ✅ A2A protocol cards
- ✅ Agent approval workflow state

**What Compute DOES NOT OWN**:
- ❌ Agent definitions (only caches temporarily)
- ❌ Agent discovery/search (that's Marketplace)
- ❌ Agent metadata versioning (that's Marketplace)

**What Compute DOES OWN**:
- ✅ Execution logs for agents it runs
- ✅ LLM provider connection state
- ✅ Temporary execution context
- ✅ Performance metrics for executions

**Alternatives Considered**:
- **Compute owns agent definitions**: Causes definition drift across instances, harder to update, no central discovery
- **No caching**: Poor performance, every execution fetches definition
- **Long-lived cache**: Risk of stale definitions, harder to propagate updates

**Linked Requirements**: FR-1 (Agent Discovery), FR-2 (Agent Execution), NFR-5 (Maintainability)

**Status**: ✅ Architecture implemented (caching optimization pending)

**Planned Enhancement**: Add TTL-based cache in Compute with metrics on cache hit/miss rates.

---

### TD-S2: SQLite for Session and Process Map Storage

**Decision**: Use SQLite for storing sessions, process maps, and runtime state in serving component.

**Rationale**:
- **Zero configuration**: No separate database server required
- **Embedded**: Database file local to serving instance
- **ACID transactions**: Data consistency guarantees
- **Fast for small-medium scale**: Suitable for development and small deployments
- **Python native**: `sqlite3` module in standard library

**Database Location**: `data/serving/datastore/claudevn_serving.db`

**Schema**:
- `sessions` table: Session metadata, status, business goal
- `process_maps` table: Serialized process map JSON with version history
- `events` table: Observability events for audit trail

**Alternatives Considered**:
- **PostgreSQL**: More scalable but requires separate server (planned migration)
- **JSON files**: Simpler but no transaction support or query capabilities
- **In-memory only**: Fastest but no persistence

**Linked Requirements**: FR-3 (Process Map Creation), FR-12 (Real-Time Observability), NFR-3 (Reliability)

**Status**: ✅ Implemented for development

**Known Limitation**: SQLite not suitable for high-concurrency production deployments. Migration to PostgreSQL planned.

**Migration Plan**: 
- SQLite for v0.x (development and small deployments)
- PostgreSQL option in v1.0 (production)
- Use Alembic for schema migrations
- Provide migration script for SQLite → PostgreSQL

---

### TD-S3: Storage Abstraction Layer

**Decision**: Implement storage interface with pluggable backends (filesystem, S3, DynamoDB, etc.).

**Rationale**:
- **Future-proof**: Easy to add cloud storage without code changes
- **Deployment flexibility**: Choose storage based on environment (local dev uses filesystem, production uses S3)
- **Testability**: Mock storage for unit tests
- **Consistency**: Same interface across all components

**Interface**: `marketplace/storage/storage_interface.py`

**Implementations**:
- `FilesystemStorage`: Local JSON files (default)
- `S3Storage`: AWS S3 (planned)
- `DynamoDBStorage`: AWS DynamoDB (planned)

**Alternatives Considered**:
- **Direct filesystem access**: Simple but inflexible
- **ORM only**: Doesn't handle object/file storage well

**Linked Requirements**: FR-1 (Agent Discovery), NFR-6 (Deployability)

**Status**: ✅ Interface implemented, filesystem backend complete, cloud backends planned

---

## Communication Patterns

### TD-C1: REST APIs for Synchronous Communication

**Decision**: Use REST APIs for all synchronous request/response communication between components.

**Rationale**:
- **Standard protocol**: HTTP/JSON universally supported
- **Tooling**: Excellent debugging tools (curl, Postman, browser)
- **Documentation**: OpenAPI/Swagger auto-generated
- **Stateless**: Each request independent, simplifies scaling
- **Idempotent**: GET/PUT/DELETE operations safely retryable

**API Versioning**: URL path versioning (`/api/v1/...`) for backward compatibility

**Alternatives Considered**:
- **gRPC**: More efficient but less accessible, harder to debug
- **GraphQL**: Flexible queries but adds complexity for simple CRUD
- **Message queue**: Async but doesn't fit request/response pattern

**Linked Requirements**: FR-9 (Compute Registration), FR-10 (Task Routing), FR-11 (Marketplace Proxy)

**Status**: ✅ Implemented

---

### TD-C2: WebSocket for Real-Time Updates

**Decision**: Use WebSocket connections from UI clients to serving for real-time event streaming.

**Rationale**:
- **Bidirectional**: Server can push updates to client without polling
- **Low latency**: Near-instant updates (< 500ms)
- **Efficient**: Single persistent connection vs repeated HTTP requests
- **Standard protocol**: Native browser support (WebSocket API)

**Connection Lifecycle**:
1. Client connects via WebSocket (`ws://localhost:8002/ws`)
2. Client subscribes to event types (activity_state_changed, map_evolved, etc.)
3. Server pushes events as they occur
4. Client updates UI in real-time
5. Connection maintained with heartbeat

**Alternatives Considered**:
- **Server-Sent Events (SSE)**: Simpler but unidirectional only
- **Polling**: Simple but inefficient and delayed
- **Long-polling**: Better than polling but still inefficient

**Linked Requirements**: FR-12 (Real-Time Observability), NFR-1 (Performance)

**Implementation**: FastAPI WebSocket endpoint in `serving/api/observability.py`

**Status**: ✅ Implemented

---

### TD-C3: HTTP Polling for Compute Heartbeats

**Decision**: Compute instances send periodic HTTP POST requests to serving for health monitoring.

**Rationale**:
- **Simple**: No persistent connections required
- **Stateless**: Serving doesn't maintain connection state
- **Firewall-friendly**: Outbound HTTP allowed in most networks
- **Failure detection**: Missing heartbeats indicate failure

**Heartbeat Interval**: 30 seconds (configurable via `COMPUTE_HEARTBEAT_INTERVAL`)

**Health States**:
- `healthy`: Heartbeat received within 60s
- `degraded`: Heartbeat missed (60-90s)
- `offline`: No heartbeat for 90s+

**Alternatives Considered**:
- **WebSocket**: More efficient but requires persistent connection and complicates compute restarts
- **TCP keepalive**: Lower level but not HTTP-friendly

**Linked Requirements**: FR-9 (Compute Registration), NFR-3 (Reliability)

**Status**: ✅ Implemented

**Known Issue**: No automatic cleanup of stale registrations. Manual script required (`scripts/cleanup_compute_registrations.sh`). TTL-based expiration planned.

---

### TD-C4: Async HTTP Client for Inter-Service Communication

**Decision**: Use `httpx` async HTTP client for all service-to-service communication.

**Rationale**:
- **Async/await native**: Works with FastAPI's async model
- **Connection pooling**: Reuses connections for efficiency
- **Timeout handling**: Built-in timeout support
- **Modern API**: Similar to `requests` but async

**Example**: Compute → Serving communication, Serving → Marketplace proxy

**Alternatives Considered**:
- **requests**: Synchronous only, blocks thread
- **aiohttp**: Good but different API from `requests`, less familiar

**Linked Requirements**: FR-10 (Task Routing), FR-11 (Marketplace Proxy), NFR-1 (Performance)

**Status**: ✅ Implemented

---

## Security and Authentication

### TD-SEC1: Session-Based Authentication (Marketplace Only)

**Decision**: Implement session-based authentication with username/password for marketplace UI.

**Rationale**:
- **Simple**: No JWT signing/verification complexity for initial version
- **Stateful**: Session stored server-side with secure session ID
- **Cookie-based**: Secure, HttpOnly cookies prevent XSS
- **Standard**: Well-understood pattern

**Implementation**:
- Login endpoint creates session, returns cookie
- Session ID stored in server memory/database
- Cookie sent with all requests for authentication
- Logout endpoint invalidates session

**Alternatives Considered**:
- **JWT tokens**: Stateless but more complex, harder to revoke
- **OAuth2**: Over-engineered for internal tool
- **API keys**: Good for programmatic access but not UI

**Linked Requirements**: FR-15 (User Management), NFR-7 (Security)

**Status**: ✅ Implemented in Marketplace only

**Known Limitation**: Serving and Compute have no authentication. Not production-secure.

**Planned**: 
- Extend to serving and compute in v0.4.0
- Add JWT option for programmatic access
- Add API key management

---

### TD-SEC2: Environment Variables for Secrets

**Decision**: Store sensitive configuration (API keys, passwords) in environment variables, never in code.

**Rationale**:
- **Security**: Prevents secrets in version control
- **Flexibility**: Different values per environment (dev, staging, prod)
- **12-factor app**: Industry best practice
- **Docker-friendly**: Easy to pass via docker-compose or Kubernetes secrets

**Secret Types**:
- `OPENAI_API_KEY`: OpenAI API authentication
- `ANTHROPIC_API_KEY`: Anthropic API authentication
- Database passwords (future)
- Session secret keys

**Configuration Loading**: `Pydantic.BaseSettings` with `env_prefix` for namespacing

**Alternatives Considered**:
- **Config files**: Risk of committing secrets
- **Secret management service**: Over-engineered for current scale (planned for production)

**Linked Requirements**: NFR-7 (Security)

**Status**: ✅ Implemented

**Example**: `.env.example` files provided, actual `.env` files in `.gitignore`

---

### TD-SEC3: No TLS (Development Only)

**Decision**: HTTP (not HTTPS) for all communication in development.

**Rationale**:
- **Simplicity**: No certificate management for local development
- **Debugging**: Easier to inspect traffic
- **Localhost only**: Development services not exposed to network

**Alternatives Considered**: N/A - TLS required for production

**Linked Requirements**: NFR-7 (Security)

**Status**: ⚠️ Development only - NOT production-secure

**Planned**:
- TLS required for production deployment (v1.0)
- Certificate management via Let's Encrypt or cloud provider
- Component-to-component mutual TLS (mTLS) option

---

### TD-SEC4: Input Validation and Sanitization

**Decision**: Validate all API inputs using Pydantic models and sanitize before use.

**Rationale**:
- **Injection prevention**: Prevents SQL injection, command injection
- **Type safety**: Ensures data types match expectations
- **Error handling**: Clear error messages for invalid input
- **Auto-documentation**: OpenAPI schemas show valid input formats

**Validation Rules**:
- String lengths limited (e.g., username 3-50 chars)
- Enum validation for status fields
- Regex patterns for IDs and names
- JSON schema validation for complex objects

**Alternatives Considered**:
- **Manual validation**: Error-prone and inconsistent
- **No validation**: Security risk

**Linked Requirements**: NFR-7 (Security), NFR-3 (Reliability)

**Status**: ✅ Implemented via Pydantic models

---

## Infrastructure

### TD-I1: Docker Containers for Deployment

**Decision**: Package each component as Docker container with multi-stage builds.

**Rationale**:
- **Consistency**: Same environment in dev, test, production
- **Isolation**: Dependencies don't conflict
- **Portability**: Runs anywhere Docker runs
- **Orchestration-ready**: Works with Docker Compose, Kubernetes

**Docker Images**:
- `claudevn/marketplace:0.3.0`
- `claudevn/serving:0.3.0`
- `claudevn/compute:0.3.0`

**Multi-stage Build**: Build frontend in Node image, copy to Python image for smaller final size

**Alternatives Considered**:
- **Virtual environments only**: Less isolation, harder to deploy
- **System packages**: Dependency conflicts, not portable

**Linked Requirements**: NFR-6 (Deployability)

**Status**: ✅ Implemented

---

### TD-I2: Docker Compose for Development

**Decision**: Use Docker Compose to orchestrate all services for local development.

**Rationale**:
- **Single command start**: `docker-compose up` starts everything
- **Service dependencies**: Automatic startup order
- **Networking**: Services can communicate via service names
- **Volume mounts**: Local code changes reflected in containers (bind mounts)
- **Environment variables**: Centralized configuration in `docker.env`

**Compose File**: `docker-compose.yml` defines 3+ services (marketplace, serving, compute-1, compute-2, ...)

**Alternatives Considered**:
- **Manual service start**: Tedious and error-prone
- **Kubernetes locally**: Over-complicated for development

**Linked Requirements**: NFR-6 (Deployability)

**Status**: ✅ Implemented

---

### TD-I3: Bind Mounts for Development, Volumes for Data

**Decision**: Use bind mounts for code (live reload) and named volumes for persistent data.

**Rationale**:
- **Bind mounts for code**: Local edits immediately available in container
- **Named volumes for data**: Persists across container restarts, better performance on Mac/Windows
- **Separation**: Code is ephemeral (from Git), data is persistent (logs, databases)

**Bind Mount Example**: `./marketplace:/app` (local code → container)

**Named Volume Example**: `marketplace_data:/app/data` (persistent storage)

**Alternatives Considered**:
- **All bind mounts**: Poor performance on Mac/Windows for data files
- **All volumes**: Can't edit code locally
- **No persistence**: Data lost on restart

**Linked Requirements**: NFR-6 (Deployability)

**Status**: ✅ Implemented

---

### TD-I4: Separate Startup Scripts for Development

**Decision**: Provide shell scripts (`start.sh`, `stop.sh`, `start_all.sh`) for non-Docker development.

**Rationale**:
- **Debugging**: Easier to debug without Docker layer
- **Fast iteration**: No container rebuild on code change
- **Python virtual envs**: Native Python development workflow
- **Port management**: Automatic port conflict detection

**Scripts**:
- `start_all.sh`: Start all services with dependency checking
- `stop_all.sh`: Stop all services gracefully
- `status.sh`: Check service status and health
- Individual `start.sh` per component

**Alternatives Considered**:
- **Docker only**: Slower rebuild cycle
- **No scripts**: Manual service management

**Linked Requirements**: NFR-6 (Deployability), NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-I5: Port Allocation

**Decision**: Fixed port assignments for services with conflict detection.

**Port Assignments**:
- Marketplace: 8001
- Serving: 8002
- Compute-1: 8003
- Compute-2: 8004
- Compute-N: 8003 + N

**Rationale**:
- **Predictable**: Documentation can reference fixed URLs
- **No collisions**: Each service has dedicated port
- **Easy testing**: Can test specific service directly
- **Multi-instance support**: Compute instances increment from 8003

**Conflict Detection**: `start_all.sh` checks if ports in use, can automatically kill or skip

**Alternatives Considered**:
- **Random ports**: Harder to document and test
- **Port 80/443**: Requires root, conflicts with other services

**Linked Requirements**: NFR-6 (Deployability)

**Status**: ✅ Implemented

---

## Design Patterns

### TD-DP1: Service Layer Pattern

**Decision**: Implement business logic in service classes separate from API endpoints.

**Rationale**:
- **Separation of concerns**: API handles HTTP, services handle logic
- **Testability**: Services tested without HTTP layer
- **Reusability**: Services can be called from multiple endpoints or other services
- **Maintainability**: Logic centralized, not duplicated across endpoints

**Pattern Structure**:
```
api/
  agents.py          # FastAPI endpoints (HTTP handling)
services/
  agent_service.py   # Business logic
models/
  agent.py           # Data models
storage/
  storage_interface.py  # Data access
```

**Example**: `marketplace/api/agents.py` calls `marketplace/services/agent_service.py`

**Alternatives Considered**:
- **Logic in endpoints**: Simpler but less testable and harder to maintain
- **Domain-driven design**: More complex than needed for current scale

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented across all components

---

### TD-DP2: Repository Pattern for Data Access

**Decision**: Abstract data access behind storage interface with implementations for different backends.

**Rationale**:
- **Abstraction**: Business logic doesn't know storage details
- **Testability**: Mock storage for unit tests
- **Flexibility**: Swap storage backend without changing business logic
- **Consistency**: Same pattern across components

**Interface**: Abstract base class defining CRUD operations

**Implementations**: Filesystem, SQLite, (future: S3, PostgreSQL, DynamoDB)

**Alternatives Considered**:
- **Direct data access**: Tightly couples logic to storage
- **ORM**: Good for SQL but doesn't fit file/object storage

**Linked Requirements**: FR-1 (Agent Discovery), NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-DP3: Dependency Injection for Configuration

**Decision**: Pass dependencies (config, storage, services) explicitly rather than using globals or singletons.

**Rationale**:
- **Testability**: Easy to inject mocks for testing
- **Clarity**: Dependencies explicit in function signatures
- **Flexibility**: Different configurations per environment
- **No global state**: Avoids side effects and race conditions

**Implementation**: FastAPI `Depends()` for endpoint dependencies

**Example**:
```python
@router.get("/agents")
async def list_agents(
    storage: Storage = Depends(get_storage),
    config: Config = Depends(get_config)
):
    ...
```

**Alternatives Considered**:
- **Global variables**: Harder to test, hidden dependencies
- **Singletons**: Better than globals but still couples code

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-DP4: Event Sourcing for Observability

**Decision**: Emit events for all significant state changes and persist them in order.

**Rationale**:
- **Audit trail**: Complete history of what happened
- **Debugging**: Can replay events to understand issues
- **Real-time updates**: Events drive UI updates
- **Analytics**: Event stream can be analyzed for insights

**Event Types**:
- `activity_state_changed`: Activity status updated
- `exchange_added`: Conversation message added
- `map_evolved`: Process map structure changed
- `session_status_changed`: Session status updated

**Event Structure**:
```json
{
  "event_type": "activity_state_changed",
  "session_id": "sess-123",
  "timestamp": "2025-12-16T10:30:00Z",
  "data": {
    "activity_id": "act-1",
    "old_state": "ready",
    "new_state": "in_progress"
  }
}
```

**Alternatives Considered**:
- **Direct state updates only**: Loses history
- **Database triggers**: Couples storage to business logic
- **Full event sourcing**: More complex than needed (events supplement, not replace, primary storage)

**Linked Requirements**: FR-12 (Real-Time Observability), NFR-4 (Observability)

**Status**: ✅ Implemented

---

### TD-DP5: Strategy Pattern for LLM Providers

**Decision**: Abstract LLM provider behind interface with implementations for OpenAI, Anthropic, Mock.

**Rationale**:
- **Flexibility**: Easy to add new providers
- **Fallback chain**: Try OpenAI, fall back to Anthropic, fall back to Mock
- **Testing**: Mock provider for deterministic tests
- **Cost optimization**: Could route to cheaper provider for simple tasks (future)

**Interface**: `LLMClient` abstract base class

**Implementations**:
- `OpenAIClient`: GPT-4, GPT-3.5
- `AnthropicClient`: Claude models
- `MockClient`: Returns predetermined responses for testing

**Provider Selection**: Environment variables or agent-level configuration

**Alternatives Considered**:
- **Hardcoded OpenAI**: Inflexible and vendor lock-in
- **LangChain**: Heavy framework, more than we need currently

**Linked Requirements**: FR-2 (Agent Execution), NFR-3 (Reliability)

**Implementation**: `compute/runtime/llm_client.py`

**Status**: ✅ Implemented

---

## LLM Integration

### TD-LLM1: Agent Definitions as JSON Files

**Decision**: Define agents as JSON files with prompt templates, not code.

**Rationale**:
- **Declarative**: Agents defined by data, not code
- **No deployment**: Update agents without restarting services
- **Version control**: Agent definitions tracked in Git
- **Marketplace-friendly**: Easy to export/import agents
- **Non-programmer editable**: Product people can modify prompts

**Agent Schema**:
```json
{
  "id": "content-writer-v1",
  "name": "Content Writer",
  "description": "Generates written content",
  "capabilities": ["content_generation", "copywriting"],
  "prompt_template": "...",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2000
}
```

**Alternatives Considered**:
- **Code-based agents**: More flexible but requires deployment and programming knowledge
- **Database storage**: Adds dependency, less Git-friendly

**Linked Requirements**: FR-1 (Agent Discovery), FR-2 (Agent Execution)

**Status**: ✅ Implemented

---

### TD-LLM2: Prompt Templates with Jinja2

**Decision**: Use Jinja2 template syntax for agent prompt templates with variable substitution.

**Rationale**:
- **Dynamic prompts**: Insert context, prior results, business goals
- **Familiar syntax**: Jinja2 widely used in Python ecosystem
- **Logic support**: Conditionals and loops if needed
- **Safety**: Template injection handled by Jinja2

**Example**:
```jinja2
You are a {{agent.name}}. 

Business Goal: {{business_goal}}

Context: {{context}}

Task: {{task_description}}

Please analyze and provide your output.
```

**Alternatives Considered**:
- **String formatting**: Less powerful, no conditionals
- **Custom template language**: Reinventing the wheel

**Linked Requirements**: FR-2 (Agent Execution), FR-4 (Activity Facilitation)

**Status**: ✅ Implemented

---

### TD-LLM3: Structured Output with JSON Parsing

**Decision**: Instruct LLMs to output JSON and parse into structured objects.

**Rationale**:
- **Predictability**: Structured data easier to work with than free text
- **Validation**: Can validate against schema
- **Integration**: Structured output can be input to next agent
- **Error handling**: Detect malformed output and retry

**Prompt Pattern**:
```
OUTPUT FORMAT:
{
  "analysis": "...",
  "recommendations": ["...", "..."],
  "confidence": "high|medium|low"
}
```

**Parsing**: Python `json.loads()` with error handling and retry on parse failure

**Fallback**: If JSON parsing fails multiple times, accept free-text output

**Alternatives Considered**:
- **Free text only**: Flexible but hard to process programmatically
- **XML**: More verbose than JSON
- **Function calling**: OpenAI-specific, not portable

**Linked Requirements**: FR-2 (Agent Execution), FR-8 (Result Synthesis)

**Status**: ✅ Implemented

---

### TD-LLM4: Token Tracking and Cost Estimation

**Decision**: Track token usage per agent execution and estimate costs.

**Rationale**:
- **Cost awareness**: Understand LLM spend
- **Optimization**: Identify expensive operations
- **Budgeting**: Estimate costs for large workflows
- **Reporting**: Show token usage to users

**Tracked Metrics**:
- Prompt tokens (input)
- Completion tokens (output)
- Total tokens
- Estimated cost (based on provider pricing)

**Implementation**: Parse token counts from LLM API responses, store in execution results

**Alternatives Considered**:
- **No tracking**: Blind to costs
- **External billing only**: Harder to attribute costs to specific operations

**Linked Requirements**: NFR-4 (Observability)

**Status**: 🔨 Partially implemented (tracking in place, no UI display yet)

---

### TD-LLM5: Mock LLM Provider for Testing

**Decision**: Implement mock LLM provider that returns predetermined responses.

**Rationale**:
- **Deterministic tests**: Tests don't fail due to LLM variance
- **No API costs**: Tests run without LLM API calls
- **Fast**: No network latency
- **Offline development**: Work without internet

**Mock Strategy**:
- Map agent ID to canned responses
- Return consistent JSON output
- Simulate token counts
- Optional delay for realism

**Example**:
```python
mock_responses = {
    "process-mapper-v1": {
        "activities": [...],
        "dependencies": [...]
    }
}
```

**Alternatives Considered**:
- **Real LLM in tests**: Expensive, slow, flaky
- **No LLM testing**: Integration gaps

**Linked Requirements**: TD-TEST2 (Integration Testing), NFR-3 (Reliability)

**Status**: ✅ Implemented

---

## Testing Strategy

### TD-TEST1: Test Pyramid Approach

**Decision**: Follow test pyramid with unit tests (base), integration tests (middle), E2E tests (top).

**Rationale**:
- **Fast feedback**: Unit tests run in milliseconds
- **Isolation**: Unit tests don't depend on external services
- **Coverage**: Integration tests verify components work together
- **Confidence**: E2E tests verify user workflows

**Test Distribution Target**:
- 70% unit tests (services, utilities, models)
- 20% integration tests (API endpoints, database, LLM mocks)
- 10% E2E tests (full workflows across components)

**Alternatives Considered**:
- **Only E2E tests**: Slow, hard to debug failures
- **Only unit tests**: Misses integration issues

**Linked Requirements**: NFR-5 (Maintainability), NFR-3 (Reliability)

**Status**: 🔨 Partial - Unit tests exist, integration tests exist, E2E coverage incomplete

---

### TD-TEST2: pytest for All Tests

**Decision**: Use pytest framework for all Python tests.

**Rationale**:
- **Powerful fixtures**: Dependency injection for tests
- **Parametrization**: Run same test with multiple inputs
- **Plugins**: Rich ecosystem (pytest-asyncio, pytest-cov)
- **Clear output**: Good failure messages
- **Async support**: Native async test support

**Test Organization**:
```
component/
  tests/
    unit/
      test_services.py
      test_models.py
    integration/
      test_api.py
      test_storage.py
    e2e/
      test_complete_workflow.py
```

**Alternatives Considered**:
- **unittest**: Built-in but less powerful
- **nose**: Older, less maintained

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-TEST3: E2E Test Scripts with Shell

**Decision**: Implement end-to-end tests as shell scripts that orchestrate full workflows.

**Rationale**:
- **Realistic**: Tests same paths users follow
- **Language-agnostic**: Works across all services
- **Easy to run**: `./test_pipeline_e2e.sh`
- **Documentation**: Script itself documents workflow

**E2E Tests**:
- `test_mock_e2e.sh`: Full workflow with mock LLM
- `test_pipeline_e2e.sh`: Pipeline execution
- `test_serving_ui.sh`: UI functionality
- `test_complete_emergent_workflow.py`: Week 6 integration test

**Alternatives Considered**:
- **Python E2E tests only**: Misses shell script user experience
- **Manual testing only**: Not repeatable

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-TEST4: Test Data Seeding

**Decision**: Provide seed data files for consistent test environments.

**Rationale**:
- **Repeatability**: Tests start from known state
- **Documentation**: Seed data shows example structures
- **Demo-ready**: Seed data works for demos too

**Seed Data Locations**:
- `marketplace/seed_data/agents.json`: Example agents
- `marketplace/seed_data/organizations.json`: Org hierarchy
- `marketplace/seed_data/users.json`: Test users

**Loading**: `scripts/seed_marketplace.sh` loads seed data

**Alternatives Considered**:
- **Generate data in tests**: More work, less realistic
- **No seed data**: Inconsistent test states

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

## Deployment and Operations

### TD-OPS1: Structured Logging with Python logging Module

**Decision**: Use Python `logging` module with structured log format across all components.

**Rationale**:
- **Standard library**: No external dependency
- **Configurable levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Multiple handlers**: File + console output
- **Rotation**: Built-in file rotation support
- **Structured format**: Timestamp, level, component, message

**Log Format**:
```
2025-12-16 10:30:15 [INFO] [marketplace.api.agents] Agent registered: content-writer-v1
```

**Log Locations**:
- `logs/marketplace.log`
- `logs/serving.log`
- `logs/compute.log`

**Rotation**: Daily rotation, keep 7 days (configurable)

**Alternatives Considered**:
- **Print statements**: Not production-suitable
- **External logging library**: Unnecessary complexity

**Linked Requirements**: NFR-4 (Observability)

**Status**: ✅ Implemented

---

### TD-OPS2: Health Check Endpoints

**Decision**: Implement `/api/v1/health` endpoint on all services returning JSON health status.

**Rationale**:
- **Monitoring**: Load balancers and monitoring tools can check health
- **Debugging**: Quick way to verify service is running
- **Dependency checking**: Can verify database, LLM provider, etc.

**Health Check Response**:
```json
{
  "status": "healthy",
  "version": "0.3.0",
  "timestamp": "2025-12-16T10:30:00Z",
  "dependencies": {
    "database": "healthy",
    "llm_provider": "healthy"
  }
}
```

**Status Values**: `healthy`, `degraded`, `unhealthy`

**Alternatives Considered**:
- **No health checks**: Harder to monitor
- **Custom protocol**: Non-standard

**Linked Requirements**: NFR-4 (Observability), NFR-3 (Reliability)

**Status**: ✅ Implemented

---

### TD-OPS3: Version File for Coordinated Releases

**Decision**: Single `VERSION` file at project root with semantic version number.

**Rationale**:
- **Single source of truth**: All components reference same version
- **Release coordination**: Version bump applies to all components
- **Simplicity**: Easy to update (one file change)

**Format**: `MAJOR.MINOR.PATCH` (Semantic Versioning)

**Example**: `0.3.0`

**Version References**:
- `VERSION` file
- `pyproject.toml` or `setup.py` (if package published)
- Docker image tags
- API responses (`/health` endpoint)

**Alternatives Considered**:
- **Per-component versions**: More complex, harder to coordinate
- **Git commit SHA**: Not human-readable

**Linked Requirements**: NFR-5 (Maintainability)

**Status**: ✅ Implemented

---

### TD-OPS4: Graceful Shutdown Handling

**Decision**: Implement signal handling (SIGTERM, SIGINT) for graceful shutdown.

**Rationale**:
- **Data integrity**: Finish in-flight requests before shutdown
- **Connection cleanup**: Close database and network connections properly
- **Resource cleanup**: Release file handles, temp files, etc.

**Shutdown Sequence**:
1. Receive shutdown signal
2. Stop accepting new requests
3. Finish in-flight requests (with timeout)
4. Close database connections
5. Flush logs
6. Exit cleanly

**Alternatives Considered**:
- **Immediate exit**: Risks data loss and corruption
- **No signal handling**: Killed forcefully by system

**Linked Requirements**: NFR-3 (Reliability)

**Status**: 🔨 Partial - Basic handling in place, not fully tested

---

### TD-OPS5: Environment-Based Configuration

**Decision**: Use environment variables for all configuration, with `.env` files for local development.

**Rationale**:
- **12-factor app**: Industry best practice
- **Deployment flexibility**: Different config per environment
- **Security**: Secrets not in code
- **Docker-friendly**: Easy to pass env vars to containers

**Configuration Loading**:
1. Check environment variables first
2. Fall back to `.env` file (development)
3. Fall back to defaults (hardcoded)

**Example**: `COMPUTE_PORT=8003` (env) > `.env` file > default (8003)

**Alternatives Considered**:
- **Config files only**: Less flexible, harder to deploy
- **Command-line arguments**: Verbose, not Docker-friendly

**Linked Requirements**: NFR-6 (Deployability)

**Status**: ✅ Implemented

---

## Decision History and Changes

### Planned Changes

**v0.4.0 (Q1 2026)**:
- **TD-SEC1**: Extend authentication to serving and compute
- **TD-S2**: Provide PostgreSQL option as alternative to SQLite
- **TD-C3**: Implement TTL-based cleanup for stale compute registrations

**v1.0.0 (Q2 2026)**:
- **TD-SEC3**: Require TLS for production deployments
- **TD-S2**: Recommend PostgreSQL for production (SQLite for development only)
- **TD-OPS6** (new): Implement metrics export (Prometheus)
- **TD-OPS7** (new): Add structured logging to external systems (ELK stack)

### Deprecated Decisions

None yet. This section will track decisions that are no longer relevant or have been superseded.

---

## Recent Changes (December 2025)

### Mock LLM Provider Enhancement (December 18, 2025)

**Change**: Enhanced Mock LLM provider with agent-aware response system to support coordinating agents that require structured JSON outputs.

**Implementation**:
- Added `AGENT_RESPONSES` dictionary mapping coordinating agent IDs to expected JSON response formats
- Modified `MockProvider.generate()` to detect agent_id in kwargs and return agent-specific responses
- Updated `AgentExecutor` to pass `agent_id` and `agent_metadata` to all LLM providers (Mock, OpenAI, Anthropic)
- Fixed JSON parsing in `CoordinatingTeamService` to extract from `output.content` structure

**Impact**:
- **All 5 coordinating agents now fully functional**: Activity Facilitator, Agent Selector, Consistency Manager, Progress Reporter, Result Synthesizer
- Enables cost-free testing of facilitated workflows without real LLM API calls
- Real LLM providers (OpenAI/Anthropic) can now access agent metadata for context-aware responses
- Standardized response format across all agent types: `{output: {content: "...", format: "text"}}`

**Files Modified**:
- `compute/runtime/providers/mock_provider.py` - Added AGENT_RESPONSES and agent detection logic
- `compute/services/agent_executor.py` - Modified LLM call to pass agent metadata (lines 157-166)
- `serving/services/coordinating_team_service.py` - Fixed `parse_facilitator_output()` and `_parse_json_output()`
- `serving/api/process_maps.py` - Fixed datetime serialization in coordinating agent endpoints

**Testing**: All coordinating agent endpoints validated (82% of functional tests passing, up from 74%).

---

## Document Maintenance

This document should be updated when:
1. **New technical decision made**: Add new section with TD-XXX ID
2. **Decision changes**: Update existing section, note in "Planned Changes"
3. **Decision deprecated**: Move to "Deprecated Decisions" with reasoning
4. **Alternative proven better**: Update "Alternatives Considered" with learnings

**Review Cadence**: Before each release (every 2-4 weeks)

**Ownership**: Tech lead approves changes. Developers and AI agents propose updates.

---

## Related Documents

- [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md) - What the system does and why
- [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md) - Implementation roadmap
- [docs/ARCHITECTURE_RESOLUTION_SUMMARY.md](docs/ARCHITECTURE_RESOLUTION_SUMMARY.md) - Gap analysis
- [README.md](README.md) - Quick start guide
