"""Unit tests for project models."""

import pytest
from datetime import datetime, timezone

from models.project import (
    Project,
    ProjectStatus,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    RepoConfig,
    ProjectListResponse,
    ProjectStats
)


class TestProjectModel:
    """Tests for Project model."""

    def test_project_required_fields(self):
        """Project should have required fields."""
        project = Project(
            project_id="proj_abc123",
            name="Test Project"
        )
        assert project.project_id == "proj_abc123"
        assert project.name == "Test Project"

    def test_project_default_values(self):
        """Project should have sensible defaults."""
        project = Project(
            project_id="proj_abc123",
            name="Test Project"
        )
        assert project.description == ""
        assert project.status == ProjectStatus.ACTIVE
        assert project.icon is None
        assert project.icon_color is None
        assert project.labels == []
        assert project.repos == []
        assert project.primary_repo_id is None
        assert project.default_base_branch == "main"
        assert project.metadata == {}

    def test_project_with_icon(self):
        """Project can have an icon."""
        project = Project(
            project_id="proj_abc123",
            name="Test Project",
            icon="database",
            icon_color="#6366f1"
        )
        assert project.icon == "database"
        assert project.icon_color == "#6366f1"

    def test_project_with_labels(self):
        """Project can have labels."""
        project = Project(
            project_id="proj_abc123",
            name="Test Project",
            labels=["frontend", "production", "critical"]
        )
        assert project.labels == ["frontend", "production", "critical"]
        assert len(project.labels) == 3

    def test_project_with_all_visual_fields(self):
        """Project can have all visual identification fields."""
        project = Project(
            project_id="proj_abc123",
            name="My API Project",
            description="Backend API service",
            icon="server",
            icon_color="#22c55e",
            labels=["backend", "api", "production"]
        )
        assert project.icon == "server"
        assert project.icon_color == "#22c55e"
        assert project.labels == ["backend", "api", "production"]
        assert project.description == "Backend API service"

    def test_project_repo_count(self):
        """Project should calculate repo_count correctly."""
        project = Project(
            project_id="proj_abc123",
            name="Test Project",
            repos=[
                RepoConfig(repo_id="repo1", name="Repo 1", url="https://example.com/1"),
                RepoConfig(repo_id="repo2", name="Repo 2", url="https://example.com/2"),
            ]
        )
        assert project.repo_count == 2

    def test_project_primary_repo(self):
        """Project should return primary_repo correctly."""
        repo1 = RepoConfig(repo_id="repo1", name="Repo 1", url="https://example.com/1")
        repo2 = RepoConfig(repo_id="repo2", name="Repo 2", url="https://example.com/2")

        project = Project(
            project_id="proj_abc123",
            name="Test Project",
            repos=[repo1, repo2],
            primary_repo_id="repo2"
        )
        assert project.primary_repo.repo_id == "repo2"

    def test_project_primary_repo_fallback(self):
        """Project should fall back to first repo if no primary set."""
        repo1 = RepoConfig(repo_id="repo1", name="Repo 1", url="https://example.com/1")
        repo2 = RepoConfig(repo_id="repo2", name="Repo 2", url="https://example.com/2")

        project = Project(
            project_id="proj_abc123",
            name="Test Project",
            repos=[repo1, repo2]
        )
        assert project.primary_repo.repo_id == "repo1"


class TestProjectCreateRequest:
    """Tests for ProjectCreateRequest model."""

    def test_create_request_required_fields(self):
        """ProjectCreateRequest should require name."""
        request = ProjectCreateRequest(name="New Project")
        assert request.name == "New Project"

    def test_create_request_default_values(self):
        """ProjectCreateRequest should have sensible defaults."""
        request = ProjectCreateRequest(name="New Project")
        assert request.description is None
        assert request.icon is None
        assert request.icon_color is None
        assert request.labels == []
        assert request.metadata == {}

    def test_create_request_with_visual_fields(self):
        """ProjectCreateRequest can include icon and labels."""
        request = ProjectCreateRequest(
            name="New Project",
            description="A new project",
            icon="code",
            icon_color="#3b82f6",
            labels=["experimental", "frontend"]
        )
        assert request.icon == "code"
        assert request.icon_color == "#3b82f6"
        assert request.labels == ["experimental", "frontend"]

    def test_create_request_with_empty_labels(self):
        """ProjectCreateRequest handles empty labels list."""
        request = ProjectCreateRequest(
            name="New Project",
            labels=[]
        )
        assert request.labels == []


class TestProjectUpdateRequest:
    """Tests for ProjectUpdateRequest model."""

    def test_update_request_all_optional(self):
        """All fields in ProjectUpdateRequest should be optional."""
        request = ProjectUpdateRequest()
        assert request.name is None
        assert request.description is None
        assert request.status is None
        assert request.icon is None
        assert request.icon_color is None
        assert request.labels is None
        assert request.metadata is None

    def test_update_request_partial_update(self):
        """ProjectUpdateRequest can have partial fields."""
        request = ProjectUpdateRequest(
            name="Updated Name",
            icon="database"
        )
        assert request.name == "Updated Name"
        assert request.icon == "database"
        assert request.description is None
        assert request.labels is None

    def test_update_request_labels_only(self):
        """ProjectUpdateRequest can update just labels."""
        request = ProjectUpdateRequest(
            labels=["new-label", "another-label"]
        )
        assert request.labels == ["new-label", "another-label"]
        assert request.name is None
        assert request.icon is None

    def test_update_request_icon_and_color(self):
        """ProjectUpdateRequest can update icon and color together."""
        request = ProjectUpdateRequest(
            icon="shield",
            icon_color="#ef4444"
        )
        assert request.icon == "shield"
        assert request.icon_color == "#ef4444"

    def test_update_request_clear_labels(self):
        """ProjectUpdateRequest can set labels to empty list."""
        request = ProjectUpdateRequest(labels=[])
        assert request.labels == []


class TestProjectListResponse:
    """Tests for ProjectListResponse model."""

    def test_list_response_with_projects(self):
        """ProjectListResponse should list projects correctly."""
        projects = [
            Project(
                project_id="proj_1",
                name="Project 1",
                icon="code",
                labels=["frontend"]
            ),
            Project(
                project_id="proj_2",
                name="Project 2",
                icon="database",
                labels=["backend", "production"]
            )
        ]
        response = ProjectListResponse(items=projects, total=2)
        assert len(response.items) == 2
        assert response.total == 2
        assert response.items[0].icon == "code"
        assert response.items[1].labels == ["backend", "production"]

    def test_list_response_empty(self):
        """ProjectListResponse can be empty."""
        response = ProjectListResponse(items=[], total=0)
        assert len(response.items) == 0
        assert response.total == 0


class TestProjectStats:
    """Tests for ProjectStats model."""

    def test_stats_structure(self):
        """ProjectStats should have correct structure."""
        stats = ProjectStats(
            total=5,
            by_status={"active": 3, "archived": 2},
            total_repos=10
        )
        assert stats.total == 5
        assert stats.by_status["active"] == 3
        assert stats.by_status["archived"] == 2
        assert stats.total_repos == 10
