"""Tests for Goal and Issue functionality in WorkMapService.

Tests the new core WorkMap functionality:
- Goal CRUD and lifecycle
- Issue CRUD with status flow
- Dependency resolution
- Priority queue scoring
- Assignment algorithm
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from services.work_map_service import WorkMapService
from models.work_map import (
    Goal, GoalStatus, GoalCreateRequest,
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueBatchCreateRequest, IssueResult
)


@pytest.fixture
def service():
    """Create service without Redis for in-memory testing."""
    return WorkMapService(redis_client=None)


# =============================================================================
# Goal Tests
# =============================================================================


class TestGoalCRUD:
    """Test Goal CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_goal(self, service):
        """Test creating a goal."""
        request = GoalCreateRequest(
            title="Build auth system",
            description="Implement complete auth flow",
            priority=IssuePriority.P1
        )

        goal = await service.create_goal(request)

        assert goal.goal_id.startswith("goal_")
        assert goal.title == "Build auth system"
        assert goal.description == "Implement complete auth flow"
        assert goal.priority == IssuePriority.P1
        assert goal.status == GoalStatus.PLANNING
        assert goal.issue_ids == []

    @pytest.mark.asyncio
    async def test_get_goal(self, service):
        """Test getting a goal by ID."""
        request = GoalCreateRequest(
            title="Test Goal",
            description="Test description"
        )
        created = await service.create_goal(request)

        goal = await service.get_goal(created.goal_id)

        assert goal is not None
        assert goal.goal_id == created.goal_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_goal(self, service):
        """Test getting a nonexistent goal returns None."""
        goal = await service.get_goal("nonexistent")
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
        goal1 = await service.create_goal(GoalCreateRequest(
            title="Planning Goal",
            description="In planning"
        ))
        goal2 = await service.create_goal(GoalCreateRequest(
            title="In Progress Goal",
            description="Being worked"
        ))
        await service.update_goal_status(goal2.goal_id, GoalStatus.IN_PROGRESS)

        result = await service.list_goals(status=GoalStatus.PLANNING)

        assert len(result.items) == 1
        assert result.items[0].goal_id == goal1.goal_id

    @pytest.mark.asyncio
    async def test_delete_goal(self, service):
        """Test deleting a goal (soft delete by default)."""
        goal = await service.create_goal(GoalCreateRequest(
            title="To Delete",
            description="Will be deleted"
        ))

        result = await service.delete_goal(goal.goal_id)

        assert result is not None
        assert result.deleted is True
        assert result.goal_id == goal.goal_id
        # Soft deleted goal should not be visible in regular get
        assert await service.get_goal(goal.goal_id) is None
        # But should be visible with include_deleted
        assert await service.get_goal(goal.goal_id, include_deleted=True) is not None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_goal(self, service):
        """Test deleting nonexistent goal returns None."""
        result = await service.delete_goal("nonexistent")
        assert result is None


class TestGoalStatusTransitions:
    """Test Goal status transitions."""

    @pytest.mark.asyncio
    async def test_goal_starts_in_planning(self, service):
        """Test that new goals start in PLANNING status."""
        goal = await service.create_goal(GoalCreateRequest(
            title="New Goal",
            description="Fresh goal"
        ))

        assert goal.status == GoalStatus.PLANNING

    @pytest.mark.asyncio
    async def test_update_goal_status(self, service):
        """Test updating goal status."""
        goal = await service.create_goal(GoalCreateRequest(
            title="Test",
            description="Test"
        ))

        updated = await service.update_goal_status(goal.goal_id, GoalStatus.IN_PROGRESS)

        assert updated is not None
        assert updated.status == GoalStatus.IN_PROGRESS


# =============================================================================
# Issue Tests
# =============================================================================


