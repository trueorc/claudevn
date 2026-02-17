"""Tests for PlannerProfileService — profile construction, updates, and reconciliation.

Tests cover:
- Profile construction from single and multiple goals
- Intent detection (expansion, consolidation, targeted investment)
- Goal intent to weight translation
- Policy rule generation per intent type
- Multi-goal reconciliation
- Profile updates: new goal, worker feedback, resource change, goal removed
- Redis persistence (save, load, history)
"""

import json
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
    ProfileTriggerType,
    ProfileWeights,
    WeightedValue,
)
from models.work_map import Goal, GoalStatus, IssuePriority
from services.planner_profile_service import (
    PlannerProfileService,
    get_planner_profile_service,
    set_planner_profile_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service():
    """PlannerProfileService with no Redis."""
    return PlannerProfileService(redis_client=None)


@pytest.fixture
def service_with_redis():
    """PlannerProfileService with mocked Redis."""
    mock_redis = MagicMock()
    mock_redis._prefix = "claudevn:"
    mock_redis._redis = AsyncMock()
    svc = PlannerProfileService(redis_client=mock_redis)
    svc._save_profile_to_redis = AsyncMock()
    svc._save_profile_history = AsyncMock()
    return svc


@pytest.fixture
def expansion_goal():
    """A goal with expansion intent (build new features)."""
    return Goal(
        goal_id="goal_expand_001",
        title="Build new payment processing system",
        description="Create and implement a new payment gateway integration with Stripe",
        project_id="project-001",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def consolidation_goal():
    """A goal with consolidation intent (harden, test, fix)."""
    return Goal(
        goal_id="goal_consolidate_001",
        title="Harden and stabilize the authentication system",
        description="Fix bugs, improve test coverage, and validate security of the auth system",
        project_id="project-001",
        priority=IssuePriority.P0,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def targeted_goal():
    """A goal with targeted investment intent."""
    return Goal(
        goal_id="goal_target_001",
        title="Focus investment on API layer",
        description="Prioritize and concentrate efforts on the specific API infrastructure",
        project_id="project-001",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def neutral_goal():
    """A goal with no strong intent signal."""
    return Goal(
        goal_id="goal_neutral_001",
        title="Work on the project",
        description="Continue the project work",
        project_id="project-001",
        priority=IssuePriority.P2,
        status=GoalStatus.IN_PROGRESS,
    )


# ============================================================================
# Intent Detection
# ============================================================================


class TestIntentDetection:
    """Test goal text to intent signal mapping."""

    def test_detect_expansion_intent(self, service, expansion_goal):
        intent = service._detect_intent(expansion_goal)
        assert intent == "expansion"

    def test_detect_consolidation_intent(self, service, consolidation_goal):
        intent = service._detect_intent(consolidation_goal)
        assert intent == "consolidation"

    def test_detect_targeted_intent(self, service, targeted_goal):
        intent = service._detect_intent(targeted_goal)
        assert intent == "targeted_investment"

    def test_detect_neutral_defaults_to_expansion(self, service, neutral_goal):
        intent = service._detect_intent(neutral_goal)
        assert intent == "expansion"

    def test_detect_mixed_signals_highest_wins(self, service):
        """When multiple intent keywords present, highest score wins."""
        goal = Goal(
            goal_id="goal_mixed",
            title="Fix and stabilize then add new features",
            description="Harden the system, improve test coverage, validate quality",
            project_id="project-001",
        )
        intent = service._detect_intent(goal)
        # consolidation keywords dominate: fix, stabilize, harden, test, validate, quality
        assert intent == "consolidation"


# ============================================================================
# Intent to Weights Translation
# ============================================================================


class TestIntentToWeights:
    """Test intent signal to ontology weight translation."""

    def test_expansion_weights(self, service, expansion_goal):
        weights = service._intent_to_weights("expansion", expansion_goal)
        assert "work_type" in weights
        assert "feature" in weights["work_type"]
        # Feature should have high weight for expansion
        entry = weights["work_type"]["feature"][0]
        assert entry[0] == 0.9  # weight
        assert entry[1] == ConfidenceLevel.HIGH  # confidence

    def test_consolidation_weights(self, service, consolidation_goal):
        weights = service._intent_to_weights("consolidation", consolidation_goal)
        assert "work_type" in weights
        assert "test" in weights["work_type"]
        assert "bug_fix" in weights["work_type"]
        # Test weight should be high
        test_entry = weights["work_type"]["test"][0]
        assert test_entry[0] == 0.9

    def test_consolidation_deprioritizes_features(self, service, consolidation_goal):
        weights = service._intent_to_weights("consolidation", consolidation_goal)
        feature_entry = weights["work_type"]["feature"][0]
        assert feature_entry[0] == 0.15  # Low weight for features

    def test_targeted_investment_weights(self, service, targeted_goal):
        weights = service._intent_to_weights("targeted_investment", targeted_goal)
        assert "work_type" in weights
        assert "lifecycle_stage" in weights

    def test_unknown_intent_returns_empty(self, service, expansion_goal):
        weights = service._intent_to_weights("nonexistent_intent", expansion_goal)
        assert weights == {}


# ============================================================================
# Policy Rule Generation
# ============================================================================


class TestPolicyRuleGeneration:
    """Test policy rule generation from intent."""

    def test_consolidation_generates_finish_wip_rule(self, service, consolidation_goal):
        rules = service._generate_policy_rules("consolidation", consolidation_goal)
        finish_rules = [r for r in rules if "finish" in r.name.lower()]
        assert len(finish_rules) == 1
        rule = finish_rules[0]
        assert rule.condition_type == PolicyConditionType.COMPLETION_ABOVE_THRESHOLD
        assert rule.condition_params["threshold"] == 0.8
        assert rule.action_type == PolicyActionType.PRESERVE_PRIORITY
        assert rule.source_goal_id == consolidation_goal.goal_id

    def test_consolidation_generates_test_blocker_rule(self, service, consolidation_goal):
        rules = service._generate_policy_rules("consolidation", consolidation_goal)
        blocker_rules = [r for r in rules if "blocker" in r.name.lower()]
        assert len(blocker_rules) == 1
        rule = blocker_rules[0]
        assert rule.condition_type == PolicyConditionType.BLOCKS_HIGH_PRIORITY
        assert rule.action_type == PolicyActionType.ELEVATE_PRIORITY

    def test_expansion_generates_defer_refactor_rule(self, service, expansion_goal):
        rules = service._generate_policy_rules("expansion", expansion_goal)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.condition_type == PolicyConditionType.IN_ONTOLOGY_CATEGORY
        assert rule.action_type == PolicyActionType.DEPRIORITIZE
        assert rule.confidence.level == ConfidenceLevel.LOW

    def test_targeted_generates_high_leverage_rule(self, service, targeted_goal):
        rules = service._generate_policy_rules("targeted_investment", targeted_goal)
        assert len(rules) == 1
        rule = rules[0]
        assert rule.condition_type == PolicyConditionType.BLOCKING_COUNT_ABOVE
        assert rule.action_type == PolicyActionType.ELEVATE_PRIORITY

    def test_rules_have_unique_ids(self, service, consolidation_goal):
        rules = service._generate_policy_rules("consolidation", consolidation_goal)
        rule_ids = [r.rule_id for r in rules]
        assert len(rule_ids) == len(set(rule_ids))

    def test_rules_reference_source_goal(self, service, consolidation_goal):
        rules = service._generate_policy_rules("consolidation", consolidation_goal)
        for rule in rules:
            assert rule.source_goal_id == consolidation_goal.goal_id


# ============================================================================
# Profile Construction
# ============================================================================


class TestProfileConstruction:
    """Test full profile construction from goals."""

    @pytest.mark.asyncio
    async def test_construct_single_goal(self, service, consolidation_goal):
        profile = await service.construct_profile(
            "project-001", [consolidation_goal]
        )

        assert profile.project_id == "project-001"
        assert profile.profile_id.startswith("profile_")
        assert consolidation_goal.goal_id in profile.active_goal_ids
        assert profile.version == 1

        # Should have consolidation weights
        test_weight = profile.weights.get_weight("work_type", "test")
        assert test_weight == 0.9

        # Should have consolidation policy rules
        assert len(profile.policy_rules) > 0

        # Should have a trigger
        assert len(profile.triggers) == 1
        assert profile.triggers[0].trigger_type == ProfileTriggerType.NEW_GOAL

    @pytest.mark.asyncio
    async def test_construct_stores_in_memory(self, service, expansion_goal):
        profile = await service.construct_profile(
            "project-001", [expansion_goal]
        )

        stored = await service.get_profile("project-001")
        assert stored is not None
        assert stored.profile_id == profile.profile_id

    @pytest.mark.asyncio
    async def test_construct_empty_goals(self, service):
        profile = await service.construct_profile("project-001", [])

        assert profile.project_id == "project-001"
        assert profile.active_goal_ids == []
        assert profile.policy_rules == []
        assert profile.triggers == []


# ============================================================================
# Multi-Goal Reconciliation
# ============================================================================


class TestMultiGoalReconciliation:
    """Test profile construction from multiple coexisting goals."""

    @pytest.mark.asyncio
    async def test_reconcile_two_goals(
        self, service, expansion_goal, consolidation_goal
    ):
        profile = await service.construct_profile(
            "project-001", [expansion_goal, consolidation_goal]
        )

        assert len(profile.active_goal_ids) == 2
        assert expansion_goal.goal_id in profile.active_goal_ids
        assert consolidation_goal.goal_id in profile.active_goal_ids

        # Feature weight should be reconciled between expansion (0.9) and consolidation (0.15)
        feature_weight = profile.weights.get_weight("work_type", "feature")
        assert 0.15 < feature_weight < 0.9  # Should be between the two

    @pytest.mark.asyncio
    async def test_reconcile_prefers_high_confidence(self, service):
        """Higher confidence signals should have more influence."""
        all_weights = {
            "work_type": {
                "test": [
                    (0.9, ConfidenceLevel.HIGH, "goal-1"),
                    (0.3, ConfidenceLevel.LOW, "goal-2"),
                ],
            },
        }

        reconciled = service._reconcile_weights(all_weights)
        test_weight = reconciled.get_weight("work_type", "test")
        # HIGH confidence (3x multiplier) vs LOW (1x), so should be closer to 0.9
        assert test_weight > 0.7

    @pytest.mark.asyncio
    async def test_reconcile_single_entry(self, service):
        """Single contributor passes through unchanged."""
        all_weights = {
            "work_type": {
                "feature": [(0.8, ConfidenceLevel.MEDIUM, "goal-1")],
            },
        }

        reconciled = service._reconcile_weights(all_weights)
        assert reconciled.get_weight("work_type", "feature") == 0.8

    @pytest.mark.asyncio
    async def test_reconcile_preserves_highest_confidence(self, service):
        """Reconciled entry should have the highest confidence from contributors."""
        all_weights = {
            "work_type": {
                "test": [
                    (0.9, ConfidenceLevel.HIGH, "goal-1"),
                    (0.7, ConfidenceLevel.LOW, "goal-2"),
                ],
            },
        }

        reconciled = service._reconcile_weights(all_weights)
        confidence = reconciled.get_confidence("work_type", "test")
        assert confidence == ConfidenceLevel.HIGH

    @pytest.mark.asyncio
    async def test_reconcile_multiple_categories(self, service):
        """Reconciliation works across all four weight categories."""
        all_weights = {
            "work_type": {
                "test": [(0.9, ConfidenceLevel.HIGH, "g1")],
            },
            "lifecycle_stage": {
                "build": [(0.7, ConfidenceLevel.MEDIUM, "g1")],
            },
            "technical_domain": {
                "backend": [(0.8, ConfidenceLevel.HIGH, "g1")],
            },
            "cluster": {
                "cluster-x": [(0.6, ConfidenceLevel.LOW, "g1")],
            },
        }

        reconciled = service._reconcile_weights(all_weights)
        assert reconciled.get_weight("work_type", "test") == 0.9
        assert reconciled.get_weight("lifecycle_stage", "build") == 0.7
        assert reconciled.get_weight("technical_domain", "backend") == 0.8
        assert reconciled.get_weight("cluster", "cluster-x") == 0.6


# ============================================================================
# Profile Updates - New Goal
# ============================================================================


class TestUpdateForNewGoal:
    """Test profile update when a new goal arrives."""

    @pytest.mark.asyncio
    async def test_update_rebuilds_profile(
        self, service, expansion_goal, consolidation_goal
    ):
        # Start with expansion goal
        await service.construct_profile("project-001", [expansion_goal])

        # Add consolidation goal
        profile = await service.update_for_new_goal(
            "project-001", consolidation_goal, [expansion_goal]
        )

        assert len(profile.active_goal_ids) == 2
        # Profile should reflect both goals
        assert profile.weights.work_type_weights  # Should have weights

    @pytest.mark.asyncio
    async def test_update_increments_version_via_reconstruct(
        self, service, expansion_goal, consolidation_goal
    ):
        # New construction always starts at version 1
        profile = await service.update_for_new_goal(
            "project-001", consolidation_goal, [expansion_goal]
        )
        assert profile.version == 1  # Reconstruction starts fresh


# ============================================================================
# Profile Updates - Worker Feedback
# ============================================================================


class TestUpdateForWorkerFeedback:
    """Test profile update from worker feedback."""

    @pytest.mark.asyncio
    async def test_blocker_feedback_adds_rule(self, service_with_redis, expansion_goal):
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        profile = await service_with_redis.update_for_worker_feedback(
            "project-001",
            "blocker",
            {"blocking_item_id": "item-123", "worker_id": "compute-001"},
        )

        assert profile is not None
        blocker_rules = [
            r for r in profile.policy_rules
            if r.action_type == PolicyActionType.ELEVATE_PRIORITY
            and "blocker" in r.name.lower()
        ]
        assert len(blocker_rules) >= 1
        assert profile.version == 2

    @pytest.mark.asyncio
    async def test_complexity_feedback_adjusts_weight(
        self, service_with_redis, expansion_goal
    ):
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        # Manually add a cluster weight
        profile = await service_with_redis.get_profile("project-001")
        profile.weights.cluster_weights["cluster-pay"] = WeightedValue(
            weight=0.5,
            confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
        )

        updated = await service_with_redis.update_for_worker_feedback(
            "project-001",
            "complexity_increase",
            {"cluster_id": "cluster-pay", "worker_id": "compute-001"},
        )

        assert updated is not None
        new_weight = updated.weights.get_weight("cluster", "cluster-pay")
        assert new_weight == 0.6  # 0.5 + 0.1

    @pytest.mark.asyncio
    async def test_feedback_no_profile_returns_none(self, service):
        result = await service.update_for_worker_feedback(
            "project-nonexistent", "blocker", {}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_feedback_adds_trigger(self, service_with_redis, expansion_goal):
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        profile = await service_with_redis.update_for_worker_feedback(
            "project-001",
            "blocker",
            {"blocking_item_id": "item-123", "worker_id": "compute-001"},
        )

        feedback_triggers = [
            t for t in profile.triggers
            if t.trigger_type == ProfileTriggerType.WORKER_FEEDBACK
        ]
        assert len(feedback_triggers) == 1
        assert feedback_triggers[0].source_id == "compute-001"


# ============================================================================
# Profile Updates - Resource Change
# ============================================================================


class TestUpdateForResourceChange:
    """Test profile update from resource condition changes."""

    @pytest.mark.asyncio
    async def test_available_skills_adds_rules(
        self, service_with_redis, expansion_goal
    ):
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        profile = await service_with_redis.update_for_resource_change(
            "project-001",
            {"available_skills": ["security-reviewer", "debugger"], "source_id": "fleet"},
        )

        assert profile is not None
        resource_rules = [r for r in profile.policy_rules if "opportunistic" in r.name.lower()]
        assert len(resource_rules) == 2
        assert all(r.confidence.level == ConfidenceLevel.LOW for r in resource_rules)

    @pytest.mark.asyncio
    async def test_resource_change_no_profile_returns_none(self, service):
        result = await service.update_for_resource_change(
            "project-nonexistent", {"available_skills": ["test"]},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_resource_change_adds_trigger(
        self, service_with_redis, expansion_goal
    ):
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        profile = await service_with_redis.update_for_resource_change(
            "project-001",
            {"available_skills": ["debugger"], "source_id": "fleet-mgr"},
        )

        resource_triggers = [
            t for t in profile.triggers
            if t.trigger_type == ProfileTriggerType.RESOURCE_CHANGE
        ]
        assert len(resource_triggers) == 1


# ============================================================================
# Profile Updates - Goal Removed
# ============================================================================


class TestUpdateForGoalRemoved:
    """Test profile rebuild when a goal is removed."""

    @pytest.mark.asyncio
    async def test_remove_goal_rebuilds_from_remaining(
        self, service_with_redis, expansion_goal, consolidation_goal
    ):
        await service_with_redis.construct_profile(
            "project-001", [expansion_goal, consolidation_goal]
        )

        profile = await service_with_redis.update_for_goal_removed(
            "project-001",
            consolidation_goal.goal_id,
            [expansion_goal],
        )

        assert profile is not None
        assert expansion_goal.goal_id in profile.active_goal_ids
        assert consolidation_goal.goal_id not in profile.active_goal_ids

    @pytest.mark.asyncio
    async def test_remove_last_goal_deletes_profile(
        self, service_with_redis, expansion_goal
    ):
        service_with_redis._delete_profile_from_redis = AsyncMock()
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        result = await service_with_redis.update_for_goal_removed(
            "project-001", expansion_goal.goal_id, []
        )

        assert result is None
        assert "project-001" not in service_with_redis._profiles

    @pytest.mark.asyncio
    async def test_remove_goal_adds_trigger(
        self, service_with_redis, expansion_goal, consolidation_goal
    ):
        await service_with_redis.construct_profile(
            "project-001", [expansion_goal, consolidation_goal]
        )

        profile = await service_with_redis.update_for_goal_removed(
            "project-001",
            consolidation_goal.goal_id,
            [expansion_goal],
        )

        removal_triggers = [
            t for t in profile.triggers
            if t.trigger_type == ProfileTriggerType.GOAL_REMOVED
        ]
        assert len(removal_triggers) == 1
        assert removal_triggers[0].source_id == consolidation_goal.goal_id


# ============================================================================
# Profile Retrieval
# ============================================================================


class TestProfileRetrieval:
    """Test profile get and history operations."""

    @pytest.mark.asyncio
    async def test_get_profile_exists(self, service, expansion_goal):
        await service.construct_profile("project-001", [expansion_goal])

        profile = await service.get_profile("project-001")
        assert profile is not None
        assert profile.project_id == "project-001"

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, service):
        profile = await service.get_profile("project-nonexistent")
        assert profile is None

    @pytest.mark.asyncio
    async def test_get_history_no_redis(self, service):
        history = await service.get_profile_history("project-001")
        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_with_redis(self):
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = AsyncMock()

        # Create a profile to serialize
        profile = PlannerProfile(
            profile_id="profile-hist-001",
            project_id="project-001",
        )
        profile_json = profile.model_dump_json()

        mock_redis._redis.lrange = AsyncMock(return_value=[profile_json.encode()])

        svc = PlannerProfileService(redis_client=mock_redis)
        history = await svc.get_profile_history("project-001", limit=5)

        assert len(history) == 1
        assert history[0].profile_id == "profile-hist-001"
        mock_redis._redis.lrange.assert_called_once()


# ============================================================================
# Redis Persistence
# ============================================================================


class TestRedisPersistence:
    """Test Redis save/load operations."""

    @pytest.mark.asyncio
    async def test_save_and_load_profile(self):
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = AsyncMock()

        profile = PlannerProfile(
            profile_id="profile-redis-001",
            project_id="project-001",
            weights=ProfileWeights(
                work_type_weights={"test": WeightedValue(weight=0.9)},
            ),
        )

        svc = PlannerProfileService(redis_client=mock_redis)
        await svc._save_profile_to_redis(profile)

        mock_redis._redis.set.assert_called_once()
        call_args = mock_redis._redis.set.call_args
        key = call_args[0][0]
        data = call_args[0][1]
        assert "active:project-001" in key
        assert "profile-redis-001" in data

    @pytest.mark.asyncio
    async def test_save_history_pushes_to_list(self):
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = AsyncMock()

        profile = PlannerProfile(
            profile_id="profile-hist-001",
            project_id="project-001",
        )

        svc = PlannerProfileService(redis_client=mock_redis)
        await svc._save_profile_history(profile)

        mock_redis._redis.lpush.assert_called_once()
        mock_redis._redis.ltrim.assert_called_once()
        # ltrim keeps last 50 entries
        ltrim_args = mock_redis._redis.ltrim.call_args[0]
        assert ltrim_args[1] == 0
        assert ltrim_args[2] == 49

    @pytest.mark.asyncio
    async def test_delete_profile_from_redis(self):
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = AsyncMock()

        svc = PlannerProfileService(redis_client=mock_redis)
        await svc._delete_profile_from_redis("project-001")

        mock_redis._redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_profiles_on_init(self):
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = AsyncMock()

        profile = PlannerProfile(
            profile_id="profile-loaded-001",
            project_id="project-001",
        )
        profile_json = profile.model_dump_json()

        # Simulate scan returning one key, then done
        mock_redis._redis.scan = AsyncMock(
            return_value=(0, [b"claudevn:planner_profile:active:project-001"])
        )
        mock_redis._redis.get = AsyncMock(return_value=profile_json.encode())

        svc = PlannerProfileService(redis_client=mock_redis)
        await svc.initialize()

        assert svc._initialized is True
        loaded = await svc.get_profile("project-001")
        assert loaded is not None
        assert loaded.profile_id == "profile-loaded-001"

    @pytest.mark.asyncio
    async def test_initialize_without_redis(self, service):
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, service):
        await service.initialize()
        await service.initialize()
        assert service._initialized is True


# ============================================================================
# Global Instance Management
# ============================================================================


class TestGlobalInstance:
    """Test singleton pattern for global service instance."""

    def test_get_before_set_raises(self):
        set_planner_profile_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_planner_profile_service()

    def test_set_and_get(self):
        svc = PlannerProfileService()
        set_planner_profile_service(svc)
        assert get_planner_profile_service() is svc
        set_planner_profile_service(None)  # Cleanup

    def test_set_none_clears(self):
        svc = PlannerProfileService()
        set_planner_profile_service(svc)
        set_planner_profile_service(None)
        with pytest.raises(RuntimeError):
            get_planner_profile_service()


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_weight_clamped_to_range(self, service_with_redis, expansion_goal):
        """Cluster weight adjustment stays within 0.0-1.0."""
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        profile = await service_with_redis.get_profile("project-001")
        profile.weights.cluster_weights["cluster-max"] = WeightedValue(
            weight=0.95,
            confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
        )

        updated = await service_with_redis.update_for_worker_feedback(
            "project-001",
            "complexity_increase",
            {"cluster_id": "cluster-max", "worker_id": "w1"},
        )

        # Should be clamped to 1.0
        assert updated.weights.get_weight("cluster", "cluster-max") == 1.0

    @pytest.mark.asyncio
    async def test_feedback_unknown_type_no_crash(
        self, service_with_redis, expansion_goal
    ):
        """Unknown feedback type still adds trigger, doesn't crash."""
        await service_with_redis.construct_profile("project-001", [expansion_goal])

        profile = await service_with_redis.update_for_worker_feedback(
            "project-001", "unknown_type", {"worker_id": "w1"}
        )

        assert profile is not None
        assert profile.version == 2  # Still increments
        feedback_triggers = [
            t for t in profile.triggers
            if t.trigger_type == ProfileTriggerType.WORKER_FEEDBACK
        ]
        assert len(feedback_triggers) == 1

    @pytest.mark.asyncio
    async def test_resource_change_empty_skills(
        self, service_with_redis, expansion_goal
    ):
        """Empty available_skills list adds no rules."""
        await service_with_redis.construct_profile("project-001", [expansion_goal])
        original_rule_count = len(
            (await service_with_redis.get_profile("project-001")).policy_rules
        )

        profile = await service_with_redis.update_for_resource_change(
            "project-001", {"available_skills": [], "source_id": "fleet"},
        )

        # Same number of rules (only original ones, no new ones)
        assert len(profile.policy_rules) == original_rule_count

    @pytest.mark.asyncio
    async def test_construct_replaces_previous_profile(
        self, service, expansion_goal, consolidation_goal
    ):
        """Constructing a new profile replaces the old one for the same project."""
        profile1 = await service.construct_profile("project-001", [expansion_goal])
        profile2 = await service.construct_profile("project-001", [consolidation_goal])

        stored = await service.get_profile("project-001")
        assert stored.profile_id == profile2.profile_id
        assert stored.profile_id != profile1.profile_id
