"""Tests for FeedbackAggregationService — signal processing, pattern detection, and profile updates.

Tests cover:
- Individual signal processing (blocker, challenge, requirement)
- Pattern detection when threshold is met
- Profile policy adjustments for individual signals
- Profile weight shifts for detected patterns
- Decision trace logging
- Severity-based adjustment scaling
- Query methods (get_signals, get_patterns, get_decision_trace)
- Redis persistence
- Global instance management
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.feedback import (
    DecisionTraceEntry,
    FeedbackPattern,
    FeedbackSeverity,
    FeedbackSignal,
    FeedbackType,
)
from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    PlannerProfile,
    ProfileWeights,
    WeightedValue,
)
from models.work_map import Goal, GoalStatus, IssuePriority
from services.feedback_aggregation_service import (
    PATTERN_THRESHOLD,
    FeedbackAggregationService,
    get_feedback_aggregation_service,
    set_feedback_aggregation_service,
)
from services.planner_profile_service import (
    PlannerProfileService,
    set_planner_profile_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service():
    """FeedbackAggregationService with no Redis."""
    return FeedbackAggregationService(redis_client=None)


@pytest.fixture
def profile_service():
    """PlannerProfileService with mocked Redis, registered globally."""
    svc = PlannerProfileService(redis_client=None)
    svc._save_profile_to_redis = AsyncMock()
    svc._save_profile_history = AsyncMock()
    set_planner_profile_service(svc)
    yield svc
    set_planner_profile_service(None)


@pytest.fixture
def expansion_goal():
    """A goal with expansion intent."""
    return Goal(
        goal_id="goal_expand_001",
        title="Build new payment processing system",
        description="Create and implement a new payment gateway",
        project_id="project-001",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
    )


@pytest.fixture
def blocker_signal():
    """A blocker feedback signal."""
    return FeedbackSignal(
        signal_id="sig_blocker_001",
        project_id="project-001",
        worker_id="compute-001",
        task_id="work-100",
        feedback_type=FeedbackType.BLOCKER,
        severity=FeedbackSeverity.HIGH,
        description="Cannot proceed due to missing API dependency",
        data={
            "blocker_type": "dependency",
            "blocking_work_id": "work-050",
        },
    )


@pytest.fixture
def challenge_signal():
    """A challenge feedback signal."""
    return FeedbackSignal(
        signal_id="sig_challenge_001",
        project_id="project-001",
        worker_id="compute-002",
        task_id="work-200",
        feedback_type=FeedbackType.CHALLENGE,
        severity=FeedbackSeverity.MEDIUM,
        description="Task scope is significantly larger than estimated",
        data={
            "challenge_type": "complexity_increase",
            "cluster_id": "cluster-payments",
        },
    )


@pytest.fixture
def requirement_signal():
    """A requirement feedback signal."""
    return FeedbackSignal(
        signal_id="sig_req_001",
        project_id="project-001",
        worker_id="compute-003",
        task_id="work-300",
        feedback_type=FeedbackType.REQUIREMENT,
        severity=FeedbackSeverity.MEDIUM,
        description="New requirement discovered: need migration script",
        data={
            "new_issue_id": "issue-999",
            "priority": "P2",
        },
    )


def _make_signal(
    signal_id: str,
    project_id: str = "project-001",
    feedback_type: FeedbackType = FeedbackType.BLOCKER,
    worker_id: str = "compute-001",
    task_id: str = "work-100",
    severity: FeedbackSeverity = FeedbackSeverity.MEDIUM,
    data: dict = None,
) -> FeedbackSignal:
    """Helper to create signals with defaults."""
    return FeedbackSignal(
        signal_id=signal_id,
        project_id=project_id,
        worker_id=worker_id,
        task_id=task_id,
        feedback_type=feedback_type,
        severity=severity,
        description=f"Test signal {signal_id}",
        data=data or {},
    )


# ============================================================================
# Individual Signal Processing
# ============================================================================


class TestIndividualSignalProcessing:
    """Test processing of individual feedback signals."""

    @pytest.mark.asyncio
    async def test_process_blocker_signal(
        self, service, profile_service, expansion_goal, blocker_signal
    ):
        """Blocker signal triggers policy adjustment via profile service."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        trace, pattern = await service.process_signal(blocker_signal)

        assert trace is not None
        assert trace.trigger_type == "individual_signal"
        assert blocker_signal.signal_id in trace.source_signal_ids
        assert pattern is None

    @pytest.mark.asyncio
    async def test_process_challenge_signal(
        self, service, profile_service, expansion_goal, challenge_signal
    ):
        """Challenge signal is processed without error."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        trace, pattern = await service.process_signal(challenge_signal)

        # Challenge goes through update_for_worker_feedback which handles "challenge"
        assert trace is not None
        assert trace.trigger_type == "individual_signal"

    @pytest.mark.asyncio
    async def test_process_requirement_signal(
        self, service, profile_service, expansion_goal, requirement_signal
    ):
        """Requirement signal is processed without error."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        trace, pattern = await service.process_signal(requirement_signal)

        assert trace is not None
        assert trace.trigger_type == "individual_signal"

    @pytest.mark.asyncio
    async def test_signal_recorded(self, service, profile_service, expansion_goal, blocker_signal):
        """Signals are stored in the service."""
        await profile_service.construct_profile("project-001", [expansion_goal])
        await service.process_signal(blocker_signal)

        signals = await service.get_signals("project-001")
        assert len(signals) == 1
        assert signals[0].signal_id == "sig_blocker_001"

    @pytest.mark.asyncio
    async def test_no_profile_returns_none_trace(self, service, blocker_signal):
        """When no profile exists, trace is None."""
        # No profile service set up
        set_planner_profile_service(None)

        trace, pattern = await service.process_signal(blocker_signal)

        assert trace is None
        assert pattern is None
        # Signal is still recorded
        signals = await service.get_signals("project-001")
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_profile_version_incremented(
        self, service, profile_service, expansion_goal, blocker_signal
    ):
        """Processing a signal increments the profile version."""
        profile = await profile_service.construct_profile("project-001", [expansion_goal])
        original_version = profile.version

        await service.process_signal(blocker_signal)

        updated = await profile_service.get_profile("project-001")
        assert updated.version > original_version


