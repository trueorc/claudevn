"""Tests for AssignmentService."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from services.assignment_service import (
    AssignmentService,
    get_assignment_service,
    set_assignment_service
)
from models.work_map import (
    WorkItem, WorkStatus, WorkPriority,
    ProgressReport, BlockerType
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.hset = AsyncMock()
    redis._redis.hgetall = AsyncMock(return_value={})
    redis._redis.delete = AsyncMock()
    redis._redis.get = AsyncMock(return_value=None)
    redis._redis.sadd = AsyncMock()
    redis._redis.srem = AsyncMock()
    redis._redis.smembers = AsyncMock(return_value=set())
    redis._redis.zrange = AsyncMock(return_value=[])
    redis._prefix = "claudevn:"
    return redis


@pytest.fixture
def service():
    """Create service without Redis for in-memory testing."""
    return AssignmentService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """Create service with mocked Redis."""
    return AssignmentService(redis_client=mock_redis)


@pytest.fixture
def sample_work_item():
    """Create a sample work item."""
    return WorkItem(
        work_id="work_001",
        title="Test Work",
        description="Test description",
        project_id="proj-001",
        priority=WorkPriority.NORMAL,
        status=WorkStatus.PENDING,
        branch_name="work/work_001",
        base_branch="main"
    )


@pytest.fixture
def work_items_dict(sample_work_item):
    """Create a dictionary of work items."""
    return {sample_work_item.work_id: sample_work_item}


class TestAssignmentServiceInit:
    """Test AssignmentService initialization."""

    def test_init_without_redis(self):
        """Test initialization without Redis client."""
        service = AssignmentService()
        assert service._redis is None
        assert service._work_items == {}
        assert service._initialized is False

    def test_init_with_redis(self, mock_redis):
        """Test initialization with Redis client."""
        service = AssignmentService(redis_client=mock_redis)
        assert service._redis is mock_redis

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization."""
        await service.initialize()
        assert service._initialized is True


class TestWorkAssignment:
    """Test work assignment operations."""

    @pytest.mark.asyncio
    async def test_assign_work(self, service, sample_work_item, work_items_dict):
        """Test assigning work to compute."""
        service.set_work_items_reference(work_items_dict)

        assignment = await service.assign_work(
            work_id=sample_work_item.work_id,
            compute_id="compute-001",
            skills=["python", "testing"]
        )

        assert assignment is not None
        assert assignment.work_id == sample_work_item.work_id
        assert assignment.skills == ["python", "testing"]

        work = work_items_dict[sample_work_item.work_id]
        assert work.status == WorkStatus.ASSIGNED
        assert work.assigned_to == "compute-001"

    @pytest.mark.asyncio
    async def test_assign_work_persists_branch_name(self, service, sample_work_item, work_items_dict):
        """Test that branch_name is persisted to WorkItem on assignment."""
        service.set_work_items_reference(work_items_dict)

        # Verify initial branch_name
        assert sample_work_item.branch_name == "work/work_001"

        assignment = await service.assign_work(
            work_id=sample_work_item.work_id,
            compute_id="compute-001",
            skills=["python"],
            branch_name="work/work_001/compute-001"
        )

        assert assignment is not None
        # WorkItem should have the updated branch_name
        work = work_items_dict[sample_work_item.work_id]
        assert work.branch_name == "work/work_001/compute-001"
        # WorkAssignment should reflect the updated branch_name
        assert assignment.branch_name == "work/work_001/compute-001"

    @pytest.mark.asyncio
    async def test_assign_work_without_branch_name_preserves_original(self, service, sample_work_item, work_items_dict):
        """Test that omitting branch_name preserves the original value."""
        service.set_work_items_reference(work_items_dict)

        assignment = await service.assign_work(
            work_id=sample_work_item.work_id,
            compute_id="compute-001",
            skills=["python"]
        )

        assert assignment is not None
        work = work_items_dict[sample_work_item.work_id]
        assert work.branch_name == "work/work_001"

    @pytest.mark.asyncio
    async def test_assign_nonexistent_work(self, service):
        """Test assigning nonexistent work returns None."""
        service.set_work_items_reference({})

        assignment = await service.assign_work(
            work_id="nonexistent",
            compute_id="compute-001",
            skills=[]
        )

        assert assignment is None

    @pytest.mark.asyncio
    async def test_assign_work_with_unmet_dependencies(self, service):
        """Test cannot assign work with unmet dependencies."""
        dep_work = WorkItem(
            work_id="work_dep",
            title="Dependency",
            description="Dep",
            project_id="proj-001",
            status=WorkStatus.PENDING,
            branch_name="work/work_dep",
            base_branch="main"
        )
        work = WorkItem(
            work_id="work_001",
            title="Dependent",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.PENDING,
            depends_on=["work_dep"],
            branch_name="work/work_001",
            base_branch="main"
        )

        service.set_work_items_reference({
            "work_dep": dep_work,
            "work_001": work
        })

        assignment = await service.assign_work(
            work_id="work_001",
            compute_id="compute-001",
            skills=[]
        )

        assert assignment is None

    @pytest.mark.asyncio
    async def test_unassign_work(self, service, sample_work_item, work_items_dict):
        """Test unassigning work."""
        service.set_work_items_reference(work_items_dict)

        # First assign
        await service.assign_work(
            work_id=sample_work_item.work_id,
            compute_id="compute-001",
            skills=[]
        )

        # Then unassign
        result = await service.unassign_work(sample_work_item.work_id)

        assert result is True
        work = work_items_dict[sample_work_item.work_id]
        assert work.status == WorkStatus.PENDING
        assert work.assigned_to is None

    @pytest.mark.asyncio
    async def test_unassign_nonexistent_work(self, service):
        """Test unassigning nonexistent work returns False."""
        service.set_work_items_reference({})
        result = await service.unassign_work("nonexistent")
        assert result is False


