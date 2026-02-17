"""Tests for ContextAffinityService."""

import pytest
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from services.context_affinity_service import (
    ContextAffinityService,
    get_context_affinity_service,
    RECENCY_HALF_LIFE_HOURS,
    AFFINITY_WEIGHT
)
from models.compute import AffinityEntry, ContextAffinityProfile


@pytest.fixture
def service():
    """Create a fresh ContextAffinityService instance."""
    return ContextAffinityService()


@pytest.fixture
def now():
    """Current timestamp for tests."""
    return datetime.now(timezone.utc)


class TestRecordCompletion:
    """Test record_completion method."""

    def test_record_completion_creates_new_profile_for_first_task(self, service, now):
        """Test that record_completion creates a new profile for the first task."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]
        work_type = "feature"

        service.record_completion(compute_id, cluster_ids, work_type)

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert profile.compute_id == compute_id
        assert len(profile.entries) == 1
        assert profile.entries[0].cluster_id == "cluster-auth"
        assert profile.entries[0].tasks_completed == 1
        assert profile.entries[0].work_types == ["feature"]
        assert profile.total_tasks_completed == 1

    def test_record_completion_increments_existing_cluster_entry(self, service):
        """Test that record_completion increments tasks_completed for existing cluster."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # First completion
        service.record_completion(compute_id, cluster_ids, "feature")

        # Second completion in same cluster
        service.record_completion(compute_id, cluster_ids, "bug_fix")

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert len(profile.entries) == 1
        assert profile.entries[0].cluster_id == "cluster-auth"
        assert profile.entries[0].tasks_completed == 2
        assert set(profile.entries[0].work_types) == {"feature", "bug_fix"}
        assert profile.total_tasks_completed == 2

    def test_record_completion_adds_new_cluster_to_existing_profile(self, service):
        """Test that record_completion adds new cluster to existing profile."""
        compute_id = "compute-001"

        # First cluster
        service.record_completion(compute_id, ["cluster-auth"], "feature")

        # Second cluster
        service.record_completion(compute_id, ["cluster-payment"], "feature")

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert len(profile.entries) == 2

        cluster_ids = {entry.cluster_id for entry in profile.entries}
        assert cluster_ids == {"cluster-auth", "cluster-payment"}

        for entry in profile.entries:
            assert entry.tasks_completed == 1

        assert profile.total_tasks_completed == 2

    def test_record_completion_merges_work_types_without_duplicates(self, service):
        """Test that record_completion merges work_types without duplicates."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # First completion with feature
        service.record_completion(compute_id, cluster_ids, "feature")

        # Second completion with feature again (should dedupe)
        service.record_completion(compute_id, cluster_ids, "feature")

        # Third completion with bug_fix
        service.record_completion(compute_id, cluster_ids, "bug_fix")

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert len(profile.entries) == 1

        # Should have both work types, but "feature" should only appear once
        work_types = profile.entries[0].work_types
        assert len(work_types) == 2
        assert set(work_types) == {"feature", "bug_fix"}

    def test_record_completion_with_empty_cluster_ids_is_no_op(self, service):
        """Test that record_completion with empty cluster_ids is a no-op."""
        compute_id = "compute-001"

        service.record_completion(compute_id, [], "feature")

        profile = service.get_profile(compute_id)
        assert profile is None

    def test_record_completion_with_none_work_type(self, service):
        """Test that record_completion works with None work_type."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        service.record_completion(compute_id, cluster_ids, None)

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert len(profile.entries) == 1
        assert profile.entries[0].work_types == []

    def test_record_completion_updates_timestamps(self, service):
        """Test that record_completion updates last_completed_at timestamp."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # Record first completion
        before = datetime.now(timezone.utc)
        service.record_completion(compute_id, cluster_ids, "feature")
        after = datetime.now(timezone.utc)

        profile = service.get_profile(compute_id)
        assert profile is not None

        # Check that timestamp is recent
        entry = profile.entries[0]
        assert before <= entry.last_completed_at <= after
        assert before <= profile.updated_at <= after

    def test_record_completion_with_multiple_clusters(self, service):
        """Test record_completion with multiple cluster_ids at once."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth", "cluster-payment", "cluster-users"]

        service.record_completion(compute_id, cluster_ids, "feature")

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert len(profile.entries) == 3
        assert profile.total_tasks_completed == 1

        for entry in profile.entries:
            assert entry.tasks_completed == 1
            assert entry.work_types == ["feature"]


