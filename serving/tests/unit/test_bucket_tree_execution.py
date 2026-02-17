"""Tests for bucket tree execution in the work orchestrator.

Covers:
- BucketTreeStore: load, save, remove_item, update_readiness
- WorkOrchestrator: bucket tree ordering, flat priority fallback,
  item removal after assignment
- trigger_bucket_tree_reorganization: profile change triggers
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.priority_bucket import (
    BucketCriterion,
    BucketCriterionType,
    BucketDefinition,
    BucketItem,
    BucketTree,
    ItemReadiness,
    PriorityBucket,
)
from models.work_map import WorkPriority
from services.bucket_tree_store import (
    BucketTreeStore,
    get_bucket_tree_store,
    set_bucket_tree_store,
    trigger_bucket_tree_reorganization,
)
from services.work_orchestrator import WorkOrchestrator


# =============================================================================
# Fixtures
# =============================================================================


def _make_tree(project_id="proj-1", items_per_bucket=None) -> BucketTree:
    """Create a BucketTree for testing.

    Args:
        project_id: Project ID for the tree
        items_per_bucket: Dict mapping bucket index to list of
            (item_id, readiness, priority_score) tuples. Defaults to
            a 2-bucket tree with items in each.
    """
    if items_per_bucket is None:
        items_per_bucket = {
            0: [
                ("work-high-1", ItemReadiness.READY, 0.9),
                ("work-high-2", ItemReadiness.READY, 0.7),
            ],
            1: [
                ("work-low-1", ItemReadiness.READY, 0.5),
                ("work-low-2", ItemReadiness.BLOCKED, 0.8),
            ],
        }

    buckets = []
    for idx, items_data in items_per_bucket.items():
        items = [
            BucketItem(
                item_id=item_id,
                readiness=readiness,
                priority_score=score,
            )
            for item_id, readiness, score in items_data
        ]
        buckets.append(PriorityBucket(
            bucket_id=f"bucket-{idx}",
            rank=idx + 1,
            definition=BucketDefinition(
                name=f"Bucket {idx}",
                is_default=(idx == len(items_per_bucket) - 1),
            ),
            items=items,
        ))

    return BucketTree(
        tree_id="tree-test",
        project_id=project_id,
        buckets=buckets,
    )


def _make_work(work_id, project_id="proj-1", priority=WorkPriority.NORMAL):
    """Create a mock work item."""
    work = MagicMock()
    work.work_id = work_id
    work.project_id = project_id
    work.priority = priority
    work.created_at = datetime.now(timezone.utc)
    return work


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis._redis = AsyncMock()
    return redis


@pytest.fixture
def store(mock_redis):
    """Create a BucketTreeStore with mock Redis."""
    return BucketTreeStore(redis_client=mock_redis)


@pytest.fixture
def orchestrator():
    """Create a WorkOrchestrator for testing."""
    return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=5)


# =============================================================================
# BucketTreeStore Tests
# =============================================================================


class TestBucketTreeStore:
    """Test BucketTreeStore CRUD operations."""

    @pytest.mark.asyncio
    async def test_load_returns_none_without_redis(self):
        """Test load returns None when Redis is not available."""
        store = BucketTreeStore(redis_client=None)
        result = await store.load("proj-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_returns_none_when_not_found(self, store, mock_redis):
        """Test load returns None when key doesn't exist."""
        mock_redis._redis.get = AsyncMock(return_value=None)
        result = await store.load("proj-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_deserializes_tree(self, store, mock_redis):
        """Test load correctly deserializes a stored BucketTree."""
        tree = _make_tree()
        mock_redis._redis.get = AsyncMock(return_value=tree.model_dump_json())

        result = await store.load("proj-1")

        assert result is not None
        assert result.tree_id == "tree-test"
        assert result.project_id == "proj-1"
        assert len(result.buckets) == 2

    @pytest.mark.asyncio
    async def test_load_handles_error(self, store, mock_redis):
        """Test load returns None on Redis error."""
        mock_redis._redis.get = AsyncMock(side_effect=Exception("Redis down"))
        result = await store.load("proj-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_persists_tree(self, store, mock_redis):
        """Test save serializes and stores tree."""
        tree = _make_tree()
        mock_redis._redis.set = AsyncMock()

        await store.save(tree)

        mock_redis._redis.set.assert_called_once()
        call_args = mock_redis._redis.set.call_args
        assert "bucket_tree:proj-1" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_save_noop_without_redis(self):
        """Test save does nothing when Redis is not available."""
        store = BucketTreeStore(redis_client=None)
        await store.save(_make_tree())  # Should not raise

    @pytest.mark.asyncio
    async def test_remove_item_found(self, store, mock_redis):
        """Test removing an item that exists in the tree."""
        tree = _make_tree()
        mock_redis._redis.get = AsyncMock(return_value=tree.model_dump_json())
        mock_redis._redis.set = AsyncMock()

        removed = await store.remove_item("proj-1", "work-high-1")

        assert removed is True
        mock_redis._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_item_not_found(self, store, mock_redis):
        """Test removing an item that doesn't exist returns False."""
        tree = _make_tree()
        mock_redis._redis.get = AsyncMock(return_value=tree.model_dump_json())
        mock_redis._redis.set = AsyncMock()

        removed = await store.remove_item("proj-1", "nonexistent")

        assert removed is False
        mock_redis._redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_item_no_tree(self, store, mock_redis):
        """Test removing from nonexistent tree returns False."""
        mock_redis._redis.get = AsyncMock(return_value=None)

        removed = await store.remove_item("proj-1", "work-1")
        assert removed is False

    @pytest.mark.asyncio
    async def test_update_item_readiness(self, store, mock_redis):
        """Test updating readiness state of an item."""
        tree = _make_tree(items_per_bucket={
            0: [("work-1", ItemReadiness.BLOCKED, 0.5)],
        })
        mock_redis._redis.get = AsyncMock(return_value=tree.model_dump_json())
        mock_redis._redis.set = AsyncMock()

        updated = await store.update_item_readiness(
            "proj-1", "work-1", ItemReadiness.READY
        )

        assert updated is True
        mock_redis._redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_item_readiness_no_change(self, store, mock_redis):
        """Test update_item_readiness returns False when readiness unchanged."""
        tree = _make_tree(items_per_bucket={
            0: [("work-1", ItemReadiness.READY, 0.5)],
        })
        mock_redis._redis.get = AsyncMock(return_value=tree.model_dump_json())
        mock_redis._redis.set = AsyncMock()

        updated = await store.update_item_readiness(
            "proj-1", "work-1", ItemReadiness.READY
        )

        assert updated is False
        mock_redis._redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_tree(self, store, mock_redis):
        """Test deleting a tree."""
        mock_redis._redis.delete = AsyncMock()

        await store.delete("proj-1")

        mock_redis._redis.delete.assert_called_once()


class TestBucketTreeStoreGlobals:
    """Test global instance management."""

    def test_set_and_get(self):
        """Test setting and getting global store instance."""
        store = BucketTreeStore()
        set_bucket_tree_store(store)
        assert get_bucket_tree_store() is store
        set_bucket_tree_store(None)

    def test_get_raises_when_not_set(self):
        """Test get raises RuntimeError when not initialized."""
        set_bucket_tree_store(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_bucket_tree_store()


# =============================================================================
# WorkOrchestrator Bucket Tree Ordering Tests
# =============================================================================


class TestOrchestratorBucketTreeOrdering:
    """Test bucket tree-based work ordering in the orchestrator."""

    @pytest.mark.asyncio
    async def test_order_by_bucket_tree_with_tree(self, orchestrator):
        """Test items are ordered by bucket tree assignment queue."""
        tree = _make_tree()

        work_high_1 = _make_work("work-high-1")
        work_high_2 = _make_work("work-high-2")
        work_low_1 = _make_work("work-low-1")

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.load = AsyncMock(return_value=tree)
            mock_get_store.return_value = mock_store

            ordered = await orchestrator._order_by_bucket_tree(
                [work_low_1, work_high_2, work_high_1]
            )

        # Bucket-0 items first (rank 1), then bucket-1 items (rank 2)
        # work-high-1 (score 0.9) before work-high-2 (score 0.7) within bucket
        assert ordered[0].work_id == "work-high-1"
        assert ordered[1].work_id == "work-high-2"
        assert ordered[2].work_id == "work-low-1"

    @pytest.mark.asyncio
    async def test_order_by_bucket_tree_fallback_no_store(self, orchestrator):
        """Test falls back to flat priority when store not initialized."""
        work_critical = _make_work("work-c", priority=WorkPriority.CRITICAL)
        work_low = _make_work("work-l", priority=WorkPriority.LOW)

        with patch(
            "services.bucket_tree_store.get_bucket_tree_store",
            side_effect=RuntimeError("not initialized"),
        ):
            ordered = await orchestrator._order_by_bucket_tree(
                [work_low, work_critical]
            )

        assert ordered[0].work_id == "work-c"
        assert ordered[1].work_id == "work-l"

    @pytest.mark.asyncio
    async def test_order_by_bucket_tree_fallback_no_tree(self, orchestrator):
        """Test falls back to flat priority when no tree exists for project."""
        work_high = _make_work("work-h", priority=WorkPriority.HIGH)
        work_normal = _make_work("work-n", priority=WorkPriority.NORMAL)

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.load = AsyncMock(return_value=None)
            mock_get_store.return_value = mock_store

            ordered = await orchestrator._order_by_bucket_tree(
                [work_normal, work_high]
            )

        assert ordered[0].work_id == "work-h"
        assert ordered[1].work_id == "work-n"

    @pytest.mark.asyncio
    async def test_order_by_bucket_tree_mixed(self, orchestrator):
        """Test items from tree and non-tree projects are both handled."""
        tree = _make_tree(project_id="proj-with-tree")

        # Item in the tree
        work_tree = _make_work("work-high-1", project_id="proj-with-tree")
        # Item NOT in any tree
        work_notree = _make_work("work-flat", project_id="proj-no-tree",
                                  priority=WorkPriority.CRITICAL)

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.load = AsyncMock(side_effect=lambda pid: tree if pid == "proj-with-tree" else None)
            mock_get_store.return_value = mock_store

            ordered = await orchestrator._order_by_bucket_tree(
                [work_notree, work_tree]
            )

        # Tree-ordered items first, then flat-fallback items
        assert ordered[0].work_id == "work-high-1"
        assert ordered[1].work_id == "work-flat"

    @pytest.mark.asyncio
    async def test_order_by_bucket_tree_skips_blocked_items(self, orchestrator):
        """Test that blocked items in the tree are not in the assignment queue."""
        # work-low-2 is BLOCKED in the tree — should not appear in queue
        tree = _make_tree()

        work_blocked = _make_work("work-low-2")

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.load = AsyncMock(return_value=tree)
            mock_get_store.return_value = mock_store

            ordered = await orchestrator._order_by_bucket_tree([work_blocked])

        # work-low-2 is BLOCKED so won't be in assignment_queue, goes to fallback
        # It still appears in the output via flat fallback
        assert len(ordered) == 1
        assert ordered[0].work_id == "work-low-2"

    @pytest.mark.asyncio
    async def test_order_by_bucket_tree_items_not_in_tree(self, orchestrator):
        """Test items with work_ids not matching any tree items fall to flat sort."""
        tree = _make_tree()

        work_unknown = _make_work("work-unknown", priority=WorkPriority.HIGH)

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.load = AsyncMock(return_value=tree)
            mock_get_store.return_value = mock_store

            ordered = await orchestrator._order_by_bucket_tree([work_unknown])

        assert len(ordered) == 1
        assert ordered[0].work_id == "work-unknown"


class TestOrchestratorFlatPriority:
    """Test flat priority sorting (legacy fallback)."""

    def test_sort_by_flat_priority(self, orchestrator):
        """Test items are sorted CRITICAL > HIGH > NORMAL > LOW."""
        work_low = _make_work("w-low", priority=WorkPriority.LOW)
        work_critical = _make_work("w-crit", priority=WorkPriority.CRITICAL)
        work_normal = _make_work("w-norm", priority=WorkPriority.NORMAL)
        work_high = _make_work("w-high", priority=WorkPriority.HIGH)

        sorted_items = orchestrator._sort_by_flat_priority(
            [work_low, work_normal, work_critical, work_high]
        )

        assert sorted_items[0].work_id == "w-crit"
        assert sorted_items[1].work_id == "w-high"
        assert sorted_items[2].work_id == "w-norm"
        assert sorted_items[3].work_id == "w-low"

    def test_sort_by_flat_priority_same_priority_uses_created_at(self, orchestrator):
        """Test items with same priority are sorted by creation time."""
        earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
        later = datetime(2026, 1, 2, tzinfo=timezone.utc)

        work_old = _make_work("w-old", priority=WorkPriority.NORMAL)
        work_old.created_at = earlier
        work_new = _make_work("w-new", priority=WorkPriority.NORMAL)
        work_new.created_at = later

        sorted_items = orchestrator._sort_by_flat_priority([work_new, work_old])

        assert sorted_items[0].work_id == "w-old"
        assert sorted_items[1].work_id == "w-new"


class TestOrchestratorRemoveFromBucketTree:
    """Test item removal from bucket tree after assignment."""

    @pytest.mark.asyncio
    async def test_remove_after_assignment(self, orchestrator):
        """Test successful removal from bucket tree."""
        work = _make_work("work-1", project_id="proj-1")

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.remove_item = AsyncMock(return_value=True)
            mock_get_store.return_value = mock_store

            await orchestrator._remove_from_bucket_tree(work)

            mock_store.remove_item.assert_called_once_with("proj-1", "work-1")

    @pytest.mark.asyncio
    async def test_remove_store_not_initialized(self, orchestrator):
        """Test graceful handling when store not initialized."""
        work = _make_work("work-1")

        with patch(
            "services.bucket_tree_store.get_bucket_tree_store",
            side_effect=RuntimeError("not initialized"),
        ):
            # Should not raise
            await orchestrator._remove_from_bucket_tree(work)

    @pytest.mark.asyncio
    async def test_remove_handles_error(self, orchestrator):
        """Test graceful handling of unexpected errors."""
        work = _make_work("work-1")

        with patch("services.bucket_tree_store.get_bucket_tree_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.remove_item = AsyncMock(side_effect=Exception("Redis error"))
            mock_get_store.return_value = mock_store

            # Should not raise
            await orchestrator._remove_from_bucket_tree(work)


# =============================================================================
# Integration: _process_pending_work with bucket tree
# =============================================================================


class TestProcessPendingWorkWithBucketTree:
    """Test _process_pending_work uses bucket tree ordering."""

    @pytest.fixture
    def orchestrator(self):
        return WorkOrchestrator(poll_interval=1, max_concurrent_spawns=5)

    @pytest.mark.asyncio
    async def test_process_pending_uses_bucket_tree(self, orchestrator):
        """Test _process_pending_work calls _order_by_bucket_tree."""
        work1 = _make_work("work-1")
        work1.skill_ids = ["code-writer"]
        work1.required_skills = []
        work1.work_type = "feature"

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[work1]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={"work-1": True})
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_order_by_bucket_tree", new_callable=AsyncMock) as mock_order, \
                 patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock), \
                 patch.object(orchestrator, "_remove_from_bucket_tree", new_callable=AsyncMock):
                mock_order.return_value = [work1]

                await orchestrator._process_pending_work()

                mock_order.assert_called_once()
                # Verify the processable items were passed
                passed_items = mock_order.call_args[0][0]
                assert len(passed_items) == 1
                assert passed_items[0].work_id == "work-1"

    @pytest.mark.asyncio
    async def test_process_pending_removes_from_tree_after_spawn(self, orchestrator):
        """Test _process_pending_work removes items from tree after successful spawn."""
        work1 = _make_work("work-1")

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[work1]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={"work-1": True})
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_order_by_bucket_tree", new_callable=AsyncMock) as mock_order, \
                 patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock) as mock_spawn, \
                 patch.object(orchestrator, "_remove_from_bucket_tree", new_callable=AsyncMock) as mock_remove:
                mock_order.return_value = [work1]

                await orchestrator._process_pending_work()

                mock_spawn.assert_called_once_with(work1)
                mock_remove.assert_called_once_with(work1)

    @pytest.mark.asyncio
    async def test_process_pending_no_remove_on_spawn_failure(self, orchestrator):
        """Test item is NOT removed from tree when spawn fails."""
        work1 = _make_work("work-1")

        with patch("services.work_map_service.get_work_map_service") as mock_get_wms:
            mock_work_map = MagicMock()
            mock_work_map.list_work = AsyncMock(return_value=MagicMock(items=[work1]))
            mock_work_map.get_ready_queue = AsyncMock(return_value=[])
            mock_work_map.get_dependencies_bulk = AsyncMock(return_value={"work-1": True})
            mock_get_wms.return_value = mock_work_map

            with patch.object(orchestrator, "_order_by_bucket_tree", new_callable=AsyncMock) as mock_order, \
                 patch.object(orchestrator, "_spawn_for_work", new_callable=AsyncMock) as mock_spawn, \
                 patch.object(orchestrator, "_remove_from_bucket_tree", new_callable=AsyncMock) as mock_remove:
                mock_order.return_value = [work1]
                mock_spawn.side_effect = Exception("Spawn failed")

                await orchestrator._process_pending_work()

                mock_spawn.assert_called_once()
                mock_remove.assert_not_called()


# =============================================================================
# Bucket Tree Reorganization Trigger Tests
# =============================================================================


class TestTriggerBucketTreeReorganization:
    """Test trigger_bucket_tree_reorganization function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_store_not_initialized(self):
        """Test returns False when bucket tree store is not set."""
        set_bucket_tree_store(None)

        result = await trigger_bucket_tree_reorganization(
            "proj-1", MagicMock(), MagicMock()
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_tree(self):
        """Test returns False when no bucket tree exists for project."""
        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=None)
        set_bucket_tree_store(mock_store)

        try:
            result = await trigger_bucket_tree_reorganization(
                "proj-1", MagicMock(), MagicMock()
            )
            assert result is False
        finally:
            set_bucket_tree_store(None)

    @pytest.mark.asyncio
    async def test_returns_false_when_reorg_service_not_initialized(self):
        """Test returns False when reorganization service is not available."""
        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=_make_tree())
        set_bucket_tree_store(mock_store)

        try:
            with patch(
                "services.bucket_reorganization_service.get_bucket_reorganization_service",
                side_effect=RuntimeError("not initialized"),
            ):
                result = await trigger_bucket_tree_reorganization(
                    "proj-1", MagicMock(), MagicMock()
                )
            assert result is False
        finally:
            set_bucket_tree_store(None)

    @pytest.mark.asyncio
    async def test_returns_false_when_shift_below_threshold(self):
        """Test returns False when profile shift is below threshold."""
        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=_make_tree())
        set_bucket_tree_store(mock_store)

        try:
            with patch(
                "services.bucket_reorganization_service.get_bucket_reorganization_service"
            ) as mock_get_reorg:
                mock_reorg = MagicMock()
                mock_reorg.detect_profile_shift.return_value = False
                mock_get_reorg.return_value = mock_reorg

                old_profile = MagicMock()
                new_profile = MagicMock()

                result = await trigger_bucket_tree_reorganization(
                    "proj-1", old_profile, new_profile
                )

            assert result is False
        finally:
            set_bucket_tree_store(None)

    @pytest.mark.asyncio
    async def test_performs_reorganization(self):
        """Test full reorganization flow when shift is significant."""
        tree = _make_tree()
        new_tree = _make_tree()  # Reorganized tree

        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=tree)
        mock_store.save = AsyncMock()
        set_bucket_tree_store(mock_store)

        try:
            with patch(
                "services.bucket_reorganization_service.get_bucket_reorganization_service"
            ) as mock_get_reorg, \
                 patch(
                "services.work_map_service.get_work_map_service"
            ) as mock_get_wms:
                # Set up reorganization service
                mock_reorg = MagicMock()
                mock_reorg.detect_profile_shift.return_value = True
                from models.priority_bucket import ReorganizationTriggerType
                mock_reorg.detect_trigger.return_value = ReorganizationTriggerType.PROFILE_SHIFT
                mock_reorg.reorganize = AsyncMock(return_value=MagicMock(
                    tree=new_tree,
                    event=MagicMock(items_moved=2, items_preserved=1),
                    previous_version=1,
                ))
                mock_get_reorg.return_value = mock_reorg

                # Set up work map with issues
                mock_issue = MagicMock()
                mock_issue.issue_id = "issue-1"
                mock_issue.title = "Test issue"
                mock_issue.description = "Test"
                mock_issue.issue_type = MagicMock(value="feature")
                mock_issue.priority = MagicMock(value="P2")
                mock_issue.depends_on = []
                mock_issue.assigned_compute_id = None

                mock_wms = MagicMock()
                mock_wms.list_issues = AsyncMock(return_value=MagicMock(items=[mock_issue]))
                mock_get_wms.return_value = mock_wms

                old_profile = MagicMock()
                new_profile = MagicMock()
                new_profile.profile_id = "profile-new"

                result = await trigger_bucket_tree_reorganization(
                    "proj-1", old_profile, new_profile
                )

            assert result is True
            mock_reorg.reorganize.assert_called_once()
            mock_store.save.assert_called_once_with(new_tree)

        finally:
            set_bucket_tree_store(None)

    @pytest.mark.asyncio
    async def test_reorganization_with_no_old_profile(self):
        """Test reorganization when old_profile is None (new profile)."""
        tree = _make_tree()
        new_tree = _make_tree()

        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=tree)
        mock_store.save = AsyncMock()
        set_bucket_tree_store(mock_store)

        try:
            with patch(
                "services.bucket_reorganization_service.get_bucket_reorganization_service"
            ) as mock_get_reorg, \
                 patch(
                "services.work_map_service.get_work_map_service"
            ) as mock_get_wms:
                mock_reorg = MagicMock()
                # detect_profile_shift should NOT be called when old_profile is None
                from models.priority_bucket import ReorganizationTriggerType
                mock_reorg.detect_trigger.return_value = ReorganizationTriggerType.PROFILE_SHIFT
                mock_reorg.reorganize = AsyncMock(return_value=MagicMock(
                    tree=new_tree,
                    event=MagicMock(items_moved=0, items_preserved=0),
                    previous_version=1,
                ))
                mock_get_reorg.return_value = mock_reorg

                mock_issue = MagicMock()
                mock_issue.issue_id = "issue-1"
                mock_issue.title = "Test"
                mock_issue.description = "Test"
                mock_issue.issue_type = MagicMock(value="feature")
                mock_issue.priority = MagicMock(value="P2")
                mock_issue.depends_on = []
                mock_issue.assigned_compute_id = None

                mock_wms = MagicMock()
                mock_wms.list_issues = AsyncMock(return_value=MagicMock(items=[mock_issue]))
                mock_get_wms.return_value = mock_wms

                new_profile = MagicMock()
                new_profile.profile_id = "profile-new"

                result = await trigger_bucket_tree_reorganization(
                    "proj-1", None, new_profile
                )

            assert result is True
            # detect_profile_shift should be skipped when old_profile is None
            mock_reorg.detect_profile_shift.assert_not_called()

        finally:
            set_bucket_tree_store(None)

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self):
        """Test reorganization handles unexpected errors without raising."""
        mock_store = MagicMock()
        mock_store.load = AsyncMock(return_value=_make_tree())
        set_bucket_tree_store(mock_store)

        try:
            with patch(
                "services.bucket_reorganization_service.get_bucket_reorganization_service"
            ) as mock_get_reorg:
                mock_reorg = MagicMock()
                mock_reorg.detect_profile_shift.return_value = True
                from models.priority_bucket import ReorganizationTriggerType
                mock_reorg.detect_trigger.return_value = ReorganizationTriggerType.PROFILE_SHIFT
                mock_get_reorg.return_value = mock_reorg

                with patch(
                    "services.work_map_service.get_work_map_service",
                    side_effect=RuntimeError("WMS not available"),
                ):
                    result = await trigger_bucket_tree_reorganization(
                        "proj-1", MagicMock(), MagicMock()
                    )

            assert result is False

        finally:
            set_bucket_tree_store(None)
