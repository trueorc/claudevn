"""User registration and authentication API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from models.user import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UpdateProfileRequest,
    UserProfileResponse,
    UserRole,
)
from services.user_service import get_user_service

router = APIRouter(prefix="/users", tags=["users"])

_bearer_scheme = HTTPBearer(auto_error=False)


def _is_bypass_mode() -> bool:
    """Check if running in bypass auth mode."""
    try:
        from config import get_config
        return get_config().cognito.auth_mode == "bypass"
    except Exception:
        return False


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """Extract and verify user from Bearer token.

    In bypass mode, returns a dev user ID without requiring a token.

    Returns:
        user_id string

    Raises:
        HTTPException 401: Missing or invalid token (non-bypass mode)
    """
    # Bypass mode — no token required, return dev user
    if _is_bypass_mode():
        if credentials:
            service = get_user_service()
            if service:
                user_id = service.verify_token(credentials.credentials)
                if user_id:
                    return user_id
        return "bypass-dev-user"

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    service = get_user_service()
    if not service:
        raise HTTPException(status_code=503, detail="User service not available")

    user_id = service.verify_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


async def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[str]:
    """Extract user from Bearer token, returning None if missing."""
    if _is_bypass_mode() and not credentials:
        return "bypass-dev-user"

    if not credentials:
        return None

    service = get_user_service()
    if not service:
        return None

    return service.verify_token(credentials.credentials)


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest):
    """Register a new user account.

    First registered user automatically gets the owner role.
    """
    service = get_user_service()
    if not service:
        raise HTTPException(status_code=503, detail="User service not available")

    try:
        user, token = await service.register(
            username=body.username,
            email=body.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return RegisterResponse(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        token=token,
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Log in with a username."""
    service = get_user_service()
    if not service:
        raise HTTPException(status_code=503, detail="User service not available")

    try:
        user, token = await service.login(username=body.username, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return LoginResponse(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        token=token,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """Get current user profile."""
    service = get_user_service()
    if not service:
        raise HTTPException(status_code=503, detail="User service not available")

    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfileResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.put("/me", response_model=UserProfileResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update current user profile."""
    service = get_user_service()
    if not service:
        raise HTTPException(status_code=503, detail="User service not available")

    try:
        user = await service.update_user(
            user_id=user_id,
            username=body.username,
            email=body.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfileResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        last_login=user.last_login,
    )
