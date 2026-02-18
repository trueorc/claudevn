# Contributing to ClaudeVN

Thank you for your interest in contributing to ClaudeVN! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Contributor License Agreement](#contributor-license-agreement)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Running the Project](#running-the-project)
- [Running Tests](#running-tests)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Reporting Issues](#reporting-issues)
- [License](#license)

## Code of Conduct

We expect all contributors to be respectful and constructive. Harassment, discrimination, and disruptive behavior will not be tolerated.

## Contributor License Agreement

All contributions require signing our [Contributor License Agreement](CLA.md). This enables dual licensing: the project is publicly available under AGPL-3.0, but the maintainer may offer alternative commercial licenses. By submitting a pull request, you agree to the CLA terms.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a feature branch from `main`
5. Make your changes
6. Submit a pull request

## Development Environment

### Prerequisites

- **Python 3.10+**
- **Node.js** (for the frontend)
- **Redis** (for state management)
- **Git**
- **Docker & Docker Compose** (optional, for running everything together)

### Setup

```bash
# Clone the repository
git clone https://github.com/trueorc/claudevn.git
cd claudevn

# Create a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r serving/requirements.txt
pip install -r marketplace/requirements.txt

# Install test dependencies
./scripts/run_unit_tests.sh --install

# Install frontend dependencies
cd serving/frontend
npm install
cd ../..
```

## Running the Project

### With Docker Compose

```bash
docker compose up
```

The coordination hub will be available at `http://localhost:8002`.

### Without Docker

Start each component separately:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Start Redis (must be running)
redis-server

# Start the serving hub (port 8002)
cd serving && uvicorn main:app --reload --port 8002

# Start the marketplace (port 8003)
cd marketplace && uvicorn main:app --reload --port 8003

# Start the frontend dev server
cd serving/frontend && npm start
```

## Running Tests

### Tier 1: Unit Tests (fast, mocked, no server required)

```bash
# Run all unit tests
./scripts/run_unit_tests.sh

# Run with verbose output
./scripts/run_unit_tests.sh -v

# Run with coverage
./scripts/run_unit_tests.sh -c

# Run a specific test file
./scripts/run_unit_tests.sh serving/tests/unit/test_models.py

# Stop on first failure
./scripts/run_unit_tests.sh -x
```

### Tier 2: Integration Tests (requires running services)

```bash
./scripts/run_integration_tests.sh
```

### Frontend Tests

```bash
cd serving/frontend
npm test
```

All pull requests must pass Tier 1 unit tests before being merged.

## Making Changes

### Branch Naming

Use the following prefixes based on the type of change:

| Prefix | Use For |
|--------|---------|
| `feat/` | New features and enhancements |
| `fix/` | Bug fixes |
| `docs/` | Documentation changes |
| `test/` | Test additions or changes |
| `refactor/` | Code refactoring |

Examples:
- `feat/issue-42-user-auth`
- `fix/issue-99-race-condition`
- `docs/issue-50-api-guide`

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>: <description> (#<issue-number>)
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

Examples:
- `feat: Add user authentication endpoint (#42)`
- `fix: Correct race condition in event handler (#99)`
- `docs: Update API reference for backlog endpoints (#50)`

### Pull Request Process

1. **All code changes go through pull requests** - never push directly to `main`.
2. Create your branch from `main`.
3. Write or update unit tests for your changes.
4. Ensure all Tier 1 unit tests pass (`./scripts/run_unit_tests.sh`).
5. Write a clear PR description with:
   - Summary of changes
   - Link to the related issue (`Closes #N`)
   - Testing checklist
6. Request a review from a maintainer.

### PR Description Template

```markdown
## Summary
- Brief description of changes

## Changes
- List of specific changes made

## Testing
- [ ] Tier 1 unit tests added/updated
- [ ] All Tier 1 unit tests passing

## Issue
Closes #N
```

## Code Style

### Python (Serving, Marketplace, Compute)

- **Models**: Pydantic v2 models in `{component}/models/{domain}.py`
- **Services**: Singleton pattern in `{component}/services/{domain}_service.py`
- **API routes**: FastAPI routers in `{component}/api/{domain}.py`
- Use `datetime.now(timezone.utc)` instead of `datetime.utcnow()`
- Use `async`/`await` for asynchronous operations
- Use type hints for function parameters and return values

### JavaScript/React (Frontend)

- Use `.jsx` extension for React components
- Functional components with hooks (no class components)
- Components in `serving/frontend/src/components/{domain}/`
- CSS co-located as `{ComponentName}.css`
- Hooks in `serving/frontend/src/hooks/use{Feature}.js`
- API clients in `serving/frontend/src/api/{domain}.js`

### Test Conventions

- **Python unit tests**: `{component}/tests/unit/test_{module}.py`
- Group tests in classes by feature (`TestFeatureInit`, `TestFeatureCreate`)
- Use `@pytest.mark.asyncio` for async tests
- Use `AsyncMock` for mocking async methods
- **Frontend tests**: Co-located with components using Jest

## Reporting Issues

When creating an issue, include:

1. **Title**: `[PRIORITY] Brief description` (e.g., `[P2] Fix login timeout`)
2. **Labels**:
   - Priority: `P0` (critical), `P1` (high), `P2` (medium), `P3` (low)
   - Type: `bug`, `enhancement`, or `documentation`
   - Area: `area:serving`, `area:compute`, `area:marketplace`, `area:git`, `area:mcp`, `area:frontend`
3. **Description**: Clear steps to reproduce (for bugs) or detailed requirements (for features)

## License

ClaudeVN is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE). By contributing, you agree that your contributions will be licensed under the same license, subject to the terms of the [CLA](CLA.md).
