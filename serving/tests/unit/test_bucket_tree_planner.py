"""Unit tests for WorkPlannerService bucket tree planning (v1.0).

Tests the new bucket tree planning mode that replaces phase-based planning
with priority bucket groupings driven by planner profiles and characterization.
"""

import pytest
from typing import Dict, List

from models.characterization import (
    BusinessMeaning,
    CharacterizationResult,
    CharacterizationStatus,
    ContextualMeaning,
    ContextualRole,
    MeaningAssessment,
    TechnicalMeaning,
)
from models.goal_decomposer import (
    DecomposedIssue,
    EstimatedComplexity,
)
from models.ontology import (
    LifecycleStage,
    OntologyTags,
    ProjectSpecificTags,
    TechnicalDomain,
    UniversalTags,
    WorkType,
)
from models.planner_profile import (
    ConfidenceBand,
    PlannerProfile,
    PolicyActionType,
    PolicyConditionType,
    PolicyRule,
    ProfileWeights,
    WeightedValue,
)
from models.priority_bucket import (
    BucketCriterion,
    BucketCriterionType,
    BucketItem,
    ItemReadiness,
)
from services.work_planner import (
    CyclicDependencyError,
    WorkPlannerService,
)


# =============================================================================
# Helpers
# =============================================================================


def make_issue(temp_id, title="Task", issue_type="feature", blocked_by=None, **kw):
    return DecomposedIssue(
        temp_id=temp_id,
        title=title,
        description=kw.get("description", f"Description for {temp_id}"),
        issue_type=issue_type,
        priority=kw.get("priority", "P2"),
        area=kw.get("area", "backend"),
        required_skills=kw.get("required_skills", []),
        estimated_complexity=kw.get("complexity", EstimatedComplexity.M),
        blocked_by=blocked_by or [],
        acceptance_criteria=[],
    )


def make_ontology_tags(
    work_type=WorkType.FEATURE,
    lifecycle_stage=LifecycleStage.BUILD,
    domains=None,
    cluster_ids=None,
):
    return OntologyTags(
        universal=UniversalTags(
            work_type=work_type,
            lifecycle_stage=lifecycle_stage,
            technical_domains=domains or [TechnicalDomain.BACKEND],
        ),
        project_specific=ProjectSpecificTags(
            cluster_ids=cluster_ids or [],
        ),
    )


def make_meaning():
    return MeaningAssessment(
        business=BusinessMeaning(summary="Adds value"),
        technical=TechnicalMeaning(summary="Implements feature"),
        contextual=ContextualMeaning(
            summary="Core work",
            role=ContextualRole.INCREMENTAL,
        ),
    )


def make_char_result(
    item_id, project_id="proj-1",
    work_type=WorkType.FEATURE,
    lifecycle_stage=LifecycleStage.BUILD,
    domains=None,
    cluster_ids=None,
):
    return CharacterizationResult(
        item_id=item_id,
        project_id=project_id,
        ontology_tags=make_ontology_tags(work_type, lifecycle_stage, domains, cluster_ids),
        meaning=make_meaning(),
        status=CharacterizationStatus.COMPLETED,
        confidence=0.85,
    )


