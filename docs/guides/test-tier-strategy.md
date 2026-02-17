# Test Tier Strategy

**Version**: 2.0.0
**Last Updated**: February 2026
**Audience**: All developers and compute agents

---

## Overview

ClaudeVN uses a two-tier test strategy with clear directory separation to balance fast feedback during development with comprehensive validation before deployment.

| Tier | Type | Speed | Server Required | When to Run |
|------|------|-------|-----------------|-------------|
| **Tier 1** | Unit tests | Fast (~seconds) | No | Every code change |
| **Tier 2** | Integration tests | Slow (~minutes) | Yes | Before merge, CI/CD |

---

## Test Directory Structure

Tests are organized by tier in separate directories:

```
project/
├── serving/tests/
│   ├── unit/           # Tier 1: Fast, mocked unit tests
│   ├── integration/    # Tier 2: Require running server
│   └── conftest.py     # Shared fixtures
├── marketplace/tests/
│   ├── unit/           # Tier 1: Fast, mocked unit tests
│   ├── integration/    # Tier 2: Require running server
│   └── conftest.py     # Shared fixtures
├── compute/tests/
│   ├── unit/           # Tier 1: Fast, mocked unit tests
│   ├── integration/    # Tier 2: Require running server
│   └── conftest.py     # Shared fixtures
├── shared/tests/       # Tier 1: Shared library tests
└── tests/              # Tier 2: System-level integration tests
```

---

## Tier 1: Unit Tests

**Purpose**: Fast feedback loop during development.

**Location**: `{service}/tests/unit/`

### Characteristics
- **Isolated**: Tests run without external dependencies
- **Mocked**: External services, databases, and APIs are mocked
- **Fast**: Full suite completes in seconds
- **Deterministic**: No flaky tests, no network dependencies

### When to Run
- After every code change
- Before every commit
- Before pushing PR

### How to Run

```bash
# Run all Tier 1 unit tests
./scripts/run_unit_tests.sh

# Run specific test file
./scripts/run_unit_tests.sh serving/tests/unit/test_models.py

# With verbose output
./scripts/run_unit_tests.sh -v

# With coverage report
./scripts/run_unit_tests.sh -c

# With HTML coverage report
./scripts/run_unit_tests.sh -h

# Fail fast (stop on first failure)
./scripts/run_unit_tests.sh -x
```

### Writing Tier 1 Tests

```python
# serving/tests/unit/test_example.py
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestFeatureCreate:
    """Unit tests for feature creation."""

    @pytest.fixture
    def mock_service(self):
        """Mock the external service."""
        service = MagicMock()
        service.create = AsyncMock(return_value={"id": "123"})
        return service

    @pytest.mark.asyncio
    async def test_creates_feature_successfully(self, mock_service):
        """Test happy path for feature creation."""
        result = await mock_service.create(name="test")
        assert result["id"] == "123"
        mock_service.create.assert_called_once_with(name="test")

    @pytest.mark.asyncio
    async def test_handles_validation_error(self, mock_service):
        """Test error handling for invalid input."""
        mock_service.create.side_effect = ValueError("Invalid name")
        with pytest.raises(ValueError):
            await mock_service.create(name="")
```

---

## Tier 2: Integration Tests

**Purpose**: Validate component interactions and real API behavior.

**Location**: `{service}/tests/integration/` and `tests/` (system-level)

### Characteristics
- **Real dependencies**: Tests against running services
- **Server required**: Needs the ClaudeVN server running
- **Slower**: Takes minutes, not seconds
- **Comprehensive**: Tests real HTTP calls, database operations

### When to Run
- Before merging to main
- In CI/CD pipeline
- When testing API contracts

### How to Run

```bash
# Run with server already running
./scripts/run_integration_tests.sh

# Auto-start server before tests
./scripts/run_integration_tests.sh -s

# With verbose output
./scripts/run_integration_tests.sh -v

# With coverage
./scripts/run_integration_tests.sh -c
```

### Prerequisites
- Server running at `http://127.0.0.1:8002`
- Redis running (if required by server)

