"""Root pytest configuration for ClaudeVN tests."""

import pytest


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test (requires running server)"
    )
