"""Request-scoped user context middleware.

Makes the authenticated user available via contextvars for any code
in the request lifecycle, without requiring explicit Depends() injection.
"""

from contextvars import ContextVar
from typing import Optional
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

from config import get_config

logger = logging.getLogger(__name__)

# Context variable for the current user - available anywhere in the request lifecycle
_current_user_var: ContextVar[Optional[dict]] = ContextVar('current_user', default=None)


def get_current_user() -> Optional[dict]:
    """Get the current authenticated user from request context.

    Returns a dict with at least 'sub' (user_id). May also contain
    'email', 'username', 'role', 'cognito:groups' depending on auth mode.

    Returns None if no authenticated user (unauthenticated request).
    """
    return _current_user_var.get(None)


def get_current_user_id() -> Optional[str]:
    """Get just the current user's ID from request context.

    Convenience wrapper around get_current_user().
    Returns None if no authenticated user.
    """
    user = _current_user_var.get(None)
    return user.get('sub') if user else None


class UserContextMiddleware(BaseHTTPMiddleware):
    """Middleware that extracts user identity and sets it in request context.

    Works with both Cognito JWT tokens and local user service tokens.
    Non-blocking: if no token or invalid token, request proceeds with user=None.

    Must be added AFTER CognitoAuthMiddleware in the middleware stack
    (which means it runs BEFORE CognitoAuthMiddleware on the request path,
    but that's fine since this middleware is non-blocking).
    """

    async def dispatch(self, request: Request, call_next):
        user = await self._extract_user(request)

        # Set on request.state for access via request object
        request.state.user = user

        # Set in contextvars for access anywhere in the call stack
        token = _current_user_var.set(user)
        try:
            response = await call_next(request)
            return response
        finally:
            _current_user_var.reset(token)

    async def _extract_user(self, request: Request) -> Optional[dict]:
        """Extract user from Bearer token, trying both auth systems."""
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            # Check bypass mode - provide dev user
            config = get_config().cognito
            if config.auth_mode == "bypass":
                return {
                    "sub": "bypass-dev-user",
                    "email": "dev@localhost",
                    "username": "dev",
                    "role": "admin",
                }
            return None

        token_str = auth_header[7:]
        config = get_config().cognito

        # Try Cognito first if in cognito mode
        if config.auth_mode == "cognito":
            try:
                from middleware.cognito_auth import _decode_cognito_token
                payload = _decode_cognito_token(token_str, config)
                return payload
            except Exception:
                pass

        # Try local user service token
        try:
            from services.user_service import get_user_service
            service = get_user_service()
            if service:
                user_id = service.verify_token(token_str)
                if user_id:
                    user = await service.get_user(user_id)
                    if user:
                        return {
                            "sub": user.user_id,
                            "email": user.email,
                            "username": user.username,
                            "role": user.role.value if user.role else None,
                        }
        except Exception as e:
            logger.debug("Local token verification failed: %s", e)

        return None