class TestNextAssignment:
    """Test get_next_assignment operations."""

    @pytest.mark.asyncio
    async def test_get_next_assignment_by_capability(self, service):
        """Test get next assignment matches capabilities."""
        work1 = WorkItem(
            work_id="work_001",
            title="Needs Python",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.PENDING,
            required_capabilities=["python"],
            branch_name="work/work_001",
            base_branch="main"
        )
        work2 = WorkItem(
            work_id="work_002",
            title="Needs Java",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.PENDING,
            required_capabilities=["java"],
            branch_name="work/work_002",
            base_branch="main"
        )

        service.set_work_items_reference({
            "work_001": work1,
            "work_002": work2
        })

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=["python"]
        )

        assert assignment is not None
        assert assignment.work_id == "work_001"

    @pytest.mark.asyncio
    async def test_get_next_assignment_priority_order(self, service):
        """Test get next assignment respects priority."""
        low_work = WorkItem(
            work_id="work_low",
            title="Low Priority",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.PENDING,
            priority=WorkPriority.LOW,
            branch_name="work/work_low",
            base_branch="main"
        )
        high_work = WorkItem(
            work_id="work_high",
            title="High Priority",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.PENDING,
            priority=WorkPriority.HIGH,
            branch_name="work/work_high",
            base_branch="main"
        )

        service.set_work_items_reference({
            "work_low": low_work,
            "work_high": high_work
        })

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[]
        )

        assert assignment is not None
        assert assignment.work_id == "work_high"

    @pytest.mark.asyncio
    async def test_get_next_assignment_no_available(self, service):
        """Test get next assignment when no work available."""
        service.set_work_items_reference({})

        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[]
        )

        assert assignment is None


