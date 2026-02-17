"""Tests for bucket reorganization trigger paths.

Verifies that profile changes correctly trigger bucket tree reorganization,
specifically fixing the bug where construct_profile() passed None as
old_profile, preventing reorganization detection.

Reference: Issue #570
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PlannerProfile,
    PolicyActionType,
    PolicyConditionType,
    PolicyRule,
    ProfileWeights,
    WeightedValue,
)
from models.priority_bucket import ReorganizationTriggerType
from models.work_map import Goal, GoalStatus, IssuePriority
from services.planner_profile_service import PlannerProfileService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """PlannerProfileService with no Redis, mocked persistence."""
    svc = PlannerProfileService(redis_client=None)
    svc._save_profile_to_redis = AsyncMock()
    svc._save_profile_history = AsyncMock()
    svc._record_profile_shift_trace = AsyncMock()
    return svc


@pytest.fixture
def expansion_goal():
    return Goal(
        goal_id="goal_expand_001",
        title="Build new payment processing system",
        description="Create and implement a new payment gateway",
        project_id="project-001",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def consolidation_goal():
    return Goal(
        goal_id="goal_consolidate_001",
        title="Harden and stabilize the authentication system",
        description="Fix bugs, improve test coverage, and validate security",
        project_id="project-001",
        priority=IssuePriority.P0,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def existing_profile():
    """A pre-existing profile for a project."""
    return PlannerProfile(
        profile_id="profile_existing",
        project_id="project-001",
        weights=ProfileWeights(
            work_type_weights={
                "feature": WeightedValue(
                    weight=0.9,
                    confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
                ),
            },
            lifecycle_stage_weights={
                "build": WeightedValue(
                    weight=0.9,
                    confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
                ),
            },
        ),
        policy_rules=[
            PolicyRule(
                rule_id="rule_existing",
                name="Defer refactoring",
                condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
                condition_params={"category": "work_type", "key": "refactor"},
                action_type=PolicyActionType.DEPRIORITIZE,
                action_params={"factor": 0.5},
                confidence=ConfidenceBand(level=ConfidenceLevel.LOW),
                source_goal_id="goal_expand_001",
            ),
        ],
        active_goal_ids=["goal_expand_001"],
        version=1,
    )


# =============================================================================
# construct_profile passes old profile to _trigger_reorganization
# =============================================================================


class TestConstructProfileReorgTrigger:
    """Verify that construct_profile captures and passes old profile."""

    @pytest.mark.asyncio
    async def test_passes_old_profile_when_one_exists(
        self, service, expansion_goal, existing_profile
    ):
        """When a profile already exists for the project, construct_profile
        should pass it as old_profile to _trigger_reorganization."""
        service._profiles["project-001"] = existing_profile
        service._trigger_reorganization = AsyncMock()

        await service.construct_profile("project-001", [expansion_goal])

        service._trigger_reorganization.assert_called_once()
        args = service._trigger_reorganization.call_args
        assert args[0][0] == "project-001"  # project_id
        assert args[0][1] is existing_profile  # old_profile
        assert args[0][2].profile_id != existing_profile.profile_id  # new profile

    @pytest.mark.asyncio
    async def test_passes_none_when_no_prior_profile(
        self, service, expansion_goal
    ):
        """When no profile exists for the project, old_profile should be None."""
        service._trigger_reorganization = AsyncMock()

        await service.construct_profile("project-001", [expansion_goal])

        service._trigger_reorganization.assert_called_once()
        args = service._trigger_reorganization.call_args
        assert args[0][0] == "project-001"
        assert args[0][1] is None  # no old profile
        assert args[0][2] is not None  # new profile

    @pytest.mark.asyncio
    async def test_new_goal_triggers_reorg_with_old_profile(
        self, service, expansion_goal, consolidation_goal, existing_profile
    ):
        """update_for_new_goal → construct_profile should pass the old profile."""
        service._profiles["project-001"] = existing_profile
        service._trigger_reorganization = AsyncMock()

        await service.update_for_new_goal(
            "project-001", consolidation_goal, [expansion_goal]
        )

        service._trigger_reorganization.assert_called_once()
        args = service._trigger_reorganization.call_args
        # old_profile should be the existing expansion profile
        assert args[0][1] is existing_profile

    @pytest.mark.asyncio
    async def test_goal_removed_triggers_reorg_with_old_profile(
        self, service, expansion_goal, consolidation_goal, existing_profile
    ):
        """update_for_goal_removed → construct_profile should pass old profile."""
        service._profiles["project-001"] = existing_profile
        service._trigger_reorganization = AsyncMock()

        await service.update_for_goal_removed(
            "project-001", "goal_consolidate_001", [expansion_goal]
        )

        service._trigger_reorganization.assert_called_once()
        args = service._trigger_reorganization.call_args
        assert args[0][1] is existing_profile


# =============================================================================
# trigger_bucket_tree_reorganization handles None old_profile
# =============================================================================


class TestTriggerBucketTreeReorganization:
    """Tests for the top-level trigger function in bucket_tree_store."""

    @pytest.mark.asyncio
    async def test_none_old_profile_with_existing_tree_triggers_reorg(self):
        """When old_profile is None but a bucket tree exists,
        reorganization should still trigger (initial profile alignment)."""
        from services.bucket_tree_store import trigger_bucket_tree_reorganization

        mock_tree = MagicMock()
        mock_tree.version = 1
        mock_tree.buckets = []

        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=mock_tree)
        mock_store.save = AsyncMock()

        mock_reorg = MagicMock()
        mock_reorg.detect_profile_shift = MagicMock(return_value=False)
        mock_reorg.detect_trigger = MagicMock(return_value=None)

        mock_result = MagicMock()
        mock_result.tree = mock_tree
        mock_result.previous_version = 1
        mock_result.event = MagicMock(items_moved=0, items_preserved=0)
        mock_reorg.reorganize = AsyncMock(return_value=mock_result)

        new_profile = PlannerProfile(
            profile_id="profile_new",
            project_id="project-001",
            version=1,
        )

        mock_wm = MagicMock()
        mock_issue_list = MagicMock()
        mock_issue_list.items = [MagicMock(
            issue_id="issue-1",
            title="Test",
            description="Test item",
            issue_type=MagicMock(value="feature"),
            priority=MagicMock(value="P1"),
            depends_on=[],
            assigned_compute_id=None,
        )]
        mock_wm.list_issues = AsyncMock(return_value=mock_issue_list)

        with patch("services.bucket_tree_store.get_bucket_tree_store", return_value=mock_store), \
             patch("services.bucket_reorganization_service.get_bucket_reorganization_service", return_value=mock_reorg), \
             patch("services.work_map_service.get_work_map_service", return_value=mock_wm):

            result = await trigger_bucket_tree_reorganization("project-001", None, new_profile)

        assert result is True
        mock_reorg.reorganize.assert_called_once()
        # Verify trigger type was PROFILE_SHIFT
        call_kwargs = mock_reorg.reorganize.call_args
        assert call_kwargs[1]["trigger_type"] == ReorganizationTriggerType.PROFILE_SHIFT

    @pytest.mark.asyncio
    async def test_no_tree_returns_false(self):
        """When no bucket tree exists, should return False."""
        from services.bucket_tree_store import trigger_bucket_tree_reorganization

        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=None)

        new_profile = PlannerProfile(
            profile_id="profile_new",
            project_id="project-001",
            version=1,
        )

        with patch("services.bucket_tree_store.get_bucket_tree_store", return_value=mock_store):
            result = await trigger_bucket_tree_reorganization("project-001", None, new_profile)

        assert result is False

    @pytest.mark.asyncio
    async def test_insignificant_shift_returns_false(self):
        """When profile shift is below threshold, should return False."""
        from services.bucket_tree_store import trigger_bucket_tree_reorganization

        mock_tree = MagicMock()
        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=mock_tree)

        mock_reorg = MagicMock()
        mock_reorg.detect_profile_shift = MagicMock(return_value=False)
        mock_reorg.detect_trigger = MagicMock(return_value=None)

        old_profile = PlannerProfile(
            profile_id="profile_old", project_id="project-001", version=1,
        )
        new_profile = PlannerProfile(
            profile_id="profile_new", project_id="project-001", version=2,
        )

        with patch("services.bucket_tree_store.get_bucket_tree_store", return_value=mock_store), \
             patch("services.bucket_reorganization_service.get_bucket_reorganization_service", return_value=mock_reorg):

            result = await trigger_bucket_tree_reorganization(
                "project-001", old_profile, new_profile
            )

        assert result is False
