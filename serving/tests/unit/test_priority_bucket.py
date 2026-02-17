"""Tests for priority bucket tree data structure.

Tests cover:
- Bucket criteria and definitions
- BucketItem ordering (intra-bucket sort)
- PriorityBucket queries (ready/blocked items, sorting)
- ReorganizationEvent tracking
- BucketTree top-level model (validation, queries, assignment queue)
"""

import pytest
from datetime import datetime, timezone

from models.priority_bucket import (
    BucketCriterion,
    BucketCriterionType,
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemReadiness,
    PriorityBucket,
    ReorganizationEvent,
    ReorganizationTriggerType,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def testing_bucket_def():
    """Bucket definition for 'Validate what's built'."""
    return BucketDefinition(
        name="Validate what is built",
        description="Testing tasks for mature capability areas",
        criteria=[
            BucketCriterion(
                criterion_type=BucketCriterionType.WORK_TYPE_IN,
                params={"values": ["test"]},
            ),
        ],
    )


@pytest.fixture
def blocker_bucket_def():
    """Bucket definition for 'Remove blockers'."""
    return BucketDefinition(
        name="Remove blockers to validation",
        description="Bug fixes, dependency resolutions",
        criteria=[
            BucketCriterion(
                criterion_type=BucketCriterionType.MATCH_ANY,
                nested=[
                    BucketCriterion(
                        criterion_type=BucketCriterionType.WORK_TYPE_IN,
                        params={"values": ["bug_fix"]},
                    ),
                    BucketCriterion(
                        criterion_type=BucketCriterionType.IS_BLOCKING,
                        params={},
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def default_bucket_def():
    """Default catch-all bucket."""
    return BucketDefinition(
        name="Park for later",
        description="Early-stage new feature work",
        is_default=True,
    )


@pytest.fixture
def sample_items():
    """Sample bucket items with varying readiness and priority."""
    return [
        BucketItem(
            item_id="item-1",
            readiness=ItemReadiness.READY,
            priority_score=0.9,
            blocking_count=3,
            completion_pct=0.0,
        ),
        BucketItem(
            item_id="item-2",
            readiness=ItemReadiness.READY,
            priority_score=0.5,
            blocking_count=0,
            completion_pct=0.8,
        ),
        BucketItem(
            item_id="item-3",
            readiness=ItemReadiness.BLOCKED,
            priority_score=0.95,
            blocking_count=5,
            completion_pct=0.0,
        ),
        BucketItem(
            item_id="item-4",
            readiness=ItemReadiness.PARTIALLY_BLOCKED,
            priority_score=0.7,
            blocking_count=1,
            completion_pct=0.5,
        ),
    ]


@pytest.fixture
def sample_bucket(testing_bucket_def, sample_items):
    """A priority bucket with items."""
    return PriorityBucket(
        bucket_id="bucket-validate",
        rank=1,
        definition=testing_bucket_def,
        items=sample_items,
    )


@pytest.fixture
def sample_tree(testing_bucket_def, blocker_bucket_def, default_bucket_def):
    """A complete bucket tree with multiple buckets."""
    return BucketTree(
        tree_id="tree-001",
        project_id="project-001",
        profile_id="profile-abc",
        buckets=[
            PriorityBucket(
                bucket_id="bucket-validate",
                rank=1,
                definition=testing_bucket_def,
                items=[
                    BucketItem(
                        item_id="test-1",
                        readiness=ItemReadiness.READY,
                        priority_score=0.9,
                        blocking_count=0,
                    ),
                    BucketItem(
                        item_id="test-2",
                        readiness=ItemReadiness.BLOCKED,
                        priority_score=0.8,
                        blocking_count=0,
                    ),
                ],
            ),
            PriorityBucket(
                bucket_id="bucket-blockers",
                rank=2,
                definition=blocker_bucket_def,
                items=[
                    BucketItem(
                        item_id="fix-1",
                        readiness=ItemReadiness.READY,
                        priority_score=0.85,
                        blocking_count=2,
                    ),
                ],
            ),
            PriorityBucket(
                bucket_id="bucket-default",
                rank=4,
                definition=default_bucket_def,
                items=[
                    BucketItem(
                        item_id="feat-1",
                        readiness=ItemReadiness.READY,
                        priority_score=0.3,
                        blocking_count=0,
                    ),
                ],
            ),
        ],
    )


# ============================================================================
# Model Tests - BucketCriterion
# ============================================================================


class TestBucketCriterion:
    """Test BucketCriterion model."""

    def test_create_simple_criterion(self):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.WORK_TYPE_IN,
            params={"values": ["test", "bug_fix"]},
        )
        assert criterion.criterion_type == BucketCriterionType.WORK_TYPE_IN
        assert criterion.params["values"] == ["test", "bug_fix"]
        assert criterion.nested == []

    def test_create_nested_match_any(self):
        criterion = BucketCriterion(
            criterion_type=BucketCriterionType.MATCH_ANY,
            nested=[
                BucketCriterion(
                    criterion_type=BucketCriterionType.WORK_TYPE_IN,
                    params={"values": ["test"]},
                ),
                BucketCriterion(
                    criterion_type=BucketCriterionType.IS_BLOCKING,
                ),
            ],
        )
        assert criterion.criterion_type == BucketCriterionType.MATCH_ANY
        assert len(criterion.nested) == 2

    def test_criterion_types(self):
        assert BucketCriterionType.WORK_TYPE_IN.value == "work_type_in"
        assert BucketCriterionType.LIFECYCLE_STAGE_IN.value == "lifecycle_stage_in"
        assert BucketCriterionType.TECHNICAL_DOMAIN_IN.value == "technical_domain_in"
        assert BucketCriterionType.CLUSTER_IN.value == "cluster_in"
        assert BucketCriterionType.WEIGHT_ABOVE.value == "weight_above"
        assert BucketCriterionType.WEIGHT_BELOW.value == "weight_below"
        assert BucketCriterionType.COMPLETION_ABOVE.value == "completion_above"
        assert BucketCriterionType.COMPLETION_BELOW.value == "completion_below"
        assert BucketCriterionType.IS_BLOCKING.value == "is_blocking"
        assert BucketCriterionType.IS_BLOCKED.value == "is_blocked"
        assert BucketCriterionType.DEPENDENCY_READY.value == "dependency_ready"
        assert BucketCriterionType.MATCH_ANY.value == "match_any"


# ============================================================================
# Model Tests - BucketDefinition
# ============================================================================


class TestBucketDefinition:
    """Test BucketDefinition model."""

    def test_create_definition(self, testing_bucket_def):
        assert testing_bucket_def.name == "Validate what is built"
        assert len(testing_bucket_def.criteria) == 1
        assert testing_bucket_def.is_default is False

    def test_default_bucket(self, default_bucket_def):
        assert default_bucket_def.is_default is True
        assert default_bucket_def.criteria == []

    def test_definition_with_multiple_criteria(self):
        defn = BucketDefinition(
            name="Complex bucket",
            criteria=[
                BucketCriterion(
                    criterion_type=BucketCriterionType.WORK_TYPE_IN,
                    params={"values": ["test"]},
                ),
                BucketCriterion(
                    criterion_type=BucketCriterionType.COMPLETION_ABOVE,
                    params={"threshold": 0.5},
                ),
            ],
        )
        assert len(defn.criteria) == 2


# ============================================================================
# Model Tests - BucketItem
# ============================================================================


class TestBucketItem:
    """Test BucketItem model."""

    def test_create_item(self):
        item = BucketItem(
            item_id="item-1",
            readiness=ItemReadiness.READY,
            priority_score=0.9,
            blocking_count=3,
        )
        assert item.item_id == "item-1"
        assert item.readiness == ItemReadiness.READY
        assert item.priority_score == 0.9
        assert item.blocking_count == 3
        assert item.completion_pct == 0.0
        assert item.context_affinity_worker is None

    def test_item_defaults(self):
        item = BucketItem(item_id="item-1")
        assert item.readiness == ItemReadiness.BLOCKED
        assert item.priority_score == 0.0
        assert item.blocking_count == 0
        assert item.completion_pct == 0.0

    def test_readiness_enum(self):
        assert ItemReadiness.READY.value == "ready"
        assert ItemReadiness.BLOCKED.value == "blocked"
        assert ItemReadiness.PARTIALLY_BLOCKED.value == "partially_blocked"

    def test_completion_boundary_zero(self):
        item = BucketItem(item_id="x", completion_pct=0.0)
        assert item.completion_pct == 0.0

    def test_completion_boundary_one(self):
        item = BucketItem(item_id="x", completion_pct=1.0)
        assert item.completion_pct == 1.0

    def test_completion_below_zero_rejected(self):
        with pytest.raises(ValueError):
            BucketItem(item_id="x", completion_pct=-0.1)

    def test_completion_above_one_rejected(self):
        with pytest.raises(ValueError):
            BucketItem(item_id="x", completion_pct=1.1)

    def test_blocking_count_negative_rejected(self):
        with pytest.raises(ValueError):
            BucketItem(item_id="x", blocking_count=-1)


class TestBucketItemSortKey:
    """Test BucketItem sort_key for intra-bucket ordering."""

    def test_ready_before_blocked(self):
        ready = BucketItem(item_id="a", readiness=ItemReadiness.READY)
        blocked = BucketItem(item_id="b", readiness=ItemReadiness.BLOCKED)
        assert ready.sort_key < blocked.sort_key

    def test_ready_before_partially_blocked(self):
        ready = BucketItem(item_id="a", readiness=ItemReadiness.READY)
        partial = BucketItem(item_id="b", readiness=ItemReadiness.PARTIALLY_BLOCKED)
        assert ready.sort_key < partial.sort_key

    def test_partially_blocked_before_blocked(self):
        partial = BucketItem(item_id="a", readiness=ItemReadiness.PARTIALLY_BLOCKED)
        blocked = BucketItem(item_id="b", readiness=ItemReadiness.BLOCKED)
        assert partial.sort_key < blocked.sort_key

    def test_higher_blocking_count_first(self):
        high = BucketItem(
            item_id="a", readiness=ItemReadiness.READY, blocking_count=5
        )
        low = BucketItem(
            item_id="b", readiness=ItemReadiness.READY, blocking_count=1
        )
        assert high.sort_key < low.sort_key

    def test_higher_priority_score_first(self):
        high = BucketItem(
            item_id="a", readiness=ItemReadiness.READY, priority_score=0.9
        )
        low = BucketItem(
            item_id="b", readiness=ItemReadiness.READY, priority_score=0.3
        )
        assert high.sort_key < low.sort_key

    def test_higher_completion_first(self):
        high = BucketItem(
            item_id="a", readiness=ItemReadiness.READY, completion_pct=0.9
        )
        low = BucketItem(
            item_id="b", readiness=ItemReadiness.READY, completion_pct=0.1
        )
        assert high.sort_key < low.sort_key

    def test_full_sort_order(self, sample_items):
        """Test that a list of items sorts correctly."""
        sorted_items = sorted(sample_items, key=lambda i: i.sort_key)
        # Ready items first, then partially blocked, then blocked
        assert sorted_items[0].item_id == "item-1"  # ready, blocking=3, score=0.9
        assert sorted_items[1].item_id == "item-2"  # ready, blocking=0, score=0.5
        assert sorted_items[2].item_id == "item-4"  # partially blocked
        assert sorted_items[3].item_id == "item-3"  # blocked


# ============================================================================
# Model Tests - PriorityBucket
# ============================================================================


class TestPriorityBucket:
    """Test PriorityBucket model."""

    def test_create_bucket(self, sample_bucket):
        assert sample_bucket.bucket_id == "bucket-validate"
        assert sample_bucket.rank == 1
        assert sample_bucket.definition.name == "Validate what is built"
        assert len(sample_bucket.items) == 4

    def test_ready_items(self, sample_bucket):
        ready = sample_bucket.ready_items
        assert len(ready) == 2
        assert all(i.readiness == ItemReadiness.READY for i in ready)

    def test_blocked_items(self, sample_bucket):
        blocked = sample_bucket.blocked_items
        assert len(blocked) == 2
        assert all(
            i.readiness in (ItemReadiness.BLOCKED, ItemReadiness.PARTIALLY_BLOCKED)
            for i in blocked
        )

    def test_item_count(self, sample_bucket):
        assert sample_bucket.item_count == 4

    def test_sort_items(self, sample_bucket):
        sample_bucket.sort_items()
        ids = [i.item_id for i in sample_bucket.items]
        assert ids == ["item-1", "item-2", "item-4", "item-3"]

    def test_empty_bucket(self, testing_bucket_def):
        bucket = PriorityBucket(
            bucket_id="empty",
            rank=1,
            definition=testing_bucket_def,
        )
        assert bucket.item_count == 0
        assert bucket.ready_items == []
        assert bucket.blocked_items == []

    def test_rank_must_be_positive(self, testing_bucket_def):
        with pytest.raises(ValueError):
            PriorityBucket(
                bucket_id="bad",
                rank=0,
                definition=testing_bucket_def,
            )


# ============================================================================
# Model Tests - ReorganizationEvent
# ============================================================================


class TestReorganizationEvent:
    """Test ReorganizationEvent model."""

    def test_create_event(self):
        event = ReorganizationEvent(
            event_id="reorg-001",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-002",
            description="New goal shifted profile from 'build' to 'harden'",
            buckets_added=1,
            buckets_removed=0,
            items_moved=5,
        )
        assert event.event_id == "reorg-001"
        assert event.trigger_type == ReorganizationTriggerType.PROFILE_SHIFT
        assert event.items_moved == 5
        assert event.timestamp is not None

    def test_trigger_types(self):
        assert ReorganizationTriggerType.PROFILE_SHIFT.value == "profile_shift"
        assert ReorganizationTriggerType.NEW_ITEMS_ADDED.value == "new_items_added"
        assert ReorganizationTriggerType.ITEMS_COMPLETED.value == "items_completed"
        assert ReorganizationTriggerType.DEPENDENCY_RESOLVED.value == "dependency_resolved"
        assert ReorganizationTriggerType.RESOURCE_CHANGE.value == "resource_change"
        assert ReorganizationTriggerType.MANUAL.value == "manual"

    def test_event_defaults(self):
        event = ReorganizationEvent(
            event_id="reorg-001",
            trigger_type=ReorganizationTriggerType.MANUAL,
        )
        assert event.buckets_added == 0
        assert event.buckets_removed == 0
        assert event.items_moved == 0

    def test_negative_counts_rejected(self):
        with pytest.raises(ValueError):
            ReorganizationEvent(
                event_id="reorg-001",
                trigger_type=ReorganizationTriggerType.MANUAL,
                items_moved=-1,
            )


# ============================================================================
# Model Tests - BucketTree
# ============================================================================


class TestBucketTree:
    """Test BucketTree top-level model."""

    def test_create_minimal(self):
        tree = BucketTree(
            tree_id="tree-001",
            project_id="project-001",
        )
        assert tree.tree_id == "tree-001"
        assert tree.project_id == "project-001"
        assert tree.profile_id is None
        assert tree.buckets == []
        assert tree.version == 1

    def test_create_full(self, sample_tree):
        assert sample_tree.tree_id == "tree-001"
        assert sample_tree.profile_id == "profile-abc"
        assert len(sample_tree.buckets) == 3

    def test_timestamps_auto_set(self):
        before = datetime.now(timezone.utc)
        tree = BucketTree(tree_id="t", project_id="p")
        after = datetime.now(timezone.utc)
        assert before <= tree.created_at <= after
        assert before <= tree.updated_at <= after


# ============================================================================
# BucketTree - Validation
# ============================================================================


class TestBucketTreeValidation:
    """Test BucketTree validation rules."""

    def test_duplicate_bucket_ids_rejected(self, testing_bucket_def):
        with pytest.raises(ValueError, match="Duplicate bucket IDs"):
            BucketTree(
                tree_id="t",
                project_id="p",
                buckets=[
                    PriorityBucket(
                        bucket_id="dup",
                        rank=1,
                        definition=testing_bucket_def,
                    ),
                    PriorityBucket(
                        bucket_id="dup",
                        rank=2,
                        definition=testing_bucket_def,
                    ),
                ],
            )

    def test_duplicate_ranks_rejected(self, testing_bucket_def):
        with pytest.raises(ValueError, match="Duplicate bucket ranks"):
            BucketTree(
                tree_id="t",
                project_id="p",
                buckets=[
                    PriorityBucket(
                        bucket_id="a",
                        rank=1,
                        definition=testing_bucket_def,
                    ),
                    PriorityBucket(
                        bucket_id="b",
                        rank=1,
                        definition=testing_bucket_def,
                    ),
                ],
            )

    def test_multiple_default_buckets_rejected(self):
        default_def = BucketDefinition(name="Default A", is_default=True)
        default_def2 = BucketDefinition(name="Default B", is_default=True)
        with pytest.raises(ValueError, match="Multiple default buckets"):
            BucketTree(
                tree_id="t",
                project_id="p",
                buckets=[
                    PriorityBucket(
                        bucket_id="a",
                        rank=1,
                        definition=default_def,
                    ),
                    PriorityBucket(
                        bucket_id="b",
                        rank=2,
                        definition=default_def2,
                    ),
                ],
            )

    def test_single_default_bucket_accepted(self, sample_tree):
        """sample_tree has one default bucket — should pass validation."""
        assert sample_tree.default_bucket is not None
        assert sample_tree.default_bucket.bucket_id == "bucket-default"


# ============================================================================
# BucketTree - Queries
# ============================================================================


class TestBucketTreeQueries:
    """Test BucketTree query methods."""

    def test_get_bucket_found(self, sample_tree):
        bucket = sample_tree.get_bucket("bucket-validate")
        assert bucket is not None
        assert bucket.rank == 1

    def test_get_bucket_not_found(self, sample_tree):
        assert sample_tree.get_bucket("nonexistent") is None

    def test_get_ranked_buckets(self, sample_tree):
        ranked = sample_tree.get_ranked_buckets()
        assert [b.rank for b in ranked] == [1, 2, 4]
        assert ranked[0].bucket_id == "bucket-validate"

    def test_find_item_found(self, sample_tree):
        result = sample_tree.find_item("fix-1")
        assert result is not None
        bucket, item = result
        assert bucket.bucket_id == "bucket-blockers"
        assert item.item_id == "fix-1"

    def test_find_item_not_found(self, sample_tree):
        assert sample_tree.find_item("nonexistent") is None

    def test_total_items(self, sample_tree):
        assert sample_tree.total_items == 4

    def test_total_ready(self, sample_tree):
        # test-1 (ready), fix-1 (ready), feat-1 (ready) = 3
        assert sample_tree.total_ready == 3

    def test_default_bucket(self, sample_tree):
        default = sample_tree.default_bucket
        assert default is not None
        assert default.bucket_id == "bucket-default"

    def test_no_default_bucket(self, testing_bucket_def):
        tree = BucketTree(
            tree_id="t",
            project_id="p",
            buckets=[
                PriorityBucket(
                    bucket_id="a",
                    rank=1,
                    definition=testing_bucket_def,
                ),
            ],
        )
        assert tree.default_bucket is None


# ============================================================================
# BucketTree - Assignment Queue
# ============================================================================


class TestAssignmentQueue:
    """Test the work assignment queue derived from the bucket tree."""

    def test_assignment_queue_order(self, sample_tree):
        queue = sample_tree.get_assignment_queue()
        item_ids = [i.item_id for i in queue]
        # Bucket 1 (rank=1) ready items first, then bucket 2, then bucket 4
        assert item_ids == ["test-1", "fix-1", "feat-1"]

    def test_assignment_queue_excludes_blocked(self, sample_tree):
        queue = sample_tree.get_assignment_queue()
        # test-2 is blocked, should not appear
        assert all(i.item_id != "test-2" for i in queue)

    def test_empty_tree_queue(self):
        tree = BucketTree(tree_id="t", project_id="p")
        assert tree.get_assignment_queue() == []

    def test_all_blocked_empty_queue(self, testing_bucket_def):
        tree = BucketTree(
            tree_id="t",
            project_id="p",
            buckets=[
                PriorityBucket(
                    bucket_id="a",
                    rank=1,
                    definition=testing_bucket_def,
                    items=[
                        BucketItem(item_id="x", readiness=ItemReadiness.BLOCKED),
                    ],
                ),
            ],
        )
        assert tree.get_assignment_queue() == []

    def test_queue_respects_intra_bucket_order(self):
        """Items within a bucket should be sorted by sort_key."""
        defn = BucketDefinition(name="Test")
        tree = BucketTree(
            tree_id="t",
            project_id="p",
            buckets=[
                PriorityBucket(
                    bucket_id="a",
                    rank=1,
                    definition=defn,
                    items=[
                        BucketItem(
                            item_id="low",
                            readiness=ItemReadiness.READY,
                            priority_score=0.1,
                            blocking_count=0,
                        ),
                        BucketItem(
                            item_id="high",
                            readiness=ItemReadiness.READY,
                            priority_score=0.9,
                            blocking_count=5,
                        ),
                    ],
                ),
            ],
        )
        queue = tree.get_assignment_queue()
        assert queue[0].item_id == "high"
        assert queue[1].item_id == "low"


# ============================================================================
# Serialization Tests
# ============================================================================


class TestSerialization:
    """Test JSON serialization/deserialization."""

    def test_tree_roundtrip(self, sample_tree):
        json_data = sample_tree.model_dump()
        restored = BucketTree(**json_data)

        assert restored.tree_id == sample_tree.tree_id
        assert restored.project_id == sample_tree.project_id
        assert len(restored.buckets) == len(sample_tree.buckets)
        assert restored.version == sample_tree.version

    def test_bucket_roundtrip(self, sample_bucket):
        json_data = sample_bucket.model_dump()
        restored = PriorityBucket(**json_data)

        assert restored.bucket_id == sample_bucket.bucket_id
        assert restored.rank == sample_bucket.rank
        assert len(restored.items) == len(sample_bucket.items)

    def test_nested_criteria_roundtrip(self, blocker_bucket_def):
        json_data = blocker_bucket_def.model_dump()
        restored = BucketDefinition(**json_data)

        assert restored.name == blocker_bucket_def.name
        assert len(restored.criteria) == 1
        assert restored.criteria[0].criterion_type == BucketCriterionType.MATCH_ANY
        assert len(restored.criteria[0].nested) == 2

    def test_tree_to_json_string(self, sample_tree):
        json_str = sample_tree.model_dump_json()
        assert isinstance(json_str, str)
        assert "tree-001" in json_str
        assert "bucket-validate" in json_str

    def test_reorganization_event_roundtrip(self):
        event = ReorganizationEvent(
            event_id="reorg-001",
            trigger_type=ReorganizationTriggerType.PROFILE_SHIFT,
            trigger_source_id="goal-002",
            items_moved=5,
        )
        json_data = event.model_dump()
        restored = ReorganizationEvent(**json_data)
        assert restored.event_id == event.event_id
        assert restored.items_moved == 5