class TestIssueCRUD:
    """Test Issue CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_issue_without_deps(self, service):
        """Test creating an issue without dependencies starts as READY."""
        request = IssueCreateRequest(
            title="Create user table",
            description="Create the users table",
            issue_type=IssueType.FEATURE,
            area=IssueArea.DATABASE,
            priority=IssuePriority.P1,
            required_skills=["db-engineer"]
        )

        issue = await service.create_issue(request)

        assert issue.issue_id.startswith("issue_")
        assert issue.title == "Create user table"
        assert issue.status == IssueStatus.READY  # No deps = ready
        assert issue.priority == IssuePriority.P1
        assert issue.area == IssueArea.DATABASE
        assert issue.required_skills == ["db-engineer"]

    @pytest.mark.asyncio
    async def test_create_issue_with_deps(self, service):
        """Test creating an issue with unmet dependencies starts as BACKLOG."""
        # Create dependency
        dep = await service.create_issue(IssueCreateRequest(
            title="Dependency",
            description="Must complete first"
        ))

        # Create dependent issue
        issue = await service.create_issue(IssueCreateRequest(
            title="Dependent",
            description="Depends on first",
            depends_on=[dep.issue_id]
        ))

        assert issue.status == IssueStatus.BACKLOG  # Has unmet deps
        assert dep.issue_id in issue.depends_on

    @pytest.mark.asyncio
    async def test_get_issue(self, service):
        """Test getting an issue by ID."""
        created = await service.create_issue(IssueCreateRequest(
            title="Test Issue",
            description="Test"
        ))

        issue = await service.get_issue(created.issue_id)

        assert issue is not None
        assert issue.issue_id == created.issue_id

    @pytest.mark.asyncio
    async def test_update_issue(self, service):
        """Test updating an issue."""
        from models.work_map import IssueUpdateRequest

        created = await service.create_issue(IssueCreateRequest(
            title="Original",
            description="Original desc",
            priority=IssuePriority.P3
        ))

        updated = await service.update_issue(
            created.issue_id,
            IssueUpdateRequest(
                title="Updated Title",
                priority=IssuePriority.P1
            )
        )

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.priority == IssuePriority.P1

    @pytest.mark.asyncio
    async def test_delete_issue(self, service):
        """Test deleting an issue."""
        issue = await service.create_issue(IssueCreateRequest(
            title="To Delete",
            description="Will be deleted"
        ))

        result = await service.delete_issue(issue.issue_id)

        assert result["deleted"] is True
        assert await service.get_issue(issue.issue_id) is None


class TestIssueStatusFlow:
    """Test Issue status flow: backlog → ready → in_progress → done."""

    @pytest.mark.asyncio
    async def test_status_transitions_valid(self, service):
        """Test valid status transitions."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Test Issue",
            description="Test"
        ))

        # ready → in_progress
        updated = await service.update_issue_status(
            issue.issue_id, IssueStatus.IN_PROGRESS
        )
        assert updated.status == IssueStatus.IN_PROGRESS
        assert updated.started_at is not None

        # in_progress → done
        updated = await service.update_issue_status(
            issue.issue_id, IssueStatus.DONE
        )
        assert updated.status == IssueStatus.DONE
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_status_transition_blocked(self, service):
        """Test transition to blocked status."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Test",
            description="Test"
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)

        updated = await service.update_issue_status(
            issue.issue_id, IssueStatus.BLOCKED
        )

        assert updated.status == IssueStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_invalid_status_transition(self, service):
        """Test invalid status transitions return None."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Test",
            description="Test"
        ))

        # Cannot go directly from READY to DONE
        result = await service.update_issue_status(
            issue.issue_id, IssueStatus.DONE
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_complete_issue_with_result(self, service):
        """Test completing an issue with result."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Test",
            description="Test"
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)

        result = IssueResult(
            branch="feat/issue-123",
            summary="Implemented feature",
            commits=["abc123", "def456"]
        )

        completed = await service.complete_issue(
            issue.issue_id, result
        )

        assert completed.status == IssueStatus.DONE
        assert completed.result is not None
        assert completed.result.branch == "feat/issue-123"
        assert len(completed.result.commits) == 2


class TestDependencyResolution:
    """Test dependency tracking and automatic unblocking."""

    @pytest.mark.asyncio
    async def test_dependency_blocks_update(self, service):
        """Test that dependencies update blocks list."""
        dep = await service.create_issue(IssueCreateRequest(
            title="Dependency",
            description="First"
        ))

        dependent = await service.create_issue(IssueCreateRequest(
            title="Dependent",
            description="Second",
            depends_on=[dep.issue_id]
        ))

        # Check blocks was updated
        dep = await service.get_issue(dep.issue_id)
        assert dependent.issue_id in dep.blocks

    @pytest.mark.asyncio
    async def test_completing_dep_unblocks_dependent(self, service):
        """Test that completing a dependency moves dependents to READY."""
        dep = await service.create_issue(IssueCreateRequest(
            title="Dependency",
            description="First"
        ))

        dependent = await service.create_issue(IssueCreateRequest(
            title="Dependent",
            description="Second",
            depends_on=[dep.issue_id]
        ))

        assert dependent.status == IssueStatus.BACKLOG

        # Complete the dependency
        await service.update_issue_status(dep.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(dep.issue_id, IssueResult())

        # Check dependent is now ready
        dependent = await service.get_issue(dependent.issue_id)
        assert dependent.status == IssueStatus.READY

    @pytest.mark.asyncio
    async def test_multiple_deps_all_must_complete(self, service):
        """Test that all dependencies must complete before ready."""
        dep1 = await service.create_issue(IssueCreateRequest(
            title="Dep 1",
            description="First dep"
        ))
        dep2 = await service.create_issue(IssueCreateRequest(
            title="Dep 2",
            description="Second dep"
        ))

        dependent = await service.create_issue(IssueCreateRequest(
            title="Dependent",
            description="Depends on both",
            depends_on=[dep1.issue_id, dep2.issue_id]
        ))

        # Complete first dep
        await service.update_issue_status(dep1.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(dep1.issue_id, IssueResult())

        # Dependent should still be backlog
        dependent = await service.get_issue(dependent.issue_id)
        assert dependent.status == IssueStatus.BACKLOG

        # Complete second dep
        await service.update_issue_status(dep2.issue_id, IssueStatus.IN_PROGRESS)
        await service.complete_issue(dep2.issue_id, IssueResult())

        # Now dependent should be ready
        dependent = await service.get_issue(dependent.issue_id)
        assert dependent.status == IssueStatus.READY


class TestPriorityScoring:
    """Test priority queue scoring: (Priority * 1000) + Age."""

    @pytest.mark.asyncio
    async def test_priority_score_calculation(self, service):
        """Test that priority score is calculated correctly."""
        issue = await service.create_issue(IssueCreateRequest(
            title="P0 Issue",
            description="Critical",
            priority=IssuePriority.P0
        ))

        # P0 = 0, so score should be 0 * 1000 + small_age
        score = issue.calculate_priority_score()
        assert score < 1000  # P0 weight * 1000 + age should be < 1000

    @pytest.mark.asyncio
    async def test_priority_ordering_in_queue(self, service):
        """Test that ready queue is ordered by priority score."""
        # Create issues in reverse priority order
        p3 = await service.create_issue(IssueCreateRequest(
            title="P3 Issue",
            description="Low",
            priority=IssuePriority.P3
        ))
        p1 = await service.create_issue(IssueCreateRequest(
            title="P1 Issue",
            description="High",
            priority=IssuePriority.P1
        ))
        p0 = await service.create_issue(IssueCreateRequest(
            title="P0 Issue",
            description="Critical",
            priority=IssuePriority.P0
        ))

        ready_queue = await service.get_ready_queue()

        # P0 should be first
        assert ready_queue[0].issue_id == p0.issue_id
        assert ready_queue[1].issue_id == p1.issue_id
        assert ready_queue[2].issue_id == p3.issue_id


class TestBatchIssueCreation:
    """Test batch issue creation for Planner."""

    @pytest.mark.asyncio
    async def test_create_issues_batch(self, service):
        """Test creating multiple issues at once."""
        goal = await service.create_goal(GoalCreateRequest(
            title="Auth System",
            description="Build auth"
        ))

        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(
                    title="Design schema",
                    description="Design database schema",
                    depends_on=[]
                ),
                IssueCreateRequest(
                    title="Implement model",
                    description="Implement user model",
                    depends_on=[0]  # Batch-internal reference
                ),
                IssueCreateRequest(
                    title="Add validation",
                    description="Add validation",
                    depends_on=[1]  # Batch-internal reference
                )
            ]
        )

        response = await service.create_issues_batch(request)

        assert response.success is True
        assert len(response.created_issues) == 3
        assert response.ready_count == 1  # Only first has no deps

    @pytest.mark.asyncio
    async def test_batch_updates_goal(self, service):
        """Test that batch creation updates goal issue list."""
        goal = await service.create_goal(GoalCreateRequest(
            title="Auth System",
            description="Build auth"
        ))

        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(title="Issue 1", description="Desc 1"),
                IssueCreateRequest(title="Issue 2", description="Desc 2")
            ]
        )

        await service.create_issues_batch(request)

        goal = await service.get_goal(goal.goal_id)
        assert len(goal.issue_ids) == 2
        assert goal.status == GoalStatus.IN_PROGRESS


class TestIssueAssignment:
    """Test issue assignment to compute instances."""

    @pytest.mark.asyncio
    async def test_assign_issue_to_compute(self, service):
        """Test assigning a ready issue to a compute."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Test Issue",
            description="Test",
            required_skills=["code-writer"]
        ))

        assigned = await service.assign_issue_to_compute(
            issue.issue_id,
            "compute-001",
            ["code-writer"]
        )

        assert assigned is not None
        assert assigned.status == IssueStatus.IN_PROGRESS
        assert assigned.assigned_compute_id == "compute-001"

    @pytest.mark.asyncio
    async def test_cannot_assign_backlog_issue(self, service):
        """Test that backlog issues cannot be assigned."""
        dep = await service.create_issue(IssueCreateRequest(
            title="Dependency",
            description="First"
        ))

        dependent = await service.create_issue(IssueCreateRequest(
            title="Dependent",
            description="Has deps",
            depends_on=[dep.issue_id]
        ))

        result = await service.assign_issue_to_compute(
            dependent.issue_id,
            "compute-001",
            []
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_issue_assignment(self, service):
        """Test getting next issue assignment."""
        # Create issues requiring different skills
        issue1 = await service.create_issue(IssueCreateRequest(
            title="DB Issue",
            description="DB work",
            required_skills=["db-engineer"],
            priority=IssuePriority.P2
        ))

        issue2 = await service.create_issue(IssueCreateRequest(
            title="Code Issue",
            description="Code work",
            required_skills=["code-writer"],
            priority=IssuePriority.P1
        ))

        # Request with code-writer skill
        assigned = await service.get_next_issue_assignment(
            "compute-001",
            ["code-writer"]
        )

        assert assigned is not None
        assert assigned.issue_id == issue2.issue_id  # Has matching skill

    @pytest.mark.asyncio
    async def test_get_next_assignment_no_match(self, service):
        """Test that no assignment is returned when no skills match."""
        await service.create_issue(IssueCreateRequest(
            title="DB Issue",
            description="Needs DB skill",
            required_skills=["db-engineer"]
        ))

        result = await service.get_next_issue_assignment(
            "compute-001",
            ["frontend-dev"]  # Wrong skill
        )

        assert result is None


class TestGoalCompletion:
    """Test goal completion when all issues are done."""

    @pytest.mark.asyncio
    async def test_goal_completes_when_all_issues_done(self, service):
        """Test that goal status changes to DONE when all issues complete."""
        goal = await service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test"
        ))

        # Create issues for this goal
        request = IssueBatchCreateRequest(
            goal_id=goal.goal_id,
            issues=[
                IssueCreateRequest(title="Issue 1", description="First"),
                IssueCreateRequest(title="Issue 2", description="Second")
            ]
        )
        response = await service.create_issues_batch(request)

        # Complete all issues
        for item in response.created_issues:
            issue_id = item["id"]
            await service.update_issue_status(issue_id, IssueStatus.IN_PROGRESS)
            await service.complete_issue(issue_id, IssueResult())

        # Check goal is done
        goal = await service.get_goal(goal.goal_id)
        assert goal.status == GoalStatus.DONE


