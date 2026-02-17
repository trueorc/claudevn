# ClaudeVN Marketplace Service

The Marketplace Service is the discovery and registry system for AI agents and tools in the ClaudeVN platform. It provides a centralized location where coordinating agents can find and select specialized agents based on their capabilities.

## 🆕 NEW: Organization-Scoped Discovery (v0.1.4)

The marketplace now includes organization-based access control for agents and tools!

### Latest Updates (v0.1.4)
- ✅ **Organization-Filtered Discovery**: Agents and tools are automatically filtered based on user's organization membership
- ✅ **Hierarchical Visibility**: Admins see resources from their org + all descendants; Users see only their org
- ✅ **Global Resources**: Resources in `<global>` org are visible to all authenticated users
- ✅ **Approval Workflow**: Submit agents for approval to parent organizations
- ✅ **Automatic Auth**: Frontend automatically includes authentication tokens in all requests

### Key Features
- **Hierarchical Organizations**: Up to 5 levels deep
- **Scope-Based Discovery**: Resources filtered by organization membership
- **Role-Based Access**: Admin and User roles
- **Session-Based Authentication**: Secure login/logout
- **Modern Web UI**: Complete management interface with scope selector
- **Agent/Tool Organization Scoping**: All resources tied to organizations

### Quick Access
- **Login**: http://localhost:8001
- **Default Credentials**: `admin` / `admin123` ⚠️ **Change immediately!**
- **Scope Selector**: User menu dropdown (top right)
- **Admin Dashboard**: Manage tab (admins only)

### Documentation
- 📖 [`SCOPE_SYSTEM.md`](SCOPE_SYSTEM.md) - Scope and permissions guide
- 👥 [`USER_ORG_SYSTEM.md`](USER_ORG_SYSTEM.md) - Complete system guide
- 📊 [`IMPLEMENTATION_SUMMARY.md`](IMPLEMENTATION_SUMMARY.md) - Implementation details
- 🎯 [`docs/ADMIN_DASHBOARD.md`](docs/ADMIN_DASHBOARD.md) - Admin dashboard guide

---

## Quick Start

**Prerequisites:**
- Python 3.9+
- pip

**Installation:**
```bash
cd marketplace
pip install -r requirements.txt
```

**Configuration:**
```bash
cp .env.example .env
# Edit .env with your settings
```

**Run:**
```bash
./start.sh
```

**Access:**
- Frontend UI: http://localhost:8001 (automatically built and served)
- API: http://localhost:8001/api/v1
- API Docs: http://localhost:8001/docs
- Health Check: http://localhost:8001/api/v1/health

---

## What It Does

The Marketplace Service enables:

**For Coordinating Agents:**
- Search for agents by capabilities
- Get ranked agent recommendations
- Query agent specifications
- Download A2A Agent Cards

**For System Administrators:**
- Register new agents and tools
- Manage access control
- Monitor marketplace statistics
- Configure storage backends

**For End Users:**
- Browse available agents
- View agent capabilities and performance
- Understand what agents can do
- See which agents work well together

---

## Architecture Overview

```
API Layer (FastAPI)
    ↓
Business Logic (Services)
    ↓
Storage Abstraction (Interface)
    ↓
Storage Implementation (Filesystem/DynamoDB/S3)
    ↓
Physical Storage
```

**Key Design Principle:** Storage backends are completely swappable via configuration. The same business logic works with filesystem, DynamoDB, S3, or any other backend that implements the interface.

---

## Storage Backends

### Filesystem Backend (Phase 1 - Default)

**Configuration:**
```bash
STORAGE_BACKEND=filesystem
STORAGE_PATH=./data/marketplace
```

**Structure:**
```
data/marketplace/
  agents/          # One JSON file per agent
  tools/           # One JSON file per tool
  access_control/  # Access rules
  _metadata/       # Collection metadata
```

**Characteristics:**
- Simple, no external dependencies
- Perfect for development
- Human-readable JSON files
- Easy debugging and inspection

### DynamoDB Backend (Future)

**Configuration:**
```bash
STORAGE_BACKEND=dynamodb
AWS_REGION=us-east-1
DYNAMODB_TABLE_PREFIX=claudevn-
```

**Characteristics:**
- Serverless, auto-scaling
- No infrastructure management
- Perfect for cloud deployments
- Pay per request

### S3 Backend (Future)

**Configuration:**
```bash
STORAGE_BACKEND=s3
S3_BUCKET=claudevn-marketplace
S3_PREFIX=production/
```

**Characteristics:**
- Object storage
- Highly durable
- Multi-region replication
- Good for distributed access

---

## API Reference

### Agent Management

**Create Agent**
```
POST /api/v1/agents
Body: {agent document}
Returns: Created agent with ID
```

**List Agents**
```
GET /api/v1/agents?capabilities=data_analysis&sort=usage_count&order=desc
Returns: Array of agents
```

**Get Agent**
```
GET /api/v1/agents/{agent_id}
Returns: Full agent document
```

**Search Agents**
```
POST /api/v1/agents/search
Body: {required_capabilities: [...]}
Returns: Ranked agent list with scores
```

