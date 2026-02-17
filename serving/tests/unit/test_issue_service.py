"""Tests for IssueService - Git-backed issue and goal storage."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import yaml

from models.issue import (
    Issue,
    IssueType,
    IssueArea,
    IssuePriority,
    IssueStatus,
    IssueResult,
    IssueCreateRequest,
    IssueUpdateRequest,
    Goal,
    GoalStatus,
    GoalCreateRequest,
    GoalUpdateRequest,
)
from services.issue_service import IssueService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock RedisClient."""
    redis = MagicMock()
    redis._redis = MagicMock()

    # Create counter for incr to return incrementing values
    counter = {"issue": 0, "goal": 0}

    # Storage for sets (to track dependencies/blocks)
    sets_storage = {}

    def incr_side_effect(key):
        if "issue_counter" in key:
            counter["issue"] += 1
            return counter["issue"]
        elif "goal_counter" in key:
            counter["goal"] += 1
            return counter["goal"]
        return 1

    async def sadd_side_effect(key, *values):
        if key not in sets_storage:
            sets_storage[key] = set()
        for value in values:
            sets_storage[key].add(value)
        return len(values)

    async def srem_side_effect(key, *values):
        if key in sets_storage:
            for value in values:
                sets_storage[key].discard(value)
        return len(values)

    async def smembers_side_effect(key):
        return sets_storage.get(key, set())

    # Mock async methods
    redis._redis.incr = AsyncMock(side_effect=incr_side_effect)
    redis._redis.exists = AsyncMock(return_value=False)
    redis._redis.set = AsyncMock()
    redis._redis.sadd = AsyncMock(side_effect=sadd_side_effect)
    redis._redis.srem = AsyncMock(side_effect=srem_side_effect)
    redis._redis.zadd = AsyncMock()
    redis._redis.zrem = AsyncMock()
    redis._redis.smembers = AsyncMock(side_effect=smembers_side_effect)

    # Mock _key method
    redis._key = lambda k: f"claudevn:{k}"

    return redis


@pytest.fixture
def mock_repo_manager(tmp_path):
    """Mock RepoManager with real filesystem for testing."""
    repo_manager = MagicMock()

    # Mock methods
    repo_manager.repo_exists = MagicMock(return_value=True)
    repo_manager.create_repo = MagicMock()
    repo_manager.add_worktree = MagicMock()
    repo_manager.remove_worktree = MagicMock()

    # Mock _repo_path to return temp directory
    repo_manager._repo_path = MagicMock(return_value=tmp_path / "workmap.git")

    return repo_manager


@pytest.fixture
async def issue_service(mock_redis, mock_repo_manager, tmp_path):
    """Create IssueService with mocked dependencies."""
    service = IssueService(
        redis_client=mock_redis,
        repo_manager=mock_repo_manager
    )

    # Create temporary worktree directory
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir(parents=True, exist_ok=True)
    service._worktree_path = worktree_path
    service._initialized = True

    # Create directory structure
    (worktree_path / "goals").mkdir(parents=True, exist_ok=True)
    (worktree_path / "issues").mkdir(parents=True, exist_ok=True)
    (worktree_path / "archive" / "done").mkdir(parents=True, exist_ok=True)

    # Mock the _git_commit method to avoid actual git operations
    service._git_commit = MagicMock()

    return service


@pytest.fixture
def sample_issue():
    """Create a sample Issue instance."""
    return Issue(
        id="issue-100",
        title="Test Issue",
        description="Test description",
        type=IssueType.FEATURE,
        area=IssueArea.API,
        priority=IssuePriority.P2,
        status=IssueStatus.READY,
        required_skills=["skill-a", "skill-b"],
        depends_on=[],
        blocks=[],
    )


@pytest.fixture
def sample_goal():
    """Create a sample Goal instance."""
    return Goal(
        id="goal-001",
        title="Test Goal",
        description="Test goal description",
        priority=IssuePriority.P1,
        status=GoalStatus.PLANNING,
        created_by="test-user",
    )


# ============================================================================
# Model Tests - Issue
# ============================================================================

