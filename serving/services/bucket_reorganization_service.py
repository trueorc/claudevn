"""Bucket Reorganization Service for dynamic work redistribution.

When the planner profile shifts, bucket boundaries must change. Tasks
redistribute because bucket definitions change, not because individual
scores change. This service implements the reorganization mechanics:

- Trigger detection: Determines when profile changes warrant reorganization
- Bucket redefinition: Rebuilds bucket structure from updated profile
- Task redistribution: Moves items into new bucket structure efficiently
- In-progress protection: Preserves assigned work during reorganization
- Decision tracing: Records each reorganization event for auditability

Reference: docs/work_management_framework.md — Section 7.4
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from models.characterization import CharacterizationResult
from models.decision_trace import (
    DecisionContext,
    DecisionImpact,
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)
from models.goal_decomposer import DecomposedIssue
from models.planner_profile import PlannerProfile, PolicyActionType
from models.priority_bucket import (
    BucketItem,
    BucketTree,
    ItemMovement,
    PriorityBucket,
    ReorganizationEvent,
    ReorganizationResult,
    ReorganizationTriggerType,
)
from services.work_planner import WorkPlannerService

logger = logging.getLogger(__name__)

# Minimum weight delta to consider a profile shift significant
WEIGHT_SHIFT_THRESHOLD = 0.1

# Minimum number of weight changes to trigger reorganization
MIN_WEIGHT_CHANGES_FOR_REORG = 1


class BucketReorganizationService:
    """Service for reorganizing bucket trees when planner profiles shift.

    Operates on the bucket structure, not individual tasks. When called,
    it redefines buckets from the updated profile and redistributes
    items accordingly, while protecting in-progress work assignments.
    """

    def __init__(self, work_planner: Optional[WorkPlannerService] = None, redis_client=None):
        """Initialize the reorganization service.

        Args:
            work_planner: WorkPlannerService for bucket creation logic.
                Falls back to a new instance if not provided.
            redis_client: Optional Redis client for persistence.
        """
        self._work_planner = work_planner or WorkPlannerService()
        self._redis = redis_client
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("Bucket reorganization service initialized")

    def _key(self, key: str) -> str:
        """Get prefixed Redis key."""
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}reorg:{key}"

    # =========================================================================
    # Trigger Detection
    # =========================================================================

    def detect_profile_shift(
        self,
        old_profile: PlannerProfile,
        new_profile: PlannerProfile,
    ) -> bool:
        """Determine if a profile change is significant enough to reorganize.

        Compares weights between old and new profiles. A shift is
        significant when any weight category changes by more than
        WEIGHT_SHIFT_THRESHOLD.

        Args:
            old_profile: Profile before the change
            new_profile: Profile after the change

        Returns:
            True if reorganization is warranted
        """
        # Version must have changed
        if new_profile.version <= old_profile.version:
            return False

        # Check weight deltas across all categories
        shift_count = 0

        shift_count += self._count_weight_shifts(
            old_profile.weights.work_type_weights,
            new_profile.weights.work_type_weights,
        )
        shift_count += self._count_weight_shifts(
            old_profile.weights.lifecycle_stage_weights,
            new_profile.weights.lifecycle_stage_weights,
        )
        shift_count += self._count_weight_shifts(
            old_profile.weights.technical_domain_weights,
            new_profile.weights.technical_domain_weights,
        )
        shift_count += self._count_weight_shifts(
            old_profile.weights.cluster_weights,
            new_profile.weights.cluster_weights,
        )

        if shift_count >= MIN_WEIGHT_CHANGES_FOR_REORG:
            return True

        # Check for new FORCE_BUCKET policy rules
        old_force_ids = {
            r.rule_id for r in old_profile.get_enabled_rules()
            if r.action_type == PolicyActionType.FORCE_BUCKET
        }
        new_force_ids = {
            r.rule_id for r in new_profile.get_enabled_rules()
            if r.action_type == PolicyActionType.FORCE_BUCKET
        }
        if new_force_ids - old_force_ids:
            return True

        return False

    def _count_weight_shifts(
        self,
        old_weights: Dict,
        new_weights: Dict,
    ) -> int:
        """Count significant weight changes between two weight dicts.

        Args:
            old_weights: Previous weights (key -> WeightedValue)
            new_weights: Updated weights (key -> WeightedValue)

        Returns:
            Number of keys with a delta >= WEIGHT_SHIFT_THRESHOLD
        """
        count = 0
        all_keys = set(old_weights.keys()) | set(new_weights.keys())

        for key in all_keys:
            old_val = old_weights.get(key)
            new_val = new_weights.get(key)

            old_weight = old_val.weight if old_val else 0.5
            new_weight = new_val.weight if new_val else 0.5

            if abs(new_weight - old_weight) >= WEIGHT_SHIFT_THRESHOLD:
                count += 1

        return count

    def detect_trigger(
        self,
        old_profile: Optional[PlannerProfile],
        new_profile: PlannerProfile,
        new_items_added: bool = False,
        items_completed: bool = False,
        resource_changed: bool = False,
    ) -> Optional[ReorganizationTriggerType]:
        """Detect the appropriate reorganization trigger type.

        Evaluates multiple potential trigger sources and returns the
        highest-priority trigger, or None if no reorganization is needed.

        Args:
            old_profile: Profile before changes (None for first-time)
            new_profile: Profile after changes
            new_items_added: Whether new work items were added
            items_completed: Whether items were completed
            resource_changed: Whether resource availability changed

        Returns:
            The trigger type, or None if reorganization is not warranted
        """
        if old_profile and self.detect_profile_shift(old_profile, new_profile):
            return ReorganizationTriggerType.PROFILE_SHIFT

        if new_items_added:
            return ReorganizationTriggerType.NEW_ITEMS_ADDED

        if items_completed:
            return ReorganizationTriggerType.ITEMS_COMPLETED

        if resource_changed:
            return ReorganizationTriggerType.RESOURCE_CHANGE

        return None

    # =========================================================================
    # Reorganization
    # =========================================================================

    async def reorganize(
        self,
        project_id: str,
        trigger_type: ReorganizationTriggerType,
        trigger_source_id: str,
        current_tree: BucketTree,
        updated_profile: PlannerProfile,
        items: List[DecomposedIssue],
        characterizations: Dict[str, CharacterizationResult],
        dependency_graph: Dict[str, List[str]],
        assigned_item_ids: Optional[Set[str]] = None,
    ) -> ReorganizationResult:
        """Reorganize a bucket tree based on an updated planner profile.

        Redefines buckets from the new profile and redistributes tasks.
        In-progress items (those in assigned_item_ids) are preserved in
        their current bucket positions where possible.

        Args:
            project_id: Project being reorganized
            trigger_type: What caused this reorganization
            trigger_source_id: ID of the trigger source (goal, worker, etc.)
            current_tree: The existing bucket tree to reorganize
            updated_profile: The new planner profile driving bucket definitions
            items: All decomposed issues in the project
            characterizations: Characterization results by item_id
            dependency_graph: Dependencies (item_id -> blocked_by list)
            assigned_item_ids: Item IDs currently assigned to compute
                instances. These items are protected from movement.

        Returns:
            ReorganizationResult with the new tree and event details
        """
        assigned = assigned_item_ids or set()
        previous_version = current_tree.version
        old_placements = self._extract_placements(current_tree)

        logger.info(
            f"Reorganizing bucket tree for project {project_id}: "
            f"trigger={trigger_type.value}, assigned={len(assigned)}, "
            f"items={len(items)}"
        )

        # Step 1: Build new bucket tree from updated profile
        new_tree = await self._work_planner.create_bucket_tree(
            project_id=project_id,
            profile=updated_profile,
            items=items,
            characterizations=characterizations,
            dependency_graph=dependency_graph,
        )

        # Step 2: Protect in-progress items by restoring their positions
        preserved_ids = self._protect_assigned_items(
            new_tree=new_tree,
            old_placements=old_placements,
            current_tree=current_tree,
            assigned_item_ids=assigned,
        )

        # Step 3: Re-sort all buckets after adjustments
        for bucket in new_tree.buckets:
            bucket.sort_items()

        # Step 4: Compute movement diff
        new_placements = self._extract_placements(new_tree)
        movements = self._compute_movements(old_placements, new_placements, assigned)

        # Step 5: Create reorganization event
        old_bucket_ids = {b.bucket_id for b in current_tree.buckets}
        new_bucket_ids = {b.bucket_id for b in new_tree.buckets}

        event = ReorganizationEvent(
            event_id=f"reorg-{uuid.uuid4().hex[:12]}",
            trigger_type=trigger_type,
            trigger_source_id=trigger_source_id,
            description=self._describe_trigger(trigger_type, trigger_source_id),
            buckets_added=len(new_bucket_ids - old_bucket_ids),
            buckets_removed=len(old_bucket_ids - new_bucket_ids),
            items_moved=len(movements),
            items_preserved=len(preserved_ids),
        )

        # Step 6: Update tree metadata
        new_tree.version = previous_version + 1
        new_tree.updated_at = datetime.now(timezone.utc)
        new_tree.reorganization_history = (
            list(current_tree.reorganization_history) + [event]
        )
        new_tree.profile_id = updated_profile.profile_id

        # Step 7: Build decision trace
        moved_item_ids = [m.item_id for m in movements]
        affected_bucket_ids = list(
            {m.from_bucket_id for m in movements} | {m.to_bucket_id for m in movements}
        )
        trace = DecisionTrace(
            trace_id=f"trace-{DecisionPointType.BUCKET_REORGANIZATION.value}-{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            decision_type=DecisionPointType.BUCKET_REORGANIZATION,
            trigger=DecisionTrigger(
                trigger_type=trigger_type.value,
                source_id=trigger_source_id,
                source_type="reorganization_trigger",
                description=self._describe_trigger(trigger_type, trigger_source_id),
            ),
            context=DecisionContext(
                profile_version=current_tree.version,
                profile_id=updated_profile.profile_id,
                bucket_tree_version=previous_version,
                active_goal_ids=list(updated_profile.active_goal_ids),
            ),
            decision_summary=(
                f"Bucket reorganization triggered by {trigger_type.value}. "
                f"{len(movements)} items moved, {len(preserved_ids)} preserved. "
                f"{event.buckets_added} buckets added, {event.buckets_removed} removed."
            ),
            key_factors=self._build_reorg_key_factors(
                trigger_type, movements, preserved_ids, event
            ),
            impact=DecisionImpact(
                affected_item_ids=moved_item_ids,
                affected_bucket_ids=affected_bucket_ids,
                tree_version_before=previous_version,
                tree_version_after=new_tree.version,
                profile_version_before=current_tree.version,
                profile_version_after=new_tree.version,
            ),
        )

        # Step 8: Persist reorganization trace
        await self._save_event_to_redis(project_id, event)
        await self._save_decision_trace(trace)

        # Step 9: Record per-item TASK_MOVEMENT traces for item-level queries
        if movements:
            await self._record_task_movement_traces(
                project_id=project_id,
                movements=movements,
                old_tree=current_tree,
                new_tree=new_tree,
                trigger_type=trigger_type,
                trigger_source_id=trigger_source_id,
                reorg_trace_id=trace.trace_id,
            )

        result = ReorganizationResult(
            tree=new_tree,
            event=event,
            items_moved_detail=movements,
            items_preserved_ids=list(preserved_ids),
            previous_version=previous_version,
        )

        logger.info(
            f"Reorganization complete for project {project_id}: "
            f"version {previous_version}->{new_tree.version}, "
            f"{len(movements)} moved, {len(preserved_ids)} preserved"
        )

        return result

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _extract_placements(
        self,
        tree: BucketTree,
    ) -> Dict[str, str]:
        """Extract item -> bucket_id mapping from a tree.

        Args:
            tree: Bucket tree to extract from

        Returns:
            Dict mapping item_id to bucket_id
        """
        placements: Dict[str, str] = {}
        for bucket in tree.buckets:
            for item in bucket.items:
                placements[item.item_id] = bucket.bucket_id
        return placements

    def _protect_assigned_items(
        self,
        new_tree: BucketTree,
        old_placements: Dict[str, str],
        current_tree: BucketTree,
        assigned_item_ids: Set[str],
    ) -> List[str]:
        """Restore assigned items to their original bucket positions.

        If an assigned item was moved to a different bucket during
        redistribution, move it back to the original bucket (if it
        still exists in the new tree). If the original bucket no
        longer exists, keep the item in its new placement.

        Args:
            new_tree: The newly created tree (mutated in place)
            old_placements: item_id -> bucket_id from old tree
            current_tree: The original tree (for bucket item metadata)
            assigned_item_ids: Items to protect

        Returns:
            List of item IDs that were actually preserved
        """
        if not assigned_item_ids:
            return []

        preserved: List[str] = []
        new_bucket_ids = {b.bucket_id for b in new_tree.buckets}

        for item_id in assigned_item_ids:
            old_bucket_id = old_placements.get(item_id)
            if not old_bucket_id:
                continue  # Item wasn't in the old tree

            # Find where the item ended up in the new tree
            new_location = new_tree.find_item(item_id)
            if not new_location:
                continue  # Item wasn't placed in the new tree

            new_bucket, bucket_item = new_location

            # If it's already in the same bucket (by ID), no action needed
            if new_bucket.bucket_id == old_bucket_id:
                preserved.append(item_id)
                continue

            # If the old bucket still exists in the new tree, move item back
            if old_bucket_id in new_bucket_ids:
                old_bucket = new_tree.get_bucket(old_bucket_id)
                if old_bucket:
                    # Remove from new location
                    new_bucket.items = [
                        i for i in new_bucket.items if i.item_id != item_id
                    ]
                    # Add to old bucket
                    old_bucket.items.append(bucket_item)
                    preserved.append(item_id)
                    continue

            # Old bucket doesn't exist in new tree — keep in new placement
            # but still count as preserved (work not disrupted)
            preserved.append(item_id)

        return preserved

    def _compute_movements(
        self,
        old_placements: Dict[str, str],
        new_placements: Dict[str, str],
        assigned_item_ids: Set[str],
    ) -> List[ItemMovement]:
        """Compute which items moved between buckets.

        Only counts non-assigned items that changed buckets.

        Args:
            old_placements: item_id -> bucket_id before reorganization
            new_placements: item_id -> bucket_id after reorganization
            assigned_item_ids: Items excluded from movement counting

        Returns:
            List of ItemMovement records
        """
        movements: List[ItemMovement] = []
        all_items = set(old_placements.keys()) | set(new_placements.keys())

        for item_id in all_items:
            if item_id in assigned_item_ids:
                continue

            old_bucket = old_placements.get(item_id)
            new_bucket = new_placements.get(item_id)

            if old_bucket and new_bucket and old_bucket != new_bucket:
                movements.append(ItemMovement(
                    item_id=item_id,
                    from_bucket_id=old_bucket,
                    to_bucket_id=new_bucket,
                ))

        return movements

    def _build_reorg_key_factors(
        self,
        trigger_type: ReorganizationTriggerType,
        movements: List[ItemMovement],
        preserved_ids: List[str],
        event: ReorganizationEvent,
    ) -> List[str]:
        """Build key factors list for a reorganization decision trace."""
        factors = []

        if trigger_type == ReorganizationTriggerType.PROFILE_SHIFT:
            factors.append("Profile weights shifted, changing bucket membership criteria")
        elif trigger_type == ReorganizationTriggerType.NEW_ITEMS_ADDED:
            factors.append("New work items require bucket placement")
        elif trigger_type == ReorganizationTriggerType.ITEMS_COMPLETED:
            factors.append("Completed items may have unblocked dependencies")
        elif trigger_type == ReorganizationTriggerType.RESOURCE_CHANGE:
            factors.append("Resource availability changed, affecting capacity allocation")

        if event.buckets_added > 0 or event.buckets_removed > 0:
            factors.append(
                f"Bucket structure changed: +{event.buckets_added} -{event.buckets_removed} buckets"
            )

        if preserved_ids:
            factors.append(
                f"{len(preserved_ids)} in-progress items protected from disruption"
            )

        return factors[:3]

    def _describe_trigger(
        self,
        trigger_type: ReorganizationTriggerType,
        trigger_source_id: str,
    ) -> str:
        """Generate a human-readable description for a trigger.

        Args:
            trigger_type: The trigger type
            trigger_source_id: Source identifier

        Returns:
            Description string
        """
        descriptions = {
            ReorganizationTriggerType.PROFILE_SHIFT: (
                f"Profile weights shifted (source: {trigger_source_id})"
            ),
            ReorganizationTriggerType.NEW_ITEMS_ADDED: (
                f"New work items added to the project"
            ),
            ReorganizationTriggerType.ITEMS_COMPLETED: (
                f"Items completed, dependencies may have resolved"
            ),
            ReorganizationTriggerType.DEPENDENCY_RESOLVED: (
                f"Dependency resolved for item {trigger_source_id}"
            ),
            ReorganizationTriggerType.RESOURCE_CHANGE: (
                f"Resource availability changed (source: {trigger_source_id})"
            ),
            ReorganizationTriggerType.MANUAL: (
                f"Manual reorganization requested"
            ),
        }
        return descriptions.get(trigger_type, f"Reorganization: {trigger_type.value}")

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def _save_event_to_redis(
        self,
        project_id: str,
        event: ReorganizationEvent,
    ) -> None:
        """Persist a reorganization event to Redis."""
        if not self._redis:
            return

        try:
            key = self._key(f"events:{project_id}")
            data = event.model_dump_json()
            await self._redis._redis.lpush(key, data)
            await self._redis._redis.ltrim(key, 0, 49)  # Keep last 50
        except Exception as e:
            logger.error(f"Error saving reorganization event to Redis: {e}")

    async def _save_decision_trace(self, trace: DecisionTrace) -> None:
        """Persist a decision trace via the DecisionTraceService.

        Falls back to direct Redis storage if the service is unavailable.
        """
        try:
            from services.decision_trace_service import get_decision_trace_service
            service = get_decision_trace_service()
            await service.record_trace(trace)
        except RuntimeError:
            # Service not initialized — fall back to direct Redis storage
            if not self._redis:
                return
            try:
                key = self._key(f"trace:{trace.project_id}")
                data = trace.model_dump_json()
                await self._redis._redis.lpush(key, data)
                await self._redis._redis.ltrim(key, 0, 99)
            except Exception as e:
                logger.error(f"Error saving reorganization trace to Redis: {e}")

    async def _record_task_movement_traces(
        self,
        project_id: str,
        movements: List[ItemMovement],
        old_tree: BucketTree,
        new_tree: BucketTree,
        trigger_type: ReorganizationTriggerType,
        trigger_source_id: str,
        reorg_trace_id: str,
    ) -> None:
        """Record individual TASK_MOVEMENT traces for each moved item.

        These traces are indexed by item_id, enabling per-item
        'why is this here?' queries.
        """
        # Build bucket name/rank lookups from both trees
        bucket_info = {}
        for bucket in old_tree.buckets + new_tree.buckets:
            if bucket.bucket_id not in bucket_info:
                bucket_info[bucket.bucket_id] = {
                    "name": bucket.definition.name if bucket.definition else bucket.bucket_id,
                    "rank": bucket.rank,
                }

        for movement in movements:
            from_info = bucket_info.get(movement.from_bucket_id, {})
            to_info = bucket_info.get(movement.to_bucket_id, {})
            from_name = from_info.get("name", movement.from_bucket_id)
            to_name = to_info.get("name", movement.to_bucket_id)
            from_rank = from_info.get("rank", "?")
            to_rank = to_info.get("rank", "?")

            trace = DecisionTrace(
                trace_id=f"trace-{DecisionPointType.TASK_MOVEMENT.value}-{uuid.uuid4().hex[:12]}",
                project_id=project_id,
                decision_type=DecisionPointType.TASK_MOVEMENT,
                trigger=DecisionTrigger(
                    trigger_type=trigger_type.value,
                    source_id=trigger_source_id,
                    source_type="reorganization_trigger",
                    description=self._describe_trigger(trigger_type, trigger_source_id),
                ),
                context=DecisionContext(
                    profile_id=new_tree.profile_id,
                    bucket_tree_version=new_tree.version,
                ),
                decision_summary=(
                    f"Moved item from '{from_name}' (rank {from_rank}) "
                    f"to '{to_name}' (rank {to_rank})"
                ),
                key_factors=[
                    f"Source bucket: {from_name} (rank {from_rank})",
                    f"Destination bucket: {to_name} (rank {to_rank})",
                    f"Triggered by {trigger_type.value}",
                ],
                impact=DecisionImpact(
                    affected_item_ids=[movement.item_id],
                    affected_bucket_ids=[movement.from_bucket_id, movement.to_bucket_id],
                    tree_version_after=new_tree.version,
                ),
                related_trace_ids=[reorg_trace_id],
            )

            await self._save_decision_trace(trace)

    # =========================================================================
    # Query Methods
    # =========================================================================

    async def get_reorganization_history(
        self,
        project_id: str,
        limit: int = 20,
    ) -> List[ReorganizationEvent]:
        """Get reorganization event history for a project.

        Args:
            project_id: Project to query
            limit: Maximum events to return

        Returns:
            List of ReorganizationEvent, most recent first
        """
        if not self._redis:
            return []

        try:
            import json
            key = self._key(f"events:{project_id}")
            raw_entries = await self._redis._redis.lrange(key, 0, limit - 1)
            events = []
            for raw in raw_entries:
                data = raw.decode() if isinstance(raw, bytes) else raw
                events.append(ReorganizationEvent(**json.loads(data)))
            return events
        except Exception as e:
            logger.error(f"Error loading reorganization history: {e}")
            return []


# =============================================================================
# Global Instance
# =============================================================================


_bucket_reorganization_service: Optional[BucketReorganizationService] = None


def get_bucket_reorganization_service() -> BucketReorganizationService:
    """Get the global bucket reorganization service instance."""
    if _bucket_reorganization_service is None:
        raise RuntimeError("Bucket reorganization service not initialized")
    return _bucket_reorganization_service


def set_bucket_reorganization_service(
    service: Optional[BucketReorganizationService],
) -> None:
    """Set the global bucket reorganization service instance."""
    global _bucket_reorganization_service
    _bucket_reorganization_service = service
