"""Cognito JWT middleware for FastAPI.

Applies Cognito token verification to all UI-facing API routes,
while allowing public routes (health, compute SSE, MCP, auth credentials)
to pass through without authentication.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request

from config import get_config

logger = logging.getLogger(__name__)

# Routes that must remain public (no Cognito auth required).
# These use their own auth mechanisms (compute registration token, MCP API key, etc.)
PUBLIC_PATH_PREFIXES = (
    "/api/v1/health",
    "/api/v1/compute/connect",       # SSE registration (uses compute auth)
    "/api/v1/compute/register",      # Compute registration (uses compute token)
    "/api/v1/compute/refresh-credentials",  # Compute credential refresh
    "/api/v1/mcp/",                  # MCP tools (uses API key auth)
    "/api/v1/auth/credentials",      # Compute credential fetching
    "/api/v1/auth/token",            # Claude token management (internal)
    "/api/v1/auth/cognito-config",   # Frontend Cognito config (needed before auth)
    "/api/v1/auth/status",           # Auth status check
    "/api/v1/marketplace/register",  # Marketplace registration
)

# Non-API routes that are always public
PUBLIC_EXACT_PATHS = (
    "/health",
    "/api/v1/health",
)

# Paths outside /api/v1/ are not gated (frontend static files, etc.)
API_PREFIX = "/api/v1/"


def _is_public_route(path: str) -> bool:
    """Check if a request path is public (no Cognito auth needed)."""
    if path in PUBLIC_EXACT_PATHS:
        return True

    # Only gate /api/v1/ routes
    if not path.startswith(API_PREFIX):
        return True

    for prefix in PUBLIC_PATH_PREFIXES:
        if path.startswith(prefix):
            return True

    return False


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces Cognito JWT auth on UI-facing API routes.

    In bypass mode, all requests pass through.
    In cognito mode, non-public routes require a valid Bearer token.
    """

    def __init__(self, app):
        super().__init__(app)
        config = get_config().cognito
        if config.auth_mode == "bypass":
            logger.warning(
                "AUTH_MODE=bypass: All API requests will be treated as authenticated. "
                "Set AUTH_MODE=cognito for production."
            )
        else:
            logger.info("Cognito auth enabled for UI API routes")

    async def dispatch(self, request: Request, call_next):
        config = get_config().cognito

        # Bypass mode - no auth checks
        if config.auth_mode == "bypass":
            return await call_next(request)

        # Public routes - no auth needed
        if _is_public_route(request.url.path):
            return await call_next(request)

        # Cognito mode - verify Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Strip "Bearer "
        try:
            from middleware.cognito_auth import _decode_cognito_token
            _decode_cognito_token(token, config)
        except Exception as e:
            logger.debug("Middleware token verification failed: %s", e)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
