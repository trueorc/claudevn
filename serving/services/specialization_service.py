"""Worker specialization boundary management service.

Manages per-worker specialization profiles, scores work-to-worker matches
based on domain affinity, tracks utilization per specialization area,
and detects imbalances across the worker pool.

With 2-3 workers, specialization boundaries are broad and deliberate.
Context affinity is the primary value driver.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from models.specialization import (
    ImbalanceSeverity,
    SpecializationImbalance,
    SpecializationProfile,
    SpecializationSummary,
    UtilizationRecord,
)

logger = logging.getLogger(__name__)

# Scoring weights
CLUSTER_MATCH_WEIGHT = 0.6
UTILIZATION_BALANCE_WEIGHT = 0.3
WORK_TYPE_MATCH_WEIGHT = 0.1


class SpecializationService:
    """Service for managing worker specialization profiles and scoring.

    Provides:
    - CRUD for specialization profiles
    - Work-to-worker match scoring
    - Utilization tracking per cluster per worker
    - Imbalance detection
    """

    def __init__(self, redis_client=None):
        """Initialize specialization service.

        Args:
            redis_client: Optional Redis client for persistence (unused in v1)
        """
        self._redis = redis_client
        # Keyed by f"{project_id}:{compute_id}"
        self._profiles: Dict[str, SpecializationProfile] = {}
        # Keyed by compute_id -> cluster_id -> UtilizationRecord
        self._utilization: Dict[str, Dict[str, UtilizationRecord]] = defaultdict(dict)

    def _profile_key(self, project_id: str, compute_id: str) -> str:
        """Build lookup key for a profile."""
        return f"{project_id}:{compute_id}"

    # ============ Profile CRUD ============

    def set_profile(
        self,
        compute_id: str,
        project_id: str,
        cluster_ids: List[str],
        preferred_work_types: Optional[List[str]] = None,
    ) -> SpecializationProfile:
        """Set or update a specialization profile for a worker.

        Args:
            compute_id: Compute instance ID
            project_id: Project ID
            cluster_ids: Domain cluster IDs this worker specializes in
            preferred_work_types: Optional preferred work types

        Returns:
            The created or updated profile
        """
        key = self._profile_key(project_id, compute_id)
        now = datetime.now(timezone.utc)

        existing = self._profiles.get(key)
        if existing:
            existing.cluster_ids = cluster_ids
            existing.preferred_work_types = preferred_work_types or []
            existing.updated_at = now
            profile = existing
        else:
            profile = SpecializationProfile(
                compute_id=compute_id,
                project_id=project_id,
                cluster_ids=cluster_ids,
                preferred_work_types=preferred_work_types or [],
                created_at=now,
                updated_at=now,
            )
            self._profiles[key] = profile

        logger.info(
            f"Set specialization profile for {compute_id} in project {project_id}: "
            f"clusters={cluster_ids}"
        )
        return profile

    def get_profile(
        self, compute_id: str, project_id: str
    ) -> Optional[SpecializationProfile]:
        """Get a specialization profile.

        Args:
            compute_id: Compute instance ID
            project_id: Project ID

        Returns:
            The profile or None
        """
        return self._profiles.get(self._profile_key(project_id, compute_id))

    def remove_profile(self, compute_id: str, project_id: str) -> bool:
        """Remove a specialization profile.

        Args:
            compute_id: Compute instance ID
            project_id: Project ID

        Returns:
            True if removed, False if not found
        """
        key = self._profile_key(project_id, compute_id)
        if key in self._profiles:
            del self._profiles[key]
            logger.info(f"Removed specialization profile for {compute_id} in project {project_id}")
            return True
        return False

    def list_profiles(self, project_id: str) -> List[SpecializationProfile]:
        """List all profiles for a project.

        Args:
            project_id: Project ID

        Returns:
            List of profiles
        """
        return [
            p for p in self._profiles.values()
            if p.project_id == project_id
        ]

    # ============ Scoring ============

    async def score_assignment(
        self,
        compute_id: str,
        work_cluster_ids: List[str],
        work_type: Optional[str],
        project_id: str,
    ) -> float:
        """Score how well a worker matches a piece of work.

        Returns a 0.0-1.0 score combining:
        - Cluster match (0.6 weight): overlap between worker profile and work clusters
        - Utilization balance (0.3 weight): prefer underutilized workers
        - Work type match (0.1 weight): preferred work types

        A worker with no profile gets a baseline score of 0.5 (generalist fallback).

        Args:
            compute_id: Compute instance ID
            work_cluster_ids: Cluster IDs associated with the work item
            work_type: Work type string (e.g., "feature", "bug_fix")
            project_id: Project ID

        Returns:
            Float score 0.0-1.0
        """
        profile = self.get_profile(compute_id, project_id)

        # No profile = generalist, gets baseline score
        if not profile:
            return 0.5

        # No cluster info on work item = can't score specialization
        if not work_cluster_ids:
            return 0.5

        # --- Cluster match score ---
        if profile.cluster_ids:
            profile_clusters = set(profile.cluster_ids)
            work_clusters = set(work_cluster_ids)
            overlap = profile_clusters & work_clusters
            cluster_score = len(overlap) / len(work_clusters) if work_clusters else 0.0
        else:
            cluster_score = 0.0

        # --- Utilization balance score ---
        utilization_score = self._compute_utilization_score(compute_id, project_id)

        # --- Work type match score ---
        work_type_score = 0.0
        if work_type and profile.preferred_work_types:
            work_type_score = 1.0 if work_type in profile.preferred_work_types else 0.0

        # Weighted combination
        total = (
            cluster_score * CLUSTER_MATCH_WEIGHT
            + utilization_score * UTILIZATION_BALANCE_WEIGHT
            + work_type_score * WORK_TYPE_MATCH_WEIGHT
        )

        return min(total, 1.0)

    def _compute_utilization_score(self, compute_id: str, project_id: str) -> float:
        """Compute utilization balance score (higher = less utilized = preferred).

        Workers with lower utilization get higher scores to balance load.

        Args:
            compute_id: Compute instance ID
            project_id: Project ID

        Returns:
            Float score 0.0-1.0
        """
        # Get all workers' total completions for this project
        all_profiles = self.list_profiles(project_id)
        if not all_profiles:
            return 0.5

        worker_totals: Dict[str, int] = {}
        for profile in all_profiles:
            cid = profile.compute_id
            records = self._utilization.get(cid, {})
            worker_totals[cid] = sum(r.tasks_completed for r in records.values())

        # Include the target worker even if not in profiles
        if compute_id not in worker_totals:
            records = self._utilization.get(compute_id, {})
            worker_totals[compute_id] = sum(r.tasks_completed for r in records.values())

        if not worker_totals:
            return 0.5

        max_total = max(worker_totals.values())
        if max_total == 0:
            return 0.5  # No work done yet, neutral score

        # Score inversely proportional to utilization
        my_total = worker_totals.get(compute_id, 0)
        return 1.0 - (my_total / max_total) if max_total > 0 else 0.5

    # ============ Utilization Tracking ============

    def record_completion(self, compute_id: str, cluster_ids: List[str]) -> None:
        """Record a task completion for utilization tracking.

        Args:
            compute_id: Compute instance ID that completed the work
            cluster_ids: Cluster IDs associated with the completed work
        """
        for cluster_id in cluster_ids:
            record = self._utilization[compute_id].get(cluster_id)
            if record:
                record.tasks_completed += 1
                record.last_completed_at = datetime.now(timezone.utc)
            else:
                self._utilization[compute_id][cluster_id] = UtilizationRecord(
                    compute_id=compute_id,
                    cluster_id=cluster_id,
                    tasks_completed=1,
                    last_completed_at=datetime.now(timezone.utc),
                )

        logger.debug(
            f"Recorded completion for {compute_id} in clusters {cluster_ids}"
        )

    def get_utilization(self, project_id: str) -> Dict[str, List[UtilizationRecord]]:
        """Get utilization records for all workers in a project.

        Args:
            project_id: Project ID

        Returns:
            Dict keyed by compute_id with list of utilization records
        """
        profiles = self.list_profiles(project_id)
        compute_ids = {p.compute_id for p in profiles}

        result: Dict[str, List[UtilizationRecord]] = {}
        for compute_id in compute_ids:
            records = self._utilization.get(compute_id, {})
            result[compute_id] = list(records.values())

        return result

    # ============ Imbalance Detection ============

    def detect_imbalances(
        self,
        project_id: str,
        known_cluster_ids: Optional[List[str]] = None,
    ) -> List[SpecializationImbalance]:
        """Detect specialization imbalances across the worker pool.

        Identifies:
        - Clusters with no assigned specialist
        - Workers with disproportionate utilization

        Args:
            project_id: Project ID
            known_cluster_ids: All known cluster IDs in the project ontology.
                If None, uses clusters referenced in profiles.

        Returns:
            List of detected imbalances
        """
        profiles = self.list_profiles(project_id)
        if not profiles:
            return []

        # Build cluster -> compute_ids mapping
        cluster_to_computes: Dict[str, List[str]] = defaultdict(list)
        all_compute_ids: Set[str] = set()
        for profile in profiles:
            all_compute_ids.add(profile.compute_id)
            for cluster_id in profile.cluster_ids:
                cluster_to_computes[cluster_id].append(profile.compute_id)

        # Determine all clusters to check
        all_clusters: Set[str] = set()
        if known_cluster_ids:
            all_clusters.update(known_cluster_ids)
        # Also include clusters referenced in profiles
        for profile in profiles:
            all_clusters.update(profile.cluster_ids)

        imbalances: List[SpecializationImbalance] = []

        # Check for uncovered clusters
        for cluster_id in all_clusters:
            assigned = cluster_to_computes.get(cluster_id, [])
            unassigned = [cid for cid in all_compute_ids if cid not in assigned]

            if not assigned:
                # No specialist for this cluster
                imbalances.append(SpecializationImbalance(
                    cluster_id=cluster_id,
                    assigned_compute_ids=[],
                    unassigned_compute_ids=list(all_compute_ids),
                    severity=ImbalanceSeverity.HIGH,
                    description=f"Cluster '{cluster_id}' has no assigned specialist",
                ))

        # Check for utilization imbalances across workers
        total_per_worker: Dict[str, int] = {}
        for compute_id in all_compute_ids:
            records = self._utilization.get(compute_id, {})
            total_per_worker[compute_id] = sum(r.tasks_completed for r in records.values())

        if total_per_worker and len(total_per_worker) > 1:
            totals = list(total_per_worker.values())
            max_total = max(totals)
            min_total = min(totals)

            if max_total > 0 and max_total > 0:
                ratio = min_total / max_total if max_total > 0 else 1.0
                if ratio < 0.3:
                    # Significant utilization imbalance
                    overloaded = [
                        cid for cid, t in total_per_worker.items()
                        if t == max_total
                    ]
                    underutilized = [
                        cid for cid, t in total_per_worker.items()
                        if t == min_total
                    ]
                    severity = (
                        ImbalanceSeverity.HIGH if ratio < 0.1
                        else ImbalanceSeverity.MEDIUM
                    )
                    imbalances.append(SpecializationImbalance(
                        cluster_id="__utilization__",
                        assigned_compute_ids=overloaded,
                        unassigned_compute_ids=underutilized,
                        utilization_ratio=ratio,
                        severity=severity,
                        description=(
                            f"Utilization imbalance: workers {overloaded} have "
                            f"{max_total} completions vs {min_total} for {underutilized} "
                            f"(ratio={ratio:.2f})"
                        ),
                    ))

        return imbalances

    # ============ Summary ============

    def get_summary(self, project_id: str) -> SpecializationSummary:
        """Get a full specialization summary for a project.

        Args:
            project_id: Project ID

        Returns:
            SpecializationSummary with profiles, utilization, and imbalances
        """
        profiles = self.list_profiles(project_id)
        utilization = self.get_utilization(project_id)
        imbalances = self.detect_imbalances(project_id)

        all_clusters: Set[str] = set()
        for profile in profiles:
            all_clusters.update(profile.cluster_ids)

        return SpecializationSummary(
            project_id=project_id,
            profiles=profiles,
            utilization=utilization,
            imbalances=imbalances,
            total_workers=len(profiles),
            total_clusters_covered=len(all_clusters),
        )


# Global instance
_specialization_service: Optional[SpecializationService] = None


def get_specialization_service() -> SpecializationService:
    """Get the global specialization service instance."""
    if _specialization_service is None:
        raise RuntimeError("Specialization service not initialized")
    return _specialization_service


def set_specialization_service(service: Optional[SpecializationService]) -> None:
    """Set the global specialization service instance."""
    global _specialization_service
    _specialization_service = service
