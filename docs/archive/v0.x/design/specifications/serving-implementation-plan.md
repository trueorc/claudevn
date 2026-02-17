# Serving Component - Implementation Plan

**Version:** 0.2.0  
**Status:** DRAFT - For Review  
**Last Updated:** 2025-11-23

---

## Executive Summary

The Serving Component is the central orchestration hub of ClaudeVN that:
- **Registers** multiple compute engines to create a virtual compute resource pool
- **Proxies** A2A protocol messages between compute instances and marketplace
- **Manages** session lifecycle and execution coordination
- **Provides** a UI for monitoring registrations, sessions, and marketplace connections

This plan builds on the existing foundation (session management, storage APIs) and follows the successful patterns established by the Marketplace implementation.

---

## Current State Assessment

### ✅ What's Already Built

1. **Session Management** (`serving/api/sessions/`)
   - Session CRUD operations
   - Session context model with status tracking
   - Task results and data references
   - Execution plan storage
   - In-memory session manager

2. **Storage API** (`serving/api/storage_api/`)
   - Blob storage endpoints (upload/download)
   - Session-scoped storage
   - Metadata management
   - File management

3. **Core Infrastructure**
   - FastAPI setup
   - Requirements defined
   - Storage backend abstraction (filesystem)
   - Basic broker structure

### ❌ What's Missing (To Be Implemented)

1. **Compute Registration System**
   - Registration API endpoints
   - Compute instance registry
   - Health checking and heartbeat
   - Capability aggregation

2. **Marketplace Integration**
   - Marketplace connection management
   - Agent discovery proxying
   - Access control synchronization
   - Multi-marketplace support

3. **A2A Protocol Support**
   - A2A message routing
   - Agent Card serving
   - Task submission and status
   - Cross-instance communication

4. **Frontend UI**
   - Registration dashboard
   - Session monitoring
   - Marketplace connections view
   - System health overview

5. **Main Application**
   - FastAPI app with all routers
   - Startup/shutdown lifecycle
   - Configuration management
   - Logging setup

---

## Architecture Overview

### Component Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND UI                            │
│  • Registration Dashboard  • Session Monitor                │
│  • Marketplace Connections • System Health                  │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      API LAYER                              │
│  • Compute Registration  • Session Management               │
│  • Marketplace Proxy     • A2A Protocol                     │
│  • Storage API           • Health/Stats                     │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   BUSINESS LOGIC                            │
│  • Registry Service      • Routing Service                  │
│  • Session Coordinator   • Marketplace Service              │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   STORAGE LAYER                             │
│  • Registry Backend      • Session Database                 │
│  • Blob Storage          • Configuration                    │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: Compute Registration

```
Compute Instance
    │
    │ POST /api/v1/compute/register
    │ { instance_id, capabilities, endpoint, health_endpoint }
    ▼
┌─────────────────────┐
│  Registration API   │
│                     │
│  - Validate request │
│  - Assign ID        │
│  - Store metadata   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Registry Service   │
│                     │
│  - Add to registry  │
│  - Start heartbeat  │
│  - Aggregate caps   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Registry Backend   │
│                     │
│  - Store instance   │
│  - Update index     │
└─────────────────────┘
```

### Data Flow: A2A Message Routing

```
Compute Instance A          Serving Component          Compute Instance B
    │                              │                           │
    │ POST /a2a/tasks              │                           │
    ├─────────────────────────────>│                           │
    │                              │                           │
    │                              │ 1. Validate & Route       │
    │                              │ 2. Find target instance   │
    │                              │                           │
    │                              │ POST /a2a/tasks           │
    │                              ├──────────────────────────>│
    │                              │                           │
    │                              │ 3. Store in session       │
    │                              │                           │
    │                              │<──────────────────────────┤
    │                              │ Task accepted (202)       │
    │<─────────────────────────────┤                           │
    │ Task queued                  │                           │
```

---

## Implementation Phases

### Phase 1: Compute Registration System (Week 1)

**Goal:** Enable compute instances to register with the serving component and create a virtual compute pool.