# ============================================================================
# Pattern Detection
# ============================================================================


class TestPatternDetection:
    """Test pattern detection across multiple signals."""

    @pytest.mark.asyncio
    async def test_no_pattern_below_threshold(
        self, service, profile_service, expansion_goal
    ):
        """Pattern not detected below PATTERN_THRESHOLD signals."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(PATTERN_THRESHOLD - 1):
            signal = _make_signal(f"sig_{i}", feedback_type=FeedbackType.BLOCKER)
            trace, pattern = await service.process_signal(signal)
            assert pattern is None

    @pytest.mark.asyncio
    async def test_pattern_detected_at_threshold(
        self, service, profile_service, expansion_goal
    ):
        """Pattern detected when PATTERN_THRESHOLD signals of same type."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        pattern = None
        for i in range(PATTERN_THRESHOLD):
            signal = _make_signal(
                f"sig_blocker_{i}",
                worker_id=f"compute-{i}",
                feedback_type=FeedbackType.BLOCKER,
            )
            _, pattern = await service.process_signal(signal)

        assert pattern is not None
        assert pattern.feedback_type == FeedbackType.BLOCKER
        assert pattern.signal_count >= PATTERN_THRESHOLD

    @pytest.mark.asyncio
    async def test_pattern_not_mixed_types(
        self, service, profile_service, expansion_goal
    ):
        """Signals of different types don't form a pattern together."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        # 2 blockers + 1 challenge = no pattern
        for i in range(2):
            await service.process_signal(
                _make_signal(f"sig_b_{i}", feedback_type=FeedbackType.BLOCKER)
            )
        _, pattern = await service.process_signal(
            _make_signal("sig_c_0", feedback_type=FeedbackType.CHALLENGE)
        )
        assert pattern is None

    @pytest.mark.asyncio
    async def test_pattern_tracks_affected_clusters(
        self, service, profile_service, expansion_goal
    ):
        """Pattern captures affected clusters from signal data."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(PATTERN_THRESHOLD):
            signal = _make_signal(
                f"sig_ch_{i}",
                feedback_type=FeedbackType.CHALLENGE,
                data={"cluster_id": "cluster-auth"},
            )
            _, pattern = await service.process_signal(signal)

        assert pattern is not None
        assert "cluster-auth" in pattern.affected_clusters

    @pytest.mark.asyncio
    async def test_pattern_updates_existing(
        self, service, profile_service, expansion_goal
    ):
        """Additional signals after pattern detection update existing pattern."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        # Create initial pattern
        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(f"sig_{i}", feedback_type=FeedbackType.BLOCKER)
            )

        # Add one more signal
        _, pattern = await service.process_signal(
            _make_signal(f"sig_{PATTERN_THRESHOLD}", feedback_type=FeedbackType.BLOCKER)
        )

        assert pattern is not None
        assert pattern.signal_count == PATTERN_THRESHOLD + 1

    @pytest.mark.asyncio
    async def test_pattern_triggers_weight_shift(
        self, service, profile_service, expansion_goal
    ):
        """Pattern detection triggers weight shifts rather than just policy rules."""
        profile = await profile_service.construct_profile("project-001", [expansion_goal])

        # Record original bug_fix weight
        original_weight = profile.weights.get_weight("work_type", "bug_fix")

        # Trigger blocker pattern
        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(f"sig_b_{i}", feedback_type=FeedbackType.BLOCKER)
            )

        updated = await profile_service.get_profile("project-001")
        new_weight = updated.weights.get_weight("work_type", "bug_fix")
        assert new_weight > original_weight


# ============================================================================
# Profile Weight Shifts for Patterns
# ============================================================================


class TestPatternWeightShifts:
    """Test weight shifts applied when patterns are detected."""

    @pytest.mark.asyncio
    async def test_blocker_pattern_increases_bugfix_weight(
        self, service, profile_service, expansion_goal
    ):
        """Blocker pattern increases bug_fix and infrastructure weights."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(f"sig_{i}", feedback_type=FeedbackType.BLOCKER)
            )

        profile = await profile_service.get_profile("project-001")
        assert profile.weights.get_weight("work_type", "bug_fix") > 0.5
        assert profile.weights.get_weight("work_type", "infrastructure") > 0.5

    @pytest.mark.asyncio
    async def test_challenge_pattern_increases_cluster_weight(
        self, service, profile_service, expansion_goal
    ):
        """Challenge pattern affecting a cluster increases that cluster's weight."""
        profile = await profile_service.construct_profile("project-001", [expansion_goal])
        profile.weights.cluster_weights["cluster-auth"] = WeightedValue(
            weight=0.5,
            confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
        )

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(
                    f"sig_ch_{i}",
                    feedback_type=FeedbackType.CHALLENGE,
                    data={"cluster_id": "cluster-auth"},
                )
            )

        updated = await profile_service.get_profile("project-001")
        assert updated.weights.get_weight("cluster", "cluster-auth") > 0.5

    @pytest.mark.asyncio
    async def test_requirement_pattern_increases_feature_weight(
        self, service, profile_service, expansion_goal
    ):
        """Requirement pattern increases feature work type weight."""
        await profile_service.construct_profile("project-001", [expansion_goal])
        original = (await profile_service.get_profile("project-001")).weights.get_weight(
            "work_type", "feature"
        )

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(f"sig_req_{i}", feedback_type=FeedbackType.REQUIREMENT)
            )

        updated = await profile_service.get_profile("project-001")
        assert updated.weights.get_weight("work_type", "feature") >= original

    @pytest.mark.asyncio
    async def test_high_severity_larger_shift(
        self, service, profile_service, expansion_goal
    ):
        """Higher severity signals produce larger weight shifts."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(
                    f"sig_{i}",
                    feedback_type=FeedbackType.BLOCKER,
                    severity=FeedbackSeverity.CRITICAL,
                )
            )

        profile = await profile_service.get_profile("project-001")
        # Critical severity should have a bigger shift than default
        bugfix_weight = profile.weights.get_weight("work_type", "bug_fix")
        assert bugfix_weight > 0.7


# ============================================================================
# Decision Trace
# ============================================================================


class TestDecisionTrace:
    """Test decision trace logging."""

    @pytest.mark.asyncio
    async def test_individual_signal_creates_trace(
        self, service, profile_service, expansion_goal, blocker_signal
    ):
        """Individual signal creates a trace entry."""
        await profile_service.construct_profile("project-001", [expansion_goal])
        await service.process_signal(blocker_signal)

        entries = await service.get_decision_trace("project-001")
        assert len(entries) == 1
        assert entries[0].trigger_type == "individual_signal"
        assert entries[0].project_id == "project-001"

    @pytest.mark.asyncio
    async def test_pattern_creates_trace(
        self, service, profile_service, expansion_goal
    ):
        """Pattern detection creates a trace entry with pattern_id."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(f"sig_{i}", feedback_type=FeedbackType.BLOCKER)
            )

        entries = await service.get_decision_trace("project-001")
        pattern_entries = [e for e in entries if e.trigger_type == "pattern_detected"]
        assert len(pattern_entries) == 1
        assert pattern_entries[0].pattern_id is not None
        assert len(pattern_entries[0].weight_changes) > 0

    @pytest.mark.asyncio
    async def test_trace_records_version_change(
        self, service, profile_service, expansion_goal, blocker_signal
    ):
        """Trace records before/after profile versions."""
        await profile_service.construct_profile("project-001", [expansion_goal])
        await service.process_signal(blocker_signal)

        entries = await service.get_decision_trace("project-001")
        assert entries[0].previous_profile_version == 1
        assert entries[0].new_profile_version == 2


