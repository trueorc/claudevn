"""Health check utilities for Compute Infrastructure (v1.0).

Provides health status logic used by the heartbeat file mechanism.
No HTTP endpoints — compute has no HTTP server.
"""

import logging

logger = logging.getLogger(__name__)


def compute_health_status(sse_connected: bool, credentials_usable: bool) -> str:
    """Determine overall health status.

    Args:
        sse_connected: Whether SSE connection to Serving is active
        credentials_usable: Whether credentials are valid or expiring

    Returns:
        Health status string: healthy, degraded, or unhealthy
    """
    if sse_connected and credentials_usable:
        return "healthy"
    if not sse_connected and not credentials_usable:
        return "unhealthy"
    return "degraded"
