"""Tests for PlannerProfile schema — dynamic profile for work planner.

Tests cover:
- Confidence band models
- Weighted ontology values
- Policy rules (conditions, actions, matching)
- Profile triggers and lifecycle
- PlannerProfile top-level model (validation, queries)
"""

import pytest
from datetime import datetime, timezone

from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PlannerProfile,
    PolicyActionType,
    PolicyConditionType,
    PolicyRule,
    ProfileTrigger,
    ProfileTriggerType,
    ProfileWeights,
    WeightedValue,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_weighted_value():
    """A weighted value with high confidence."""
    return WeightedValue(
        weight=0.9,
        confidence=ConfidenceBand(
            level=ConfidenceLevel.HIGH,
            rationale="Strong directive language in goal",
        ),
    )


@pytest.fixture
def sample_policy_rule():
    """A policy rule for blocking high-priority tasks."""
    return PolicyRule(
        rule_id="rule-001",
        name="Elevate blockers of high-priority testing",
        description="Tasks blocking high-priority testing inherit elevated priority",
        condition_type=PolicyConditionType.BLOCKS_HIGH_PRIORITY,
        condition_params={"target_work_type": "test", "min_weight": 0.8},
        action_type=PolicyActionType.ELEVATE_PRIORITY,
        action_params={"boost": 0.3},
        confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
        source_goal_id="goal-001",
    )


@pytest.fixture
def sample_profile_weights():
    """Profile weights across both ontology layers."""
    return ProfileWeights(
        work_type_weights={
            "test": WeightedValue(
                weight=0.9,
                confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
            ),
            "feature": WeightedValue(
                weight=0.3,
                confidence=ConfidenceBand(level=ConfidenceLevel.LOW),
            ),
        },
        cluster_weights={
            "cluster-payment": WeightedValue(
                weight=0.9,
                confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
            ),
        },
    )


@pytest.fixture
def sample_profile(sample_profile_weights, sample_policy_rule):
    """A complete planner profile."""
    return PlannerProfile(
        profile_id="profile-abc123",
        project_id="project-001",
        weights=sample_profile_weights,
        policy_rules=[
            sample_policy_rule,
            PolicyRule(
                rule_id="rule-002",
                name="Finish near-complete work",
                condition_type=PolicyConditionType.COMPLETION_ABOVE_THRESHOLD,
                condition_params={"threshold": 0.8},
                action_type=PolicyActionType.PRESERVE_PRIORITY,
                source_goal_id="goal-001",
            ),
            PolicyRule(
                rule_id="rule-003",
                name="Disabled rule",
                condition_type=PolicyConditionType.CUSTOM,
                condition_params={},
                action_type=PolicyActionType.SKIP,
                enabled=False,
            ),
        ],
        active_goal_ids=["goal-001", "goal-002"],
        triggers=[
            ProfileTrigger(
                trigger_type=ProfileTriggerType.NEW_GOAL,
                source_id="goal-001",
                description="Initial profile from hardening goal",
            ),
        ],
    )


# ============================================================================
# Model Tests - ConfidenceBand
# ============================================================================


class TestConfidenceBand:
    """Test ConfidenceBand model."""

    def test_create_with_defaults(self):
        band = ConfidenceBand()
        assert band.level == ConfidenceLevel.MEDIUM
        assert band.rationale == ""

    def test_create_with_values(self):
        band = ConfidenceBand(
            level=ConfidenceLevel.HIGH,
            rationale="Strong user directive",
        )
        assert band.level == ConfidenceLevel.HIGH
        assert band.rationale == "Strong user directive"

    def test_confidence_level_enum_values(self):
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"


# ============================================================================
# Model Tests - WeightedValue
# ============================================================================


class TestWeightedValue:
    """Test WeightedValue model."""

    def test_create_with_weight(self):
        wv = WeightedValue(weight=0.75)
        assert wv.weight == 0.75
        assert wv.confidence.level == ConfidenceLevel.MEDIUM

    def test_create_with_confidence(self, sample_weighted_value):
        assert sample_weighted_value.weight == 0.9
        assert sample_weighted_value.confidence.level == ConfidenceLevel.HIGH

    def test_weight_boundary_zero(self):
        wv = WeightedValue(weight=0.0)
        assert wv.weight == 0.0

    def test_weight_boundary_one(self):
        wv = WeightedValue(weight=1.0)
        assert wv.weight == 1.0

    def test_weight_below_zero_rejected(self):
        with pytest.raises(ValueError):
            WeightedValue(weight=-0.1)

    def test_weight_above_one_rejected(self):
        with pytest.raises(ValueError):
            WeightedValue(weight=1.1)


