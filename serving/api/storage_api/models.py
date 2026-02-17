"""Pydantic models for storage API endpoints."""

from typing import Optional
from pydantic import BaseModel


class BlobUploadResponse(BaseModel):
    """Response from blob upload."""
    blob_id: str
    url: str
    size: int
    mime_type: str
    expires_at: Optional[str] = None


class BlobMetadataResponse(BaseModel):
    """Blob metadata response."""
    blob_id: str
    size: int
    mime_type: str
    created_at: str
    expires_at: Optional[str] = None
    session_id: Optional[str] = None
    filename: Optional[str] = None


class StorageStatsResponse(BaseModel):
    """Storage statistics response."""
    backend: str
    total_size: int
    blob_count: int
    expired_count: int

