"""Cache management API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, status

from storage.cache_backend import get_cache_backend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats")
async def get_cache_stats():
    """Get cache statistics.
    
    Returns:
        Cache statistics (number of entries, size, etc.)
    """
    cache = get_cache_backend()
    
    # For filesystem cache, use built-in stats method
    if hasattr(cache, 'get_stats'):
        stats = cache.get_stats()
        
        return {
            "backend": "filesystem",
            **stats
        }
    
    return {
        "backend": "unknown",
        "message": "Cache stats not available for this backend"
    }


@router.delete("/clear")
async def clear_cache():
    """Clear all cache entries.
    
    Returns:
        Confirmation message
    """
    cache = get_cache_backend()

    try:
        cleared = await cache.clear()

        logger.info(f"Cache cleared via API ({cleared} entries)")
        return {
            "status": "success",
            "cleared_entries": cleared,
            "message": f"Cleared {cleared} cache entries"
        }

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing cache: {str(e)}"
        )


@router.post("/cleanup")
async def cleanup_expired_entries():
    """Clean up expired cache entries.
    
    Returns:
        Number of entries deleted
    """
    cache = get_cache_backend()
    
    try:
        if hasattr(cache, 'cleanup_expired'):
            deleted = await cache.cleanup_expired()
            
            logger.info(f"Cleaned up {deleted} expired cache entries")
            
            return {
                "status": "success",
                "deleted_entries": deleted,
                "message": f"Cleaned up {deleted} expired entries"
            }
        else:
            return {
                "status": "not_supported",
                "message": "This cache backend does not support cleanup"
            }
            
    except Exception as e:
        logger.error(f"Error cleaning up cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cleaning up cache: {str(e)}"
        )


@router.delete("/{key}")
async def delete_cache_entry(key: str):
    """Delete a specific cache entry.
    
    Args:
        key: Cache key to delete
        
    Returns:
        Confirmation message
    """
    cache = get_cache_backend()
    
    try:
        success = await cache.delete(key)
        
        if success:
            return {
                "status": "success",
                "key": key,
                "message": "Cache entry deleted"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cache entry not found: {key}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting cache entry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting cache entry: {str(e)}"
        )
