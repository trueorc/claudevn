"""Pytest configuration for compute integration tests.

This configures Tier 2 integration tests that require running services.
"""

import os
import pytest


def pytest_addoption(parser):
    """Add --run-integration option for integration tests."""
    try:
        parser.addoption(
            "--run-integration",
            action="store_true",
            default=False,
            help="run integration tests"
        )
    except ValueError:
        # Option already added by parent conftest
        pass


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires running server)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration is passed."""
    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Integration tests require --run-integration flag"
        )
        for item in items:
            if "integration" in item.keywords or "integration" in str(item.fspath):
                item.add_marker(skip_integration)


@pytest.fixture(scope="session")
def serving_url():
    """Get the serving URL from environment or use default."""
    return os.getenv("SERVING_URL", "http://localhost:8002")


@pytest.fixture(scope="session")
def api_prefix():
    """Get the API prefix."""
    return "/api/v1"
