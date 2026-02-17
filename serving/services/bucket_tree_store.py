"""Bucket Tree Store for Redis-backed persistence of priority bucket trees.

Provides load, save, and mutation operations for BucketTree instances.
The work orchestrator uses this store to retrieve the current bucket tree
for a project and update it after work assignments.

Reference: docs/work_management_framework.md — Section 7.3
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from models.priority_bucket import BucketTree, ItemReadiness, ReorganizationTriggerType

logger = logging.getLogger(__name__)

# Redis key prefix for bucket trees
_KEY_PREFIX = "claudevn:bucket_tree:"


class BucketTreeStore:
    """Redis-backed storage for priority bucket trees.

    One bucket tree per project. The tree is serialized as JSON and
    stored under a single Redis key per project.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _key(self, project_id: str) -> str:
        return f"{_KEY_PREFIX}{project_id}"

    async def load(self, project_id: str) -> Optional[BucketTree]:
        """Load the current bucket tree for a project.

        Returns None if no tree exists or Redis is unavailable.
        """
        if not self._redis:
            return None

        try:
            raw = await self._redis._redis.get(self._key(project_id))
            if not raw:
                return None
            data = raw.decode() if isinstance(raw, bytes) else raw
            return BucketTree(**json.loads(data))
        except Exception as e:
            logger.error(f"Error loading bucket tree for project {project_id}: {e}")
            return None

    async def save(self, tree: BucketTree) -> None:
        """Persist a bucket tree to Redis."""
        if not self._redis:
            return

        try:
            data = tree.model_dump_json()
            await self._redis._redis.set(self._key(tree.project_id), data)
        except Exception as e:
            logger.error(f"Error saving bucket tree for project {tree.project_id}: {e}")

    async def remove_item(self, project_id: str, item_id: str) -> bool:
        """Remove an assigned item from the bucket tree.

        After a work item is assigned to compute, it should be removed
        from the tree so it is not re-assigned on the next poll cycle.

        Returns True if the item was found and removed.
        """
        tree = await self.load(project_id)
        if not tree:
            return False

        removed = False
        for bucket in tree.buckets:
            before = len(bucket.items)
            bucket.items = [i for i in bucket.items if i.item_id != item_id]
            if len(bucket.items) < before:
                removed = True
                break

        if removed:
            tree.updated_at = datetime.now(timezone.utc)
            await self.save(tree)

        return removed

    async def update_item_readiness(
        self,
        project_id: str,
        item_id: str,
        readiness: ItemReadiness,
    ) -> bool:
        """Update the readiness state of an item in the tree.

        Called when dependencies are resolved and an item becomes READY.

        Returns True if the item was found and updated.
        """
        tree = await self.load(project_id)
        if not tree:
            return False

        result = tree.find_item(item_id)
        if not result:
            return False

        _bucket, item = result
        if item.readiness == readiness:
            return False  # No change needed

        item.readiness = readiness
        tree.updated_at = datetime.now(timezone.utc)
        await self.save(tree)
        return True

    async def delete(self, project_id: str) -> None:
        """Delete the bucket tree for a project."""
        if not self._redis:
            return

        try:
            await self._redis._redis.delete(self._key(project_id))
        except Exception as e:
            logger.error(f"Error deleting bucket tree for project {project_id}: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_bucket_tree_store: Optional[BucketTreeStore] = None


def get_bucket_tree_store() -> BucketTreeStore:
    """Get the global bucket tree store instance."""
    if _bucket_tree_store is None:
        raise RuntimeError("Bucket tree store not initialized")
    return _bucket_tree_store


def set_bucket_tree_store(store: Optional[BucketTreeStore]) -> None:
    """Set the global bucket tree store instance."""
    global _bucket_tree_store
    _bucket_tree_store = store


# =============================================================================
# Initial Bucket Tree Creation
# =============================================================================


async def create_initial_bucket_tree(
    project_id: str,
    decomposed_issues,
    dependency_graph,
    characterization_map=None,
    replace_existing: bool = False,
) -> bool:
    """Create the initial bucket tree for a project after decomposition.

    Called after goal decomposition creates issues. Loads (or constructs)
    the planner profile, then uses WorkPlannerService.create_bucket_tree()
    to build and persist the tree.

    All dependencies are resolved lazily; if any required service is not
    initialized, the creation is skipped gracefully.

    Args:
        project_id: Project to create bucket tree for
        decomposed_issues: List of DecomposedIssue from decomposition
        dependency_graph: Dependencies (item_id -> blocked_by list)
        characterization_map: Optional characterization results by item_id
        replace_existing: If True, rebuild even if a tree already exists
            (used by supplemental decomposition to incorporate new items)

    Returns:
        True if bucket tree was created, False if skipped
    """
    if not decomposed_issues:
        logger.debug(f"No issues for project {project_id}, skipping bucket tree creation")
        return False

    try:
        store = get_bucket_tree_store()
    except RuntimeError:
        logger.debug("Bucket tree store not initialized, skipping initial creation")
        return False

    # Check if a tree already exists — don't overwrite unless replacing
    existing_tree = await store.load(project_id)
    if existing_tree and not replace_existing:
        logger.debug(
            f"Bucket tree already exists for project {project_id} "
            f"(version {existing_tree.version}), skipping initial creation"
        )
        return False

    # Load or construct planner profile
    try:
        from services.planner_profile_service import get_planner_profile_service
        profile_service = get_planner_profile_service()
        profile = await profile_service.get_profile(project_id)

        if not profile:
            # Construct a profile from the goal(s) associated with this project
            from services.goal_service import get_goal_service
            goal_service = get_goal_service()
            active_goals = await goal_service.list_active_goals(project_id)
            if active_goals:
                profile = await profile_service.construct_profile(project_id, active_goals)
            else:
                logger.debug(
                    f"No active goals for project {project_id}, "
                    "skipping bucket tree creation"
                )
                return False
    except RuntimeError:
        logger.debug("Planner profile service not initialized, skipping bucket tree creation")
        return False

    # Create the bucket tree
    try:
        from services.work_planner import get_work_planner_service
        planner = get_work_planner_service()

        tree = await planner.create_bucket_tree(
            project_id=project_id,
            profile=profile,
            items=decomposed_issues,
            characterizations=characterization_map or {},
            dependency_graph=dependency_graph,
        )

        await store.save(tree)

        logger.info(
            f"Created initial bucket tree for project {project_id}: "
            f"{len(tree.buckets)} buckets, {tree.total_items} items, "
            f"{tree.total_ready} ready"
        )
        return True

    except Exception as e:
        logger.error(f"Error creating initial bucket tree for project {project_id}: {e}")
        return False


# =============================================================================
# Reorganization Trigger
# =============================================================================


async def trigger_bucket_tree_reorganization(
    project_id: str,
    old_profile,
    new_profile,
) -> bool:
    """Trigger bucket tree reorganization after a profile change.

    Called by the planner profile service when weights or policy rules
    shift. Evaluates whether the shift is significant enough to warrant
    reorganization, and if so, rebuilds the bucket tree.

    All dependencies are resolved lazily; if any required service is not
    initialized, the reorganization is skipped gracefully.

    Args:
        project_id: Project whose profile changed
        old_profile: Profile before the change (may be None for new profiles)
        new_profile: Profile after the change

    Returns:
        True if reorganization was performed, False if skipped
    """
    try:
        store = get_bucket_tree_store()
    except RuntimeError:
        return False

    # Load current bucket tree — if none exists, nothing to reorganize
    current_tree = await store.load(project_id)
    if not current_tree:
        logger.debug(f"No bucket tree for project {project_id}, skipping reorganization")
        return False

    # Check if the shift is significant
    try:
        from services.bucket_reorganization_service import get_bucket_reorganization_service
        reorg_service = get_bucket_reorganization_service()
    except RuntimeError:
        logger.debug("Bucket reorganization service not initialized, skipping")
        return False

    if old_profile and not reorg_service.detect_profile_shift(old_profile, new_profile):
        logger.debug(f"Profile shift for project {project_id} below threshold, skipping")
        return False

    # Determine trigger type
    trigger_type = reorg_service.detect_trigger(
        old_profile=old_profile,
        new_profile=new_profile,
    )

    # If no old profile but a tree exists, treat as initial profile alignment
    if not trigger_type and old_profile is None:
        trigger_type = ReorganizationTriggerType.PROFILE_SHIFT

    if not trigger_type:
        return False

    # Load issues for the project to feed reorganization
    try:
        from services.work_map_service import get_work_map_service
        from models.goal_decomposer import DecomposedIssue

        work_map = get_work_map_service()
        issue_response = await work_map.list_issues(project_id=project_id, limit=500)
        issues = issue_response.items

        if not issues:
            logger.debug(f"No issues for project {project_id}, skipping reorganization")
            return False

        # Convert Issue objects to DecomposedIssue for the planner
        decomposed_items = []
        dependency_graph = {}
        for issue in issues:
            decomposed_items.append(DecomposedIssue(
                temp_id=issue.issue_id,
                title=issue.title,
                description=issue.description,
                issue_type=issue.issue_type.value if hasattr(issue.issue_type, 'value') else str(issue.issue_type),
                priority=issue.priority.value if hasattr(issue.priority, 'value') else str(issue.priority),
                blocked_by=issue.depends_on,
            ))
            if issue.depends_on:
                dependency_graph[issue.issue_id] = issue.depends_on

        # Get assigned item IDs (items currently being worked on)
        assigned_item_ids = {
            issue.issue_id for issue in issues
            if issue.assigned_compute_id
        }

        # Perform reorganization (characterizations empty — separate integration gap)
        result = await reorg_service.reorganize(
            project_id=project_id,
            trigger_type=trigger_type,
            trigger_source_id=new_profile.profile_id,
            current_tree=current_tree,
            updated_profile=new_profile,
            items=decomposed_items,
            characterizations={},
            dependency_graph=dependency_graph,
            assigned_item_ids=assigned_item_ids,
        )

        # Persist the reorganized tree
        await store.save(result.tree)

        logger.info(
            f"Bucket tree reorganized for project {project_id}: "
            f"version {result.previous_version}->{result.tree.version}, "
            f"{result.event.items_moved} items moved, "
            f"{result.event.items_preserved} preserved"
        )
        return True

    except Exception as e:
        logger.error(f"Error during bucket tree reorganization for project {project_id}: {e}")
        return False
