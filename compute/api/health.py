"""Health check endpoints for Compute Infrastructure (v1.0)."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])


def _compute_health_status(sse_connected: bool, credentials_usable: bool) -> str:
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


@router.get("/health")
async def health_check():
    """Health check endpoint.

    Returns status of the compute infrastructure including credential health.
    Used by Docker health checks.
    """
    from services.claude_code_spawner import get_claude_code_spawner
    from services.sse_event_client import get_sse_event_client
    from services.credential_monitor import get_credential_monitor

    spawner = get_claude_code_spawner()
    sse_client = get_sse_event_client()
    cred_monitor = get_credential_monitor()

    # Check if SSE client is connected
    sse_connected = sse_client.is_connected if sse_client else False

    # Check credential health
    credentials_usable = cred_monitor.is_usable if cred_monitor else True
    cred_status = cred_monitor.get_status() if cred_monitor else None

    # Determine auth_status for serving's compute registry
    if cred_monitor and cred_monitor.is_usable:
        auth_status = "authorized"
    elif cred_monitor and cred_monitor.status.value == "expired":
        auth_status = "expired"
    else:
        auth_status = "unauthorized"

    response = {
        "status": _compute_health_status(sse_connected, credentials_usable),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "architecture": "v1.0",
        "sse_connected": sse_connected,
        "running_instances": spawner.get_status()["running_instances"] if spawner else 0,
        "auth_status": auth_status,
    }

    if cred_status:
        response["credentials"] = {
            "status": cred_status["status"],
            "valid": cred_status["credentials_valid"],
            "expires_at": cred_status["expires_at"],
            "last_check": cred_status["last_check"],
        }

    return response


@router.get("/stats")
async def get_stats():
    """Get detailed statistics."""
    from services.claude_code_spawner import get_claude_code_spawner
    from services.sse_event_client import get_sse_event_client
    from services.credential_monitor import get_credential_monitor

    spawner = get_claude_code_spawner()
    sse_client = get_sse_event_client()
    cred_monitor = get_credential_monitor()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spawner": spawner.get_status() if spawner else None,
        "sse_client": sse_client.get_status() if sse_client else None,
        "credentials": cred_monitor.get_status() if cred_monitor else None,
    }