class TestStatusOperations:
    """Test status update operations."""

    @pytest.mark.asyncio
    async def test_update_status_valid_transition(self, service):
        """Test valid status transition."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-001"
        )

        service.set_work_items_reference({"work_001": work})

        result = await service.update_status(
            work_id="work_001",
            status=WorkStatus.IN_PROGRESS,
            compute_id="compute-001"
        )

        assert result is not None
        assert result.status == WorkStatus.IN_PROGRESS
        assert result.started_at is not None

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self, service, sample_work_item, work_items_dict):
        """Test invalid status transition returns None."""
        service.set_work_items_reference(work_items_dict)

        # PENDING -> COMPLETED is not valid
        result = await service.update_status(
            work_id=sample_work_item.work_id,
            status=WorkStatus.COMPLETED
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_status_completed_to_completed_idempotent(self, service):
        """Test COMPLETED->COMPLETED is idempotent, not an error (#829)."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.COMPLETED,
            assigned_to="compute-001",
        )
        service.set_work_items_reference({"work_001": work})

        result = await service.update_status(
            work_id="work_001",
            status=WorkStatus.COMPLETED,
        )

        # Should return the work item (idempotent), not None (error)
        assert result is not None
        assert result.status == WorkStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_status_failed_to_failed_idempotent(self, service):
        """Test FAILED->FAILED is idempotent, not an error (#829)."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.FAILED,
            assigned_to="compute-001",
        )
        service.set_work_items_reference({"work_001": work})

        result = await service.update_status(
            work_id="work_001",
            status=WorkStatus.FAILED,
        )

        assert result is not None
        assert result.status == WorkStatus.FAILED

    @pytest.mark.asyncio
    async def test_update_status_authorization_check(self, service):
        """Test status update authorization."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-001"
        )

        service.set_work_items_reference({"work_001": work})

        # Wrong compute ID should fail
        result = await service.update_status(
            work_id="work_001",
            status=WorkStatus.IN_PROGRESS,
            compute_id="wrong-compute"
        )

        assert result is None


class TestProgressReporting:
    """Test progress reporting."""

    @pytest.mark.asyncio
    async def test_report_progress(self, service):
        """Test reporting progress."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001"
        )

        service.set_work_items_reference({"work_001": work})

        report = ProgressReport(
            work_id="work_001",
            progress_percent=50,
            status=WorkStatus.IN_PROGRESS,
            note="Halfway done"
        )

        result = await service.report_progress("work_001", report)

        assert result is not None
        assert result.progress_percent == 50
        assert len(result.progress_notes) == 1

    @pytest.mark.asyncio
    async def test_complete_work(self, service):
        """Test completing work with result."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001"
        )

        service.set_work_items_reference({"work_001": work})

        result = await service.complete_work(
            work_id="work_001",
            result={"output": "success"},
            compute_id="compute-001"
        )

        assert result is not None
        assert result.status == WorkStatus.COMPLETED
        assert result.progress_percent == 100
        assert result.result == {"output": "success"}


class TestBlockerOperations:
    """Test blocker management."""

    @pytest.mark.asyncio
    async def test_add_blocker(self, service):
        """Test adding a blocker."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001"
        )

        service.set_work_items_reference({"work_001": work})

        blocker = await service.add_blocker(
            work_id="work_001",
            blocker_type=BlockerType.EXTERNAL,
            description="Waiting for API access"
        )

        assert blocker is not None
        assert blocker.blocker_type == BlockerType.EXTERNAL

        work = service._work_items["work_001"]
        assert work.status == WorkStatus.BLOCKED
        assert len(work.blockers) == 1

    @pytest.mark.asyncio
    async def test_resolve_blocker(self, service):
        """Test resolving a blocker."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS
        )

        service.set_work_items_reference({"work_001": work})

        blocker = await service.add_blocker(
            work_id="work_001",
            blocker_type=BlockerType.EXTERNAL,
            description="Waiting"
        )

        result = await service.resolve_blocker(
            work_id="work_001",
            blocker_id=blocker.blocker_id,
            resolution_note="Access granted"
        )

        assert result is True
        work = service._work_items["work_001"]
        assert work.blockers[0].resolution_note == "Access granted"


