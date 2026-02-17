"""Tests for internal Git repository creation.

Tests the create_internal_repo() service method, remove_repo() cleanup,
API endpoint, and backward compatibility.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.project_service import ProjectService
from models.project import (
    ProjectCreateRequest, RepoAddRequest,
    RepoCreateInternalRequest, RepoConfig
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service():
    """Create a ProjectService for testing (no Redis)."""
    return ProjectService()


@pytest.fixture
def create_request():
    """Create a basic project create request."""
    return ProjectCreateRequest(
        name="Test Project",
        description="A test project"
    )


@pytest.fixture
def mock_repo_manager():
    """Create a mock RepoManager."""
    manager = MagicMock()
    manager.create_repo.return_value = "/repos/test.git"
    manager.get_repo_url.return_value = "git@localhost:/repos/test.git"
    manager.delete_repo.return_value = True
    return manager


@pytest.fixture
def mock_ssh_server():
    """Create a mock SSH server."""
    server = MagicMock()
    server.get_clone_url.return_value = "ssh://git@serving:2222/repos/test.git"
    return server


def _patch_git(mock_repo_manager, mock_ssh_server=None):
    """Return context managers to patch git dependencies used by project_service."""
    return (
        patch("api.git.get_repo_manager", return_value=mock_repo_manager),
        patch("git.ssh_server.get_ssh_server", return_value=mock_ssh_server),
    )


# =============================================================================
# Test: create_internal_repo() service method
# =============================================================================

class TestCreateInternalRepo:
    """Test creating internal Git repositories."""

    @pytest.mark.asyncio
    async def test_create_internal_repo_with_ssh(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test creating an internal repo uses SSH URL when available."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo")
            )

        assert repo is not None
        assert repo.repo_id.startswith("repo_")
        assert repo.name == "my-repo"
        assert repo.is_internal is True
        assert repo.url == "ssh://git@serving:2222/repos/test.git"
        assert repo.default_branch == "main"
        assert "git_project_name" in repo.metadata

    @pytest.mark.asyncio
    async def test_create_internal_repo_without_ssh(
        self, service, create_request, mock_repo_manager
    ):
        """Test creating an internal repo falls back to local URL without SSH server."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, None)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo")
            )

        assert repo is not None
        assert repo.url == "git@localhost:/repos/test.git"

    @pytest.mark.asyncio
    async def test_create_internal_repo_custom_branch(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test creating an internal repo with custom default branch."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo", default_branch="develop")
            )

        assert repo.default_branch == "develop"

    @pytest.mark.asyncio
    async def test_create_internal_repo_sets_primary_if_first(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that first internal repo becomes primary."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="first-repo")
            )

        updated = await service.get_project(project.project_id)
        assert updated.primary_repo_id == repo.repo_id

    @pytest.mark.asyncio
    async def test_create_internal_repo_second_not_primary(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that second internal repo doesn't override primary."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            first = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="first")
            )
            await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="second")
            )

        updated = await service.get_project(project.project_id)
        assert updated.primary_repo_id == first.repo_id
        assert len(updated.repos) == 2

    @pytest.mark.asyncio
    async def test_create_internal_repo_nonexistent_project(
        self, service, mock_repo_manager, mock_ssh_server
    ):
        """Test creating internal repo for non-existent project returns None."""
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            result = await service.create_internal_repo(
                "nonexistent",
                RepoCreateInternalRequest(name="my-repo")
            )

        assert result is None
        mock_repo_manager.create_repo.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_internal_repo_calls_repo_manager(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that create_internal_repo calls RepoManager.create_repo."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo")
            )

        git_project_name = repo.metadata["git_project_name"]
        assert git_project_name.startswith(project.project_id)
        mock_repo_manager.create_repo.assert_called_once_with(git_project_name)

    @pytest.mark.asyncio
    async def test_create_internal_repo_stores_git_project_name(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that git_project_name is stored in repo metadata."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo")
            )

        git_name = repo.metadata["git_project_name"]
        assert project.project_id in git_name
        assert repo.repo_id in git_name


# =============================================================================
# Test: remove_repo() cleanup for internal repos
# =============================================================================

class TestRemoveInternalRepo:
    """Test that remove_repo cleans up internal Git repos."""

    @pytest.mark.asyncio
    async def test_remove_internal_repo_deletes_git_repo(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that removing an internal repo deletes the bare Git repo."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo")
            )
            git_project_name = repo.metadata["git_project_name"]

            # Reset mock to track delete call separately
            mock_repo_manager.reset_mock()

            await service.remove_repo(project.project_id, repo.repo_id)

        mock_repo_manager.delete_repo.assert_called_once_with(git_project_name)

    @pytest.mark.asyncio
    async def test_remove_external_repo_no_cleanup(
        self, service, create_request
    ):
        """Test that removing an external repo doesn't attempt Git cleanup."""
        project = await service.create_project(create_request)

        repo = await service.add_repo(
            project.project_id,
            RepoAddRequest(name="ext-repo", url="https://github.com/org/repo.git")
        )

        # Should not raise or try to import git modules
        result = await service.remove_repo(project.project_id, repo.repo_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_internal_repo_handles_cleanup_error(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that cleanup errors are logged but don't fail removal."""
        project = await service.create_project(create_request)
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)

        with p1, p2:
            repo = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="my-repo")
            )

            # Make delete fail
            mock_repo_manager.delete_repo.side_effect = Exception("disk error")

            result = await service.remove_repo(project.project_id, repo.repo_id)

        # Removal should still succeed
        assert result is True
        updated = await service.get_project(project.project_id)
        assert len(updated.repos) == 0


