"""Session-specific storage endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends

from .models import BlobMetadataResponse
from .dependencies import StorageBackend, get_storage
from storage import StorageError


logger = logging.getLogger(__name__)

router = APIRouter()


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

