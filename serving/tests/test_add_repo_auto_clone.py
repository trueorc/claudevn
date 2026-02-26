"""Unit tests for auto-clone behavior in ProjectService.add_repo()."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.project import (
    Project, RepoAddRequest, RepoCreateInternalRequest, RepoSyncResponse
)
from services.project_service import ProjectService

# Patch targets: local imports resolve names from source modules
PATCH_GET_SYNC = "services.repo_sync_service.get_repo_sync_service"
PATCH_GET_RM = "api.git.get_repo_manager"


@pytest.fixture
def project_service():
    """Create a ProjectService with no Redis."""
    service = ProjectService(redis_client=None)
    service._initialized = True
    return service


@pytest.fixture
def project(project_service):
    """Create a test project in the service."""
    proj = Project(
        project_id="proj_test123",
        name="Test Project",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    project_service._projects["proj_test123"] = proj
    return proj


@pytest.fixture
def repo_add_request():
    """Create a standard repo add request."""
    return RepoAddRequest(
        name="my-repo",
        url="https://github.com/org/my-repo.git",
        default_branch="main",
        ssh_key_id="key_abc",
        metadata={"custom": "value"},
    )


def _mock_sync_service(success=False, message="skip"):
    """Create a mock RepoSyncService with clone_repo returning given result."""
    mock_sync = MagicMock()
    mock_sync.clone_repo = AsyncMock(
        return_value=RepoSyncResponse(
            repo_id="ignored",
            project_id="proj_test123",
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
        "http://serving:8002/git/proj_test123_repo_test.git"
    )
    return mock_rm


class TestAddRepoMetadata:
    """Tests for metadata set during add_repo."""

    @pytest.mark.asyncio
    async def test_git_project_name_stored(
        self, project_service, project, repo_add_request
    ):
        """add_repo should store git_project_name in metadata."""
        mock_sync = _mock_sync_service(success=False)

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert repo is not None
        assert repo.metadata["git_project_name"] == f"proj_test123_{repo.repo_id}"

    @pytest.mark.asyncio
    async def test_origin_url_preserved(
        self, project_service, project, repo_add_request
    ):
        """add_repo should store original URL as origin_url in metadata."""
        mock_sync = _mock_sync_service(success=False)

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert repo.metadata["origin_url"] == "https://github.com/org/my-repo.git"

    @pytest.mark.asyncio
    async def test_custom_metadata_preserved(
        self, project_service, project, repo_add_request
    ):
        """add_repo should preserve user-provided metadata alongside new fields."""
        mock_sync = _mock_sync_service(success=False)

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert repo.metadata["custom"] == "value"
        assert "git_project_name" in repo.metadata
        assert "origin_url" in repo.metadata


class TestAddRepoAutoClone:
    """Tests for auto-clone behavior on add_repo."""

    @pytest.mark.asyncio
    async def test_clone_called_on_add(
        self, project_service, project, repo_add_request
    ):
        """add_repo should call RepoSyncService.clone_repo."""
        mock_sync = _mock_sync_service(success=True)
        mock_rm = _mock_repo_manager()

        with patch(PATCH_GET_SYNC, return_value=mock_sync), \
             patch(PATCH_GET_RM, return_value=mock_rm):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        mock_sync.clone_repo.assert_awaited_once_with("proj_test123", repo.repo_id)

    @pytest.mark.asyncio
    async def test_url_updated_on_successful_clone(
        self, project_service, project, repo_add_request
    ):
        """On successful clone, repo.url should be updated to internal URL."""
        mock_sync = _mock_sync_service(success=True)
        mock_rm = _mock_repo_manager()

        with patch(PATCH_GET_SYNC, return_value=mock_sync), \
             patch(PATCH_GET_RM, return_value=mock_rm):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert "serving:8002" in repo.url
        assert repo.metadata["origin_url"] == "https://github.com/org/my-repo.git"

    @pytest.mark.asyncio
    async def test_url_unchanged_on_failed_clone(
        self, project_service, project, repo_add_request
    ):
        """On failed clone, repo.url should remain the original external URL."""
        mock_sync = _mock_sync_service(success=False, message="Auth failed")

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert repo.url == "https://github.com/org/my-repo.git"

    @pytest.mark.asyncio
    async def test_repo_added_even_on_clone_exception(
        self, project_service, project, repo_add_request
    ):
        """If clone raises an exception, repo should still be added."""
        with patch(PATCH_GET_SYNC, side_effect=RuntimeError("service unavailable")):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert repo is not None
        assert repo.repo_id in [r.repo_id for r in project.repos]
        assert repo.url == "https://github.com/org/my-repo.git"

    @pytest.mark.asyncio
    async def test_repo_is_primary_when_first(
        self, project_service, project, repo_add_request
    ):
        """First repo added should become primary."""
        mock_sync = _mock_sync_service(success=False)

        with patch(PATCH_GET_SYNC, return_value=mock_sync):
            repo = await project_service.add_repo("proj_test123", repo_add_request)

        assert project.primary_repo_id == repo.repo_id


class TestCreateInternalRepoUnchanged:
    """Verify create_internal_repo is not regressed."""

    @pytest.mark.asyncio
    async def test_create_internal_repo_still_works(self, project_service, project):
        """create_internal_repo should work as before (no auto-clone)."""
        request = RepoCreateInternalRequest(name="internal-repo")
        mock_rm = _mock_repo_manager()

        with patch(PATCH_GET_RM, return_value=mock_rm):
            repo = await project_service.create_internal_repo(
                "proj_test123", request
            )

        assert repo is not None
        assert repo.is_internal is True
        assert "git_project_name" in repo.metadata
        mock_rm.create_repo.assert_called_once()
