# Development and Test Scripts

This directory contains all operational scripts for the ClaudeVN platform.

## Development Scripts

### `setup_environment.sh`
Initial setup - installs all Python dependencies for all components.

```bash
./setup_environment.sh
```

### `start_all.sh`
Start complete development environment with all services.

**Features**:
- Resilient - handles already running services
- Checks and frees ports automatically
- Installs missing dependencies
- Shows health status for all services
- Optional live log viewing

```bash
./start_all.sh
```

### `stop_all.sh`
Stop all ClaudeVN services gracefully.

```bash
./stop_all.sh
```

### `status.sh`
Check status of all services.

```bash
./status.sh
```

**Output**:
- Service status (running/stopped)
- Port and PID information
- Health check results
- Marketplace statistics
- Log locations

---

## Test Scripts

### `run_all_tests.sh`
Run complete test suite across all components.

```bash
./run_all_tests.sh
```

### `test_mock_e2e.sh`
End-to-end test with mock LLM provider.

```bash
./test_mock_e2e.sh
```

### `test_pipeline_e2e.sh`
Test pipeline execution workflow.

```bash
./test_pipeline_e2e.sh
```

### `test_real_ai.sh`
Test with real LLM providers (requires API keys).

```bash
./test_real_ai.sh
```

### `test_observability.sh`
Test real-time observability features.

```bash
./test_observability.sh
```

### `test_serving_ui.sh`
Test serving component UI functionality.

```bash
./test_serving_ui.sh
```

---

## Working Directory

All scripts should be executed from the project root directory:

```bash
cd /path/to/claudevn
./docs/scripts/start_all.sh
```

---

## Related Documentation

- [FUNCTIONAL_REQUIREMENTS.md](../../FUNCTIONAL_REQUIREMENTS.md) - What the system does
- [TECHNICAL_DECISIONS.md](../../TECHNICAL_DECISIONS.md) - How it's built
- [README.md](../../README.md) - Quick start guide
