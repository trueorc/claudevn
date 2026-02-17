"""Blob storage API endpoints for the Serving Component.

This module provides a modular API structure for blob storage.
Each concern (upload, download, metadata, etc.) is in its own file.
"""

from fastapi import APIRouter

from . import upload, download, metadata, session, management

# Create main router
router = APIRouter(prefix="/api/storage", tags=["storage"])

# Include all sub-routers
router.include_router(upload.router)
router.include_router(download.router)
router.include_router(metadata.router)
router.include_router(session.router)
router.include_router(management.router)

# Export for convenience
__all__ = ["router"]