def make_profile(
    profile_id="profile-001",
    project_id="proj-1",
    work_type_weights=None,
    lifecycle_stage_weights=None,
    technical_domain_weights=None,
    cluster_weights=None,
    policy_rules=None,
):
    weights = ProfileWeights(
        work_type_weights=work_type_weights or {},
        lifecycle_stage_weights=lifecycle_stage_weights or {},
        technical_domain_weights=technical_domain_weights or {},
        cluster_weights=cluster_weights or {},
    )
    return PlannerProfile(
        profile_id=profile_id,
        project_id=project_id,
        weights=weights,
        policy_rules=policy_rules or [],
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    return WorkPlannerService()


@pytest.fixture
def simple_items():
    """Three independent items, no dependencies."""
    return [
        make_issue("item-1", "Set up database", issue_type="feature"),
        make_issue("item-2", "Write tests", issue_type="test"),
        make_issue("item-3", "Update docs", issue_type="documentation"),
    ]


@pytest.fixture
def dependent_items():
    """Items with a dependency chain: item-1 → item-2 → item-3."""
    return [
        make_issue("item-1", "Schema design", blocked_by=[]),
        make_issue("item-2", "API endpoints", blocked_by=["item-1"]),
        make_issue("item-3", "Integration tests", blocked_by=["item-2"]),
    ]


@pytest.fixture
def simple_characterizations():
    """Characterizations for simple_items."""
    return {
        "item-1": make_char_result("item-1", work_type=WorkType.FEATURE),
        "item-2": make_char_result("item-2", work_type=WorkType.TEST),
        "item-3": make_char_result("item-3", work_type=WorkType.DOCUMENTATION),
    }


@pytest.fixture
def dependent_characterizations():
    """Characterizations for dependent_items."""
    return {
        "item-1": make_char_result("item-1", work_type=WorkType.FEATURE),
        "item-2": make_char_result("item-2", work_type=WorkType.FEATURE),
        "item-3": make_char_result("item-3", work_type=WorkType.TEST),
    }


@pytest.fixture
def default_profile():
    """Profile with no special weights (all defaults)."""
    return make_profile()


@pytest.fixture
def weighted_profile():
    """Profile with high weights on testing and build lifecycle."""
    return make_profile(
        work_type_weights={
            "test": WeightedValue(weight=0.9),
            "feature": WeightedValue(weight=0.5),
            "documentation": WeightedValue(weight=0.3),
        },
        lifecycle_stage_weights={
            "build": WeightedValue(weight=0.8),
            "validate": WeightedValue(weight=0.7),
        },
    )


# =============================================================================
# create_bucket_tree Tests
# =============================================================================


class TestCreateBucketTree:
    @pytest.mark.asyncio
    async def test_returns_bucket_tree(
        self, service, simple_items, simple_characterizations, default_profile
    ):
        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=simple_items,
            characterizations=simple_characterizations,
            dependency_graph={},
        )

        assert tree.tree_id.startswith("tree-")
        assert tree.project_id == "proj-1"
        assert tree.profile_id == "profile-001"
        assert tree.total_items == 3

    @pytest.mark.asyncio
    async def test_all_items_placed(
        self, service, simple_items, simple_characterizations, default_profile
    ):
        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=simple_items,
            characterizations=simple_characterizations,
            dependency_graph={},
        )

        # All 3 items should be placed somewhere
        assert tree.total_items == 3

    @pytest.mark.asyncio
    async def test_detects_cycles(
        self, service, simple_characterizations, default_profile
    ):
        cyclic_items = [
            make_issue("a", blocked_by=["b"]),
            make_issue("b", blocked_by=["a"]),
        ]
        with pytest.raises(CyclicDependencyError):
            await service.create_bucket_tree(
                project_id="proj-1",
                profile=default_profile,
                items=cyclic_items,
                characterizations={},
                dependency_graph={"a": ["b"], "b": ["a"]},
            )

    @pytest.mark.asyncio
    async def test_empty_items(self, service, default_profile):
        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=[],
            characterizations={},
            dependency_graph={},
        )

        assert tree.total_items == 0

    @pytest.mark.asyncio
    async def test_items_sorted_within_buckets(
        self, service, dependent_items, dependent_characterizations, default_profile
    ):
        dep_graph = {
            "item-2": ["item-1"],
            "item-3": ["item-2"],
        }
        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=dependent_items,
            characterizations=dependent_characterizations,
            dependency_graph=dep_graph,
        )

        # Items should be sorted by readiness
        queue = tree.get_assignment_queue()
        if queue:
            # First ready item should be item-1 (no deps)
            assert queue[0].item_id == "item-1"


# =============================================================================
# _define_buckets_from_profile Tests
# =============================================================================


