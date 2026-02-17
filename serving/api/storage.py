"""Blob storage API endpoints for the Serving Component."""

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from storage import StorageBackend, BlobNotFoundError, StorageError, StorageLimitError


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/storage", tags=["storage"])


# Dependency to get storage backend (will be injected by main app)
def get_storage() -> StorageBackend:
    """Get storage backend instance.
    
    This should be overridden by the main app to provide the actual storage backend.
    """
    raise NotImplementedError("Storage backend not configured")


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


@router.post("/upload", response_model=BlobUploadResponse)
async def upload_blob(
    file: UploadFile = File(...),
    session_id: Optional[str] = Query(None, description="Session ID for tracking"),
    ttl: Optional[int] = Query(None, description="Time-to-live in seconds"),
    storage: StorageBackend = Depends(get_storage)
):
    """Upload a blob to storage.
    
    Args:
        file: File to upload
        session_id: Optional session ID for tracking
        ttl: Optional TTL in seconds (overrides default)
        storage: Storage backend (injected)
        
    Returns:
        BlobUploadResponse with blob URL and metadata
    """
    try:
        # Generate unique blob ID
        blob_id = str(uuid.uuid4())
        
        # Read file data
        data = await file.read()
        
        # Get MIME type
        mime_type = file.content_type or "application/octet-stream"
        
        # Upload to storage
        metadata = await storage.upload(
            data=data,
            blob_id=blob_id,
            mime_type=mime_type,
            session_id=session_id,
            filename=file.filename,
            ttl=ttl
        )
        
        # Generate URL (relative to serving component)
        url = f"/api/storage/{blob_id}"
        
        logger.info(
            f"Uploaded blob {blob_id}: {metadata.size} bytes, "
            f"session={session_id}, filename={file.filename}"
        )
        
        return BlobUploadResponse(
            blob_id=metadata.blob_id,
            url=url,
            size=metadata.size,
            mime_type=metadata.mime_type,
            expires_at=metadata.expires_at.isoformat() if metadata.expires_at else None
        )
        
    except StorageLimitError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except StorageError as e:
        logger.error(f"Storage error during upload: {e}")
        raise HTTPException(status_code=500, detail="Storage error")
    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{blob_id}")
async def download_blob(
    blob_id: str,
    storage: StorageBackend = Depends(get_storage)
):
    """Download a blob from storage.
    
    Args:
        blob_id: Blob identifier
        storage: Storage backend (injected)
        
    Returns:
        Binary data with appropriate content type
    """
    try:
        # Get metadata first (for content type)
        metadata = await storage.get_metadata(blob_id)
        
        # Download data
        data = await storage.download(blob_id)
        
        logger.debug(f"Downloaded blob {blob_id}: {len(data)} bytes")
        
        # Return binary response with content type
        return Response(
            content=data,
            media_type=metadata.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{metadata.filename}"'
            } if metadata.filename else {}
        )
        
    except BlobNotFoundError:
        raise HTTPException(status_code=404, detail="Blob not found")
    except StorageError as e:
        logger.error(f"Storage error during download: {e}")
        raise HTTPException(status_code=500, detail="Storage error")
    except Exception as e:
        logger.error(f"Unexpected error during download: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{blob_id}/metadata", response_model=BlobMetadataResponse)
async def get_blob_metadata(
    blob_id: str,
    storage: StorageBackend = Depends(get_storage)
):
    """Get metadata for a blob.
    
    Args:
        blob_id: Blob identifier
        storage: Storage backend (injected)
        
    Returns:
        Blob metadata
    """
    try:
        metadata = await storage.get_metadata(blob_id)
        
        return BlobMetadataResponse(
            blob_id=metadata.blob_id,
            size=metadata.size,
            mime_type=metadata.mime_type,
            created_at=metadata.created_at.isoformat(),
            expires_at=metadata.expires_at.isoformat() if metadata.expires_at else None,
            session_id=metadata.session_id,
            filename=metadata.filename
        )
        
    except BlobNotFoundError:
        raise HTTPException(status_code=404, detail="Blob not found")
    except StorageError as e:
        logger.error(f"Storage error getting metadata: {e}")
        raise HTTPException(status_code=500, detail="Storage error")


@router.delete("/{blob_id}")
async def delete_blob(
    blob_id: str,
    storage: StorageBackend = Depends(get_storage)
):
    """Delete a blob from storage.
    
    Args:
        blob_id: Blob identifier
        storage: Storage backend (injected)
        
    Returns:
        Success message
    """
    try:
        deleted = await storage.delete(blob_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Blob not found")
        
        logger.info(f"Deleted blob {blob_id}")
        
        return {"status": "deleted", "blob_id": blob_id}
        
    except StorageError as e:
        logger.error(f"Storage error during delete: {e}")
        raise HTTPException(status_code=500, detail="Storage error")


@router.get("/session/{session_id}/blobs", response_model=list[BlobMetadataResponse])
async def list_session_blobs(
    session_id: str,
    storage: StorageBackend = Depends(get_storage)
):
    """List all blobs for a session.
    
    Args:
        session_id: Session identifier
        storage: Storage backend (injected)
        
    Returns:
        List of blob metadata
    """
    try:
        blobs = await storage.list_by_session(session_id)
        
        return [
            BlobMetadataResponse(
                blob_id=blob.blob_id,
                size=blob.size,
                mime_type=blob.mime_type,
                created_at=blob.created_at.isoformat(),
                expires_at=blob.expires_at.isoformat() if blob.expires_at else None,
                session_id=blob.session_id,
                filename=blob.filename
            )
            for blob in blobs
        ]
        
    except StorageError as e:
        logger.error(f"Storage error listing blobs: {e}")
        raise HTTPException(status_code=500, detail="Storage error")


@router.post("/cleanup")
async def cleanup_expired_blobs(
    storage: StorageBackend = Depends(get_storage)
):
    """Clean up expired blobs.
    
    Args:
        storage: Storage backend (injected)
        
    Returns:
        Number of blobs deleted
    """
    try:
        deleted_count = await storage.cleanup_expired()
        
        logger.info(f"Cleanup: deleted {deleted_count} expired blobs")
        
        return {
            "status": "completed",
            "deleted_count": deleted_count
        }
        
    except StorageError as e:
        logger.error(f"Storage error during cleanup: {e}")
        raise HTTPException(status_code=500, detail="Storage error")


@router.get("/stats", response_model=StorageStatsResponse)
async def get_storage_stats(
    storage: StorageBackend = Depends(get_storage)
):
    """Get storage statistics.
    
    Args:
        storage: Storage backend (injected)
        
    Returns:
        Storage statistics
    """
    try:
        stats = await storage.get_storage_stats()
        
        return StorageStatsResponse(
            backend=stats["backend"],
            total_size=stats["total_size"],
            blob_count=stats["blob_count"],
            expired_count=stats["expired_count"]
        )
        
    except StorageError as e:
        logger.error(f"Storage error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Storage error")

