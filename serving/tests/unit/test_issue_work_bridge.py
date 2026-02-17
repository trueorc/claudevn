"""Tests for Issue-to-WorkItem bridge functionality.

Tests the three key components:
1. create_work_from_issue() - converts ready Issue → pending WorkItem
2. _convert_ready_issues() - orchestrator loop integration
3. complete_work() - updates parent Issue when WorkItem completes
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.work_map import (
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority, IssueResult,
    WorkItem, WorkStatus, WorkPriority, WorkCreateRequest,
    GoalStatus
)
from models.project import Project, RepoConfig
from services.work_map_service import WorkMapService
from services.work_orchestrator import WorkOrchestrator


# ============ Fixtures ============


@pytest.fixture
def mock_issue():
    """Create a ready issue for testing."""
    return Issue(
        issue_id="issue_abc123",
        title="Implement user auth",
        description="Add JWT authentication to the API",
        issue_type=IssueType.FEATURE,
        area=IssueArea.API,
        priority=IssuePriority.P1,
        status=IssueStatus.READY,
        required_skills=["code-writer", "test-automator"],
        required_labels=["backend"],
        required_tools=["pytest"],
        project_id="proj_test1",
        goal_id="goal_xyz",
    )


@pytest.fixture
def mock_project():
    """Create a mock project with repo config."""
    return Project(
        project_id="proj_test1",
        name="Test Project",
        repos=[
            RepoConfig(
                repo_id="repo_1",
                name="main-repo",
                url="git@github.com:test/repo.git",
                default_branch="develop",
            )
        ],
        primary_repo_id="repo_1",
        default_base_branch="develop",
    )


@pytest.fixture
def work_map_service():
    """Create a WorkMapService with mocked dependencies."""
    service = WorkMapService(redis_client=None)
    service._issue_service._save_issue_to_redis = AsyncMock()
    service._issue_service._save_issue_history_entry = AsyncMock()
    service._goal_service._save_goal_to_redis = AsyncMock()
    return service


# ============ Tests: create_work_from_issue ============


class TestCreateWorkFromIssue:
    """Test WorkMapService.create_work_from_issue()."""

    @pytest.mark.asyncio
    async def test_creates_work_from_ready_issue(self, work_map_service, mock_issue, mock_project):
        """Test successful conversion of a ready Issue to a WorkItem."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)

            work = await service.create_work_from_issue("issue_abc123")

        assert work is not None
        assert work.title == "Implement user auth"
        assert work.description == "Add JWT authentication to the API"
        assert work.work_type == "feature"
        assert work.priority == WorkPriority.HIGH
        assert work.required_skills == ["code-writer", "test-automator"]
        assert work.required_labels == ["backend"]
        assert work.required_tools == ["pytest"]
        assert work.project_id == "proj_test1"
        assert work.base_branch == "develop"
        assert work.status == WorkStatus.PENDING

        # Verify context links back to issue
        assert work.context["issue_id"] == "issue_abc123"
        assert work.context["goal_id"] == "goal_xyz"
        assert work.context["repo_url"] == "git@github.com:test/repo.git"

        # Issue remains READY until dispatched to compute (see #860).
        # IN_PROGRESS is set only after send_work_assigned() succeeds.
        assert mock_issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_issue(self, work_map_service):
        """Test returns None when issue doesn't exist."""
        result = await work_map_service.create_work_from_issue("issue_missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_non_ready_issue(self, work_map_service, mock_issue):
        """Test returns None when issue is not in READY status."""
        mock_issue.status = IssueStatus.BACKLOG
        work_map_service._issue_service._issues["issue_abc123"] = mock_issue

        result = await work_map_service.create_work_from_issue("issue_abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_if_work_already_exists(self, work_map_service, mock_issue, mock_project):
        """Test returns None if active WorkItem already exists for issue."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        # Add an existing work item for this issue
        existing_work = WorkItem(
            work_id="work_existing",
            title="Existing work",
            description="Already in progress",
            project_id="proj_test1",
            status=WorkStatus.IN_PROGRESS,
            context={"issue_id": "issue_abc123"},
        )
        service._work_items["work_existing"] = existing_work

        result = await service.create_work_from_issue("issue_abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_retry_after_failed_work(self, work_map_service, mock_issue, mock_project):
        """Test allows creating new work if previous work failed."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        # Add a failed work item for this issue
        failed_work = WorkItem(
            work_id="work_failed",
            title="Failed work",
            description="Previously failed",
            project_id="proj_test1",
            status=WorkStatus.FAILED,
            context={"issue_id": "issue_abc123"},
        )
        service._work_items["work_failed"] = failed_work

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)

            work = await service.create_work_from_issue("issue_abc123")

        assert work is not None

    @pytest.mark.asyncio
    async def test_priority_mapping(self, work_map_service, mock_project):
        """Test IssuePriority → WorkPriority mapping."""
        service = work_map_service
        expected = {
            IssuePriority.P0: WorkPriority.CRITICAL,
            IssuePriority.P1: WorkPriority.HIGH,
            IssuePriority.P2: WorkPriority.NORMAL,
            IssuePriority.P3: WorkPriority.LOW,
        }

        for issue_priority, work_priority in expected.items():
            issue = Issue(
                issue_id=f"issue_{issue_priority.value}",
                title=f"Priority {issue_priority.value}",
                description="Test",
                priority=issue_priority,
                status=IssueStatus.READY,
                project_id="proj_test1",
            )
            service._issue_service._issues[issue.issue_id] = issue

            with patch("services.project_service.get_project_service") as mock_proj_svc:
                mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)
                work = await service.create_work_from_issue(issue.issue_id)

            assert work.priority == work_priority, f"Expected {work_priority} for {issue_priority}"

    @pytest.mark.asyncio
    async def test_type_mapping(self, work_map_service, mock_project):
        """Test IssueType → work_type mapping."""
        service = work_map_service
        expected = {
            IssueType.FEATURE: "feature",
            IssueType.BUG: "bug",
            IssueType.REFACTOR: "refactor",
            IssueType.DOCS: "docs",
            IssueType.TEST: "test",
        }

        for issue_type, work_type in expected.items():
            issue = Issue(
                issue_id=f"issue_{issue_type.value}",
                title=f"Type {issue_type.value}",
                description="Test",
                issue_type=issue_type,
                status=IssueStatus.READY,
                project_id="proj_test1",
            )
            service._issue_service._issues[issue.issue_id] = issue

            with patch("services.project_service.get_project_service") as mock_proj_svc:
                mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)
                work = await service.create_work_from_issue(issue.issue_id)

            assert work.work_type == work_type, f"Expected {work_type} for {issue_type}"

    @pytest.mark.asyncio
    async def test_handles_missing_project_gracefully(self, work_map_service, mock_issue):
        """Test handles missing project service gracefully."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=None)

            work = await service.create_work_from_issue("issue_abc123")

        assert work is not None
        assert work.base_branch == "main"  # Falls back to default
        assert "repo_url" not in work.context

    @pytest.mark.asyncio
    async def test_handles_project_without_repo(self, work_map_service, mock_issue):
        """Test handles project with no repos."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        empty_project = Project(
            project_id="proj_test1",
            name="Empty Project",
            repos=[],
            default_base_branch="main",
        )

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=empty_project)

            work = await service.create_work_from_issue("issue_abc123")

        assert work is not None
        assert work.base_branch == "main"

    @pytest.mark.asyncio
    async def test_issue_without_project_id_uses_default(self, work_map_service):
        """Test issue without project_id uses 'default'."""
        issue = Issue(
            issue_id="issue_no_proj",
            title="No project issue",
            description="Test",
            status=IssueStatus.READY,
            project_id=None,
        )
        work_map_service._issue_service._issues["issue_no_proj"] = issue

        work = await work_map_service.create_work_from_issue("issue_no_proj")

        assert work is not None
        assert work.project_id == "default"


