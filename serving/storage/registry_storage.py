"""Registry storage backend for compute and marketplace instances.

Provides filesystem-based persistence for instance registrations.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RegistryStorage:
    """Filesystem-based storage for instance registrations.

    Stores compute and marketplace instances as JSON files.
    """

    def __init__(self, base_path: str):
        """Initialize registry storage.

        Args:
            base_path: Base path for storage directory
        """
        self._base_path = Path(base_path)
        self._registry_path = self._base_path / "registry"
        self._compute_path = self._registry_path / "compute"
        self._marketplace_path = self._registry_path / "marketplaces"

        # Ensure directories exist
        self._compute_path.mkdir(parents=True, exist_ok=True)
        self._marketplace_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized registry storage at {self._registry_path}")

    # ==========================================================================
    # Compute Instance Storage
    # ==========================================================================

    async def save_compute_instance(self, instance_id: str, data: Dict[str, Any]) -> None:
        """Save a compute instance.

        Args:
            instance_id: Instance ID
            data: Instance data as dictionary
        """
        file_path = self._compute_path / f"{instance_id}.json"
        data["_saved_at"] = datetime.utcnow().isoformat()

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.debug(f"Saved compute instance: {instance_id}")

    async def load_compute_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Load a compute instance.

        Args:
            instance_id: Instance ID

        Returns:
            Instance data or None if not found
        """
        file_path = self._compute_path / f"{instance_id}.json"

        if not file_path.exists():
            return None

        with open(file_path) as f:
            return json.load(f)

    async def delete_compute_instance(self, instance_id: str) -> bool:
        """Delete a compute instance.

        Args:
            instance_id: Instance ID

        Returns:
            True if deleted, False if not found
        """
        file_path = self._compute_path / f"{instance_id}.json"

        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted compute instance: {instance_id}")
            return True

        return False

    async def list_compute_instances(self) -> List[Dict[str, Any]]:
        """List all compute instances.

        Returns:
            List of instance data dictionaries
        """
        instances = []

        for file_path in self._compute_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    instances.append(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return instances

    # ==========================================================================
    # Marketplace Instance Storage
    # ==========================================================================

    async def save_marketplace(self, marketplace_id: str, data: Dict[str, Any]) -> None:
        """Save a marketplace instance.

        Args:
            marketplace_id: Marketplace ID
            data: Marketplace data as dictionary
        """
        file_path = self._marketplace_path / f"{marketplace_id}.json"
        data["_saved_at"] = datetime.utcnow().isoformat()

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.debug(f"Saved marketplace: {marketplace_id}")

    async def load_marketplace(self, marketplace_id: str) -> Optional[Dict[str, Any]]:
        """Load a marketplace instance.

        Args:
            marketplace_id: Marketplace ID

        Returns:
            Marketplace data or None if not found
        """
        file_path = self._marketplace_path / f"{marketplace_id}.json"

        if not file_path.exists():
            return None

        with open(file_path) as f:
            return json.load(f)

    async def delete_marketplace(self, marketplace_id: str) -> bool:
        """Delete a marketplace instance.

        Args:
            marketplace_id: Marketplace ID

        Returns:
            True if deleted, False if not found
        """
        file_path = self._marketplace_path / f"{marketplace_id}.json"

        if file_path.exists():
            file_path.unlink()
            logger.debug(f"Deleted marketplace: {marketplace_id}")
            return True

        return False

    async def load_all_instances(self, instance_type: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Load all instances as a dict keyed by ID.

        Args:
            instance_type: Type of instances to load. Use "marketplaces" for
                marketplace instances, or None/omit for compute instances.

        Returns:
            Dictionary mapping instance IDs to their data
        """
        if instance_type == "marketplaces":
            target_path = self._marketplace_path
            id_field = "marketplace_id"
        else:
            target_path = self._compute_path
            id_field = "instance_id"

        result: Dict[str, Dict[str, Any]] = {}

        for file_path in target_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                # Use the ID field from data, falling back to filename stem
                instance_id = data.get(id_field, file_path.stem)
                result[instance_id] = data
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return result

    async def list_marketplaces(self) -> List[Dict[str, Any]]:
        """List all marketplaces.

        Returns:
            List of marketplace data dictionaries
        """
        marketplaces = []

        for file_path in self._marketplace_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    marketplaces.append(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return marketplaces