class TestDefineBucketsFromProfile:
    def test_default_profile_creates_default_bucket(self, service, default_profile):
        buckets = service._define_buckets_from_profile(default_profile)

        # Should have at least a default catch-all bucket
        assert len(buckets) >= 1
        default_buckets = [b for b in buckets if b.definition.is_default]
        assert len(default_buckets) == 1
        assert default_buckets[0].definition.name == "General work"

    def test_high_weight_work_types_create_bucket(self, service, weighted_profile):
        buckets = service._define_buckets_from_profile(weighted_profile)

        # "test" has weight 0.9 (>= 0.7), so should create a work type bucket
        work_type_buckets = [
            b for b in buckets
            if not b.definition.is_default
            and any(
                c.criterion_type == BucketCriterionType.WORK_TYPE_IN
                for c in b.definition.criteria
            )
        ]
        assert len(work_type_buckets) == 1
        criteria = work_type_buckets[0].definition.criteria[0]
        assert "test" in criteria.params["values"]

    def test_high_weight_stages_create_bucket(self, service, weighted_profile):
        buckets = service._define_buckets_from_profile(weighted_profile)

        stage_buckets = [
            b for b in buckets
            if not b.definition.is_default
            and any(
                c.criterion_type == BucketCriterionType.LIFECYCLE_STAGE_IN
                for c in b.definition.criteria
            )
        ]
        assert len(stage_buckets) == 1
        criteria = stage_buckets[0].definition.criteria[0]
        assert "build" in criteria.params["values"]

    def test_policy_force_bucket_creates_bucket(self, service):
        profile = make_profile(
            policy_rules=[
                PolicyRule(
                    rule_id="rule-1",
                    name="Critical blockers first",
                    condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE,
                    condition_params={"threshold": 2},
                    action_type=PolicyActionType.FORCE_BUCKET,
                    action_params={"target_bucket": "blockers"},
                ),
            ],
        )
        buckets = service._define_buckets_from_profile(profile)

        policy_buckets = [
            b for b in buckets if b.bucket_id.startswith("bucket-policy-")
        ]
        assert len(policy_buckets) == 1
        assert policy_buckets[0].definition.name == "Critical blockers first"
        assert policy_buckets[0].rank == 1  # Highest priority

    def test_bucket_ranks_are_unique(self, service, weighted_profile):
        buckets = service._define_buckets_from_profile(weighted_profile)
        ranks = [b.rank for b in buckets]
        assert len(ranks) == len(set(ranks))

    def test_default_bucket_has_highest_rank_number(self, service, weighted_profile):
        buckets = service._define_buckets_from_profile(weighted_profile)
        default_bucket = [b for b in buckets if b.definition.is_default][0]
        max_rank = max(b.rank for b in buckets)
        assert default_bucket.rank == max_rank


# =============================================================================
# _place_items_in_buckets Tests
# =============================================================================


class TestPlaceItemsInBuckets:
    @pytest.mark.asyncio
    async def test_items_placed_by_work_type(self, service):
        """Items matching work type criteria go to that bucket."""
        profile = make_profile(
            work_type_weights={
                "test": WeightedValue(weight=0.9),
            },
        )
        items = [
            make_issue("item-1", issue_type="feature"),
            make_issue("item-2", issue_type="test"),
        ]
        chars = {
            "item-1": make_char_result("item-1", work_type=WorkType.FEATURE),
            "item-2": make_char_result("item-2", work_type=WorkType.TEST),
        }

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=profile,
            items=items,
            characterizations=chars,
            dependency_graph={},
        )

        # item-2 (test) should be in the priority work types bucket
        found = tree.find_item("item-2")
        assert found is not None
        bucket, item = found
        assert "test" in bucket.definition.name.lower() or not bucket.definition.is_default

    @pytest.mark.asyncio
    async def test_unmatched_items_go_to_default(self, service):
        """Items not matching any criteria go to the default bucket."""
        profile = make_profile(
            work_type_weights={
                "test": WeightedValue(weight=0.9),
            },
        )
        items = [
            make_issue("item-1", issue_type="feature"),
        ]
        chars = {
            "item-1": make_char_result("item-1", work_type=WorkType.FEATURE),
        }

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=profile,
            items=items,
            characterizations=chars,
            dependency_graph={},
        )

        found = tree.find_item("item-1")
        assert found is not None
        bucket, _ = found
        assert bucket.definition.is_default

    @pytest.mark.asyncio
    async def test_items_without_characterization_placed(self, service, default_profile):
        """Items without characterization still get placed (in default bucket)."""
        items = [make_issue("item-1")]

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=items,
            characterizations={},  # No characterizations
            dependency_graph={},
        )

        assert tree.total_items == 1


# =============================================================================
# _compute_readiness Tests
# =============================================================================


class TestComputeReadiness:
    def test_no_deps_is_ready(self, service):
        all_ids = {"item-1", "item-2"}
        result = service._compute_readiness("item-1", {}, all_ids)
        assert result == ItemReadiness.READY

    def test_external_deps_is_ready(self, service):
        """Deps on items outside the current set are treated as resolved."""
        all_ids = {"item-1"}
        dep_graph = {"item-1": ["external-item"]}
        result = service._compute_readiness("item-1", dep_graph, all_ids)
        assert result == ItemReadiness.READY

    def test_internal_dep_is_blocked(self, service):
        all_ids = {"item-1", "item-2"}
        dep_graph = {"item-2": ["item-1"]}
        result = service._compute_readiness("item-2", dep_graph, all_ids)
        assert result == ItemReadiness.BLOCKED


