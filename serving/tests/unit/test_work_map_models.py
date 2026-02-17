"""Tests for work_map models.

Comprehensive unit tests for Pydantic models in the work_map module.
Tests validation, defaults, enums, and model behaviors.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError

from models.work_map import (
    WorkStatus, WorkPriority, BlockerType,
    Blocker, WorkItem, WorkCreateRequest, WorkUpdateRequest,
    WorkAssignment, ProgressReport, WorkListResponse, WorkStats
)


# =============================================================================
# Test: Enums
# =============================================================================

class TestWorkStatusEnum:
    """Test WorkStatus enum."""

    def test_work_status_values(self):
        """Test all WorkStatus enum values exist."""
        assert WorkStatus.PENDING == "pending"
        assert WorkStatus.ASSIGNED == "assigned"
        assert WorkStatus.IN_PROGRESS == "in_progress"
        assert WorkStatus.BLOCKED == "blocked"
        assert WorkStatus.REVIEW == "review"
        assert WorkStatus.COMPLETED == "completed"
        assert WorkStatus.FAILED == "failed"

    def test_work_status_from_string(self):
        """Test creating WorkStatus from string."""
        assert WorkStatus("pending") == WorkStatus.PENDING
        assert WorkStatus("completed") == WorkStatus.COMPLETED

    def test_work_status_invalid(self):
        """Test invalid WorkStatus value."""
        with pytest.raises(ValueError):
            WorkStatus("invalid_status")


class TestWorkPriorityEnum:
    """Test WorkPriority enum."""

    def test_work_priority_values(self):
        """Test all WorkPriority enum values."""
        assert WorkPriority.CRITICAL == "critical"
        assert WorkPriority.HIGH == "high"
        assert WorkPriority.NORMAL == "normal"
        assert WorkPriority.LOW == "low"

    def test_work_priority_ordering_conceptual(self):
        """Test conceptual priority ordering."""
        # Document expected priority order (highest to lowest)
        priorities = [
            WorkPriority.CRITICAL,
            WorkPriority.HIGH,
            WorkPriority.NORMAL,
            WorkPriority.LOW
        ]
        assert len(priorities) == 4


class TestBlockerTypeEnum:
    """Test BlockerType enum."""

    def test_blocker_type_values(self):
        """Test all BlockerType enum values."""
        assert BlockerType.DEPENDENCY == "dependency"
        assert BlockerType.EXTERNAL == "external"
        assert BlockerType.RESOURCE == "resource"
        assert BlockerType.CLARIFICATION == "clarification"
        assert BlockerType.TECHNICAL == "technical"


# =============================================================================
# Test: Blocker Model
# =============================================================================

class TestBlockerModel:
    """Test Blocker model."""

    def test_blocker_required_fields(self):
        """Test blocker requires essential fields."""
        blocker = Blocker(
            blocker_id="blocker_001",
            blocker_type=BlockerType.DEPENDENCY,
            description="Waiting on task A"
        )

        assert blocker.blocker_id == "blocker_001"
        assert blocker.blocker_type == BlockerType.DEPENDENCY
        assert blocker.description == "Waiting on task A"

    def test_blocker_missing_required_field(self):
        """Test blocker validation for missing fields."""
        with pytest.raises(ValidationError):
            Blocker(
                blocker_type=BlockerType.EXTERNAL,
                description="Missing blocker_id"
            )

    def test_blocker_default_values(self):
        """Test blocker default values."""
        blocker = Blocker(
            blocker_id="blocker_001",
            blocker_type=BlockerType.TECHNICAL,
            description="Technical issue"
        )

        assert blocker.blocking_work_id is None
        assert blocker.resolved_at is None
        assert blocker.resolved_by is None
        assert blocker.resolution_note is None
        assert isinstance(blocker.created_at, datetime)

    def test_blocker_is_resolved_false(self):
        """Test is_resolved property when not resolved."""
        blocker = Blocker(
            blocker_id="blocker_001",
            blocker_type=BlockerType.EXTERNAL,
            description="Unresolved"
        )

        assert blocker.is_resolved is False

    def test_blocker_is_resolved_true(self):
        """Test is_resolved property when resolved."""
        blocker = Blocker(
            blocker_id="blocker_001",
            blocker_type=BlockerType.CLARIFICATION,
            description="Resolved",
            resolved_at=datetime.now(timezone.utc),
            resolved_by="user_001",
            resolution_note="Clarified requirements"
        )

        assert blocker.is_resolved is True

    def test_blocker_with_blocking_work_id(self):
        """Test blocker with dependency work ID."""
        blocker = Blocker(
            blocker_id="blocker_001",
            blocker_type=BlockerType.DEPENDENCY,
            description="Depends on work_abc",
            blocking_work_id="work_abc"
        )

        assert blocker.blocking_work_id == "work_abc"


# =============================================================================
# Test: WorkItem Model
# =============================================================================

class TestWorkItemModel:
    """Test WorkItem model."""

    def test_work_item_required_fields(self):
        """Test work item with required fields."""
        item = WorkItem(
            work_id="work_001",
            title="Implement feature X",
            description="Add the X feature",
            project_id="proj_001"
        )

        assert item.work_id == "work_001"
        assert item.title == "Implement feature X"
        assert item.description == "Add the X feature"
        assert item.project_id == "proj_001"

    def test_work_item_missing_required(self):
        """Test work item validation for missing required fields."""
        with pytest.raises(ValidationError):
            WorkItem(
                work_id="work_001",
                title="Missing project_id"
                # Missing description and project_id
            )

    def test_work_item_empty_project_id_rejected(self):
        """Test work item rejects empty project_id (Issue #373)."""
        with pytest.raises(ValidationError) as exc_info:
            WorkItem(
                work_id="work_001",
                title="Test",
                description="Test",
                project_id=""
            )
        # Verify the error is about project_id
        errors = exc_info.value.errors()
        assert any("project_id" in str(e.get("loc", [])) for e in errors)

    def test_work_item_whitespace_project_id_rejected(self):
        """Test work item rejects whitespace-only project_id (Issue #373)."""
        with pytest.raises(ValidationError) as exc_info:
            WorkItem(
                work_id="work_001",
                title="Test",
                description="Test",
                project_id="   "
            )
        # Verify the error mentions project attachment
        errors = exc_info.value.errors()
        assert any("project" in str(e.get("msg", "")).lower() for e in errors)

    def test_work_item_project_id_strips_whitespace(self):
        """Test work item strips whitespace from project_id (Issue #373)."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="  proj_001  "
        )
        assert item.project_id == "proj_001"

    def test_work_item_defaults(self):
        """Test work item default values."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test description",
            project_id="proj_001"
        )

        assert item.work_type == "task"
        assert item.priority == WorkPriority.NORMAL
        assert item.tags == []
        assert item.required_skills == []
        assert item.required_capabilities == []
        assert item.context == {}
        assert item.depends_on == []
        assert item.blocks == []
        assert item.base_branch == "main"
        assert item.status == WorkStatus.PENDING
        assert item.assigned_to is None
        assert item.assigned_skills == []
        assert item.blockers == []
        assert item.progress_percent == 0
        assert item.progress_notes == []
        assert item.result is None
        assert item.error is None

    def test_work_item_progress_validation(self):
        """Test progress_percent validation (0-100)."""
        # Valid range
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            progress_percent=50
        )
        assert item.progress_percent == 50

        # At boundaries
        item_0 = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            progress_percent=0
        )
        assert item_0.progress_percent == 0

        item_100 = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            progress_percent=100
        )
        assert item_100.progress_percent == 100

    def test_work_item_progress_invalid(self):
        """Test invalid progress_percent values."""
        with pytest.raises(ValidationError):
            WorkItem(
                work_id="work_001",
                title="Test",
                description="Test",
                project_id="proj_001",
                progress_percent=-1
            )

        with pytest.raises(ValidationError):
            WorkItem(
                work_id="work_001",
                title="Test",
                description="Test",
                project_id="proj_001",
                progress_percent=101
            )

    def test_work_item_active_blockers_empty(self):
        """Test active_blockers when no blockers."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001"
        )

        assert item.active_blockers == []
        assert item.is_blocked is False

    def test_work_item_active_blockers_with_resolved(self):
        """Test active_blockers filters resolved blockers."""
        resolved = Blocker(
            blocker_id="b1",
            blocker_type=BlockerType.EXTERNAL,
            description="Resolved",
            resolved_at=datetime.now(timezone.utc)
        )
        unresolved = Blocker(
            blocker_id="b2",
            blocker_type=BlockerType.TECHNICAL,
            description="Still active"
        )

        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            blockers=[resolved, unresolved]
        )

        assert len(item.active_blockers) == 1
        assert item.active_blockers[0].blocker_id == "b2"
        assert item.is_blocked is True

    def test_work_item_can_start_pending(self):
        """Test can_start for pending work."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            status=WorkStatus.PENDING
        )

        assert item.can_start is True

    def test_work_item_can_start_assigned(self):
        """Test can_start for assigned work."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            status=WorkStatus.ASSIGNED
        )

        assert item.can_start is True

    def test_work_item_cannot_start_in_progress(self):
        """Test can_start is False for in-progress work."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            status=WorkStatus.IN_PROGRESS
        )

        assert item.can_start is False

    def test_work_item_cannot_start_blocked(self):
        """Test can_start is False when blocked."""
        blocker = Blocker(
            blocker_id="b1",
            blocker_type=BlockerType.DEPENDENCY,
            description="Blocked"
        )

        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001",
            status=WorkStatus.PENDING,
            blockers=[blocker]
        )

        assert item.can_start is False


