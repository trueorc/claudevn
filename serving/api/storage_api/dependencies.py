"""Shared dependencies for storage API endpoints."""

from storage import StorageBackend


# Dependency to get storage backend (will be injected by main app)
def get_storage() -> StorageBackend:
    """Get storage backend instance.
    
    This should be overridden by the main app to provide the actual storage backend.
    """
    raise NotImplementedError("Storage backend not configured")


__all__ = ["get_storage", "StorageBackend"]