# =============================================================================
# _compute_blocking_count Tests
# =============================================================================


class TestComputeBlockingCount:
    def test_no_dependents(self, service):
        items = [make_issue("item-1"), make_issue("item-2")]
        count = service._compute_blocking_count("item-1", items, {"item-1", "item-2"})
        assert count == 0

    def test_blocks_two_items(self, service):
        items = [
            make_issue("item-1"),
            make_issue("item-2", blocked_by=["item-1"]),
            make_issue("item-3", blocked_by=["item-1"]),
        ]
        count = service._compute_blocking_count(
            "item-1", items, {"item-1", "item-2", "item-3"}
        )
        assert count == 2

    def test_only_counts_internal(self, service):
        items = [
            make_issue("item-1"),
            make_issue("item-2", blocked_by=["item-1"]),
        ]
        # item-3 is not in all_ids
        count = service._compute_blocking_count("item-1", items, {"item-1", "item-2"})
        assert count == 1


# =============================================================================
# _compute_priority_score Tests
# =============================================================================


class TestComputePriorityScore:
    def test_uncharacterized_returns_default(self, service, default_profile):
        score = service._compute_priority_score(None, default_profile)
        assert score == 0.5

    def test_weighted_profile_affects_score(self, service):
        profile = make_profile(
            work_type_weights={
                "test": WeightedValue(weight=0.9),
            },
            lifecycle_stage_weights={
                "validate": WeightedValue(weight=0.8),
            },
        )
        char = make_char_result(
            "item-1",
            work_type=WorkType.TEST,
            lifecycle_stage=LifecycleStage.VALIDATE,
        )
        score = service._compute_priority_score(char, profile)

        # work_type=test→0.9, lifecycle=validate→0.8, domain=backend→default 0.5
        # Average = (0.9 + 0.8 + 0.5) / 3 ≈ 0.733
        assert score > 0.7

    def test_low_weights_give_low_score(self, service):
        profile = make_profile(
            work_type_weights={
                "documentation": WeightedValue(weight=0.1),
            },
            lifecycle_stage_weights={
                "deploy": WeightedValue(weight=0.2),
            },
        )
        char = make_char_result(
            "item-1",
            work_type=WorkType.DOCUMENTATION,
            lifecycle_stage=LifecycleStage.DEPLOY,
        )
        score = service._compute_priority_score(char, profile)
        assert score < 0.4

    def test_cluster_weights_included(self, service):
        profile = make_profile(
            cluster_weights={
                "auth-cluster": WeightedValue(weight=0.95),
            },
        )
        char = make_char_result(
            "item-1",
            cluster_ids=["auth-cluster"],
        )
        score = service._compute_priority_score(char, profile)
        # Cluster weight of 0.95 should pull score up
        assert score > 0.5


# =============================================================================
# _evaluate_criterion Tests
# =============================================================================