# =============================================================================
# Test: Backward compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Test that existing add_repo still works with is_internal=False."""

    @pytest.mark.asyncio
    async def test_external_repo_not_internal(self, service, create_request):
        """Test that repos added via add_repo have is_internal=False."""
        project = await service.create_project(create_request)

        repo = await service.add_repo(
            project.project_id,
            RepoAddRequest(name="ext", url="https://github.com/org/repo.git")
        )

        assert repo.is_internal is False

    @pytest.mark.asyncio
    async def test_repo_config_default_is_internal_false(self):
        """Test that RepoConfig defaults is_internal to False."""
        repo = RepoConfig(
            repo_id="repo_test",
            name="test",
            url="https://example.com/repo.git"
        )

        assert repo.is_internal is False

    @pytest.mark.asyncio
    async def test_mixed_repos_in_project(
        self, service, create_request, mock_repo_manager, mock_ssh_server
    ):
        """Test that a project can have both internal and external repos."""
        project = await service.create_project(create_request)

        # Add external repo
        ext = await service.add_repo(
            project.project_id,
            RepoAddRequest(name="external", url="https://github.com/org/repo.git")
        )

        # Add internal repo
        p1, p2 = _patch_git(mock_repo_manager, mock_ssh_server)
        with p1, p2:
            internal = await service.create_internal_repo(
                project.project_id,
                RepoCreateInternalRequest(name="internal")
            )

        updated = await service.get_project(project.project_id)
        assert len(updated.repos) == 2
        assert ext.is_internal is False
        assert internal.is_internal is True


# =============================================================================
# Test: API endpoint
# =============================================================================

class TestCreateInternalRepoAPI:
    """Test POST /{project_id}/repos/internal endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client using the main app."""
        from fastapi.testclient import TestClient
        from app import app
        return TestClient(app)

    @pytest.fixture
    def mock_project_service(self):
        """Mock the project service singleton."""
        import services.project_service as module
        original = module._project_service
        mock_svc = MagicMock()
        module._project_service = mock_svc
        yield mock_svc
        module._project_service = original

    def test_create_internal_repo_201(self, client, mock_project_service):
        """Test successful creation returns 201."""
        mock_repo = RepoConfig(
            repo_id="repo_abc12345",
            name="my-repo",
            url="ssh://git@serving:2222/repos/test.git",
            default_branch="main",
            is_internal=True,
            metadata={"git_project_name": "proj_test_repo_abc12345"}
        )
        mock_project_service.create_internal_repo = AsyncMock(return_value=mock_repo)

        response = client.post(
            "/api/v1/projects/proj_test123/repos/internal",
            json={"name": "my-repo"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "my-repo"
        assert data["is_internal"] is True
        assert data["url"] == "ssh://git@serving:2222/repos/test.git"
        assert data["repo_id"] == "repo_abc12345"

    def test_create_internal_repo_404_project_not_found(
        self, client, mock_project_service
    ):
        """Test 404 when project doesn't exist."""
        mock_project_service.create_internal_repo = AsyncMock(return_value=None)

        response = client.post(
            "/api/v1/projects/nonexistent/repos/internal",
            json={"name": "my-repo"}
        )

        assert response.status_code == 404

    def test_create_internal_repo_with_custom_branch(
        self, client, mock_project_service
    ):
        """Test creation with custom default branch."""
        mock_repo = RepoConfig(
            repo_id="repo_abc12345",
            name="my-repo",
            url="ssh://git@serving:2222/repos/test.git",
            default_branch="develop",
            is_internal=True
        )
        mock_project_service.create_internal_repo = AsyncMock(return_value=mock_repo)

        response = client.post(
            "/api/v1/projects/proj_test123/repos/internal",
            json={"name": "my-repo", "default_branch": "develop"}
        )

        assert response.status_code == 201
        assert response.json()["default_branch"] == "develop"

    def test_existing_add_repo_still_works(self, client, mock_project_service):
        """Test that the existing add_repo endpoint still functions."""
        mock_repo = RepoConfig(
            repo_id="repo_ext12345",
            name="ext-repo",
            url="https://github.com/org/repo.git",
            default_branch="main",
            is_internal=False
        )
        mock_project_service.add_repo = AsyncMock(return_value=mock_repo)

        response = client.post(
            "/api/v1/projects/proj_test123/repos",
            json={
                "name": "ext-repo",
                "url": "https://github.com/org/repo.git"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_internal"] is False
        assert data["name"] == "ext-repo"
