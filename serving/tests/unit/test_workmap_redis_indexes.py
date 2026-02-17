"""Tests for WorkMap Redis indexes functionality."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from models.work_map import (
    WorkItem, WorkStatus, WorkPriority, WorkCreateRequest
)
from services.work_map_service import WorkMapService


@pytest.fixture
def mock_redis():
    """Mock Redis client with all needed async methods."""
    redis = MagicMock()
    redis._redis = MagicMock()
    redis._redis.hset = AsyncMock()
    redis._redis.hgetall = AsyncMock(return_value={})
    redis._redis.sadd = AsyncMock()
    redis._redis.srem = AsyncMock()
    redis._redis.smembers = AsyncMock(return_value=set())
    redis._redis.zadd = AsyncMock()
    redis._redis.zrem = AsyncMock()
    redis._redis.zrange = AsyncMock(return_value=[])
    redis._redis.set = AsyncMock()
    redis._redis.get = AsyncMock(return_value=None)
    redis._redis.delete = AsyncMock()
    redis._redis.scan = AsyncMock(return_value=(0, []))
    redis._prefix = "claudevn:"
    redis._key = lambda k: f"claudevn:{k}"
    return redis


@pytest.fixture
def service():
    """Service without Redis for in-memory testing."""
    return WorkMapService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """Service with mocked Redis."""
    return WorkMapService(redis_client=mock_redis)


# =============================================================================
# Test Dependency Indexes
# =============================================================================


class TestDependencyIndexes:
    """Tests for dependency tracking indexes."""

    @pytest.mark.asyncio
    async def test_save_creates_dependency_indexes(self, service_with_redis, mock_redis):
        """Test that saving work creates dependency indexes."""
        # Create a dependency work item first
        dep_work = await service_with_redis.create_work(WorkCreateRequest(
            title="Dependency work",
            description="This is a dependency",
            project_id="project-1"
        ))

        # Create work that depends on it
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Dependent work",
            description="This depends on another",
            depends_on=[dep_work.work_id],
            project_id="project-1"
        ))

        # Verify dependency index calls
        sadd_calls = [call for call in mock_redis._redis.sadd.call_args_list]

        # Should have called sadd for depends_on index
        depends_on_call = any(
            f"workmap:work:depends_on:{work.work_id}" in str(call)
            for call in sadd_calls
        )
        assert depends_on_call, "Should create depends_on index"

        # Should have called sadd for blocks index
        blocks_call = any(
            f"workmap:work:blocks:{dep_work.work_id}" in str(call)
            for call in sadd_calls
        )
        assert blocks_call, "Should create blocks index"

    @pytest.mark.asyncio
    async def test_delete_removes_dependency_indexes(self, service_with_redis, mock_redis):
        """Test that deleting work removes dependency indexes."""
        # Create work items
        dep_work = await service_with_redis.create_work(WorkCreateRequest(
            title="Dependency",
            description="Dep",
            project_id="project-1"
        ))

        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Dependent",
            description="Depends",
            depends_on=[dep_work.work_id],
            project_id="project-1"
        ))

        # Reset mock calls to check delete operations
        mock_redis._redis.srem.reset_mock()
        mock_redis._redis.delete.reset_mock()

        # Delete the dependent work
        await service_with_redis.delete_work(work.work_id)

        # Should have removed from dependency indexes
        srem_calls = [str(call) for call in mock_redis._redis.srem.call_args_list]
        delete_calls = [str(call) for call in mock_redis._redis.delete.call_args_list]

        # Check that depends_on index was cleaned up
        assert any("depends_on" in call for call in srem_calls + delete_calls)


# =============================================================================
# Test Skill Indexes
# =============================================================================


class TestSkillIndexes:
    """Tests for skill-based indexes."""

    @pytest.mark.asyncio
    async def test_save_creates_skill_index(self, service_with_redis, mock_redis):
        """Test that saving work creates skill index entries."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Skilled work",
            description="Work requiring specific skills",
            required_skills=["python", "testing"],
            project_id="project-1"
        ))

        # Verify skill index calls
        sadd_calls = [str(call) for call in mock_redis._redis.sadd.call_args_list]

        assert any("workmap:work:skill:python" in call for call in sadd_calls)
        assert any("workmap:work:skill:testing" in call for call in sadd_calls)

    @pytest.mark.asyncio
    async def test_delete_removes_skill_index(self, service_with_redis, mock_redis):
        """Test that deleting work removes skill index entries."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Skilled work",
            description="Work requiring skills",
            required_skills=["python"],
            project_id="project-1"
        ))

        mock_redis._redis.srem.reset_mock()
        await service_with_redis.delete_work(work.work_id)

        srem_calls = [str(call) for call in mock_redis._redis.srem.call_args_list]
        assert any("workmap:work:skill:python" in call for call in srem_calls)

    @pytest.mark.asyncio
    async def test_get_work_by_skill_in_memory(self, service):
        """Test getting work by skill without Redis."""
        # Create work items with different skills
        work1 = await service.create_work(WorkCreateRequest(
            title="Python work",
            description="Needs Python",
            required_skills=["python"],
            project_id="project-1"
        ))
        work2 = await service.create_work(WorkCreateRequest(
            title="Testing work",
            description="Needs testing",
            required_skills=["testing"],
            project_id="project-1"
        ))
        work3 = await service.create_work(WorkCreateRequest(
            title="Both work",
            description="Needs both",
            required_skills=["python", "testing"],
            project_id="project-1"
        ))

        # Get work by Python skill
        python_work = await service.get_work_by_skill("python")
        assert len(python_work) == 2
        python_ids = [w.work_id for w in python_work]
        assert work1.work_id in python_ids
        assert work3.work_id in python_ids

        # Get work by testing skill
        testing_work = await service.get_work_by_skill("testing")
        assert len(testing_work) == 2
        testing_ids = [w.work_id for w in testing_work]
        assert work2.work_id in testing_ids
        assert work3.work_id in testing_ids


# =============================================================================
# Test Priority Queue
# =============================================================================


class TestPriorityQueue:
    """Tests for priority queue functionality."""

    @pytest.mark.asyncio
    async def test_pending_work_added_to_priority_queue(self, service_with_redis, mock_redis):
        """Test that pending work is added to priority queue."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Queued work",
            description="Should be in queue",
            priority=WorkPriority.HIGH,
            project_id="project-1"
        ))

        zadd_calls = [str(call) for call in mock_redis._redis.zadd.call_args_list]
        assert any("workmap:work:pending:queue" in call for call in zadd_calls)

    @pytest.mark.asyncio
    async def test_assigned_work_removed_from_priority_queue(self, service_with_redis, mock_redis):
        """Test that assigned work is removed from priority queue."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Work to assign",
            description="Will be assigned",
            project_id="project-1"
        ))

        mock_redis._redis.zrem.reset_mock()
        await service_with_redis.assign_work(work.work_id, "compute-1", ["skill-1"])

        zrem_calls = [str(call) for call in mock_redis._redis.zrem.call_args_list]
        assert any("workmap:work:pending:queue" in call for call in zrem_calls)

    @pytest.mark.asyncio
    async def test_get_pending_queue_in_memory(self, service):
        """Test getting pending queue without Redis."""
        # Create work items with different priorities
        low = await service.create_work(WorkCreateRequest(
            title="Low priority",
            description="Low",
            priority=WorkPriority.LOW,
            project_id="project-1"
        ))
        high = await service.create_work(WorkCreateRequest(
            title="High priority",
            description="High",
            priority=WorkPriority.HIGH,
            project_id="project-1"
        ))
        critical = await service.create_work(WorkCreateRequest(
            title="Critical priority",
            description="Critical",
            priority=WorkPriority.CRITICAL,
            project_id="project-1"
        ))

        queue = await service.get_pending_queue()
        assert len(queue) == 3

        # Should be ordered: critical, high, normal, low
        assert queue[0].work_id == critical.work_id
        assert queue[1].work_id == high.work_id
        assert queue[2].work_id == low.work_id

    @pytest.mark.asyncio
    async def test_get_pending_queue_respects_limit(self, service):
        """Test that pending queue respects limit."""
        for i in range(5):
            await service.create_work(WorkCreateRequest(
                title=f"Work {i}",
                description=f"Work item {i}",
                project_id="project-1"
            ))

        queue = await service.get_pending_queue(limit=3)
        assert len(queue) == 3


# =============================================================================
# Test Compute Assignment Tracking
# =============================================================================


class TestComputeAssignmentTracking:
    """Tests for compute current assignment tracking."""

    @pytest.mark.asyncio
    async def test_assign_sets_compute_current(self, service_with_redis, mock_redis):
        """Test that assigning work sets compute's current assignment."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Work to track",
            description="Track compute assignment",
            project_id="project-1"
        ))

        mock_redis._redis.set.reset_mock()
        await service_with_redis.assign_work(work.work_id, "compute-1", ["skill-1"])

        set_calls = [str(call) for call in mock_redis._redis.set.call_args_list]
        assert any("workmap:compute:compute-1:current" in call for call in set_calls)

    @pytest.mark.asyncio
    async def test_unassign_clears_compute_current(self, service_with_redis, mock_redis):
        """Test that unassigning work clears compute's current assignment."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Work to unassign",
            description="Will be unassigned",
            project_id="project-1"
        ))
        await service_with_redis.assign_work(work.work_id, "compute-1", ["skill-1"])

        mock_redis._redis.delete.reset_mock()
        await service_with_redis.unassign_work(work.work_id)

        delete_calls = [str(call) for call in mock_redis._redis.delete.call_args_list]
        assert any("workmap:compute:compute-1:current" in call for call in delete_calls)

    @pytest.mark.asyncio
    async def test_complete_clears_compute_current(self, service_with_redis, mock_redis):
        """Test that completing work clears compute's current assignment."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Work to complete",
            description="Will be completed",
            project_id="project-1"
        ))
        await service_with_redis.assign_work(work.work_id, "compute-1", ["skill-1"])
        await service_with_redis.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-1")

        mock_redis._redis.delete.reset_mock()
        await service_with_redis.complete_work(work.work_id, {"result": "done"}, "compute-1")

        delete_calls = [str(call) for call in mock_redis._redis.delete.call_args_list]
        assert any("workmap:compute:compute-1:current" in call for call in delete_calls)

    @pytest.mark.asyncio
    async def test_get_compute_current_work_in_memory(self, service):
        """Test getting compute's current work without Redis."""
        work = await service.create_work(WorkCreateRequest(
            title="Assigned work",
            description="Currently assigned",
            project_id="project-1"
        ))
        await service.assign_work(work.work_id, "compute-1", ["skill-1"])

        current = await service.get_compute_current_work("compute-1")
        assert current == work.work_id

        # After unassign, should return None
        await service.unassign_work(work.work_id)
        current = await service.get_compute_current_work("compute-1")
        assert current is None


