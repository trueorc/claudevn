# ClaudeVN Functional Requirements

**Version**: 0.3.0  
**Last Updated**: December 18, 2025  
**Status**: Living Document - Source of Truth  
**Purpose**: Define what ClaudeVN does and why, for all stakeholders working on the system

---

## Document Purpose

This document serves as the **authoritative source of truth** for ClaudeVN's functional and non-functional requirements. It is intentionally non-technical and focuses on **what** the system does and **why** it exists. For technical implementation decisions, see [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md).

**Target Audience**: Product owners, developers, testers, AI agents, and anyone tasked with understanding or modifying the system.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Three-Component Architecture](#three-component-architecture)
3. [Core Concepts](#core-concepts)
4. [Functional Requirements](#functional-requirements)
5. [Non-Functional Requirements](#non-functional-requirements)
6. [User Roles and Permissions](#user-roles-and-permissions)
7. [Integration Points](#integration-points)
8. [Future Vision](#future-vision)

---

## System Overview

### What is ClaudeVN?

ClaudeVN is an **AI agent orchestration platform** that enables dynamic, conversation-driven coordination between specialized AI agents to accomplish complex business goals. Unlike traditional workflow systems that require predefined pipelines, ClaudeVN facilitates emergent collaboration where agents self-organize and adapt during execution.

### Problem Statement

Complex business processes often require:
- Multiple specialized AI agents working together
- Dynamic adaptation when requirements change or blockers occur
- Quality assurance to catch contradictory outputs
- Synthesis of results from multiple sources into coherent deliverables

Traditional workflow orchestration breaks down when:
- The sequence of steps isn't known upfront
- Requirements emerge during execution
- Blockers require dynamic replanning
- Manual coordination overhead becomes prohibitive

### Solution Approach

ClaudeVN provides:
1. **Agent Discovery**: A marketplace where agents with different capabilities can be discovered and selected
2. **Distributed Execution**: Multiple compute engines that can execute agents with LLM integration
3. **Facilitated Coordination**: Coordinating agents that manage conversations, detect blockers, and synthesize results
4. **Real-Time Observability**: Live tracking of process evolution, activity status, and agent interactions

### Key Differentiators

- **Emergent Processes**: Work structure develops naturally from agent interactions rather than being predefined
- **Conversation-Driven**: Facilitator agents conduct multi-turn conversations to understand needs and detect blockers
- **Self-Correcting**: System detects contradictions across agent outputs and initiates reconciliation
- **Distributed**: Agents can run across multiple compute instances without central bottleneck
- **Standards-Based**: Uses A2A (Agent-to-Agent) protocol for interoperability

---

## Three-Component Architecture

ClaudeVN consists of three independent microservices, each with distinct responsibilities:

### Marketplace (Port 8001)

**Purpose**: Central registry and source of truth for agent definitions and metadata.

**Key Responsibilities**:
- **Agent Definition Storage**: OWNS all agent definitions (JSON files with capabilities, prompts, requirements)
- **Agent Discovery**: Provides search and filtering by capabilities and organizational scope
- **User & Organization Management**: Manages users, roles, and hierarchical organization structure
- **A2A Card Generation**: Produces Agent-to-Agent protocol cards for interoperability
- **Approval Workflow**: Manages agent submission and approval process

**Communication Pattern**: 
- **Private/Internal**: Marketplace does not expose APIs to external clients
- **Accessed via Serving**: Serving component proxies requests to marketplace
- Compute instances do NOT communicate directly with marketplace

**Data Ownership**:
- ✅ OWNS: Agent definitions, tool definitions, user data, organization hierarchy
- ❌ Does NOT own: Sessions, process maps, execution state (those belong to Serving/Compute)

**Technology**: FastAPI backend, React frontend, filesystem/S3 storage, session-based authentication

---

### Serving (Port 8002)

**Purpose**: Central orchestration hub and communication broker for the entire platform.

**Key Responsibilities**:
- **Public API**: ONLY component with publicly accessible REST API
- **Communication Broker**: Facilitates all inter-component communication via events/messages
- **Session Management**: Creates and tracks facilitated sessions with business goals
- **Process Map Management**: Stores and versions dynamic process maps
- **Compute Registry**: Tracks registered compute instances and their capabilities
- **Marketplace Proxy**: Forwards agent discovery requests to marketplace on behalf of clients
- **Event Bus**: Real-time event streaming via WebSocket to UI clients
- **Coordinating Agent Orchestration**: Invokes coordinating agents running in compute

**Communication Pattern**:
- **Public REST API**: Accepts requests from users, UI, external systems
- **Outbound to Marketplace**: Proxies agent discovery requests
- **Outbound to Compute**: Routes tasks for agent execution
- **WebSocket**: Streams events to UI clients
- **Event-driven**: Uses pub/sub for internal coordination

**Data Ownership**:
- ✅ OWNS: Sessions, process maps, compute registry, marketplace registry, event history
- ❌ Does NOT own: Agent definitions (those belong to Marketplace)

**Technology**: FastAPI backend, React frontend, SQLite/PostgreSQL, WebSocket, event bus

---

### Compute (Port 8003+)

**Purpose**: Distributed agent execution runtime with LLM integration.

**Key Responsibilities**:
- **Agent Execution**: Runs agents (both specialized and coordinating) with LLM integration
- **LLM Provider Integration**: Connects to OpenAI, Anthropic, or Mock providers
- **Tool Execution**: Enables agents to invoke tools during execution
- **Auto-Registration**: Registers with Serving on startup, sends heartbeats
- **Agent Definition Cache**: Can cache agent definitions short-term for performance (does NOT own)

**Communication Pattern**:
- **Private/Internal**: Compute does not expose APIs to external clients
- **Outbound to Serving only**: Sends registration, heartbeats, results to Serving API
- **Receives tasks from Serving**: Serving routes execution requests to compute
- Does NOT communicate directly with Marketplace or other Compute instances

**Data Ownership**:
- ✅ OWNS: Execution logs, temporary execution state, LLM provider connections
- ❌ Does NOT own: Agent definitions (fetched from Marketplace via Serving, can cache short-term)
- ❌ Does NOT own: Process maps, sessions (those belong to Serving)

**Scaling Model**:
- Multiple compute instances can run simultaneously (compute-1, compute-2, ...)
- Each registers independently with Serving
- Serving aggregates capabilities and routes tasks
- Enables horizontal scaling of agent execution capacity

**Technology**: FastAPI backend, LLM client abstraction, tool execution framework, filesystem storage for logs

---

### Communication Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│                  External Clients                   │
│            (Users, UI, External Systems)            │
└────────────────────┬────────────────────────────────┘
                     │
                     │ REST API (Public)
                     ▼
          ┌──────────────────────┐
          │   Serving (8002)     │
          │  ✅ PUBLIC API       │
          │  • Communication     │
          │    Broker            │
          │  • Event Bus         │
          │  • WebSocket         │
          └──────┬─────────┬─────┘
                 │         │
    Serving API  │         │  Serving API
    (Internal)   │         │  (Internal)
                 ▼         ▼
        ┌────────────┐  ┌────────────┐
        │ Marketplace│  │  Compute   │
        │   (8001)   │  │ (8003+)    │
        │ ❌ PRIVATE │  │ ❌ PRIVATE │
        │            │  │            │
        │ OWNS:      │  │ EXECUTES:  │
        │ • Agents   │  │ • Agents   │
        │ • Tools    │  │ • LLM calls│
        │ • Users    │  │ • Tools    │
        └────────────┘  └────────────┘
             │                 │
             │                 │
             └─────────────────┘
               No Direct Communication
               (All via Serving)
```

**Key Principles**:
1. **Single Public API**: Only Serving exposes REST API to external clients
2. **Serving as Broker**: All inter-component communication flows through Serving
3. **Private Components**: Marketplace and Compute are internal-only, not directly accessible
4. **Event-Driven**: Real-time updates via WebSocket and event bus, not polling
5. **Agent Definition Authority**: Marketplace is the ONLY source of truth for agent definitions
6. **Caching Allowed**: Compute can cache agent definitions for performance, but Marketplace owns them

---

## Core Concepts

### 1. Agents

**Definition**: An AI agent is a specialized unit of intelligence designed to perform specific types of work.

**Types**:

#### Coordinating Agents
Manage the overall process and facilitate collaboration:
- **Process Mapper**: Analyzes business goals and creates initial activity structures ✅ (process-mapper-v1)
- **Agent Selector**: Recommends which specialized agents should handle each activity ✅ (agent-selector-v1)
- **Activity Facilitator**: Conducts conversations with agents, detects blockers, proposes next steps ✅ (activity-facilitator-v1)
- **Consistency Manager**: Reviews outputs for contradictions and initiates reconciliation (planned)
- **Progress Reporter**: Provides intelligent progress analysis beyond simple metrics (planned)
- **Result Synthesizer**: Aggregates outputs into final deliverables and assesses goal achievement (agent-result-synthesizer-v1)

#### Specialized Agents
Perform specific work (examples):
- Content Writer Agent
- Data Analyst Agent
- Code Generator Agent
- Research Agent
- Quality Assurance Agent

**Agent Characteristics**:
- Have defined capabilities (e.g., "data_analysis", "content_generation")
- Scoped to organizations (visibility controlled by org hierarchy)
- Can require specific tools to execute
- Executed by compute engines with LLM integration

### 2. Process Maps

**Definition**: A dynamic, versioned structure representing the activities, dependencies, and state of work toward a business goal.

**Purpose**:
- Provide structure to emergent workflows
- Track what work is planned, in-progress, and complete
- Visualize dependencies between activities
- Maintain history of process evolution

**Key Properties**:
- **Dynamic**: Can be restructured during execution (activities added, dependencies changed)
- **Versioned**: Each structural change increments version with reasoning
- **Activity-Based**: Work organized into discrete activities with status tracking
- **Conversation-Aware**: Records exchanges between facilitators and agents

**Activity States**:
- `proposed`: Identified as potential next step
- `ready`: Dependencies met, can be executed
- `in_progress`: Currently being facilitated or executed
- `blocked`: Waiting on external dependency
- `completed`: Successfully finished
- `failed`: Execution failed
- `skipped`: No longer needed
- `revisit`: Needs rework due to contradiction

### 3. Facilitated Sessions

**Definition**: A goal-driven execution context where coordinating agents manage the lifecycle from business goal to completion.

**Lifecycle**:
1. **Initiation**: User submits business goal
2. **Mapping**: Process Mapper creates initial structure
3. **Facilitation**: Activity Facilitator manages execution through conversations
4. **Adaptation**: Process map evolves based on blockers and findings
5. **Synthesis**: Result Synthesizer creates final deliverable
6. **Completion**: Session marked as goal achieved or needs more work

**Session Modes**:
- **Facilitated**: Full emergent coordination (target vision)
- **Pipeline**: Predetermined sequence (currently working)
- **Simple Task**: Single agent execution

### 4. Virtual Compute Pool

**Definition**: Multiple compute engine instances that register with the serving component to create a distributed execution environment.

**Purpose**:
- Scale agent execution horizontally
- Isolate workloads across infrastructure
- Enable redundancy and fault tolerance
- Support diverse environments (cloud, on-premise, hybrid)

**Characteristics**:
- Compute instances auto-register on startup
- Serving aggregates capabilities across all instances
- Tasks routed to appropriate instance based on capabilities
- Health monitoring with automatic deregistration of failed instances

### 5. Organization Hierarchy

**Definition**: A multi-level structure that controls visibility and access to agents, tools, and resources.

**Purpose**:
- Scope agent discovery to relevant organizational context
- Control who can see and use which agents
- Support multi-tenant deployments
- Enable teams to create private agents

**Hierarchy Rules**:
- Up to 5 levels deep
- Admins see their org + all descendants
- Users see only their org
- Global org (`<global>`) visible to all
- Creating sub-org automatically grants Admin role to creator

---

## Functional Requirements

### FR-1: Agent Discovery and Registry

**Requirement**: Users must be able to discover agents based on capabilities and organizational scope.

**Rationale**: Coordinating agents need to find appropriate specialized agents to execute work. Users need to understand what agents are available.

**Capabilities**:
- Search agents by capability (e.g., "data_analysis")
- Filter by organization scope (hierarchical visibility)
- View agent metadata (name, description, capabilities, requirements)
- Browse agents through web UI
- Register new agents with approval workflow
- Generate A2A (Agent-to-Agent) protocol cards

**Success Criteria**:
- Agent Selector can query marketplace and receive ranked recommendations
- Users can browse available agents in their scope
- New agents submitted for approval appear in parent org admin dashboard
- A2A cards downloadable for interoperability

**Current Status**: ✅ **Fully Implemented** (Marketplace v0.1.4)

---

### FR-2: Agent Execution

**Requirement**: System must execute agents with appropriate LLM integration and return results.

**Rationale**: Agents require LLM calls to perform reasoning and generate outputs.

**Capabilities**:
- Execute agents with context (business goal, activity details, prior results)
- Integrate with multiple LLM providers (OpenAI, Anthropic, Mock)
- Support tool invocation during agent execution
- Handle execution errors gracefully with fallbacks
- Track token usage and costs

**Success Criteria**:
- Single agent task submitted and executed successfully
- Agent receives proper context and returns structured output
- LLM provider failures fallback appropriately
- Execution metrics recorded

**Current Status**: ✅ **Fully Implemented**

---

### FR-3: Process Map Creation

**Requirement**: Given a business goal, system must create an initial process map with activities and dependencies.

**Rationale**: Emergent workflows need starting structure. Process Mapper agent analyzes goals and proposes initial breakdown.

**Capabilities**:
- Analyze business goal in natural language
- Identify required capabilities and activities
- Establish initial dependencies between activities
- Assign preliminary agents to activities (via Agent Selector)
- Store process map with version 1

**Success Criteria**:
- Business goal submitted, initial map returned
- Activities have clear descriptions and capability requirements
- Dependencies reflect logical sequence
- Map stored and retrievable

**Current Status**: ✅ **Implemented** (Backend complete, frontend partial)

---

### FR-4: Activity Facilitation (Conversation-Driven)

**Requirement**: Activity Facilitator must conduct multi-turn conversations with participant agents to understand needs, detect blockers, and determine completion.

**Rationale**: Static task assignment doesn't account for dynamic needs. Conversations enable agents to request what they need and report issues.

**Capabilities**:
- Initiate facilitation conversation for an activity
- Ask agent what it needs to proceed
- Receive agent responses and parse requirements
- Detect blockers (missing data, access, dependencies)
- Confirm with agent when activity is complete
- Record conversation exchanges to process map

**Success Criteria**:
- Multi-turn exchange recorded (3+ back-and-forth messages)
- Blocker detected when agent reports missing dependency
- Activity marked complete only when agent confirms
- Conversation history stored in process map

**Current Status**: 🔨 **Partially Implemented** (Week 1 tests passing, but not integrated into full workflow)

**Planned Completion**: Tracked in [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md)

---

### FR-5: Dynamic Activity Creation

**Requirement**: When blockers are detected, system must create new prerequisite activities and update dependencies.

**Rationale**: Rigid workflows fail when unforeseen dependencies emerge. System must adapt by creating resolution activities.

**Capabilities**:
- Detect blocker during facilitation (e.g., "I need database access")
- Generate new activity to resolve blocker (e.g., "Obtain database access")
- Insert new activity before blocked activity in process map
- Update dependency graph (blocked activity now depends on new activity)
- Increment process map version with reasoning

**Success Criteria**:
- Blocker reported, new activity created automatically
- Original activity marked as dependent on new activity
- Process map version incremented (e.g., v1 → v2)
- Evolution reasoning captured

**Current Status**: 🔨 **Partially Implemented** (Week 2 tests passing, not integrated)

**Planned Completion**: Tracked in [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md)

---

### FR-6: Consistency Detection and Reconciliation

**Requirement**: System must detect contradictory outputs across activities and create reconciliation activities.

**Rationale**: Multiple agents working independently may produce inconsistent results. Quality depends on detecting and resolving contradictions.

**Capabilities**:
- After activity completion, invoke Consistency Manager
- Compare outputs across all completed activities
- Detect contradictions (e.g., Activity A says "65% retention", Activity B says "70% retention")
- Mark contradicting activities for revisit
- Create reconciliation activity to resolve discrepancy
- Update process map with new activity and dependencies

**Success Criteria**:
- Contradiction detected across outputs
- Both activities marked with "revisit" status
- Reconciliation activity created and assigned
- Reconciliation output resolves contradiction

**Current Status**: 🔨 **Partially Implemented** (Week 3 tests passing, not integrated)

**Planned Completion**: Tracked in [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md)

---

### FR-7: Process Map Evolution

**Requirement**: Process maps must restructure based on triggers (blockers, contradictions, findings) with version tracking.

**Rationale**: Static structures don't reflect reality. Process evolution must be tracked for auditability and understanding.

**Capabilities**:
- Detect evolution triggers (blocker, contradiction, replanning)
- Restructure activities and dependencies
- Increment version number
- Record evolution reasoning and timestamp
- Maintain complete version history

**Success Criteria**:
- Map evolves from v1 → v2 → v3 with clear triggers
- Each version has reasoning (e.g., "Added resolution activity for blocker")
- History browsable through API and UI
- Audit trail complete

**Current Status**: 🔨 **Partially Implemented** (Week 4 tests passing, not integrated)

**Planned Completion**: Tracked in [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md)

---

### FR-8: Result Synthesis and Goal Achievement

**Requirement**: System must aggregate outputs from all activities, create final deliverable, and determine if business goal achieved.

**Rationale**: Emergent workflows don't have predetermined endpoints. System must assess when collective work satisfies the original goal.

**Capabilities**:
- Collect outputs from all completed activities
- Invoke Result Synthesizer agent to create unified deliverable
- Generate executive summary, key findings, recommendations
- Assess goal alignment, completeness percentage, gaps
- Determine goal achievement (alignment=high, completeness≥80%, no gaps)
- Mark session status (GOAL_ACHIEVED, NEEDS_MORE_WORK, COMPLETED)

**Success Criteria**:
- Final deliverable structured with title, summary, findings, recommendations
- Goal achievement calculated correctly
- Gaps identified when goal not met
- Session marked with appropriate status

**Current Status**: 🔨 **Partially Implemented** (Week 5 tests passing, not integrated)

**Planned Completion**: Tracked in [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md)

---

### FR-9: Compute Instance Registration

**Requirement**: Compute engines must register with serving on startup and maintain health status.

**Rationale**: Distributed execution requires serving to know available compute resources and route tasks appropriately.

**Capabilities**:
- Compute auto-registers on startup with unique instance ID
- Reports capabilities (agents and tools available)
- Sends heartbeat at regular intervals (default 30s)
- Serving marks instance as degraded/offline if heartbeats stop
- Instance can deregister gracefully on shutdown
- Manual cleanup available for stale registrations

**Success Criteria**:
- Compute starts and appears in serving registry within 5 seconds
- Heartbeat maintains "healthy" status
- Serving detects when compute stops responding (within 90s)
- Multiple computes can register simultaneously

**Current Status**: ✅ **Implemented** (Manual cleanup script required for stale entries)

**Known Issue**: No automatic TTL expiration or instance ID stability across restarts. Tracked in [docs/E2E_GAPS_SUMMARY.md](docs/E2E_GAPS_SUMMARY.md).

---

### FR-10: Task Routing

**Requirement**: Serving must route task execution requests to appropriate compute instance based on capabilities.

**Rationale**: Virtual compute pool only useful if tasks intelligently routed to instances that can execute them.

**Capabilities**:
- Accept task submission with required capability
- Query compute registry for instances with that capability
- Select instance (round-robin or least-loaded strategy)
- Forward task to selected compute instance
- Return result to caller
- Handle compute unavailability with fallback

**Success Criteria**:
- Task requiring "content_generation" routed to compute with content-writer agent
- Multiple computes with same capability used in rotation
- Task fails gracefully if no capable compute available
- Execution result returned to caller

**Current Status**: ✅ **Implemented** (Basic routing working)

---

### FR-11: Marketplace Proxy

**Requirement**: Serving must connect to one or more marketplaces and proxy agent discovery requests.

**Rationale**: Enables serving to query agents on behalf of coordinating agents without direct marketplace coupling.

**Capabilities**:
- Register multiple marketplace connections
- Query all connected marketplaces for agent search
- Aggregate and deduplicate results
- Cache results for performance (configurable TTL)
- Health check marketplace connections
- Prioritize marketplaces based on availability

**Success Criteria**:
- Multiple marketplaces registered via API
- Agent search returns combined results from all marketplaces
- Duplicate agents deduplicated correctly
- Cache improves response time on repeated queries

**Current Status**: ✅ **Implemented** (Core functionality complete)

---

### FR-12: Real-Time Observability

**Requirement**: Users must see real-time updates of process execution through web UI.

**Rationale**: Emergent processes require visibility into what's happening. Users need to understand activity status, blockers, and progress.

**Capabilities**:
- Event-driven architecture with WebSocket connections
- Activity state changes broadcast immediately (proposed → ready → in-progress → completed)
- Conversation exchanges displayed as they occur
- Process map evolution visualized
- Resource utilization across compute instances
- Comprehensive event log with filtering

**Success Criteria**:
- UI updates within 500ms of activity state change
- Conversation exchanges appear in real-time
- Multiple users see same updates simultaneously
- Events persisted for historical review

**Current Status**: ✅ **Implemented** (WebSocket infrastructure complete, UI partially integrated)

---

### FR-13: Organization-Based Access Control

**Requirement**: Agents and tools must be scoped to organizations with hierarchical visibility.

**Rationale**: Multi-tenant platform requires isolation. Teams need private agents. Admins need oversight across sub-organizations.

**Capabilities**:
- Users belong to organizations with roles (Admin or User)
- Agents scoped to organizations
- Hierarchical visibility rules:
  - Admins see their org + all descendants
  - Users see only their org
  - Global org visible to all
- Creating sub-org grants creator Admin role automatically
- Discovery automatically filters by scope

**Success Criteria**:
- User in "TeamA" sees only TeamA agents
- Admin of "TeamA" sees TeamA + TeamA-SubProject agents
- Global agents visible to all users
- User creates sub-org and becomes Admin automatically

**Current Status**: ✅ **Fully Implemented and Tested** (Marketplace v0.1.4)
- Agent registration, retrieval, update, delete all working
- Filtering by capabilities, agent_type, tags, organization_id verified
- Hierarchical org access confirmed (child orgs see parent agents)
- Agent versioning supported (multiple versions coexist)
- Status tracking functional (active/inactive)

---

### FR-14: Pipeline Execution (Deterministic Mode)

**Requirement**: System must support predetermined pipeline execution for known workflows.

**Rationale**: Not all workflows require emergence. Some processes have well-defined sequences that shouldn't change.

**Capabilities**:
- Define pipeline with fixed steps and dependencies
- Execute steps in order with dependency checking
- Aggregate results from all steps
- Support branching (conditional execution based on results)
- Provide pipeline execution API endpoint

**Success Criteria**:
- Pipeline with 5 steps executes in correct order
- Step 3 waits for Steps 1 and 2 to complete
- Results from all steps aggregated in final output
- Error in Step 2 fails dependent steps appropriately

**Current Status**: ✅ **Implemented** (Production-ready)

**Note**: This is the "traditional orchestration" mode vs emergent facilitation.

---

### FR-15: User Management

**Requirement**: Administrators must be able to create and manage users within their organizational scope.

**Rationale**: Platform requires authentication and user-scoped operations.

**Capabilities**:
- Create users with username/password (Admins only)
- Assign users to organizations with roles
- Users can view members of their organization
- Session-based authentication with login/logout
- Change password functionality
- Users can create sub-organizations (become Admin of new org)

**Success Criteria**:
- Admin creates user in their org
- User logs in successfully
- User sees only their org's members
- User creates sub-org and gains Admin role

**Current Status**: ✅ **Fully Implemented** (Marketplace)

**Known Limitation**: Authentication only implemented in Marketplace. Serving and Compute do not have authentication. Planned for future release.

---

## Non-Functional Requirements

### NFR-1: Performance

**Requirement**: System must respond to user interactions within acceptable timeframes.

**Targets**:
- Agent discovery search: < 500ms (cached), < 2s (uncached)
- Single task execution: Depends on LLM (typically 2-10s)
- Process map creation: < 5s for typical business goal
- UI event updates: < 500ms from state change
- Heartbeat processing: < 100ms

**Rationale**: Users expect responsive interfaces. Long delays reduce confidence in system.

**Current Status**: Performance targets met in testing. No formal benchmarks established yet.

---

### NFR-2: Scalability

**Requirement**: System must scale horizontally to support increased load.

**Capabilities**:
- Multiple compute instances can be added without limit
- Serving can handle N concurrent sessions (tested with 10)
- Marketplace handles thousands of agents (tested with dozens)
- Database queries optimized with indexes

**Targets**:
- Support 100+ concurrent sessions
- Support 1000+ agents in marketplace
- Support 10+ compute instances per serving

**Rationale**: Platform must grow with organizational needs without architectural changes.

**Current Status**: Architecture supports scale. Load testing not yet performed.

**Known Limitation**: Current SQLite storage will need migration to PostgreSQL for production scale. See [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md).

---

### NFR-3: Reliability

**Requirement**: System must gracefully handle failures and maintain data integrity.

**Capabilities**:
- LLM provider failures fall back to alternate providers or mock
- Compute instance failures detected within 90s (heartbeat timeout)
- Failed tasks can be retried
- Data persisted before acknowledgment
- Transaction boundaries for data consistency

**Targets**:
- Zero data loss on graceful shutdown
- Compute failure detected within 90s
- LLM provider failover within 5s
- Session state recoverable after serving restart

**Rationale**: Users rely on system for critical work. Data loss or silent failures unacceptable.

**Current Status**: Basic error handling implemented. No formal disaster recovery plan.

---

### NFR-4: Observability

**Requirement**: System must provide comprehensive logging and monitoring.

**Capabilities**:
- Structured logging to files with rotation
- Log levels configurable per component
- Metrics API for resource utilization
- Health check endpoints on all services
- Event history persisted for audit trail
- Real-time event streaming to UI

**Rationale**: Troubleshooting and optimization require visibility into system behavior.

**Current Status**: ✅ Implemented across all components

---

### NFR-5: Maintainability

**Requirement**: System must be understandable and modifiable by future contributors.

**Capabilities**:
- Clear component boundaries with defined APIs
- Consistent code structure across components (services, API, models)
- Comprehensive documentation (architecture, API specs, guides)
- Type hints throughout Python codebase
- Automated tests for critical functionality
- Version tracking in VERSION file

**Rationale**: Long-term viability requires new developers to understand and modify system.

**Current Status**: ✅ Architecture well-documented. Test coverage variable by component.

---

### NFR-6: Deployability

**Requirement**: System must be easy to deploy in development and production environments.

**Capabilities**:
- Docker Compose for complete stack deployment
- Individual component startup scripts for development
- Environment variable configuration (no hardcoded values)
- Health checks for readiness verification
- Graceful shutdown handling
- Port conflict detection and resolution

**Rationale**: Difficult deployments slow development and increase production risk.

**Current Status**: ✅ Development deployment excellent. Production deployment not fully defined.

---

### NFR-7: Security (Future)

**Requirement**: System must protect against unauthorized access and data exposure.

**Capabilities Required**:
- Authentication on serving and compute components
- API key management for LLM providers
- Encrypted communication between components (TLS)
- Input validation and sanitization
- SQL injection prevention
- Rate limiting on public endpoints

**Targets**:
- All API endpoints require authentication
- Secrets stored securely (environment variables, not code)
- Component-to-component communication encrypted
- Audit trail for all actions

**Rationale**: Production deployment requires security. Multi-tenant platform requires isolation.

**Current Status**: ⚠️ **Partial** - Marketplace has authentication. Serving and Compute do not. No TLS. Not production-secure.

**Planned**: Tracked in technical backlog.

---

### NFR-8: Standards Compliance

**Requirement**: System should adhere to industry standards for interoperability.

**Standards**:
- **A2A Protocol**: Agent-to-Agent communication protocol for agent cards
- **OpenAPI 3.0**: REST API documentation format
- **WebSocket (RFC 6455)**: Real-time bidirectional communication
- **JSON**: Data exchange format
- **Semantic Versioning**: Version numbering (MAJOR.MINOR.PATCH)

**Rationale**: Standards enable integration with other systems and tools.

**Current Status**: ✅ A2A cards implemented. OpenAPI docs auto-generated. WebSocket implemented.

---

## User Roles and Permissions

### Role: Platform Admin (Future)

**Capabilities**:
- Manage all organizations
- View all agents, tools, sessions
- Configure system settings
- Access all logs and metrics

**Current Status**: Not implemented. No platform-wide admin role exists.

---

### Role: Organization Admin

**Scope**: Single organization + all descendants

**Capabilities**:
- Create/edit/delete users in their organization
- Approve agents submitted to their organization
- Create sub-organizations
- View all agents in their org + descendants
- View members across all descendant orgs
- Manage organization settings

**Current Status**: ✅ Implemented in Marketplace

---

### Role: Organization User

**Scope**: Single organization only

**Capabilities**:
- View agents in their organization
- View members of their organization
- Submit agents for approval
- Create sub-organizations (become Admin of new org)
- Create and execute sessions using accessible agents

**Current Status**: ✅ Implemented in Marketplace

---

### Role: Anonymous (Future)

**Capabilities**:
- View public documentation
- View global agents (read-only)

**Current Status**: Not implemented. No anonymous access.

---

## Integration Points

### INT-1: LLM Providers

**Purpose**: Execute agents with large language model reasoning

**Supported Providers**:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude models)
- Mock (deterministic testing)

**Integration Method**:
- API key authentication
- REST API calls
- Fallback chain (primary → secondary → mock)

**Configuration**: Environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)

**Reference**: [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) Section TD-8

---

### INT-2: Storage Backends

**Purpose**: Persist agents, tools, sessions, process maps

**Current Implementations**:
- Filesystem storage (JSON files)
- SQLite (sessions, process maps in serving)

**Planned**:
- PostgreSQL (production)
- S3 (cloud storage)
- DynamoDB (cloud NoSQL)

**Reference**: [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) Section TD-5

---

### INT-3: External Marketplaces (Future)

**Purpose**: Discover agents from third-party marketplaces

**Integration Method**:
- Marketplace registration API in serving
- REST API proxy for agent search
- A2A card format for agent metadata

**Current Status**: Architecture supports but no external marketplaces integrated yet

---

### INT-4: Monitoring Systems (Future)

**Purpose**: Export metrics to external monitoring platforms

**Planned Integrations**:
- Prometheus (metrics export)
- Grafana (dashboards)
- ELK Stack (log aggregation)

**Current Status**: Health check endpoints exist but no integrations

---

## Future Vision

### Vision: Full Emergent Coordination

**When**: Tracked in [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md)

**Description**: All 6 coordinating agents working seamlessly to create truly self-organizing workflows. Business goals submitted evolve into complete solutions through agent conversations, blocker detection, dynamic activity creation, consistency checking, and result synthesis.

**Key Milestones**:
- Week 6 integration test passing (conversation → blocker → adaptation → synthesis → completion)
- Frontend UI for facilitated sessions complete
- Real-time process map evolution visualization
- Production deployment with authentication

---

### Vision: Multi-Organization Deployment

**When**: Post v1.0

**Description**: Platform deployed as multi-tenant SaaS where organizations operate independently with isolated data and agents.

**Requirements**:
- Complete authentication and authorization
- Data isolation per organization
- Billing and usage tracking
- Organization-level configuration
- Admin portal for platform operators

---

### Vision: Agent Marketplace Ecosystem

**When**: Post v1.0

**Description**: Third-party developers publish agents to marketplace. Organizations discover and use agents from multiple sources.

**Requirements**:
- Agent submission portal for developers
- Rating and review system
- Usage analytics
- Monetization support (paid agents)
- Security vetting process

---

### Vision: Advanced Observability

**When**: Post v1.0

**Description**: Comprehensive monitoring, analytics, and optimization features.

**Requirements**:
- Process analytics (common patterns, bottlenecks)
- Agent performance metrics
- Cost optimization recommendations
- Predictive failure detection
- Custom dashboard builder

---

## Document Maintenance

This document is the **living source of truth** and should be updated with each release:

1. When requirements change: Update relevant section, link to TECHNICAL_DECISIONS.md updates
2. When features complete: Update "Current Status" from 🔨 to ✅
3. When new requirements added: Follow FR-N numbering, link to technical decisions
4. When features deprecated: Mark as such with reasoning

**Review Cadence**: Before each release (currently every 2-4 weeks)

**Ownership**: Product owner approves changes. Developers and AI agents propose updates.

---

## Related Documents

- [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md) - Technical implementation decisions
- [docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md](docs/EMERGENT_WORKFLOW_IMPLEMENTATION.md) - Week-by-week implementation plan
- [docs/END_TO_END_AUDIT.md](docs/END_TO_END_AUDIT.md) - Process-by-process audit
- [docs/E2E_GAPS_SUMMARY.md](docs/E2E_GAPS_SUMMARY.md) - Quick reference of missing features
- [README.md](README.md) - Quick start and user-facing documentation
