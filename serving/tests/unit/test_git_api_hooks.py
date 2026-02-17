"""Tests for Git API hook endpoints.

Unit tests for the hook-related API endpoints:
- GET /repos/{project}/status - Extended repo status with hooks
- GET /repos/{project}/hooks - Hook status
- POST /repos/{project}/hooks - Install hooks
- POST /repos/hooks/migrate - Migrate all repos
"""

import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

# Import the app and api.git module to reset globals
from app import app
import api.git as git_module


# API base path (must match app.py)
API_BASE = "/api/v1/git"


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_repo_manager():
    """Mock RepoManager for testing by resetting and replacing the global."""
    # Reset the global singleton
    original = git_module._repo_manager
    mock_manager = MagicMock()
    git_module._repo_manager = mock_manager
    yield mock_manager
    # Restore original
    git_module._repo_manager = original


# =============================================================================
# Test: GET /repos/{project}/hooks
# =============================================================================

class TestGetHookStatus:
    """Test GET /git/repos/{project}/hooks endpoint."""

    def test_get_hook_status_success(self, client, mock_repo_manager):
        """Test getting hook status for a repo."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.verify_hooks.return_value = {
            "hooks_installed": True,
            "pre_receive": {
                "exists": True,
                "executable": True,
                "path": "/repos/test.git/hooks/pre-receive"
            },
            "post_receive": {
                "exists": True,
                "executable": True,
                "path": "/repos/test.git/hooks/post-receive"
            }
        }

        response = client.get(f"{API_BASE}/repos/test_project/hooks")

        assert response.status_code == 200
        data = response.json()
        assert data["project"] == "test_project"
        assert data["hooks_installed"] is True
        assert data["pre_receive"]["exists"] is True
        assert data["pre_receive"]["executable"] is True
        assert data["post_receive"]["exists"] is True

    def test_get_hook_status_not_installed(self, client, mock_repo_manager):
        """Test getting hook status when hooks not installed."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.verify_hooks.return_value = {
            "hooks_installed": False,
            "pre_receive": {
                "exists": False,
                "executable": False,
                "path": None
            },
            "post_receive": {
                "exists": False,
                "executable": False,
                "path": None
            }
        }

        response = client.get(f"{API_BASE}/repos/test_project/hooks")

        assert response.status_code == 200
        data = response.json()
        assert data["hooks_installed"] is False

    def test_get_hook_status_repo_not_found(self, client, mock_repo_manager):
        """Test getting hook status for non-existent repo."""
        mock_repo_manager.repo_exists.return_value = False

        response = client.get(f"{API_BASE}/repos/nonexistent/hooks")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# =============================================================================
# Test: POST /repos/{project}/hooks
# =============================================================================