# =============================================================================
# Test Blocker Query Methods
# =============================================================================


class TestBlockerQueries:
    """Tests for work blocker query methods."""

    @pytest.mark.asyncio
    async def test_get_work_blockers_in_memory(self, service):
        """Test getting what blocks a work item."""
        dep1 = await service.create_work(WorkCreateRequest(
            title="Dep 1",
            description="First dependency",
            project_id="project-1"
        ))
        dep2 = await service.create_work(WorkCreateRequest(
            title="Dep 2",
            description="Second dependency",
            project_id="project-1"
        ))
        work = await service.create_work(WorkCreateRequest(
            title="Blocked work",
            description="Has dependencies",
            depends_on=[dep1.work_id, dep2.work_id],
            project_id="project-1"
        ))

        blockers = await service.get_work_blockers(work.work_id)
        assert len(blockers) == 2
        assert dep1.work_id in blockers
        assert dep2.work_id in blockers

    @pytest.mark.asyncio
    async def test_get_blocked_by_work_in_memory(self, service):
        """Test getting what a work item blocks."""
        dep = await service.create_work(WorkCreateRequest(
            title="Dependency",
            description="Blocks other work",
            project_id="project-1"
        ))
        blocked1 = await service.create_work(WorkCreateRequest(
            title="Blocked 1",
            description="Blocked by dep",
            depends_on=[dep.work_id],
            project_id="project-1"
        ))
        blocked2 = await service.create_work(WorkCreateRequest(
            title="Blocked 2",
            description="Also blocked by dep",
            depends_on=[dep.work_id],
            project_id="project-1"
        ))

        blocked = await service.get_blocked_by_work(dep.work_id)
        assert len(blocked) == 2
        assert blocked1.work_id in blocked
        assert blocked2.work_id in blocked


