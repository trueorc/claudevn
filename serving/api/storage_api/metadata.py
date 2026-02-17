"""Blob metadata endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends

from .models import BlobMetadataResponse
from .dependencies import StorageBackend, get_storage
from storage import BlobNotFoundError, StorageError


logger = logging.getLogger(__name__)

router = APIRouter()


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