#### 1.1 Data Models
- [ ] `ComputeInstance` model (id, endpoint, capabilities, status, metadata)
- [ ] `InstanceStatus` enum (online, offline, degraded, error)
- [ ] `InstanceCapabilities` model (agents, tools, resources)
- [ ] `RegistrationRequest/Response` models

#### 1.2 Registry Service
- [ ] `ComputeRegistry` class (in-memory + persistent storage)
- [ ] `add_instance()` - Register new compute instance
- [ ] `remove_instance()` - Deregister instance
- [ ] `get_instance()` - Get instance by ID
- [ ] `list_instances()` - List all registered instances
- [ ] `get_by_capability()` - Find instances with specific capabilities
- [ ] `update_status()` - Update instance health status
- [ ] `get_aggregated_capabilities()` - Get combined capabilities

#### 1.3 Registry API Endpoints
```
POST   /api/v1/compute/register         Register compute instance
DELETE /api/v1/compute/{instance_id}    Deregister instance
GET    /api/v1/compute                  List registered instances
GET    /api/v1/compute/{instance_id}    Get instance details
PATCH  /api/v1/compute/{instance_id}    Update instance metadata
GET    /api/v1/compute/capabilities     Get aggregated capabilities
POST   /api/v1/compute/{instance_id}/health  Health check callback
```

#### 1.4 Health Monitoring
- [ ] Background task for heartbeat checking
- [ ] Configurable health check interval (default: 30s)
- [ ] Auto-deregistration for unhealthy instances (after N failures)
- [ ] Health status webhook support

#### 1.5 Storage Backend
- [ ] Extend filesystem backend for registry
- [ ] `registry/` directory structure
- [ ] Instance metadata files
- [ ] Capability index

**Deliverables:**
- Compute instances can register/deregister
- Health monitoring running
- Registry persisted to storage
- API endpoints functional
- Unit tests for registry service

**Success Criteria:**
- Multiple compute instances can register simultaneously
- Capabilities are correctly aggregated
- Failed instances are detected and marked offline
- Registry survives serving component restart

---

### Phase 2: Marketplace Integration (Week 2)

**Goal:** Connect to marketplace(s) and proxy agent discovery requests.

#### 2.1 Data Models
- [ ] `MarketplaceConnection` model (id, url, name, status)
- [ ] `MarketplaceStatus` enum (connected, disconnected, error)
- [ ] `ConnectionRequest/Response` models
- [ ] `ProxyCache` model for agent metadata

#### 2.2 Marketplace Service
- [ ] `MarketplaceManager` class
- [ ] `add_marketplace()` - Register marketplace connection
- [ ] `remove_marketplace()` - Remove marketplace
- [ ] `list_marketplaces()` - List all marketplaces
- [ ] `test_connection()` - Verify marketplace connectivity
- [ ] `proxy_agent_search()` - Forward search to marketplace
- [ ] `proxy_agent_details()` - Forward agent details request
- [ ] `sync_access_control()` - Sync permissions
- [ ] Cache management for agent metadata

#### 2.3 Marketplace API Endpoints
```
POST   /api/v1/marketplaces/connect     Connect to marketplace
DELETE /api/v1/marketplaces/{id}        Disconnect marketplace
GET    /api/v1/marketplaces             List marketplaces
GET    /api/v1/marketplaces/{id}        Get marketplace details
GET    /api/v1/marketplaces/{id}/agents List agents from marketplace
POST   /api/v1/marketplaces/{id}/search Search agents in marketplace
```

#### 2.4 Proxy Endpoints (A2A Compatible)
```
GET    /a2a/agents                      List all available agents (from all sources)
GET    /a2a/agents/{id}                 Get agent card (proxied or local)
POST   /a2a/agents/search               Search across all marketplaces
```

#### 2.5 Multi-Marketplace Support
- [ ] Query multiple marketplaces in parallel
- [ ] Merge and deduplicate results
- [ ] Prioritize by marketplace (configurable)
- [ ] Handle marketplace failures gracefully
- [ ] Cache results with TTL