**Get Agent Card (A2A)**
```
GET /api/v1/agents/{agent_id}/card
Returns: A2A-compliant Agent Card
```

### Tool Management

Similar endpoints at `/api/v1/tools`

### Access Control

**Set Access Rule**
```
POST /api/v1/access
Body: {access rule}
```

**Get Instance Permissions**
```
GET /api/v1/access/instances/{instance_id}
Returns: All applicable rules
```

### Health & Stats

**Health Check**
```
GET /api/v1/health
Returns: Service status
```

**Statistics**
```
GET /api/v1/stats
Returns: Marketplace statistics
```

---

## Data Model

### Agent Document

```
{
  "id": "agent-data-analyst-v1",
  "name": "Data Analyst Agent",
  "description": "Analyzes data...",
  "agent_type": "specialized",
  "version": "1.0.0",
  "capabilities": ["data_analysis", "statistical_analysis"],
  "supported_input_types": ["text/csv", "application/json"],
  "supported_output_types": ["application/json"],
  "complexity_level": "medium",
  "estimated_duration": 120,
  "language_model": "gpt-4",
  "created_at": "2025-11-21T10:00:00Z",
  "updated_at": "2025-11-21T10:00:00Z"
}
```

### Tool Document

```
{
  "id": "tool-data-processor-v1",
  "name": "Data Processor",
  "description": "Processes structured data...",
  "tool_type": "ecosystem",
  "version": "1.0.0",
  "parameters": {JSON schema},
  "return_type": {JSON schema}
}
```

---

## Configuration

### Environment Variables

**Service Configuration**
- `MARKETPLACE_PORT`: Service port (default: 8001)
- `MARKETPLACE_HOST`: Bind address (default: 0.0.0.0)
- `LOG_LEVEL`: Logging level (default: INFO)

**Storage Configuration**
- `STORAGE_BACKEND`: Backend type (filesystem, dynamodb, s3)
- `STORAGE_PATH`: Path for filesystem backend
- `STORAGE_CONFIG`: JSON config for backend-specific settings

**API Configuration**
- `CORS_ORIGINS`: CORS allowed origins (default: *)
- `API_VERSION`: API version (default: v1)
- `MAX_PAGE_SIZE`: Max results per page (default: 100)

**Future: Authentication**
- `AUTH_ENABLED`: Enable auth (default: false)
- `JWT_SECRET`: JWT secret
- `ADMIN_API_KEY`: Admin API key

---

## Seed Data

On first startup, the marketplace is seeded with:

**Coordinating Agents (5):**
- Goal Decomposer Agent
- Team Assembler Agent
- Execution Coordinator Agent
- Progress Tracker Agent
- Result Synthesizer Agent

**Specialized Agents (2):**
- Content Writer Agent
- Research Agent

**Tools:**
- None in Phase 1

Seed data is loaded from `seed_data/` directory and is idempotent.

---

## Integration

### With Serving Component

Serving Component queries marketplace for agent discovery:

```python
# In Serving Component
import requests

marketplace_url = "http://localhost:8001"
response = requests.get(
    f"{marketplace_url}/api/v1/agents/search",
    json={"required_capabilities": ["data_analysis"]}
)
agents = response.json()
```

### With Compute Instances

Coordinating agents query marketplace directly:

```python
# In Team Assembler Agent
import requests

response = requests.post(
    f"{self.marketplace_url}/api/v1/agents/search",
    json={"required_capabilities": required_caps}
)
ranked_agents = response.json()
```

### Caching

External systems may cache agent data:
- Recommended TTL: 5 minutes
- Invalidation via polling (webhooks in future)
- Cache Agent Cards for performance

---

## Development

### Directory Structure

```
marketplace/
  main.py              # FastAPI application
  requirements.txt     # Dependencies
  start.sh            # Startup script
  .env.example        # Environment template
  api/                # API endpoints
    agents.py
    tools.py
    access.py
    health.py
  storage/            # Storage layer
    backend.py        # Abstract interface
    filesystem.py     # Filesystem implementation
    config.py         # Backend configuration
  services/           # Business logic
    agent_service.py
    tool_service.py
    search_service.py
  models/             # Pydantic models
    agent.py
    tool.py
  utils/              # Utilities
    validation.py
    a2a_card.py
  seed_data/          # Initial data
    agents.json
  data/               # Runtime storage (gitignored)
```

### Adding a New Agent

**Option 1: API**
```bash
curl -X POST http://localhost:8001/api/v1/agents \
  -H "Content-Type: application/json" \
  -d @new_agent.json
```

**Option 2: Add to Seed Data**
Edit `seed_data/agents.json` and restart service.

### Adding a Storage Backend

1. Create new file in `storage/` (e.g., `postgres.py`)
2. Implement `StorageBackend` interface
3. Register in `storage/config.py`
4. Set `STORAGE_BACKEND=postgres` in `.env`

No changes to business logic required!

---

## Testing

### Manual Test Scenarios

