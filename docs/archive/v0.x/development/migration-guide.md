# Migration Guide: From Monolithic to Modular Structure

This guide explains the new modular structure and how to use it.

## Overview

We've refactored the codebase from monolithic files into a modular structure to prevent files from becoming thousands of lines long as we add features.

## What Changed?

### 1. Sessions API (serving/api/sessions/)

**Before:**
```
serving/api/sessions.py (334 lines)
```

**After:**
```
serving/api/sessions/
├── __init__.py          # Router aggregation
├── models.py            # Pydantic models
├── dependencies.py      # Shared dependencies
├── utils.py             # Utility functions
├── crud.py              # Create, Read, Update, Delete
├── status.py            # Status management
├── results.py           # Task results
├── data_refs.py         # Data references
├── execution_plan.py    # Execution plans
└── stats.py             # Statistics
```

**Benefits:**
- Each file is under 100 lines
- Easy to find specific functionality
- Multiple developers can work on different concerns simultaneously
- Better test organization

---

### 2. Storage API (serving/api/storage_api/)

**Before:**
```
serving/api/storage.py (312 lines)
```

**After:**
```
serving/api/storage_api/
├── __init__.py          # Router aggregation
├── models.py            # Pydantic models
├── dependencies.py      # Shared dependencies
├── upload.py            # Upload operations
├── download.py          # Download operations
├── metadata.py          # Metadata and deletion
├── session.py           # Session-specific storage
└── management.py        # Cleanup and stats
```

---

### 3. LLM Provider Registry (compute/runtime/providers/)

**Before:**
```python
# llm_client.py
def _create_provider(self, config):
    if config.provider == LLMProvider.OPENAI:
        return OpenAIProvider(config)
    elif config.provider == LLMProvider.ANTHROPIC:
        raise LLMConfigError("Not implemented")
    # ... more elif statements
```

**After:**
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

# openai_provider.py
@ProviderRegistry.register("openai")
class OpenAIProvider(BaseLLMProvider):
    ...

# llm_client.py
def _create_provider(self, config):
    return ProviderRegistry.create_provider(config, api_key=api_key)
```

**Benefits:**
- No need to modify llm_client.py to add new providers
- Providers auto-register on import
- Clear template for new providers (_template.py)

---

## How to Use the New Structure

### Using the Sessions API

**In your main application:**

```python
from fastapi import FastAPI
from serving.api.sessions import router as sessions_router

app = FastAPI()
app.include_router(sessions_router)
```

That's it! All endpoints are automatically included.

**Endpoints remain the same:**
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `DELETE /api/sessions/{id}`
- `PATCH /api/sessions/{id}/status`
- `POST /api/sessions/{id}/task_results`
- `POST /api/sessions/{id}/data_refs`
- `PUT /api/sessions/{id}/execution_plan`
- `GET /api/sessions/stats/summary`

---

### Using the Storage API

**In your main application:**

```python
from fastapi import FastAPI
from serving.api.storage_api import router as storage_router

app = FastAPI()
app.include_router(storage_router)
```

**Endpoints remain the same:**
- `POST /api/storage/upload`
- `GET /api/storage/{blob_id}`
- `GET /api/storage/{blob_id}/metadata`
- `DELETE /api/storage/{blob_id}`
- `GET /api/storage/session/{id}/blobs`
- `POST /api/storage/cleanup`
- `GET /api/storage/stats`

---

### Adding a New LLM Provider

1. **Copy the template:**
```bash
cp compute/runtime/providers/_template.py compute/runtime/providers/anthropic_provider.py
```

2. **Update the provider:**
```python
@ProviderRegistry.register("anthropic")
class AnthropicProvider(BaseLLMProvider):
    def __init__(self, config: LLMConfig, api_key: Optional[str] = None):
        super().__init__(config)
        # Initialize Anthropic client
        ...
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # Implement generation logic
        ...
```

3. **Import in `__init__.py`:**
```python
# compute/runtime/providers/__init__.py
from .anthropic_provider import AnthropicProvider

