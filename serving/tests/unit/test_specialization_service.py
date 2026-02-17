"""Tests for SpecializationService."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from models.specialization import (
    ImbalanceSeverity,
    SpecializationProfile,
    UtilizationRecord,
)
from services.specialization_service import (
    SpecializationService,
    get_specialization_service,
    set_specialization_service,
)


@pytest.fixture
def service():
    """Create a specialization service for testing."""
    return SpecializationService(redis_client=None)


@pytest.fixture
def project_id():
    return "proj-001"


@pytest.fixture
def compute_a():
    return "compute-a"


@pytest.fixture
def compute_b():
    return "compute-b"


class TestSpecializationProfileCRUD:
    """Test profile create, read, update, delete operations."""

    def test_set_profile_creates_new(self, service, project_id, compute_a):
        """Setting a profile for the first time creates it."""
        profile = service.set_profile(
            compute_id=compute_a,
            project_id=project_id,
            cluster_ids=["cluster-frontend", "cluster-api"],
        )

        assert profile.compute_id == compute_a
        assert profile.project_id == project_id
        assert profile.cluster_ids == ["cluster-frontend", "cluster-api"]
        assert profile.preferred_work_types == []
        assert profile.created_at is not None
        assert profile.updated_at is not None

    def test_set_profile_updates_existing(self, service, project_id, compute_a):
        """Setting a profile again updates the existing one."""
        service.set_profile(
            compute_id=compute_a,
            project_id=project_id,
            cluster_ids=["cluster-frontend"],
        )
        profile = service.set_profile(
            compute_id=compute_a,
            project_id=project_id,
            cluster_ids=["cluster-backend", "cluster-data"],
            preferred_work_types=["bug_fix"],
        )

        assert profile.cluster_ids == ["cluster-backend", "cluster-data"]
        assert profile.preferred_work_types == ["bug_fix"]

    def test_get_profile_found(self, service, project_id, compute_a):
        """Getting an existing profile returns it."""
        service.set_profile(
            compute_id=compute_a,
            project_id=project_id,
            cluster_ids=["cluster-frontend"],
        )
        profile = service.get_profile(compute_a, project_id)
        assert profile is not None
        assert profile.compute_id == compute_a

    def test_get_profile_not_found(self, service, project_id, compute_a):
        """Getting a non-existent profile returns None."""
        profile = service.get_profile(compute_a, project_id)
        assert profile is None

    def test_remove_profile_found(self, service, project_id, compute_a):
        """Removing an existing profile returns True."""
        service.set_profile(
            compute_id=compute_a,
            project_id=project_id,
            cluster_ids=["cluster-frontend"],
        )
        result = service.remove_profile(compute_a, project_id)
        assert result is True
        assert service.get_profile(compute_a, project_id) is None

    def test_remove_profile_not_found(self, service, project_id, compute_a):
        """Removing a non-existent profile returns False."""
        result = service.remove_profile(compute_a, project_id)
        assert result is False

    def test_list_profiles_filters_by_project(self, service, compute_a, compute_b):
        """list_profiles only returns profiles for the requested project."""
        service.set_profile(compute_a, "proj-001", ["cluster-a"])
        service.set_profile(compute_b, "proj-001", ["cluster-b"])
        service.set_profile(compute_a, "proj-002", ["cluster-c"])

        profiles = service.list_profiles("proj-001")
        assert len(profiles) == 2
        compute_ids = {p.compute_id for p in profiles}
        assert compute_ids == {compute_a, compute_b}

    def test_list_profiles_empty(self, service, project_id):
        """list_profiles returns empty list when no profiles exist."""
        profiles = service.list_profiles(project_id)
        assert profiles == []

    def test_profiles_isolated_by_project(self, service, compute_a):
        """Profiles for different projects are independent."""
        service.set_profile(compute_a, "proj-001", ["cluster-a"])
        service.set_profile(compute_a, "proj-002", ["cluster-b"])

        p1 = service.get_profile(compute_a, "proj-001")
        p2 = service.get_profile(compute_a, "proj-002")
        assert p1.cluster_ids == ["cluster-a"]
        assert p2.cluster_ids == ["cluster-b"]


class TestSpecializationScoring:
    """Test work-to-worker match scoring."""

    @pytest.mark.asyncio
    async def test_no_profile_returns_baseline(self, service, project_id, compute_a):
        """Worker with no profile gets baseline score of 0.5."""
        score = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend"],
            work_type="feature",
            project_id=project_id,
        )
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_no_work_clusters_returns_baseline(self, service, project_id, compute_a):
        """Work with no cluster IDs gets baseline score of 0.5."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        score = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=[],
            work_type="feature",
            project_id=project_id,
        )
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_specialist_scores_higher_than_generalist(
        self, service, project_id, compute_a, compute_b
    ):
        """Specialist for a cluster scores higher than a worker with no profile."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        # compute_b has no profile (generalist)

        score_specialist = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend"],
            work_type=None,
            project_id=project_id,
        )
        score_generalist = await service.score_assignment(
            compute_id=compute_b,
            work_cluster_ids=["cluster-frontend"],
            work_type=None,
            project_id=project_id,
        )

        assert score_specialist > score_generalist

    @pytest.mark.asyncio
    async def test_full_cluster_match_scores_high(self, service, project_id, compute_a):
        """Full cluster overlap scores highest."""
        service.set_profile(compute_a, project_id, ["cluster-frontend", "cluster-api"])

        score = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend"],
            work_type=None,
            project_id=project_id,
        )
        # Cluster match = 1.0 (full overlap), utilization = 0.5 (neutral), work type = 0.0
        # Total = 1.0 * 0.6 + 0.5 * 0.3 + 0.0 = 0.75
        assert score > 0.7

    @pytest.mark.asyncio
    async def test_partial_cluster_match(self, service, project_id, compute_a):
        """Partial cluster match scores proportionally."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])

        score = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend", "cluster-backend"],
            work_type=None,
            project_id=project_id,
        )
        # Cluster match = 0.5 (1 of 2 clusters), utilization = 0.5, work type = 0.0
        # Total = 0.5 * 0.6 + 0.5 * 0.3 + 0.0 = 0.45
        assert 0.3 < score < 0.6

    @pytest.mark.asyncio
    async def test_no_cluster_match_scores_low(self, service, project_id, compute_a):
        """Zero cluster overlap scores lowest for a specialized worker."""
        service.set_profile(compute_a, project_id, ["cluster-data"])

        score = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend"],
            work_type=None,
            project_id=project_id,
        )
        # Cluster match = 0.0, utilization = 0.5, work type = 0.0
        # Total = 0.0 * 0.6 + 0.5 * 0.3 + 0.0 = 0.15
        assert score < 0.3

    @pytest.mark.asyncio
    async def test_work_type_match_adds_bonus(self, service, project_id, compute_a):
        """Preferred work type adds a small score bonus."""
        service.set_profile(
            compute_a, project_id, ["cluster-frontend"],
            preferred_work_types=["bug_fix"],
        )

        score_with_match = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend"],
            work_type="bug_fix",
            project_id=project_id,
        )
        score_without_match = await service.score_assignment(
            compute_id=compute_a,
            work_cluster_ids=["cluster-frontend"],
            work_type="feature",
            project_id=project_id,
        )

        assert score_with_match > score_without_match

    @pytest.mark.asyncio
    async def test_generalist_still_gets_work(self, service, project_id, compute_b):
        """Workers without profiles still receive a non-zero score."""
        score = await service.score_assignment(
            compute_id=compute_b,
            work_cluster_ids=["cluster-frontend"],
            work_type="feature",
            project_id=project_id,
        )
        assert score == 0.5  # Baseline, not zero