class TestTimeoutOperations:
    """Test timeout and stale work detection."""

    @pytest.mark.asyncio
    async def test_get_stale_work(self, service):
        """Test getting stale work items."""
        stale_work = WorkItem(
            work_id="work_stale",
            title="Stale Work",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            last_activity_at=datetime.now(timezone.utc) - timedelta(minutes=60)
        )
        fresh_work = WorkItem(
            work_id="work_fresh",
            title="Fresh Work",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            last_activity_at=datetime.now(timezone.utc)
        )

        service.set_work_items_reference({
            "work_stale": stale_work,
            "work_fresh": fresh_work
        })

        stale = await service.get_stale_work(timeout_minutes=30)

        assert len(stale) == 1
        assert stale[0].work_id == "work_stale"

    @pytest.mark.asyncio
    async def test_mark_work_timed_out_retry(self, service):
        """Test marking work as timed out returns to pending."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
            retry_count=0
        )

        service.set_work_items_reference({"work_001": work})

        result = await service.mark_work_timed_out("work_001", max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.PENDING
        assert result.retry_count == 1
        assert result.assigned_to is None

    @pytest.mark.asyncio
    async def test_mark_work_timed_out_max_retries(self, service):
        """Test marking work as timed out at max retries marks failed."""
        work = WorkItem(
            work_id="work_001",
            title="Test",
            description="Test",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
            retry_count=2
        )

        service.set_work_items_reference({"work_001": work})

        result = await service.mark_work_timed_out("work_001", max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.FAILED
        assert result.retry_count == 3
        assert "timed out after 3 retries" in result.error


class TestAssignmentServiceGlobals:
    """Test global instance management."""

    def test_set_get_service(self):
        """Test setting and getting global service."""
        service = AssignmentService()
        set_assignment_service(service)

        retrieved = get_assignment_service()
        assert retrieved is service

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_assignment_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_assignment_service()


# ============================================================================
# Test get_failed_work and mark_work_for_retry
# ============================================================================


class TestGetFailedWork:
    """Test retrieval of failed work items eligible for retry."""

    @pytest.fixture
    def service_with_items(self, service):
        """Create service with various work items."""
        items = {
            "work_failed_1": WorkItem(
                work_id="work_failed_1",
                title="Failed 1",
                description="Desc",
                project_id="proj-001",
                status=WorkStatus.FAILED,
                retry_count=0,
            ),
            "work_failed_2": WorkItem(
                work_id="work_failed_2",
                title="Failed 2",
                description="Desc",
                project_id="proj-001",
                status=WorkStatus.FAILED,
                retry_count=2,
            ),
            "work_failed_3": WorkItem(
                work_id="work_failed_3",
                title="Failed 3 (exhausted)",
                description="Desc",
                project_id="proj-001",
                status=WorkStatus.FAILED,
                retry_count=3,
            ),
            "work_pending": WorkItem(
                work_id="work_pending",
                title="Pending",
                description="Desc",
                project_id="proj-001",
                status=WorkStatus.PENDING,
            ),
        }
        service.set_work_items_reference(items)
        return service

    @pytest.mark.asyncio
    async def test_get_failed_work_returns_eligible(self, service_with_items):
        """Test returns only FAILED items under max_retries."""
        result = await service_with_items.get_failed_work(max_retries=3)

        ids = {w.work_id for w in result}
        assert ids == {"work_failed_1", "work_failed_2"}
        # work_failed_3 has retry_count=3 >= max_retries=3
        assert "work_failed_3" not in ids
        # work_pending is not FAILED
        assert "work_pending" not in ids

    @pytest.mark.asyncio
    async def test_get_failed_work_no_items(self, service):
        """Test returns empty list when no failed items."""
        service.set_work_items_reference({})
        result = await service.get_failed_work(max_retries=3)
        assert result == []


class TestMarkWorkForRetry:
    """Test returning failed work to PENDING for retry."""

    @pytest.fixture
    def service_with_failed(self, service):
        """Create service with a failed work item."""
        items = {
            "work_retry": WorkItem(
                work_id="work_retry",
                title="Failed Work",
                description="Git clone failed",
                project_id="proj-001",
                status=WorkStatus.FAILED,
                retry_count=0,
                error="Git clone failed",
                assigned_to="compute-001",
                assigned_skills=["code-writer"],
            ),
        }
        service.set_work_items_reference(items)
        return service

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_success(self, service_with_failed):
        """Test successful retry returns work to PENDING."""
        mock_save = AsyncMock()
        result = await service_with_failed.mark_work_for_retry(
            "work_retry", max_retries=3, save_callback=mock_save
        )

        assert result is not None
        assert result.status == WorkStatus.PENDING
        assert result.retry_count == 1
        assert result.error is None
        assert result.assigned_to is None
        assert result.assigned_skills == []
        assert result.assigned_at is None
        assert result.started_at is None
        assert result.completed_at is None
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_exhausted(self, service_with_failed):
        """Test retry with exhausted attempts leaves work as FAILED."""
        # Set retry_count to just below max
        service_with_failed._work_items["work_retry"].retry_count = 2

        mock_save = AsyncMock()
        result = await service_with_failed.mark_work_for_retry(
            "work_retry", max_retries=3, save_callback=mock_save
        )

        assert result is not None
        assert result.status == WorkStatus.FAILED
        assert result.retry_count == 3
        assert "failed after 3 retry attempts" in result.error
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_not_found(self, service):
        """Test retry for nonexistent work returns None."""
        service.set_work_items_reference({})
        result = await service.mark_work_for_retry("nonexistent", max_retries=3)
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_wrong_status(self, service):
        """Test retry for non-FAILED work returns None."""
        items = {
            "work_pending": WorkItem(
                work_id="work_pending",
                title="Pending",
                description="Desc",
                project_id="proj-001",
                status=WorkStatus.PENDING,
            ),
        }
        service.set_work_items_reference(items)

        result = await service.mark_work_for_retry("work_pending", max_retries=3)
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_adds_progress_note(self, service_with_failed):
        """Test retry adds a progress note."""
        mock_save = AsyncMock()
        result = await service_with_failed.mark_work_for_retry(
            "work_retry", max_retries=3, save_callback=mock_save
        )

        assert len(result.progress_notes) == 1
        assert "Retrying after failure" in result.progress_notes[0]
        assert "attempt 1/3" in result.progress_notes[0]

    @pytest.mark.asyncio
    async def test_mark_work_for_retry_with_redis(self, service_with_redis, mock_redis):
        """Test retry cleans up Redis indexes."""
        items = {
            "work_redis": WorkItem(
                work_id="work_redis",
                title="Failed Redis Work",
                description="Desc",
                project_id="proj-001",
                status=WorkStatus.FAILED,
                retry_count=0,
                assigned_to="compute-001",
            ),
        }
        service_with_redis.set_work_items_reference(items)

        mock_save = AsyncMock()
        result = await service_with_redis.mark_work_for_retry(
            "work_redis", max_retries=3, save_callback=mock_save
        )

        assert result.status == WorkStatus.PENDING
        # Verify Redis cleanup calls
        mock_redis._redis.srem.assert_any_call(
            "claudevn:workmap:work:status:failed", "work_redis"
        )
        mock_redis._redis.srem.assert_any_call(
            "claudevn:workmap:work:assignee:compute-001", "work_redis"
        )
        mock_redis._redis.delete.assert_any_call(
            "claudevn:workmap:workmap:compute:compute-001:current"
        )


class TestGetStaleAssignedWork:
    """Test detection of ASSIGNED work items that were never started."""

    @pytest.mark.asyncio
    async def test_returns_stale_assigned_items(self, service):
        """ASSIGNED items older than threshold with no started_at are returned."""
        work = WorkItem(
            work_id="work_stale",
            title="Stale Assigned",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-001",
            assigned_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            started_at=None,
        )
        service._work_items = {"work_stale": work}

        result = await service.get_stale_assigned_work(assigned_timeout_minutes=3)
        assert len(result) == 1
        assert result[0].work_id == "work_stale"

    @pytest.mark.asyncio
    async def test_ignores_recently_assigned(self, service):
        """ASSIGNED items within the threshold are not returned."""
        work = WorkItem(
            work_id="work_fresh",
            title="Fresh Assigned",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-001",
            assigned_at=datetime.now(timezone.utc) - timedelta(seconds=30),
            started_at=None,
        )
        service._work_items = {"work_fresh": work}

        result = await service.get_stale_assigned_work(assigned_timeout_minutes=3)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_ignores_started_items(self, service):
        """ASSIGNED items with started_at set are not returned."""
        work = WorkItem(
            work_id="work_started",
            title="Started",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-001",
            assigned_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        service._work_items = {"work_started": work}

        result = await service.get_stale_assigned_work(assigned_timeout_minutes=3)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_ignores_non_assigned_statuses(self, service):
        """Only ASSIGNED items are returned, not PENDING or IN_PROGRESS."""
        pending = WorkItem(
            work_id="work_pending",
            title="Pending",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.PENDING,
        )
        in_progress = WorkItem(
            work_id="work_ip",
            title="In Progress",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.IN_PROGRESS,
            assigned_to="compute-001",
            assigned_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        service._work_items = {
            "work_pending": pending,
            "work_ip": in_progress,
        }

        result = await service.get_stale_assigned_work(assigned_timeout_minutes=3)
        assert len(result) == 0


class TestResetAssignedToPending:
    """Test resetting stale ASSIGNED work items back to PENDING."""

    @pytest.mark.asyncio
    async def test_resets_to_pending(self, service):
        """Successfully resets ASSIGNED item to PENDING."""
        work = WorkItem(
            work_id="work_reset",
            title="Reset Me",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-001",
            assigned_skills=["code-writer"],
            assigned_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        service._work_items = {"work_reset": work}

        result = await service.reset_assigned_to_pending("work_reset")

        assert result is not None
        assert result.status == WorkStatus.PENDING
        assert result.assigned_to is None
        assert result.assigned_skills == []
        assert result.assigned_at is None
        assert result.started_at is None
        assert len(result.progress_notes) == 1
        assert "Stale ASSIGNED recovery" in result.progress_notes[0]
        assert "compute-001" in result.progress_notes[0]

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, service):
        """Returns None when work_id not found."""
        service._work_items = {}
        result = await service.reset_assigned_to_pending("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_non_assigned_status(self, service):
        """Returns None when work item is not in ASSIGNED status."""
        work = WorkItem(
            work_id="work_pending",
            title="Pending",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.PENDING,
        )
        service._work_items = {"work_pending": work}

        result = await service.reset_assigned_to_pending("work_pending")
        assert result is None

    @pytest.mark.asyncio
    async def test_cleans_up_redis(self, service_with_redis, mock_redis):
        """Verifies Redis index cleanup on reset."""
        work = WorkItem(
            work_id="work_redis",
            title="Redis Reset",
            description="desc",
            project_id="proj-001",
            status=WorkStatus.ASSIGNED,
            assigned_to="compute-002",
            assigned_skills=["code-writer"],
            assigned_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        service_with_redis._work_items = {"work_redis": work}

        save_cb = AsyncMock()
        result = await service_with_redis.reset_assigned_to_pending(
            "work_redis", save_callback=save_cb
        )

        assert result.status == WorkStatus.PENDING
        mock_redis._redis.srem.assert_any_call(
            "claudevn:workmap:work:status:assigned", "work_redis"
        )
        mock_redis._redis.srem.assert_any_call(
            "claudevn:workmap:work:assignee:compute-002", "work_redis"
        )
        mock_redis._redis.delete.assert_any_call(
            "claudevn:workmap:workmap:compute:compute-002:current"
        )
        save_cb.assert_awaited_once()
