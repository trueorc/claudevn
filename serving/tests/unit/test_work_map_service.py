"""Tests for WorkMapService."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from services.work_map_service import (
    WorkMapService,
    get_work_map_service,
    set_work_map_service
)
from models.work_map import (
    WorkItem, WorkStatus, WorkPriority, WorkCreateRequest,
    WorkUpdateRequest, WorkAssignment, ProgressReport, Blocker,
    BlockerType, WorkStats, WorkListResponse,
    IssueStatus, IssueCreateRequest,
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.hset = AsyncMock()
    redis._redis.hgetall = AsyncMock(return_value={})
    redis._redis.delete = AsyncMock()
    redis._redis.sadd = AsyncMock()
    redis._redis.srem = AsyncMock()
    redis._redis.scan = AsyncMock(return_value=(0, []))
    redis._prefix = "claudevn:"
    return redis


@pytest.fixture
def service():
    """Create service without Redis for in-memory testing."""
    return WorkMapService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """Create service with mocked Redis."""
    return WorkMapService(redis_client=mock_redis)


@pytest.fixture
def sample_create_request():
    """Create a sample work creation request."""
    return WorkCreateRequest(
        title="Test Work Item",
        description="Test description",
        work_type="task",
        priority=WorkPriority.NORMAL,
        tags=["test", "sample"],
        required_skills=["skill-a"],
        required_capabilities=["cap-x"],
        context={"key": "value"},
        depends_on=[],
        project_id="proj-001",
        base_branch="main"
    )


class TestWorkMapServiceInit:
    """Test WorkMapService initialization."""

    def test_init_without_redis(self):
        """Test initialization without Redis client."""
        service = WorkMapService()
        assert service._redis is None
        assert service._work_items == {}
        assert service._initialized is False

    def test_init_with_redis(self, mock_redis):
        """Test initialization with Redis client."""
        service = WorkMapService(redis_client=mock_redis)
        assert service._redis is mock_redis
        assert service._work_items == {}

    @pytest.mark.asyncio
    async def test_initialize(self, service):
        """Test service initialization."""
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self, service_with_redis, mock_redis):
        """Test service initialization loads from Redis."""
        await service_with_redis.initialize()
        assert service_with_redis._initialized is True
        mock_redis._redis.scan.assert_called()


class TestWorkMapServiceCRUD:
    """Test CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_work_item(self, service, sample_create_request):
        """Test creating a work item."""
        work = await service.create_work(sample_create_request)

        assert work.work_id.startswith("work_")
        assert work.title == "Test Work Item"
        assert work.description == "Test description"
        assert work.status == WorkStatus.PENDING
        assert work.priority == WorkPriority.NORMAL
        assert work.project_id == "proj-001"
        assert work.branch_name.startswith("f/work_")

    @pytest.mark.asyncio
    async def test_create_work_item_with_dependencies(self, service):
        """Test creating work with dependencies."""
        # Create dependency first
        dep_request = WorkCreateRequest(
            title="Dependency",
            description="Dependency work",
            project_id="proj-001"
        )
        dep_work = await service.create_work(dep_request)

        # Create dependent work
        request = WorkCreateRequest(
            title="Dependent Work",
            description="Depends on first work",
            project_id="proj-001",
            depends_on=[dep_work.work_id]
        )
        work = await service.create_work(request)

        assert dep_work.work_id in work.depends_on
        # Verify dependency graph updated
        dep_updated = await service.get_work(dep_work.work_id)
        assert work.work_id in dep_updated.blocks

    @pytest.mark.asyncio
    async def test_get_work_item(self, service, sample_create_request):
        """Test getting a work item by ID."""
        created = await service.create_work(sample_create_request)

        work = await service.get_work(created.work_id)

        assert work is not None
        assert work.work_id == created.work_id
        assert work.title == "Test Work Item"

    @pytest.mark.asyncio
    async def test_get_nonexistent_work(self, service):
        """Test getting nonexistent work returns None."""
        work = await service.get_work("nonexistent-work-id")
        assert work is None

    @pytest.mark.asyncio
    async def test_update_work_item(self, service, sample_create_request):
        """Test updating a work item."""
        created = await service.create_work(sample_create_request)

        update_request = WorkUpdateRequest(
            title="Updated Title",
            priority=WorkPriority.HIGH,
            tags=["updated"]
        )
        updated = await service.update_work(created.work_id, update_request)

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.priority == WorkPriority.HIGH
        assert "updated" in updated.tags
        assert updated.updated_at > created.created_at

    @pytest.mark.asyncio
    async def test_update_nonexistent_work(self, service):
        """Test updating nonexistent work returns None."""
        update_request = WorkUpdateRequest(title="New Title")
        result = await service.update_work("nonexistent", update_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_work_item(self, service, sample_create_request):
        """Test deleting a work item."""
        created = await service.create_work(sample_create_request)

        result = await service.delete_work(created.work_id)

        assert result is True
        assert await service.get_work(created.work_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_work(self, service):
        """Test deleting nonexistent work returns False."""
        result = await service.delete_work("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_work_updates_dependency_graph(self, service):
        """Test deleting work updates dependency graph."""
        # Create dependency
        dep_request = WorkCreateRequest(
            title="Dependency",
            description="Dep",
            project_id="proj-001"
        )
        dep_work = await service.create_work(dep_request)

        # Create dependent
        request = WorkCreateRequest(
            title="Dependent",
            description="Dep",
            project_id="proj-001",
            depends_on=[dep_work.work_id]
        )
        work = await service.create_work(request)

        # Delete dependent
        await service.delete_work(work.work_id)

        # Verify dependency graph cleaned up
        dep_updated = await service.get_work(dep_work.work_id)
        assert work.work_id not in dep_updated.blocks


class TestWorkMapServiceAssignment:
    """Test assignment operations."""

    @pytest.mark.asyncio
    async def test_assign_work_to_compute(self, service, sample_create_request):
        """Test assigning work to a compute instance."""
        work = await service.create_work(sample_create_request)

        assignment = await service.assign_work(
            work_id=work.work_id,
            compute_id="compute-001",
            skills=["skill-a", "skill-b"]
        )

        assert assignment is not None
        assert assignment.work_id == work.work_id
        assert assignment.skills == ["skill-a", "skill-b"]

        # Verify work updated
        updated = await service.get_work(work.work_id)
        assert updated.status == WorkStatus.ASSIGNED
        assert updated.assigned_to == "compute-001"
        assert updated.assigned_at is not None

    @pytest.mark.asyncio
    async def test_assign_nonexistent_work(self, service):
        """Test assigning nonexistent work returns None."""
        assignment = await service.assign_work(
            work_id="nonexistent",
            compute_id="compute-001",
            skills=[]
        )
        assert assignment is None

    @pytest.mark.asyncio
    async def test_assign_work_with_unmet_dependencies(self, service):
        """Test cannot assign work with unmet dependencies."""
        # Create dependency
        dep_request = WorkCreateRequest(
            title="Dependency",
            description="Dep",
            project_id="proj-001"
        )
        dep_work = await service.create_work(dep_request)

        # Create dependent
        request = WorkCreateRequest(
            title="Dependent",
            description="Dep",
            project_id="proj-001",
            depends_on=[dep_work.work_id]
        )
        work = await service.create_work(request)

        # Try to assign - should fail due to unmet dependency
        assignment = await service.assign_work(
            work_id=work.work_id,
            compute_id="compute-001",
            skills=[]
        )
        assert assignment is None

    @pytest.mark.asyncio
    async def test_assign_work_after_dependency_completed(self, service):
        """Test can assign work after dependency is completed."""
        # Create dependency
        dep_request = WorkCreateRequest(
            title="Dependency",
            description="Dep",
            project_id="proj-001"
        )
        dep_work = await service.create_work(dep_request)

        # Create dependent
        request = WorkCreateRequest(
            title="Dependent",
            description="Dep",
            project_id="proj-001",
            depends_on=[dep_work.work_id]
        )
        work = await service.create_work(request)

        # Complete dependency
        await service.assign_work(dep_work.work_id, "compute-001", [])
        await service.update_status(dep_work.work_id, WorkStatus.IN_PROGRESS, "compute-001")
        await service.complete_work(dep_work.work_id, {"done": True}, "compute-001")

        # Now should be able to assign
        assignment = await service.assign_work(
            work_id=work.work_id,
            compute_id="compute-002",
            skills=[]
        )
        assert assignment is not None

    @pytest.mark.asyncio
    async def test_unassign_work(self, service, sample_create_request):
        """Test unassigning work from compute."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])

        result = await service.unassign_work(work.work_id)

        assert result is True
        updated = await service.get_work(work.work_id)
        assert updated.status == WorkStatus.PENDING
        assert updated.assigned_to is None

    @pytest.mark.asyncio
    async def test_unassign_nonexistent_work(self, service):
        """Test unassigning nonexistent work returns False."""
        result = await service.unassign_work("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_next_assignment_by_capability(self, service):
        """Test get next assignment matches capabilities."""
        # Create work requiring specific capability
        request1 = WorkCreateRequest(
            title="Work 1",
            description="Needs cap-x",
            project_id="proj-001",
            required_capabilities=["cap-x"]
        )
        work1 = await service.create_work(request1)

        request2 = WorkCreateRequest(
            title="Work 2",
            description="Needs cap-y",
            project_id="proj-001",
            required_capabilities=["cap-y"]
        )
        work2 = await service.create_work(request2)

        # Request with cap-x only
        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=["cap-x"]
        )

        assert assignment is not None
        assert assignment.work_id == work1.work_id

    @pytest.mark.asyncio
    async def test_get_next_assignment_priority_order(self, service):
        """Test get next assignment prioritizes by priority."""
        # Create low priority first
        low_request = WorkCreateRequest(
            title="Low Priority",
            description="Low",
            project_id="proj-001",
            priority=WorkPriority.LOW
        )
        low_work = await service.create_work(low_request)

        # Create high priority second
        high_request = WorkCreateRequest(
            title="High Priority",
            description="High",
            project_id="proj-001",
            priority=WorkPriority.HIGH
        )
        high_work = await service.create_work(high_request)

        # Should get high priority first
        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[]
        )

        assert assignment is not None
        assert assignment.work_id == high_work.work_id

    @pytest.mark.asyncio
    async def test_get_next_assignment_no_available_work(self, service):
        """Test get next assignment when no work available."""
        assignment = await service.get_next_assignment(
            compute_id="compute-001",
            capabilities=[]
        )
        assert assignment is None


class TestWorkMapServiceStatus:
    """Test status operations."""

    @pytest.mark.asyncio
    async def test_update_work_status_transitions(self, service, sample_create_request):
        """Test valid status transitions."""
        work = await service.create_work(sample_create_request)

        # PENDING -> ASSIGNED
        await service.assign_work(work.work_id, "compute-001", [])
        work = await service.get_work(work.work_id)
        assert work.status == WorkStatus.ASSIGNED

        # ASSIGNED -> IN_PROGRESS
        result = await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")
        assert result is not None
        assert result.status == WorkStatus.IN_PROGRESS
        assert result.started_at is not None

        # IN_PROGRESS -> COMPLETED
        result = await service.update_status(work.work_id, WorkStatus.COMPLETED, "compute-001")
        assert result is not None
        assert result.status == WorkStatus.COMPLETED
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_invalid_status_transition(self, service, sample_create_request):
        """Test invalid status transitions return None."""
        work = await service.create_work(sample_create_request)

        # PENDING -> COMPLETED is not valid (must go through ASSIGNED, IN_PROGRESS)
        result = await service.update_status(work.work_id, WorkStatus.COMPLETED)
        assert result is None

    @pytest.mark.asyncio
    async def test_status_authorization_check(self, service, sample_create_request):
        """Test status update authorization."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])

        # Wrong compute ID should fail
        result = await service.update_status(
            work.work_id,
            WorkStatus.IN_PROGRESS,
            compute_id="wrong-compute"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_complete_work(self, service, sample_create_request):
        """Test completing work with result."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        result = await service.complete_work(
            work_id=work.work_id,
            result={"output": "success", "data": [1, 2, 3]},
            compute_id="compute-001"
        )

        assert result is not None
        assert result.status == WorkStatus.COMPLETED
        assert result.result == {"output": "success", "data": [1, 2, 3]}
        assert result.progress_percent == 100

    @pytest.mark.asyncio
    async def test_fail_work(self, service, sample_create_request):
        """Test transitioning work to failed status."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        result = await service.update_status(
            work.work_id,
            WorkStatus.FAILED,
            "compute-001"
        )

        assert result is not None
        assert result.status == WorkStatus.FAILED
        assert result.completed_at is not None


class TestWorkMapServiceBlockers:
    """Test blocker operations."""

    @pytest.mark.asyncio
    async def test_add_blocker(self, service, sample_create_request):
        """Test adding a blocker to work."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        blocker = await service.add_blocker(
            work_id=work.work_id,
            blocker_type=BlockerType.EXTERNAL,
            description="Waiting for API access"
        )

        assert blocker is not None
        assert blocker.blocker_id.startswith("blk_")
        assert blocker.blocker_type == BlockerType.EXTERNAL
        assert blocker.description == "Waiting for API access"

        # Verify work status changed
        updated = await service.get_work(work.work_id)
        assert updated.status == WorkStatus.BLOCKED
        assert len(updated.blockers) == 1

    @pytest.mark.asyncio
    async def test_add_dependency_blocker(self, service, sample_create_request):
        """Test adding a dependency blocker."""
        # Create blocking work
        blocking_work = await service.create_work(sample_create_request)

        # Create blocked work
        blocked_request = WorkCreateRequest(
            title="Blocked Work",
            description="Blocked",
            project_id="proj-001"
        )
        blocked_work = await service.create_work(blocked_request)
        await service.assign_work(blocked_work.work_id, "compute-001", [])
        await service.update_status(blocked_work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        blocker = await service.add_blocker(
            work_id=blocked_work.work_id,
            blocker_type=BlockerType.DEPENDENCY,
            description="Waiting for data",
            blocking_work_id=blocking_work.work_id
        )

        assert blocker is not None
        assert blocker.blocking_work_id == blocking_work.work_id

    @pytest.mark.asyncio
    async def test_resolve_blocker(self, service, sample_create_request):
        """Test resolving a blocker."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        blocker = await service.add_blocker(
            work_id=work.work_id,
            blocker_type=BlockerType.EXTERNAL,
            description="Waiting"
        )

        result = await service.resolve_blocker(
            work_id=work.work_id,
            blocker_id=blocker.blocker_id,
            resolution_note="Access granted",
            resolved_by="admin"
        )

        assert result is True

        updated = await service.get_work(work.work_id)
        assert updated.status == WorkStatus.IN_PROGRESS  # Unblocked
        assert updated.blockers[0].is_resolved
        assert updated.blockers[0].resolution_note == "Access granted"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_blocker(self, service, sample_create_request):
        """Test resolving nonexistent blocker returns False."""
        work = await service.create_work(sample_create_request)

        result = await service.resolve_blocker(
            work_id=work.work_id,
            blocker_id="nonexistent"
        )
        assert result is False


class TestWorkMapServiceQuery:
    """Test query operations."""

    @pytest.mark.asyncio
    async def test_list_work_all(self, service):
        """Test listing all work items."""
        # Create multiple work items
        for i in range(5):
            request = WorkCreateRequest(
                title=f"Work {i}",
                description=f"Description {i}",
                project_id="proj-001"
            )
            await service.create_work(request)

        result = await service.list_work()

        assert len(result.items) == 5
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_list_work_by_status(self, service):
        """Test listing work items filtered by status."""
        # Create pending work
        request1 = WorkCreateRequest(
            title="Pending Work",
            description="Pending",
            project_id="proj-001"
        )
        await service.create_work(request1)

        # Create and assign work
        request2 = WorkCreateRequest(
            title="Assigned Work",
            description="Assigned",
            project_id="proj-001"
        )
        work2 = await service.create_work(request2)
        await service.assign_work(work2.work_id, "compute-001", [])

        # List pending only
        result = await service.list_work(status=WorkStatus.PENDING)
        assert len(result.items) == 1
        assert result.items[0].title == "Pending Work"

        # List assigned only
        result = await service.list_work(status=WorkStatus.ASSIGNED)
        assert len(result.items) == 1
        assert result.items[0].title == "Assigned Work"

    @pytest.mark.asyncio
    async def test_list_work_by_project(self, service):
        """Test listing work items filtered by project."""
        # Create work in project A
        request1 = WorkCreateRequest(
            title="Project A Work",
            description="A",
            project_id="proj-a"
        )
        await service.create_work(request1)

        # Create work in project B
        request2 = WorkCreateRequest(
            title="Project B Work",
            description="B",
            project_id="proj-b"
        )
        await service.create_work(request2)

        # List project A only
        result = await service.list_work(project_id="proj-a")
        assert len(result.items) == 1
        assert result.items[0].project_id == "proj-a"

    @pytest.mark.asyncio
    async def test_list_work_by_priority(self, service):
        """Test listing work items filtered by priority."""
        # Create different priorities
        for priority in [WorkPriority.LOW, WorkPriority.NORMAL, WorkPriority.HIGH]:
            request = WorkCreateRequest(
                title=f"{priority.value} Priority",
                description="Test",
                project_id="proj-001",
                priority=priority
            )
            await service.create_work(request)

        # List high priority only
        result = await service.list_work(priority=WorkPriority.HIGH)
        assert len(result.items) == 1
        assert result.items[0].priority == WorkPriority.HIGH

    @pytest.mark.asyncio
    async def test_list_work_pagination(self, service):
        """Test listing work with limit."""
        # Create 10 work items
        for i in range(10):
            request = WorkCreateRequest(
                title=f"Work {i}",
                description=f"Description {i}",
                project_id="proj-001"
            )
            await service.create_work(request)

        # Get only 5
        result = await service.list_work(limit=5)
        assert len(result.items) == 5
        assert result.total == 10

    @pytest.mark.asyncio
    async def test_get_stats(self, service):
        """Test getting work map statistics."""
        # Create work items with different statuses and priorities
        request1 = WorkCreateRequest(
            title="Work 1",
            description="Test",
            project_id="proj-a",
            priority=WorkPriority.HIGH
        )
        work1 = await service.create_work(request1)

        request2 = WorkCreateRequest(
            title="Work 2",
            description="Test",
            project_id="proj-b",
            priority=WorkPriority.LOW
        )
        work2 = await service.create_work(request2)
        await service.assign_work(work2.work_id, "compute-001", [])

        stats = await service.get_stats()

        assert stats.total == 2
        assert stats.by_status.get("pending", 0) == 1
        assert stats.by_status.get("assigned", 0) == 1
        assert stats.by_priority.get("high", 0) == 1
        assert stats.by_priority.get("low", 0) == 1
        assert stats.assigned_count == 1
        assert stats.unassigned_count == 1


class TestWorkMapServiceDependencies:
    """Test dependency operations."""

    @pytest.mark.asyncio
    async def test_get_dependencies(self, service):
        """Test getting dependency information."""
        # Create dependency
        dep_request = WorkCreateRequest(
            title="Dependency",
            description="Dep",
            project_id="proj-001"
        )
        dep_work = await service.create_work(dep_request)

        # Create dependent
        request = WorkCreateRequest(
            title="Dependent",
            description="Dep",
            project_id="proj-001",
            depends_on=[dep_work.work_id]
        )
        work = await service.create_work(request)

        deps = await service.get_dependencies(work.work_id)

        assert deps["work_id"] == work.work_id
        assert len(deps["depends_on"]) == 1
        assert deps["depends_on"][0]["work_id"] == dep_work.work_id
        assert deps["depends_on"][0]["completed"] is False
        assert deps["all_dependencies_met"] is False

    @pytest.mark.asyncio
    async def test_check_dependencies_met(self, service):
        """Test dependency completion checking."""
        # Create dependency
        dep_request = WorkCreateRequest(
            title="Dependency",
            description="Dep",
            project_id="proj-001"
        )
        dep_work = await service.create_work(dep_request)

        # Create dependent
        request = WorkCreateRequest(
            title="Dependent",
            description="Dep",
            project_id="proj-001",
            depends_on=[dep_work.work_id]
        )
        work = await service.create_work(request)

        # Initially not met
        deps = await service.get_dependencies(work.work_id)
        assert deps["all_dependencies_met"] is False

        # Complete dependency
        await service.assign_work(dep_work.work_id, "compute-001", [])
        await service.update_status(dep_work.work_id, WorkStatus.IN_PROGRESS, "compute-001")
        await service.complete_work(dep_work.work_id, {}, "compute-001")

        # Now should be met
        deps = await service.get_dependencies(work.work_id)
        assert deps["all_dependencies_met"] is True

    @pytest.mark.asyncio
    async def test_get_dependencies_nonexistent_work(self, service):
        """Test getting dependencies for nonexistent work."""
        deps = await service.get_dependencies("nonexistent")
        assert deps == {}


class TestWorkMapServiceProgress:
    """Test progress reporting."""

    @pytest.mark.asyncio
    async def test_report_progress(self, service, sample_create_request):
        """Test reporting progress on work."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        report = ProgressReport(
            work_id=work.work_id,
            progress_percent=50,
            status=WorkStatus.IN_PROGRESS,
            note="Halfway done"
        )
        result = await service.report_progress(work.work_id, report)

        assert result is not None
        assert result.progress_percent == 50
        assert len(result.progress_notes) == 1
        assert "Halfway done" in result.progress_notes[0]

    @pytest.mark.asyncio
    async def test_report_progress_with_blockers(self, service, sample_create_request):
        """Test reporting progress with new blockers."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        report = ProgressReport(
            work_id=work.work_id,
            progress_percent=30,
            status=WorkStatus.BLOCKED,
            blockers=[{
                "type": "external",
                "description": "Need approval"
            }]
        )
        result = await service.report_progress(work.work_id, report)

        assert result is not None
        assert len(result.blockers) == 1
        assert result.blockers[0].description == "Need approval"


class TestWorkMapServiceGlobals:
    """Test global instance management."""

    def test_set_get_service(self):
        """Test setting and getting global service."""
        service = WorkMapService()
        set_work_map_service(service)

        retrieved = get_work_map_service()
        assert retrieved is service

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_work_map_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_work_map_service()


class TestWorkMapServiceTimeout:
    """Test timeout and stuck-work detection functionality."""

    @pytest.mark.asyncio
    async def test_get_stale_work_returns_old_in_progress(self, service, sample_create_request):
        """Test get_stale_work returns work that has been IN_PROGRESS too long."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        # Simulate work being stale by backdating last_activity_at
        work = await service.get_work(work.work_id)
        work.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        work.updated_at = datetime.now(timezone.utc) - timedelta(minutes=60)

        stale_work = await service.get_stale_work(timeout_minutes=30)

        assert len(stale_work) == 1
        assert stale_work[0].work_id == work.work_id

    @pytest.mark.asyncio
    async def test_get_stale_work_excludes_recent_activity(self, service, sample_create_request):
        """Test get_stale_work excludes work with recent activity."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        # Work just started - should not be stale
        stale_work = await service.get_stale_work(timeout_minutes=30)

        assert len(stale_work) == 0

    @pytest.mark.asyncio
    async def test_get_stale_work_excludes_non_in_progress(self, service, sample_create_request):
        """Test get_stale_work only returns IN_PROGRESS work."""
        work = await service.create_work(sample_create_request)

        # Work is PENDING, not IN_PROGRESS
        work = await service.get_work(work.work_id)
        work.updated_at = datetime.now(timezone.utc) - timedelta(minutes=60)

        stale_work = await service.get_stale_work(timeout_minutes=30)

        assert len(stale_work) == 0

    @pytest.mark.asyncio
    async def test_mark_work_timed_out_returns_to_pending(self, service, sample_create_request):
        """Test marking work as timed out returns it to PENDING for retry."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", ["skill-a"])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        updated = await service.mark_work_timed_out(work.work_id, max_retries=3)

        assert updated is not None
        assert updated.status == WorkStatus.PENDING
        assert updated.retry_count == 1
        assert updated.assigned_to is None
        assert updated.started_at is None
        assert updated.last_activity_at is None
        assert "Timed out" in updated.progress_notes[-1]

    @pytest.mark.asyncio
    async def test_mark_work_timed_out_marks_failed_at_max_retries(
        self, service, sample_create_request
    ):
        """Test marking work as timed out marks FAILED at max retries."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        # Simulate already having 2 retries
        work = await service.get_work(work.work_id)
        work.retry_count = 2

        # Third retry should mark as FAILED
        updated = await service.mark_work_timed_out(work.work_id, max_retries=3)

        assert updated is not None
        assert updated.status == WorkStatus.FAILED
        assert updated.retry_count == 3
        assert updated.error is not None
        assert "timed out after 3 retries" in updated.error

    @pytest.mark.asyncio
    async def test_mark_work_timed_out_nonexistent_work(self, service):
        """Test marking nonexistent work returns None."""
        result = await service.mark_work_timed_out("nonexistent_work_id", max_retries=3)
        assert result is None

    @pytest.mark.asyncio
    async def test_report_progress_updates_last_activity(self, service, sample_create_request):
        """Test that reporting progress updates last_activity_at."""
        work = await service.create_work(sample_create_request)
        await service.assign_work(work.work_id, "compute-001", [])
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        # Get initial activity time
        work = await service.get_work(work.work_id)
        initial_activity = work.last_activity_at

        # Small delay to ensure time difference
        import asyncio
        await asyncio.sleep(0.01)

        # Report progress
        report = ProgressReport(
            work_id=work.work_id,
            progress_percent=50,
            status=WorkStatus.IN_PROGRESS,
            note="Making progress"
        )
        updated = await service.report_progress(work.work_id, report)

        assert updated.last_activity_at > initial_activity

    @pytest.mark.asyncio
    async def test_work_item_has_retry_count_field(self, service, sample_create_request):
        """Test that WorkItem has retry_count field initialized to 0."""
        work = await service.create_work(sample_create_request)

        assert hasattr(work, 'retry_count')
        assert work.retry_count == 0

    @pytest.mark.asyncio
    async def test_work_item_has_last_activity_at_field(self, service, sample_create_request):
        """Test that WorkItem has last_activity_at field."""
        work = await service.create_work(sample_create_request)

        assert hasattr(work, 'last_activity_at')
        # Initially None until work starts
        assert work.last_activity_at is None

        # After starting, should be set
        await service.assign_work(work.work_id, "compute-001", [])
        updated = await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        assert updated.last_activity_at is not None


class TestWorkMapServiceIssueHistory:
    """Test WorkMapService issue history functionality."""

    @pytest.fixture
    def issue_create_request(self):
        """Create a sample issue creation request."""
        from models.work_map import IssueCreateRequest, IssueArea
        return IssueCreateRequest(
            title="Test Issue",
            description="Test description",
            area=IssueArea.API
        )

    @pytest.mark.asyncio
    async def test_get_issue_history_without_redis(self, service, issue_create_request):
        """Test getting issue history without Redis returns empty history."""
        issue = await service.create_issue(issue_create_request)
        history = await service.get_issue_history(issue.issue_id)

        assert history.issue_id == issue.issue_id
        assert history.entries == []

    @pytest.mark.asyncio
    async def test_get_issue_history_with_redis(self, service_with_redis, mock_redis, issue_create_request):
        """Test getting issue history with Redis."""
        import json
        from datetime import datetime, timezone

        # Setup mock to return history entries
        mock_redis._redis.lrange = AsyncMock(return_value=[
            json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "create",
                "details": "Created: Test Issue"
            })
        ])
        mock_redis._redis.lpush = AsyncMock()
        mock_redis._redis.ltrim = AsyncMock()

        issue = await service_with_redis.create_issue(issue_create_request)
        history = await service_with_redis.get_issue_history(issue.issue_id)

        assert history.issue_id == issue.issue_id
        assert len(history.entries) == 1
        assert history.entries[0].message == "Created: Test Issue"

    @pytest.mark.asyncio
    async def test_history_entry_saved_on_create(self, service_with_redis, mock_redis, issue_create_request):
        """Test that a history entry is saved when creating an issue."""
        mock_redis._redis.lpush = AsyncMock()
        mock_redis._redis.ltrim = AsyncMock()
        mock_redis._redis.lrange = AsyncMock(return_value=[])

        await service_with_redis.create_issue(issue_create_request)

        # Verify lpush was called to add history
        mock_redis._redis.lpush.assert_called()

    @pytest.mark.asyncio
    async def test_history_entry_saved_on_update(self, service_with_redis, mock_redis, issue_create_request):
        """Test that a history entry is saved when updating an issue."""
        from models.work_map import IssueUpdateRequest

        mock_redis._redis.lpush = AsyncMock()
        mock_redis._redis.ltrim = AsyncMock()
        mock_redis._redis.lrange = AsyncMock(return_value=[])

        issue = await service_with_redis.create_issue(issue_create_request)

        # Reset mock to check update call
        mock_redis._redis.lpush.reset_mock()

        update_request = IssueUpdateRequest(title="Updated Title")
        await service_with_redis.update_issue(issue.issue_id, update_request)

        # Verify lpush was called for the update
        mock_redis._redis.lpush.assert_called()


