"""Unit tests for goal progress metrics (GoalService.get_goal_progress).

Tests the multi-dimensional progress computation including:
- Issue status breakdown and completion percentage
- Characterization progress (ontology_tags populated)
- Execution velocity and trend detection
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from models.work_map import (
    Goal, GoalProgressMetrics, GoalStatus, IssueStatus,
    IssuePriority, Issue, IssueType, IssueArea,
)
from models.ontology import OntologyTags, UniversalTags
from services.goal_service import GoalService


# ============ Fixtures ============

@pytest.fixture
def goal_service():
    """Create GoalService with no Redis."""
    service = GoalService(redis_client=None)
    service._save_goal_to_redis = AsyncMock()
    return service


def _make_goal(goal_id="goal_test1", status=GoalStatus.IN_PROGRESS, **kwargs):
    return Goal(
        goal_id=goal_id,
        title="Test goal",
        description="Test description",
        status=status,
        **kwargs,
    )


def _make_issue(
    issue_id,
    goal_id="goal_test1",
    status=IssueStatus.BACKLOG,
    ontology_tags=None,
    completed_at=None,
):
    return Issue(
        issue_id=issue_id,
        title=f"Issue {issue_id}",
        description="desc",
        goal_id=goal_id,
        status=status,
        ontology_tags=ontology_tags,
        completed_at=completed_at,
    )


# ============ Tests: Basic Cases ============


class TestGoalProgressBasic:
    """Tests for basic progress metric computation."""

    @pytest.mark.asyncio
    async def test_nonexistent_goal_returns_none(self, goal_service):
        result = await goal_service.get_goal_progress("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_goal_with_no_issues(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {}

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result is not None
        assert result.goal_id == goal.goal_id
        assert result.goal_status == GoalStatus.IN_PROGRESS
        assert result.total_issues == 0
        assert result.done_count == 0
        assert result.completion_percent == 0.0
        assert result.velocity_7d == 0
        assert result.velocity_trend == "steady"

    @pytest.mark.asyncio
    async def test_goal_with_all_done_issues(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.DONE),
            "i2": _make_issue("i2", status=IssueStatus.DONE),
            "i3": _make_issue("i3", status=IssueStatus.DONE),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.total_issues == 3
        assert result.done_count == 3
        assert result.completion_percent == 100.0
        assert result.in_progress_count == 0
        assert result.blocked_count == 0
        assert result.failed_count == 0


# ============ Tests: Status Breakdown ============


class TestGoalProgressStatusBreakdown:
    """Tests for issue status counts."""

    @pytest.mark.asyncio
    async def test_mixed_status_counts(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.DONE),
            "i2": _make_issue("i2", status=IssueStatus.IN_PROGRESS),
            "i3": _make_issue("i3", status=IssueStatus.BLOCKED),
            "i4": _make_issue("i4", status=IssueStatus.FAILED),
            "i5": _make_issue("i5", status=IssueStatus.READY),
            "i6": _make_issue("i6", status=IssueStatus.BACKLOG),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.total_issues == 6
        assert result.done_count == 1
        assert result.in_progress_count == 1
        assert result.blocked_count == 1
        assert result.failed_count == 1
        assert result.ready_count == 1
        assert result.backlog_count == 1

    @pytest.mark.asyncio
    async def test_completion_percent_calculation(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.DONE),
            "i2": _make_issue("i2", status=IssueStatus.DONE),
            "i3": _make_issue("i3", status=IssueStatus.IN_PROGRESS),
            "i4": _make_issue("i4", status=IssueStatus.BACKLOG),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.completion_percent == 50.0

    @pytest.mark.asyncio
    async def test_only_counts_issues_for_this_goal(self, goal_service):
        goal = _make_goal(goal_id="goal_a")
        goal_service._goals["goal_a"] = goal
        goal_service._issues = {
            "i1": _make_issue("i1", goal_id="goal_a", status=IssueStatus.DONE),
            "i2": _make_issue("i2", goal_id="goal_b", status=IssueStatus.DONE),
            "i3": _make_issue("i3", goal_id="goal_a", status=IssueStatus.BACKLOG),
        }

        result = await goal_service.get_goal_progress("goal_a")

        assert result.total_issues == 2
        assert result.done_count == 1
        assert result.backlog_count == 1


# ============ Tests: Characterization ============


class TestGoalProgressCharacterization:
    """Tests for characterization progress metrics."""

    @pytest.mark.asyncio
    async def test_no_characterized_issues(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {
            "i1": _make_issue("i1", ontology_tags=None),
            "i2": _make_issue("i2", ontology_tags=None),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.characterized_count == 0
        assert result.characterization_percent == 0.0

    @pytest.mark.asyncio
    async def test_some_characterized_issues(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        tags = OntologyTags(
            universal=UniversalTags(
                work_type="feature",
                lifecycle_stage="build",
                technical_domains=["frontend"],
            )
        )
        goal_service._issues = {
            "i1": _make_issue("i1", ontology_tags=tags),
            "i2": _make_issue("i2", ontology_tags=None),
            "i3": _make_issue("i3", ontology_tags=tags),
            "i4": _make_issue("i4", ontology_tags=None),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.characterized_count == 2
        assert result.characterization_percent == 50.0

    @pytest.mark.asyncio
    async def test_all_characterized(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal
        tags = OntologyTags(
            universal=UniversalTags(
                work_type="bug_fix",
                lifecycle_stage="build",
                technical_domains=["backend"],
            )
        )
        goal_service._issues = {
            "i1": _make_issue("i1", ontology_tags=tags),
            "i2": _make_issue("i2", ontology_tags=tags),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.characterized_count == 2
        assert result.characterization_percent == 100.0


# ============ Tests: Velocity and Trend ============


class TestGoalProgressVelocity:
    """Tests for execution velocity and trend detection."""

    @pytest.mark.asyncio
    async def test_velocity_counts_recent_completions(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        now = datetime.now(timezone.utc)
        three_days_ago = now - timedelta(days=3)

        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.DONE, completed_at=three_days_ago),
            "i2": _make_issue("i2", status=IssueStatus.DONE, completed_at=now - timedelta(days=1)),
            "i3": _make_issue("i3", status=IssueStatus.IN_PROGRESS),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.velocity_7d == 2

    @pytest.mark.asyncio
    async def test_velocity_excludes_old_completions(self, goal_service):
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        now = datetime.now(timezone.utc)
        old = now - timedelta(days=20)

        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.DONE, completed_at=old),
            "i2": _make_issue("i2", status=IssueStatus.DONE, completed_at=now - timedelta(days=2)),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.velocity_7d == 1

    @pytest.mark.asyncio
    async def test_trend_accelerating(self, goal_service):
        """More completions this week than last week → accelerating."""
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        now = datetime.now(timezone.utc)
        goal_service._issues = {
            # This week: 3 completions
            "i1": _make_issue("i1", status=IssueStatus.DONE, completed_at=now - timedelta(days=1)),
            "i2": _make_issue("i2", status=IssueStatus.DONE, completed_at=now - timedelta(days=2)),
            "i3": _make_issue("i3", status=IssueStatus.DONE, completed_at=now - timedelta(days=3)),
            # Last week: 1 completion
            "i4": _make_issue("i4", status=IssueStatus.DONE, completed_at=now - timedelta(days=10)),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.velocity_7d == 3
        assert result.velocity_trend == "accelerating"

    @pytest.mark.asyncio
    async def test_trend_stalling(self, goal_service):
        """Fewer completions this week than last week → stalling."""
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        now = datetime.now(timezone.utc)
        goal_service._issues = {
            # This week: 1 completion
            "i1": _make_issue("i1", status=IssueStatus.DONE, completed_at=now - timedelta(days=1)),
            # Last week: 3 completions
            "i2": _make_issue("i2", status=IssueStatus.DONE, completed_at=now - timedelta(days=8)),
            "i3": _make_issue("i3", status=IssueStatus.DONE, completed_at=now - timedelta(days=9)),
            "i4": _make_issue("i4", status=IssueStatus.DONE, completed_at=now - timedelta(days=10)),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.velocity_7d == 1
        assert result.velocity_trend == "stalling"

    @pytest.mark.asyncio
    async def test_trend_steady(self, goal_service):
        """Same completions this week and last week → steady."""
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        now = datetime.now(timezone.utc)
        goal_service._issues = {
            # This week: 2 completions
            "i1": _make_issue("i1", status=IssueStatus.DONE, completed_at=now - timedelta(days=1)),
            "i2": _make_issue("i2", status=IssueStatus.DONE, completed_at=now - timedelta(days=3)),
            # Last week: 2 completions
            "i3": _make_issue("i3", status=IssueStatus.DONE, completed_at=now - timedelta(days=8)),
            "i4": _make_issue("i4", status=IssueStatus.DONE, completed_at=now - timedelta(days=10)),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.velocity_7d == 2
        assert result.velocity_trend == "steady"

    @pytest.mark.asyncio
    async def test_trend_steady_when_no_completions(self, goal_service):
        """No completions in either period → steady."""
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.IN_PROGRESS),
            "i2": _make_issue("i2", status=IssueStatus.BACKLOG),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.velocity_7d == 0
        assert result.velocity_trend == "steady"

    @pytest.mark.asyncio
    async def test_done_without_completed_at_not_counted(self, goal_service):
        """Issues with DONE status but no completed_at should not count for velocity."""
        goal = _make_goal()
        goal_service._goals[goal.goal_id] = goal

        goal_service._issues = {
            "i1": _make_issue("i1", status=IssueStatus.DONE, completed_at=None),
            "i2": _make_issue("i2", status=IssueStatus.DONE, completed_at=None),
        }

        result = await goal_service.get_goal_progress(goal.goal_id)

        assert result.done_count == 2
        assert result.velocity_7d == 0


# ============ Tests: Goal Status Pass-through ============


class TestGoalProgressGoalStatus:
    """Tests that goal status is correctly passed through."""

    @pytest.mark.asyncio
    async def test_planning_goal_status(self, goal_service):
        goal = _make_goal(status=GoalStatus.PLANNING)
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {}

        result = await goal_service.get_goal_progress(goal.goal_id)
        assert result.goal_status == GoalStatus.PLANNING

    @pytest.mark.asyncio
    async def test_done_goal_status(self, goal_service):
        goal = _make_goal(status=GoalStatus.DONE)
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {}

        result = await goal_service.get_goal_progress(goal.goal_id)
        assert result.goal_status == GoalStatus.DONE

    @pytest.mark.asyncio
    async def test_failed_goal_status(self, goal_service):
        goal = _make_goal(status=GoalStatus.FAILED)
        goal_service._goals[goal.goal_id] = goal
        goal_service._issues = {}

        result = await goal_service.get_goal_progress(goal.goal_id)
        assert result.goal_status == GoalStatus.FAILED


# ============ Tests: GoalProgressMetrics Model ============


class TestGoalProgressMetricsModel:
    """Tests for the GoalProgressMetrics Pydantic model."""

    def test_default_values(self):
        metrics = GoalProgressMetrics(
            goal_id="g1",
            goal_status=GoalStatus.IN_PROGRESS,
        )
        assert metrics.total_issues == 0
        assert metrics.done_count == 0
        assert metrics.completion_percent == 0.0
        assert metrics.velocity_trend == "steady"
        assert metrics.computed_at is not None

    def test_all_fields_populated(self):
        metrics = GoalProgressMetrics(
            goal_id="g1",
            goal_status=GoalStatus.IN_PROGRESS,
            total_issues=10,
            done_count=5,
            in_progress_count=2,
            blocked_count=1,
            failed_count=1,
            ready_count=1,
            backlog_count=0,
            completion_percent=50.0,
            characterized_count=7,
            characterization_percent=70.0,
            velocity_7d=3,
            velocity_trend="accelerating",
        )
        assert metrics.total_issues == 10
        assert metrics.done_count == 5
        assert metrics.velocity_trend == "accelerating"
