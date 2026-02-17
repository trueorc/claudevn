"""Unit tests for PlannerFocusService.

Tests the focus summary generation and goal alignment calculation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

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
from models.work_map import Goal, GoalIntentType, GoalStatus, IssuePriority
from services.planner_focus_service import PlannerFocusService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    return PlannerFocusService()


@pytest.fixture
def sample_goal():
    return Goal(
        goal_id="goal_1",
        title="Build user authentication",
        description="Add login and signup",
        project_id="proj_1",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
        primary_intent=GoalIntentType.EXPANSION,
        intent_strength=0.8,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_goal_consolidation():
    return Goal(
        goal_id="goal_2",
        title="Harden test coverage",
        description="Improve stability and testing",
        project_id="proj_1",
        priority=IssuePriority.P0,
        status=GoalStatus.IN_PROGRESS,
        primary_intent=GoalIntentType.CONSOLIDATION,
        intent_strength=0.9,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_profile(sample_goal):
    return PlannerProfile(
        profile_id="profile_1",
        project_id="proj_1",
        weights=ProfileWeights(
            work_type_weights={
                "feature": WeightedValue(
                    weight=0.9,
                    confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
                ),
                "test": WeightedValue(
                    weight=0.4,
                    confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
                ),
                "refactor": WeightedValue(
                    weight=0.2,
                    confidence=ConfidenceBand(level=ConfidenceLevel.LOW),
                ),
            },
            lifecycle_stage_weights={
                "build": WeightedValue(
                    weight=0.9,
                    confidence=ConfidenceBand(level=ConfidenceLevel.HIGH),
                ),
                "design": WeightedValue(
                    weight=0.7,
                    confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
                ),
            },
        ),
        policy_rules=[
            PolicyRule(
                rule_id="rule_1",
                name="Defer refactoring during expansion",
                description="Deprioritize refactoring work",
                condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
                condition_params={"category": "work_type", "key": "refactor"},
                action_type=PolicyActionType.DEPRIORITIZE,
                action_params={"factor": 0.5},
                confidence=ConfidenceBand(level=ConfidenceLevel.LOW),
                source_goal_id="goal_1",
            ),
        ],
        active_goal_ids=["goal_1"],
        triggers=[
            ProfileTrigger(
                trigger_type=ProfileTriggerType.NEW_GOAL,
                source_id="goal_1",
                description="Profile constructed from goal: Build user authentication",
            ),
        ],
        version=1,
    )


@pytest.fixture
def sample_issues():
    return [
        {"issue_id": "iss_1", "title": "Login form", "status": "in_progress", "goal_id": "goal_1"},
        {"issue_id": "iss_2", "title": "Signup API", "status": "ready", "goal_id": "goal_1"},
        {"issue_id": "iss_3", "title": "Session middleware", "status": "done", "goal_id": "goal_1"},
        {"issue_id": "iss_4", "title": "Write auth tests", "status": "in_progress", "goal_id": "goal_2"},
        {"issue_id": "iss_5", "title": "Fix flaky test", "status": "blocked", "goal_id": "goal_2"},
        {"issue_id": "iss_6", "title": "Unrelated refactor", "status": "ready", "goal_id": None},
    ]


# =============================================================================
# Focus Summary Tests
# =============================================================================


class TestGetFocusSummary:
    """Tests for focus summary generation."""

    @pytest.mark.asyncio
    async def test_no_profile_returns_empty(self, service):
        result = await service.get_focus_summary("proj_1", None, [])
        assert result.project_id == "proj_1"
        assert result.has_profile is False
        assert "No active planner profile" in result.optimization_target

    @pytest.mark.asyncio
    async def test_no_profile_with_goals(self, service, sample_goal):
        result = await service.get_focus_summary("proj_1", None, [sample_goal])
        assert result.has_profile is False
        assert result.active_goal_count == 1

    @pytest.mark.asyncio
    async def test_with_profile(self, service, sample_profile, sample_goal):
        result = await service.get_focus_summary("proj_1", sample_profile, [sample_goal])
        assert result.has_profile is True
        assert result.project_id == "proj_1"
        assert result.primary_intent == "expansion"
        assert result.profile_version == 1
        assert result.active_goal_count == 1

    @pytest.mark.asyncio
    async def test_optimization_target_description(self, service, sample_profile, sample_goal):
        result = await service.get_focus_summary("proj_1", sample_profile, [sample_goal])
        assert "Building new features" in result.optimization_target
        assert "1 active goal" in result.optimization_target

    @pytest.mark.asyncio
    async def test_weight_categories(self, service, sample_profile, sample_goal):
        result = await service.get_focus_summary("proj_1", sample_profile, [sample_goal])
        assert len(result.weight_categories) >= 1
        work_type_cat = next(
            (c for c in result.weight_categories if c.category == "work_type"), None
        )
        assert work_type_cat is not None
        assert work_type_cat.label == "Work Type"
        assert len(work_type_cat.weights) == 3
        # Should be sorted by weight descending
        assert work_type_cat.weights[0].key == "feature"
        assert work_type_cat.weights[0].weight == 0.9

    @pytest.mark.asyncio
    async def test_lifecycle_weights_included(self, service, sample_profile, sample_goal):
        result = await service.get_focus_summary("proj_1", sample_profile, [sample_goal])
        lifecycle_cat = next(
            (c for c in result.weight_categories if c.category == "lifecycle_stage"), None
        )
        assert lifecycle_cat is not None
        assert len(lifecycle_cat.weights) == 2

    @pytest.mark.asyncio
    async def test_policy_rules_included(self, service, sample_profile, sample_goal):
        result = await service.get_focus_summary("proj_1", sample_profile, [sample_goal])
        assert len(result.active_rules) == 1
        rule = result.active_rules[0]
        assert rule.name == "Defer refactoring during expansion"
        assert rule.action == "Deprioritize"
        assert rule.source_goal_title == "Build user authentication"

    @pytest.mark.asyncio
    async def test_last_trigger(self, service, sample_profile, sample_goal):
        result = await service.get_focus_summary("proj_1", sample_profile, [sample_goal])
        assert result.last_trigger is not None
        assert "Build user authentication" in result.last_trigger

    @pytest.mark.asyncio
    async def test_empty_weights_profile(self, service, sample_goal):
        empty_profile = PlannerProfile(
            profile_id="profile_empty",
            project_id="proj_1",
            active_goal_ids=["goal_1"],
            version=1,
        )
        result = await service.get_focus_summary("proj_1", empty_profile, [sample_goal])
        assert result.has_profile is True
        assert len(result.weight_categories) == 0


class TestDominantIntent:
    """Tests for dominant intent detection."""

    def test_single_intent(self, service):
        goals = [MagicMock(primary_intent=GoalIntentType.EXPANSION)]
        result = service._determine_dominant_intent(goals)
        assert result == "expansion"

    def test_multiple_same_intent(self, service):
        goals = [
            MagicMock(primary_intent=GoalIntentType.CONSOLIDATION),
            MagicMock(primary_intent=GoalIntentType.CONSOLIDATION),
        ]
        result = service._determine_dominant_intent(goals)
        assert result == "consolidation"

    def test_no_intents(self, service):
        goals = [MagicMock(primary_intent=None)]
        result = service._determine_dominant_intent(goals)
        assert result is None

    def test_mixed_intents_most_common_wins(self, service):
        goals = [
            MagicMock(primary_intent=GoalIntentType.EXPANSION),
            MagicMock(primary_intent=GoalIntentType.EXPANSION),
            MagicMock(primary_intent=GoalIntentType.CONSOLIDATION),
        ]
        result = service._determine_dominant_intent(goals)
        assert result == "expansion"


# =============================================================================
# Goal Alignment Tests
# =============================================================================


class TestGetGoalAlignment:
    """Tests for goal alignment calculation."""

    @pytest.mark.asyncio
    async def test_empty_goals_and_issues(self, service):
        result = await service.get_goal_alignment("proj_1", [], [])
        assert result.project_id == "proj_1"
        assert result.total_goals == 0
        assert result.total_issues == 0
        assert result.overall_alignment == 0.0

    @pytest.mark.asyncio
    async def test_alignment_with_data(
        self, service, sample_goal, sample_goal_consolidation, sample_issues
    ):
        result = await service.get_goal_alignment(
            "proj_1",
            [sample_goal, sample_goal_consolidation],
            sample_issues,
        )
        assert result.total_goals == 2
        assert result.total_issues == 6
        assert result.unaligned_issue_count == 1  # iss_6 has no goal_id

    @pytest.mark.asyncio
    async def test_alignment_percentages(
        self, service, sample_goal, sample_goal_consolidation, sample_issues
    ):
        result = await service.get_goal_alignment(
            "proj_1",
            [sample_goal, sample_goal_consolidation],
            sample_issues,
        )
        # Total active: iss_1 (in_progress), iss_2 (ready), iss_4 (in_progress), iss_6 (ready) = 4
        # goal_1 active: iss_1, iss_2 = 2 → 50%
        # goal_2 active: iss_4 = 1 → 25%
        goal_1_entry = next(e for e in result.goals if e.goal_id == "goal_1")
        goal_2_entry = next(e for e in result.goals if e.goal_id == "goal_2")
        assert goal_1_entry.alignment_percentage == 50.0
        assert goal_2_entry.alignment_percentage == 25.0

    @pytest.mark.asyncio
    async def test_completed_count(
        self, service, sample_goal, sample_issues
    ):
        result = await service.get_goal_alignment(
            "proj_1",
            [sample_goal],
            sample_issues,
        )
        goal_1_entry = next(e for e in result.goals if e.goal_id == "goal_1")
        assert goal_1_entry.completed_issues == 1  # iss_3
        assert goal_1_entry.total_issues == 3

    @pytest.mark.asyncio
    async def test_gap_detection_no_active_work(self, service):
        goal = Goal(
            goal_id="goal_gap",
            title="Blocked goal",
            description="All work blocked",
            priority=IssuePriority.P2,
            status=GoalStatus.IN_PROGRESS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        issues = [
            {"issue_id": "iss_a", "title": "Blocked item", "status": "blocked", "goal_id": "goal_gap"},
        ]
        result = await service.get_goal_alignment("proj_1", [goal], issues)
        entry = result.goals[0]
        assert entry.has_gaps is True
        assert "blocked" in entry.gap_description.lower()

    @pytest.mark.asyncio
    async def test_gap_detection_no_issues(self, service):
        goal = Goal(
            goal_id="goal_empty",
            title="Empty goal",
            description="No issues yet",
            priority=IssuePriority.P2,
            status=GoalStatus.IN_PROGRESS,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        result = await service.get_goal_alignment("proj_1", [goal], [])
        entry = result.goals[0]
        assert entry.has_gaps is True
        assert "No issues created" in entry.gap_description

    @pytest.mark.asyncio
    async def test_conflict_indicators(
        self, service, sample_goal, sample_goal_consolidation, sample_issues
    ):
        conflicts = [
            {"goal_id_a": "goal_1", "goal_id_b": "goal_2"},
        ]
        result = await service.get_goal_alignment(
            "proj_1",
            [sample_goal, sample_goal_consolidation],
            sample_issues,
            conflicts=conflicts,
        )
        goal_1_entry = next(e for e in result.goals if e.goal_id == "goal_1")
        goal_2_entry = next(e for e in result.goals if e.goal_id == "goal_2")
        assert goal_1_entry.has_conflicts is True
        assert "goal_2" in goal_1_entry.competing_goal_ids
        assert goal_2_entry.has_conflicts is True
        assert "goal_1" in goal_2_entry.competing_goal_ids

    @pytest.mark.asyncio
    async def test_no_conflicts(
        self, service, sample_goal, sample_issues
    ):
        result = await service.get_goal_alignment(
            "proj_1", [sample_goal], sample_issues
        )
        entry = result.goals[0]
        assert entry.has_conflicts is False
        assert entry.competing_goal_ids == []

    @pytest.mark.asyncio
    async def test_overall_alignment_percentage(
        self, service, sample_goal, sample_issues
    ):
        # 5 out of 6 issues have a goal_id
        result = await service.get_goal_alignment(
            "proj_1", [sample_goal], sample_issues
        )
        # 5/6 = 83.3%
        assert result.overall_alignment == 83.3

    @pytest.mark.asyncio
    async def test_goal_metadata_in_entries(
        self, service, sample_goal, sample_issues
    ):
        result = await service.get_goal_alignment(
            "proj_1", [sample_goal], sample_issues
        )
        entry = result.goals[0]
        assert entry.goal_title == "Build user authentication"
        assert entry.goal_status == "in_progress"
        assert entry.goal_priority == "P1"
        assert entry.primary_intent == "expansion"


# =============================================================================
# Weight Category Building Tests
# =============================================================================


class TestBuildWeightCategories:
    """Tests for weight category construction."""

    def test_empty_profile(self, service):
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj_1",
        )
        categories = service._build_weight_categories(profile)
        assert categories == []

    def test_sorts_by_weight_descending(self, service):
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj_1",
            weights=ProfileWeights(
                work_type_weights={
                    "test": WeightedValue(weight=0.3, confidence=ConfidenceBand()),
                    "feature": WeightedValue(weight=0.9, confidence=ConfidenceBand()),
                    "refactor": WeightedValue(weight=0.5, confidence=ConfidenceBand()),
                },
            ),
        )
        categories = service._build_weight_categories(profile)
        assert len(categories) == 1
        weights = categories[0].weights
        assert weights[0].key == "feature"
        assert weights[1].key == "refactor"
        assert weights[2].key == "test"

    def test_cluster_weights_included(self, service):
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj_1",
            weights=ProfileWeights(
                cluster_weights={
                    "auth_cluster": WeightedValue(weight=0.8, confidence=ConfidenceBand()),
                },
            ),
        )
        categories = service._build_weight_categories(profile)
        cluster_cat = next(
            (c for c in categories if c.category == "cluster"), None
        )
        assert cluster_cat is not None
        assert cluster_cat.label == "Domain Clusters"
        assert len(cluster_cat.weights) == 1


# =============================================================================
# Rule Summary Tests
# =============================================================================


class TestBuildRuleSummaries:
    """Tests for policy rule summary building."""

    def test_disabled_rules_excluded(self, service):
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj_1",
            policy_rules=[
                PolicyRule(
                    rule_id="r1",
                    name="Disabled rule",
                    condition_type=PolicyConditionType.CUSTOM,
                    action_type=PolicyActionType.SKIP,
                    enabled=False,
                ),
            ],
        )
        summaries = service._build_rule_summaries(profile, {})
        assert len(summaries) == 0

    def test_goal_title_resolved(self, service, sample_goal):
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj_1",
            policy_rules=[
                PolicyRule(
                    rule_id="r1",
                    name="Test rule",
                    condition_type=PolicyConditionType.CUSTOM,
                    action_type=PolicyActionType.ELEVATE_PRIORITY,
                    source_goal_id="goal_1",
                ),
            ],
        )
        lookup = {"goal_1": sample_goal}
        summaries = service._build_rule_summaries(profile, lookup)
        assert len(summaries) == 1
        assert summaries[0].source_goal_title == "Build user authentication"

    def test_action_label_mapped(self, service):
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj_1",
            policy_rules=[
                PolicyRule(
                    rule_id="r1",
                    name="Test",
                    condition_type=PolicyConditionType.CUSTOM,
                    action_type=PolicyActionType.ELEVATE_PRIORITY,
                ),
            ],
        )
        summaries = service._build_rule_summaries(profile, {})
        assert summaries[0].action == "Elevate priority"