class TestIssueStats:
    """Test issue statistics."""

    @pytest.mark.asyncio
    async def test_get_issue_stats(self, service):
        """Test getting issue statistics."""
        # Create issues in different states
        issue1 = await service.create_issue(IssueCreateRequest(
            title="Ready",
            description="Ready issue",
            priority=IssuePriority.P1,
            area=IssueArea.API
        ))

        issue2 = await service.create_issue(IssueCreateRequest(
            title="In Progress",
            description="Working",
            priority=IssuePriority.P2,
            area=IssueArea.DATABASE
        ))
        await service.update_issue_status(issue2.issue_id, IssueStatus.IN_PROGRESS)

        stats = await service.get_issue_stats()

        assert stats.total == 2
        assert stats.ready_count == 1
        assert stats.in_progress_count == 1
        assert stats.by_priority.get("P1", 0) == 1
        assert stats.by_priority.get("P2", 0) == 1
        assert stats.by_area.get("api", 0) == 1
        assert stats.by_area.get("database", 0) == 1


class TestIssueListFilters:
    """Test issue list filtering."""

    @pytest.mark.asyncio
    async def test_list_issues_by_status(self, service):
        """Test listing issues filtered by status."""
        await service.create_issue(IssueCreateRequest(
            title="Ready Issue",
            description="Ready"
        ))

        issue2 = await service.create_issue(IssueCreateRequest(
            title="In Progress",
            description="Working"
        ))
        await service.update_issue_status(issue2.issue_id, IssueStatus.IN_PROGRESS)

        result = await service.list_issues(status=IssueStatus.READY)

        assert len(result.items) == 1
        assert result.items[0].title == "Ready Issue"

    @pytest.mark.asyncio
    async def test_list_issues_by_priority(self, service):
        """Test listing issues filtered by priority."""
        await service.create_issue(IssueCreateRequest(
            title="P0 Issue",
            description="Critical",
            priority=IssuePriority.P0
        ))
        await service.create_issue(IssueCreateRequest(
            title="P2 Issue",
            description="Normal",
            priority=IssuePriority.P2
        ))

        result = await service.list_issues(priority=IssuePriority.P0)

        assert len(result.items) == 1
        assert result.items[0].priority == IssuePriority.P0

    @pytest.mark.asyncio
    async def test_list_issues_by_goal(self, service):
        """Test listing issues filtered by goal."""
        goal = await service.create_goal(GoalCreateRequest(
            title="Test Goal",
            description="Test"
        ))

        await service.create_issue(IssueCreateRequest(
            title="Goal Issue",
            description="Part of goal",
            goal_id=goal.goal_id
        ))
        await service.create_issue(IssueCreateRequest(
            title="Other Issue",
            description="No goal"
        ))

        result = await service.list_issues(goal_id=goal.goal_id)

        assert len(result.items) == 1
        assert result.items[0].goal_id == goal.goal_id

    @pytest.mark.asyncio
    async def test_list_issues_by_skill(self, service):
        """Test listing issues filtered by required skill."""
        await service.create_issue(IssueCreateRequest(
            title="DB Issue",
            description="Needs DB",
            required_skills=["db-engineer", "code-writer"]
        ))
        await service.create_issue(IssueCreateRequest(
            title="Frontend Issue",
            description="Needs Frontend",
            required_skills=["frontend-dev"]
        ))

        result = await service.list_issues(skill="db-engineer")

        assert len(result.items) == 1
        assert "db-engineer" in result.items[0].required_skills


class TestIssueStatusRetryTransition:
    """Test FAILED→IN_PROGRESS transition for retry support.

    See: https://github.com/Guarrdon/claudevn/issues/662
    """

    @pytest.mark.asyncio
    async def test_failed_to_in_progress_valid(self, service):
        """FAILED→IN_PROGRESS should be a valid transition (retry support)."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Retry Test",
            description="Test"
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)
        await service.update_issue_status(issue.issue_id, IssueStatus.FAILED)

        result = await service.update_issue_status(
            issue.issue_id, IssueStatus.IN_PROGRESS
        )

        assert result is not None
        assert result.status == IssueStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_failed_to_ready_still_valid(self, service):
        """FAILED→READY should still be valid."""
        issue = await service.create_issue(IssueCreateRequest(
            title="Ready Test",
            description="Test"
        ))
        await service.update_issue_status(issue.issue_id, IssueStatus.IN_PROGRESS)
        await service.update_issue_status(issue.issue_id, IssueStatus.FAILED)

        result = await service.update_issue_status(
            issue.issue_id, IssueStatus.READY
        )

        assert result is not None
        assert result.status == IssueStatus.READY
