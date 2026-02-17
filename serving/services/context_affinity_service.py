"""Context affinity tracking service for compute instances.

Tracks which domain clusters each compute instance has built context in,
enabling smarter work assignment that preserves valuable context.

With 2-3 workers, context affinity becomes a primary assignment factor
since each worker develops deep context in their assigned areas.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.compute import AffinityEntry, ContextAffinityProfile

logger = logging.getLogger(__name__)

# Recency decay half-life in hours.
# After this many hours, a domain's recency weight drops to 0.5.
RECENCY_HALF_LIFE_HOURS = 24.0

# Weight of affinity score in assignment decisions (0.0-1.0 bonus range).
AFFINITY_WEIGHT = 0.8


class ContextAffinityService:
    """Service for tracking and scoring compute instance context affinity.

    Maintains per-instance affinity profiles that record which domain
    clusters a worker has completed tasks in, with recency weighting.
    """

    def __init__(self):
        self._profiles: Dict[str, ContextAffinityProfile] = {}

    def get_profile(self, compute_id: str) -> Optional[ContextAffinityProfile]:
        """Get the affinity profile for a compute instance."""
        return self._profiles.get(compute_id)

    def record_completion(
        self,
        compute_id: str,
        cluster_ids: List[str],
        work_type: Optional[str] = None,
    ) -> None:
        """Record a task completion to update affinity profile.

        Args:
            compute_id: Compute instance that completed the task
            cluster_ids: Domain cluster IDs from the completed work item
            work_type: Type of work completed (e.g., "feature", "bug_fix")
        """
        if not cluster_ids:
            return

        profile = self._profiles.get(compute_id)
        if not profile:
            profile = ContextAffinityProfile(compute_id=compute_id)
            self._profiles[compute_id] = profile

        now = datetime.now(timezone.utc)
        entries_by_cluster = {e.cluster_id: e for e in profile.entries}

        updated_entries = []
        for entry in profile.entries:
            if entry.cluster_id in cluster_ids:
                work_types = list(set(entry.work_types + ([work_type] if work_type else [])))
                updated_entries.append(AffinityEntry(
                    cluster_id=entry.cluster_id,
                    tasks_completed=entry.tasks_completed + 1,
                    last_completed_at=now,
                    work_types=work_types,
                ))
            else:
                updated_entries.append(entry)

        for cluster_id in cluster_ids:
            if cluster_id not in entries_by_cluster:
                updated_entries.append(AffinityEntry(
                    cluster_id=cluster_id,
                    tasks_completed=1,
                    last_completed_at=now,
                    work_types=[work_type] if work_type else [],
                ))

        self._profiles[compute_id] = ContextAffinityProfile(
            compute_id=compute_id,
            entries=updated_entries,
            total_tasks_completed=profile.total_tasks_completed + 1,
            updated_at=now,
        )

    def score_affinity(
        self,
        compute_id: str,
        work_cluster_ids: List[str],
    ) -> float:
        """Score how well a compute instance's context matches work requirements.

        Uses recency-weighted scoring: recent experience in a domain is worth
        more than stale experience. Score decays with a configurable half-life.

        Args:
            compute_id: Compute instance to score
            work_cluster_ids: Domain cluster IDs from the work item

        Returns:
            Float score 0.0-1.0 representing context affinity strength
        """
        if not work_cluster_ids:
            return 0.0

        profile = self._profiles.get(compute_id)
        if not profile or not profile.entries:
            return 0.0

        now = datetime.now(timezone.utc)
        entries_by_cluster = {e.cluster_id: e for e in profile.entries}

        total_score = 0.0
        for cluster_id in work_cluster_ids:
            entry = entries_by_cluster.get(cluster_id)
            if not entry:
                continue

            hours_since = (now - entry.last_completed_at).total_seconds() / 3600.0
            recency_weight = math.pow(0.5, hours_since / RECENCY_HALF_LIFE_HOURS)

            depth_factor = min(entry.tasks_completed / 5.0, 1.0)

            total_score += recency_weight * (0.6 + 0.4 * depth_factor)

        return min(total_score / len(work_cluster_ids), 1.0)


# Module-level singleton
_affinity_service: Optional[ContextAffinityService] = None


def get_context_affinity_service() -> ContextAffinityService:
    """Get or create the singleton ContextAffinityService."""
    global _affinity_service
    if _affinity_service is None:
        _affinity_service = ContextAffinityService()
    return _affinity_service