**Deliverables:**
- Connect to marketplace instances
- Proxy agent discovery requests
- Aggregate results from multiple marketplaces
- A2A endpoints functional
- Integration tests with marketplace

**Success Criteria:**
- Serving can connect to 1+ marketplaces
- Agent searches work across marketplaces
- Results are properly merged and cached
- Marketplace failures don't break serving

---

### Phase 3: A2A Protocol & Message Routing (Week 3)

**Goal:** Implement A2A protocol for inter-instance communication.

#### 3.1 A2A Models
- [ ] `A2ATask` model (id, agent_id, input, status, metadata)
- [ ] `A2ATaskStatus` enum (submitted, working, completed, failed, cancelled)
- [ ] `A2AMessage` model (from, to, type, payload)
- [ ] `A2ARoute` model (source, target, protocol)

#### 3.2 Routing Service
- [ ] `A2ARouter` class
- [ ] `route_task()` - Route task to appropriate compute instance
- [ ] `route_message()` - Route message between instances
- [ ] `get_route()` - Find route for agent/capability
- [ ] `broadcast()` - Send to all instances
- [ ] Message queue for async delivery
- [ ] Retry logic for failed deliveries

#### 3.3 A2A Protocol Endpoints
```
POST   /a2a/tasks                       Submit task to agent
GET    /a2a/tasks/{task_id}             Get task status
GET    /a2a/tasks/{task_id}/stream      SSE stream for task updates
PATCH  /a2a/tasks/{task_id}             Update task (cancel, provide input)
POST   /a2a/messages                    Send message between instances
```

#### 3.4 Session Integration
- [ ] Link A2A tasks to sessions
- [ ] Track task execution in session context
- [ ] Store task results in session
- [ ] Session-aware routing
- [ ] Cross-session data sharing

#### 3.5 WebSocket/SSE Support
- [ ] Server-Sent Events for task updates
- [ ] WebSocket connections for real-time updates
- [ ] Connection management
- [ ] Reconnection handling

**Deliverables:**
- A2A protocol endpoints working
- Tasks routed to correct compute instances
- Real-time task status updates
- Message routing between instances
- Integration with session management

**Success Criteria:**
- Task submitted to Instance A can invoke agent on Instance B
- Status updates flow back correctly
- Sessions track all A2A tasks
- SSE streaming works reliably

---

### Phase 4: Frontend UI (Week 4)

**Goal:** Build a React frontend for monitoring and management.

#### 4.1 UI Components (Following Marketplace Pattern)
- [ ] `Dashboard.jsx` - Main overview
- [ ] `ComputeRegistry.jsx` - Registered compute instances table
- [ ] `ComputeInstanceCard.jsx` - Instance details card
- [ ] `MarketplaceConnections.jsx` - Connected marketplaces
- [ ] `MarketplaceCard.jsx` - Marketplace details card
- [ ] `SessionMonitor.jsx` - Active/recent sessions
- [ ] `SessionDetail.jsx` - Session details and timeline
- [ ] `HealthStatus.jsx` - System health overview
- [ ] `CapabilityView.jsx` - Aggregated capabilities view

#### 4.2 Dashboard Features
- [ ] **Compute Panel:**
  - List of registered instances (online/offline)
  - Health status indicators
  - Capabilities summary
  - Last heartbeat time
  - Register new instance form

- [ ] **Marketplace Panel:**
  - Connected marketplaces
  - Connection status
  - Agent counts
  - Connect new marketplace form

- [ ] **Session Panel:**
  - Active sessions count
  - Recent sessions list
  - Session status breakdown
  - Quick session details

- [ ] **System Health:**
  - Overall status
  - API response time
  - Storage usage
  - Active connections

#### 4.3 Compute Registry View
- [ ] Table with columns: Instance ID, Status, Capabilities, Endpoint, Last Seen
- [ ] Filters: Status (all/online/offline), Capability
- [ ] Actions: View details, Test health, Deregister
- [ ] Real-time status updates
- [ ] Capability badges
- [ ] Health history chart

