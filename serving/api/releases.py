"""Release notes API — serves markdown release notes from docs/releases/."""

from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/releases", tags=["releases"])

# Search multiple locations for the releases directory
_SEARCH_PATHS = [
    Path(__file__).resolve().parent.parent.parent / "docs" / "releases",  # dev
    Path("/app/docs/releases"),  # docker
]


def _get_releases_dir() -> Path:
    for p in _SEARCH_PATHS:
        if p.is_dir():
            return p
    raise FileNotFoundError("Release notes directory not found")


def _parse_version(filename: str) -> str:
    """Extract version string from filename like v0.4.0.md -> 0.4.0."""
    return filename.removeprefix("v").removesuffix(".md")


def _version_sort_key(version: str) -> tuple:
    """Convert version string to tuple for sorting."""
    parts = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


@router.get("")
async def list_releases():
    """List available release versions, newest first."""
    try:
        releases_dir = _get_releases_dir()
    except FileNotFoundError:
        return {"versions": []}

    versions = []
    for f in releases_dir.glob("v*.md"):
        versions.append(_parse_version(f.stem))

    versions.sort(key=_version_sort_key, reverse=True)
    return {"versions": versions}


@router.get("/{version}")
async def get_release(version: str):
    """Get markdown content for a specific version."""
    try:
        releases_dir = _get_releases_dir()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Release notes not found")

    # Try both with and without v prefix
    for name in [f"v{version}.md", f"{version}.md"]:
        path = releases_dir / name
        if path.is_file():
            return {"version": version, "content": path.read_text()}

    raise HTTPException(status_code=404, detail=f"Release notes for {version} not found")