class TestIssueModel:
    """Test Issue model serialization."""

    def test_issue_to_yaml(self, sample_issue):
        """Test Issue to_yaml serialization."""
        yaml_str = sample_issue.to_yaml()

        # Parse back to check structure
        data = yaml.safe_load(yaml_str)

        assert data["id"] == "issue-100"
        assert data["title"] == "Test Issue"
        assert data["description"] == "Test description"
        assert data["type"] == "feature"
        assert data["area"] == "api"
        assert data["priority"] == "P2"
        assert data["status"] == "ready"
        assert data["required_skills"] == ["skill-a", "skill-b"]
        assert data["depends_on"] == []
        assert data["blocks"] == []
        assert "created_at" in data

    def test_issue_from_yaml_roundtrip(self, sample_issue):
        """Test Issue to_yaml/from_yaml roundtrip."""
        yaml_str = sample_issue.to_yaml()
        restored = Issue.from_yaml(yaml_str)

        assert restored.id == sample_issue.id
        assert restored.title == sample_issue.title
        assert restored.description == sample_issue.description
        assert restored.type == sample_issue.type
        assert restored.area == sample_issue.area
        assert restored.priority == sample_issue.priority
        assert restored.status == sample_issue.status
        assert restored.required_skills == sample_issue.required_skills
        assert restored.depends_on == sample_issue.depends_on
        assert restored.blocks == sample_issue.blocks

    def test_issue_with_result_serialization(self, sample_issue):
        """Test Issue serialization with result."""
        sample_issue.result = IssueResult(
            branch="feature/issue-100",
            summary="Completed successfully",
            commits=["abc123", "def456"]
        )

        yaml_str = sample_issue.to_yaml()
        restored = Issue.from_yaml(yaml_str)

        assert restored.result is not None
        assert restored.result.branch == "feature/issue-100"
        assert restored.result.summary == "Completed successfully"
        assert restored.result.commits == ["abc123", "def456"]

    def test_issue_with_timestamps_serialization(self):
        """Test Issue serialization with all timestamps."""
        now = datetime.now(timezone.utc)

        issue = Issue(
            id="issue-200",
            title="Test",
            description="Test",
            area=IssueArea.DATABASE,
            created_at=now,
            started_at=now,
            completed_at=now,
        )

        yaml_str = issue.to_yaml()
        restored = Issue.from_yaml(yaml_str)

        assert restored.created_at is not None
        assert restored.started_at is not None
        assert restored.completed_at is not None

    def test_issue_enum_values(self):
        """Test Issue enum values work correctly."""
        issue = Issue(
            id="issue-300",
            title="Test",
            description="Test",
            type=IssueType.BUG,
            area=IssueArea.FRONTEND,
            priority=IssuePriority.P0,
            status=IssueStatus.IN_PROGRESS,
        )

        assert issue.type.value == "bug"
        assert issue.area.value == "frontend"
        assert issue.priority.value == "P0"
        assert issue.status.value == "in_progress"


# ============================================================================
# Model Tests - Goal
# ============================================================================

class TestGoalModel:
    """Test Goal model serialization."""

    def test_goal_to_yaml(self, sample_goal):
        """Test Goal to_yaml serialization."""
        yaml_str = sample_goal.to_yaml()

        # Parse back to check structure
        data = yaml.safe_load(yaml_str)

        assert data["id"] == "goal-001"
        assert data["title"] == "Test Goal"
        assert data["description"] == "Test goal description"
        assert data["priority"] == "P1"
        assert data["status"] == "planning"
        assert data["created_by"] == "test-user"
        assert "created_at" in data
        assert data["issue_ids"] == []

    def test_goal_from_yaml_roundtrip(self, sample_goal):
        """Test Goal to_yaml/from_yaml roundtrip."""
        yaml_str = sample_goal.to_yaml()
        restored = Goal.from_yaml(yaml_str)

        assert restored.id == sample_goal.id
        assert restored.title == sample_goal.title
        assert restored.description == sample_goal.description
        assert restored.priority == sample_goal.priority
        assert restored.status == sample_goal.status
        assert restored.created_by == sample_goal.created_by
        assert restored.issue_ids == sample_goal.issue_ids

    def test_goal_with_issue_ids(self):
        """Test Goal serialization with issue IDs."""
        goal = Goal(
            id="goal-002",
            title="Test",
            description="Test",
            created_by="user",
            issue_ids=["issue-1", "issue-2", "issue-3"],
        )

        yaml_str = goal.to_yaml()
        restored = Goal.from_yaml(yaml_str)

        assert restored.issue_ids == ["issue-1", "issue-2", "issue-3"]

    def test_goal_enum_values(self):
        """Test Goal enum values work correctly."""
        goal = Goal(
            id="goal-003",
            title="Test",
            description="Test",
            created_by="user",
            priority=IssuePriority.P3,
            status=GoalStatus.DONE,
        )

        assert goal.priority.value == "P3"
        assert goal.status.value == "done"