#### 4.4 Marketplace Connections View
- [ ] Cards for each marketplace
- [ ] Connection status indicator
- [ ] Test connection button
- [ ] View agents in marketplace
- [ ] Sync access control button
- [ ] Add new marketplace form

#### 4.5 Session Monitor View
- [ ] Sessions table with: ID, Status, Created, Updated, Goal
- [ ] Filter by status
- [ ] Search by ID or goal
- [ ] Session detail modal/page
- [ ] Execution plan visualization
- [ ] Task results timeline
- [ ] Data references list

#### 4.6 API Client (`api.js`)
```javascript
// Compute Registry
export const getComputeInstances = async () => {...}
export const getComputeInstance = async (instanceId) => {...}
export const registerComputeInstance = async (data) => {...}
export const deregisterComputeInstance = async (instanceId) => {...}
export const testComputeHealth = async (instanceId) => {...}

// Marketplaces
export const getMarketplaces = async () => {...}
export const connectMarketplace = async (data) => {...}
export const disconnectMarketplace = async (id) => {...}
export const testMarketplaceConnection = async (id) => {...}
export const getMarketplaceAgents = async (id) => {...}

// Sessions
export const getSessions = async (filters) => {...}
export const getSession = async (sessionId) => {...}
export const createSession = async (data) => {...}
export const deleteSession = async (sessionId) => {...}

// System
export const getSystemHealth = async () => {...}
export const getSystemStats = async () => {...}
```

#### 4.7 Build Integration
- [ ] Vite configuration
- [ ] Frontend build script
- [ ] Integration with FastAPI static serving
- [ ] Development mode (`npm run dev`)
- [ ] Production build (`npm run build`)

**Deliverables:**
- Complete React frontend
- All UI components functional
- Real-time updates working
- Responsive design
- Built and integrated with backend

**Success Criteria:**
- UI shows all registered compute instances
- Marketplace connections visible and manageable
- Session monitoring works in real-time
- Health status accurate and updated
- Production build served by FastAPI

---

### Phase 5: Main Application & Integration (Week 5)

**Goal:** Complete the main application and integrate all components.

#### 5.1 Main Application (`app.py`)
- [ ] FastAPI app initialization
- [ ] Lifespan events (startup/shutdown)
- [ ] Storage initialization
- [ ] Registry initialization
- [ ] Marketplace manager initialization
- [ ] Router inclusion (all API endpoints)
- [ ] CORS configuration
- [ ] Static file serving (frontend)
- [ ] Health check endpoint
- [ ] Root endpoint with service info

#### 5.2 Configuration Management
- [ ] `.env` support
- [ ] `config.py` for configuration management
- [ ] Environment variable validation
- [ ] Configuration documentation (`ENV_TEMPLATE.md`)
- [ ] Default values for all settings

#### 5.3 Logging System
- [ ] Structured logging setup
- [ ] Log levels per module
- [ ] File logging (`logs/serving.log`)
- [ ] Console logging (development)
- [ ] Request/response logging (optional)
- [ ] Performance metrics logging

#### 5.4 Startup Scripts
- [ ] `start.sh` - Start serving component
- [ ] `stop.sh` - Stop serving component
- [ ] Port checking and cleanup
- [ ] Dependency installation
- [ ] Frontend building
- [ ] Health check verification

#### 5.5 Integration Points
- [ ] **With Marketplace:**
  - Test connection to marketplace
  - Proxy agent discovery
  - Sync user/org permissions (future)

- [ ] **With Compute:**
  - Test registration workflow
  - Health monitoring
  - Task routing

- [ ] **Storage:**
  - Registry persistence
  - Session persistence
  - Blob storage

#### 5.6 Testing
- [ ] Unit tests for all services
- [ ] Integration tests for API endpoints
- [ ] End-to-end tests for workflows
- [ ] Load testing for registry
- [ ] Test data/fixtures

**Deliverables:**
- Complete working serving component
- All components integrated
- Startup/shutdown scripts working
- Configuration system complete
- Test suite passing

