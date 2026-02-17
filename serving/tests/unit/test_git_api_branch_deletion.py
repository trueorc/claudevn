"""Tests for Git API branch deletion endpoint.

Unit tests for the branch deletion API endpoint:
- DELETE /repos/{project}/branches/{branch} - Delete a branch
"""

import pytest
from unittest.mock import MagicMock

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
# Test: DELETE /repos/{project}/branches/{branch}
# =============================================================================

class TestDeleteBranch:
    """Test DELETE /git/repos/{project}/branches/{branch} endpoint."""

    def test_delete_branch_success(self, client, mock_repo_manager):
        """Test successfully deleting a branch."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.delete_branch.return_value = True

        response = client.delete(f"{API_BASE}/repos/test_project/branches/feature-branch")

        assert response.status_code == 200
        data = response.json()
        assert data["project"] == "test_project"
        assert data["branch"] == "feature-branch"
        assert data["deleted"] is True
        mock_repo_manager.delete_branch.assert_called_once_with("test_project", "feature-branch")

    def test_delete_branch_repo_not_found(self, client, mock_repo_manager):
        """Test deleting branch from non-existent repo."""
        mock_repo_manager.repo_exists.return_value = False

        response = client.delete(f"{API_BASE}/repos/nonexistent/branches/feature-branch")

        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]

    def test_delete_branch_not_found(self, client, mock_repo_manager):
        """Test deleting non-existent branch."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.delete_branch.return_value = False

        response = client.delete(f"{API_BASE}/repos/test_project/branches/nonexistent-branch")

        assert response.status_code == 404
        assert "Branch not found" in response.json()["detail"]

    def test_delete_branch_protected_main(self, client, mock_repo_manager):
        """Test deleting protected 'main' branch is forbidden."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.delete_branch.side_effect = ValueError("Cannot delete protected branch: main")

        response = client.delete(f"{API_BASE}/repos/test_project/branches/main")

        assert response.status_code == 403
        assert "protected branch" in response.json()["detail"].lower()

    def test_delete_branch_protected_master(self, client, mock_repo_manager):
        """Test deleting protected 'master' branch is forbidden."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.delete_branch.side_effect = ValueError("Cannot delete protected branch: master")

        response = client.delete(f"{API_BASE}/repos/test_project/branches/master")

        assert response.status_code == 403
        assert "protected branch" in response.json()["detail"].lower()

    def test_delete_branch_with_slashes(self, client, mock_repo_manager):
        """Test deleting branch with slashes in name (e.g., feature/issue-123)."""
        mock_repo_manager.repo_exists.return_value = True
        mock_repo_manager.delete_branch.return_value = True

        # URL encode the branch path
        response = client.delete(f"{API_BASE}/repos/test_project/branches/feature%2Fissue-123")

        assert response.status_code == 200
        data = response.json()
        assert data["branch"] == "feature/issue-123"
        assert data["deleted"] is True


# =============================================================================
# Test: RepoManager.delete_branch method
# =============================================================================

class TestRepoManagerDeleteBranch:
    """Test RepoManager.delete_branch method directly."""

    def test_delete_branch_protected_main_raises(self):
        """Test delete_branch raises ValueError for main branch."""
        from git.repo_manager import RepoManager

        repo_manager = RepoManager()

        with pytest.raises(ValueError) as exc_info:
            repo_manager.delete_branch("test_project", "main")

        assert "Cannot delete protected branch: main" in str(exc_info.value)

    def test_delete_branch_protected_master_raises(self):
        """Test delete_branch raises ValueError for master branch."""
        from git.repo_manager import RepoManager

        repo_manager = RepoManager()

        with pytest.raises(ValueError) as exc_info:
            repo_manager.delete_branch("test_project", "master")

        assert "Cannot delete protected branch: master" in str(exc_info.value)
