# Marketplace Quick Reference

One-page summary of the Marketplace Service design.

---

## What It Is

The Marketplace is ClaudeVN's discovery system where coordinating agents find and select specialized agents based on capabilities.

---

## Architecture (4 Layers)

```
┌─────────────────────────────────────────┐
│  API Layer (FastAPI REST)              │  ← External interface
├─────────────────────────────────────────┤
│  Business Logic (Services)              │  ← Search, match, validate
├─────────────────────────────────────────┤
│  Storage Abstraction (Interface)        │  ← Backend-agnostic layer
├─────────────────────────────────────────┤
│  Storage Implementation (Backend)       │  ← Filesystem/DynamoDB/S3
└─────────────────────────────────────────┘
```

---

## Storage Backend Swapping

**Simple Config Change:**
```
# Today
STORAGE_BACKEND=filesystem

# Tomorrow
STORAGE_BACKEND=dynamodb

# Same code, different storage
```

**Implementations:**
- **Filesystem** (Phase 1): JSON files in directories
- **DynamoDB** (Future): Serverless NoSQL
- **S3** (Future): Object storage

---

## Data Model

**Agent Document:**
- Identity: id, name, version, type
- Capabilities: array of capability tags
- Technical: input/output types, complexity, duration
- Metadata: publisher, tags, timestamps
- Performance: usage count, success rate

**Tool Document:**
- Identity: id, name, version, type  
- Specification: parameter schema, return type
- Implementation: connection details
- Access: restrictions and allowed agents

---

## Mock Agents

### 1. Content Writer Agent (Specialized)
- **Purpose:** Generate summaries, reports, documentation
- **Capabilities:** content_generation, summarization, report_writing, documentation, tone_adaptation
- **Duration:** 60-180 seconds
- **Use Case:** Executive summaries, technical docs, audience-appropriate content

### 2. Research Agent (Specialized)
- **Purpose:** Gather and synthesize information
- **Capabilities:** information_gathering, source_synthesis, fact_verification, topic_investigation, citation_management
- **Duration:** 120-300 seconds
- **Use Case:** Business intelligence, competitive analysis, fact-checking

---

## API Endpoints

**Agents:**
- `POST /api/v1/agents` - Create
- `GET /api/v1/agents` - List (filter, sort, paginate)
- `GET /api/v1/agents/{id}` - Get
- `PUT /api/v1/agents/{id}` - Update
- `DELETE /api/v1/agents/{id}` - Delete
- `GET /api/v1/agents/{id}/card` - A2A Card
- `POST /api/v1/agents/search` - Capability search

**Tools:** Similar CRUD at `/api/v1/tools`

**Access:** Rules at `/api/v1/access`

**Health:** Status at `/api/v1/health`

---

## Frontend (React)

**Pages:**
1. **Browse** - Search, filter, grid/list view, pagination
2. **Agent Detail** - Full specs, metrics, Agent Card
3. **Tools** - Tool-specific browsing
4. **Admin** - Registration forms (future)

**Features:**
- Real-time search
- Multi-select filters
- Grid/list toggle
- Deep linking
- Responsive design

---

## Key Features

**Capability Matching:**
- Search by required capabilities
- Rank by relevance (match score, specialization, performance)
- Return scored list

**Overlap Detection:**
- Compare new agents to existing
- Flag if >70% capability overlap + >60% similarity
- Prevent marketplace pollution

**A2A Compliance:**
- Generate Agent Cards on demand
- Standard protocol format
- External system compatibility

---

## Integration

**With Serving:**
- Serving queries marketplace for discovery
- Read-only relationship
- Optional caching (5min TTL)

**With Compute:**
- Coordinating agents query directly
- Capability-based search
- Agent Card retrieval

---

## Configuration

**Required:**
- `MARKETPLACE_PORT` - Service port (8001)
- `STORAGE_BACKEND` - Backend type

**Optional:**
- `STORAGE_PATH` - Filesystem path
- `LOG_LEVEL` - Logging verbosity
- `CORS_ORIGINS` - CORS settings
- `MAX_PAGE_SIZE` - Query limits

---

## Deployment

**Standalone:**
```bash
cd marketplace
./start.sh
```

**Access:**
- API: http://localhost:8001/api/v1
- Health: http://localhost:8001/api/v1/health

**Storage:**
- Default: `./data/marketplace/`
- Collections: agents/, tools/, access_control/

---

## Seed Data

**Coordinating Agents (5):**
- Goal Decomposer
- Team Assembler
- Execution Coordinator
- Progress Tracker
- Result Synthesizer

**Specialized Agents (2):**
- Content Writer
- Research Agent

**Tools:** None (Phase 1)

---

## Business Logic

**Search Scoring:**
```
Score = Capability matches (×10)
      + Specialization bonus (+5)
      + Success rate bonus (≤+10)
      + Popularity bonus (≤+2)
      + Locality bonus (+20)
```

**Overlap Detection:**
```
IF capability_overlap > 70%
   AND description_similarity > 60%
THEN flag for review
```

---

## Testing

**Key Scenarios:**
- Create/list/get/update/delete agents
- Search by capabilities
- Filter and pagination
- A2A Card generation
- Backend swapping
- Error handling

**Tools:**
```bash
curl http://localhost:8001/api/v1/health
curl http://localhost:8001/api/v1/agents
curl -X POST .../agents/search -d '{...}'
```

---

## File Organization

```
marketplace/
  main.py              # Entry point
  requirements.txt     # Dependencies
  start.sh            # Startup
  api/                # Endpoints
  storage/            # Backends
  services/           # Business logic
  models/             # Data models
  utils/              # Helpers
  seed_data/          # Initial data
  data/               # Runtime storage
```

---

## Documentation

**Full Design:**
- `/docs/marketplace-design.md` - Complete specification
- `/docs/marketplace-design-summary.md` - Executive summary
- `/docs/marketplace-architecture-diagrams.md` - Visual diagrams
- `/marketplace/README.md` - Operational guide
- `/MARKETPLACE-DESIGN-REVIEW.md` - Approval checklist

---

## Status

**Current:** ✅ Design complete, ready for approval

**Next:** Implementation after approval

---

## Key Design Decisions

1. **Storage Abstraction** - Complete backend flexibility
2. **Independent Service** - No dependencies on other components
3. **A2A Compliance** - Standard protocol for interoperability
4. **Simple First** - Filesystem for Phase 1, scale later
5. **Stateless API** - Horizontal scalability ready
6. **No Auth** - Phase 1 focuses on functionality
7. **Document Model** - Flexible JSON documents
8. **RESTful Design** - Industry standard API patterns

---

## Success Criteria

✅ Runs standalone on port 8001  
✅ Creates and lists agents via API  
✅ Frontend displays agents with search  
✅ Two mock agents included  
✅ Storage backend swappable  
✅ Agent Cards in A2A format  
✅ Health check operational  

---

## Questions?

See full documentation in `/docs/` directory.

**Ready for implementation after approval.**

