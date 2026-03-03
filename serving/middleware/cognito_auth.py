"""Cognito JWT verification for FastAPI.

Provides a dependency function that verifies AWS Cognito access tokens
on UI-facing API routes. Supports bypass mode for local development.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import CognitoConfig, get_config

logger = logging.getLogger(__name__)

# Lazy-loaded PyJWKClient (only when cognito mode is active)
_jwk_client = None
_jwt_module = None

# HTTPBearer scheme - auto_error=False so we handle missing tokens ourselves
_bearer_scheme = HTTPBearer(auto_error=False)

# Hardcoded dev user payload for bypass mode
BYPASS_USER = {
    "sub": "bypass-dev-user",
    "email": "dev@localhost",
    "cognito:groups": ["admin"],
}


def _get_jwk_client(config: CognitoConfig):
    """Get or create the PyJWKClient for JWKS key caching."""
    global _jwk_client, _jwt_module
    if _jwk_client is None:
        import jwt as pyjwt
        from jwt import PyJWKClient

        _jwt_module = pyjwt
        jwks_url = (
            f"https://cognito-idp.{config.region}.amazonaws.com"
            f"/{config.user_pool_id}/.well-known/jwks.json"
        )
        _jwk_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwk_client


def _decode_cognito_token(token: str, config: CognitoConfig) -> dict:
    """Decode and verify a Cognito access token.

    Verifies:
    - Signature (RS256 via JWKS)
    - Issuer (must match Cognito User Pool)
    - Token use (must be 'access')
    - Expiration

    Returns the decoded token payload.
    """
    client = _get_jwk_client(config)
    signing_key = client.get_signing_key_from_jwt(token)

    issuer = (
        f"https://cognito-idp.{config.region}.amazonaws.com"
        f"/{config.user_pool_id}"
    )

    payload = _jwt_module.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=issuer,
        options={
            "verify_aud": False,  # Cognito access tokens don't have 'aud'
            "verify_exp": True,
        },
    )

    # Cognito access tokens use 'client_id' not 'aud', and 'token_use' = 'access'
    if payload.get("token_use") != "access":
        raise ValueError("Token is not an access token")

    if payload.get("client_id") != config.app_client_id:
        raise ValueError("Token client_id does not match app client")

    return payload


async def verify_cognito_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency to verify Cognito JWT tokens.

    In bypass mode, returns a hardcoded dev user.
    In cognito mode, verifies the Bearer token and returns the decoded payload.

    Returns:
        Dict with at least: sub, email, cognito:groups
    """
    config = get_config().cognito

    # Bypass mode - no auth required
    if config.auth_mode == "bypass":
        return BYPASS_USER

    # Cognito mode - require valid token
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = _decode_cognito_token(credentials.credentials, config)
        return payload
    except Exception as e:
        logger.debug("Token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_current_user(
    token_payload: dict = Depends(verify_cognito_token),
) -> dict:
    """Convenience dependency for downstream routes.

    Returns the verified token payload (sub, email, groups).
    """
    return token_payload


def reset_jwk_client():
    """Reset the cached JWK client (for testing)."""
    global _jwk_client, _jwt_module
    _jwk_client = None
    _jwt_module = None