# ============================================================================
# Test mark_work_for_retry resets issue status
# ============================================================================


class TestMarkWorkForRetryIssueStatus:
    """Regression: mark_work_for_retry must reset the parent issue status.

    Previously, when a work item was retried, the parent issue stayed FAILED.
    On subsequent failure, this caused an invalid FAILED→FAILED transition warning.

    See: https://github.com/Guarrdon/claudevn/issues/662
    """

    @pytest.fixture
    def service(self):
        return WorkMapService(redis_client=None)

    @pytest.mark.asyncio
    async def test_retry_resets_issue_to_in_progress(self, service):
        """When work retries, parent issue should go from FAILED to IN_PROGRESS."""
        # Create an issue and advance it to FAILED
        issue = await service.create_issue(IssueCreateRequest(
            title="Test Issue",
            description="Test",
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)
        await service.update_issue_status(issue.issue_id, IssueStatus.FAILED)

        # Create a work item linked to the issue
        work = await service.create_work(WorkCreateRequest(
            title="Test Work",
            description="Test",
            required_capabilities=["coding"],
            project_id="proj-1",
        ))
        # Link work to issue via context
        work.context = {"issue_id": issue.issue_id}

        # Manually set work to FAILED to simulate a failed execution
        work.status = WorkStatus.FAILED
        work.retry_count = 0

        # Now retry the work
        result = await service.mark_work_for_retry(work.work_id, max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.PENDING

        # The parent issue should now be IN_PROGRESS, not FAILED
        refreshed_issue = await service.get_issue(issue.issue_id)
        assert refreshed_issue.status == IssueStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_retry_no_issue_link_still_works(self, service):
        """Retry should work even if work has no linked issue."""
        work = await service.create_work(WorkCreateRequest(
            title="Unlinked Work",
            description="No issue link",
            required_capabilities=["coding"],
            project_id="proj-1",
        ))
        work.status = WorkStatus.FAILED
        work.retry_count = 0

        result = await service.mark_work_for_retry(work.work_id, max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.PENDING

    @pytest.mark.asyncio
    async def test_exhausted_retry_does_not_reset_issue(self, service):
        """When retries are exhausted, issue should stay FAILED."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Exhausted Issue",
            description="Test",
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)
        await service.update_issue_status(issue.issue_id, IssueStatus.FAILED)

        work = await service.create_work(WorkCreateRequest(
            title="Exhausted Work",
            description="Test",
            required_capabilities=["coding"],
            project_id="proj-1",
        ))
        work.context = {"issue_id": issue.issue_id}
        work.status = WorkStatus.FAILED
        work.retry_count = 2  # At max

        result = await service.mark_work_for_retry(work.work_id, max_retries=3)

        assert result is not None
        assert result.status == WorkStatus.FAILED  # Exhausted

        # Issue should still be FAILED
        refreshed_issue = await service.get_issue(issue.issue_id)
        assert refreshed_issue.status == IssueStatus.FAILED

    @pytest.mark.asyncio
    async def test_full_retry_lifecycle_no_invalid_transitions(self, service):
        """Full lifecycle: create → assign → fail → retry → assign → fail (no warnings)."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Lifecycle Issue",
            description="Test",
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)

        work = await service.create_work(WorkCreateRequest(
            title="Lifecycle Work",
            description="Test",
            required_capabilities=["coding"],
            project_id="proj-1",
        ))
        work.context = {"issue_id": issue.issue_id}

        # Simulate assignment: PENDING → ASSIGNED → IN_PROGRESS
        await service.assign_work(
            work_id=work.work_id,
            compute_id="compute-001",
            skills=["code-writer"]
        )
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-001")

        # First failure (IN_PROGRESS → FAILED)
        failed = await service.fail_work_and_update_issue(work.work_id, "SSH error")
        assert failed is not None
        issue_after_fail = await service.get_issue(issue.issue_id)
        assert issue_after_fail.status == IssueStatus.FAILED

        # Retry — should reset issue to IN_PROGRESS
        retried = await service.mark_work_for_retry(work.work_id, max_retries=3)
        assert retried.status == WorkStatus.PENDING
        issue_after_retry = await service.get_issue(issue.issue_id)
        assert issue_after_retry.status == IssueStatus.IN_PROGRESS

        # Simulate re-assignment: PENDING → ASSIGNED → IN_PROGRESS
        await service.assign_work(
            work_id=work.work_id,
            compute_id="compute-002",
            skills=["code-writer"]
        )
        await service.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-002")

        # Second failure — should succeed without FAILED→FAILED warning
        failed2 = await service.fail_work_and_update_issue(work.work_id, "SSH error 2")
        assert failed2 is not None
        issue_after_fail2 = await service.get_issue(issue.issue_id)
        assert issue_after_fail2.status == IssueStatus.FAILED