class TestEvaluateCriterion:
    def test_work_type_in_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.WORK_TYPE_IN,
            params={"values": ["test", "bug_fix"]},
        )
        item = make_issue("item-1", issue_type="test")
        char = make_char_result("item-1", work_type=WorkType.TEST)

        assert service._evaluate_criterion(
            criterion, item, char, set(), [], {}
        ) is True

    def test_work_type_in_no_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.WORK_TYPE_IN,
            params={"values": ["test"]},
        )
        item = make_issue("item-1", issue_type="feature")
        char = make_char_result("item-1", work_type=WorkType.FEATURE)

        assert service._evaluate_criterion(
            criterion, item, char, set(), [], {}
        ) is False

    def test_work_type_fallback_to_issue_type(self, service):
        """Without characterization, falls back to issue type hint."""
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.WORK_TYPE_IN,
            params={"values": ["feature"]},
        )
        item = make_issue("item-1", issue_type="feature")

        assert service._evaluate_criterion(
            criterion, item, None, set(), [], {}
        ) is True

    def test_lifecycle_stage_in_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.LIFECYCLE_STAGE_IN,
            params={"values": ["build", "test"]},
        )
        char = make_char_result("item-1", lifecycle_stage=LifecycleStage.BUILD)

        assert service._evaluate_criterion(
            criterion, make_issue("item-1"), char, set(), [], {}
        ) is True

    def test_technical_domain_in_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.TECHNICAL_DOMAIN_IN,
            params={"values": ["frontend", "api"]},
        )
        char = make_char_result(
            "item-1", domains=[TechnicalDomain.API, TechnicalDomain.BACKEND]
        )

        # Has api domain, which is in the criterion values
        assert service._evaluate_criterion(
            criterion, make_issue("item-1"), char, set(), [], {}
        ) is True

    def test_cluster_in_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.CLUSTER_IN,
            params={"values": ["auth-cluster"]},
        )
        char = make_char_result("item-1", cluster_ids=["auth-cluster", "other"])

        assert service._evaluate_criterion(
            criterion, make_issue("item-1"), char, set(), [], {}
        ) is True

    def test_is_blocking_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.IS_BLOCKING,
            params={"min_count": 2},
        )
        items = [
            make_issue("item-1"),
            make_issue("item-2", blocked_by=["item-1"]),
            make_issue("item-3", blocked_by=["item-1"]),
        ]
        all_ids = {"item-1", "item-2", "item-3"}

        assert service._evaluate_criterion(
            criterion, items[0], None, all_ids, items, {}
        ) is True

    def test_dependency_ready_match(self, service):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.DEPENDENCY_READY,
            params={},
        )
        all_ids = {"item-1", "item-2"}

        # item-1 has no deps → READY
        assert service._evaluate_criterion(
            criterion, make_issue("item-1"), None, all_ids, [], {}
        ) is True

    def test_match_any_or_logic(self, service):
        """MATCH_ANY should use OR logic on nested criteria."""
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.MATCH_ANY,
            nested=[
                BucketCriterion(
                    criterion_type=BucketCriterionType.WORK_TYPE_IN,
                    params={"values": ["test"]},
                ),
                BucketCriterion(
                    criterion_type=BucketCriterionType.WORK_TYPE_IN,
                    params={"values": ["bug_fix"]},
                ),
            ],
        )
        char = make_char_result("item-1", work_type=WorkType.BUG_FIX)

        # Matches the second nested criterion
        assert service._evaluate_criterion(
            criterion, make_issue("item-1"), char, set(), [], {}
        ) is True


# =============================================================================
# Assignment Queue Tests
# =============================================================================


class TestAssignmentQueue:
    @pytest.mark.asyncio
    async def test_ready_items_first(self, service):
        """Ready items from higher-priority buckets should come first."""
        profile = make_profile(
            work_type_weights={
                "test": WeightedValue(weight=0.9),
            },
        )
        items = [
            make_issue("item-1", issue_type="feature"),
            make_issue("item-2", issue_type="test"),
        ]
        chars = {
            "item-1": make_char_result("item-1", work_type=WorkType.FEATURE),
            "item-2": make_char_result("item-2", work_type=WorkType.TEST),
        }

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=profile,
            items=items,
            characterizations=chars,
            dependency_graph={},
        )

        queue = tree.get_assignment_queue()
        assert len(queue) == 2
        # The test item should be in a higher-priority bucket
        assert queue[0].item_id == "item-2"

    @pytest.mark.asyncio
    async def test_blocked_items_not_in_queue(self, service, default_profile):
        """Blocked items should not appear in the assignment queue."""
        items = [
            make_issue("item-1"),
            make_issue("item-2", blocked_by=["item-1"]),
        ]
        chars = {
            "item-1": make_char_result("item-1"),
            "item-2": make_char_result("item-2"),
        }
        dep_graph = {"item-2": ["item-1"]}

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=items,
            characterizations=chars,
            dependency_graph=dep_graph,
        )

        queue = tree.get_assignment_queue()
        queue_ids = [qi.item_id for qi in queue]
        assert "item-1" in queue_ids
        assert "item-2" not in queue_ids  # blocked

    @pytest.mark.asyncio
    async def test_blocking_items_have_higher_priority(self, service, default_profile):
        """Items that block others should be prioritized within a bucket."""
        items = [
            make_issue("item-1"),
            make_issue("item-2"),
            make_issue("item-3", blocked_by=["item-1"]),
            make_issue("item-4", blocked_by=["item-1"]),
        ]
        chars = {
            "item-1": make_char_result("item-1"),
            "item-2": make_char_result("item-2"),
            "item-3": make_char_result("item-3"),
            "item-4": make_char_result("item-4"),
        }
        dep_graph = {
            "item-3": ["item-1"],
            "item-4": ["item-1"],
        }

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=items,
            characterizations=chars,
            dependency_graph=dep_graph,
        )

        queue = tree.get_assignment_queue()
        if len(queue) >= 2:
            # item-1 blocks 2 items, item-2 blocks 0
            # item-1 should come before item-2
            item1_idx = next(
                (i for i, q in enumerate(queue) if q.item_id == "item-1"), -1
            )
            item2_idx = next(
                (i for i, q in enumerate(queue) if q.item_id == "item-2"), -1
            )
            assert item1_idx < item2_idx


