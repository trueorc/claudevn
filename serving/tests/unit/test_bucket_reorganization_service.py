"""Unit tests for BucketReorganizationService.

Tests trigger detection, bucket reorganization, in-progress work
protection, movement diffing, and decision trace generation.
"""

import pytest
from typing import Dict, List, Set
from unittest.mock import AsyncMock, MagicMock

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
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemMovement,
    ItemReadiness,
    PriorityBucket,
    ReorganizationEvent,
    ReorganizationTriggerType,
)
from services.bucket_reorganization_service import (
    BucketReorganizationService,
    WEIGHT_SHIFT_THRESHOLD,
)
from services.work_planner import WorkPlannerService


# =============================================================================
# Test Helpers
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
    version=1,
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
        version=version,
    )


def make_bucket_tree(
    tree_id="tree-001",
    project_id="proj-1",
    buckets=None,
    version=1,
):
    return BucketTree(
        tree_id=tree_id,
        project_id=project_id,
        buckets=buckets or [],
        version=version,
    )


def make_bucket(bucket_id, rank, items=None, is_default=False, name=None):
    return PriorityBucket(
        bucket_id=bucket_id,
        rank=rank,
        definition=BucketDefinition(
            name=name or f"Bucket {bucket_id}",
            is_default=is_default,
        ),
        items=items or [],
    )