__all__ = [..., "AnthropicProvider"]
```

4. **Provider is now available:**
```python
config = LLMConfig(
    provider=LLMProvider.ANTHROPIC,
    model="claude-3-sonnet",
    temperature=0.7
)
client = LLMClient([config], api_keys={"anthropic": "sk-ant-..."})
```

---

## File Organization Principles

### 1. Maximum File Size
- **Soft limit:** 200 lines per file
- **Hard limit:** 300 lines per file
- If a file exceeds these limits, refactor it

### 2. Single Responsibility
- Each file should have ONE clear purpose
- Example: `crud.py` handles CRUD operations only
- Example: `status.py` handles status updates only

### 3. Shared Code
- Models go in `models.py`
- Dependencies go in `dependencies.py`
- Utility functions go in `utils.py`

### 4. Router Aggregation
- `__init__.py` aggregates all sub-routers
- Main application imports only from `__init__.py`

---

## Testing Strategy

### Module-Level Tests

Each module gets its own test file:

```
tests/serving/api/sessions/
├── test_crud.py
├── test_status.py
├── test_results.py
└── ...
```

### Integration Tests

Test that all endpoints are properly registered:

```python
# tests/serving/api/test_sessions_integration.py
def test_sessions_router_includes_all_endpoints():
    from serving.api.sessions import router
    
    paths = [route.path for route in router.routes]
    
    assert "/api/sessions" in paths
    assert "/api/sessions/{session_id}" in paths
    assert "/api/sessions/{session_id}/status" in paths
    # ...
```

---

## Adding New Functionality

### Example: Adding Session Search

1. **Create new endpoint file:**
```python
# serving/api/sessions/search.py
from fastapi import APIRouter, Query, Depends

router = APIRouter()

@router.get("/search")
async def search_sessions(
    query: str = Query(...),
    manager = Depends(get_session_manager)
):
    """Search sessions by various criteria."""
    # Implementation
    ...
```

2. **Add to router aggregation:**
```python
# serving/api/sessions/__init__.py
from . import crud, status, results, data_refs, execution_plan, stats, search

router.include_router(search.router)
```

3. **Done!** The endpoint is now available at `/api/sessions/search`

---

## Common Patterns

### Pattern 1: Shared Models

```python
# models.py
class CreateRequest(BaseModel):
    ...

class UpdateRequest(BaseModel):
    ...

class Response(BaseModel):
    ...

# crud.py
from .models import CreateRequest, Response

@router.post("", response_model=Response)
async def create(request: CreateRequest):
    ...
```

### Pattern 2: Shared Dependencies

```python
# dependencies.py
def get_manager():
    return manager_instance

# crud.py
from .dependencies import get_manager

@router.post("")
async def create(manager = Depends(get_manager)):
    ...
```

### Pattern 3: Shared Utilities

```python
# utils.py
def transform_context(context):
    return Response(...)

# crud.py
from .utils import transform_context

@router.get("/{id}")
async def get(id: str):
    context = await manager.get(id)
    return transform_context(context)
```

---

## Backwards Compatibility

### API Endpoints

**All endpoint paths remain exactly the same.** This is a purely internal refactoring.

- `POST /api/sessions` still works
- `GET /api/storage/{blob_id}` still works
- All responses are identical

### Code Imports

**Old imports still work** (if old files are kept temporarily):

```python
# Still works
from serving.api.sessions import router

# Also works
from serving.api.sessions import SessionResponse
```

**New recommended imports:**

```python
# Import router from module
from serving.api.sessions import router

# Import models explicitly
from serving.api.sessions.models import SessionResponse
```

---

## Migration Checklist

If you're updating an existing deployment:

- [ ] Update imports in main application file
- [ ] Run tests to verify functionality
- [ ] Check that all endpoints respond correctly
- [ ] Update any documentation
- [ ] Remove old monolithic files (optional, after verification)

---

## Future Additions

### Planned Modular APIs

1. **Instance Management API** (`serving/api/instances/`)
   - Registration
   - Health checks
   - Metrics

2. **A2A Protocol API** (`serving/api/a2a/`)
   - Task submission
   - Task status
   - Streaming

3. **Admin API** (`serving/api/admin/`)
   - System stats
   - Configuration
   - Maintenance

---

## Getting Help

If you have questions about the new structure:

1. Check the refactoring plan: `docs/refactoring-plan.md`
2. Look at existing modules for examples
3. Use the template files as a starting point
4. Follow the file organization principles

---

## Summary

**Key Benefits:**
✅ Files stay small and focused
✅ Easy to find and modify code
✅ Better collaboration (less merge conflicts)
✅ Clear patterns for adding features
✅ Automatic provider registration
✅ Better test organization

**No Breaking Changes:**
✅ All API endpoints unchanged
✅ All responses identical
✅ Backwards compatible imports
✅ Same functionality, better structure

