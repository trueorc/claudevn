"""Unit tests for project filtering and sorting functionality."""

import pytest
from datetime import datetime, timezone, timedelta

from models.project import Project, ProjectStatus, ProjectListResponse
from services.project_service import ProjectService


class TestProjectServiceFiltering:
    """Tests for ProjectService list_projects filtering."""

    @pytest.fixture
    def service(self):
        """Create a fresh ProjectService instance."""
        return ProjectService()

    @pytest.fixture
    def sample_projects(self, service):
        """Create sample projects for testing."""
        now = datetime.now(timezone.utc)

        projects = [
            Project(
                project_id="proj_alpha",
                name="Alpha Project",
                description="First project for testing",
                status=ProjectStatus.ACTIVE,
                created_at=now - timedelta(days=10),
                updated_at=now - timedelta(days=5)
            ),
            Project(
                project_id="proj_beta",
                name="Beta Project",
                description="Second project with different status",
                status=ProjectStatus.ARCHIVED,
                created_at=now - timedelta(days=5),
                updated_at=now - timedelta(days=1)
            ),
            Project(
                project_id="proj_gamma",
                name="Gamma API",
                description="Testing API functionality",
                status=ProjectStatus.ACTIVE,
                created_at=now - timedelta(days=1),
                updated_at=now
            ),
            Project(
                project_id="proj_delta",
                name="Delta Service",
                description="Suspended service project",
                status=ProjectStatus.SUSPENDED,
                created_at=now - timedelta(days=20),
                updated_at=now - timedelta(days=10)
            )
        ]

        for project in projects:
            service._projects[project.project_id] = project

        return projects

    @pytest.mark.asyncio
    async def test_list_projects_no_filters(self, service, sample_projects):
        """List all projects when no filters applied."""
        result = await service.list_projects()

        assert isinstance(result, ProjectListResponse)
        assert result.total == 4
        assert len(result.items) == 4

    @pytest.mark.asyncio
    async def test_filter_by_status_active(self, service, sample_projects):
        """Filter projects by active status."""
        result = await service.list_projects(status=ProjectStatus.ACTIVE)

        assert result.total == 2
        assert all(p.status == ProjectStatus.ACTIVE for p in result.items)
        project_ids = [p.project_id for p in result.items]
        assert "proj_alpha" in project_ids
        assert "proj_gamma" in project_ids

    @pytest.mark.asyncio
    async def test_filter_by_status_archived(self, service, sample_projects):
        """Filter projects by archived status."""
        result = await service.list_projects(status=ProjectStatus.ARCHIVED)

        assert result.total == 1
        assert result.items[0].project_id == "proj_beta"

    @pytest.mark.asyncio
    async def test_filter_by_status_suspended(self, service, sample_projects):
        """Filter projects by suspended status."""
        result = await service.list_projects(status=ProjectStatus.SUSPENDED)

        assert result.total == 1
        assert result.items[0].project_id == "proj_delta"

    @pytest.mark.asyncio
    async def test_search_by_name(self, service, sample_projects):
        """Search projects by name."""
        result = await service.list_projects(search="Alpha")

        assert result.total == 1
        assert result.items[0].name == "Alpha Project"

    @pytest.mark.asyncio
    async def test_search_by_description(self, service, sample_projects):
        """Search projects by description."""
        result = await service.list_projects(search="API")

        assert result.total == 1
        assert result.items[0].project_id == "proj_gamma"

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, service, sample_projects):
        """Search should be case-insensitive."""
        result = await service.list_projects(search="project")

        # "project" matches: "Alpha Project", "Beta Project", "Suspended service project"
        assert result.total == 3
        project_ids = [p.project_id for p in result.items]
        assert "proj_alpha" in project_ids
        assert "proj_beta" in project_ids
        assert "proj_delta" in project_ids

    @pytest.mark.asyncio
    async def test_search_partial_match(self, service, sample_projects):
        """Search should match partial strings."""
        result = await service.list_projects(search="test")

        assert result.total == 2
        project_ids = [p.project_id for p in result.items]
        assert "proj_alpha" in project_ids
        assert "proj_gamma" in project_ids

    @pytest.mark.asyncio
    async def test_search_no_results(self, service, sample_projects):
        """Search with no matching results."""
        result = await service.list_projects(search="nonexistent")

        assert result.total == 0
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_sort_name_asc(self, service, sample_projects):
        """Sort projects by name ascending."""
        result = await service.list_projects(sort="name_asc")

        names = [p.name for p in result.items]
        assert names == sorted(names, key=str.lower)
        assert names[0] == "Alpha Project"
        assert names[-1] == "Gamma API"

    @pytest.mark.asyncio
    async def test_sort_name_desc(self, service, sample_projects):
        """Sort projects by name descending."""
        result = await service.list_projects(sort="name_desc")

        names = [p.name for p in result.items]
        assert names == sorted(names, key=str.lower, reverse=True)
        assert names[0] == "Gamma API"
        assert names[-1] == "Alpha Project"

    @pytest.mark.asyncio
    async def test_sort_created_asc(self, service, sample_projects):
        """Sort projects by created date ascending (oldest first)."""
        result = await service.list_projects(sort="created_asc")

        assert result.items[0].project_id == "proj_delta"  # Created 20 days ago
        assert result.items[-1].project_id == "proj_gamma"  # Created 1 day ago

    @pytest.mark.asyncio
    async def test_sort_created_desc(self, service, sample_projects):
        """Sort projects by created date descending (newest first)."""
        result = await service.list_projects(sort="created_desc")

        assert result.items[0].project_id == "proj_gamma"  # Created 1 day ago
        assert result.items[-1].project_id == "proj_delta"  # Created 20 days ago

    @pytest.mark.asyncio
    async def test_sort_updated_asc(self, service, sample_projects):
        """Sort projects by updated date ascending."""
        result = await service.list_projects(sort="updated_asc")

        assert result.items[0].project_id == "proj_delta"  # Updated 10 days ago
        assert result.items[-1].project_id == "proj_gamma"  # Updated now

    @pytest.mark.asyncio
    async def test_sort_updated_desc(self, service, sample_projects):
        """Sort projects by updated date descending."""
        result = await service.list_projects(sort="updated_desc")

        assert result.items[0].project_id == "proj_gamma"  # Updated now
        assert result.items[-1].project_id == "proj_delta"  # Updated 10 days ago

    @pytest.mark.asyncio
    async def test_combined_status_and_search(self, service, sample_projects):
        """Combine status filter with search."""
        result = await service.list_projects(
            status=ProjectStatus.ACTIVE,
            search="Project"
        )

        assert result.total == 1
        assert result.items[0].project_id == "proj_alpha"

    @pytest.mark.asyncio
    async def test_combined_all_filters(self, service, sample_projects):
        """Combine status, search, and sort."""
        result = await service.list_projects(
            status=ProjectStatus.ACTIVE,
            search="",
            sort="name_desc"
        )

        assert result.total == 2
        assert result.items[0].name == "Gamma API"
        assert result.items[1].name == "Alpha Project"

    @pytest.mark.asyncio
    async def test_empty_projects_list(self, service):
        """Handle empty projects list."""
        result = await service.list_projects()

        assert result.total == 0
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_invalid_sort_ignored(self, service, sample_projects):
        """Invalid sort option should be ignored."""
        result = await service.list_projects(sort="invalid_sort")

        # Should return all projects without errors
        assert result.total == 4


class TestSortOrderEnum:
    """Tests for API SortOrder enum."""

    def test_sort_order_values(self):
        """Verify all expected sort order values exist."""
        from api.projects import SortOrder

        assert SortOrder.NAME_ASC.value == "name_asc"
        assert SortOrder.NAME_DESC.value == "name_desc"
        assert SortOrder.CREATED_ASC.value == "created_asc"
        assert SortOrder.CREATED_DESC.value == "created_desc"
        assert SortOrder.UPDATED_ASC.value == "updated_asc"
        assert SortOrder.UPDATED_DESC.value == "updated_desc"
