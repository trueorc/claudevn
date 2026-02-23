"""SSH key management service for ClaudeVN.

Generates, stores, and retrieves SSH key pairs for authenticating with
external Git hosts (GitHub, GitLab, etc.). Users add the public key as a
deploy key on the remote repo; Serving uses the private key for
clone/fetch/push operations via GIT_SSH_COMMAND.
"""

import json
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_config

logger = logging.getLogger(__name__)

SSH_KEY_ID_PREFIX = "sshk_"


class SSHKeyService:
    """Service for managing SSH key pairs."""

    def __init__(self, ssh_keys_path: Optional[str] = None):
        """Initialize the SSH key service.

        Args:
            ssh_keys_path: Path to SSH keys directory.
                          Defaults to config value.
        """
        if ssh_keys_path:
            self._keys_path = Path(ssh_keys_path)
        else:
            config = get_config()
            self._keys_path = Path(config.git.ssh_keys_path)

    def _ensure_keys_dir(self) -> None:
        """Ensure the SSH keys directory exists."""
        self._keys_path.mkdir(parents=True, exist_ok=True)

    def _generate_key_id(self) -> str:
        """Generate a unique SSH key ID."""
        return f"{SSH_KEY_ID_PREFIX}{uuid.uuid4().hex[:12]}"

    def _private_key_path(self, key_id: str) -> Path:
        """Get private key file path."""
        return self._keys_path / f"{key_id}_key"

    def _public_key_path(self, key_id: str) -> Path:
        """Get public key file path."""
        return self._keys_path / f"{key_id}_key.pub"

    def _metadata_path(self, key_id: str) -> Path:
        """Get metadata sidecar file path."""
        return self._keys_path / f"{key_id}_key.json"

    def generate_key(self, description: str = "") -> Dict[str, Any]:
        """Generate a new ed25519 SSH key pair.

        Args:
            description: Optional label for the key.

        Returns:
            Dict with key_id, public_key, and fingerprint.
        """
        self._ensure_keys_dir()

        key_id = self._generate_key_id()
        private_path = self._private_key_path(key_id)
        public_path = self._public_key_path(key_id)

        # Generate ed25519 key pair with ssh-keygen
        subprocess.run(
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-f", str(private_path),
                "-N", "",  # No passphrase
                "-C", f"claudevn-{key_id}",
            ],
            check=True,
            capture_output=True,
        )

        # Set correct file permissions
        os.chmod(private_path, 0o600)
        os.chmod(public_path, 0o644)

        # Read public key and fingerprint
        public_key = public_path.read_text().strip()
        fingerprint = self._get_fingerprint(public_path)

        # Write metadata sidecar
        metadata = {
            "key_id": key_id,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._metadata_path(key_id).write_text(json.dumps(metadata))

        logger.info(f"Generated SSH key: {key_id} ({description})")

        return {
            "key_id": key_id,
            "public_key": public_key,
            "fingerprint": fingerprint,
            "description": description,
        }

    def _get_fingerprint(self, public_key_path: Path) -> str:
        """Get the fingerprint of a public key."""
        result = subprocess.run(
            ["ssh-keygen", "-lf", str(public_key_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    def list_keys(self) -> List[Dict[str, Any]]:
        """List all SSH keys (metadata only, no private key material).

        Returns:
            List of key metadata dicts.
        """
        results = []

        if not self._keys_path.exists():
            return results

        for meta_file in sorted(self._keys_path.glob("sshk_*_key.json")):
            try:
                metadata = json.loads(meta_file.read_text())
                key_id = metadata["key_id"]
                public_path = self._public_key_path(key_id)

                entry = {
                    "key_id": key_id,
                    "description": metadata.get("description", ""),
                    "created_at": metadata.get("created_at", ""),
                }

                if public_path.exists():
                    entry["fingerprint"] = self._get_fingerprint(public_path)

                results.append(entry)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping malformed metadata: {meta_file}: {e}")

        return results

    def get_key(self, key_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific key's public key and metadata.

        Args:
            key_id: The SSH key identifier.

        Returns:
            Dict with key_id, public_key, fingerprint, description or None.
        """
        public_path = self._public_key_path(key_id)
        meta_path = self._metadata_path(key_id)

        if not public_path.exists():
            return None

        public_key = public_path.read_text().strip()
        fingerprint = self._get_fingerprint(public_path)

        metadata: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                pass

        return {
            "key_id": key_id,
            "public_key": public_key,
            "fingerprint": fingerprint,
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at", ""),
        }

    def delete_key(self, key_id: str) -> bool:
        """Delete an SSH key pair.

        Args:
            key_id: The SSH key identifier.

        Returns:
            True if deleted, False if not found.
        """
        private_path = self._private_key_path(key_id)
        public_path = self._public_key_path(key_id)
        meta_path = self._metadata_path(key_id)

        if not private_path.exists() and not public_path.exists():
            return False

        for path in (private_path, public_path, meta_path):
            if path.exists():
                path.unlink()

        logger.info(f"Deleted SSH key: {key_id}")
        return True

    def key_exists(self, key_id: str) -> bool:
        """Check if an SSH key exists."""
        return self._private_key_path(key_id).exists()


# Global instance
_ssh_key_service: Optional[SSHKeyService] = None


def get_ssh_key_service() -> SSHKeyService:
    """Get the global SSH key service (creates if needed)."""
    global _ssh_key_service
    if _ssh_key_service is None:
        _ssh_key_service = SSHKeyService()
    return _ssh_key_service


def set_ssh_key_service(service: Optional[SSHKeyService]) -> None:
    """Set the global SSH key service."""
    global _ssh_key_service
    _ssh_key_service = service
