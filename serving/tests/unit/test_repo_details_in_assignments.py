"""Tests for repository details in work assignments (#30).

Verifies that git_project_name, clone_url, and default_branch are correctly
populated in WorkAssignment, TaskAssignment, and the SSE dispatch context.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.work_map import WorkAssignment, WorkItem, WorkStatus, WorkPriority
from models.compute import WorkAssignedEvent
from mcp.models import TaskAssignment
from services.assignment_service import AssignmentService
from services.project_service import ProjectService
from models.project import Project, RepoConfig


# =============================================================================
# Model Tests
# =============================================================================


class TestWorkAssignmentRepoFields:
    """Test WorkAssignment model has repo detail fields."""

    def test_fields_default_to_none(self):
        """Repo detail fields should default to None."""
        assignment = WorkAssignment(
            work_id="w1",
            title="Test",
            description="Test desc",
            skills=["skill-1"],
            branch_name="work/w1",
            base_branch="main",
        )
        assert assignment.git_project_name is None
        assert assignment.clone_url is None
        assert assignment.default_branch is None

    def test_fields_can_be_set(self):
        """Repo detail fields should accept values."""
        assignment = WorkAssignment(
            work_id="w1",
            title="Test",
            description="Test desc",
            skills=["skill-1"],
            branch_name="work/w1",
            base_branch="main",
            git_project_name="proj_abc_repo_def",
            clone_url="http://serving:8002/git/proj_abc_repo_def.git",
            default_branch="develop",
        )
        assert assignment.git_project_name == "proj_abc_repo_def"
        assert assignment.clone_url == "http://serving:8002/git/proj_abc_repo_def.git"
        assert assignment.default_branch == "develop"

    def test_serialization_includes_repo_fields(self):
        """Repo detail fields should appear in serialized output."""
        assignment = WorkAssignment(
            work_id="w1",
            title="Test",
            description="Test desc",
            skills=["skill-1"],
            branch_name="work/w1",
            base_branch="main",
            git_project_name="proj_abc_repo_def",
            clone_url="http://serving:8002/git/proj_abc_repo_def.git",
            default_branch="develop",
        )
        data = assignment.model_dump()
        assert data["git_project_name"] == "proj_abc_repo_def"
        assert data["clone_url"] == "http://serving:8002/git/proj_abc_repo_def.git"
        assert data["default_branch"] == "develop"


class TestTaskAssignmentRepoFields:
    """Test TaskAssignment MCP model has repo detail fields."""

    def test_fields_default_to_none(self):
        """Repo detail fields should default to None."""
        assignment = TaskAssignment(
            task_id="t1",
            title="Test",
            description="Test desc",
            skill_ids=["skill-1"],
            branch_name="work/t1",
        )
        assert assignment.git_project_name is None
        assert assignment.clone_url is None
        assert assignment.default_branch is None

    def test_fields_can_be_set(self):
        """Repo detail fields should accept values."""
        assignment = TaskAssignment(
            task_id="t1",
            title="Test",
            description="Test desc",
            skill_ids=["skill-1"],
            branch_name="work/t1",
            git_project_name="proj_abc_repo_def",
            clone_url="http://serving:8002/git/proj_abc_repo_def.git",
            default_branch="develop",
        )
        assert assignment.git_project_name == "proj_abc_repo_def"
        assert assignment.clone_url == "http://serving:8002/git/proj_abc_repo_def.git"
        assert assignment.default_branch == "develop"


class TestWorkAssignedEventRepoFields:
    """Test WorkAssignedEvent SSE model has repo detail fields."""

    def test_fields_default_to_none(self):
        """Repo detail fields should default to None."""
        event = WorkAssignedEvent(
            task_id="t1",
            title="Test",
            branch_name="work/t1",
        )
        assert event.git_project_name is None
        assert event.clone_url is None
        assert event.default_branch is None

    def test_fields_can_be_set(self):
        """Repo detail fields should accept values."""
        event = WorkAssignedEvent(
            task_id="t1",
            title="Test",
            branch_name="work/t1",
            git_project_name="proj_abc_repo_def",
            clone_url="http://serving:8002/git/proj_abc_repo_def.git",
            default_branch="develop",
        )
        assert event.git_project_name == "proj_abc_repo_def"
        assert event.clone_url == "http://serving:8002/git/proj_abc_repo_def.git"
        assert event.default_branch == "develop"


# =============================================================================
# ProjectService.resolve_repo_details Tests
# =============================================================================


class TestResolveRepoDetails:
    """Test ProjectService.resolve_repo_details()."""

    @pytest.fixture
    def project_service(self):
        """Create a project service with a test project."""
        service = ProjectService()
        project = Project(
            project_id="proj_abc",
            name="Test Project",
            repos=[
                RepoConfig(
                    repo_id="repo_def",
                    name="my-repo",
                    url="http://serving:8002/git/proj_abc_repo_def.git",
                    default_branch="develop",
                    is_internal=True,
                    metadata={"git_project_name": "proj_abc_repo_def"},
                )
            ],
            primary_repo_id="repo_def",
        )
        service._projects["proj_abc"] = project
        return service

    @pytest.fixture
    def project_service_external(self):
        """Create a project service with an external repo."""
        service = ProjectService()
        project = Project(
            project_id="proj_ext",
            name="External Project",
            repos=[
                RepoConfig(
                    repo_id="repo_ext",
                    name="ext-repo",
                    url="https://github.com/user/repo.git",
                    default_branch="main",
                    is_internal=False,
                )
            ],
            primary_repo_id="repo_ext",
        )
        service._projects["proj_ext"] = project
        return service

    @pytest.mark.asyncio
    async def test_resolve_internal_repo(self, project_service):
        """Internal repo should return composite git_project_name."""
        result = await project_service.resolve_repo_details("proj_abc")
        assert result is not None
        assert result["git_project_name"] == "proj_abc_repo_def"
        assert result["clone_url"] == "http://serving:8002/git/proj_abc_repo_def.git"
        assert result["default_branch"] == "develop"

    @pytest.mark.asyncio
    async def test_resolve_external_repo(self, project_service_external):
        """External repo should return project_id as git_project_name."""
        result = await project_service_external.resolve_repo_details("proj_ext")
        assert result is not None
        assert result["git_project_name"] == "proj_ext"
        assert result["clone_url"] == "https://github.com/user/repo.git"
        assert result["default_branch"] == "main"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_project(self, project_service):
        """Nonexistent project should return None."""
        result = await project_service.resolve_repo_details("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_specific_repo_id(self, project_service):
        """Should resolve by specific repo_id."""
        result = await project_service.resolve_repo_details("proj_abc", repo_id="repo_def")
        assert result is not None
        assert result["git_project_name"] == "proj_abc_repo_def"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_repo_id(self, project_service):
        """Should return None for nonexistent repo_id."""
        result = await project_service.resolve_repo_details("proj_abc", repo_id="nonexistent")
        assert result is None


# =============================================================================
# AssignmentService Integration Tests
# =============================================================================


class TestAssignWorkRepoDetails:
    """Test that assign_work populates repo details."""

    @pytest.fixture
    def assignment_service(self):
        """Create assignment service with work items."""
        service = AssignmentService(redis_client=None)
        work = WorkItem(
            work_id="work_001",
            title="Linked Repo Work",
            description="Work on linked repo",
            project_id="proj_abc",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.PENDING,
            branch_name="work/work_001",
            base_branch="main",
        )
        items = {work.work_id: work}
        service.set_work_items_reference(items)
        return service

    @pytest.mark.asyncio
    async def test_assign_work_includes_repo_details(self, assignment_service):
        """assign_work should include repo details from project service."""
        mock_repo_details = {
            "git_project_name": "proj_abc_repo_def",
            "clone_url": "http://serving:8002/git/proj_abc_repo_def.git",
            "default_branch": "develop",
        }

        with patch.object(
            assignment_service, "_resolve_repo_details",
            new_callable=AsyncMock, return_value=mock_repo_details
        ):
            result = await assignment_service.assign_work(
                work_id="work_001",
                compute_id="compute-001",
                skills=["skill-1"],
            )

        assert result is not None
        assert result.git_project_name == "proj_abc_repo_def"
        assert result.clone_url == "http://serving:8002/git/proj_abc_repo_def.git"
        assert result.default_branch == "develop"

    @pytest.mark.asyncio
    async def test_assign_work_handles_missing_repo_details(self, assignment_service):
        """assign_work should work even if repo details are unavailable."""
        with patch.object(
            assignment_service, "_resolve_repo_details",
            new_callable=AsyncMock, return_value=None
        ):
            result = await assignment_service.assign_work(
                work_id="work_001",
                compute_id="compute-001",
                skills=["skill-1"],
            )

        assert result is not None
        assert result.git_project_name is None
        assert result.clone_url is None
        assert result.default_branch is None

    @pytest.mark.asyncio
    async def test_assign_work_handles_repo_details_error(self, assignment_service):
        """assign_work should not fail if repo details resolution raises."""
        with patch.object(
            assignment_service, "_resolve_repo_details",
            new_callable=AsyncMock, side_effect=RuntimeError("Service down")
        ):
            # Should still succeed — repo details are best-effort
            result = await assignment_service.assign_work(
                work_id="work_001",
                compute_id="compute-001",
                skills=["skill-1"],
            )

        assert result is not None
        # Fields will have whatever the exception path produces
        # The key point is assign_work doesn't crash


# =============================================================================
# MCP Assignment Tool Tests
# =============================================================================


class TestMCPAssignmentPassthrough:
    """Test that MCP assignment tool passes through repo details."""

    @pytest.mark.asyncio
    async def test_get_assignment_includes_repo_details(self):
        """get_assignment should pass repo details to TaskAssignment."""
        mock_assignment = WorkAssignment(
            work_id="work_001",
            title="Test",
            description="Test desc",
            skills=["skill-1"],
            skill_ids=["skill-1"],
            branch_name="work/work_001",
            base_branch="main",
            git_project_name="proj_abc_repo_def",
            clone_url="http://serving:8002/git/proj_abc_repo_def.git",
            default_branch="develop",
        )

        mock_service = MagicMock()
        mock_service.get_next_assignment = AsyncMock(return_value=mock_assignment)

        with patch("mcp.tools.assignment.get_work_map_service", return_value=mock_service):
            from mcp.tools.assignment import get_assignment
            from mcp.models import GetAssignmentInput

            input_data = GetAssignmentInput(
                compute_id="compute-001",
                capabilities=["skill-1"],
            )
            result, error = await get_assignment(input_data)

        assert error is None
        assert result is not None
        assert result.git_project_name == "proj_abc_repo_def"
        assert result.clone_url == "http://serving:8002/git/proj_abc_repo_def.git"
        assert result.default_branch == "develop"