**Success Criteria:**
- `./serving/start.sh` launches fully functional serving component
- Frontend accessible at http://localhost:8002
- Marketplace connection works
- Compute registration works
- All API endpoints functional
- Tests passing

---

### Phase 6: Documentation & Polish (Week 6)

**Goal:** Complete documentation and polish the release.

#### 6.1 Documentation
- [ ] `serving/README.md` - Comprehensive guide
- [ ] `serving/QUICKSTART.md` - Quick start guide
- [ ] `serving/ENV_TEMPLATE.md` - Configuration reference
- [ ] API documentation (auto-generated from FastAPI)
- [ ] Architecture diagrams
- [ ] Deployment guide
- [ ] Troubleshooting guide

#### 6.2 Release Documentation
- [ ] `docs/releases/0.2.0/CHANGELOG.md`
- [ ] `docs/releases/0.2.0/RELEASE_NOTES.md`
- [ ] `docs/releases/0.2.0/SERVING_IMPLEMENTATION.md`
- [ ] Update main `README.md`
- [ ] Update `docs/README.md`
- [ ] Update version in `VERSION` file

#### 6.3 Examples & Demos
- [ ] Example compute registration script
- [ ] Example marketplace connection script
- [ ] Demo scenario: Register 3 compute instances
- [ ] Demo scenario: Multi-marketplace search
- [ ] Demo scenario: A2A task routing

#### 6.4 Polish
- [ ] Error message improvements
- [ ] Logging message clarity
- [ ] UI polish and styling
- [ ] Performance optimizations
- [ ] Code cleanup and refactoring
- [ ] Type hints completion
- [ ] Docstring improvements

#### 6.5 Integration Testing
- [ ] Test with real marketplace instance
- [ ] Test with multiple compute instances
- [ ] Test error scenarios
- [ ] Test recovery scenarios
- [ ] Performance testing
- [ ] Security review

**Deliverables:**
- Complete documentation
- Release notes and changelog
- Demo scenarios working
- Code polished and reviewed
- All tests passing

**Success Criteria:**
- New user can start serving component in 5 minutes
- Documentation is clear and comprehensive
- Demo scenarios run successfully
- No critical bugs
- Ready for release

---

## Technical Specifications

### API Endpoints Summary

```
# Compute Registry
POST   /api/v1/compute/register
DELETE /api/v1/compute/{instance_id}
GET    /api/v1/compute
GET    /api/v1/compute/{instance_id}
PATCH  /api/v1/compute/{instance_id}
GET    /api/v1/compute/capabilities
POST   /api/v1/compute/{instance_id}/health

# Marketplace Integration
POST   /api/v1/marketplaces/connect
DELETE /api/v1/marketplaces/{id}
GET    /api/v1/marketplaces
GET    /api/v1/marketplaces/{id}
GET    /api/v1/marketplaces/{id}/agents
POST   /api/v1/marketplaces/{id}/search

# A2A Protocol
GET    /a2a/agents
GET    /a2a/agents/{id}
POST   /a2a/agents/search
POST   /a2a/tasks
GET    /a2a/tasks/{task_id}
GET    /a2a/tasks/{task_id}/stream
PATCH  /a2a/tasks/{task_id}
POST   /a2a/messages

# Session Management (already exists)
POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{id}
DELETE /api/v1/sessions/{id}
PATCH  /api/v1/sessions/{id}/status
POST   /api/v1/sessions/{id}/task_results
POST   /api/v1/sessions/{id}/data_refs
PUT    /api/v1/sessions/{id}/execution_plan

# Storage API (already exists)
POST   /api/v1/storage/upload
GET    /api/v1/storage/download/{blob_id}
GET    /api/v1/storage/metadata/{blob_id}
DELETE /api/v1/storage/{blob_id}

# Health & Stats
GET    /api/v1/health
GET    /api/v1/stats
```

### Data Models

