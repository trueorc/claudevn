"""URL conversion utilities for HTTPS ↔ SSH git remote URLs."""

import re
from typing import Optional

# Matches HTTPS git URLs: https://github.com/org/repo.git
_HTTPS_PATTERN = re.compile(
    r"^https?://([^/]+)/(.+?)(?:\.git)?$"
)

# Matches SSH git URLs: git@github.com:org/repo.git
_SSH_PATTERN = re.compile(
    r"^git@([^:]+):(.+?)(?:\.git)?$"
)


def https_to_ssh(url: str) -> Optional[str]:
    """Convert an HTTPS git URL to SSH format.

    Examples:
        https://github.com/org/repo.git  → git@github.com:org/repo.git
        https://gitlab.com/org/repo      → git@gitlab.com:org/repo.git

    Returns None if the URL is not a valid HTTPS git URL.
    """
    match = _HTTPS_PATTERN.match(url)
    if not match:
        return None
    host, path = match.group(1), match.group(2)
    return f"git@{host}:{path}.git"


def ssh_to_https(url: str) -> Optional[str]:
    """Convert an SSH git URL to HTTPS format.

    Examples:
        git@github.com:org/repo.git  → https://github.com/org/repo.git
        git@gitlab.com:org/repo      → https://gitlab.com/org/repo.git

    Returns None if the URL is not a valid SSH git URL.
    """
    match = _SSH_PATTERN.match(url)
    if not match:
        return None
    host, path = match.group(1), match.group(2)
    return f"https://{host}/{path}.git"


def is_ssh_url(url: str) -> bool:
    """Check if a URL is an SSH git URL."""
    return _SSH_PATTERN.match(url) is not None


def is_https_url(url: str) -> bool:
    """Check if a URL is an HTTPS git URL."""
    return _HTTPS_PATTERN.match(url) is not None


def ensure_ssh_url(url: str) -> str:
    """Return the SSH form of the URL. If already SSH, return as-is.

    Raises ValueError if the URL cannot be converted.
    """
    if is_ssh_url(url):
        return url
    converted = https_to_ssh(url)
    if converted is None:
        raise ValueError(f"Cannot convert URL to SSH format: {url}")
    return converted
