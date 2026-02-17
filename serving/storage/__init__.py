"""Storage backends for TrueOrc Serving component.

Provides pluggable storage backends for:
- Registry persistence (compute/marketplace instances)
- Cache (agent search results, etc.)
- Data provider (sessions, blobs, artifacts)
"""

from .registry_storage import RegistryStorage
from .cache_backend import FilesystemCache, get_cache_backend, set_cache_backend
from .data_provider import FilesystemDataProvider, get_data_provider, set_data_provider

__all__ = [
    "RegistryStorage",
    "FilesystemCache",
    "get_cache_backend",
    "set_cache_backend",
    "FilesystemDataProvider",
    "get_data_provider",
    "set_data_provider",
]