class TestScoreAffinity:
    """Test score_affinity method."""

    def test_score_affinity_returns_zero_for_unknown_compute(self, service):
        """Test that score_affinity returns 0.0 for unknown compute."""
        score = service.score_affinity("unknown-compute", ["cluster-auth"])
        assert score == 0.0

    def test_score_affinity_returns_zero_for_empty_work_clusters(self, service):
        """Test that score_affinity returns 0.0 for empty work clusters."""
        compute_id = "compute-001"

        # Set up profile
        service.record_completion(compute_id, ["cluster-auth"], "feature")

        # Query with empty clusters
        score = service.score_affinity(compute_id, [])
        assert score == 0.0

    def test_score_affinity_returns_high_score_for_recent_matching_clusters(self, service):
        """Test that score_affinity returns high score for recently completed matching clusters."""
        compute_id = "compute-001"

        # Complete task just now with 5+ tasks (full depth factor)
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")

        # Score for the same cluster just completed
        score = service.score_affinity(compute_id, ["cluster-auth"])

        # Recent task (hours_since ≈ 0) → recency_weight ≈ 1.0
        # 5 tasks → depth_factor = 1.0
        # score per cluster = 1.0 * (0.6 + 0.4 * 1.0) = 1.0
        # Final score = min(1.0 / 1, 1.0) = 1.0
        assert score >= 0.98  # Account for tiny time delta
        assert score <= 1.0

    def test_score_affinity_returns_lower_score_for_stale_matching_clusters(self, service):
        """Test that score_affinity returns lower score for stale matching clusters (recency decay)."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # Create a profile with a task completed 48 hours ago
        # We'll manually construct the profile to control timestamp
        now = datetime.now(timezone.utc)
        old_timestamp = now - timedelta(hours=48)

        profile = ContextAffinityProfile(
            compute_id=compute_id,
            entries=[
                AffinityEntry(
                    cluster_id="cluster-auth",
                    tasks_completed=5,
                    last_completed_at=old_timestamp,
                    work_types=["feature"]
                )
            ],
            total_tasks_completed=5,
            updated_at=old_timestamp
        )
        service._profiles[compute_id] = profile

        # Score affinity
        score = service.score_affinity(compute_id, cluster_ids)

        # At 48 hours: recency_weight = 0.5^(48/24) = 0.5^2 = 0.25
        # depth_factor = 1.0 (5 tasks)
        # score per cluster = 0.25 * (0.6 + 0.4 * 1.0) = 0.25
        expected_score = 0.25
        assert abs(score - expected_score) < 0.01

    def test_score_affinity_returns_partial_score_for_partial_cluster_overlap(self, service):
        """Test that score_affinity returns partial score for partial cluster overlap."""
        compute_id = "compute-001"

        # Complete tasks in cluster-auth only
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "feature")

        # Request score for 2 clusters: one matching, one not
        score = service.score_affinity(compute_id, ["cluster-auth", "cluster-payment"])

        # recency ≈ 1.0, depth_factor = 1.0 for cluster-auth
        # score for cluster-auth = 1.0 * 1.0 = 1.0
        # score for cluster-payment = 0 (no entry)
        # average = 1.0 / 2 = 0.5
        assert 0.48 <= score <= 0.52

    def test_score_affinity_depth_factor_increases_with_tasks_completed(self, service):
        """Test that depth factor increases with tasks_completed up to cap."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # Test with 1 task (depth_factor = 0.2)
        service.record_completion(compute_id, cluster_ids, "feature")
        score_1 = service.score_affinity(compute_id, cluster_ids)
        # Expected: 1.0 * (0.6 + 0.4 * 0.2) = 0.68
        assert 0.66 <= score_1 <= 0.70

        # Add more tasks (depth_factor = 0.6)
        service.record_completion(compute_id, cluster_ids, "feature")
        service.record_completion(compute_id, cluster_ids, "feature")
        score_3 = service.score_affinity(compute_id, cluster_ids)
        # Expected: 1.0 * (0.6 + 0.4 * 0.6) = 0.84
        assert 0.82 <= score_3 <= 0.86

        # Add more tasks to reach cap (depth_factor = 1.0)
        service.record_completion(compute_id, cluster_ids, "feature")
        service.record_completion(compute_id, cluster_ids, "feature")
        score_5 = service.score_affinity(compute_id, cluster_ids)
        # Expected: 1.0 * (0.6 + 0.4 * 1.0) = 1.0
        assert 0.98 <= score_5 <= 1.0

        # Adding more shouldn't increase beyond cap
        service.record_completion(compute_id, cluster_ids, "feature")
        service.record_completion(compute_id, cluster_ids, "feature")
        score_7 = service.score_affinity(compute_id, cluster_ids)
        assert 0.98 <= score_7 <= 1.0

        # Verify increasing trend
        assert score_1 < score_3 < score_5
        assert score_5 <= score_7

    def test_score_affinity_recency_decay_over_time(self, service):
        """Test recency decay behavior over different time boundaries."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]
        now = datetime.now(timezone.utc)

        test_cases = [
            (0, 1.0),      # Just completed
            (24, 0.5),     # 24 hours (one half-life)
            (48, 0.25),    # 48 hours (two half-lives)
            (72, 0.125),   # 72 hours (three half-lives)
        ]

        for hours_ago, expected_recency_weight in test_cases:
            # Create profile with task completed at specific time
            timestamp = now - timedelta(hours=hours_ago)
            profile = ContextAffinityProfile(
                compute_id=f"{compute_id}-{hours_ago}h",
                entries=[
                    AffinityEntry(
                        cluster_id="cluster-auth",
                        tasks_completed=5,  # Full depth factor
                        last_completed_at=timestamp,
                        work_types=["feature"]
                    )
                ],
                total_tasks_completed=5,
                updated_at=timestamp
            )
            service._profiles[f"{compute_id}-{hours_ago}h"] = profile

            # Calculate score
            score = service.score_affinity(f"{compute_id}-{hours_ago}h", cluster_ids)

            # Expected score = recency_weight * 1.0 (full depth)
            expected_score = expected_recency_weight * 1.0

            assert abs(score - expected_score) < 0.02, \
                f"At {hours_ago}h: expected {expected_score}, got {score}"

    def test_score_affinity_capped_at_one(self, service):
        """Test that score_affinity is capped at 1.0 even with perfect match."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # Create perfect scenario: many tasks, very recent
        for _ in range(10):
            service.record_completion(compute_id, cluster_ids, "feature")

        score = service.score_affinity(compute_id, cluster_ids)
        assert score <= 1.0

    def test_score_affinity_with_no_matching_clusters(self, service):
        """Test score_affinity when none of the requested clusters match."""
        compute_id = "compute-001"

        # Complete tasks in cluster-auth
        service.record_completion(compute_id, ["cluster-auth"], "feature")

        # Request score for different cluster
        score = service.score_affinity(compute_id, ["cluster-payment"])

        # No matching clusters → score = 0
        assert score == 0.0