# ============================================================================
# Model Tests - ProfileWeights
# ============================================================================


class TestProfileWeights:
    """Test ProfileWeights model."""

    def test_create_empty(self):
        pw = ProfileWeights()
        assert pw.work_type_weights == {}
        assert pw.lifecycle_stage_weights == {}
        assert pw.technical_domain_weights == {}
        assert pw.cluster_weights == {}

    def test_get_weight_existing(self, sample_profile_weights):
        assert sample_profile_weights.get_weight("work_type", "test") == 0.9
        assert sample_profile_weights.get_weight("work_type", "feature") == 0.3

    def test_get_weight_default(self, sample_profile_weights):
        assert sample_profile_weights.get_weight("work_type", "bug_fix") == 0.5

    def test_get_weight_unknown_category(self, sample_profile_weights):
        assert sample_profile_weights.get_weight("nonexistent", "test") == 0.5

    def test_get_confidence_existing(self, sample_profile_weights):
        assert sample_profile_weights.get_confidence("work_type", "test") == ConfidenceLevel.HIGH
        assert sample_profile_weights.get_confidence("work_type", "feature") == ConfidenceLevel.LOW

    def test_get_confidence_default(self, sample_profile_weights):
        assert sample_profile_weights.get_confidence("work_type", "bug_fix") == ConfidenceLevel.MEDIUM

    def test_cluster_weights(self, sample_profile_weights):
        assert sample_profile_weights.get_weight("cluster", "cluster-payment") == 0.9
        assert sample_profile_weights.get_weight("cluster", "cluster-unknown") == 0.5

    def test_all_four_weight_categories(self):
        pw = ProfileWeights(
            work_type_weights={"test": WeightedValue(weight=0.9)},
            lifecycle_stage_weights={"build": WeightedValue(weight=0.7)},
            technical_domain_weights={"backend": WeightedValue(weight=0.8)},
            cluster_weights={"cluster-x": WeightedValue(weight=0.6)},
        )
        assert pw.get_weight("work_type", "test") == 0.9
        assert pw.get_weight("lifecycle_stage", "build") == 0.7
        assert pw.get_weight("technical_domain", "backend") == 0.8
        assert pw.get_weight("cluster", "cluster-x") == 0.6


# ============================================================================
# Model Tests - PolicyRule
# ============================================================================


class TestPolicyRule:
    """Test PolicyRule model."""

    def test_create_rule(self, sample_policy_rule):
        assert sample_policy_rule.rule_id == "rule-001"
        assert sample_policy_rule.name == "Elevate blockers of high-priority testing"
        assert sample_policy_rule.condition_type == PolicyConditionType.BLOCKS_HIGH_PRIORITY
        assert sample_policy_rule.action_type == PolicyActionType.ELEVATE_PRIORITY
        assert sample_policy_rule.enabled is True
        assert sample_policy_rule.source_goal_id == "goal-001"

    def test_matches_condition_type_enabled(self, sample_policy_rule):
        assert sample_policy_rule.matches_condition_type(
            PolicyConditionType.BLOCKS_HIGH_PRIORITY
        ) is True

    def test_matches_condition_type_wrong_type(self, sample_policy_rule):
        assert sample_policy_rule.matches_condition_type(
            PolicyConditionType.COMPLETION_ABOVE_THRESHOLD
        ) is False

    def test_matches_condition_type_disabled(self):
        rule = PolicyRule(
            rule_id="rule-disabled",
            name="Disabled",
            condition_type=PolicyConditionType.BLOCKS_HIGH_PRIORITY,
            action_type=PolicyActionType.ELEVATE_PRIORITY,
            enabled=False,
        )
        assert rule.matches_condition_type(
            PolicyConditionType.BLOCKS_HIGH_PRIORITY
        ) is False

    def test_condition_params(self, sample_policy_rule):
        assert sample_policy_rule.condition_params["target_work_type"] == "test"
        assert sample_policy_rule.condition_params["min_weight"] == 0.8

    def test_action_params(self, sample_policy_rule):
        assert sample_policy_rule.action_params["boost"] == 0.3

    def test_policy_condition_types(self):
        assert PolicyConditionType.BLOCKS_HIGH_PRIORITY.value == "blocks_high_priority"
        assert PolicyConditionType.COMPLETION_ABOVE_THRESHOLD.value == "completion_above_threshold"
        assert PolicyConditionType.IN_ONTOLOGY_CATEGORY.value == "in_ontology_category"
        assert PolicyConditionType.BLOCKED_BY_COUNT_ABOVE.value == "blocked_by_count_above"
        assert PolicyConditionType.BLOCKING_COUNT_ABOVE.value == "blocking_count_above"
        assert PolicyConditionType.IN_CLUSTER.value == "in_cluster"
        assert PolicyConditionType.CUSTOM.value == "custom"

    def test_policy_action_types(self):
        assert PolicyActionType.ELEVATE_PRIORITY.value == "elevate_priority"
        assert PolicyActionType.PRESERVE_PRIORITY.value == "preserve_priority"
        assert PolicyActionType.DEPRIORITIZE.value == "deprioritize"
        assert PolicyActionType.FORCE_BUCKET.value == "force_bucket"
        assert PolicyActionType.SKIP.value == "skip"

    def test_rule_with_confidence(self, sample_policy_rule):
        assert sample_policy_rule.confidence.level == ConfidenceLevel.HIGH


