"""Tests for PlannerProfileService intent integration.

Verifies that the planner profile service correctly uses persisted
intent from the Goal model and scales weights by intent strength.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.planner_profile_service import PlannerProfileService
from models.work_map import (
    Goal, GoalIntentType, GoalStatus, GoalAdjustIntentRequest,
    IntentSignal, IssuePriority,
)


@pytest.fixture
def service():
    """Create PlannerProfileService without Redis."""
    return PlannerProfileService(redis_client=None)


@pytest.fixture
def expansion_goal():
    """Goal with persisted expansion intent."""
    return Goal(
        goal_id="goal_expand",
        title="Build new auth",
        description="Create authentication system",
        project_id="proj_1",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
        primary_intent=GoalIntentType.EXPANSION,
        intent_strength=0.8,
    )


@pytest.fixture
def consolidation_goal():
    """Goal with persisted consolidation intent."""
    return Goal(
        goal_id="goal_consolidate",
        title="Stabilize payments",
        description="Fix payment bugs",
        project_id="proj_1",
        priority=IssuePriority.P0,
        status=GoalStatus.IN_PROGRESS,
        primary_intent=GoalIntentType.CONSOLIDATION,
        intent_strength=0.9,
    )


@pytest.fixture
def quality_goal():
    """Goal with persisted quality intent."""
    return Goal(
        goal_id="goal_quality",
        title="Improve tests",
        description="Add coverage",
        project_id="proj_1",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
        primary_intent=GoalIntentType.QUALITY_FOCUSED,
        intent_strength=0.7,
    )


@pytest.fixture
def no_intent_goal():
    """Goal without persisted intent (fallback to keyword detection)."""
    return Goal(
        goal_id="goal_no_intent",
        title="Build something new",
        description="Create and implement a feature",
        project_id="proj_1",
        priority=IssuePriority.P2,
        status=GoalStatus.IN_PROGRESS,
    )


class TestDetectIntent:
    """Test _detect_intent with persisted vs fallback behavior."""

    def test_uses_persisted_intent(self, service, expansion_goal):
        """Test that persisted primary_intent is used directly."""
        intent = service._detect_intent(expansion_goal)
        assert intent == "expansion"

    def test_uses_persisted_consolidation(self, service, consolidation_goal):
        """Test persisted consolidation intent."""
        intent = service._detect_intent(consolidation_goal)
        assert intent == "consolidation"

    def test_uses_persisted_quality(self, service, quality_goal):
        """Test persisted quality_focused intent."""
        intent = service._detect_intent(quality_goal)
        assert intent == "quality_focused"

    def test_fallback_keyword_detection(self, service, no_intent_goal):
        """Test fallback to keyword detection when no persisted intent."""
        intent = service._detect_intent(no_intent_goal)
        # "Build" and "Create" and "implement" should trigger expansion
        assert intent == "expansion"


class TestGoalWeightFactor:
    """Test _get_goal_weight_factor."""

    def test_high_strength_high_factor(self, service, expansion_goal):
        """Test that high intent_strength gives high weight factor."""
        factor = service._get_goal_weight_factor(expansion_goal)
        # 0.5 + 0.8 = 1.3
        assert factor == pytest.approx(1.3)

    def test_low_strength_low_factor(self, service):
        """Test that low intent_strength gives low weight factor."""
        goal = Goal(
            goal_id="goal_weak", title="Maybe build", description="Consider",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.EXPANSION, intent_strength=0.2,
        )
        factor = service._get_goal_weight_factor(goal)
        # 0.5 + 0.2 = 0.7
        assert factor == pytest.approx(0.7)

    def test_no_strength_neutral_factor(self, service, no_intent_goal):
        """Test that zero intent_strength gives neutral factor."""
        factor = service._get_goal_weight_factor(no_intent_goal)
        assert factor == 1.0


class TestIntentToWeightsScaling:
    """Test that _intent_to_weights scales by intent strength."""

    def test_strong_intent_higher_weights(self, service):
        """Test that stronger intent produces higher weights."""
        strong_goal = Goal(
            goal_id="strong", title="Build", description="Create",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.EXPANSION, intent_strength=0.9,
        )
        weak_goal = Goal(
            goal_id="weak", title="Build", description="Create",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.EXPANSION, intent_strength=0.2,
        )

        strong_weights = service._intent_to_weights("expansion", strong_goal)
        weak_weights = service._intent_to_weights("expansion", weak_goal)

        # Both should have work_type weights
        assert "work_type" in strong_weights
        assert "work_type" in weak_weights

        # Strong goal should have higher or equal weights
        for key in strong_weights.get("work_type", {}):
            if key in weak_weights.get("work_type", {}):
                strong_val = strong_weights["work_type"][key][0][0]
                weak_val = weak_weights["work_type"][key][0][0]
                assert strong_val >= weak_val


class TestConstructProfile:
    """Test profile construction with intent-enriched goals."""

    @pytest.mark.asyncio
    async def test_single_expansion_goal(self, service, expansion_goal):
        """Test profile from single expansion goal."""
        profile = await service.construct_profile("proj_1", [expansion_goal])

        assert profile.project_id == "proj_1"
        assert "goal_expand" in profile.active_goal_ids
        # Expansion should have high feature weight
        feature_weight = profile.weights.get_weight("work_type", "feature")
        assert feature_weight > 0.5

    @pytest.mark.asyncio
    async def test_single_quality_goal(self, service, quality_goal):
        """Test profile from single quality-focused goal."""
        profile = await service.construct_profile("proj_1", [quality_goal])

        assert "goal_quality" in profile.active_goal_ids
        # Quality focus should have high test weight
        test_weight = profile.weights.get_weight("work_type", "test")
        assert test_weight > 0.5

    @pytest.mark.asyncio
    async def test_multi_goal_reconciliation(
        self, service, expansion_goal, consolidation_goal
    ):
        """Test profile reconciles multiple goals."""
        profile = await service.construct_profile(
            "proj_1", [expansion_goal, consolidation_goal]
        )

        assert len(profile.active_goal_ids) == 2
        # Both goals' rules should be present
        assert len(profile.policy_rules) > 0

    @pytest.mark.asyncio
    async def test_quality_focused_rules(self, service, quality_goal):
        """Test that quality_focused intent generates correct rules."""
        profile = await service.construct_profile("proj_1", [quality_goal])

        rule_names = [r.name for r in profile.policy_rules]
        assert "Finish near-complete work" in rule_names
        assert "Defer new features during quality focus" in rule_names

    @pytest.mark.asyncio
    async def test_profile_triggers(self, service, expansion_goal):
        """Test that profile records goal triggers."""
        profile = await service.construct_profile("proj_1", [expansion_goal])

        assert len(profile.triggers) == 1
        assert profile.triggers[0].source_id == expansion_goal.goal_id

    @pytest.mark.asyncio
    async def test_update_for_goal_removed(
        self, service, expansion_goal, consolidation_goal
    ):
        """Test profile rebuild when a goal is removed."""
        # Build initial profile with both goals
        await service.construct_profile(
            "proj_1", [expansion_goal, consolidation_goal]
        )

        # Remove expansion goal
        profile = await service.update_for_goal_removed(
            "proj_1", expansion_goal.goal_id, [consolidation_goal]
        )

        assert profile is not None
        assert expansion_goal.goal_id not in profile.active_goal_ids
        assert consolidation_goal.goal_id in profile.active_goal_ids


class TestGoalModels:
    """Test the new goal model fields."""

    def test_goal_intent_fields_default(self):
        """Test Goal model default values for intent fields."""
        goal = Goal(
            goal_id="test", title="Test", description="Test",
            project_id="proj_1",
        )
        assert goal.intent_signals == []
        assert goal.primary_intent is None
        assert goal.intent_strength == 0.0

    def test_goal_with_intent(self):
        """Test Goal model with intent fields set."""
        goal = Goal(
            goal_id="test", title="Test", description="Test",
            project_id="proj_1",
            primary_intent=GoalIntentType.EXPANSION,
            intent_strength=0.75,
            intent_signals=[
                IntentSignal(
                    intent_type=GoalIntentType.EXPANSION,
                    strength=0.75,
                    keywords_matched=["build", "create"],
                ),
            ],
        )
        assert goal.primary_intent == GoalIntentType.EXPANSION
        assert goal.intent_strength == 0.75
        assert len(goal.intent_signals) == 1

    def test_goal_retired_status(self):
        """Test that RETIRED is a valid GoalStatus."""
        assert GoalStatus.RETIRED == "retired"
        goal = Goal(
            goal_id="test", title="Test", description="Test",
            project_id="proj_1", status=GoalStatus.RETIRED,
        )
        assert goal.status == GoalStatus.RETIRED

    def test_goal_intent_type_enum(self):
        """Test all GoalIntentType values."""
        assert GoalIntentType.EXPANSION == "expansion"
        assert GoalIntentType.CONSOLIDATION == "consolidation"
        assert GoalIntentType.TARGETED_INVESTMENT == "targeted_investment"
        assert GoalIntentType.QUALITY_FOCUSED == "quality_focused"

    def test_intent_signal_model(self):
        """Test IntentSignal creation and fields."""
        signal = IntentSignal(
            intent_type=GoalIntentType.EXPANSION,
            strength=0.8,
            detected_from="comment",
            source_id="comment_123",
            keywords_matched=["build", "create"],
        )
        assert signal.intent_type == GoalIntentType.EXPANSION
        assert signal.strength == 0.8
        assert signal.detected_from == "comment"
        assert signal.source_id == "comment_123"
        assert signal.detected_at is not None

    def test_goal_adjust_request(self):
        """Test GoalAdjustIntentRequest model."""
        request = GoalAdjustIntentRequest(
            primary_intent=GoalIntentType.CONSOLIDATION,
            intent_strength=0.9,
            title="Updated title",
            reparse_intent=True,
        )
        assert request.primary_intent == GoalIntentType.CONSOLIDATION
        assert request.intent_strength == 0.9
        assert request.title == "Updated title"
        assert request.reparse_intent is True

    def test_goal_adjust_request_minimal(self):
        """Test GoalAdjustIntentRequest with no fields."""
        request = GoalAdjustIntentRequest()
        assert request.primary_intent is None
        assert request.intent_strength is None
        assert request.reparse_intent is False
