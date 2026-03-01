"""Tests for multi-bucket membership in BucketTree."""

import pytest
from serving.models.priority_bucket import (
    BucketCriterion,
    BucketCriterionType,
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemReadiness,
    PriorityBucket,
)


def _make_item(item_id: str, readiness: str = "ready") -> BucketItem:
    return BucketItem(item_id=item_id, readiness=readiness, priority_score=0.5)


def _make_bucket(bucket_id: str, rank: int, name: str, items: list) -> PriorityBucket:
    return PriorityBucket(
        bucket_id=bucket_id,
        rank=rank,
        definition=BucketDefinition(name=name),
        items=items,
    )


class TestMultiBucketMembership:
    """Tests for items appearing in multiple buckets."""

    def setup_method(self):
        """Create a tree where item_a is in both bucket_1 and bucket_2."""
        self.item_a_b1 = _make_item("item_a", "ready")
        self.item_a_b2 = _make_item("item_a", "ready")
        self.item_b = _make_item("item_b", "ready")
        self.item_c = _make_item("item_c", "blocked")

        self.tree = BucketTree(
            tree_id="tree_1",
            project_id="proj_1",
            buckets=[
                _make_bucket("bucket_1", 1, "Critical", [self.item_a_b1, self.item_b]),
                _make_bucket("bucket_2", 2, "Features", [self.item_a_b2, self.item_c]),
            ],
        )

    def test_find_item_returns_highest_ranked_bucket(self):
        result = self.tree.find_item("item_a")
        assert result is not None
        bucket, item = result
        assert bucket.bucket_id == "bucket_1"
        assert item.item_id == "item_a"

    def test_find_item_buckets_returns_all(self):
        results = self.tree.find_item_buckets("item_a")
        assert len(results) == 2
        assert results[0][0].bucket_id == "bucket_1"
        assert results[1][0].bucket_id == "bucket_2"

    def test_find_item_buckets_single_bucket(self):
        results = self.tree.find_item_buckets("item_b")
        assert len(results) == 1
        assert results[0][0].bucket_id == "bucket_1"

    def test_find_item_buckets_not_found(self):
        results = self.tree.find_item_buckets("nonexistent")
        assert results == []

    def test_find_item_not_found(self):
        assert self.tree.find_item("nonexistent") is None

    def test_assignment_queue_deduplicates(self):
        """Item in multiple buckets should only appear once in queue."""
        queue = self.tree.get_assignment_queue()
        item_ids = [item.item_id for item in queue]
        assert item_ids.count("item_a") == 1
        # Should come from bucket_1 (higher priority)
        assert item_ids[0] == "item_a" or item_ids[1] == "item_a"

    def test_assignment_queue_excludes_blocked(self):
        queue = self.tree.get_assignment_queue()
        item_ids = [item.item_id for item in queue]
        assert "item_c" not in item_ids

    def test_total_items_counts_unique(self):
        # 3 unique items: item_a, item_b, item_c (item_a in 2 buckets)
        assert self.tree.total_items == 3

    def test_total_ready_counts_per_bucket(self):
        # total_ready counts per-bucket (item_a counted twice since ready in both)
        assert self.tree.total_ready == 3


class TestSingleBucketBackwardCompat:
    """Ensure single-bucket items work as before."""

    def test_find_item_single_bucket(self):
        tree = BucketTree(
            tree_id="tree_1",
            project_id="proj_1",
            buckets=[
                _make_bucket("b1", 1, "Only", [_make_item("item_x")]),
            ],
        )
        result = tree.find_item("item_x")
        assert result is not None
        assert result[0].bucket_id == "b1"

    def test_assignment_queue_single_item(self):
        tree = BucketTree(
            tree_id="tree_1",
            project_id="proj_1",
            buckets=[
                _make_bucket("b1", 1, "Only", [_make_item("item_x")]),
            ],
        )
        queue = tree.get_assignment_queue()
        assert len(queue) == 1
        assert queue[0].item_id == "item_x"
