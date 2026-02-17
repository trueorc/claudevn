"""Tests for IssueOpsService project_id filtering (#450).

Tests that issues can be scoped to projects via project_id field.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from models.work_map import (
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueBatchCreateRequest, IssueListResponse,
)
from services.issue_ops_service import IssueOpsService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def service():
    """Create IssueOpsService without Redis (in-memory only)."""
    svc = IssueOpsService(redis_client=None)
    svc._initialized = True
    svc._save_issue_to_redis = AsyncMock()
    svc._save_issue_history_entry = AsyncMock()
    svc._delete_issue_from_redis = AsyncMock()
    return svc


@pytest.fixture
def service_with_goal():
    """Create IssueOpsService with mocked goal service."""
    mock_goal_service = MagicMock()
    mock_goal_service.get_goal = AsyncMock()
    mock_goal_service._save_goal_to_redis = AsyncMock()

    svc = IssueOpsService(redis_client=None, goal_service=mock_goal_service)
    svc._initialized = True
    svc._save_issue_to_redis = AsyncMock()
    svc._save_issue_history_entry = AsyncMock()
    svc._delete_issue_from_redis = AsyncMock()
    return svc, mock_goal_service


# ============================================================================
# Model Tests
# ============================================================================

class TestIssueProjectIdField:
    """Test Issue model has project_id field."""

    def test_issue_has_project_id_field(self):
        """Test Issue model accepts project_id."""
        issue = Issue(
            issue_id="issue_test1",
            title="Test",
            description="Test",
            project_id="proj_abc123",
        )
        assert issue.project_id == "proj_abc123"

    def test_issue_project_id_defaults_to_none(self):
        """Test project_id defaults to None for backwards compatibility."""
        issue = Issue(
            issue_id="issue_test2",
            title="Test",
            description="Test",
        )
        assert issue.project_id is None

    def test_create_request_has_project_id(self):
        """Test IssueCreateRequest accepts project_id."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
            project_id="proj_abc123",
        )
        assert request.project_id == "proj_abc123"

    def test_create_request_project_id_defaults_to_none(self):
        """Test IssueCreateRequest project_id defaults to None."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
        )
        assert request.project_id is None


# ============================================================================
# Create Issue Tests
# ============================================================================

class TestCreateIssueWithProjectId:
    """Test creating issues with project_id."""

    @pytest.mark.asyncio
    async def test_create_issue_stores_project_id(self, service):
        """Test that created issue has project_id set."""
        request = IssueCreateRequest(
            title="Test Issue",
            description="Test",
            project_id="proj_abc123",
        )
        issue = await service.create_issue(request)

        assert issue.project_id == "proj_abc123"

    @pytest.mark.asyncio
    async def test_create_issue_without_project_id(self, service):
        """Test creating issue without project_id works (backwards compat)."""
        request = IssueCreateRequest(
            title="Test Issue",
            description="Test",
        )
        issue = await service.create_issue(request)

        assert issue.project_id is None


# ============================================================================
# List Issues Filter Tests
# ============================================================================

class TestListIssuesProjectFilter:
    """Test list_issues filtering by project_id."""

    @pytest.mark.asyncio
    async def test_list_issues_filters_by_project_id(self, service):
        """Test that list_issues returns only issues for the given project."""
        # Create issues in different projects
        await service.create_issue(IssueCreateRequest(
            title="Project A Issue 1",
            description="Test",
            project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="Project A Issue 2",
            description="Test",
            project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="Project B Issue 1",
            description="Test",
            project_id="proj_bbb",
        ))
        await service.create_issue(IssueCreateRequest(
            title="No Project Issue",
            description="Test",
        ))

        # Filter by project A
        result = await service.list_issues(project_id="proj_aaa")

        assert len(result.items) == 2
        assert all(i.project_id == "proj_aaa" for i in result.items)
        titles = {i.title for i in result.items}
        assert titles == {"Project A Issue 1", "Project A Issue 2"}

    @pytest.mark.asyncio
    async def test_list_issues_no_project_filter_returns_all(self, service):
        """Test that list_issues without project_id returns all issues."""
        await service.create_issue(IssueCreateRequest(
            title="Project A", description="Test", project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="Project B", description="Test", project_id="proj_bbb",
        ))
        await service.create_issue(IssueCreateRequest(
            title="No Project", description="Test",
        ))

        result = await service.list_issues()

        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_list_issues_project_filter_with_status(self, service):
        """Test combining project_id and status filters."""
        # Create a dependency issue first so the second issue is BACKLOG
        dep = await service.create_issue(IssueCreateRequest(
            title="Ready in A",
            description="Test",
            project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="Backlog in A",
            description="Test",
            project_id="proj_aaa",
            depends_on=[dep.issue_id],
        ))

        # Filter by project A and ready status
        result = await service.list_issues(
            project_id="proj_aaa",
            status=IssueStatus.READY,
        )

        assert len(result.items) == 1
        assert result.items[0].title == "Ready in A"

    @pytest.mark.asyncio
    async def test_list_issues_empty_project_returns_empty(self, service):
        """Test filtering by a project with no issues returns empty."""
        await service.create_issue(IssueCreateRequest(
            title="Project A", description="Test", project_id="proj_aaa",
        ))

        result = await service.list_issues(project_id="proj_nonexistent")

        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_list_issues_stats_scoped_to_project(self, service):
        """Test that total and by_status stats are scoped to the filtered project (#718)."""
        # Create issues across two projects
        await service.create_issue(IssueCreateRequest(
            title="A-1", description="Test", project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="A-2", description="Test", project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="B-1", description="Test", project_id="proj_bbb",
        ))
        await service.create_issue(IssueCreateRequest(
            title="B-2", description="Test", project_id="proj_bbb",
        ))
        await service.create_issue(IssueCreateRequest(
            title="B-3", description="Test", project_id="proj_bbb",
        ))

        # Filter to project A only
        result = await service.list_issues(project_id="proj_aaa")

        # Stats should reflect only project A (2 issues), not all (5)
        assert result.total == 2
        total_from_status = sum(result.by_status.values())
        assert total_from_status == 2

    @pytest.mark.asyncio
    async def test_list_issues_stats_empty_for_new_project(self, service):
        """Test that a project with no issues shows zero stats (#718)."""
        # Create issues in another project
        await service.create_issue(IssueCreateRequest(
            title="Other", description="Test", project_id="proj_other",
        ))

        # Query a project with zero issues
        result = await service.list_issues(project_id="proj_empty")

        assert result.total == 0
        assert result.by_status == {}
        assert result.by_priority == {}

    @pytest.mark.asyncio
    async def test_list_issues_stats_no_filter_shows_all(self, service):
        """Test that stats without project filter show global totals."""
        await service.create_issue(IssueCreateRequest(
            title="A", description="Test", project_id="proj_aaa",
        ))
        await service.create_issue(IssueCreateRequest(
            title="B", description="Test", project_id="proj_bbb",
        ))

        result = await service.list_issues()

        assert result.total == 2
        total_from_status = sum(result.by_status.values())
        assert total_from_status == 2


# ============================================================================
# Batch Create Tests
# ============================================================================

class TestBatchCreateProjectId:
    """Test batch issue creation inherits project_id from goal."""

    @pytest.mark.asyncio
    async def test_batch_create_inherits_project_id_from_goal(self, service_with_goal):
        """Test batch-created issues inherit project_id from parent goal."""
        service, mock_goal_service = service_with_goal

        # Mock goal with project_id
        mock_goal = MagicMock()
        mock_goal.project_id = "proj_from_goal"
        mock_goal.issue_ids = []
        mock_goal.status = "planning"
        mock_goal_service.get_goal.return_value = mock_goal

        request = IssueBatchCreateRequest(
            goal_id="goal_test1",
            issues=[
                IssueCreateRequest(
                    title="Batch Issue 1",
                    description="Test",
                ),
                IssueCreateRequest(
                    title="Batch Issue 2",
                    description="Test",
                ),
            ],
        )

        result = await service.create_issues_batch(request)

        assert result.success is True
        assert len(result.created_issues) == 2

        # Verify all created issues have the goal's project_id
        for item in result.created_issues:
            issue = service._issues[item["id"]]
            assert issue.project_id == "proj_from_goal"

    @pytest.mark.asyncio
    async def test_batch_create_issue_project_id_overrides_goal(self, service_with_goal):
        """Test individual issue project_id overrides goal's project_id."""
        service, mock_goal_service = service_with_goal

        mock_goal = MagicMock()
        mock_goal.project_id = "proj_from_goal"
        mock_goal.issue_ids = []
        mock_goal.status = "planning"
        mock_goal_service.get_goal.return_value = mock_goal

        request = IssueBatchCreateRequest(
            goal_id="goal_test1",
            issues=[
                IssueCreateRequest(
                    title="Issue with override",
                    description="Test",
                    project_id="proj_override",
                ),
                IssueCreateRequest(
                    title="Issue inheriting",
                    description="Test",
                ),
            ],
        )

        result = await service.create_issues_batch(request)

        assert result.success is True
        issues = {
            service._issues[item["id"]].title: service._issues[item["id"]]
            for item in result.created_issues
        }
        assert issues["Issue with override"].project_id == "proj_override"
        assert issues["Issue inheriting"].project_id == "proj_from_goal"
