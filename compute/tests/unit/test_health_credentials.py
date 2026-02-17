"""Unit tests for health endpoint with credential status (issue #538)."""

import pytest
from unittest.mock import MagicMock, patch

from api.health import _compute_health_status


class TestComputeHealthStatus:
    """Tests for _compute_health_status helper."""

    def test_healthy_when_both_good(self):
        """Status is healthy when SSE connected and credentials usable."""
        assert _compute_health_status(sse_connected=True, credentials_usable=True) == "healthy"

    def test_degraded_when_sse_disconnected(self):
        """Status is degraded when only SSE is down."""
        assert _compute_health_status(sse_connected=False, credentials_usable=True) == "degraded"

    def test_degraded_when_credentials_bad(self):
        """Status is degraded when only credentials are bad."""
        assert _compute_health_status(sse_connected=True, credentials_usable=False) == "degraded"

    def test_unhealthy_when_both_bad(self):
        """Status is unhealthy when both SSE and credentials are down."""
        assert _compute_health_status(sse_connected=False, credentials_usable=False) == "unhealthy"
