"""Storage management endpoints (cleanup, stats, admin)."""

import logging
from fastapi import APIRouter, HTTPException, Depends

from .models import StorageStatsResponse
from .dependencies import StorageBackend, get_storage
from storage import StorageError


logger = logging.getLogger(__name__)

router = APIRouter()


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

