"""Local file-based authentication provider.

Reads credentials from an external file (username:password per line).
The application never writes to this file — it is read-only.

WARNING: This provider is for development and testing only.
Credentials are stored in plain text. Use Cognito for production.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class LocalAuthProvider:
    """Authenticates users against an external credential file.

    The file format is one `username:password` per line.
    Lines starting with # are comments. Blank lines are ignored.
    """

    def __init__(self, users_file: str):
        self._users_file = Path(users_file)
        self._credentials: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Load credentials from the users file."""
        if not self._users_file.exists():
            logger.warning(
                "Local users file not found: %s — no local users available",
                self._users_file,
            )
            return

        count = 0
        for line_num, raw_line in enumerate(self._users_file.read_text().splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                logger.warning(
                    "Skipping malformed line %d in %s (no colon separator)",
                    line_num,
                    self._users_file,
                )
                continue
            username, password = line.split(":", 1)
            username = username.strip()
            password = password.strip()
            if not username:
                logger.warning(
                    "Skipping line %d in %s (empty username)", line_num, self._users_file
                )
                continue
            self._credentials[username] = password
            count += 1

        logger.warning(
            "LOCAL AUTH MODE — loaded %d user(s) from %s. "
            "This is NOT for production use.",
            count,
            self._users_file,
        )

    def verify(self, username: str, password: str) -> bool:
        """Verify username and password against the credential file.

        Returns True if credentials match, False otherwise.
        """
        stored = self._credentials.get(username)
        if stored is None:
            return False
        return stored == password

    def list_usernames(self) -> list[str]:
        """Return all usernames from the credential file."""
        return list(self._credentials.keys())

    def reload(self) -> None:
        """Reload credentials from the file (e.g., after file edit)."""
        self._credentials.clear()
        self._load()


# Module-level singleton
_local_auth_provider: Optional[LocalAuthProvider] = None


def get_local_auth_provider() -> Optional[LocalAuthProvider]:
    """Get the global local auth provider instance."""
    return _local_auth_provider


def set_local_auth_provider(provider: Optional[LocalAuthProvider]) -> None:
    """Set the global local auth provider instance."""
    global _local_auth_provider
    _local_auth_provider = provider
