# ClaudeVN Code Refactoring Plan

## Executive Summary

This document identifies files that will grow significantly as we add features, and proposes a modular refactoring strategy to maintain clean, maintainable code.

## Files at Risk of Becoming Too Large

### 1. **serving/api/sessions.py** (Currently 334 lines)

**Current State:**
- 10+ API endpoints
- All session management in one file
- Includes: CRUD operations, status updates, task results, data refs, execution plans, statistics

**Growth Vectors:**
- Session workflows (pause, resume, fork)
- Advanced querying and filtering
- Session templates
- Session sharing and permissions
- Export/import functionality
- Webhooks for session events
- Session cleanup policies
- Session archiving

**Risk Level:** 🔴 **HIGH** - Could easily reach 1000+ lines

---

### 2. **serving/api/storage.py** (Currently 312 lines)

**Current State:**
- 8 API endpoints for blob storage
- Upload, download, metadata, cleanup

**Growth Vectors:**
- Storage quotas and limits
- Access control and permissions
- Multi-part uploads for large files
- Versioning support
- Storage policies (retention, lifecycle)
- Storage backends (S3, Azure, GCS)
- Compression and encryption
- Thumbnail generation for images
- Virus scanning

**Risk Level:** 🟡 **MEDIUM-HIGH** - Could reach 600-800 lines

---

### 3. **compute/runtime/llm_client.py** (Currently 300 lines)

**Current State:**
- LLMClient with multi-provider support
- Currently only OpenAI implemented
- Fallback and retry logic

**Growth Vectors:**
- Anthropic provider implementation
- Ollama provider implementation
- More providers (Cohere, Hugging Face, etc.)
- Response caching layer
- Prompt template management
- Token budget management
- Fine-tuning support
- Embedding support
- Function calling / tool use
- Streaming improvements
- Rate limiting per provider

**Risk Level:** 🔴 **HIGH** - Could reach 800+ lines without refactoring

---

### 4. **serving/broker/session_context.py** (Currently 322 lines)

**Current State:**
- SessionContext dataclass
- SessionContextManager with in-memory storage

**Growth Vectors:**
- Database backend (SQLite, PostgreSQL)
- Redis backend for distributed systems
- Session locking for concurrent access
- Session snapshots and rollback
- Session search and indexing
- Session analytics
- Memory management for large contexts
- Context compression

**Risk Level:** 🟡 **MEDIUM-HIGH** - Could reach 600+ lines

---

### 5. **serving/storage/filesystem.py** (Currently 296 lines)

**Current State:**
- Filesystem storage backend implementation
- Complete implementation for local storage

**Growth Vectors:**
- S3-compatible backend
- Azure Blob Storage backend
- Google Cloud Storage backend
- Multi-region replication
- Storage optimization (deduplication)
- Backup and restore

**Risk Level:** 🟢 **LOW** - Well-contained, will create separate files for new backends

---

### 6. **Future Files** (Not Yet Created)

These files don't exist yet but will need careful structure from the start:

#### **serving/api/instances.py**
- Instance registration
- Health checks
- Capability management
- Load balancing
- Instance metrics

**Estimated Size:** 400-600 lines

#### **serving/api/a2a.py**
- A2A protocol endpoints
- Task submission
- Task status and streaming
- Agent card serving
- Protocol negotiation

**Estimated Size:** 500-800 lines

#### **serving/broker/router.py**
- Message routing logic
- Task queuing
- Priority handling
- Load distribution

**Estimated Size:** 400-600 lines

---

## Proposed Refactoring Strategy

### 1. Modularize Sessions API

**Current:**
```
serving/api/sessions.py (334 lines, all endpoints)
```

**Proposed:**
```
serving/api/sessions/
├── __init__.py              # Router aggregation
├── crud.py                  # Create, Read, Update, Delete
├── status.py                # Status management endpoints
├── results.py               # Task results endpoints
├── data_refs.py             # Data reference endpoints
├── execution_plan.py        # Execution plan endpoints
├── stats.py                 # Statistics endpoints
└── models.py                # Pydantic models
```

**Benefits:**
- Each file stays under 100-150 lines
- Easy to find specific functionality
- Multiple developers can work simultaneously
- Testing becomes more focused
- Clear separation of concerns

---

### 2. Modularize Storage API

**Current:**
```
serving/api/storage.py (312 lines)
```

**Proposed:**
```
serving/api/storage/
├── __init__.py              # Router aggregation
├── upload.py                # Upload endpoints
├── download.py              # Download endpoints
├── metadata.py              # Metadata endpoints
├── management.py            # Cleanup, stats, admin
├── session.py               # Session-specific storage
├── models.py                # Pydantic models
└── permissions.py           # Access control (future)
```

---

### 3. Create LLM Provider Registry

**Current:**
```
compute/runtime/llm_client.py (300 lines)
compute/runtime/providers/
├── base.py
├── openai_provider.py
└── __init__.py
```

**Proposed:**
```
compute/runtime/llm_client.py (150 lines - core client only)
compute/runtime/providers/
├── __init__.py              # Provider registry
├── registry.py              # Auto-discovery system
├── base.py                  # Base classes
├── openai.py                # OpenAI provider
├── anthropic.py             # Anthropic provider (future)
├── ollama.py                # Ollama provider (future)
├── cache.py                 # Response caching layer
└── utils.py                 # Shared utilities
```