class TestAssignmentIntegration:
    """Test integration with assignment service."""

    def test_affinity_score_is_added_to_candidate_scoring(self, service):
        """Test that affinity score is added to candidate scoring in get_next_assignment."""
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # Build affinity
        for _ in range(5):
            service.record_completion(compute_id, cluster_ids, "feature")

        # Get affinity score
        affinity_score = service.score_affinity(compute_id, cluster_ids)

        # Verify score is significant and would affect assignment
        assert affinity_score > 0.9

        # Simulate integration: base_score + (affinity_score * AFFINITY_WEIGHT)
        base_score = 2.0
        adjusted_score = base_score + (affinity_score * AFFINITY_WEIGHT)

        # Should add ~0.8 to base score
        assert adjusted_score > base_score
        assert abs(adjusted_score - (base_score + 0.8)) < 0.1

    @pytest.mark.asyncio
    async def test_worker_with_matching_affinity_is_preferred(self):
        """Test that worker with matching affinity is preferred over worker without."""
        from services.assignment_service import AssignmentService
        from models.work_map import WorkItem, WorkStatus, WorkPriority

        # Create assignment service
        assignment_service = AssignmentService(redis_client=None)
        await assignment_service.initialize()

        # Create affinity service with profile
        affinity_service = ContextAffinityService()

        # Build strong affinity for compute-001 in cluster-auth
        for _ in range(5):
            affinity_service.record_completion("compute-001", ["cluster-auth"], "feature")

        # Create two work items: one matching affinity, one not
        work_matching = WorkItem(
            work_id="work-matching",
            title="Auth Work",
            description="Work in auth cluster",
            project_id="proj-001",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.PENDING,
            tags=["cluster-auth"],  # Matches affinity
            branch_name="work/matching",
            base_branch="main",
            created_at=datetime.now(timezone.utc)
        )

        work_non_matching = WorkItem(
            work_id="work-non-matching",
            title="Payment Work",
            description="Work in payment cluster",
            project_id="proj-001",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.PENDING,
            tags=["cluster-payment"],  # Does not match affinity
            branch_name="work/non-matching",
            base_branch="main",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)  # Older
        )

        # Set work items
        work_items = {
            work_matching.work_id: work_matching,
            work_non_matching.work_id: work_non_matching
        }
        assignment_service.set_work_items_reference(work_items)

        # Mock the affinity service singleton (import happens inside the function)
        with patch('services.context_affinity_service.get_context_affinity_service', return_value=affinity_service):
            # Get next assignment (provide empty capabilities list since work items have no requirements)
            assignment = await assignment_service.get_next_assignment(
                compute_id="compute-001",
                capabilities=[],
                labels=[],
                tools_available=[]
            )

            # Should get the matching work even though non-matching is older
            assert assignment is not None
            assert assignment.work_id == "work-matching"

    @pytest.mark.asyncio
    async def test_affinity_does_not_override_critical_priority_work(self):
        """Test that affinity doesn't override critical priority work."""
        from services.assignment_service import AssignmentService
        from models.work_map import WorkItem, WorkStatus, WorkPriority

        # Create assignment service
        assignment_service = AssignmentService(redis_client=None)
        await assignment_service.initialize()

        # Create affinity service with profile
        affinity_service = ContextAffinityService()

        # Build strong affinity for cluster-auth
        for _ in range(5):
            affinity_service.record_completion("compute-001", ["cluster-auth"], "feature")

        # Create critical work without affinity match
        work_critical = WorkItem(
            work_id="work-critical",
            title="Critical Payment Work",
            description="Critical work in payment cluster",
            project_id="proj-001",
            priority=WorkPriority.CRITICAL,
            status=WorkStatus.PENDING,
            tags=["cluster-payment"],  # Does not match affinity
            branch_name="work/critical",
            base_branch="main",
            created_at=datetime.now(timezone.utc)
        )

        # Create normal priority work with affinity match
        work_normal = WorkItem(
            work_id="work-normal",
            title="Normal Auth Work",
            description="Normal work in auth cluster",
            project_id="proj-001",
            priority=WorkPriority.NORMAL,
            status=WorkStatus.PENDING,
            tags=["cluster-auth"],  # Matches affinity
            branch_name="work/normal",
            base_branch="main",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )

        # Set work items
        work_items = {
            work_critical.work_id: work_critical,
            work_normal.work_id: work_normal
        }
        assignment_service.set_work_items_reference(work_items)

        # Mock the affinity service singleton (import happens inside the function)
        with patch('services.context_affinity_service.get_context_affinity_service', return_value=affinity_service):
            # Get next assignment (provide empty capabilities list since work items have no requirements)
            assignment = await assignment_service.get_next_assignment(
                compute_id="compute-001",
                capabilities=[],
                labels=[],
                tools_available=[]
            )

            # Should get critical work despite no affinity match
            assert assignment is not None
            assert assignment.work_id == "work-critical"