# =============================================================================
# Test Timeout Clears Compute Assignment
# =============================================================================


class TestTimeoutClearsComputeAssignment:
    """Tests for timeout handling compute assignment cleanup."""

    @pytest.mark.asyncio
    async def test_timeout_retry_clears_compute(self, service_with_redis, mock_redis):
        """Test that timeout with retry clears compute assignment."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Work that times out",
            description="Will timeout and retry",
            project_id="project-1"
        ))
        await service_with_redis.assign_work(work.work_id, "compute-1", ["skill-1"])
        await service_with_redis.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-1")

        mock_redis._redis.delete.reset_mock()
        await service_with_redis.mark_work_timed_out(work.work_id, max_retries=3)

        delete_calls = [str(call) for call in mock_redis._redis.delete.call_args_list]
        assert any("workmap:compute:compute-1:current" in call for call in delete_calls)

    @pytest.mark.asyncio
    async def test_timeout_fail_clears_compute(self, service_with_redis, mock_redis):
        """Test that timeout with failure clears compute assignment."""
        work = await service_with_redis.create_work(WorkCreateRequest(
            title="Work that fails",
            description="Will timeout and fail",
            project_id="project-1"
        ))
        await service_with_redis.assign_work(work.work_id, "compute-1", ["skill-1"])
        await service_with_redis.update_status(work.work_id, WorkStatus.IN_PROGRESS, "compute-1")

        # Reach max retries
        service_with_redis._work_items[work.work_id].retry_count = 2

        mock_redis._redis.delete.reset_mock()
        await service_with_redis.mark_work_timed_out(work.work_id, max_retries=3)

        delete_calls = [str(call) for call in mock_redis._redis.delete.call_args_list]
        assert any("workmap:compute:compute-1:current" in call for call in delete_calls)
