# ClaudeVN Testing Guide

This guide covers the test structure and how to run tests for the ClaudeVN platform.

## Test Organization

Tests are organized into two tiers with clear directory separation:

```
project/
├── serving/tests/
│   ├── unit/           # Tier 1: Fast, mocked unit tests
│   └── integration/    # Tier 2: Require running server
├── marketplace/tests/
│   ├── unit/           # Tier 1: Fast, mocked unit tests
│   └── integration/    # Tier 2: Require running server
├── compute/tests/
│   ├── unit/           # Tier 1: Fast, mocked unit tests
│   └── integration/    # Tier 2: Require running server
├── shared/tests/       # Tier 1: Shared library tests
└── tests/              # Tier 2: System-level integration tests
```

### Tier 1: Unit Tests (`*/tests/unit/`)

- **Fast**: Run in seconds, no external dependencies
- **Mocked**: All external services are mocked
- **Isolated**: No network calls, no database, no Redis
- **Location**: `serving/tests/unit/`, `marketplace/tests/unit/`, `compute/tests/unit/`, `shared/tests/`

### Tier 2: Integration Tests (`*/tests/integration/`)

- **Slower**: Require running services
- **Real dependencies**: Test against actual Redis, HTTP endpoints
- **Prerequisites**: Running server, Redis, etc.
- **Location**: `serving/tests/integration/`, `marketplace/tests/integration/`, `compute/tests/integration/`, `tests/`

## Running Tests

### Tier 1: Unit Tests

```bash
# Run all unit tests
./scripts/run_unit_tests.sh

# Run with verbose output
./scripts/run_unit_tests.sh -v

# Run with coverage
./scripts/run_unit_tests.sh -c

# Run specific test file
./scripts/run_unit_tests.sh serving/tests/unit/test_models.py

# Stop on first failure
./scripts/run_unit_tests.sh -x
```

### Tier 2: Integration Tests

```bash
# Run integration tests (server must be running)
./scripts/run_integration_tests.sh

# Auto-start server and run tests
./scripts/run_integration_tests.sh -s

# Run with verbose output
./scripts/run_integration_tests.sh -s -v

# Run specific test file
./scripts/run_integration_tests.sh serving/tests/integration/test_api_integration.py
```

## Writing Tests

### Unit Test Guidelines

1. Place in `{service}/tests/unit/` directory
2. Mock all external dependencies (Redis, HTTP, file system)
3. Tests should run in isolation without any setup
4. Use `pytest.fixture` for common test setup

Example:
```python
# serving/tests/unit/test_my_service.py
import pytest
from unittest.mock import MagicMock, patch

from services.my_service import MyService

class TestMyService:
    @pytest.fixture
    def service(self):
        return MyService()

    def test_do_something(self, service):
        with patch('services.my_service.redis_client') as mock_redis:
            mock_redis.get.return_value = '{"key": "value"}'
            result = service.do_something()
            assert result == expected
```

### Integration Test Guidelines

1. Place in `{service}/tests/integration/` directory
2. Document prerequisites in docstring
3. Use real services (Redis, HTTP endpoints)
4. Clean up test data after each test

Example:
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

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_check(self):
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8002/health")
            assert response.status_code == 200
```

## Coverage

Generate coverage reports:

```bash
# Unit tests with coverage
./scripts/run_unit_tests.sh -c

# HTML report
./scripts/run_unit_tests.sh -h

# View HTML report
open htmlcov/index.html
```

## CI/CD Integration

In CI pipelines:

```yaml
# Run unit tests (no dependencies required)
- name: Unit Tests
  run: ./scripts/run_unit_tests.sh

# Run integration tests (requires services)
- name: Integration Tests
  run: |
    docker-compose up -d
    ./scripts/run_integration_tests.sh
    docker-compose down
```

## Troubleshooting

### Module Import Errors

If you see `ModuleNotFoundError`, ensure:
1. You're running from the project root
2. The test script sets up PYTHONPATH correctly
3. The `conftest.py` in the tests directory is present

### Test Discovery Issues

If tests aren't being discovered:
1. Ensure test files are named `test_*.py`
2. Ensure test functions are named `test_*`
3. Check that `__init__.py` is NOT present in `unit/` or `integration/` directories

### Path Issues After Moving Tests

If tests reference files with relative paths, update the path calculation:
```python
# Before (test was in tests/)
HOOK_PATH = Path(__file__).parent.parent / "git" / "hooks"

# After (test is in tests/unit/)
HOOK_PATH = Path(__file__).parent.parent.parent / "git" / "hooks"
```
