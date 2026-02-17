"""Data provider for TrueOrc Serving component.

Provides filesystem-based storage for sessions, blobs, and artifacts.
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Global data provider instance
_data_provider: Optional["FilesystemDataProvider"] = None


def get_data_provider() -> Optional["FilesystemDataProvider"]:
    """Get the global data provider instance."""
    return _data_provider


def set_data_provider(provider: "FilesystemDataProvider") -> None:
    """Set the global data provider instance."""
    global _data_provider
    _data_provider = provider


class FilesystemDataProvider:
    """Filesystem-based data provider.

    Stores data as JSON files organized by key prefix (namespace).
    """

    def __init__(self, datastore_path: str):
        """Initialize filesystem data provider.

        Args:
            datastore_path: Path to datastore directory
        """
        self._datastore_path = Path(datastore_path)

        # Ensure datastore directory exists
        self._datastore_path.mkdir(parents=True, exist_ok=True)

        # Common subdirectories
        (self._datastore_path / "sessions").mkdir(exist_ok=True)
        (self._datastore_path / "blobs").mkdir(exist_ok=True)
        (self._datastore_path / "artifacts").mkdir(exist_ok=True)

        logger.info(f"Initialized filesystem data provider at {self._datastore_path}")

    def _key_to_path(self, key: str) -> Path:
        """Convert key to file path.

        Keys can be namespaced with colons, e.g., "sessions:session-123"
        which maps to datastore_path/sessions/session-123.json

        Args:
            key: Data key

        Returns:
            Path to data file
        """
        parts = key.split(":", 1)

        if len(parts) == 2:
            namespace, item_key = parts
            # Sanitize key for filename
            safe_key = item_key.replace("/", "_").replace("\\", "_")
            return self._datastore_path / namespace / f"{safe_key}.json"
        else:
            safe_key = key.replace("/", "_").replace("\\", "_")
            return self._datastore_path / f"{safe_key}.json"

    async def store(
        self,
        key: str,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Store data.

        Args:
            key: Storage key (can be namespaced like "sessions:session-123")
            data: Data to store (must be JSON serializable)
            metadata: Optional metadata to store with data
        """
        file_path = self._key_to_path(key)

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "key": key,
            "data": data,
            "metadata": metadata or {},
            "stored_at": datetime.utcnow().isoformat()
        }

        try:
            with open(file_path, "w") as f:
                json.dump(entry, f, indent=2, default=str)
            logger.debug(f"Stored data: {key}")
        except Exception as e:
            logger.error(f"Failed to store {key}: {e}")
            raise

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve data.

        Args:
            key: Storage key

        Returns:
            Stored data or None if not found
        """
        file_path = self._key_to_path(key)

        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                entry = json.load(f)
            return entry.get("data")
        except Exception as e:
            logger.warning(f"Failed to retrieve {key}: {e}")
            return None

    async def retrieve_with_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve data with metadata.

        Args:
            key: Storage key

        Returns:
            Dict with 'data', 'metadata', 'stored_at' or None if not found
        """
        file_path = self._key_to_path(key)

        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to retrieve {key}: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete data.

        Args:
            key: Storage key

        Returns:
            True if deleted, False if not found
        """
        file_path = self._key_to_path(key)

        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted data: {key}")
            return True

        return False

    async def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Storage key

        Returns:
            True if exists
        """
        file_path = self._key_to_path(key)
        return file_path.exists()

    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """List all keys, optionally filtered by prefix.

        Args:
            prefix: Optional prefix filter (e.g., "sessions" for all session keys)

        Returns:
            List of keys
        """
        keys = []

        if prefix:
            # List keys in specific namespace
            namespace_path = self._datastore_path / prefix
            if namespace_path.exists():
                for file_path in namespace_path.glob("*.json"):
                    item_key = file_path.stem
                    keys.append(f"{prefix}:{item_key}")
        else:
            # List all keys recursively
            for file_path in self._datastore_path.rglob("*.json"):
                relative = file_path.relative_to(self._datastore_path)
                parts = list(relative.parts)

                if len(parts) > 1:
                    namespace = parts[0]
                    item_key = parts[-1].replace(".json", "")
                    keys.append(f"{namespace}:{item_key}")
                else:
                    keys.append(parts[0].replace(".json", ""))

        return keys

    async def store_blob(self, blob_id: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Store binary blob data.

        Args:
            blob_id: Unique blob identifier
            data: Binary data
            content_type: MIME type

        Returns:
            Blob reference key
        """
        blob_path = self._datastore_path / "blobs" / blob_id

        # Store the blob data
        with open(blob_path, "wb") as f:
            f.write(data)

        # Store metadata
        metadata_path = self._datastore_path / "blobs" / f"{blob_id}.meta.json"
        metadata = {
            "blob_id": blob_id,
            "content_type": content_type,
            "size": len(data),
            "stored_at": datetime.utcnow().isoformat()
        }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.debug(f"Stored blob: {blob_id} ({len(data)} bytes)")
        return f"blobs:{blob_id}"

    async def retrieve_blob(self, blob_id: str) -> Optional[bytes]:
        """Retrieve binary blob data.

        Args:
            blob_id: Blob identifier

        Returns:
            Binary data or None if not found
        """
        blob_path = self._datastore_path / "blobs" / blob_id

        if not blob_path.exists():
            return None

        with open(blob_path, "rb") as f:
            return f.read()

    async def get_blob_metadata(self, blob_id: str) -> Optional[Dict[str, Any]]:
        """Get blob metadata.

        Args:
            blob_id: Blob identifier

        Returns:
            Metadata dict or None if not found
        """
        metadata_path = self._datastore_path / "blobs" / f"{blob_id}.meta.json"

        if not metadata_path.exists():
            return None

        with open(metadata_path) as f:
            return json.load(f)

    async def delete_blob(self, blob_id: str) -> bool:
        """Delete blob and metadata.

        Args:
            blob_id: Blob identifier

        Returns:
            True if deleted, False if not found
        """
        blob_path = self._datastore_path / "blobs" / blob_id
        metadata_path = self._datastore_path / "blobs" / f"{blob_id}.meta.json"

        deleted = False

        if blob_path.exists():
            blob_path.unlink()
            deleted = True

        if metadata_path.exists():
            metadata_path.unlink()

        if deleted:
            logger.debug(f"Deleted blob: {blob_id}")

        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics.

        Returns:
            Dict with storage statistics
        """
        total_files = 0
        total_size = 0
        by_namespace = {}

        for file_path in self._datastore_path.rglob("*"):
            if file_path.is_file():
                total_files += 1
                total_size += file_path.stat().st_size

                # Count by namespace
                relative = file_path.relative_to(self._datastore_path)
                if len(relative.parts) > 1:
                    namespace = relative.parts[0]
                    by_namespace[namespace] = by_namespace.get(namespace, 0) + 1
                else:
                    by_namespace["root"] = by_namespace.get("root", 0) + 1

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "by_namespace": by_namespace,
            "datastore_path": str(self._datastore_path)
        }