# =============================================================================
# Test: WorkCreateRequest Model
# =============================================================================

class TestWorkCreateRequestModel:
    """Test WorkCreateRequest model."""

    def test_create_request_required_fields(self):
        """Test create request with required fields."""
        request = WorkCreateRequest(
            title="New Work",
            description="Work description",
            project_id="proj_001"
        )

        assert request.title == "New Work"
        assert request.description == "Work description"
        assert request.project_id == "proj_001"

    def test_create_request_defaults(self):
        """Test create request default values."""
        request = WorkCreateRequest(
            title="New Work",
            description="Description",
            project_id="proj_001"
        )

        assert request.work_type == "task"
        assert request.priority == WorkPriority.NORMAL
        assert request.tags == []
        assert request.required_skills == []
        assert request.required_capabilities == []
        assert request.context == {}
        assert request.depends_on == []
        assert request.base_branch == "main"

    def test_create_request_custom_values(self):
        """Test create request with custom values."""
        request = WorkCreateRequest(
            title="Critical Bug",
            description="Fix critical bug",
            work_type="bug",
            priority=WorkPriority.CRITICAL,
            tags=["urgent", "production"],
            required_skills=["debugging"],
            required_capabilities=["python"],
            context={"file": "main.py"},
            depends_on=["work_000"],
            project_id="proj_001",
            base_branch="develop"
        )

        assert request.work_type == "bug"
        assert request.priority == WorkPriority.CRITICAL
        assert request.tags == ["urgent", "production"]
        assert request.base_branch == "develop"

    def test_create_request_missing_required(self):
        """Test create request validation for missing fields."""
        with pytest.raises(ValidationError):
            WorkCreateRequest(
                title="Missing fields"
                # Missing description and project_id
            )

    def test_create_request_empty_project_id_rejected(self):
        """Test create request rejects empty project_id (Issue #373)."""
        with pytest.raises(ValidationError) as exc_info:
            WorkCreateRequest(
                title="New Work",
                description="Description",
                project_id=""
            )
        # Verify error is about project_id
        errors = exc_info.value.errors()
        assert any("project_id" in str(e.get("loc", [])) for e in errors)

    def test_create_request_whitespace_project_id_rejected(self):
        """Test create request rejects whitespace-only project_id (Issue #373)."""
        with pytest.raises(ValidationError) as exc_info:
            WorkCreateRequest(
                title="New Work",
                description="Description",
                project_id="   "
            )
        # Verify the error mentions project attachment
        errors = exc_info.value.errors()
        assert any("project" in str(e.get("msg", "")).lower() for e in errors)

    def test_create_request_project_id_strips_whitespace(self):
        """Test create request strips whitespace from project_id (Issue #373)."""
        request = WorkCreateRequest(
            title="New Work",
            description="Description",
            project_id="  proj_001  "
        )
        assert request.project_id == "proj_001"

    def test_create_request_missing_project_id_error_message(self):
        """Test create request provides clear error for missing project_id (Issue #373)."""
        with pytest.raises(ValidationError) as exc_info:
            WorkCreateRequest(
                title="New Work",
                description="Description"
                # Missing project_id
            )
        # Verify we get a field required error
        errors = exc_info.value.errors()
        project_errors = [e for e in errors if "project_id" in str(e.get("loc", []))]
        assert len(project_errors) > 0


