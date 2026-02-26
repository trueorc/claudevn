"""Unit tests for atomic repo creation during project creation (issue #61).

Tests that create_project() with repos field creates/links repos atomically
and surfaces clone errors in repo metadata.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.project import (
    Project, PendingRepoRequest, ProjectCreateRequest,
    RepoSyncResponse,
)
from services.project_service import ProjectService

PATCH_GET_SYNC = "services.repo_sync_service.get_repo_sync_service"
PATCH_GET_RM = "api.git.get_repo_manager"


@pytest.fixture
def project_service():
    """Create a ProjectService with no Redis."""
    service = ProjectService(redis_client=None)
    service._initialized = True
    return service


def _mock_sync_service(success=True, message="ok"):
    """Create a mock RepoSyncService."""
    mock_sync = MagicMock()
    mock_sync.clone_repo = AsyncMock(
        return_value=RepoSyncResponse(
            repo_id="ignored",
            project_id="ignored",
            operation="clone",
            success=success,
            message=message,
        )
    )
    return mock_sync


def _mock_repo_manager():
    """Create a mock RepoManager."""
    mock_rm = MagicMock()
    mock_rm.get_repo_url.return_value = (
        "http://serving:8002/git/test.git"
    )
    return mock_rm


class TestCreateProjectWithoutRepos:
    """Verify create_project still works with no repos (backward compat)."""

    @pytest.mark.asyncio
    async def test_create_project_no_repos(self, project_service):
        """Creating a project with no repos should work as before."""
        request = ProjectCreateRequest(
            name="My Project",
            description="A test project",
        )

        project = await project_service.create_project(request)

        assert project.name == "My Project"
        assert project.description == "A test project"
        assert len(project.repos) == 0
        assert project.project_id in project_service._projects

    @pytest.mark.asyncio
    async def test_create_project_empty_repos_list(self, project_service):
        """Creating a project with empty repos list works."""
        request = ProjectCreateRequest(
            name="My Project",
            repos=[],
        )

        project = await project_service.create_project(request)

        assert len(project.repos) == 0


class TestCreateProjectWithInternalRepo:
    """Test creating a project with internal (create mode) repos."""

    @pytest.mark.asyncio
    async def test_internal_repo_created(self, project_service):
        """Internal repo should be created during project creation."""
        mock_rm = _mock_repo_manager()

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="create",
                    name="my-internal-repo",
                    default_branch="main",
                ),
            ],
        )

        with patch(PATCH_GET_RM, return_value=mock_rm):
            project = await project_service.create_project(request)

        assert len(project.repos) == 1
        assert project.repos[0].name == "my-internal-repo"
        assert project.repos[0].is_internal is True
        mock_rm.create_repo.assert_called_once()

    @pytest.mark.asyncio
    async def test_internal_repo_is_primary(self, project_service):
        """First repo should become primary."""
        mock_rm = _mock_repo_manager()

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(mode="create", name="repo-1"),
            ],
        )

        with patch(PATCH_GET_RM, return_value=mock_rm):
            project = await project_service.create_project(request)

        assert project.primary_repo_id == project.repos[0].repo_id


class TestCreateProjectWithLinkedRepo:
    """Test creating a project with linked (external) repos."""

    @pytest.mark.asyncio
    async def test_linked_repo_cloned_on_success(self, project_service):
        """Linked repo should be cloned atomically during creation."""
        mock_sync = _mock_sync_service(success=True)
        mock_rm = _mock_repo_manager()

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="link",
                    name="ext-repo",
                    url="https://github.com/org/ext-repo.git",
                    default_branch="main",
                ),
            ],
        )

        with patch(PATCH_GET_SYNC, return_value=mock_sync), \
             patch(PATCH_GET_RM, return_value=mock_rm):
            project = await project_service.create_project(request)

        assert len(project.repos) == 1
        assert project.repos[0].name == "ext-repo"
        mock_sync.clone_repo.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clone_error_recorded_in_metadata(self, project_service):
        """Clone failure should be recorded in repo metadata, not raise."""
        mock_sync = _mock_sync_service(
            success=False, message="Authentication failed"
        )

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="link",
                    name="ext-repo",
                    url="https://github.com/org/ext-repo.git",
                ),
            ],
        )

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            project = await project_service.create_project(request)

        assert len(project.repos) == 1
        repo = project.repos[0]
        assert repo.metadata.get("clone_error") == "Authentication failed"

    @pytest.mark.asyncio
    async def test_project_created_even_on_clone_failure(self, project_service):
        """Project should still be created even if clone fails."""
        mock_sync = _mock_sync_service(success=False, message="Timeout")

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="link",
                    name="ext-repo",
                    url="https://github.com/org/ext-repo.git",
                ),
            ],
        )

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            project = await project_service.create_project(request)

        assert project is not None
        assert project.project_id in project_service._projects
        assert project.name == "My Project"


class TestCreateProjectWithMixedRepos:
    """Test creating a project with both internal and linked repos."""

    @pytest.mark.asyncio
    async def test_mixed_repos_created(self, project_service):
        """Both internal and linked repos should be created."""
        mock_sync = _mock_sync_service(success=True)
        mock_rm = _mock_repo_manager()

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="create",
                    name="internal-repo",
                ),
                PendingRepoRequest(
                    mode="link",
                    name="linked-repo",
                    url="https://github.com/org/linked.git",
                ),
            ],
        )

        with patch(PATCH_GET_SYNC, return_value=mock_sync), \
             patch(PATCH_GET_RM, return_value=mock_rm):
            project = await project_service.create_project(request)

        assert len(project.repos) == 2
        names = [r.name for r in project.repos]
        assert "internal-repo" in names
        assert "linked-repo" in names

    @pytest.mark.asyncio
    async def test_first_repo_is_primary(self, project_service):
        """First repo (internal) should be primary."""
        mock_sync = _mock_sync_service(success=True)
        mock_rm = _mock_repo_manager()

        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(mode="create", name="first-repo"),
                PendingRepoRequest(
                    mode="link",
                    name="second-repo",
                    url="https://github.com/org/second.git",
                ),
            ],
        )

        with patch(PATCH_GET_SYNC, return_value=mock_sync), \
             patch(PATCH_GET_RM, return_value=mock_rm):
            project = await project_service.create_project(request)

        primary = next(
            r for r in project.repos if r.repo_id == project.primary_repo_id
        )
        assert primary.name == "first-repo"


class TestCreateProjectRepoEdgeCases:
    """Test edge cases for repo creation during project creation."""

    @pytest.mark.asyncio
    async def test_invalid_mode_skipped(self, project_service):
        """Invalid repo mode should be skipped without failing."""
        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="invalid",
                    name="bad-repo",
                ),
            ],
        )

        project = await project_service.create_project(request)

        assert project is not None
        assert len(project.repos) == 0

    @pytest.mark.asyncio
    async def test_link_without_url_skipped(self, project_service):
        """Link mode without URL should be skipped."""
        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="link",
                    name="no-url-repo",
                    url=None,
                ),
            ],
        )

        project = await project_service.create_project(request)

        assert len(project.repos) == 0

    @pytest.mark.asyncio
    async def test_repo_exception_doesnt_break_creation(self, project_service):
        """Exception during repo processing should not fail project creation."""
        request = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(
                    mode="create",
                    name="will-fail",
                ),
            ],
        )

        # Mock create_internal_repo to raise
        with patch.object(
            project_service,
            "create_internal_repo",
            side_effect=RuntimeError("boom"),
        ):
            project = await project_service.create_project(request)

        assert project is not None
        assert project.project_id in project_service._projects


class TestPendingRepoRequestModel:
    """Test the PendingRepoRequest model validation."""

    def test_create_mode(self):
        """Create mode should work without URL."""
        req = PendingRepoRequest(mode="create", name="test-repo")
        assert req.mode == "create"
        assert req.url is None
        assert req.default_branch == "main"

    def test_link_mode(self):
        """Link mode with URL should work."""
        req = PendingRepoRequest(
            mode="link",
            name="ext-repo",
            url="https://github.com/org/repo.git",
            default_branch="develop",
        )
        assert req.mode == "link"
        assert req.url == "https://github.com/org/repo.git"
        assert req.default_branch == "develop"

    def test_project_create_request_with_repos(self):
        """ProjectCreateRequest should accept repos field."""
        req = ProjectCreateRequest(
            name="My Project",
            repos=[
                PendingRepoRequest(mode="create", name="repo-1"),
                PendingRepoRequest(
                    mode="link",
                    name="repo-2",
                    url="https://example.com/repo.git",
                ),
            ],
        )
        assert len(req.repos) == 2

    def test_project_create_request_without_repos(self):
        """ProjectCreateRequest should default repos to empty list."""
        req = ProjectCreateRequest(name="My Project")
        assert req.repos == []