# ============================================================================
# Query Methods
# ============================================================================


class TestQueryMethods:
    """Test signal, pattern, and trace query methods."""

    @pytest.mark.asyncio
    async def test_get_signals_empty(self, service):
        signals = await service.get_signals("nonexistent")
        assert signals == []

    @pytest.mark.asyncio
    async def test_get_signals_filtered_by_type(
        self, service, profile_service, expansion_goal
    ):
        await profile_service.construct_profile("project-001", [expansion_goal])

        await service.process_signal(
            _make_signal("sig_b", feedback_type=FeedbackType.BLOCKER)
        )
        await service.process_signal(
            _make_signal("sig_c", feedback_type=FeedbackType.CHALLENGE)
        )

        blockers = await service.get_signals("project-001", FeedbackType.BLOCKER)
        assert len(blockers) == 1
        assert blockers[0].feedback_type == FeedbackType.BLOCKER

    @pytest.mark.asyncio
    async def test_get_signals_most_recent_first(
        self, service, profile_service, expansion_goal
    ):
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(5):
            await service.process_signal(
                _make_signal(f"sig_{i}", feedback_type=FeedbackType.BLOCKER)
            )

        signals = await service.get_signals("project-001")
        # Most recent should be first
        for j in range(len(signals) - 1):
            assert signals[j].timestamp >= signals[j + 1].timestamp

    @pytest.mark.asyncio
    async def test_get_signals_limit(
        self, service, profile_service, expansion_goal
    ):
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(10):
            await service.process_signal(
                _make_signal(f"sig_{i}", feedback_type=FeedbackType.BLOCKER)
            )

        signals = await service.get_signals("project-001", limit=3)
        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_get_patterns_empty(self, service):
        patterns = await service.get_patterns("nonexistent")
        assert patterns == []

    @pytest.mark.asyncio
    async def test_get_decision_trace_empty(self, service):
        trace = await service.get_decision_trace("nonexistent")
        assert trace == []