# =============================================================================
# Test: WorkUpdateRequest Model
# =============================================================================

class TestWorkUpdateRequestModel:
    """Test WorkUpdateRequest model."""

    def test_update_request_all_optional(self):
        """Test that all fields are optional."""
        request = WorkUpdateRequest()

        assert request.title is None
        assert request.description is None
        assert request.priority is None
        assert request.tags is None
        assert request.context is None

    def test_update_request_partial(self):
        """Test partial update request."""
        request = WorkUpdateRequest(
            title="Updated Title",
            priority=WorkPriority.HIGH
        )

        assert request.title == "Updated Title"
        assert request.priority == WorkPriority.HIGH
        assert request.description is None


# =============================================================================
# Test: WorkAssignment Model
# =============================================================================

class TestWorkAssignmentModel:
    """Test WorkAssignment model."""

    def test_assignment_required_fields(self):
        """Test assignment with required fields."""
        assignment = WorkAssignment(
            work_id="work_001",
            title="Task Title",
            description="Task description",
            skills=["python"],
            branch_name="feature/work_001",
            base_branch="main"
        )

        assert assignment.work_id == "work_001"
        assert assignment.skills == ["python"]
        assert assignment.branch_name == "feature/work_001"

    def test_assignment_defaults(self):
        """Test assignment default values."""
        assignment = WorkAssignment(
            work_id="work_001",
            title="Title",
            description="Desc",
            skills=[],
            branch_name="branch",
            base_branch="main"
        )

        assert assignment.context == {}
        assert assignment.dependencies == []
        assert assignment.dependency_outputs == {}


