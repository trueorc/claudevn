"""Tests for version module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestGetVersion:
    """Tests for get_version function."""

    def test_get_version_returns_string(self):
        """Test that get_version returns a non-empty string."""
        # Clear the cache to ensure fresh read
        from claudevn_shared.version import get_version
        get_version.cache_clear()

        version = get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_get_version_format(self):
        """Test that version follows semantic versioning format."""
        from claudevn_shared.version import get_version
        get_version.cache_clear()

        version = get_version()
        parts = version.split(".")
        assert len(parts) >= 2, "Version should have at least major.minor"
        # Each part should be a valid number
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"

    def test_get_version_matches_version_file(self):
        """Test that get_version returns content from VERSION file."""
        from claudevn_shared.version import get_version, _find_version_file
        get_version.cache_clear()

        # Read VERSION file directly using the same finder function
        version_file = _find_version_file()
        expected = version_file.read_text().strip()

        version = get_version()
        assert version == expected

    def test_get_version_is_cached(self):
        """Test that get_version uses LRU cache."""
        from claudevn_shared.version import get_version
        get_version.cache_clear()

        # First call
        version1 = get_version()
        # Check cache info
        cache_info = get_version.cache_info()
        assert cache_info.hits == 0
        assert cache_info.misses == 1

        # Second call should be cached
        version2 = get_version()
        cache_info = get_version.cache_info()
        assert cache_info.hits == 1
        assert cache_info.misses == 1

        assert version1 == version2


class TestVersionConstant:
    """Tests for VERSION constant."""

    def test_version_constant_exists(self):
        """Test that VERSION constant is exported."""
        from claudevn_shared.version import VERSION
        assert VERSION is not None
        assert isinstance(VERSION, str)

    def test_version_constant_matches_get_version(self):
        """Test that VERSION constant matches get_version result."""
        from claudevn_shared.version import VERSION, get_version
        get_version.cache_clear()
        assert VERSION == get_version()


class TestVersionInInit:
    """Tests for version exports in __init__.py."""

    def test_version_exported_from_init(self):
        """Test that version is exported from claudevn_shared."""
        from claudevn_shared import __version__, get_version, VERSION
        assert __version__ is not None
        assert get_version is not None
        assert VERSION is not None

    def test_dunder_version_matches_version(self):
        """Test that __version__ matches VERSION."""
        from claudevn_shared import __version__, VERSION
        assert __version__ == VERSION


class TestFindVersionFile:
    """Tests for _find_version_file function."""

    def test_find_version_file_exists(self):
        """Test that _find_version_file finds the VERSION file."""
        from claudevn_shared.version import _find_version_file
        version_file = _find_version_file()
        assert version_file.exists()
        assert version_file.name == "VERSION"

    def test_find_version_file_returns_path(self):
        """Test that _find_version_file returns a Path object."""
        from claudevn_shared.version import _find_version_file
        version_file = _find_version_file()
        assert isinstance(version_file, Path)