class TestUtilizationTracking:
    """Test utilization recording and retrieval."""

    def test_record_completion_increments(self, service, compute_a):
        """Recording completions increments the counter."""
        service.record_completion(compute_a, ["cluster-frontend"])
        service.record_completion(compute_a, ["cluster-frontend"])
        service.record_completion(compute_a, ["cluster-backend"])

        records = service._utilization[compute_a]
        assert records["cluster-frontend"].tasks_completed == 2
        assert records["cluster-backend"].tasks_completed == 1

    def test_record_completion_sets_timestamp(self, service, compute_a):
        """Recording completion sets last_completed_at."""
        service.record_completion(compute_a, ["cluster-frontend"])

        record = service._utilization[compute_a]["cluster-frontend"]
        assert record.last_completed_at is not None

    def test_get_utilization_returns_project_workers(
        self, service, project_id, compute_a, compute_b
    ):
        """get_utilization only returns data for workers with profiles."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-backend"])

        service.record_completion(compute_a, ["cluster-frontend"])
        service.record_completion(compute_b, ["cluster-backend"])
        service.record_completion("compute-c", ["cluster-data"])  # No profile

        utilization = service.get_utilization(project_id)
        assert compute_a in utilization
        assert compute_b in utilization
        assert "compute-c" not in utilization

    @pytest.mark.asyncio
    async def test_overloaded_worker_scores_lower(
        self, service, project_id, compute_a, compute_b
    ):
        """Worker with higher utilization scores lower due to balance penalty."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-frontend"])

        # Overload compute_a
        for _ in range(10):
            service.record_completion(compute_a, ["cluster-frontend"])
        # compute_b has done nothing

        score_a = await service.score_assignment(
            compute_a, ["cluster-frontend"], None, project_id
        )
        score_b = await service.score_assignment(
            compute_b, ["cluster-frontend"], None, project_id
        )

        # Both match on cluster, but B should score higher due to utilization balance
        assert score_b > score_a