**Agent CRUD:**
1. Create agent with valid data → Success
2. Create agent with missing field → 400 Error
3. Create duplicate agent → 409 Error
4. List all agents → Returns array
5. Filter by capability → Returns matching
6. Get agent by ID → Returns document
7. Get non-existent agent → 404 Error
8. Update agent → Changes persisted
9. Delete agent → Removed from listings

**Search:**
1. Search by capability → Ranked results
2. Empty search → All agents
3. No matches → Empty array

**Agent Card:**
1. Get Agent Card → Valid A2A JSON
2. Card reflects agent data → Accurate

**Storage:**
1. Switch backends → Same behavior
2. Backend failure → Graceful error

### Test with curl

```bash
# Health check
curl http://localhost:8001/api/v1/health

# List agents
curl http://localhost:8001/api/v1/agents

# Search by capability
curl -X POST http://localhost:8001/api/v1/agents/search \
  -H "Content-Type: application/json" \
  -d '{"required_capabilities": ["data_analysis"]}'

# Get Agent Card
curl http://localhost:8001/api/v1/agents/agent-data-analyst-v1/card
```

---

## Monitoring

### Health Check

```bash
curl http://localhost:8001/api/v1/health
```

Returns:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "storage_backend": "filesystem",
  "storage_status": "connected",
  "agent_count": 7,
  "tool_count": 0
}
```

### Statistics

```bash
curl http://localhost:8001/api/v1/stats
```

Returns:
```json
{
  "agents": {
    "total": 7,
    "coordinating": 5,
    "specialized": 2
  },
  "tools": {
    "total": 0
  },
  "popular_capabilities": [
    "data_analysis",
    "goal_decomposition"
  ]
}
```

### Logs

Logs are written to stdout in structured format:
```json
{
  "timestamp": "2025-11-21T10:00:00Z",
  "level": "INFO",
  "message": "Agent created",
  "agent_id": "agent-xyz",
  "request_id": "abc-123"
}
```

---

## Troubleshooting

### Service won't start

**Check port availability:**
```bash
lsof -i :8001
```

**Check storage path permissions:**
```bash
ls -la data/marketplace
```

**Check environment variables:**
```bash
env | grep STORAGE
```

### Agent not found

**Verify agent exists:**
```bash
ls data/marketplace/agents/
```

**Check agent ID format:**
- Must match filename without .json extension

### Storage backend errors

**Filesystem:**
- Verify path exists and is writable
- Check disk space

**DynamoDB (future):**
- Verify AWS credentials
- Check table permissions
- Verify region

**S3 (future):**
- Verify bucket exists
- Check S3 permissions
- Verify credentials

### API returns 500 errors

**Check logs:**
```bash
tail -f logs/marketplace.log
```

**Verify storage backend:**
```bash
curl http://localhost:8001/api/v1/health
```

---

## Performance

### Response Times (Expected)

- List agents: < 100ms (local filesystem)
- Search agents: < 200ms (local filesystem)
- Get agent: < 50ms (local filesystem)
- Create agent: < 100ms (local filesystem)

### Scalability

**Horizontal:**
- Stateless design
- Load balancer friendly
- Requires shared storage backend (DynamoDB, S3)

**Vertical:**
- Single instance handles 100+ req/sec
- Bottleneck is typically storage backend

### Optimization

**Caching (future):**
- Popular agents cached in memory
- Search results cached with TTL
- Agent Cards cached after generation

**Database Indexes (future):**
- Index on capabilities
- Index on agent_type
- Index on tags

---

## Security

### Phase 1 (Current)

- No authentication (open marketplace)
- Input validation on all endpoints
- Schema enforcement
- Safe for development and trusted environments

### Future Phases

**Authentication:**
- API keys for write operations
- JWT tokens for user operations
- OAuth for frontend

**Authorization:**
- Role-based access control
- Per-agent access rules
- Audit logging

**Storage:**
- Encryption at rest
- Encryption in transit (HTTPS)
- Secure credential management

---

## Documentation

**Full Design:** See `/docs/marketplace-design.md`
**Summary:** See `/docs/marketplace-design-summary.md`
**Architecture Diagrams:** See `/docs/marketplace-architecture-diagrams.md`

---

## Support

For issues or questions:
1. Check the documentation in `/docs`
2. Review existing issues on GitHub
3. Check logs for error details
4. Verify configuration and environment

---

## Roadmap

### Phase 1 (Current)
- ✅ RESTful API design
- ✅ Filesystem storage backend
- ✅ Agent CRUD operations
- ✅ Capability search
- ✅ A2A Agent Card generation
- ⏳ Frontend UI (pending)
- ⏳ Seed data loading (pending)

### Phase 2
- Authentication and authorization
- Agent versioning
- Enhanced search (fuzzy, semantic)
- Webhook notifications
- DynamoDB backend

### Phase 3
- Performance analytics
- Agent testing framework
- S3 backend
- Automated overlap detection
- Agent recommendation engine

### Phase 4
- Monetization support
- Reputation system
- User reviews and ratings
- Certification program

---

## License

See LICENSE file in repository root.