#### ComputeInstance
```python
class ComputeInstance(BaseModel):
    instance_id: str
    name: str
    endpoint: str
    health_endpoint: Optional[str]
    status: InstanceStatus
    capabilities: InstanceCapabilities
    metadata: Dict[str, Any]
    registered_at: datetime
    last_heartbeat: datetime
    version: str
```

#### MarketplaceConnection
```python
class MarketplaceConnection(BaseModel):
    connection_id: str
    name: str
    url: str
    status: MarketplaceStatus
    agent_count: int
    last_sync: datetime
    metadata: Dict[str, Any]
```

#### A2ATask
```python
class A2ATask(BaseModel):
    task_id: str
    agent_id: str
    session_id: Optional[str]
    input: Dict[str, Any]
    status: A2ATaskStatus
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
```

### Storage Structure

```
data/serving/
├── registry/
│   ├── compute/
│   │   ├── instance-{id}.json
│   │   └── index.json
│   └── marketplaces/
│       ├── marketplace-{id}.json
│       └── index.json
├── sessions/
│   └── session-{id}.json
├── tasks/
│   └── task-{id}.json
└── blobs/
    └── {blob-id}
```

### Configuration

```bash
# Serving Component Configuration

# Server
SERVING_HOST=0.0.0.0
SERVING_PORT=8002
API_VERSION=v1

# Storage
STORAGE_BACKEND=filesystem
STORAGE_PATH=./data/serving
BLOB_MAX_SIZE=104857600  # 100MB
BLOB_TTL=3600  # 1 hour

# Registry
HEALTH_CHECK_INTERVAL=30  # seconds
HEALTH_CHECK_TIMEOUT=5    # seconds
MAX_FAILED_CHECKS=3       # before marking offline
AUTO_DEREGISTER=false     # auto-remove failed instances

# Marketplace
MARKETPLACE_CACHE_TTL=300 # 5 minutes
MAX_MARKETPLACES=10

# A2A Protocol
A2A_TASK_TIMEOUT=300      # 5 minutes
A2A_MESSAGE_RETRY=3
SSE_KEEPALIVE=30          # seconds

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/serving.log

# CORS
CORS_ORIGINS=*
```

---

## Success Metrics

### Technical Metrics
- [ ] All API endpoints operational (100% coverage)
- [ ] Unit test coverage > 80%
- [ ] Integration tests passing
- [ ] API response time < 100ms (95th percentile)
- [ ] UI loads in < 2s
- [ ] Support 10+ compute instances
- [ ] Support 5+ marketplace connections
- [ ] Handle 100+ concurrent sessions

### Functional Metrics
- [ ] Compute registration works end-to-end
- [ ] Marketplace proxy works
- [ ] A2A tasks route correctly
- [ ] Health monitoring detects failures
- [ ] UI shows real-time updates
- [ ] Documentation is complete

### User Experience
- [ ] New user can start serving in < 5 minutes
- [ ] UI is intuitive and responsive
- [ ] Error messages are helpful
- [ ] Logs are clear and useful

---

## Risks & Mitigation

### Risk 1: Complex A2A Protocol Implementation
**Impact:** High  
**Probability:** Medium  
**Mitigation:**
- Start with simple task routing
- Implement SSE incrementally
- Test with mock compute instances
- Reference A2A specification closely

### Risk 2: Multi-Marketplace Coordination
**Impact:** Medium  
**Probability:** Medium  
**Mitigation:**
- Implement single marketplace first
- Add multi-marketplace support incrementally
- Use caching aggressively
- Handle failures gracefully

### Risk 3: Real-Time UI Updates
**Impact:** Low  
**Probability:** Low  
**Mitigation:**
- Use polling as fallback
- Implement SSE gradually
- Test with slow connections
- Provide manual refresh option

### Risk 4: Health Monitoring Reliability
**Impact:** High  
**Probability:** Low  
**Mitigation:**
- Configurable check intervals
- Multiple failure threshold
- Manual override option
- Detailed logging

---

## Dependencies

### Internal
- `marketplace` - Must be running for integration testing
- `shared` - Common types and utilities
- `compute` - For end-to-end testing (can use mocks initially)

