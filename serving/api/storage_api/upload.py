"""Blob upload endpoints."""

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends

from .models import BlobUploadResponse
from .dependencies import StorageBackend, get_storage
from storage import StorageError, StorageLimitError


logger = logging.getLogger(__name__)

router = APIRouter()


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