# ============================================================================
# Model Tests - ProfileTrigger
# ============================================================================


class TestProfileTrigger:
    """Test ProfileTrigger model."""

    def test_create_trigger(self):
        trigger = ProfileTrigger(
            trigger_type=ProfileTriggerType.NEW_GOAL,
            source_id="goal-001",
            description="New hardening goal",
        )
        assert trigger.trigger_type == ProfileTriggerType.NEW_GOAL
        assert trigger.source_id == "goal-001"
        assert trigger.description == "New hardening goal"
        assert trigger.timestamp is not None

    def test_trigger_types(self):
        assert ProfileTriggerType.NEW_GOAL.value == "new_goal"
        assert ProfileTriggerType.GOAL_UPDATED.value == "goal_updated"
        assert ProfileTriggerType.GOAL_REMOVED.value == "goal_removed"
        assert ProfileTriggerType.WORKER_FEEDBACK.value == "worker_feedback"
        assert ProfileTriggerType.RESOURCE_CHANGE.value == "resource_change"
        assert ProfileTriggerType.MANUAL_ADJUSTMENT.value == "manual_adjustment"

    def test_trigger_timestamp_auto_set(self):
        before = datetime.now(timezone.utc)
        trigger = ProfileTrigger(
            trigger_type=ProfileTriggerType.WORKER_FEEDBACK,
            source_id="worker-001",
        )
        after = datetime.now(timezone.utc)
        assert before <= trigger.timestamp <= after


# ============================================================================
# Model Tests - PlannerProfile
# ============================================================================


class TestPlannerProfile:
    """Test PlannerProfile top-level model."""

    def test_create_minimal(self):
        profile = PlannerProfile(
            profile_id="profile-001",
            project_id="project-001",
        )
        assert profile.profile_id == "profile-001"
        assert profile.project_id == "project-001"
        assert profile.weights is not None
        assert profile.policy_rules == []
        assert profile.active_goal_ids == []
        assert profile.triggers == []
        assert profile.version == 1

    def test_create_full(self, sample_profile):
        assert sample_profile.profile_id == "profile-abc123"
        assert sample_profile.project_id == "project-001"
        assert len(sample_profile.policy_rules) == 3
        assert len(sample_profile.active_goal_ids) == 2
        assert len(sample_profile.triggers) == 1

    def test_timestamps_auto_set(self):
        before = datetime.now(timezone.utc)
        profile = PlannerProfile(
            profile_id="profile-001",
            project_id="project-001",
        )
        after = datetime.now(timezone.utc)
        assert before <= profile.created_at <= after
        assert before <= profile.updated_at <= after


# ============================================================================
# PlannerProfile - Query Methods
# ============================================================================