# ============================================================================
# IssueService Tests - Initialization
# ============================================================================

class TestIssueServiceInit:
    """Test IssueService initialization."""

    def test_init_stores_dependencies(self, mock_redis, mock_repo_manager):
        """Test initialization stores dependencies correctly."""
        service = IssueService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager
        )

        assert service._redis is mock_redis
        assert service._repo_manager is mock_repo_manager
        assert service._repo_name == "workmap"
        assert service._initialized is False
        assert service._worktree_path is None

    @pytest.mark.asyncio
    async def test_initialize_creates_repo_if_not_exists(self, mock_redis, mock_repo_manager):
        """Test initialize creates workmap repo if it doesn't exist."""
        mock_repo_manager.repo_exists = MagicMock(return_value=False)

        service = IssueService(
            redis_client=mock_redis,
            repo_manager=mock_repo_manager
        )

        await service.initialize()

        mock_repo_manager.create_repo.assert_called_once_with("workmap", install_hooks=False)
        assert service._initialized is True


# ============================================================================
# IssueService Tests - Issue CRUD
# ============================================================================

class TestIssueServiceIssues:
    """Test Issue CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_issue_generates_id(self, issue_service):
        """Test create_issue generates unique ID."""
        request = IssueCreateRequest(
            title="New Issue",
            description="Description",
            area=IssueArea.API,
        )

        issue = await issue_service.create_issue(request)

        assert issue.id.startswith("issue-")
        assert issue.title == "New Issue"
        assert issue.description == "Description"
        assert issue.area == IssueArea.API

    @pytest.mark.asyncio
    async def test_create_issue_with_no_deps_is_ready(self, issue_service):
        """Test issue with no dependencies starts as READY."""
        request = IssueCreateRequest(
            title="No Dependencies",
            description="Test",
            area=IssueArea.API,
            depends_on=[],
        )

        issue = await issue_service.create_issue(request)

        assert issue.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_create_issue_with_deps_is_backlog(self, issue_service):
        """Test issue with unmet dependencies starts as BACKLOG."""
        request = IssueCreateRequest(
            title="Has Dependencies",
            description="Test",
            area=IssueArea.API,
            depends_on=["issue-999"],  # Non-existent dependency
        )

        issue = await issue_service.create_issue(request)

        assert issue.status == IssueStatus.BACKLOG

    @pytest.mark.asyncio
    async def test_get_issue_returns_none_for_missing(self, issue_service):
        """Test get_issue returns None for non-existent issue."""
        issue = await issue_service.get_issue("nonexistent")

        assert issue is None

    @pytest.mark.asyncio
    async def test_get_issue_returns_created_issue(self, issue_service):
        """Test get_issue retrieves created issue."""
        request = IssueCreateRequest(
            title="Test Issue",
            description="Test",
            area=IssueArea.API,
        )

        created = await issue_service.create_issue(request)
        retrieved = await issue_service.get_issue(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == created.title

    @pytest.mark.asyncio
    async def test_update_issue_fields(self, issue_service):
        """Test updating issue fields."""
        # Create issue
        request = IssueCreateRequest(
            title="Original Title",
            description="Original description",
            area=IssueArea.API,
            priority=IssuePriority.P2,
        )
        created = await issue_service.create_issue(request)

        # Update issue
        update_request = IssueUpdateRequest(
            title="Updated Title",
            priority=IssuePriority.P0,
        )
        updated = await issue_service.update_issue(created.id, update_request)

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.priority == IssuePriority.P0
        assert updated.description == "Original description"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_nonexistent_issue_returns_none(self, issue_service):
        """Test updating non-existent issue returns None."""
        update_request = IssueUpdateRequest(title="New Title")
        result = await issue_service.update_issue("nonexistent", update_request)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_issue_removes_file(self, issue_service):
        """Test deleting issue removes file."""
        # Create issue
        request = IssueCreateRequest(
            title="To Delete",
            description="Test",
            area=IssueArea.API,
        )
        created = await issue_service.create_issue(request)

        # Verify file exists
        issue_path = issue_service._worktree_path / "issues" / f"{created.id}.yaml"
        assert issue_path.exists()

        # Delete issue
        result = await issue_service.delete_issue(created.id)

        assert result is True
        assert not issue_path.exists()

        # Verify can't retrieve
        retrieved = await issue_service.get_issue(created.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_issue_returns_false(self, issue_service):
        """Test deleting non-existent issue returns False."""
        result = await issue_service.delete_issue("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_issues_with_status_filter(self, issue_service):
        """Test listing issues filtered by status."""
        # Create ready issue
        request1 = IssueCreateRequest(
            title="Ready Issue",
            description="Test",
            area=IssueArea.API,
        )
        await issue_service.create_issue(request1)

        # Create backlog issue
        request2 = IssueCreateRequest(
            title="Backlog Issue",
            description="Test",
            area=IssueArea.API,
            depends_on=["issue-999"],
        )
        await issue_service.create_issue(request2)

        # List ready issues only
        result = await issue_service.list_issues(status=IssueStatus.READY)

        assert len(result.items) == 1
        assert result.items[0].title == "Ready Issue"
        assert result.items[0].status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_list_issues_with_priority_filter(self, issue_service):
        """Test listing issues filtered by priority."""
        # Create P0 issue
        request1 = IssueCreateRequest(
            title="P0 Issue",
            description="Test",
            area=IssueArea.API,
            priority=IssuePriority.P0,
        )
        await issue_service.create_issue(request1)

        # Create P2 issue
        request2 = IssueCreateRequest(
            title="P2 Issue",
            description="Test",
            area=IssueArea.API,
            priority=IssuePriority.P2,
        )
        await issue_service.create_issue(request2)

        # List P0 issues only
        result = await issue_service.list_issues(priority=IssuePriority.P0)

        assert len(result.items) == 1
        assert result.items[0].title == "P0 Issue"
        assert result.items[0].priority == IssuePriority.P0

    @pytest.mark.asyncio
    async def test_list_issues_with_goal_filter(self, issue_service):
        """Test listing issues filtered by goal."""
        # Create issues with different goals
        request1 = IssueCreateRequest(
            title="Goal A Issue",
            description="Test",
            area=IssueArea.API,
            goal_id="goal-001",
        )
        await issue_service.create_issue(request1)

        request2 = IssueCreateRequest(
            title="Goal B Issue",
            description="Test",
            area=IssueArea.API,
            goal_id="goal-002",
        )
        await issue_service.create_issue(request2)

        # List goal-001 issues only
        result = await issue_service.list_issues(goal_id="goal-001")

        assert len(result.items) == 1
        assert result.items[0].title == "Goal A Issue"
        assert result.items[0].goal_id == "goal-001"

    @pytest.mark.asyncio
    async def test_list_issues_returns_stats(self, issue_service):
        """Test list_issues returns statistics."""
        # Create various issues
        await issue_service.create_issue(IssueCreateRequest(
            title="Ready P0",
            description="Test",
            area=IssueArea.API,
            priority=IssuePriority.P0,
        ))

        await issue_service.create_issue(IssueCreateRequest(
            title="Ready P1",
            description="Test",
            area=IssueArea.API,
            priority=IssuePriority.P1,
        ))

        await issue_service.create_issue(IssueCreateRequest(
            title="Backlog P0",
            description="Test",
            area=IssueArea.API,
            priority=IssuePriority.P0,
            depends_on=["issue-999"],
        ))

        result = await issue_service.list_issues()

        assert result.total == 3
        assert result.by_status.get("ready", 0) == 2
        assert result.by_status.get("backlog", 0) == 1
        assert result.by_priority.get("P0", 0) == 2
        assert result.by_priority.get("P1", 0) == 1


# ============================================================================
# IssueService Tests - Goal CRUD
# ============================================================================

class TestIssueServiceGoals:
    """Test Goal CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_goal_generates_id(self, issue_service):
        """Test create_goal generates unique ID."""
        request = GoalCreateRequest(
            title="New Goal",
            description="Goal description",
            created_by="test-user",
        )

        goal = await issue_service.create_goal(request)

        assert goal.id.startswith("goal-")
        assert goal.title == "New Goal"
        assert goal.description == "Goal description"
        assert goal.created_by == "test-user"
        assert goal.status == GoalStatus.PLANNING

    @pytest.mark.asyncio
    async def test_get_goal_returns_none_for_missing(self, issue_service):
        """Test get_goal returns None for non-existent goal."""
        goal = await issue_service.get_goal("nonexistent")

        assert goal is None

    @pytest.mark.asyncio
    async def test_get_goal_returns_created_goal(self, issue_service):
        """Test get_goal retrieves created goal."""
        request = GoalCreateRequest(
            title="Test Goal",
            description="Test",
            created_by="user",
        )

        created = await issue_service.create_goal(request)
        retrieved = await issue_service.get_goal(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == created.title

    @pytest.mark.asyncio
    async def test_update_goal_fields(self, issue_service):
        """Test updating goal fields."""
        # Create goal
        request = GoalCreateRequest(
            title="Original Title",
            description="Original description",
            created_by="user",
        )
        created = await issue_service.create_goal(request)

        # Update goal
        update_request = GoalUpdateRequest(
            title="Updated Title",
            status=GoalStatus.IN_PROGRESS,
        )
        updated = await issue_service.update_goal(created.id, update_request)

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.status == GoalStatus.IN_PROGRESS
        assert updated.description == "Original description"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_nonexistent_goal_returns_none(self, issue_service):
        """Test updating non-existent goal returns None."""
        update_request = GoalUpdateRequest(title="New Title")
        result = await issue_service.update_goal("nonexistent", update_request)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_goal(self, issue_service):
        """Test deleting goal removes file."""
        # Create goal
        request = GoalCreateRequest(
            title="To Delete",
            description="Test",
            created_by="user",
        )
        created = await issue_service.create_goal(request)

        # Verify file exists
        goal_path = issue_service._worktree_path / "goals" / f"{created.id}.yaml"
        assert goal_path.exists()

        # Delete goal
        result = await issue_service.delete_goal(created.id)

        assert result is True
        assert not goal_path.exists()

        # Verify can't retrieve
        retrieved = await issue_service.get_goal(created.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_goal_returns_false(self, issue_service):
        """Test deleting non-existent goal returns False."""
        result = await issue_service.delete_goal("nonexistent")

        assert result is False


# ============================================================================
# IssueService Tests - Status Transitions
# ============================================================================

class TestIssueStatusTransitions:
    """Test issue status transitions."""

    @pytest.mark.asyncio
    async def test_complete_issue_sets_done_status(self, issue_service):
        """Test completing issue sets DONE status."""
        # Create issue
        request = IssueCreateRequest(
            title="To Complete",
            description="Test",
            area=IssueArea.API,
        )
        created = await issue_service.create_issue(request)

        # Complete issue
        result = IssueResult(
            branch="feature/issue-100",
            summary="Completed successfully",
            commits=["abc123"],
        )

        updated = await issue_service.complete_issue(created.id, result)

        assert updated is not None
        assert updated.status == IssueStatus.DONE
        assert updated.completed_at is not None
        assert updated.result is not None
        assert updated.result.branch == "feature/issue-100"
        assert updated.result.summary == "Completed successfully"

    @pytest.mark.asyncio
    async def test_complete_nonexistent_issue_returns_none(self, issue_service):
        """Test completing non-existent issue returns None."""
        result = IssueResult(
            branch="feature/test",
            summary="Test",
            commits=[],
        )

        updated = await issue_service.complete_issue("nonexistent", result)

        assert updated is None

    @pytest.mark.asyncio
    async def test_complete_issue_resolves_dependencies(self, issue_service):
        """Test completing issue moves blocked issues to READY."""
        # Create dependency issue
        dep_request = IssueCreateRequest(
            title="Dependency",
            description="Test",
            area=IssueArea.API,
        )
        dep_issue = await issue_service.create_issue(dep_request)

        # Create blocked issue
        blocked_request = IssueCreateRequest(
            title="Blocked",
            description="Test",
            area=IssueArea.API,
            depends_on=[dep_issue.id],
        )
        blocked_issue = await issue_service.create_issue(blocked_request)

        # Blocked issue should be in BACKLOG
        assert blocked_issue.status == IssueStatus.BACKLOG

        # Complete dependency
        result = IssueResult(
            branch="feature/dep",
            summary="Done",
            commits=[],
        )
        await issue_service.complete_issue(dep_issue.id, result)

        # Blocked issue should now be READY
        unblocked = await issue_service.get_issue(blocked_issue.id)
        assert unblocked is not None
        assert unblocked.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_fail_issue_sets_failed_status(self, issue_service):
        """Test failing issue sets FAILED status."""
        # Create issue
        request = IssueCreateRequest(
            title="To Fail",
            description="Test",
            area=IssueArea.API,
        )
        created = await issue_service.create_issue(request)

        # Fail issue
        updated = await issue_service.fail_issue(created.id, "Error occurred")

        assert updated is not None
        assert updated.status == IssueStatus.FAILED
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_nonexistent_issue_returns_none(self, issue_service):
        """Test failing non-existent issue returns None."""
        updated = await issue_service.fail_issue("nonexistent", "Error")

        assert updated is None


# ============================================================================
# IssueService Tests - Dependency Graph
# ============================================================================

class TestIssueServiceDependencies:
    """Test dependency graph operations."""

    @pytest.mark.asyncio
    async def test_create_issue_updates_blocks_list(self, issue_service):
        """Test creating dependent issue updates dependency's blocks list."""
        # Create dependency
        dep_request = IssueCreateRequest(
            title="Dependency",
            description="Test",
            area=IssueArea.API,
        )
        dep_issue = await issue_service.create_issue(dep_request)

        # Create dependent issue
        blocked_request = IssueCreateRequest(
            title="Blocked",
            description="Test",
            area=IssueArea.API,
            depends_on=[dep_issue.id],
        )
        blocked_issue = await issue_service.create_issue(blocked_request)

        # Dependency should now have blocked issue in blocks list
        updated_dep = await issue_service.get_issue(dep_issue.id)
        assert blocked_issue.id in updated_dep.blocks

    @pytest.mark.asyncio
    async def test_delete_issue_updates_dependency_graph(self, issue_service):
        """Test deleting issue removes it from dependency blocks lists."""
        # Create dependency
        dep_request = IssueCreateRequest(
            title="Dependency",
            description="Test",
            area=IssueArea.API,
        )
        dep_issue = await issue_service.create_issue(dep_request)

        # Create dependent issue
        blocked_request = IssueCreateRequest(
            title="Blocked",
            description="Test",
            area=IssueArea.API,
            depends_on=[dep_issue.id],
        )
        blocked_issue = await issue_service.create_issue(blocked_request)

        # Verify dependency has blocked issue in blocks list
        dep_before = await issue_service.get_issue(dep_issue.id)
        assert blocked_issue.id in dep_before.blocks

        # Delete blocked issue
        result = await issue_service.delete_issue(blocked_issue.id)
        assert result is True

        # Dependency should no longer have blocked issue in blocks list
        updated_dep = await issue_service.get_issue(dep_issue.id)
        assert blocked_issue.id not in updated_dep.blocks

    @pytest.mark.asyncio
    async def test_resolve_dependencies_multiple_blockers(self, issue_service):
        """Test issue with multiple dependencies only becomes READY when all complete."""
        # Create two dependencies
        dep1 = await issue_service.create_issue(IssueCreateRequest(
            title="Dep 1",
            description="Test",
            area=IssueArea.API,
        ))

        dep2 = await issue_service.create_issue(IssueCreateRequest(
            title="Dep 2",
            description="Test",
            area=IssueArea.API,
        ))

        # Create issue depending on both
        blocked = await issue_service.create_issue(IssueCreateRequest(
            title="Blocked",
            description="Test",
            area=IssueArea.API,
            depends_on=[dep1.id, dep2.id],
        ))

        assert blocked.status == IssueStatus.BACKLOG

        # Complete first dependency
        result = IssueResult(branch="test", summary="Done", commits=[])
        await issue_service.complete_issue(dep1.id, result)

        # Should still be BACKLOG
        blocked_refreshed = await issue_service.get_issue(blocked.id)
        assert blocked_refreshed.status == IssueStatus.BACKLOG

        # Complete second dependency
        await issue_service.complete_issue(dep2.id, result)

        # Should now be READY
        blocked_final = await issue_service.get_issue(blocked.id)
        assert blocked_final.status == IssueStatus.READY


# ============================================================================
# IssueService Tests - Redis Indexing
# ============================================================================

class TestIssueServiceRedisIndexing:
    """Test Redis indexing operations."""

    @pytest.mark.asyncio
    async def test_create_issue_updates_status_index(self, issue_service, mock_redis):
        """Test creating issue updates Redis status index."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
            area=IssueArea.API,
        )

        issue = await issue_service.create_issue(request)

        # Should add to status index
        mock_redis._redis.sadd.assert_any_call(
            "claudevn:workmap:issues:status:ready",
            issue.id
        )

    @pytest.mark.asyncio
    async def test_create_ready_issue_adds_to_priority_queue(self, issue_service, mock_redis):
        """Test creating READY issue adds to priority queue."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
            area=IssueArea.API,
            priority=IssuePriority.P0,
        )

        issue = await issue_service.create_issue(request)

        # Should add to priority queue with score
        mock_redis._redis.zadd.assert_called()

    @pytest.mark.asyncio
    async def test_create_issue_updates_skill_index(self, issue_service, mock_redis):
        """Test creating issue with required skills updates skill index."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
            area=IssueArea.API,
            required_skills=["skill-a", "skill-b"],
        )

        issue = await issue_service.create_issue(request)

        # Should add to skill indexes
        mock_redis._redis.sadd.assert_any_call(
            "claudevn:workmap:issues:skill:skill-a",
            issue.id
        )
        mock_redis._redis.sadd.assert_any_call(
            "claudevn:workmap:issues:skill:skill-b",
            issue.id
        )

    @pytest.mark.asyncio
    async def test_delete_issue_removes_from_indexes(self, issue_service, mock_redis):
        """Test deleting issue removes from all Redis indexes."""
        request = IssueCreateRequest(
            title="Test",
            description="Test",
            area=IssueArea.API,
            required_skills=["skill-a"],
        )

        issue = await issue_service.create_issue(request)

        # Reset mock to clear create calls
        mock_redis._redis.srem.reset_mock()

        await issue_service.delete_issue(issue.id)

        # Should remove from status indexes
        mock_redis._redis.srem.assert_called()


# ============================================================================
# IssueService Tests - Archive
# ============================================================================

class TestIssueServiceArchive:
    """Test issue archiving."""

    @pytest.mark.asyncio
    async def test_archive_done_issue_moves_file(self, issue_service):
        """Test archiving completed issue moves file to archive."""
        # Create and complete issue
        request = IssueCreateRequest(
            title="To Archive",
            description="Test",
            area=IssueArea.API,
        )
        created = await issue_service.create_issue(request)

        result = IssueResult(branch="test", summary="Done", commits=[])
        await issue_service.complete_issue(created.id, result)

        # Archive issue
        success = await issue_service.archive_issue(created.id)

        assert success is True

        # File should be in archive, not issues
        issue_path = issue_service._worktree_path / "issues" / f"{created.id}.yaml"
        archive_path = issue_service._worktree_path / "archive" / "done" / f"{created.id}.yaml"

        assert not issue_path.exists()
        assert archive_path.exists()

        # Should still be retrievable
        retrieved = await issue_service.get_issue(created.id)
        assert retrieved is not None
        assert retrieved.status == IssueStatus.DONE

    @pytest.mark.asyncio
    async def test_archive_non_done_issue_fails(self, issue_service):
        """Test archiving non-DONE issue fails."""
        # Create ready issue
        request = IssueCreateRequest(
            title="Not Done",
            description="Test",
            area=IssueArea.API,
        )
        created = await issue_service.create_issue(request)

        # Try to archive
        success = await issue_service.archive_issue(created.id)

        assert success is False

    @pytest.mark.asyncio
    async def test_archive_nonexistent_issue_fails(self, issue_service):
        """Test archiving non-existent issue fails."""
        success = await issue_service.archive_issue("nonexistent")

        assert success is False
