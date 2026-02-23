"""Tests for repository sync service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from models.project import (
    Project, RepoConfig, RepoCloneStatus,
    RepoStatusResponse, RepoSyncResponse
)
from services.repo_sync_service import RepoSyncService


@pytest.fixture
def mock_repo_manager():
    """Create a mock repo manager."""
    manager = MagicMock()
    manager.repo_exists.return_value = False
    manager.clone_from_url.return_value = "/path/to/repo"
    manager.pull_from_origin.return_value = {"success": True, "output": "Updated"}
    manager.push_to_origin.return_value = {"success": True, "output": "Pushed"}
    manager.get_repo_status.return_value = {
        "path": "/path/to/repo",
        "origin_url": "git@github.com:test/repo.git",
        "default_branch": "main",
        "branches": ["main", "develop"],
        "branch_count": 2,
        "is_mirror": False,
        "is_linked": True
    }
    return manager


@pytest.fixture
def sample_project():
    """Create a sample project with repos."""
    return Project(
        project_id="proj-123",
        name="Test Project",
        repos=[
            RepoConfig(
                repo_id="repo-1",
                name="test-repo",
                url="git@github.com:test/repo.git",
                default_branch="main",
                ssh_key_id="key-1"
            )
        ]
    )


@pytest.fixture
def sync_service(mock_repo_manager):
    """Create a sync service with mocked dependencies."""
    with patch("services.repo_sync_service.get_config") as mock_config:
        mock_config.return_value.git.ssh_keys_path = "/tmp/ssh_keys"
        service = RepoSyncService(repo_manager=mock_repo_manager)
    return service


class TestRepoSyncService:
    """Test RepoSyncService class."""

    @pytest.mark.asyncio
    async def test_clone_repo_success(self, sync_service, sample_project, mock_repo_manager):
        """Test successful repository clone."""
        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_service._save_project.return_value = None
            mock_ps.return_value = mock_service

            result = await sync_service.clone_repo("proj-123", "repo-1")

            assert result.success is True
            assert result.operation == "clone"
            mock_repo_manager.clone_from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_clone_repo_project_not_found(self, sync_service):
        """Test clone when project doesn't exist."""
        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = None
            mock_ps.return_value = mock_service

            result = await sync_service.clone_repo("nonexistent", "repo-1")

            assert result.success is False
            assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_clone_repo_repo_not_found(self, sync_service, sample_project):
        """Test clone when repo doesn't exist in project."""
        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_ps.return_value = mock_service

            result = await sync_service.clone_repo("proj-123", "nonexistent-repo")

            assert result.success is False
            assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_clone_repo_already_exists(self, sync_service, sample_project, mock_repo_manager):
        """Test clone when repo already exists locally."""
        mock_repo_manager.repo_exists.return_value = True

        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_ps.return_value = mock_service

            result = await sync_service.clone_repo("proj-123", "repo-1")

            assert result.success is False
            assert "already cloned" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pull_repo_success(self, sync_service, sample_project, mock_repo_manager):
        """Test successful repository pull."""
        mock_repo_manager.repo_exists.return_value = True

        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_service._save_project.return_value = None
            mock_ps.return_value = mock_service

            result = await sync_service.pull_repo("proj-123", "repo-1")

            assert result.success is True
            assert result.operation == "pull"
            mock_repo_manager.pull_from_origin.assert_called_once()

    @pytest.mark.asyncio
    async def test_pull_repo_not_cloned(self, sync_service, sample_project, mock_repo_manager):
        """Test pull when repo not cloned."""
        mock_repo_manager.repo_exists.return_value = False

        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_ps.return_value = mock_service

            result = await sync_service.pull_repo("proj-123", "repo-1")

            assert result.success is False
            assert "not cloned" in result.message.lower()

    @pytest.mark.asyncio
    async def test_push_to_origin_success(self, sync_service, sample_project, mock_repo_manager):
        """Test successful branch push."""
        mock_repo_manager.repo_exists.return_value = True

        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_service._save_project.return_value = None
            mock_ps.return_value = mock_service

            result = await sync_service.push_to_origin("proj-123", "repo-1", "feature/test")

            assert result.success is True
            assert result.operation == "push"
            mock_repo_manager.push_to_origin.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_repo_status_not_cloned(self, sync_service, sample_project, mock_repo_manager):
        """Test status when repo not cloned."""
        mock_repo_manager.repo_exists.return_value = False

        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_ps.return_value = mock_service

            result = await sync_service.get_repo_status("proj-123", "repo-1")

            assert result is not None
            assert result.clone_status == RepoCloneStatus.NOT_CLONED

    @pytest.mark.asyncio
    async def test_get_repo_status_cloned(self, sync_service, sample_project, mock_repo_manager):
        """Test status when repo is cloned."""
        mock_repo_manager.repo_exists.return_value = True
        sample_project.repos[0].metadata["last_sync"] = datetime.now(timezone.utc).isoformat()

        with patch("services.repo_sync_service.get_project_service") as mock_ps:
            mock_service = AsyncMock()
            mock_service.get_project.return_value = sample_project
            mock_ps.return_value = mock_service

            result = await sync_service.get_repo_status("proj-123", "repo-1")

            assert result is not None
            assert result.clone_status == RepoCloneStatus.CLONED
            assert result.branch_count == 2
            assert result.is_mirror is False
            assert result.is_linked is True


class TestLocalNameGeneration:
    """Test local repo name generation."""

    def test_get_repo_local_name(self, sync_service):
        """Test local name format."""
        name = sync_service._get_repo_local_name("proj-123", "repo-1")
        assert name == "proj-123_repo-1"
