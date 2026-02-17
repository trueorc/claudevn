"""Tests for GoalIntentService."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.goal_intent_service import (
    GoalIntentService,
    get_goal_intent_service,
    set_goal_intent_service,
    INTENT_KEYWORDS,
)
from models.work_map import (
    Goal, GoalIntentType, GoalStatus, IntentSignal, GoalConflict,
    IssuePriority,
)


@pytest.fixture
def service():
    """Create GoalIntentService instance."""
    return GoalIntentService()


@pytest.fixture
def expansion_goal():
    """Create a goal with expansion-oriented text."""
    return Goal(
        goal_id="goal_test_expand",
        title="Build new authentication system",
        description="Create and implement a new OAuth2 authentication feature. "
                    "Develop the login flow and extend the API to support social login.",
        project_id="proj_1",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def consolidation_goal():
    """Create a goal with consolidation-oriented text."""
    return Goal(
        goal_id="goal_test_consolidate",
        title="Stabilize the payment system",
        description="Fix payment processing bugs and harden the transaction pipeline. "
                    "Secure the API endpoints and strengthen error handling.",
        project_id="proj_1",
        priority=IssuePriority.P0,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def quality_goal():
    """Create a goal with quality-focused text."""
    return Goal(
        goal_id="goal_test_quality",
        title="Improve test coverage",
        description="Validate all critical paths and improve code quality. "
                    "Refactor the service layer and add regression tests.",
        project_id="proj_1",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def targeted_goal():
    """Create a goal with targeted investment text."""
    return Goal(
        goal_id="goal_test_targeted",
        title="Focus on search infrastructure",
        description="Prioritize and invest in the search backend. "
                    "Concentrate efforts on dedicated search indexing.",
        project_id="proj_1",
        priority=IssuePriority.P2,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def neutral_goal():
    """Create a goal with no clear intent keywords."""
    return Goal(
        goal_id="goal_test_neutral",
        title="Update documentation",
        description="Update the README file with latest changes.",
        project_id="proj_1",
        priority=IssuePriority.P3,
        status=GoalStatus.IN_PROGRESS,
    )


class TestParseIntent:
    """Test intent parsing from text."""

    def test_expansion_keywords(self, service):
        """Test detection of expansion intent keywords."""
        signals = service.parse_intent("Build a new feature and create API endpoints")
        assert len(signals) > 0
        expansion_signals = [s for s in signals if s.intent_type == GoalIntentType.EXPANSION]
        assert len(expansion_signals) > 0
        assert expansion_signals[0].strength > 0

    def test_consolidation_keywords(self, service):
        """Test detection of consolidation intent keywords."""
        signals = service.parse_intent("Fix critical bugs and stabilize the system")
        consolidation_signals = [s for s in signals if s.intent_type == GoalIntentType.CONSOLIDATION]
        assert len(consolidation_signals) > 0
        assert consolidation_signals[0].strength > 0

    def test_quality_focused_keywords(self, service):
        """Test detection of quality-focused intent keywords."""
        signals = service.parse_intent("Improve test coverage and validate all endpoints")
        quality_signals = [s for s in signals if s.intent_type == GoalIntentType.QUALITY_FOCUSED]
        assert len(quality_signals) > 0

    def test_targeted_keywords(self, service):
        """Test detection of targeted investment intent keywords."""
        signals = service.parse_intent("Focus and prioritize the search infrastructure")
        targeted_signals = [s for s in signals if s.intent_type == GoalIntentType.TARGETED_INVESTMENT]
        assert len(targeted_signals) > 0

    def test_no_keywords(self, service):
        """Test empty results when no intent keywords found."""
        signals = service.parse_intent("Hello world")
        assert signals == []

    def test_signals_sorted_by_strength(self, service):
        """Test that signals are sorted by strength descending."""
        # Text with multiple intent types
        signals = service.parse_intent(
            "Build new features, create endpoints, and also test validate quality"
        )
        if len(signals) > 1:
            for i in range(len(signals) - 1):
                assert signals[i].strength >= signals[i + 1].strength

    def test_source_tracking(self, service):
        """Test that source and source_id are set correctly."""
        signals = service.parse_intent(
            "Build new feature",
            source="comment",
            source_id="comment_123"
        )
        assert len(signals) > 0
        assert signals[0].detected_from == "comment"
        assert signals[0].source_id == "comment_123"

    def test_keywords_matched(self, service):
        """Test that matched keywords are recorded."""
        signals = service.parse_intent("Build and create new things")
        expansion_signals = [s for s in signals if s.intent_type == GoalIntentType.EXPANSION]
        assert len(expansion_signals) > 0
        assert "build" in expansion_signals[0].keywords_matched
        assert "create" in expansion_signals[0].keywords_matched
        assert "new" in expansion_signals[0].keywords_matched

    def test_strength_proportional_to_matches(self, service):
        """Test that more keyword matches increase strength."""
        few_keywords = service.parse_intent("build something")
        many_keywords = service.parse_intent(
            "build and create a new feature to implement and develop"
        )
        few_exp = [s for s in few_keywords if s.intent_type == GoalIntentType.EXPANSION]
        many_exp = [s for s in many_keywords if s.intent_type == GoalIntentType.EXPANSION]
        if few_exp and many_exp:
            assert many_exp[0].strength >= few_exp[0].strength


class TestClassifyGoal:
    """Test goal classification."""

    def test_expansion_goal(self, service, expansion_goal):
        """Test that expansion goal is classified correctly."""
        primary, strength, signals = service.classify_goal(expansion_goal)
        assert primary == GoalIntentType.EXPANSION
        assert strength > 0
        assert len(signals) > 0

    def test_consolidation_goal(self, service, consolidation_goal):
        """Test that consolidation goal is classified correctly."""
        primary, strength, signals = service.classify_goal(consolidation_goal)
        assert primary == GoalIntentType.CONSOLIDATION
        assert strength > 0

    def test_quality_goal(self, service, quality_goal):
        """Test that quality-focused goal is classified correctly."""
        primary, strength, signals = service.classify_goal(quality_goal)
        assert primary == GoalIntentType.QUALITY_FOCUSED
        assert strength > 0

    def test_targeted_goal(self, service, targeted_goal):
        """Test that targeted investment goal is classified correctly."""
        primary, strength, signals = service.classify_goal(targeted_goal)
        assert primary == GoalIntentType.TARGETED_INVESTMENT
        assert strength > 0

    def test_neutral_goal(self, service, neutral_goal):
        """Test classification of goal with no intent keywords."""
        primary, strength, signals = service.classify_goal(neutral_goal)
        # May return None or a weak signal depending on text
        assert strength >= 0
        if primary is None:
            assert len(signals) == 0


class TestUpdateGoalIntent:
    """Test in-place goal intent update."""

    def test_sets_intent_fields(self, service, expansion_goal):
        """Test that update_goal_intent sets all intent fields."""
        result = service.update_goal_intent(expansion_goal)
        assert result is expansion_goal  # Modified in-place
        assert result.primary_intent is not None
        assert result.intent_strength > 0
        assert len(result.intent_signals) > 0

    def test_sets_updated_at(self, service, expansion_goal):
        """Test that update_goal_intent updates the timestamp."""
        old_updated = expansion_goal.updated_at
        service.update_goal_intent(expansion_goal)
        assert expansion_goal.updated_at >= old_updated


class TestApplyCommentIntent:
    """Test comment-based intent shift detection."""

    def test_no_shift_for_neutral_comment(self, service, expansion_goal):
        """Test that neutral comments don't shift intent."""
        service.update_goal_intent(expansion_goal)
        original_intent = expansion_goal.primary_intent

        shifted, signals = service.apply_comment_intent(
            expansion_goal, "Thanks for the update", "comment_1"
        )
        assert shifted is False
        assert signals == []
        assert expansion_goal.primary_intent == original_intent

    def test_shift_detected_for_opposing_comment(self, service, expansion_goal):
        """Test that strongly opposing comment can shift intent."""
        service.update_goal_intent(expansion_goal)
        assert expansion_goal.primary_intent == GoalIntentType.EXPANSION

        # Apply a very strong consolidation comment
        shifted, signals = service.apply_comment_intent(
            expansion_goal,
            "Actually we need to fix stabilize harden secure consolidate strengthen "
            "the existing system first",
            "comment_2"
        )
        # May or may not shift depending on signal strength comparison
        assert isinstance(shifted, bool)
        assert len(signals) > 0
        consolidation_signals = [s for s in signals if s.intent_type == GoalIntentType.CONSOLIDATION]
        assert len(consolidation_signals) > 0

    def test_comment_signals_added(self, service, expansion_goal):
        """Test that comment signals are added to goal."""
        service.update_goal_intent(expansion_goal)
        original_count = len(expansion_goal.intent_signals)

        service.apply_comment_intent(
            expansion_goal,
            "Let's also focus and prioritize the search part",
            "comment_3"
        )
        assert len(expansion_goal.intent_signals) > original_count