**Provider Registry Pattern:**
```python
# registry.py
class ProviderRegistry:
    _providers = {}
    
    @classmethod
    def register(cls, provider_name):
        def decorator(provider_class):
            cls._providers[provider_name] = provider_class
            return provider_class
        return decorator
    
    @classmethod
    def get_provider(cls, provider_name):
        return cls._providers.get(provider_name)

# openai.py
@ProviderRegistry.register("openai")
class OpenAIProvider(BaseLLMProvider):
    ...

# anthropic.py
@ProviderRegistry.register("anthropic")
class AnthropicProvider(BaseLLMProvider):
    ...
```

---

### 4. Separate Session Storage Backends

**Current:**
```
serving/broker/session_context.py (322 lines)
```

**Proposed:**
```
serving/broker/
├── session_context.py       # Core SessionContext dataclass (100 lines)
├── session_manager.py       # Manager interface (100 lines)
└── storage/
    ├── __init__.py
    ├── base.py              # Abstract backend
    ├── memory.py            # In-memory (current)
    ├── sqlite.py            # SQLite backend (future)
    ├── postgresql.py        # PostgreSQL backend (future)
    └── redis.py             # Redis backend (future)
```

---

### 5. Create API Router Factory

**For Future Growth:**

```
serving/api/
├── __init__.py              # Main router factory
├── sessions/                # Session management
├── storage/                 # Blob storage
├── instances/               # Instance management (future)
├── a2a/                     # A2A protocol (future)
├── admin/                   # Admin endpoints (future)
└── utils/                   # Shared utilities
    ├── dependencies.py      # Common dependencies
    ├── auth.py              # Authentication
    └── validation.py        # Input validation
```

**Main router factory:**
```python
# serving/api/__init__.py
from fastapi import APIRouter
from .sessions import router as sessions_router
from .storage import router as storage_router

def create_api_router() -> APIRouter:
    """Create and configure all API routes"""
    root_router = APIRouter()
    
    # Include all sub-routers
    root_router.include_router(sessions_router)
    root_router.include_router(storage_router)
    # Future: instances_router, a2a_router, etc.
    
    return root_router
```

---

## Implementation Priority

### Phase 1: Immediate (Before Further Development)
1. ✅ **Refactor sessions API** → modular structure
2. ✅ **Refactor storage API** → modular structure
3. ✅ **Create provider registry** → prepare for new LLM providers

### Phase 2: Near-Term (Next 2-4 weeks)
4. **Separate session storage backends** → prepare for database support
5. **Create instances API structure** → modular from the start
6. **Create A2A API structure** → modular from the start

### Phase 3: Medium-Term (1-2 months)
7. **Add session search and filtering** → dedicated module
8. **Add storage permissions** → dedicated module
9. **Add LLM response caching** → dedicated module

---

## Implementation Guidelines

### 1. Module Organization Rules

- **Maximum file size:** 200 lines (soft limit)
- **Maximum function length:** 50 lines
- **One responsibility per file**
- **Clear naming conventions**
- **Comprehensive docstrings**

### 2. Router Pattern

Each API module should follow this pattern:

```python
# api/domain/__init__.py
from fastapi import APIRouter
from . import crud, status, special_ops

router = APIRouter(prefix="/api/domain", tags=["domain"])

# Include sub-routers
router.include_router(crud.router)
router.include_router(status.router)
router.include_router(special_ops.router)
```

### 3. Shared Models

```python
# api/domain/models.py
from pydantic import BaseModel

class CreateRequest(BaseModel):
    ...

class UpdateRequest(BaseModel):
    ...

class Response(BaseModel):
    ...
```

### 4. Shared Dependencies

```python
# api/domain/dependencies.py
from fastapi import Depends

def get_manager():
    return manager_instance
```

---

## Testing Strategy

### 1. Module-Level Tests

Each module gets its own test file:
```
tests/serving/api/sessions/
├── test_crud.py
├── test_status.py
├── test_results.py
└── ...
```

### 2. Integration Tests

Test router aggregation:
```python
# tests/serving/api/test_sessions_integration.py
def test_all_sessions_endpoints_registered():
    assert "/api/sessions" in app.routes
    assert "/api/sessions/{id}" in app.routes
    ...
```

---

## Migration Path

### For Existing Files:

1. **Create new directory structure**
2. **Move endpoints to new files** (copy first, then refactor)
3. **Update imports in main application**
4. **Run tests to verify functionality**
5. **Remove old file**
6. **Update documentation**

### Backwards Compatibility:

- All endpoint paths remain unchanged
- API behavior remains identical
- Only internal organization changes

---

## Expected Outcomes

### Maintainability
- ✅ Files stay under 200 lines
- ✅ Easy to locate specific functionality
- ✅ Reduced merge conflicts
- ✅ Clearer code ownership

### Scalability
- ✅ Can add features without file bloat
- ✅ New developers can navigate easily
- ✅ Plugin architecture for providers
- ✅ Easy to add new backends

### Testing
- ✅ Focused unit tests
- ✅ Faster test execution
- ✅ Better test organization
- ✅ Higher code coverage

---

## Next Steps

1. **Review this plan** with team
2. **Prioritize refactoring** tasks
3. **Create detailed implementation tickets**
4. **Begin Phase 1 refactoring**
5. **Document new structure** as we go
6. **Update project-structure.md** with new patterns

---

## Appendix: File Size Projections

| File | Current | Projected (no refactor) | Projected (with refactor) |
|------|---------|-------------------------|---------------------------|
| sessions.py | 334 | 1000+ | 100-150 per module |
| storage.py | 312 | 600-800 | 100-150 per module |
| llm_client.py | 300 | 800+ | 150 (client) + 150-200 per provider |
| session_context.py | 322 | 600+ | 100 (context) + 100-150 per backend |

---

**Document Version:** 1.0  
**Date:** 2025-11-21  
**Author:** ClaudeVN Development Team