### External
- FastAPI, Uvicorn
- SQLAlchemy (for future DB backend)
- aiofiles, httpx
- Redis (optional, for distributed setups)
- React, Vite (frontend)

### Development
- pytest, pytest-asyncio
- httpx (testing)
- pytest-cov (coverage)
- black, ruff (linting)

---

## Questions for Review

### Architecture Questions
1. **Storage Backend**: Continue with filesystem for Phase 1, or implement SQLite for registry?
   - *Recommendation*: Start with filesystem (matches marketplace), add SQLite in future version
   
2. **Health Monitoring**: Should we use active checks (serving → compute) or passive heartbeats (compute → serving)?
   - *Recommendation*: Passive heartbeats (simpler, more scalable)

3. **A2A Protocol**: Full A2A spec compliance or subset for MVP?
   - *Recommendation*: Subset for MVP (task submission, status, basic routing)

### Feature Scope Questions
4. **Multi-Marketplace Priority**: Which marketplace to query first when multiple are connected?
   - *Options*: 
     - User-configurable priority
     - Round-robin
     - Fastest response
   - *Recommendation*: User-configurable priority per marketplace

5. **Session Linking**: Should all A2A tasks be linked to sessions, or support standalone tasks?
   - *Recommendation*: Support both (sessions optional)

6. **UI Complexity**: How detailed should the session monitoring be in Phase 4?
   - *Recommendation*: Basic monitoring in Phase 4, detailed execution visualization in future version

### Technical Questions
7. **Real-Time Updates**: SSE, WebSocket, or polling?
   - *Recommendation*: SSE for task updates, polling for UI dashboards (simpler, good enough)

8. **Authentication**: Implement auth in Phase 1 or defer?
   - *Recommendation*: Defer to v0.3.0 (align with marketplace auth implementation)

9. **Database**: When should we migrate from filesystem to database?
   - *Recommendation*: Serving v0.3.0 or when registry has >100 instances (whichever first)

---

## Next Steps

### Immediate Actions (Before Starting Implementation)
1. **Review this plan** - Provide feedback on scope, architecture, phases
2. **Clarify questions** - Answer questions in section above
3. **Adjust timeline** - Confirm 6-week timeline or adjust
4. **Prioritize features** - Confirm must-haves vs. nice-to-haves
5. **Define success** - Agree on Phase 1 completion criteria

### Once Plan is Approved
1. **Phase 1 Kickoff** - Start with compute registration system
2. **Create feature branch** - `feature/serving-component-v0.2.0`
3. **Set up project board** - Track tasks and progress
4. **Daily standups** - Quick sync on progress and blockers

---

## Appendix

### A. Comparison with Marketplace Implementation

| Aspect | Marketplace | Serving |
|--------|-------------|---------|
| **Storage** | Filesystem → DynamoDB | Filesystem → SQLite → PostgreSQL |
| **Frontend** | React + Vite | React + Vite (same pattern) |
| **API Style** | RESTful FastAPI | RESTful FastAPI + A2A Protocol |
| **Auth** | User/Org/Scope | Defer to v0.3.0 |
| **Deployment** | Port 8001 | Port 8002 |
| **Complexity** | Medium | High (coordination logic) |

### B. A2A Protocol Subset for MVP

**Included:**
- Agent Card serving (GET /a2a/agents)
- Task submission (POST /a2a/tasks)
- Task status (GET /a2a/tasks/{id})
- Task updates via SSE (GET /a2a/tasks/{id}/stream)

**Deferred:**
- Full webhook support
- Complex task dependencies
- Bidirectional streaming
- Advanced authentication

### C. References

- [Platform Overview](../architecture/platform-overview.md)
- [Technical Specifications](./technical-specifications.md)
- [Agent Marketplace Orchestration Design](./agent-marketplace-orchestration-design.md)
- [Coordinating Agents Spec](./coordinating-agents-spec.md)
- [Marketplace Spec](./marketplace-spec.md)

---

**Document Status:** DRAFT - Ready for Review  
**Next Review Date:** TBD  
**Approval Required From:** Project Lead