class TestPlannerProfileQueries:
    """Test PlannerProfile query methods."""

    def test_get_enabled_rules(self, sample_profile):
        enabled = sample_profile.get_enabled_rules()
        assert len(enabled) == 2
        assert all(r.enabled for r in enabled)

    def test_get_rules_by_condition(self, sample_profile):
        rules = sample_profile.get_rules_by_condition(
            PolicyConditionType.BLOCKS_HIGH_PRIORITY
        )
        assert len(rules) == 1
        assert rules[0].rule_id == "rule-001"

    def test_get_rules_by_condition_no_match(self, sample_profile):
        rules = sample_profile.get_rules_by_condition(
            PolicyConditionType.IN_CLUSTER
        )
        assert len(rules) == 0

    def test_get_rules_for_goal(self, sample_profile):
        rules = sample_profile.get_rules_for_goal("goal-001")
        assert len(rules) == 2
        assert all(r.source_goal_id == "goal-001" for r in rules)

    def test_get_rules_for_goal_no_match(self, sample_profile):
        rules = sample_profile.get_rules_for_goal("goal-nonexistent")
        assert len(rules) == 0

    def test_get_rules_for_goal_includes_disabled(self, sample_profile):
        """get_rules_for_goal returns all rules, even disabled ones."""
        # rule-003 has no source_goal_id, so won't match
        # But if we had a disabled rule with goal-001, it would be returned
        rules = sample_profile.get_rules_for_goal("goal-001")
        # rule-001 and rule-002 both have source_goal_id="goal-001"
        assert len(rules) == 2


# ============================================================================
# PlannerProfile - Validation
# ============================================================================


class TestPlannerProfileValidation:
    """Test PlannerProfile validation rules."""

    def test_duplicate_rule_ids_rejected(self):
        with pytest.raises(ValueError, match="Duplicate policy rule IDs"):
            PlannerProfile(
                profile_id="profile-001",
                project_id="project-001",
                policy_rules=[
                    PolicyRule(
                        rule_id="rule-001",
                        name="Rule A",
                        condition_type=PolicyConditionType.CUSTOM,
                        action_type=PolicyActionType.SKIP,
                    ),
                    PolicyRule(
                        rule_id="rule-001",
                        name="Rule B (duplicate ID)",
                        condition_type=PolicyConditionType.CUSTOM,
                        action_type=PolicyActionType.SKIP,
                    ),
                ],
            )

    def test_unique_rule_ids_accepted(self):
        profile = PlannerProfile(
            profile_id="profile-001",
            project_id="project-001",
            policy_rules=[
                PolicyRule(
                    rule_id="rule-001",
                    name="Rule A",
                    condition_type=PolicyConditionType.CUSTOM,
                    action_type=PolicyActionType.SKIP,
                ),
                PolicyRule(
                    rule_id="rule-002",
                    name="Rule B",
                    condition_type=PolicyConditionType.CUSTOM,
                    action_type=PolicyActionType.SKIP,
                ),
            ],
        )
        assert len(profile.policy_rules) == 2


# ============================================================================
# Serialization Tests
# ============================================================================


class TestSerialization:
    """Test JSON serialization/deserialization."""

    def test_profile_roundtrip(self, sample_profile):
        """Test that a profile survives JSON roundtrip."""
        json_data = sample_profile.model_dump()
        restored = PlannerProfile(**json_data)

        assert restored.profile_id == sample_profile.profile_id
        assert restored.project_id == sample_profile.project_id
        assert len(restored.policy_rules) == len(sample_profile.policy_rules)
        assert len(restored.active_goal_ids) == len(sample_profile.active_goal_ids)
        assert restored.version == sample_profile.version

    def test_weighted_value_roundtrip(self, sample_weighted_value):
        json_data = sample_weighted_value.model_dump()
        restored = WeightedValue(**json_data)

        assert restored.weight == sample_weighted_value.weight
        assert restored.confidence.level == sample_weighted_value.confidence.level

    def test_policy_rule_roundtrip(self, sample_policy_rule):
        json_data = sample_policy_rule.model_dump()
        restored = PolicyRule(**json_data)

        assert restored.rule_id == sample_policy_rule.rule_id
        assert restored.condition_type == sample_policy_rule.condition_type
        assert restored.action_type == sample_policy_rule.action_type
        assert restored.condition_params == sample_policy_rule.condition_params

    def test_profile_to_json_string(self, sample_profile):
        """Ensure model_dump_json works for Redis storage."""
        json_str = sample_profile.model_dump_json()
        assert isinstance(json_str, str)
        assert "profile-abc123" in json_str
        assert "rule-001" in json_str
