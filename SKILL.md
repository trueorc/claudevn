---
name: claudevn-patterns
description: Coding patterns extracted from ClaudeVN AI agent orchestration platform
version: 1.0.0
source: local-git-analysis
analyzed_commits: 200
---

# ClaudeVN Development Patterns

## Commit Conventions

This project uses **conventional commits** with issue references:

| Prefix | Usage |
|--------|-------|
| `feat:` | New features (59% of commits) |
| `fix:` | Bug fixes (20% of commits) |
| `docs:` | Documentation updates (9%) |
| `test:` | Test-related changes (8%) |
| `refactor:` | Code restructuring (2%) |
| `chore:` | Maintenance tasks (2%) |

**Commit message format:**
```
feat: Short description of feature (#issue-number)
fix: Brief bug fix description (#issue-number)
docs: Documentation update description
```

**73% of commits reference GitHub issues** - always link commits to issues.

**Branch naming convention:**
```
{type}/issue-{number}-{short-description}
```

Examples:
- `feat/issue-155-shutdown-handler`
- `fix/issue-102-failing-unit-tests`
- `docs/issue-149-goal-api-endpoints`

## Code Architecture

### Directory Structure

```
serving/              # Central coordination hub (FastAPI, Python 3.10+)
├── api/              # API route handlers (one file per domain)
├── models/           # Pydantic data models
├── services/         # Business logic services
├── git/              # Git infrastructure (SSH, hooks, PR management)
├── mcp/              # MCP server for compute communication
│   └── tools/        # MCP tool implementations
├── tests/            # Unit and integration tests
└── frontend/         # React UI with TailwindCSS
    └── src/
        ├── api/          # API client functions
        ├── components/   # React components by domain
        ├── hooks/        # Custom React hooks
        └── pages/        # Page-level components

marketplace/          # Skill marketplace service (separate from Serving)
├── skills/           # Skill definitions (YAML)
│   └── system/       # System-provided skills
├── personas/         # Persona bundles (YAML)
│   └── system/       # System personas
├── services/         # Business logic
└── tests/            # Test files

compute/              # Claude Code compute infrastructure
├── api/              # API endpoints
├── services/         # Service layer
└── tests/            # Test files
```

### File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| API routes | `{domain}.py` | `serving/api/work_map.py` |
| Models | `{domain}.py` | `serving/models/compute.py` |
| Services | `{domain}_service.py` | `serving/services/work_map_service.py` |
| Tests | `test_{module}.py` | `serving/tests/test_work_map_service.py` |
| React components | `{ComponentName}.jsx` | `WorkMapGraph.jsx` |
| React hooks | `use{HookName}.js` | `useWorkMap.js` |
| API clients | `{domain}.js` | `api/workmap.js` |
| Skills | `{skill-name}.yaml` | `skills/system/code-writer.yaml` |

### Most Frequently Changed Files

1. `serving/app.py` - Main FastAPI application
2. `serving/services/work_map_service.py` - Work coordination logic
3. `serving/models/work_map.py` - Work map data models
4. `CLAUDE.md` - Project instructions for Claude Code
5. `marketplace/api.py` - Marketplace API routes

## Workflows

### Adding a New API Endpoint

1. Create/update model in `serving/models/{domain}.py`
2. Add business logic in `serving/services/{domain}_service.py`
3. Create API route in `serving/api/{domain}.py`
4. Register route in `serving/app.py`
5. Add tests in `serving/tests/test_{domain}_{feature}.py`
6. Update frontend API client if needed

### Adding a New Skill

1. Create YAML definition in `marketplace/skills/system/{skill-name}.yaml`
2. Include: id, name, description, version, author, instructions, tags
3. Add test coverage in `marketplace/tests/test_skill_registry.py`
4. Skills should follow the code-writer.yaml template structure

### Adding a New MCP Tool

1. Create tool in `serving/mcp/tools/{tool_name}.py`
2. Register in `serving/mcp/tools/__init__.py`
3. Add models in `serving/mcp/models.py`
4. Register in `serving/mcp/server.py`
5. Add tests in `serving/tests/test_mcp_{tool_name}.py`

### Adding a Frontend Feature

1. Create component in `serving/frontend/src/components/{domain}/`
2. Add CSS file `{ComponentName}.css` alongside component
3. Create hook in `serving/frontend/src/hooks/use{Feature}.js`
4. Add API client in `serving/frontend/src/api/{domain}.js`
5. Update page in `serving/frontend/src/pages/{Page}Page.jsx`
6. Register route in `serving/frontend/src/App.jsx` if new page

## Testing Patterns

### Test Structure

```python
"""Tests for {module}."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Fixtures
@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.hset = AsyncMock()
    return redis

@pytest.fixture
def service():
    """Create service for testing."""
    return MyService(redis_client=None)

# Test Classes grouped by functionality
class TestServiceInit:
    """Test service initialization."""

    def test_init_without_deps(self):
        """Test initialization without dependencies."""
        pass

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test async operations."""
        pass
```

### Test File Organization

- Unit tests: `{component}/tests/test_{module}.py`
- Integration tests: `tests/test_{integration_type}.py`
- Run unit tests: `scripts/run_unit_tests.sh`
- Run integration tests: `scripts/run_integration_tests.sh`

### Test Naming

- Test files: `test_{module_name}.py`
- Test classes: `Test{FeatureName}` (e.g., `TestWorkMapServiceInit`)
- Test methods: `test_{action}_{scenario}` (e.g., `test_init_without_redis`)

## Code Quality

### Python Standards

- Use Pydantic v2 `model_config` (not deprecated `class Config`)
- Use `datetime.now(timezone.utc)` (not deprecated `datetime.utcnow()`)
- Type hints on all function signatures
- Docstrings for modules, classes, and public methods
- AsyncMock for async method mocking

### Pull Request Requirements

1. All changes go through Pull Requests (never push directly to main)
2. Branch naming: `{type}/issue-{number}-{description}`
3. Reference issue in commit message: `feat: Description (#123)`
4. Tests must pass before merge
5. Only Serving can merge to main

### Git Hooks

- Pre-receive: Validates branch naming (`{type}/issue-{number}-...`)
- Post-receive: Updates PR queue status in Redis
- Branch protection: Compute instances can only push their own branches

## Domain-Specific Patterns

### Work Coordination

- WorkMap tracks goals and issues with dependencies
- Redis used for indexes and status tracking
- Git branches for state management (1 branch = 1 work unit)
- SSE for real-time event streaming

### Skill System

- Skills are YAML files with instructions for Claude Code
- Personas are pre-bundled skill combinations
- Marketplace is a separate service (port 8003)
- Skills compose via simple concatenation

### Compute Communication

- MCP tools for compute-to-serving communication
- SSE for serving-to-compute events
- Git worktrees for parallel branch access
- Registration via SSE connection
