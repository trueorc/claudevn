"""Authentication models for Claude token-based credential management."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


class AuthStatus(str, Enum):
    """Claude authentication status."""
    NOT_CONFIGURED = "not_configured"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    ERROR = "error"


class TokenStatus(str, Enum):
    """Token lifecycle status in Redis."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AuthStatusResponse(BaseModel):
    """Response for auth status endpoint."""
    status: AuthStatus
    authenticated: bool
    expires_at: Optional[str] = None
    message: Optional[str] = None


class TokenSubmitRequest(BaseModel):
    """Request to submit a Claude API token."""
    token: str
    component_id: str = "serving"
    component_type: str = "serving"

    @field_validator("token")
    @classmethod
    def validate_token_format(cls, v: str) -> str:
        if not v.startswith("sk-ant-oat01-"):
            raise ValueError("Token must start with 'sk-ant-oat01-'")
        return v


class TokenSubmitResponse(BaseModel):
    """Response for token submission."""
    status: AuthStatus
    message: str
    expires_at: Optional[str] = None


class CredentialsResponse(BaseModel):
    """Response for credentials endpoint."""
    credentials: dict
    expires_at: Optional[str] = None


class TokenInfoResponse(BaseModel):
    """Response for token info endpoint (no raw token exposed)."""
    component_id: str
    status: str
    authorized_at: Optional[str] = None
    expires_at: Optional[str] = None
    component_type: str = "serving"


class TokenListResponse(BaseModel):
    """Response for listing all token statuses."""
    items: list[TokenInfoResponse]


class SystemAuthStatusResponse(BaseModel):
    """System-level auth overview."""
    serving_authorized: bool
    compute_authorized: int = 0
    compute_unauthorized: int = 0
    tokens_expiring_soon: int = 0