# ============================================================================
# Global Instance Management
# ============================================================================


class TestGlobalInstance:
    """Test singleton pattern for global service instance."""

    def test_get_before_set_raises(self):
        set_feedback_aggregation_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_feedback_aggregation_service()

    def test_set_and_get(self):
        svc = FeedbackAggregationService()
        set_feedback_aggregation_service(svc)
        assert get_feedback_aggregation_service() is svc
        set_feedback_aggregation_service(None)

    def test_set_none_clears(self):
        svc = FeedbackAggregationService()
        set_feedback_aggregation_service(svc)
        set_feedback_aggregation_service(None)
        with pytest.raises(RuntimeError):
            get_feedback_aggregation_service()


# ============================================================================
# Initialization
# ============================================================================


class TestInitialization:
    """Test service initialization."""

    @pytest.mark.asyncio
    async def test_initialize_without_redis(self, service):
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, service):
        await service.initialize()
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self):
        mock_redis = MagicMock()
        mock_redis._prefix = "claudevn:"
        mock_redis._redis = AsyncMock()
        mock_redis._redis.scan = AsyncMock(return_value=(0, []))

        svc = FeedbackAggregationService(redis_client=mock_redis)
        await svc.initialize()
        assert svc._initialized is True


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_weight_clamped_to_max(
        self, service, profile_service, expansion_goal
    ):
        """Weight shift doesn't exceed 1.0."""
        profile = await profile_service.construct_profile("project-001", [expansion_goal])
        profile.weights.work_type_weights["bug_fix"] = WeightedValue(
            weight=0.95,
            confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
        )

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(
                    f"sig_{i}",
                    feedback_type=FeedbackType.BLOCKER,
                    severity=FeedbackSeverity.CRITICAL,
                )
            )

        updated = await profile_service.get_profile("project-001")
        assert updated.weights.get_weight("work_type", "bug_fix") <= 1.0

    @pytest.mark.asyncio
    async def test_challenge_pattern_creates_new_cluster_weight(
        self, service, profile_service, expansion_goal
    ):
        """Challenge pattern for unknown cluster creates a new weight entry."""
        await profile_service.construct_profile("project-001", [expansion_goal])

        for i in range(PATTERN_THRESHOLD):
            await service.process_signal(
                _make_signal(
                    f"sig_ch_{i}",
                    feedback_type=FeedbackType.CHALLENGE,
                    data={"cluster_id": "cluster-new"},
                )
            )

        profile = await profile_service.get_profile("project-001")
        assert "cluster-new" in profile.weights.cluster_weights
        assert profile.weights.get_weight("cluster", "cluster-new") > 0.5

    @pytest.mark.asyncio
    async def test_multiple_projects_isolated(
        self, service, profile_service
    ):
        """Signals from different projects don't interfere."""
        goal_a = Goal(
            goal_id="goal_a", title="Build features", description="Add new things",
            project_id="project-A", priority=IssuePriority.P1, status=GoalStatus.IN_PROGRESS,
        )
        goal_b = Goal(
            goal_id="goal_b", title="Build features", description="Add new things",
            project_id="project-B", priority=IssuePriority.P1, status=GoalStatus.IN_PROGRESS,
        )
        await profile_service.construct_profile("project-A", [goal_a])
        await profile_service.construct_profile("project-B", [goal_b])

        await service.process_signal(
            _make_signal("sig_a", project_id="project-A")
        )
        await service.process_signal(
            _make_signal("sig_b", project_id="project-B")
        )

        signals_a = await service.get_signals("project-A")
        signals_b = await service.get_signals("project-B")
        assert len(signals_a) == 1
        assert len(signals_b) == 1