# ============ Tests: Orchestrator _convert_ready_issues ============


class TestConvertReadyIssues:
    """Test WorkOrchestrator._convert_ready_issues()."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator for testing."""
        return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=3)

    @pytest.mark.asyncio
    async def test_converts_ready_issues(self, orchestrator):
        """Test ready issues are converted to work items."""
        mock_issue = MagicMock()
        mock_issue.issue_id = "issue_ready1"

        mock_work = MagicMock()
        mock_work.work_id = "work_new1"

        with patch("services.work_map_service.get_work_map_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_service.get_ready_queue = AsyncMock(return_value=[mock_issue])
            mock_service.create_work_from_issue = AsyncMock(return_value=mock_work)
            mock_get_svc.return_value = mock_service

            converted = await orchestrator._convert_ready_issues()

        assert converted == 1
        mock_service.create_work_from_issue.assert_called_once_with("issue_ready1")

    @pytest.mark.asyncio
    async def test_converts_multiple_issues(self, orchestrator):
        """Test multiple ready issues are all converted."""
        issues = [MagicMock(issue_id=f"issue_{i}") for i in range(3)]
        works = [MagicMock(work_id=f"work_{i}") for i in range(3)]

        with patch("services.work_map_service.get_work_map_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_service.get_ready_queue = AsyncMock(return_value=issues)
            mock_service.create_work_from_issue = AsyncMock(side_effect=works)
            mock_get_svc.return_value = mock_service

            converted = await orchestrator._convert_ready_issues()

        assert converted == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_ready_issues(self, orchestrator):
        """Test returns 0 when no ready issues exist."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_service.get_ready_queue = AsyncMock(return_value=[])
            mock_get_svc.return_value = mock_service

            converted = await orchestrator._convert_ready_issues()

        assert converted == 0

    @pytest.mark.asyncio
    async def test_skips_issues_that_fail_conversion(self, orchestrator):
        """Test continues converting even if some issues fail."""
        issues = [MagicMock(issue_id=f"issue_{i}") for i in range(3)]

        with patch("services.work_map_service.get_work_map_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_service.get_ready_queue = AsyncMock(return_value=issues)
            # First succeeds, second returns None (already exists), third succeeds
            mock_service.create_work_from_issue = AsyncMock(
                side_effect=[MagicMock(work_id="w1"), None, MagicMock(work_id="w3")]
            )
            mock_get_svc.return_value = mock_service

            converted = await orchestrator._convert_ready_issues()

        assert converted == 2

    @pytest.mark.asyncio
    async def test_handles_error_in_individual_conversion(self, orchestrator):
        """Test handles exceptions in individual issue conversion."""
        issues = [MagicMock(issue_id="issue_ok"), MagicMock(issue_id="issue_err")]

        with patch("services.work_map_service.get_work_map_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_service.get_ready_queue = AsyncMock(return_value=issues)
            mock_service.create_work_from_issue = AsyncMock(
                side_effect=[MagicMock(work_id="w1"), Exception("conversion error")]
            )
            mock_get_svc.return_value = mock_service

            converted = await orchestrator._convert_ready_issues()

        assert converted == 1  # Only the successful one counts

    @pytest.mark.asyncio
    async def test_handles_service_error(self, orchestrator):
        """Test handles error from work_map_service gracefully."""
        with patch("services.work_map_service.get_work_map_service") as mock_get_svc:
            mock_get_svc.side_effect = RuntimeError("service not initialized")

            converted = await orchestrator._convert_ready_issues()

        assert converted == 0


# ============ Tests: IN_PROGRESS set only on dispatch ============


class TestDispatchSetsIssueInProgress:
    """Verify IssueStatus.IN_PROGRESS is set only after successful dispatch (#860).

    create_work_from_issue() must leave the issue READY; only a successful
    send_work_assigned() call (in _assign_work_via_sse) may transition it to
    IN_PROGRESS.  This prevents issues from appearing in-progress when compute
    slots are exhausted and work items sit queued as PENDING.
    """

    @pytest.mark.asyncio
    async def test_create_work_leaves_issue_ready(self, work_map_service, mock_issue, mock_project):
        """create_work_from_issue() must NOT move issue to IN_PROGRESS."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)
            work = await service.create_work_from_issue("issue_abc123")

        assert work is not None
        # Issue must remain READY — dispatch hasn't happened yet
        assert mock_issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_successful_sse_dispatch_sets_in_progress(self, work_map_service, mock_issue):
        """After send_work_assigned succeeds, issue transitions to IN_PROGRESS."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue
        service._issue_service._save_issue_to_redis = AsyncMock()

        # Simulate successful dispatch: call update_issue_status as the orchestrator would
        await service.update_issue_status("issue_abc123", IssueStatus.IN_PROGRESS, "compute-1")

        assert mock_issue.status == IssueStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_failed_dispatch_leaves_issue_ready(self, work_map_service, mock_issue, mock_project):
        """When no compute is available and dispatch is skipped, issue stays READY."""
        service = work_map_service
        service._issue_service._issues["issue_abc123"] = mock_issue

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)
            work = await service.create_work_from_issue("issue_abc123")

        assert work is not None
        assert work.status == WorkStatus.PENDING
        # Issue is still READY — no compute was assigned
        assert mock_issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_multiple_ready_issues_stay_ready_when_slots_exhausted(self, work_map_service, mock_project):
        """All issues remain READY after work item creation when compute capacity is limited."""
        service = work_map_service

        # Create 3 ready issues
        issues = []
        for i in range(3):
            issue = Issue(
                issue_id=f"issue_{i}",
                title=f"Issue {i}",
                description="Test",
                status=IssueStatus.READY,
                project_id="proj_test1",
            )
            service._issue_service._issues[f"issue_{i}"] = issue
            issues.append(issue)

        with patch("services.project_service.get_project_service") as mock_proj_svc:
            mock_proj_svc.return_value.get_project = AsyncMock(return_value=mock_project)
            for issue in issues:
                work = await service.create_work_from_issue(issue.issue_id)
                assert work is not None

        # All issues must remain READY — dispatch hasn't happened yet
        for issue in issues:
            assert issue.status == IssueStatus.READY, (
                f"Issue {issue.issue_id} was prematurely set to {issue.status}"
            )


# ============ Tests: complete_work with Issue update ============


class TestCompleteWorkIssueUpdate:
    """Test that complete_work() updates the parent Issue."""

    @pytest.fixture
    def work_map_service(self):
        """Create service with mocked dependencies."""
        service = WorkMapService(redis_client=None)
        service._issue_service._save_issue_to_redis = AsyncMock()
        service._issue_service._save_issue_history_entry = AsyncMock()
        service._goal_service._save_goal_to_redis = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_completes_work_and_updates_issue(self, work_map_service):
        """Test completing work also completes the parent issue."""
        service = work_map_service

        # Create an issue
        issue = Issue(
            issue_id="issue_complete1",
            title="Test issue",
            description="Test",
            status=IssueStatus.IN_PROGRESS,
            project_id="proj_1",
        )
        service._issue_service._issues["issue_complete1"] = issue

        # Create a work item linked to the issue
        work = WorkItem(
            work_id="work_complete1",
            title="Test work",
            description="Test",
            project_id="proj_1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-1",
            issue_id="issue_complete1",
            context={"issue_id": "issue_complete1"},
        )
        service._work_items["work_complete1"] = work

        # Patch event bus to avoid errors
        with patch("services.assignment_service.get_event_bus") as mock_bus:
            mock_bus.return_value.emit_event = AsyncMock()

            result = await service.complete_work(
                "work_complete1",
                {"branch": "work/test", "summary": "Done", "commits": ["abc123"]},
                "compute-1"
            )

        assert result is not None
        assert result.status == WorkStatus.COMPLETED

        # Verify issue was updated
        assert issue.status == IssueStatus.DONE
        assert issue.result is not None
        assert issue.result.summary == "Done"

    @pytest.mark.asyncio
    async def test_completes_work_without_issue_link(self, work_map_service):
        """Test completing work without issue_id in context works fine."""
        service = work_map_service

        work = WorkItem(
            work_id="work_solo",
            title="Solo work",
            description="No issue link",
            project_id="proj_1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-1",
            context={},  # No issue_id
        )
        service._work_items["work_solo"] = work

        with patch("services.assignment_service.get_event_bus") as mock_bus:
            mock_bus.return_value.emit_event = AsyncMock()

            result = await service.complete_work(
                "work_solo",
                {"summary": "Done"},
                "compute-1"
            )

        assert result is not None
        assert result.status == WorkStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_complete_work_triggers_dependency_cascade(self, work_map_service):
        """Test that completing work cascades to unblock dependent issues."""
        service = work_map_service

        # Create two issues: issue_b depends on issue_a
        issue_a = Issue(
            issue_id="issue_a",
            title="First issue",
            description="Do first",
            status=IssueStatus.IN_PROGRESS,
            project_id="proj_1",
            blocks=["issue_b"],
        )
        issue_b = Issue(
            issue_id="issue_b",
            title="Second issue",
            description="Do second",
            status=IssueStatus.BACKLOG,
            project_id="proj_1",
            depends_on=["issue_a"],
        )
        service._issue_service._issues["issue_a"] = issue_a
        service._issue_service._issues["issue_b"] = issue_b

        # Create work item for issue_a
        work = WorkItem(
            work_id="work_a",
            title="Work for issue A",
            description="Test",
            project_id="proj_1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-1",
            issue_id="issue_a",
            context={"issue_id": "issue_a"},
        )
        service._work_items["work_a"] = work

        with patch("services.assignment_service.get_event_bus") as mock_bus:
            mock_bus.return_value.emit_event = AsyncMock()

            await service.complete_work(
                "work_a",
                {"branch": "work/a", "summary": "Done"},
                "compute-1"
            )

        # issue_a should be DONE
        assert issue_a.status == IssueStatus.DONE

        # issue_b should have been unblocked (moved from BACKLOG to READY)
        assert issue_b.status == IssueStatus.READY


# ============ Tests: fail_work_and_update_issue ============


class TestFailWorkAndUpdateIssue:
    """Test WorkMapService.fail_work_and_update_issue()."""

    @pytest.fixture
    def work_map_service(self):
        """Create service with mocked dependencies."""
        service = WorkMapService(redis_client=None)
        service._issue_service._save_issue_to_redis = AsyncMock()
        service._issue_service._save_issue_history_entry = AsyncMock()
        service._goal_service._save_goal_to_redis = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_fails_work_and_updates_issue(self, work_map_service):
        """Test failing work also marks the parent issue as failed."""
        service = work_map_service

        issue = Issue(
            issue_id="issue_fail1",
            title="Failing issue",
            description="Will fail",
            status=IssueStatus.IN_PROGRESS,
            project_id="proj_1",
        )
        service._issue_service._issues["issue_fail1"] = issue

        work = WorkItem(
            work_id="work_fail1",
            title="Failing work",
            description="Will fail",
            project_id="proj_1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-1",
            context={"issue_id": "issue_fail1"},
        )
        service._work_items["work_fail1"] = work

        with patch("services.assignment_service.get_event_bus") as mock_bus:
            mock_bus.return_value.emit_event = AsyncMock()

            result = await service.fail_work_and_update_issue(
                "work_fail1", "Compute crashed", "compute-1"
            )

        assert result is not None
        assert result.status == WorkStatus.FAILED
        assert result.error == "Compute crashed"
        assert issue.status == IssueStatus.FAILED

    @pytest.mark.asyncio
    async def test_fail_work_without_issue_link(self, work_map_service):
        """Test failing work without issue_id in context."""
        service = work_map_service

        work = WorkItem(
            work_id="work_fail_solo",
            title="Solo failing work",
            description="No issue",
            project_id="proj_1",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-1",
            context={},
        )
        service._work_items["work_fail_solo"] = work

        with patch("services.assignment_service.get_event_bus") as mock_bus:
            mock_bus.return_value.emit_event = AsyncMock()

            result = await service.fail_work_and_update_issue(
                "work_fail_solo", "Error occurred", "compute-1"
            )

        assert result is not None
        assert result.status == WorkStatus.FAILED

    @pytest.mark.asyncio
    async def test_fail_nonexistent_work(self, work_map_service):
        """Test failing nonexistent work returns None."""
        result = await work_map_service.fail_work_and_update_issue(
            "work_nonexistent", "Error"
        )
        assert result is None