# =============================================================================
# Test: ProgressReport Model
# =============================================================================

class TestProgressReportModel:
    """Test ProgressReport model."""

    def test_progress_report_required_fields(self):
        """Test progress report with required fields."""
        report = ProgressReport(
            work_id="work_001",
            progress_percent=50,
            status=WorkStatus.IN_PROGRESS
        )

        assert report.work_id == "work_001"
        assert report.progress_percent == 50
        assert report.status == WorkStatus.IN_PROGRESS

    def test_progress_report_validation(self):
        """Test progress_percent validation."""
        with pytest.raises(ValidationError):
            ProgressReport(
                work_id="work_001",
                progress_percent=150,  # Invalid
                status=WorkStatus.IN_PROGRESS
            )

    def test_progress_report_with_note(self):
        """Test progress report with note."""
        report = ProgressReport(
            work_id="work_001",
            progress_percent=75,
            status=WorkStatus.IN_PROGRESS,
            note="Almost done",
            blockers=[{"type": "external", "desc": "Waiting"}]
        )

        assert report.note == "Almost done"
        assert len(report.blockers) == 1


# =============================================================================
# Test: WorkListResponse Model
# =============================================================================

class TestWorkListResponseModel:
    """Test WorkListResponse model."""

    def test_list_response_empty(self):
        """Test empty list response."""
        response = WorkListResponse(
            items=[],
            total=0,
            by_status={},
            by_priority={}
        )

        assert len(response.items) == 0
        assert response.total == 0

    def test_list_response_with_items(self):
        """Test list response with items."""
        item = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj_001"
        )

        response = WorkListResponse(
            items=[item],
            total=1,
            by_status={"pending": 1},
            by_priority={"normal": 1}
        )

        assert len(response.items) == 1
        assert response.by_status["pending"] == 1


# =============================================================================
# Test: WorkStats Model
# =============================================================================

class TestWorkStatsModel:
    """Test WorkStats model."""

    def test_work_stats_all_fields(self):
        """Test work stats with all fields."""
        stats = WorkStats(
            total=10,
            by_status={"pending": 5, "completed": 5},
            by_priority={"normal": 7, "high": 3},
            by_project={"proj_001": 10},
            blocked_count=2,
            assigned_count=3,
            unassigned_count=5
        )

        assert stats.total == 10
        assert stats.blocked_count == 2
        assert stats.assigned_count == 3
        assert stats.unassigned_count == 5
        assert stats.by_project["proj_001"] == 10


# =============================================================================
# Test: IssueHistory Models
# =============================================================================

class TestIssueHistoryModels:
    """Test IssueHistory and IssueHistoryEntry models."""

    def test_issue_history_entry_required_fields(self):
        """Test IssueHistoryEntry with required fields."""
        from models.work_map import IssueHistoryEntry
        from datetime import datetime, timezone

        entry = IssueHistoryEntry(
            commit="create",
            author="system",
            timestamp=datetime.now(timezone.utc),
            message="Created issue"
        )

        assert entry.commit == "create"
        assert entry.author == "system"
        assert entry.message == "Created issue"

    def test_issue_history_empty(self):
        """Test IssueHistory with no entries."""
        from models.work_map import IssueHistory

        history = IssueHistory(
            issue_id="issue_001",
            entries=[]
        )

        assert history.issue_id == "issue_001"
        assert history.entries == []

    def test_issue_history_with_entries(self):
        """Test IssueHistory with multiple entries."""
        from models.work_map import IssueHistory, IssueHistoryEntry
        from datetime import datetime, timezone

        entries = [
            IssueHistoryEntry(
                commit="create",
                author="system",
                timestamp=datetime.now(timezone.utc),
                message="Created issue"
            ),
            IssueHistoryEntry(
                commit="update",
                author="system",
                timestamp=datetime.now(timezone.utc),
                message="Updated title"
            )
        ]

        history = IssueHistory(
            issue_id="issue_001",
            entries=entries
        )

        assert len(history.entries) == 2
        assert history.entries[0].commit == "create"
        assert history.entries[1].commit == "update"
