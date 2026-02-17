"""Blob download endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from .dependencies import StorageBackend, get_storage
from storage import BlobNotFoundError, StorageError


logger = logging.getLogger(__name__)

router = APIRouter()


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

