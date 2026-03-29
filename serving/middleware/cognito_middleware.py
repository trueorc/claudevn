"""Authentication middleware for FastAPI.

Applies token verification to all UI-facing API routes,
while allowing public routes (health, compute SSE, MCP, auth credentials)
to pass through without authentication.

Supports three auth modes:
- cognito: Verifies Cognito JWT tokens
- local: Verifies HMAC tokens issued by the local user service
- bypass: No auth checks (development only)
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
    "/api/v1/compute/connect",       # SSE registration (approval workflow gates access)
    "/api/v1/compute/register",      # Compute registration (starts in PENDING status)
    "/api/v1/compute/refresh-credentials",  # Compute credential refresh
    "/api/v1/compute/events",        # Compute event callbacks (verified by compute registry)
    "/api/v1/compute/decomposition/", # Decomposition result submission
    "/api/v1/compute/characterization/", # Characterization result submission
    "/api/v1/mcp/",                  # MCP tools (uses API key auth)
    "/api/v1/auth/credentials",      # Compute credential fetching
    "/api/v1/auth/token",            # Claude token management (internal)
    "/api/v1/auth/cognito-config",   # Frontend Cognito config (needed before auth)
    "/api/v1/auth/status",           # Auth status check
    "/api/v1/marketplaces/register",  # Marketplace registration
    "/api/v1/marketplaces/marketplace-",  # Marketplace heartbeat/status (service-to-service)
    "/api/v1/users/login",           # User login (local auth mode)
    "/api/v1/users/register",        # User registration (local auth mode)
    "/api/v1/releases",              # Release notes (public, non-sensitive)
    "/api/v1/events/stream",         # SSE event stream (EventSource can't set auth headers)
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
    """Middleware that enforces token auth on UI-facing API routes.

    In bypass mode, all requests pass through.
    In cognito mode, non-public routes require a valid Cognito JWT.
    In local mode, non-public routes require a valid HMAC token
    (issued by the local user service at login).
    """

    def __init__(self, app):
        super().__init__(app)
        config = get_config().cognito
        if config.auth_mode == "bypass":
            logger.warning(
                "AUTH_MODE=bypass: All API requests will be treated as authenticated. "
                "Set AUTH_MODE=cognito for production."
            )
        elif config.auth_mode == "local":
            logger.warning(
                "AUTH_MODE=local: Using local file-based auth. "
                "NOT for production use."
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

        # Both cognito and local modes require a Bearer token
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Strip "Bearer "

        if config.auth_mode == "local":
            # Local mode - verify HMAC token from user service
            from services.user_service import get_user_service
            service = get_user_service()
            if not service or not service.verify_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            # Cognito mode - verify JWT
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