class TestImbalanceDetection:
    """Test imbalance detection logic."""

    def test_no_profiles_returns_empty(self, service, project_id):
        """No profiles means no imbalances."""
        imbalances = service.detect_imbalances(project_id)
        assert imbalances == []

    def test_detects_uncovered_cluster(
        self, service, project_id, compute_a, compute_b
    ):
        """Detects when a known cluster has no specialist."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-frontend"])

        imbalances = service.detect_imbalances(
            project_id,
            known_cluster_ids=["cluster-frontend", "cluster-backend"],
        )

        # cluster-backend has no specialist
        uncovered = [i for i in imbalances if i.cluster_id == "cluster-backend"]
        assert len(uncovered) == 1
        assert uncovered[0].severity == ImbalanceSeverity.HIGH
        assert uncovered[0].assigned_compute_ids == []

    def test_no_imbalance_when_clusters_covered(
        self, service, project_id, compute_a, compute_b
    ):
        """No uncovered-cluster imbalance when all clusters have a specialist."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-backend"])

        imbalances = service.detect_imbalances(
            project_id,
            known_cluster_ids=["cluster-frontend", "cluster-backend"],
        )

        uncovered = [i for i in imbalances if i.cluster_id != "__utilization__"]
        assert len(uncovered) == 0

    def test_detects_utilization_imbalance(
        self, service, project_id, compute_a, compute_b
    ):
        """Detects when one worker handles disproportionate share."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-backend"])

        # Overload compute_a heavily
        for _ in range(20):
            service.record_completion(compute_a, ["cluster-frontend"])
        # compute_b has done nothing

        imbalances = service.detect_imbalances(project_id)

        util_imbalances = [i for i in imbalances if i.cluster_id == "__utilization__"]
        assert len(util_imbalances) == 1
        assert util_imbalances[0].utilization_ratio == 0.0

    def test_no_utilization_imbalance_when_balanced(
        self, service, project_id, compute_a, compute_b
    ):
        """No utilization imbalance when workers are balanced."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-backend"])

        for _ in range(5):
            service.record_completion(compute_a, ["cluster-frontend"])
            service.record_completion(compute_b, ["cluster-backend"])

        imbalances = service.detect_imbalances(project_id)

        util_imbalances = [i for i in imbalances if i.cluster_id == "__utilization__"]
        assert len(util_imbalances) == 0


class TestSpecializationSummary:
    """Test summary generation."""

    def test_summary_contains_all_data(
        self, service, project_id, compute_a, compute_b
    ):
        """Summary includes profiles, utilization, and imbalance data."""
        service.set_profile(compute_a, project_id, ["cluster-frontend"])
        service.set_profile(compute_b, project_id, ["cluster-backend"])
        service.record_completion(compute_a, ["cluster-frontend"])

        summary = service.get_summary(project_id)
        assert summary.project_id == project_id
        assert summary.total_workers == 2
        assert summary.total_clusters_covered == 2
        assert len(summary.profiles) == 2


class TestGlobalSingleton:
    """Test singleton get/set pattern."""

    def test_get_before_set_raises(self):
        """get_specialization_service raises if not initialized."""
        # Save current state
        from services import specialization_service as mod
        old = mod._specialization_service

        try:
            mod._specialization_service = None
            with pytest.raises(RuntimeError, match="not initialized"):
                get_specialization_service()
        finally:
            mod._specialization_service = old

    def test_set_and_get(self):
        """set then get returns the same instance."""
        from services import specialization_service as mod
        old = mod._specialization_service

        try:
            svc = SpecializationService()
            set_specialization_service(svc)
            assert get_specialization_service() is svc
        finally:
            mod._specialization_service = old

    def test_set_none_clears(self):
        """Setting None clears the service."""
        from services import specialization_service as mod
        old = mod._specialization_service

        try:
            set_specialization_service(SpecializationService())
            set_specialization_service(None)
            with pytest.raises(RuntimeError):
                get_specialization_service()
        finally:
            mod._specialization_service = old
