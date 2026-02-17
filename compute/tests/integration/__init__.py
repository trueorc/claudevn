"""Integration tests for compute ↔ serving communication.

These are Tier 2 integration tests that require running services:
- Serving at http://localhost:8002
- Optionally Redis if required by serving

Run with:
    ./scripts/run_integration_tests.sh -s compute/tests/integration/

Or with docker:
    docker-compose up -d
    pytest compute/tests/integration/ -v --run-integration
"""
