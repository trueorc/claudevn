"""Cognito user management API endpoints.

Provides admin endpoints for inviting, listing, and removing users
from the Cognito User Pool. Requires COGNITO_ADMIN_ENABLED=true.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from config import get_config
from services import cognito_user_service

router = APIRouter(prefix="/cognito-users", tags=["cognito-users"])


class InviteRequest(BaseModel):
    email: str


class InviteResponse(BaseModel):
    email: str
    status: str
    created: str


class UserListResponse(BaseModel):
    users: list[dict]


class ResendResponse(BaseModel):
    username: str
    status: str


def _check_admin_enabled():
    """Raise 404 if Cognito admin endpoints are disabled."""
    config = get_config().cognito
    if config.auth_mode == "bypass":
        raise HTTPException(
            status_code=404,
            detail="User management is not available in bypass mode",
        )
    if not config.admin_enabled:
        raise HTTPException(
            status_code=404,
            detail="Cognito admin endpoints are disabled (set COGNITO_ADMIN_ENABLED=true)",
        )


@router.post("/invite", response_model=InviteResponse)
async def invite_user(body: InviteRequest):
    """Invite a new user by email. Sends Cognito invitation with temporary password."""
    _check_admin_enabled()
    try:
        result = await cognito_user_service.invite_user(body.email)
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invite user: {e}")


@router.get("", response_model=UserListResponse)
async def list_users():
    """List all users in the Cognito User Pool."""
    _check_admin_enabled()
    try:
        users = await cognito_user_service.list_users()
        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list users: {e}")


@router.delete("/{username}")
async def remove_user(username: str):
    """Remove a user from the Cognito User Pool."""
    _check_admin_enabled()
    try:
        removed = await cognito_user_service.remove_user(username)
        if not removed:
            raise HTTPException(status_code=404, detail=f"User {username} not found")
        return {"removed": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove user: {e}")


@router.post("/{username}/resend-invite", response_model=ResendResponse)
async def resend_invite(username: str):
    """Resend invitation email for a user with expired temporary password."""
    _check_admin_enabled()
    try:
        result = await cognito_user_service.resend_invite(username)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resend invite: {e}")
