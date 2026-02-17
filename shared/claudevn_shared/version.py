"""Version management for ClaudeVN platform.

Provides centralized version reading from the root VERSION file.
All components should import get_version() from this module.

Supports multiple environments:
- Development: Finds VERSION by searching parent directories
- Docker: Finds VERSION at /app/VERSION
- CI/Testing: Falls back to "0.0.0-dev" if not found
"""

import os
from functools import lru_cache
from pathlib import Path


def _find_version_file() -> Path:
    """Find the VERSION file by searching multiple locations.

    Search order:
    1. CLAUDEVN_VERSION_FILE environment variable (explicit path)
    2. /app/VERSION (Docker container standard location)
    3. Parent directory traversal (development environment)
    """
    # Check environment variable first
    env_path = os.environ.get("CLAUDEVN_VERSION_FILE")
    if env_path:
        version_file = Path(env_path)
        if version_file.exists():
            return version_file

    # Check Docker standard location
    docker_version = Path("/app/VERSION")
    if docker_version.exists():
        return docker_version

    # Search up to 5 levels (shared/claudevn_shared/version.py -> root)
    current = Path(__file__).resolve()
    for _ in range(5):
        current = current.parent
        version_file = current / "VERSION"
        if version_file.exists():
            return version_file

    raise FileNotFoundError("VERSION file not found in any parent directory or /app/VERSION")


@lru_cache(maxsize=1)
def get_version() -> str:
    """Get the ClaudeVN platform version from the root VERSION file.

    Returns:
        Version string (e.g., "0.3.0")

    Raises:
        FileNotFoundError: If VERSION file cannot be found
    """
    version_file = _find_version_file()
    return version_file.read_text().strip()


# For backwards compatibility and convenience
VERSION = get_version()