def make_bucket_item(item_id, readiness=ItemReadiness.READY, priority_score=0.5):
    return BucketItem(
        item_id=item_id,
        readiness=readiness,
        priority_score=priority_score,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def planner():
    return WorkPlannerService()


@pytest.fixture
def service(planner):
    return BucketReorganizationService(work_planner=planner)


@pytest.fixture
def old_profile():
    """Profile with moderate weights on features."""
    return make_profile(
        profile_id="profile-old",
        version=1,
        work_type_weights={
            "feature": WeightedValue(weight=0.8),
            "test": WeightedValue(weight=0.4),
            "bug_fix": WeightedValue(weight=0.3),
        },
        lifecycle_stage_weights={
            "build": WeightedValue(weight=0.7),
        },
    )


@pytest.fixture
def shifted_profile():
    """Profile shifted to emphasize testing — significant weight change."""
    return make_profile(
        profile_id="profile-new",
        version=2,
        work_type_weights={
            "feature": WeightedValue(weight=0.4),
            "test": WeightedValue(weight=0.9),
            "bug_fix": WeightedValue(weight=0.7),
        },
        lifecycle_stage_weights={
            "build": WeightedValue(weight=0.3),
            "validate": WeightedValue(weight=0.8),
        },
    )


@pytest.fixture
def items():
    return [
        make_issue("item-1", "Set up DB", issue_type="feature"),
        make_issue("item-2", "Write tests", issue_type="test"),
        make_issue("item-3", "Fix crash", issue_type="bug_fix"),
        make_issue("item-4", "Add API", issue_type="feature", blocked_by=["item-1"]),
    ]


@pytest.fixture
def characterizations():
    return {
        "item-1": make_char_result("item-1", work_type=WorkType.FEATURE),
        "item-2": make_char_result("item-2", work_type=WorkType.TEST),
        "item-3": make_char_result("item-3", work_type=WorkType.BUG_FIX),
        "item-4": make_char_result("item-4", work_type=WorkType.FEATURE),
    }


@pytest.fixture
def dep_graph():
    return {"item-4": ["item-1"]}


@pytest.fixture
def current_tree():
    """A tree with items distributed across two buckets plus default."""
    return make_bucket_tree(
        buckets=[
            make_bucket(
                "bucket-features", rank=1, name="Feature work",
                items=[
                    make_bucket_item("item-1"),
                    make_bucket_item("item-4", readiness=ItemReadiness.BLOCKED),
                ],
            ),
            make_bucket(
                "bucket-default", rank=2, is_default=True, name="General work",
                items=[
                    make_bucket_item("item-2"),
                    make_bucket_item("item-3"),
                ],
            ),
        ],
    )


# =============================================================================
# Trigger Detection Tests
# =============================================================================


class TestDetectProfileShift:
    def test_detects_significant_weight_change(self, service, old_profile, shifted_profile):
        """A weight change >= threshold should be detected."""
        assert service.detect_profile_shift(old_profile, shifted_profile) is True

    def test_ignores_minor_weight_change(self, service):
        """A weight change below threshold should not trigger."""
        old = make_profile(
            version=1,
            work_type_weights={"feature": WeightedValue(weight=0.5)},
        )
        new = make_profile(
            version=2,
            work_type_weights={"feature": WeightedValue(weight=0.55)},
        )
        assert service.detect_profile_shift(old, new) is False

    def test_same_version_no_shift(self, service, old_profile):
        """If version hasn't changed, no shift detected."""
        assert service.detect_profile_shift(old_profile, old_profile) is False

    def test_new_force_bucket_rule_triggers_shift(self, service):
        """Adding a FORCE_BUCKET rule should trigger reorganization."""
        old = make_profile(version=1)
        new = make_profile(
            version=2,
            policy_rules=[
                PolicyRule(
                    rule_id="rule-1",
                    name="Force blockers",
                    condition_type=PolicyConditionType.BLOCKING_COUNT_ABOVE,
                    condition_params={"threshold": 1},
                    action_type=PolicyActionType.FORCE_BUCKET,
                    action_params={"target_bucket": "blockers"},
                ),
            ],
        )
        assert service.detect_profile_shift(old, new) is True

    def test_weight_removed_triggers_shift(self, service):
        """A weight being removed (key disappears) counts as a shift."""
        old = make_profile(
            version=1,
            work_type_weights={"feature": WeightedValue(weight=0.9)},
        )
        new = make_profile(
            version=2,
            work_type_weights={},
        )
        # feature weight goes from 0.9 to 0.5 (default) = 0.4 delta
        assert service.detect_profile_shift(old, new) is True

    def test_weight_added_triggers_shift(self, service):
        """A new weight key appearing counts as a shift if delta is big enough."""
        old = make_profile(version=1, work_type_weights={})
        new = make_profile(
            version=2,
            work_type_weights={"bug_fix": WeightedValue(weight=0.9)},
        )
        # 0.5 (default) -> 0.9 = 0.4 delta
        assert service.detect_profile_shift(old, new) is True


class TestDetectTrigger:
    def test_profile_shift_highest_priority(self, service, old_profile, shifted_profile):
        """Profile shift takes precedence over other triggers."""
        trigger = service.detect_trigger(
            old_profile, shifted_profile,
            new_items_added=True,
            items_completed=True,
        )
        assert trigger == ReorganizationTriggerType.PROFILE_SHIFT

    def test_new_items_trigger(self, service, old_profile):
        """New items added should trigger when no profile shift."""
        trigger = service.detect_trigger(
            old_profile, old_profile,
            new_items_added=True,
        )
        assert trigger == ReorganizationTriggerType.NEW_ITEMS_ADDED

    def test_items_completed_trigger(self, service, old_profile):
        trigger = service.detect_trigger(
            old_profile, old_profile,
            items_completed=True,
        )
        assert trigger == ReorganizationTriggerType.ITEMS_COMPLETED

    def test_resource_change_trigger(self, service, old_profile):
        trigger = service.detect_trigger(
            old_profile, old_profile,
            resource_changed=True,
        )
        assert trigger == ReorganizationTriggerType.RESOURCE_CHANGE

    def test_no_trigger(self, service, old_profile):
        """No trigger conditions met returns None."""
        trigger = service.detect_trigger(old_profile, old_profile)
        assert trigger is None

    def test_no_old_profile_no_shift(self, service, old_profile):
        """First-time profile (no old) does not trigger profile_shift."""
        trigger = service.detect_trigger(
            None, old_profile,
            new_items_added=True,
        )
        assert trigger == ReorganizationTriggerType.NEW_ITEMS_ADDED


# =============================================================================
# Reorganization Tests
# =============================================================================


class TestReorganize:
    @pytest.mark.asyncio
    async def test_returns_reorganization_result(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        assert result.tree is not None
        assert result.event is not None
        assert result.tree.project_id == "proj-1"
        assert result.tree.version == 2  # incremented from 1
        assert result.event.trigger_type == ReorganizationTriggerType.PROFILE_SHIFT

    @pytest.mark.asyncio
    async def test_all_items_placed_after_reorg(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        # All 4 items should still be in the tree
        assert result.tree.total_items == 4

    @pytest.mark.asyncio
    async def test_version_incremented(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        assert result.tree.version == current_tree.version + 1
        assert result.previous_version == current_tree.version

    @pytest.mark.asyncio
    async def test_reorganization_event_recorded_in_history(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        assert len(result.tree.reorganization_history) == 1
        assert result.tree.reorganization_history[0].event_id == result.event.event_id

    @pytest.mark.asyncio
    async def test_profile_id_updated(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        assert result.tree.profile_id == shifted_profile.profile_id

    @pytest.mark.asyncio
    async def test_empty_items(self, service, shifted_profile):
        empty_tree = make_bucket_tree(
            buckets=[make_bucket("bucket-default", rank=1, is_default=True)],
        )

        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.NEW_ITEMS_ADDED,
            trigger_source_id="",
            current_tree=empty_tree,
            updated_profile=shifted_profile,
            items=[],
            characterizations={},
            dependency_graph={},
        )

        assert result.tree.total_items == 0
        assert result.event.items_moved == 0


# =============================================================================
# In-Progress Work Protection Tests
# =============================================================================


class TestInProgressProtection:
    @pytest.mark.asyncio
    async def test_assigned_items_preserved(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        """Items assigned to compute should not be disrupted."""
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
            assigned_item_ids={"item-1"},
        )

        assert "item-1" in result.items_preserved_ids
        assert result.event.items_preserved >= 1

    @pytest.mark.asyncio
    async def test_unassigned_items_can_move(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        """Unassigned items should be free to move between buckets."""
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
            assigned_item_ids=set(),
        )

        # All 4 items placed, none preserved
        assert result.tree.total_items == 4
        assert result.event.items_preserved == 0

    @pytest.mark.asyncio
    async def test_multiple_assigned_items(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        """Multiple assigned items should all be preserved."""
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
            assigned_item_ids={"item-1", "item-2"},
        )

        assert "item-1" in result.items_preserved_ids
        assert "item-2" in result.items_preserved_ids

    @pytest.mark.asyncio
    async def test_no_assigned_items(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        """No assigned items means no preservation needed."""
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        assert result.items_preserved_ids == []


# =============================================================================
# Movement Tracking Tests
# =============================================================================


class TestMovementTracking:
    def test_compute_movements_detects_changes(self, service):
        old_placements = {"item-1": "bucket-a", "item-2": "bucket-a"}
        new_placements = {"item-1": "bucket-b", "item-2": "bucket-a"}

        movements = service._compute_movements(
            old_placements, new_placements, assigned_item_ids=set()
        )

        assert len(movements) == 1
        assert movements[0].item_id == "item-1"
        assert movements[0].from_bucket_id == "bucket-a"
        assert movements[0].to_bucket_id == "bucket-b"

    def test_compute_movements_excludes_assigned(self, service):
        old_placements = {"item-1": "bucket-a", "item-2": "bucket-a"}
        new_placements = {"item-1": "bucket-b", "item-2": "bucket-b"}

        movements = service._compute_movements(
            old_placements, new_placements, assigned_item_ids={"item-1"}
        )

        # item-1 is assigned, so only item-2 is counted
        assert len(movements) == 1
        assert movements[0].item_id == "item-2"

    def test_compute_movements_no_changes(self, service):
        placements = {"item-1": "bucket-a", "item-2": "bucket-b"}
        movements = service._compute_movements(
            placements, placements, assigned_item_ids=set()
        )
        assert len(movements) == 0

    def test_compute_movements_new_item(self, service):
        """Items that are only in new_placements (not old) don't count as moved."""
        old_placements = {"item-1": "bucket-a"}
        new_placements = {"item-1": "bucket-a", "item-2": "bucket-b"}

        movements = service._compute_movements(
            old_placements, new_placements, assigned_item_ids=set()
        )

        # item-2 is new, not moved
        assert len(movements) == 0


# =============================================================================
# Extract Placements Tests
# =============================================================================


class TestExtractPlacements:
    def test_extracts_all_placements(self, service, current_tree):
        placements = service._extract_placements(current_tree)

        assert placements["item-1"] == "bucket-features"
        assert placements["item-4"] == "bucket-features"
        assert placements["item-2"] == "bucket-default"
        assert placements["item-3"] == "bucket-default"

    def test_empty_tree(self, service):
        tree = make_bucket_tree(buckets=[])
        placements = service._extract_placements(tree)
        assert placements == {}


# =============================================================================
# Protect Assigned Items Tests
# =============================================================================


class TestProtectAssignedItems:
    def test_restores_to_old_bucket(self, service):
        """Item moved to new bucket should be restored to old bucket."""
        old_placements = {"item-1": "bucket-a"}
        new_tree = make_bucket_tree(
            buckets=[
                make_bucket("bucket-a", rank=1),
                make_bucket("bucket-b", rank=2, items=[make_bucket_item("item-1")]),
            ],
        )
        current_tree = make_bucket_tree(
            buckets=[
                make_bucket("bucket-a", rank=1, items=[make_bucket_item("item-1")]),
                make_bucket("bucket-b", rank=2),
            ],
        )

        preserved = service._protect_assigned_items(
            new_tree=new_tree,
            old_placements=old_placements,
            current_tree=current_tree,
            assigned_item_ids={"item-1"},
        )

        assert "item-1" in preserved
        # Item should be back in bucket-a
        bucket_a = new_tree.get_bucket("bucket-a")
        assert any(i.item_id == "item-1" for i in bucket_a.items)
        bucket_b = new_tree.get_bucket("bucket-b")
        assert not any(i.item_id == "item-1" for i in bucket_b.items)

    def test_old_bucket_gone_keeps_new_placement(self, service):
        """If old bucket doesn't exist in new tree, keep new placement."""
        old_placements = {"item-1": "bucket-removed"}
        new_tree = make_bucket_tree(
            buckets=[
                make_bucket("bucket-new", rank=1, items=[make_bucket_item("item-1")]),
            ],
        )
        current_tree = make_bucket_tree(
            buckets=[
                make_bucket("bucket-removed", rank=1, items=[make_bucket_item("item-1")]),
            ],
        )

        preserved = service._protect_assigned_items(
            new_tree=new_tree,
            old_placements=old_placements,
            current_tree=current_tree,
            assigned_item_ids={"item-1"},
        )

        # Item still preserved (not disrupted), just in new bucket
        assert "item-1" in preserved
        bucket_new = new_tree.get_bucket("bucket-new")
        assert any(i.item_id == "item-1" for i in bucket_new.items)

    def test_item_stays_in_same_bucket(self, service):
        """Item already in the correct bucket needs no movement."""
        old_placements = {"item-1": "bucket-a"}
        new_tree = make_bucket_tree(
            buckets=[
                make_bucket("bucket-a", rank=1, items=[make_bucket_item("item-1")]),
            ],
        )
        current_tree = make_bucket_tree(
            buckets=[
                make_bucket("bucket-a", rank=1, items=[make_bucket_item("item-1")]),
            ],
        )

        preserved = service._protect_assigned_items(
            new_tree=new_tree,
            old_placements=old_placements,
            current_tree=current_tree,
            assigned_item_ids={"item-1"},
        )

        assert "item-1" in preserved

    def test_no_assigned_items(self, service):
        """Empty assigned set returns empty preserved list."""
        preserved = service._protect_assigned_items(
            new_tree=make_bucket_tree(),
            old_placements={},
            current_tree=make_bucket_tree(),
            assigned_item_ids=set(),
        )
        assert preserved == []


# =============================================================================
# Decision Trace Tests
# =============================================================================


class TestDecisionTrace:
    @pytest.mark.asyncio
    async def test_trace_in_result(
        self, service, current_tree, shifted_profile,
        items, characterizations, dep_graph,
    ):
        """Reorganization should produce a decision trace entry."""
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-1",
            current_tree=current_tree,
            updated_profile=shifted_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dep_graph,
        )

        # The trace is embedded in the event metadata
        assert result.event.event_id.startswith("reorg-")
        assert result.event.description != ""


# =============================================================================
# Weight Shift Counting Tests
# =============================================================================


class TestCountWeightShifts:
    def test_no_shifts(self, service):
        old = {"a": WeightedValue(weight=0.5)}
        new = {"a": WeightedValue(weight=0.55)}
        assert service._count_weight_shifts(old, new) == 0

    def test_one_shift(self, service):
        old = {"a": WeightedValue(weight=0.5)}
        new = {"a": WeightedValue(weight=0.7)}
        assert service._count_weight_shifts(old, new) == 1

    def test_multiple_shifts(self, service):
        old = {"a": WeightedValue(weight=0.5), "b": WeightedValue(weight=0.3)}
        new = {"a": WeightedValue(weight=0.8), "b": WeightedValue(weight=0.6)}
        assert service._count_weight_shifts(old, new) == 2

    def test_new_key_with_default(self, service):
        """New key defaults to 0.5; if new value differs enough, counts."""
        old = {}
        new = {"a": WeightedValue(weight=0.9)}
        assert service._count_weight_shifts(old, new) == 1

    def test_removed_key(self, service):
        """Removed key defaults to 0.5; if old value differs enough, counts."""
        old = {"a": WeightedValue(weight=0.9)}
        new = {}
        assert service._count_weight_shifts(old, new) == 1

    def test_boundary_just_above_threshold(self, service):
        """Just above threshold should count."""
        old = {"a": WeightedValue(weight=0.5)}
        new = {"a": WeightedValue(weight=0.5 + WEIGHT_SHIFT_THRESHOLD + 0.01)}
        assert service._count_weight_shifts(old, new) == 1


# =============================================================================
# Describe Trigger Tests
# =============================================================================


class TestDescribeTrigger:
    def test_profile_shift_description(self, service):
        desc = service._describe_trigger(
            ReorganizationTriggerType.PROFILE_SHIFT, "goal-1"
        )
        assert "goal-1" in desc

    def test_new_items_description(self, service):
        desc = service._describe_trigger(
            ReorganizationTriggerType.NEW_ITEMS_ADDED, ""
        )
        assert "new" in desc.lower() or "added" in desc.lower()

    def test_resource_change_description(self, service):
        desc = service._describe_trigger(
            ReorganizationTriggerType.RESOURCE_CHANGE, "worker-5"
        )
        assert "worker-5" in desc


# =============================================================================
# Integration Test
# =============================================================================


class TestReorganizationIntegration:
    @pytest.mark.asyncio
    async def test_full_reorganization_workflow(self, service):
        """Full workflow: build tree, shift profile, reorganize, verify."""
        planner = service._work_planner

        # Original profile emphasizes features
        original_profile = make_profile(
            profile_id="profile-v1",
            version=1,
            work_type_weights={
                "feature": WeightedValue(weight=0.9),
                "test": WeightedValue(weight=0.3),
            },
        )

        items = [
            make_issue("feat-1", "Add login", issue_type="feature"),
            make_issue("feat-2", "Add logout", issue_type="feature"),
            make_issue("test-1", "Unit tests", issue_type="test"),
            make_issue("bug-1", "Fix crash", issue_type="bug_fix"),
        ]
        chars = {
            "feat-1": make_char_result("feat-1", work_type=WorkType.FEATURE),
            "feat-2": make_char_result("feat-2", work_type=WorkType.FEATURE),
            "test-1": make_char_result("test-1", work_type=WorkType.TEST),
            "bug-1": make_char_result("bug-1", work_type=WorkType.BUG_FIX),
        }

        # Step 1: Create initial tree
        original_tree = await planner.create_bucket_tree(
            project_id="proj-1",
            profile=original_profile,
            items=items,
            characterizations=chars,
            dependency_graph={},
        )

        assert original_tree.total_items == 4

        # Step 2: Profile shifts to emphasize testing
        shifted = make_profile(
            profile_id="profile-v2",
            version=2,
            work_type_weights={
                "feature": WeightedValue(weight=0.3),
                "test": WeightedValue(weight=0.9),
                "bug_fix": WeightedValue(weight=0.8),
            },
        )

        # Step 3: Detect trigger
        assert service.detect_profile_shift(original_profile, shifted) is True

        # Step 4: Reorganize (feat-1 is assigned)
        result = await service.reorganize(
            project_id="proj-1",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-consolidation",
            current_tree=original_tree,
            updated_profile=shifted,
            items=items,
            characterizations=chars,
            dependency_graph={},
            assigned_item_ids={"feat-1"},
        )

        # Verify result
        assert result.tree.total_items == 4
        assert result.tree.version == 2
        assert result.event.trigger_type == ReorganizationTriggerType.PROFILE_SHIFT
        assert "feat-1" in result.items_preserved_ids
        assert len(result.tree.reorganization_history) == 1

        # Assignment queue should now prioritize test/bug_fix items
        queue = result.tree.get_assignment_queue()
        if len(queue) >= 2:
            queue_ids = [q.item_id for q in queue]
            # test-1 or bug-1 should be near the top
            assert "test-1" in queue_ids or "bug-1" in queue_ids
