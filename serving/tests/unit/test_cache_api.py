"""Unit tests for cache API endpoints.

Tests use FastAPI TestClient with mocked FilesystemCache backend.

Reference: Issue #695
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.cache import router


@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.clear = AsyncMock(return_value=0)
    cache.delete = AsyncMock(return_value=True)
    cache.cleanup_expired = AsyncMock(return_value=0)
    cache.get_stats = MagicMock(return_value={
        "total_entries": 5,
        "active_entries": 3,
        "expired_entries": 2,
        "total_size_bytes": 1024,
        "cache_path": "/tmp/cache",
        "default_ttl": 300,
    })
    return cache


@pytest.fixture
def client(mock_cache):
    app = FastAPI()
    app.include_router(router)
    with patch("api.cache.get_cache_backend", return_value=mock_cache):
        yield TestClient(app)


# =============================================================================
# DELETE /cache/clear
# =============================================================================


class TestClearCache:
    """Tests for the clear_cache endpoint - the main bug fix."""

    def test_clear_empty_cache_returns_success(self, client, mock_cache):
        """Bug #695: clear() returns 0 for empty cache, should still succeed."""
        mock_cache.clear = AsyncMock(return_value=0)
        resp = client.delete("/cache/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["cleared_entries"] == 0

    def test_clear_populated_cache_returns_count(self, client, mock_cache):
        mock_cache.clear = AsyncMock(return_value=5)
        resp = client.delete("/cache/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["cleared_entries"] == 5

    def test_clear_exception_returns_500(self, client, mock_cache):
        mock_cache.clear = AsyncMock(side_effect=OSError("Permission denied"))
        resp = client.delete("/cache/clear")
        assert resp.status_code == 500
        assert "Permission denied" in resp.json()["detail"]


# =============================================================================
# GET /cache/stats
# =============================================================================


class TestCacheStats:
    def test_stats_with_filesystem_backend(self, client, mock_cache):
        resp = client.get("/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend"] == "filesystem"
        assert data["total_entries"] == 5
        assert data["active_entries"] == 3

    def test_stats_without_get_stats_method(self, client, mock_cache):
        del mock_cache.get_stats
        resp = client.get("/cache/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend"] == "unknown"


# =============================================================================
# POST /cache/cleanup
# =============================================================================


class TestCleanupExpired:
    def test_cleanup_returns_deleted_count(self, client, mock_cache):
        mock_cache.cleanup_expired = AsyncMock(return_value=3)
        resp = client.post("/cache/cleanup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["deleted_entries"] == 3

    def test_cleanup_not_supported(self, client, mock_cache):
        del mock_cache.cleanup_expired
        resp = client.post("/cache/cleanup")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_supported"

    def test_cleanup_exception_returns_500(self, client, mock_cache):
        mock_cache.cleanup_expired = AsyncMock(side_effect=RuntimeError("disk error"))
        resp = client.post("/cache/cleanup")
        assert resp.status_code == 500
        assert "disk error" in resp.json()["detail"]


# =============================================================================
# DELETE /cache/{key}
# =============================================================================


class TestDeleteCacheEntry:
    def test_delete_existing_key(self, client, mock_cache):
        mock_cache.delete = AsyncMock(return_value=True)
        resp = client.delete("/cache/my-key")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["key"] == "my-key"

    def test_delete_missing_key_returns_404(self, client, mock_cache):
        mock_cache.delete = AsyncMock(return_value=False)
        resp = client.delete("/cache/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_delete_exception_returns_500(self, client, mock_cache):
        mock_cache.delete = AsyncMock(side_effect=OSError("disk full"))
        resp = client.delete("/cache/bad-key")
        assert resp.status_code == 500
        assert "disk full" in resp.json()["detail"]