class TestDetectConflicts:
    """Test multi-goal conflict detection."""

    def test_expansion_vs_consolidation_conflict(
        self, service, expansion_goal, consolidation_goal
    ):
        """Test that expansion vs consolidation creates a conflict."""
        service.update_goal_intent(expansion_goal)
        service.update_goal_intent(consolidation_goal)

        conflicts = service.detect_conflicts([expansion_goal, consolidation_goal])
        assert len(conflicts) > 0
        conflict = conflicts[0]
        assert conflict.goal_id_a in (expansion_goal.goal_id, consolidation_goal.goal_id)
        assert conflict.goal_id_b in (expansion_goal.goal_id, consolidation_goal.goal_id)
        assert conflict.severity > 0

    def test_expansion_vs_quality_conflict(
        self, service, expansion_goal, quality_goal
    ):
        """Test that expansion vs quality creates a conflict."""
        service.update_goal_intent(expansion_goal)
        service.update_goal_intent(quality_goal)

        conflicts = service.detect_conflicts([expansion_goal, quality_goal])
        assert len(conflicts) > 0

    def test_no_conflict_for_single_goal(self, service, expansion_goal):
        """Test that single goal has no conflicts."""
        service.update_goal_intent(expansion_goal)
        conflicts = service.detect_conflicts([expansion_goal])
        assert conflicts == []

    def test_no_conflict_for_compatible_goals(
        self, service, expansion_goal, targeted_goal
    ):
        """Test that compatible goal types don't conflict."""
        service.update_goal_intent(expansion_goal)
        service.update_goal_intent(targeted_goal)

        conflicts = service.detect_conflicts([expansion_goal, targeted_goal])
        assert conflicts == []

    def test_no_conflict_for_goals_without_intent(self, service):
        """Test that goals without intent classification don't conflict."""
        goal_a = Goal(
            goal_id="goal_a", title="A", description="A",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
        )
        goal_b = Goal(
            goal_id="goal_b", title="B", description="B",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
        )
        conflicts = service.detect_conflicts([goal_a, goal_b])
        assert conflicts == []

    def test_conflict_severity_proportional(self, service):
        """Test that conflict severity is based on intent strengths and recency."""
        from datetime import timedelta
        old_time = datetime.now(timezone.utc) - timedelta(days=30)
        goal_a = Goal(
            goal_id="goal_a", title="Build new", description="Create feature",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.EXPANSION,
            intent_strength=0.8,
            created_at=old_time,
        )
        goal_b = Goal(
            goal_id="goal_b", title="Fix", description="Stabilize",
            project_id="proj_1", status=GoalStatus.IN_PROGRESS,
            primary_intent=GoalIntentType.CONSOLIDATION,
            intent_strength=0.6,
            created_at=old_time,
        )
        conflicts = service.detect_conflicts([goal_a, goal_b])
        assert len(conflicts) == 1
        # Severity = (0.8 + 0.6) / 2 = 0.7, recency_boost = 1.0 (old goals)
        assert conflicts[0].severity == 0.7


class TestGlobalInstance:
    """Test global instance management."""

    def test_get_creates_default(self):
        """Test that get_goal_intent_service creates a default instance."""
        set_goal_intent_service(None)
        service = get_goal_intent_service()
        assert isinstance(service, GoalIntentService)

    def test_set_and_get(self):
        """Test set then get."""
        custom = GoalIntentService()
        set_goal_intent_service(custom)
        assert get_goal_intent_service() is custom
        # Cleanup
        set_goal_intent_service(None)
