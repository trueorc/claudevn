"""SSH key manager for compute instance authentication.

Manages SSH keys that allow compute instances to push/pull from
Git repositories via SSH.
"""

import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import get_config, GitConfig

logger = logging.getLogger(__name__)


class SSHKeyManager:
    """Manages SSH keys for compute instance Git access."""

    def __init__(self, config: Optional[GitConfig] = None):
        """Initialize SSH key manager.

        Args:
            config: Git configuration (defaults to global config)
        """
        self._config = config or get_config().git
        self._keys_path = Path(self._config.ssh_keys_path)
        self._authorized_keys_file = self._keys_path / "authorized_keys"

    def _ensure_keys_dir(self) -> None:
        """Ensure SSH keys directory exists with proper permissions."""
        self._keys_path.mkdir(parents=True, exist_ok=True)
        # Set directory permissions (755) — the sshd privsep child (uid 101)
        # must be able to traverse this directory to read authorized_keys.
        # The host private key remains protected by its own 600 permissions.
        self._keys_path.chmod(0o755)

    def _load_authorized_keys(self) -> Dict[str, str]:
        """Load authorized keys file.

        Returns:
            Dict mapping compute_id to public key line
        """
        if not self._authorized_keys_file.exists():
            return {}

        keys = {}
        content = self._authorized_keys_file.read_text()

        for line in content.strip().split("\n"):
            if not line or line.startswith("#"):
                continue

            # Parse comment to get compute_id
            # Format: command="...",no-port-forwarding,... ssh-ed25519 AAAA... compute-001
            match = re.search(r'\s(compute-[a-zA-Z0-9_-]+)\s*$', line)
            if match:
                compute_id = match.group(1)
                keys[compute_id] = line

        return keys

    def _save_authorized_keys(self, keys: Dict[str, str]) -> None:
        """Save authorized keys file.

        Args:
            keys: Dict mapping compute_id to public key line
        """
        self._ensure_keys_dir()

        content = "# ClaudeVN authorized keys - managed automatically\n"
        content += f"# Last updated: {datetime.now(timezone.utc).isoformat()}\n"
        content += "#\n"

        for compute_id in sorted(keys.keys()):
            content += f"{keys[compute_id]}\n"

        self._authorized_keys_file.write_text(content)
        # Set file permissions (644) — authorized_keys contains public keys
        # (not secrets) and must be readable by the sshd privsep child process
        # (uid 101) which performs pre-authentication key matching.
        self._authorized_keys_file.chmod(0o644)

    def _format_authorized_key(self, public_key: str, compute_id: str) -> str:
        """Format a public key for authorized_keys file.

        Args:
            public_key: SSH public key
            compute_id: Compute instance ID

        Returns:
            Formatted authorized_keys line
        """
        # Clean up the public key
        public_key = public_key.strip()

        # Extract key type and key data
        parts = public_key.split()
        if len(parts) < 2:
            raise ValueError("Invalid public key format")

        key_type = parts[0]
        key_data = parts[1]

        # Restrict SSH capabilities (git-shell as login shell already limits commands)
        restrictions = [
            "no-port-forwarding",
            "no-X11-forwarding",
            "no-agent-forwarding",
            "no-pty"
        ]

        # Format: restrictions key_type key_data comment
        return f"{','.join(restrictions)} {key_type} {key_data} {compute_id}"

    def register_key(self, compute_id: str, public_key: str) -> bool:
        """Register an SSH public key for a compute instance.

        Args:
            compute_id: Compute instance ID
            public_key: SSH public key (e.g., "ssh-ed25519 AAAA...")

        Returns:
            True if key was registered (new or updated)

        Raises:
            ValueError: If public key format is invalid
        """
        logger.info(f"Registering SSH key for compute: {compute_id}")

        # Validate key format
        if not self._validate_public_key(public_key):
            raise ValueError("Invalid SSH public key format")

        keys = self._load_authorized_keys()
        formatted_key = self._format_authorized_key(public_key, compute_id)

        # Check if already registered with same key
        if compute_id in keys and keys[compute_id] == formatted_key:
            logger.debug(f"Key already registered for: {compute_id}")
            return False

        keys[compute_id] = formatted_key
        self._save_authorized_keys(keys)

        logger.info(f"SSH key registered for: {compute_id}")
        return True

    def revoke_key(self, compute_id: str) -> bool:
        """Revoke SSH key for a compute instance.

        Args:
            compute_id: Compute instance ID

        Returns:
            True if key was revoked, False if not found
        """
        logger.info(f"Revoking SSH key for compute: {compute_id}")

        keys = self._load_authorized_keys()

        if compute_id not in keys:
            logger.warning(f"No key found for: {compute_id}")
            return False

        del keys[compute_id]
        self._save_authorized_keys(keys)

        logger.info(f"SSH key revoked for: {compute_id}")
        return True

    def is_registered(self, compute_id: str) -> bool:
        """Check if compute instance has a registered key.

        Args:
            compute_id: Compute instance ID

        Returns:
            True if key is registered
        """
        keys = self._load_authorized_keys()
        return compute_id in keys

    def list_registered(self) -> List[str]:
        """List all registered compute instances.

        Returns:
            List of compute IDs with registered keys
        """
        keys = self._load_authorized_keys()
        return sorted(keys.keys())

    def generate_key_pair(self, compute_id: str) -> Tuple[str, str]:
        """Generate a new SSH key pair for a compute instance.

        Args:
            compute_id: Compute instance ID

        Returns:
            Tuple of (private_key, public_key)
        """
        self._ensure_keys_dir()

        # Generate key pair
        key_file = self._keys_path / f"{compute_id}_key"
        pub_file = self._keys_path / f"{compute_id}_key.pub"

        # Remove existing keys if any
        key_file.unlink(missing_ok=True)
        pub_file.unlink(missing_ok=True)

        # Generate new key
        subprocess.run(
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-f", str(key_file),
                "-N", "",  # No passphrase
                "-C", compute_id
            ],
            check=True,
            capture_output=True
        )

        private_key = key_file.read_text()
        public_key = pub_file.read_text()

        # Clean up files (return in memory only)
        key_file.unlink()
        pub_file.unlink()

        return private_key, public_key

    def _validate_public_key(self, public_key: str) -> bool:
        """Validate SSH public key format.

        Args:
            public_key: SSH public key string

        Returns:
            True if valid format
        """
        public_key = public_key.strip()

        # Basic format check
        parts = public_key.split()
        if len(parts) < 2:
            return False

        key_type = parts[0]
        valid_types = [
            "ssh-rsa",
            "ssh-ed25519",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521"
        ]

        if key_type not in valid_types:
            return False

        # Key data should be base64
        key_data = parts[1]
        try:
            import base64
            base64.b64decode(key_data)
            return True
        except Exception:
            return False

    def get_authorized_keys_path(self) -> Path:
        """Get path to authorized_keys file.

        Returns:
            Path to authorized_keys file
        """
        return self._authorized_keys_file

    def sync_to_system(self, system_path: Optional[str] = None) -> bool:
        """Sync authorized_keys to system location.

        This copies the managed authorized_keys file to a system location
        (e.g., /home/git/.ssh/authorized_keys) if specified.

        Args:
            system_path: Target path (e.g., "/home/git/.ssh/authorized_keys")

        Returns:
            True if synced successfully
        """
        if not system_path:
            return False

        if not self._authorized_keys_file.exists():
            logger.warning("No authorized_keys file to sync")
            return False

        target = Path(system_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        content = self._authorized_keys_file.read_text()
        target.write_text(content)
        target.chmod(0o600)

        logger.info(f"Authorized keys synced to: {system_path}")
        return True
