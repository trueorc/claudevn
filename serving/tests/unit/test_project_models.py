"""Tests for project models.

Comprehensive unit tests for Pydantic models in the project module.
Tests validation, defaults, enums, and model behaviors.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from models.project import (
    ProjectStatus, RepoCloneStatus,
    RepoConfig, Project, ProjectCreateRequest, ProjectUpdateRequest,
    RepoAddRequest, ProjectListResponse, ProjectStats,
    RepoStatusResponse, RepoSyncResponse
)


# =============================================================================
# Test: Enums
# =============================================================================

class TestProjectStatusEnum:
    """Test ProjectStatus enum."""

    def test_project_status_values(self):
        """Test all ProjectStatus enum values."""
        assert ProjectStatus.ACTIVE == "active"
        assert ProjectStatus.ARCHIVED == "archived"
        assert ProjectStatus.SUSPENDED == "suspended"

    def test_project_status_from_string(self):
        """Test creating ProjectStatus from string."""
        assert ProjectStatus("active") == ProjectStatus.ACTIVE
        assert ProjectStatus("archived") == ProjectStatus.ARCHIVED

    def test_project_status_invalid(self):
        """Test invalid ProjectStatus value."""
        with pytest.raises(ValueError):
            ProjectStatus("deleted")


class TestRepoCloneStatusEnum:
    """Test RepoCloneStatus enum."""

    def test_repo_clone_status_values(self):
        """Test all RepoCloneStatus enum values."""
        assert RepoCloneStatus.NOT_CLONED == "not_cloned"
        assert RepoCloneStatus.CLONING == "cloning"
        assert RepoCloneStatus.CLONED == "cloned"
        assert RepoCloneStatus.ERROR == "error"


# =============================================================================
# Test: RepoConfig Model
# =============================================================================

class TestRepoConfigModel:
    """Test RepoConfig model."""

    def test_repo_config_required_fields(self):
        """Test repo config with required fields."""
        config = RepoConfig(
            repo_id="repo_001",
            name="my-repo",
            url="https://github.com/org/my-repo.git"
        )

        assert config.repo_id == "repo_001"
        assert config.name == "my-repo"
        assert config.url == "https://github.com/org/my-repo.git"

    def test_repo_config_missing_required(self):
        """Test repo config validation for missing fields."""
        with pytest.raises(ValidationError):
            RepoConfig(
                repo_id="repo_001",
                name="my-repo"
                # Missing url
            )

    def test_repo_config_defaults(self):
        """Test repo config default values."""
        config = RepoConfig(
            repo_id="repo_001",
            name="my-repo",
            url="https://github.com/org/my-repo.git"
        )

        assert config.default_branch == "main"
        assert config.path is None
        assert config.ssh_key_id is None
        assert config.metadata == {}
        assert isinstance(config.added_at, datetime)

    def test_repo_config_custom_values(self):
        """Test repo config with custom values."""
        config = RepoConfig(
            repo_id="repo_001",
            name="my-repo",
            url="git@github.com:org/my-repo.git",
            default_branch="develop",
            path="/var/repos/my-repo",
            ssh_key_id="key_abc",
            metadata={"private": True}
        )

        assert config.default_branch == "develop"
        assert config.path == "/var/repos/my-repo"
        assert config.ssh_key_id == "key_abc"
        assert config.metadata["private"] is True


# =============================================================================
# Test: Project Model
# =============================================================================

class TestProjectModel:
    """Test Project model."""

    def test_project_required_fields(self):
        """Test project with required fields."""
        project = Project(
            project_id="proj_001",
            name="My Project"
        )

        assert project.project_id == "proj_001"
        assert project.name == "My Project"

    def test_project_missing_required(self):
        """Test project validation for missing fields."""
        with pytest.raises(ValidationError):
            Project(name="Missing project_id")

    def test_project_defaults(self):
        """Test project default values."""
        project = Project(
            project_id="proj_001",
            name="My Project"
        )

        assert project.description == ""
        assert project.status == ProjectStatus.ACTIVE
        assert project.repos == []
        assert project.primary_repo_id is None
        assert project.default_base_branch == "main"
        assert project.work_branch_pattern == "{type}/{task}/{compute-id}"
        assert project.metadata == {}
        assert isinstance(project.created_at, datetime)
        assert isinstance(project.updated_at, datetime)

    def test_project_repo_count_empty(self):
        """Test repo_count property when empty."""
        project = Project(
            project_id="proj_001",
            name="My Project"
        )

        assert project.repo_count == 0

    def test_project_repo_count_with_repos(self):
        """Test repo_count property with repos."""
        repo1 = RepoConfig(
            repo_id="repo_001",
            name="repo1",
            url="https://github.com/org/repo1.git"
        )
        repo2 = RepoConfig(
            repo_id="repo_002",
            name="repo2",
            url="https://github.com/org/repo2.git"
        )

        project = Project(
            project_id="proj_001",
            name="My Project",
            repos=[repo1, repo2]
        )

        assert project.repo_count == 2

    def test_project_primary_repo_none(self):
        """Test primary_repo when no repos exist."""
        project = Project(
            project_id="proj_001",
            name="My Project"
        )

        assert project.primary_repo is None

    def test_project_primary_repo_first_default(self):
        """Test primary_repo defaults to first repo."""
        repo = RepoConfig(
            repo_id="repo_001",
            name="repo1",
            url="https://github.com/org/repo1.git"
        )

        project = Project(
            project_id="proj_001",
            name="My Project",
            repos=[repo]
        )

        assert project.primary_repo is not None
        assert project.primary_repo.repo_id == "repo_001"

    def test_project_primary_repo_explicit(self):
        """Test primary_repo with explicit primary_repo_id."""
        repo1 = RepoConfig(
            repo_id="repo_001",
            name="repo1",
            url="https://github.com/org/repo1.git"
        )
        repo2 = RepoConfig(
            repo_id="repo_002",
            name="repo2",
            url="https://github.com/org/repo2.git"
        )

        project = Project(
            project_id="proj_001",
            name="My Project",
            repos=[repo1, repo2],
            primary_repo_id="repo_002"
        )

        assert project.primary_repo.repo_id == "repo_002"

    def test_project_primary_repo_invalid_id(self):
        """Test primary_repo with non-existent primary_repo_id."""
        repo = RepoConfig(
            repo_id="repo_001",
            name="repo1",
            url="https://github.com/org/repo1.git"
        )

        project = Project(
            project_id="proj_001",
            name="My Project",
            repos=[repo],
            primary_repo_id="nonexistent"
        )

        assert project.primary_repo is None


# =============================================================================
# Test: ProjectCreateRequest Model
# =============================================================================

class TestProjectCreateRequestModel:
    """Test ProjectCreateRequest model."""

    def test_create_request_required_fields(self):
        """Test create request with required fields."""
        request = ProjectCreateRequest(name="New Project")

        assert request.name == "New Project"

    def test_create_request_defaults(self):
        """Test create request default values."""
        request = ProjectCreateRequest(name="New Project")

        assert request.description is None
        assert request.metadata == {}

    def test_create_request_custom_values(self):
        """Test create request with custom values."""
        request = ProjectCreateRequest(
            name="My Project",
            description="A detailed description",
            metadata={"team": "platform", "priority": "high"}
        )

        assert request.description == "A detailed description"
        assert request.metadata["team"] == "platform"

    def test_create_request_description_none_accepted(self):
        """Test that description=None is accepted (blank description fix #588)."""
        request = ProjectCreateRequest(name="Project", description=None)

        assert request.description is None

    def test_create_request_description_omitted_defaults_to_none(self):
        """Test that omitting description defaults to None (blank description fix #588)."""
        request = ProjectCreateRequest(name="Project")

        assert request.description is None

    def test_create_request_description_empty_string_accepted(self):
        """Test that empty string description is accepted."""
        request = ProjectCreateRequest(name="Project", description="")

        assert request.description == ""

    def test_create_request_description_valid_string_preserved(self):
        """Test that a valid description string is preserved."""
        request = ProjectCreateRequest(name="Project", description="My description")

        assert request.description == "My description"

    def test_create_request_description_whitespace_only(self):
        """Test that whitespace-only description is accepted."""
        request = ProjectCreateRequest(name="Project", description="   ")

        assert request.description == "   "


# =============================================================================
# Test: ProjectUpdateRequest Model
# =============================================================================

class TestProjectUpdateRequestModel:
    """Test ProjectUpdateRequest model."""

    def test_update_request_all_optional(self):
        """Test that all fields are optional."""
        request = ProjectUpdateRequest()

        assert request.name is None
        assert request.description is None
        assert request.status is None
        assert request.primary_repo_id is None
        assert request.default_base_branch is None
        assert request.work_branch_pattern is None
        assert request.metadata is None

    def test_update_request_partial(self):
        """Test partial update request."""
        request = ProjectUpdateRequest(
            name="Updated Name",
            status=ProjectStatus.ARCHIVED
        )

        assert request.name == "Updated Name"
        assert request.status == ProjectStatus.ARCHIVED
        assert request.description is None

    def test_update_request_work_config(self):
        """Test update request with work configuration."""
        request = ProjectUpdateRequest(
            default_base_branch="develop",
            work_branch_pattern="feature/{task}/{id}"
        )

        assert request.default_base_branch == "develop"
        assert request.work_branch_pattern == "feature/{task}/{id}"


# =============================================================================
# Test: RepoAddRequest Model
# =============================================================================

class TestRepoAddRequestModel:
    """Test RepoAddRequest model."""

    def test_add_request_required_fields(self):
        """Test add request with required fields."""
        request = RepoAddRequest(
            name="new-repo",
            url="https://github.com/org/new-repo.git"
        )

        assert request.name == "new-repo"
        assert request.url == "https://github.com/org/new-repo.git"

    def test_add_request_defaults(self):
        """Test add request default values."""
        request = RepoAddRequest(
            name="new-repo",
            url="https://github.com/org/new-repo.git"
        )

        assert request.default_branch == "main"
        assert request.ssh_key_id is None
        assert request.metadata == {}

    def test_add_request_custom_values(self):
        """Test add request with custom values."""
        request = RepoAddRequest(
            name="private-repo",
            url="git@github.com:org/private.git",
            default_branch="master",
            ssh_key_id="key_xyz",
            metadata={"ci_enabled": True}
        )

        assert request.default_branch == "master"
        assert request.ssh_key_id == "key_xyz"
        assert request.metadata["ci_enabled"] is True


# =============================================================================
# Test: ProjectListResponse Model
# =============================================================================

class TestProjectListResponseModel:
    """Test ProjectListResponse model."""

    def test_list_response_empty(self):
        """Test empty list response."""
        response = ProjectListResponse(
            items=[],
            total=0
        )

        assert len(response.items) == 0
        assert response.total == 0

    def test_list_response_with_items(self):
        """Test list response with items."""
        project = Project(
            project_id="proj_001",
            name="Project 1"
        )

        response = ProjectListResponse(
            items=[project],
            total=1
        )

        assert len(response.items) == 1
        assert response.items[0].name == "Project 1"


# =============================================================================
# Test: ProjectStats Model
# =============================================================================

class TestProjectStatsModel:
    """Test ProjectStats model."""

    def test_project_stats_all_fields(self):
        """Test project stats with all fields."""
        stats = ProjectStats(
            total=5,
            by_status={"active": 4, "archived": 1},
            total_repos=12
        )

        assert stats.total == 5
        assert stats.by_status["active"] == 4
        assert stats.total_repos == 12


# =============================================================================
# Test: RepoStatusResponse Model
# =============================================================================

class TestRepoStatusResponseModel:
    """Test RepoStatusResponse model."""

    def test_status_response_required_fields(self):
        """Test status response with required fields."""
        response = RepoStatusResponse(
            repo_id="repo_001",
            name="my-repo",
            url="https://github.com/org/my-repo.git"
        )

        assert response.repo_id == "repo_001"
        assert response.name == "my-repo"
        assert response.url == "https://github.com/org/my-repo.git"

    def test_status_response_defaults(self):
        """Test status response default values."""
        response = RepoStatusResponse(
            repo_id="repo_001",
            name="my-repo",
            url="https://github.com/org/my-repo.git"
        )

        assert response.clone_status == RepoCloneStatus.NOT_CLONED
        assert response.local_path is None
        assert response.origin_url is None
        assert response.default_branch is None
        assert response.branches == []
        assert response.branch_count == 0
        assert response.is_mirror is False
        assert response.last_sync is None
        assert response.error_message is None

    def test_status_response_cloned(self):
        """Test status response for cloned repo."""
        response = RepoStatusResponse(
            repo_id="repo_001",
            name="my-repo",
            url="https://github.com/org/my-repo.git",
            clone_status=RepoCloneStatus.CLONED,
            local_path="/var/repos/my-repo",
            default_branch="main",
            branches=["main", "develop", "feature/x"],
            branch_count=3,
            is_mirror=True,
            last_sync=datetime.now(timezone.utc)
        )

        assert response.clone_status == RepoCloneStatus.CLONED
        assert response.branch_count == 3
        assert response.is_mirror is True

    def test_status_response_error(self):
        """Test status response with error."""
        response = RepoStatusResponse(
            repo_id="repo_001",
            name="my-repo",
            url="https://github.com/org/my-repo.git",
            clone_status=RepoCloneStatus.ERROR,
            error_message="Authentication failed"
        )

        assert response.clone_status == RepoCloneStatus.ERROR
        assert response.error_message == "Authentication failed"


# =============================================================================
# Test: RepoSyncResponse Model
# =============================================================================

class TestRepoSyncResponseModel:
    """Test RepoSyncResponse model."""

    def test_sync_response_required_fields(self):
        """Test sync response with required fields."""
        response = RepoSyncResponse(
            repo_id="repo_001",
            project_id="proj_001",
            operation="clone",
            success=True,
            message="Clone successful"
        )

        assert response.repo_id == "repo_001"
        assert response.project_id == "proj_001"
        assert response.operation == "clone"
        assert response.success is True
        assert response.message == "Clone successful"

    def test_sync_response_defaults(self):
        """Test sync response default values."""
        response = RepoSyncResponse(
            repo_id="repo_001",
            project_id="proj_001",
            operation="pull",
            success=True,
            message="Pull complete"
        )

        assert response.output is None
        assert isinstance(response.timestamp, datetime)

    def test_sync_response_with_output(self):
        """Test sync response with output."""
        response = RepoSyncResponse(
            repo_id="repo_001",
            project_id="proj_001",
            operation="push",
            success=False,
            message="Push failed",
            output="error: failed to push some refs"
        )

        assert response.success is False
        assert response.output == "error: failed to push some refs"

    def test_sync_response_operations(self):
        """Test various operation types."""
        for op in ["clone", "pull", "push"]:
            response = RepoSyncResponse(
                repo_id="repo_001",
                project_id="proj_001",
                operation=op,
                success=True,
                message=f"{op} complete"
            )
            assert response.operation == op