class TestEdgeCases:
    """Test edge cases."""

    def test_multiple_workers_with_overlapping_affinity(self, service):
        """Test multiple workers with overlapping affinity."""
        # Worker 1: Strong affinity in auth
        for _ in range(10):
            service.record_completion("compute-001", ["cluster-auth"], "feature")

        # Worker 2: Moderate affinity in auth and payment
        for _ in range(3):
            service.record_completion("compute-002", ["cluster-auth"], "feature")
        for _ in range(3):
            service.record_completion("compute-002", ["cluster-payment"], "feature")

        # Worker 3: No affinity
        # (no completions)

        # Score auth work for all workers
        score_1 = service.score_affinity("compute-001", ["cluster-auth"])
        score_2 = service.score_affinity("compute-002", ["cluster-auth"])
        score_3 = service.score_affinity("compute-003", ["cluster-auth"])

        # Worker 1 should have highest score
        assert score_1 > score_2 > score_3
        assert score_3 == 0.0

        # Score payment work
        score_1_payment = service.score_affinity("compute-001", ["cluster-payment"])
        score_2_payment = service.score_affinity("compute-002", ["cluster-payment"])

        # Worker 2 should have affinity for payment, worker 1 should not
        assert score_2_payment > score_1_payment
        assert score_1_payment == 0.0

    def test_recency_decay_behavior_over_time_boundaries(self):
        """Test recency decay behavior over precise time boundaries."""
        service = ContextAffinityService()
        compute_id = "compute-001"
        cluster_ids = ["cluster-auth"]

        # Create entries at specific timestamps
        now = datetime.now(timezone.utc)

        # Test half-life decay formula directly
        test_points = [
            (0, 1.0),           # t=0: 2^0 = 1.0
            (12, 0.707),        # t=0.5 half-lives: 2^-0.5 ≈ 0.707
            (24, 0.5),          # t=1 half-life: 2^-1 = 0.5
            (36, 0.354),        # t=1.5 half-lives: 2^-1.5 ≈ 0.354
            (48, 0.25),         # t=2 half-lives: 2^-2 = 0.25
            (96, 0.0625),       # t=4 half-lives: 2^-4 = 0.0625
        ]

        for hours_ago, expected_weight in test_points:
            timestamp = now - timedelta(hours=hours_ago)

            # Create profile
            profile = ContextAffinityProfile(
                compute_id=f"{compute_id}-{hours_ago}",
                entries=[
                    AffinityEntry(
                        cluster_id="cluster-auth",
                        tasks_completed=5,  # Full depth
                        last_completed_at=timestamp,
                        work_types=["feature"]
                    )
                ],
                total_tasks_completed=5,
                updated_at=timestamp
            )
            service._profiles[f"{compute_id}-{hours_ago}"] = profile

            # Score (depth_factor = 1.0, so score = recency_weight)
            score = service.score_affinity(f"{compute_id}-{hours_ago}", cluster_ids)

            # Verify decay
            assert abs(score - expected_weight) < 0.02, \
                f"At {hours_ago}h: expected {expected_weight}, got {score}"

    def test_get_profile_returns_none_for_unknown_compute(self, service):
        """Test that get_profile returns None for unknown compute."""
        profile = service.get_profile("unknown-compute")
        assert profile is None

    def test_singleton_pattern(self):
        """Test that get_context_affinity_service returns singleton."""
        service1 = get_context_affinity_service()
        service2 = get_context_affinity_service()

        assert service1 is service2

        # Verify they share state
        service1.record_completion("compute-001", ["cluster-auth"], "feature")
        profile = service2.get_profile("compute-001")
        assert profile is not None
        assert profile.compute_id == "compute-001"

    def test_concurrent_updates_to_same_profile(self, service):
        """Test handling of concurrent updates to same profile."""
        compute_id = "compute-001"

        # Simulate concurrent completions
        service.record_completion(compute_id, ["cluster-auth"], "feature")
        service.record_completion(compute_id, ["cluster-payment"], "feature")
        service.record_completion(compute_id, ["cluster-auth"], "bug_fix")

        profile = service.get_profile(compute_id)
        assert profile is not None
        assert len(profile.entries) == 2
        assert profile.total_tasks_completed == 3

        # Verify auth cluster has both work types
        auth_entry = next(e for e in profile.entries if e.cluster_id == "cluster-auth")
        assert auth_entry.tasks_completed == 2
        assert set(auth_entry.work_types) == {"feature", "bug_fix"}


class TestConstants:
    """Test that constants are properly defined."""

    def test_recency_half_life_hours(self):
        """Test RECENCY_HALF_LIFE_HOURS constant."""
        assert RECENCY_HALF_LIFE_HOURS == 24.0

    def test_affinity_weight(self):
        """Test AFFINITY_WEIGHT constant."""
        assert AFFINITY_WEIGHT == 0.8
