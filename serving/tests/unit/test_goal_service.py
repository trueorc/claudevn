"""Tests for GoalService."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from services.goal_service import (
    GoalService,
    get_goal_service,
    set_goal_service
)
from models.work_map import (
    Goal, GoalStatus, GoalCreateRequest,
    Issue, IssueStatus, IssueArea
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
    return GoalService(redis_client=None)


@pytest.fixture
def service_with_redis(mock_redis):
    """Create service with mocked Redis."""
    return GoalService(redis_client=mock_redis)


@pytest.fixture
def sample_goal_request():
    """Create a sample goal creation request."""
    return GoalCreateRequest(
        title="Test Goal",
        description="Test goal description",
        priority="P1"
    )


class TestGoalServiceInit:
    """Test GoalService initialization."""

    def test_init_without_redis(self):
        """Test initialization without Redis client."""
        service = GoalService()
        assert service._redis is None
        assert service._goals == {}
        assert service._initialized is False

    def test_init_with_redis(self, mock_redis):
        """Test initialization with Redis client."""
        service = GoalService(redis_client=mock_redis)
        assert service._redis is mock_redis
        assert service._goals == {}

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


class TestGoalCRUD:
    """Test Goal CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_goal(self, service, sample_goal_request):
        """Test creating a goal."""
        goal = await service.create_goal(sample_goal_request)

        assert goal.goal_id.startswith("goal_")
        assert goal.title == "Test Goal"
        assert goal.description == "Test goal description"
        assert goal.status == GoalStatus.PLANNING

    @pytest.mark.asyncio
    async def test_get_goal(self, service, sample_goal_request):
        """Test getting a goal by ID."""
        created = await service.create_goal(sample_goal_request)
        goal = await service.get_goal(created.goal_id)

        assert goal is not None
        assert goal.goal_id == created.goal_id
        assert goal.title == "Test Goal"

    @pytest.mark.asyncio
    async def test_get_nonexistent_goal(self, service):
        """Test getting nonexistent goal returns None."""
        goal = await service.get_goal("nonexistent-goal-id")
        assert goal is None

    @pytest.mark.asyncio
    async def test_list_goals(self, service):
        """Test listing goals."""
        for i in range(3):
            await service.create_goal(GoalCreateRequest(
                title=f"Goal {i}",
                description=f"Description {i}"
            ))

        result = await service.list_goals()

        assert result.total == 3
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_list_goals_by_status(self, service):
        """Test listing goals filtered by status."""
        goal = await service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test"
        ))

        # Planning by default
        result = await service.list_goals(status=GoalStatus.PLANNING)
        assert len(result.items) == 1

        result = await service.list_goals(status=GoalStatus.IN_PROGRESS)
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_update_goal_status(self, service, sample_goal_request):
        """Test updating goal status."""
        goal = await service.create_goal(sample_goal_request)

        updated = await service.update_goal_status(goal.goal_id, GoalStatus.IN_PROGRESS)

        assert updated is not None
        assert updated.status == GoalStatus.IN_PROGRESS
        assert updated.updated_at > goal.created_at

    @pytest.mark.asyncio
    async def test_update_goal_status_nonexistent(self, service):
        """Test updating nonexistent goal returns None."""
        result = await service.update_goal_status("nonexistent", GoalStatus.IN_PROGRESS)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_goal_soft(self, service, sample_goal_request):
        """Test soft deleting a goal (default behavior)."""
        goal = await service.create_goal(sample_goal_request)

        result = await service.delete_goal(goal.goal_id)

        assert result is not None
        assert result.deleted is True
        assert result.goal_id == goal.goal_id
        assert result.deleted_at is not None

        # Goal should not be visible in regular get
        assert await service.get_goal(goal.goal_id) is None

        # Goal should be visible with include_deleted=True
        deleted_goal = await service.get_goal(goal.goal_id, include_deleted=True)
        assert deleted_goal is not None
        assert deleted_goal.deleted_at is not None

    @pytest.mark.asyncio
    async def test_delete_goal_hard(self, service, sample_goal_request):
        """Test hard deleting a goal."""
        goal = await service.create_goal(sample_goal_request)

        result = await service.delete_goal(goal.goal_id, hard=True)

        assert result is not None
        assert result.deleted is True
        assert result.goal_id == goal.goal_id
        assert result.deleted_at is None  # Hard delete doesn't set deleted_at

        # Goal should be completely gone
        assert await service.get_goal(goal.goal_id) is None
        assert await service.get_goal(goal.goal_id, include_deleted=True) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_goal(self, service):
        """Test deleting nonexistent goal returns None."""
        result = await service.delete_goal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_goal(self, service, sample_goal_request):
        """Test restoring a soft-deleted goal."""
        goal = await service.create_goal(sample_goal_request)

        # Soft delete the goal
        await service.delete_goal(goal.goal_id)
        assert await service.get_goal(goal.goal_id) is None

        # Restore the goal
        restored = await service.restore_goal(goal.goal_id)

        assert restored is not None
        assert restored.deleted_at is None
        assert restored.goal_id == goal.goal_id

        # Goal should be visible again
        assert await service.get_goal(goal.goal_id) is not None

    @pytest.mark.asyncio
    async def test_restore_nonexistent_goal(self, service):
        """Test restoring nonexistent goal returns None."""
        result = await service.restore_goal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_non_deleted_goal(self, service, sample_goal_request):
        """Test restoring a goal that isn't deleted returns None."""
        goal = await service.create_goal(sample_goal_request)

        result = await service.restore_goal(goal.goal_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_goals_excludes_deleted(self, service):
        """Test that list_goals excludes soft-deleted goals by default."""
        # Create 3 goals
        for i in range(3):
            await service.create_goal(GoalCreateRequest(
                title=f"Goal {i}",
                description=f"Description {i}"
            ))

        # Verify 3 goals
        result = await service.list_goals()
        assert result.total == 3

        # Soft delete one
        goals = result.items
        await service.delete_goal(goals[0].goal_id)

        # Should now have 2 visible
        result = await service.list_goals()
        assert result.total == 2
        assert len(result.items) == 2

        # Should have 3 with include_deleted
        result = await service.list_goals(include_deleted=True)
        assert len(result.items) == 3


class TestGoalIssueRelationship:
    """Test goal-issue relationship management."""

    @pytest.mark.asyncio
    async def test_get_goal_issues(self, service, sample_goal_request):
        """Test getting issues for a goal."""
        goal = await service.create_goal(sample_goal_request)

        # Create mock issues
        issue1 = Issue(
            issue_id="issue_001",
            title="Issue 1",
            description="Test",
            area=IssueArea.API,
            goal_id=goal.goal_id
        )
        issue2 = Issue(
            issue_id="issue_002",
            title="Issue 2",
            description="Test",
            area=IssueArea.API,
            goal_id=goal.goal_id
        )
        issue3 = Issue(
            issue_id="issue_003",
            title="Issue 3",
            description="Test",
            area=IssueArea.API,
            goal_id="other_goal"
        )

        # Set issues reference
        service.set_issues_reference({
            "issue_001": issue1,
            "issue_002": issue2,
            "issue_003": issue3
        })

        issues = await service.get_goal_issues(goal.goal_id)

        assert len(issues) == 2
        assert all(i.goal_id == goal.goal_id for i in issues)

    @pytest.mark.asyncio
    async def test_update_goal_issues(self, service, sample_goal_request):
        """Test updating goal's issue list."""
        goal = await service.create_goal(sample_goal_request)

        issue_ids = ["issue_001", "issue_002", "issue_003"]
        updated = await service.update_goal_issues(goal.goal_id, issue_ids)

        assert updated is not None
        assert updated.issue_ids == issue_ids
        assert updated.status == GoalStatus.IN_PROGRESS  # Auto-transitions

    @pytest.mark.asyncio
    async def test_update_goal_issues_nonexistent(self, service):
        """Test updating issues for nonexistent goal returns None."""
        result = await service.update_goal_issues("nonexistent", [])
        assert result is None


class TestGoalCompletion:
    """Test goal completion checking."""

    @pytest.mark.asyncio
    async def test_check_goal_completion_all_done(self, service, sample_goal_request):
        """Test goal completes when all issues are done."""
        goal = await service.create_goal(sample_goal_request)

        # Create mock done issues
        issue1 = Issue(
            issue_id="issue_001",
            title="Issue 1",
            description="Test",
            area=IssueArea.API,
            goal_id=goal.goal_id,
            status=IssueStatus.DONE
        )
        issue2 = Issue(
            issue_id="issue_002",
            title="Issue 2",
            description="Test",
            area=IssueArea.API,
            goal_id=goal.goal_id,
            status=IssueStatus.DONE
        )

        service.set_issues_reference({
            "issue_001": issue1,
            "issue_002": issue2
        })

        await service.check_goal_completion(goal.goal_id)

        updated = await service.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.DONE

    @pytest.mark.asyncio
    async def test_check_goal_completion_not_all_done(self, service, sample_goal_request):
        """Test goal does not complete when issues remain."""
        goal = await service.create_goal(sample_goal_request)

        issue1 = Issue(
            issue_id="issue_001",
            title="Issue 1",
            description="Test",
            area=IssueArea.API,
            goal_id=goal.goal_id,
            status=IssueStatus.DONE
        )
        issue2 = Issue(
            issue_id="issue_002",
            title="Issue 2",
            description="Test",
            area=IssueArea.API,
            goal_id=goal.goal_id,
            status=IssueStatus.IN_PROGRESS
        )

        service.set_issues_reference({
            "issue_001": issue1,
            "issue_002": issue2
        })

        await service.check_goal_completion(goal.goal_id)

        updated = await service.get_goal(goal.goal_id)
        assert updated.status == GoalStatus.PLANNING


class TestGoalArchive:
    """Test goal archive/unarchive operations."""

    @pytest.mark.asyncio
    async def test_archive_goal(self, service, sample_goal_request):
        """Test archiving a goal."""
        goal = await service.create_goal(sample_goal_request)

        archived = await service.archive_goal(goal.goal_id)

        assert archived is not None
        assert archived.archived is True
        assert archived.archived_at is not None
        assert archived.goal_id == goal.goal_id

    @pytest.mark.asyncio
    async def test_archive_goal_already_archived(self, service, sample_goal_request):
        """Test archiving an already archived goal returns it unchanged."""
        goal = await service.create_goal(sample_goal_request)

        # Archive first time
        archived1 = await service.archive_goal(goal.goal_id)
        original_archived_at = archived1.archived_at

        # Archive second time
        archived2 = await service.archive_goal(goal.goal_id)

        assert archived2 is not None
        assert archived2.archived is True
        # Should keep original archived_at
        assert archived2.archived_at == original_archived_at

    @pytest.mark.asyncio
    async def test_archive_nonexistent_goal(self, service):
        """Test archiving nonexistent goal returns None."""
        result = await service.archive_goal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_archive_deleted_goal(self, service, sample_goal_request):
        """Test archiving a deleted goal returns None."""
        goal = await service.create_goal(sample_goal_request)

        # Soft delete the goal
        await service.delete_goal(goal.goal_id)

        # Try to archive
        result = await service.archive_goal(goal.goal_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_unarchive_goal(self, service, sample_goal_request):
        """Test unarchiving a goal."""
        goal = await service.create_goal(sample_goal_request)

        # Archive first
        await service.archive_goal(goal.goal_id)

        # Unarchive
        unarchived = await service.unarchive_goal(goal.goal_id)

        assert unarchived is not None
        assert unarchived.archived is False
        assert unarchived.archived_at is None

    @pytest.mark.asyncio
    async def test_unarchive_non_archived_goal(self, service, sample_goal_request):
        """Test unarchiving a non-archived goal returns it unchanged."""
        goal = await service.create_goal(sample_goal_request)

        result = await service.unarchive_goal(goal.goal_id)

        assert result is not None
        assert result.archived is False

    @pytest.mark.asyncio
    async def test_unarchive_nonexistent_goal(self, service):
        """Test unarchiving nonexistent goal returns None."""
        result = await service.unarchive_goal("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_goals_excludes_archived(self, service):
        """Test that list_goals excludes archived goals by default."""
        # Create 3 goals
        goals = []
        for i in range(3):
            goal = await service.create_goal(GoalCreateRequest(
                title=f"Goal {i}",
                description=f"Description {i}"
            ))
            goals.append(goal)

        # Verify 3 goals
        result = await service.list_goals()
        assert result.total == 3

        # Archive one
        await service.archive_goal(goals[0].goal_id)

        # Should now have 2 visible
        result = await service.list_goals()
        assert result.total == 2
        assert len(result.items) == 2

        # Should have 3 with include_archived
        result = await service.list_goals(include_archived=True)
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_get_goal_returns_archived(self, service, sample_goal_request):
        """Test that get_goal returns archived goals (for direct access)."""
        goal = await service.create_goal(sample_goal_request)

        # Archive
        await service.archive_goal(goal.goal_id)

        # get_goal should still return the archived goal
        retrieved = await service.get_goal(goal.goal_id)
        assert retrieved is not None
        assert retrieved.archived is True

    @pytest.mark.asyncio
    async def test_archived_goal_persists_to_redis(self, service_with_redis, mock_redis, sample_goal_request):
        """Test that archived state is saved to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)

        # Archive
        await service_with_redis.archive_goal(goal.goal_id)

        # Verify Redis was called with archived field
        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('archived') == 'true'
        assert 'archived_at' in mapping


class TestGoalServiceGlobals:
    """Test global instance management."""

    def test_set_get_service(self):
        """Test setting and getting global service."""
        service = GoalService()
        set_goal_service(service)

        retrieved = get_goal_service()
        assert retrieved is service

    def test_get_service_not_initialized(self):
        """Test getting service when not initialized raises error."""
        set_goal_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_goal_service()


class TestGoalProjectAssociation:
    """Test goal-project association (#398)."""

    @pytest.mark.asyncio
    async def test_create_goal_with_project_id(self, service):
        """Test creating a goal with a project_id."""
        request = GoalCreateRequest(
            title="Project Goal",
            description="A goal associated with a project",
            priority="P1",
            project_id="project_123"
        )
        goal = await service.create_goal(request)

        assert goal.goal_id.startswith("goal_")
        assert goal.title == "Project Goal"
        assert goal.project_id == "project_123"

    @pytest.mark.asyncio
    async def test_create_goal_without_project_id(self, service, sample_goal_request):
        """Test creating a goal without a project_id (backwards compatible)."""
        goal = await service.create_goal(sample_goal_request)

        assert goal.goal_id.startswith("goal_")
        assert goal.project_id is None

    @pytest.mark.asyncio
    async def test_list_goals_filter_by_project(self, service):
        """Test listing goals filtered by project_id."""
        # Create goals for different projects (unique descriptions to avoid dedup)
        for i in range(2):
            await service.create_goal(GoalCreateRequest(
                title=f"Project A Goal {i}",
                description=f"Project A description {i}",
                project_id="project_a"
            ))
        for i in range(3):
            await service.create_goal(GoalCreateRequest(
                title=f"Project B Goal {i}",
                description=f"Project B description {i}",
                project_id="project_b"
            ))
        # Create a goal without project
        await service.create_goal(GoalCreateRequest(
            title="No Project Goal",
            description="No project description"
        ))

        # Filter by project_a
        result = await service.list_goals(project_id="project_a")
        assert result.total == 2
        assert len(result.items) == 2
        assert all(g.project_id == "project_a" for g in result.items)

        # Filter by project_b
        result = await service.list_goals(project_id="project_b")
        assert result.total == 3
        assert len(result.items) == 3
        assert all(g.project_id == "project_b" for g in result.items)

    @pytest.mark.asyncio
    async def test_list_goals_all_projects(self, service):
        """Test listing all goals when no project filter is specified."""
        await service.create_goal(GoalCreateRequest(
            title="Project A Goal",
            description="Project A all-projects test",
            project_id="project_a"
        ))
        await service.create_goal(GoalCreateRequest(
            title="Project B Goal",
            description="Project B all-projects test",
            project_id="project_b"
        ))
        await service.create_goal(GoalCreateRequest(
            title="No Project Goal",
            description="No project all-projects test"
        ))

        # No filter - return all
        result = await service.list_goals()
        assert result.total == 3
        assert len(result.items) == 3

    @pytest.mark.asyncio
    async def test_list_goals_project_filter_with_status(self, service):
        """Test filtering by both project_id and status."""
        # Create goals with different statuses (unique descriptions to avoid dedup)
        goal1 = await service.create_goal(GoalCreateRequest(
            title="Goal 1",
            description="Status filter goal 1",
            project_id="project_a"
        ))
        goal2 = await service.create_goal(GoalCreateRequest(
            title="Goal 2",
            description="Status filter goal 2",
            project_id="project_a"
        ))
        await service.create_goal(GoalCreateRequest(
            title="Goal 3",
            description="Status filter goal 3",
            project_id="project_b"
        ))

        # Update one goal to in_progress
        await service.update_goal_status(goal1.goal_id, GoalStatus.IN_PROGRESS)

        # Filter by project_a and planning status
        result = await service.list_goals(
            project_id="project_a",
            status=GoalStatus.PLANNING
        )
        assert len(result.items) == 1
        assert result.items[0].goal_id == goal2.goal_id

    @pytest.mark.asyncio
    async def test_project_id_persists_to_redis(self, service_with_redis, mock_redis):
        """Test that project_id is saved to Redis."""
        request = GoalCreateRequest(
            title="Project Goal",
            description="Test",
            project_id="project_xyz"
        )
        await service_with_redis.create_goal(request)

        # Verify Redis was called with project_id field
        hset_calls = mock_redis._redis.hset.call_args_list
        assert len(hset_calls) > 0
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('project_id') == 'project_xyz'

    @pytest.mark.asyncio
    async def test_project_id_empty_persists_as_empty_string(self, service_with_redis, mock_redis):
        """Test that None project_id is saved as empty string in Redis."""
        request = GoalCreateRequest(
            title="No Project Goal",
            description="Test"
        )
        await service_with_redis.create_goal(request)

        # Verify Redis was called with empty project_id
        hset_calls = mock_redis._redis.hset.call_args_list
        assert len(hset_calls) > 0
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('project_id') == ''


class TestGoalDecompositionId:
    """Test decomposition_id tracking on goals (#414)."""

    @pytest.mark.asyncio
    async def test_goal_created_without_decomposition_id(self, service, sample_goal_request):
        """Test that new goals have no decomposition_id by default."""
        goal = await service.create_goal(sample_goal_request)
        assert goal.decomposition_id is None

    @pytest.mark.asyncio
    async def test_update_goal_decomposition_id(self, service, sample_goal_request):
        """Test updating a goal with a decomposition_id."""
        goal = await service.create_goal(sample_goal_request)

        updated = await service.update_goal_decomposition_id(
            goal.goal_id, "decomp-abc123"
        )

        assert updated is not None
        assert updated.decomposition_id == "decomp-abc123"
        assert updated.updated_at > goal.created_at

    @pytest.mark.asyncio
    async def test_update_decomposition_id_nonexistent_goal(self, service):
        """Test updating decomposition_id for nonexistent goal returns None."""
        result = await service.update_goal_decomposition_id(
            "nonexistent", "decomp-abc123"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_decomposition_id_persists_after_get(self, service, sample_goal_request):
        """Test that decomposition_id persists when retrieving the goal."""
        goal = await service.create_goal(sample_goal_request)
        await service.update_goal_decomposition_id(goal.goal_id, "decomp-xyz789")

        retrieved = await service.get_goal(goal.goal_id)
        assert retrieved.decomposition_id == "decomp-xyz789"

    @pytest.mark.asyncio
    async def test_decomposition_id_persists_to_redis(self, service_with_redis, mock_redis, sample_goal_request):
        """Test that decomposition_id is saved to Redis."""
        goal = await service_with_redis.create_goal(sample_goal_request)
        await service_with_redis.update_goal_decomposition_id(
            goal.goal_id, "decomp-redis-test"
        )

        # Verify Redis was called with decomposition_id field
        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('decomposition_id') == 'decomp-redis-test'

    @pytest.mark.asyncio
    async def test_decomposition_id_none_persists_as_empty_string(self, service_with_redis, mock_redis, sample_goal_request):
        """Test that None decomposition_id is saved as empty string in Redis."""
        await service_with_redis.create_goal(sample_goal_request)

        hset_calls = mock_redis._redis.hset.call_args_list
        last_call = hset_calls[-1]
        mapping = last_call.kwargs.get('mapping', last_call.args[1] if len(last_call.args) > 1 else {})
        assert mapping.get('decomposition_id') == ''

    @pytest.mark.asyncio
    async def test_decomposition_id_can_be_overwritten(self, service, sample_goal_request):
        """Test that decomposition_id can be updated multiple times."""
        goal = await service.create_goal(sample_goal_request)

        await service.update_goal_decomposition_id(goal.goal_id, "decomp-first")
        updated = await service.update_goal_decomposition_id(goal.goal_id, "decomp-second")

        assert updated.decomposition_id == "decomp-second"
