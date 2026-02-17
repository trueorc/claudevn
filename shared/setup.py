"""Setup script for claudevn_shared package."""

from pathlib import Path
from setuptools import setup, find_packages


def get_version():
    """Read version from root VERSION file."""
    version_file = Path(__file__).parent.parent / "VERSION"
    return version_file.read_text().strip()


setup(
    name="claudevn-shared",
    version=get_version(),
    description="Shared utilities and types for ClaudeVN platform",
    author="ClaudeVN Team",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        # Core dependencies
    ],
)