class TestInstallHooks:
    """Test POST /git/repos/{project}/hooks endpoint."""

    def test_install_hooks_success(self, client, mock_repo_manager):
        """Test installing hooks on a repo."""
        mock_repo_manager.repo_exists.return_value = True

        response = client.post(f"{API_BASE}/repos/test_project/hooks")

        assert response.status_code == 200
        data = response.json()
        assert data["project"] == "test_project"
        assert data["success"] is True
        mock_repo_manager.install_hooks.assert_called_once_with("test_project")

    def test_install_hooks_repo_not_found(self, client, mock_repo_manager):
        """Test installing hooks on non-existent repo."""
        mock_repo_manager.repo_exists.return_value = False

        response = client.post(f"{API_BASE}/repos/nonexistent/hooks")

        assert response.status_code == 404

    def test_install_hooks_failure(self, client, mock_repo_manager):
        """Test installing hooks when installation fails."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.install_hooks.side_effect = Exception("Permission denied")

        response = client.post(f"{API_BASE}/repos/test_project/hooks")

        assert response.status_code == 500
        assert "Permission denied" in response.json()["detail"]


# =============================================================================
# Test: POST /repos/hooks/migrate
# =============================================================================

class TestMigrateHooks:
    """Test POST /git/repos/hooks/migrate endpoint."""

    def test_migrate_hooks_success(self, client, mock_repo_manager):
        """Test migrating hooks to all repos."""
        mock_repo_manager.install_hooks_all.return_value = {
            "total": 3,
            "success": 3,
            "failed": 0,
            "results": {
                "repo1": {"success": True},
                "repo2": {"success": True},
                "repo3": {"success": True}
            }
        }

        response = client.post(f"{API_BASE}/repos/hooks/migrate")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["success"] == 3
        assert data["failed"] == 0
        mock_repo_manager.install_hooks_all.assert_called_once()

    def test_migrate_hooks_partial_failure(self, client, mock_repo_manager):
        """Test migrating hooks with partial failures."""
        mock_repo_manager.install_hooks_all.return_value = {
            "total": 3,
            "success": 2,
            "failed": 1,
            "results": {
                "repo1": {"success": True},
                "repo2": {"success": False, "error": "Permission denied"},
                "repo3": {"success": True}
            }
        }

        response = client.post(f"{API_BASE}/repos/hooks/migrate")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["success"] == 2
        assert data["failed"] == 1

    def test_migrate_hooks_empty(self, client, mock_repo_manager):
        """Test migrating hooks when no repos exist."""
        mock_repo_manager.install_hooks_all.return_value = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "results": {}
        }

        response = client.post(f"{API_BASE}/repos/hooks/migrate")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


# =============================================================================
# Test: GET /repos/{project}/status
# =============================================================================

class TestGetRepoStatus:
    """Test GET /git/repos/{project}/status endpoint."""

    def test_get_repo_status_with_hooks(self, client, mock_repo_manager):
        """Test getting repo status with hook info."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.get_repo_status.return_value = {
            "path": "/repos/test.git",
            "origin_url": None,
            "default_branch": "main",
            "branches": ["main", "feature/test"],
            "branch_count": 2,
            "is_mirror": False
        }
        mock_repo_manager.get_repo_url.return_value = "git@localhost:test.git"
        mock_repo_manager.verify_hooks.return_value = {
            "hooks_installed": True,
            "pre_receive": {
                "exists": True,
                "executable": True,
                "path": "/repos/test.git/hooks/pre-receive"
            },
            "post_receive": {
                "exists": True,
                "executable": True,
                "path": "/repos/test.git/hooks/post-receive"
            }
        }

        response = client.get(f"{API_BASE}/repos/test_project/status")

        assert response.status_code == 200
        data = response.json()
        assert data["project"] == "test_project"
        assert data["hooks_installed"] is True
        assert data["hooks"] is not None
        assert data["hooks"]["hooks_installed"] is True

    def test_get_repo_status_no_hooks(self, client, mock_repo_manager):
        """Test getting repo status when hooks not installed."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.get_repo_status.return_value = {
            "path": "/repos/test.git",
            "origin_url": None,
            "default_branch": "main",
            "branches": ["main"],
            "branch_count": 1,
            "is_mirror": False
        }
        mock_repo_manager.get_repo_url.return_value = "git@localhost:test.git"
        mock_repo_manager.verify_hooks.return_value = {
            "hooks_installed": False,
            "pre_receive": {
                "exists": False,
                "executable": False,
                "path": None
            },
            "post_receive": {
                "exists": False,
                "executable": False,
                "path": None
            }
        }

        response = client.get(f"{API_BASE}/repos/test_project/status")

        assert response.status_code == 200
        data = response.json()
        assert data["hooks_installed"] is False

    def test_get_repo_status_not_found(self, client, mock_repo_manager):
        """Test getting status for non-existent repo."""
        mock_repo_manager.repo_exists.return_value = False

        response = client.get(f"{API_BASE}/repos/nonexistent/status")

        assert response.status_code == 404
