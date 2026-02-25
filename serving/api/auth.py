"""Authentication API router for Claude token-based credential management.

Provides REST endpoints for token lifecycle management:
- POST /auth/token         - Submit a token for a component
- GET  /auth/token/{id}    - Get auth status for a component
- DELETE /auth/token/{id}  - Revoke a token for a component
- GET  /auth/tokens        - List all component auth statuses
- GET  /auth/status        - System-level auth overview (auto-detects Redis imports)
- POST /auth/refresh       - Force reload credentials from Redis
- GET  /auth/credentials   - Raw credentials for compute (authenticated)
"""

from fastapi import APIRouter, HTTPException
from models.auth import (
    TokenSubmitRequest,
    TokenInfoResponse,
    TokenListResponse,
    SystemAuthStatusResponse,
)
from services.claude_auth_service import get_claude_auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


def _get_service():
    """Get the auth service or raise 503."""
    service = get_claude_auth_service()
    if service is None:
        raise HTTPException(status_code=503, detail="Auth service not enabled")
    return service


@router.get("/status")
async def get_auth_status():
    """System-level auth overview.

    Returns 404 if auth service is disabled (frontend skips auth gate).
    Returns counts of authorized/unauthorized compute instances and
    whether serving itself is authorized.
    """
    service = get_claude_auth_service()
    if service is None:
        raise HTTPException(status_code=404, detail="Auth service not enabled")

    system_status = service.get_system_auth_status()
    # Also include legacy fields for backward compatibility
    basic_status = await service.get_status()
    return {**basic_status, **system_status}


@router.post("/refresh")
async def refresh_from_redis():
    """Force reload credentials from Redis.

    Useful after importing credentials externally (e.g. via import-credentials.py)
    or for manual recovery without restarting the service.
    """
    service = _get_service()
    result = await service.refresh_from_redis()
    return result


@router.post("/token")
async def submit_token(body: TokenSubmitRequest):
    """Submit an API token for storage.

    Users obtain tokens via `claude setup-token` on any machine with a
    browser, then paste the token here. Validates format and stores in Redis.
    """
    service = _get_service()
    result = await service.store_token(
        token=body.token,
        component_id=body.component_id,
        component_type=body.component_type,
    )
    return result


@router.get("/token/{component_id}", response_model=TokenInfoResponse)
async def get_token_info(component_id: str):
    """Get auth status for a specific component.

    Does NOT return the raw token (security). Returns status, timestamps,
    and component type.
    """
    service = _get_service()
    info = service.get_token_info(component_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"No token found for component: {component_id}")
    return info


@router.delete("/token/{component_id}")
async def revoke_token(component_id: str):
    """Revoke a token for a component.

    Marks the token as revoked and removes it from storage.
    """
    service = _get_service()
    revoked = await service.clear_credentials(component_id=component_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"No token found for component: {component_id}")
    return {"revoked": True}


@router.get("/tokens", response_model=TokenListResponse)
async def list_tokens():
    """List auth status for all components.

    Returns metadata for all stored tokens. Raw token values are
    never exposed.
    """
    service = _get_service()
    items = service.list_tokens()
    return {"items": items}


@router.get("/credentials")
async def get_credentials():
    """Get raw credentials for compute instances.

    Unauthenticated: compute instances call this during initial startup
    (before registration) to obtain Claude OAuth credentials. Access is
    restricted to the internal Docker network.
    Returns 503 if no credentials are available.
    """
    service = _get_service()
    creds = await service.get_credentials()
    if not creds:
        raise HTTPException(status_code=503, detail="No credentials available")

    status = await service.get_status()
    return {"credentials": creds, "expires_at": status.get("expires_at")}