### Writing Tier 2 Tests

```python
# serving/tests/integration/test_api.py
"""
Integration tests for API endpoints.

Prerequisites:
- Running serving instance at http://localhost:8002
- Running Redis instance

Run with: ./scripts/run_integration_tests.sh
"""
import pytest
import httpx

class TestAPIEndpoints:
    """Integration tests for API endpoints."""

    @pytest.fixture
    def client(self):
        """Create HTTP client for API calls."""
        return httpx.AsyncClient(base_url="http://127.0.0.1:8002")

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Test health check returns 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_skill_via_api(self, client):
        """Test creating a skill through the real API."""
        response = await client.post("/api/v1/skills", json={
            "id": "test-skill",
            "name": "Test Skill",
            "description": "A test skill",
            "instructions": "Do testing things"
        })
        assert response.status_code == 201
```

---

## Workflow for Feature Development

### During Development (Tier 1 Only)

```bash
# 1. Create isolated worktree
git worktree add /workspace/issue-123 -b feat/issue-123-new-feature origin/main
cd /workspace/issue-123

# 2. Write code and tests
# ... implement feature ...
# ... write unit tests in {service}/tests/unit/ ...

# 3. Run Tier 1 tests frequently
./scripts/run_unit_tests.sh -v

# 4. Before committing
./scripts/run_unit_tests.sh

# 5. Create PR
git push -u origin feat/issue-123-new-feature
gh pr create ...
```

### Creating Follow-up Issue for Tier 2 Tests

If your feature needs integration tests, create a separate issue:

```bash
gh issue create \
  --title "[P2] Add integration tests for {feature}" \
  --body "Add Tier 2 integration tests for the feature implemented in #123.

## Tests Needed
- [ ] Test API endpoint responds correctly
- [ ] Test database persistence
- [ ] Test error handling with real services

## Related
- Implements testing for #123" \
  --label "test" \
  --label "P2" \
  --label "area:serving"
```

---

## Test Scripts Reference

| Script | Purpose | Speed |
|--------|---------|-------|
| `./scripts/run_unit_tests.sh` | Tier 1 unit tests | Fast |
| `./scripts/run_integration_tests.sh` | Tier 2 integration tests | Slow |

### Script Options

Both scripts support:
- `-v, --verbose` - Verbose output
- `-c, --coverage` - Enable coverage reporting
- `-h, --html` - Generate HTML coverage report
- `-x, --fail-fast` - Stop on first failure
- `-i, --install` - Install test dependencies

Integration script additionally supports:
- `-s, --start-server` - Auto-start server before tests

---

## CI/CD Integration

In CI/CD pipelines:

```yaml
# .github/workflows/test.yml
jobs:
  tier1-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Tier 1 Unit Tests
        run: ./scripts/run_unit_tests.sh -c

  tier2-integration-tests:
    runs-on: ubuntu-latest
    needs: tier1-unit-tests  # Only run if Tier 1 passes
    steps:
      - uses: actions/checkout@v4
      - name: Start services
        run: docker-compose up -d
      - name: Run Tier 2 Integration Tests
        run: ./scripts/run_integration_tests.sh -c
```

---

## Best Practices

### DO
- Run Tier 1 tests before every commit
- Write unit tests for new features in `tests/unit/`
- Write integration tests in `tests/integration/`
- Mock external dependencies in Tier 1 tests
- Create separate issues for Tier 2 tests
- Keep Tier 1 tests fast (< 1 second per test)

### DON'T
- Skip Tier 1 tests to save time
- Mix unit and integration tests in the same directory
- Require a running server for Tier 1 tests
- Run Tier 2 tests during active development
- Block PRs for missing Tier 2 tests (create follow-up issue instead)
- Add `__init__.py` to `unit/` or `integration/` directories (causes import issues)

---

## Related Documentation

- [Testing Guide](./testing.md)
- [Worktree Workflow Guide](./worktree-workflow.md)
- [Code Issue Workflow](../../.claude/commands/code-issue.md)