# =============================================================================
# Integration Tests
# =============================================================================


class TestBucketTreeIntegration:
    @pytest.mark.asyncio
    async def test_full_workflow(self, service):
        """Full workflow: profile → bucket tree → assignment queue."""
        profile = make_profile(
            work_type_weights={
                "bug_fix": WeightedValue(weight=0.95),
                "feature": WeightedValue(weight=0.5),
                "test": WeightedValue(weight=0.7),
            },
            lifecycle_stage_weights={
                "validate": WeightedValue(weight=0.8),
            },
        )
        items = [
            make_issue("feat-1", "Add login", issue_type="feature"),
            make_issue("bug-1", "Fix crash", issue_type="bug_fix"),
            make_issue("test-1", "E2E tests", issue_type="test"),
            make_issue("feat-2", "Add logout", issue_type="feature", blocked_by=["feat-1"]),
        ]
        chars = {
            "feat-1": make_char_result("feat-1", work_type=WorkType.FEATURE),
            "bug-1": make_char_result("bug-1", work_type=WorkType.BUG_FIX),
            "test-1": make_char_result("test-1", work_type=WorkType.TEST),
            "feat-2": make_char_result("feat-2", work_type=WorkType.FEATURE),
        }
        dep_graph = {"feat-2": ["feat-1"]}

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=profile,
            items=items,
            characterizations=chars,
            dependency_graph=dep_graph,
        )

        assert tree.total_items == 4
        assert tree.total_ready == 3  # feat-2 is blocked

        queue = tree.get_assignment_queue()
        assert len(queue) == 3  # only ready items
        # bug-1 should be in the high-priority bucket (bug_fix weight=0.95)
        assert queue[0].item_id == "bug-1"

    @pytest.mark.asyncio
    async def test_policy_rule_drives_bucket(self, service):
        """Policy rules with FORCE_BUCKET should create and populate buckets."""
        profile = make_profile(
            policy_rules=[
                PolicyRule(
                    rule_id="rule-hotfix",
                    name="Hotfix items",
                    condition_type=PolicyConditionType.IN_ONTOLOGY_CATEGORY,
                    condition_params={
                        "category": "work_type",
                        "values": ["bug_fix"],
                    },
                    action_type=PolicyActionType.FORCE_BUCKET,
                    action_params={"target_bucket": "hotfix"},
                ),
            ],
        )
        items = [
            make_issue("feat-1", issue_type="feature"),
            make_issue("bug-1", issue_type="bug_fix"),
        ]
        chars = {
            "feat-1": make_char_result("feat-1", work_type=WorkType.FEATURE),
            "bug-1": make_char_result("bug-1", work_type=WorkType.BUG_FIX),
        }

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=profile,
            items=items,
            characterizations=chars,
            dependency_graph={},
        )

        # bug-1 should be in the policy-driven bucket
        found = tree.find_item("bug-1")
        assert found is not None
        bucket, _ = found
        assert bucket.bucket_id == "bucket-policy-rule-hotfix"
        assert bucket.rank == 1  # Highest priority

    @pytest.mark.asyncio
    async def test_mixed_characterized_and_uncharacterized(self, service, default_profile):
        """Mix of characterized and uncharacterized items."""
        items = [
            make_issue("char-1"),
            make_issue("unchar-1"),
        ]
        chars = {
            "char-1": make_char_result("char-1"),
            # "unchar-1" has no characterization
        }

        tree = await service.create_bucket_tree(
            project_id="proj-1",
            profile=default_profile,
            items=items,
            characterizations=chars,
            dependency_graph={},
        )

        assert tree.total_items == 2
        # Both should be findable
        assert tree.find_item("char-1") is not None
        assert tree.find_item("unchar-1") is not None
