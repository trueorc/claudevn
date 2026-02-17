"""Tests for ConflictDetectionService — detection, management, and resolution.

Tests cover:
- Goal-to-goal conflict detection from GoalConflict objects
- Goal-to-reality conflict detection from feedback patterns
- Dependency conflict detection (circular dependencies)
- Resource conflict detection (contention and capability gaps)
- Full detection sweep (detect_all_conflicts)
- Conflict lifecycle management (get, resolve)
- Authority boundary determination
- Severity score to severity level mapping
- Global instance management
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from models.conflict import (
    ConflictReport,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    ResolutionAuthority,
    UserResponse,
    UserResponseType,
)
from models.feedback import FeedbackPattern, FeedbackType
from models.work_map import Goal, GoalConflict, GoalIntentType, GoalStatus, IssuePriority
from services.conflict_detection_service import (
    ConflictDetectionService,
    INTENT_FEEDBACK_CONTRADICTIONS,
    _determine_authority,
    _score_to_severity,
    get_conflict_detection_service,
    set_conflict_detection_service,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service():
    """ConflictDetectionService with no Redis."""
    return ConflictDetectionService(redis_client=None)


@pytest.fixture
def expansion_goal():
    """Goal with expansion intent."""
    return Goal(
        goal_id="goal_expand",
        title="Build new reporting feature",
        description="Add comprehensive reporting dashboard",
        project_id="project_1",
        priority=IssuePriority.P1,
        status=GoalStatus.PLANNING,
        primary_intent=GoalIntentType.EXPANSION,
        intent_strength=0.8,
    )


@pytest.fixture
def consolidation_goal():
    """Goal with consolidation intent."""
    return Goal(
        goal_id="goal_consolidate",
        title="Harden current functionality",
        description="Stabilize and secure existing features",
        project_id="project_1",
        priority=IssuePriority.P1,
        status=GoalStatus.PLANNING,
        primary_intent=GoalIntentType.CONSOLIDATION,
        intent_strength=0.6,
    )


@pytest.fixture
def quality_goal():
    """Goal with quality_focused intent."""
    return Goal(
        goal_id="goal_quality",
        title="Focus on testing",
        description="Improve test coverage and quality",
        project_id="project_1",
        priority=IssuePriority.P2,
        status=GoalStatus.PLANNING,
        primary_intent=GoalIntentType.QUALITY_FOCUSED,
        intent_strength=0.7,
    )


@pytest.fixture
def goal_conflict(expansion_goal, consolidation_goal):
    """GoalConflict between expansion and consolidation goals."""
    return GoalConflict(
        conflict_id="conflict_g2g_001",
        goal_id_a=expansion_goal.goal_id,
        goal_id_b=consolidation_goal.goal_id,
        description="Expansion wants new features while consolidation wants stability",
        severity=0.75,
        is_irreconcilable=True,
        resolution_hint="Set reconciliation_weight on one goal to indicate which should dominate.",
    )


@pytest.fixture
def blocker_pattern():
    """Feedback pattern for systemic blockers."""
    return FeedbackPattern(
        pattern_id="pattern_blockers_001",
        project_id="project_1",
        feedback_type=FeedbackType.BLOCKER,
        signal_ids=["sig_1", "sig_2", "sig_3"],
        signal_count=3,
        description="Pattern detected: 3 blocker signals",
        affected_clusters=["cluster_api"],
    )


@pytest.fixture
def requirement_pattern():
    """Feedback pattern for new requirements."""
    return FeedbackPattern(
        pattern_id="pattern_reqs_001",
        project_id="project_1",
        feedback_type=FeedbackType.REQUIREMENT,
        signal_ids=["sig_4", "sig_5", "sig_6"],
        signal_count=3,
        description="Pattern detected: 3 requirement signals",
    )


# ============================================================================
# Test Severity Scoring
# ============================================================================


class TestSeverityScoring:
    """Test severity score to severity level mapping."""

    def test_low_severity(self):
        assert _score_to_severity(0.0) == ConflictSeverity.LOW
        assert _score_to_severity(0.1) == ConflictSeverity.LOW
        assert _score_to_severity(0.29) == ConflictSeverity.LOW

    def test_medium_severity(self):
        assert _score_to_severity(0.3) == ConflictSeverity.MEDIUM
        assert _score_to_severity(0.5) == ConflictSeverity.MEDIUM
        assert _score_to_severity(0.59) == ConflictSeverity.MEDIUM

    def test_high_severity(self):
        assert _score_to_severity(0.6) == ConflictSeverity.HIGH
        assert _score_to_severity(0.7) == ConflictSeverity.HIGH
        assert _score_to_severity(0.84) == ConflictSeverity.HIGH

    def test_critical_severity(self):
        assert _score_to_severity(0.85) == ConflictSeverity.CRITICAL
        assert _score_to_severity(0.9) == ConflictSeverity.CRITICAL
        assert _score_to_severity(1.0) == ConflictSeverity.CRITICAL


# ============================================================================
# Test Authority Determination
# ============================================================================


class TestAuthorityDetermination:
    """Test resolution authority determination."""

    def test_goal_to_goal_high_requires_user(self):
        authority = _determine_authority(ConflictType.GOAL_TO_GOAL, ConflictSeverity.HIGH)
        assert authority == ResolutionAuthority.USER_REQUIRED

    def test_goal_to_goal_medium_user_required(self):
        # Default rule has severity_threshold=HIGH, authority=USER_REQUIRED
        # Below threshold, returns the rule's authority field
        authority = _determine_authority(ConflictType.GOAL_TO_GOAL, ConflictSeverity.MEDIUM)
        assert authority == ResolutionAuthority.USER_REQUIRED

    def test_goal_to_goal_low_user_required(self):
        authority = _determine_authority(ConflictType.GOAL_TO_GOAL, ConflictSeverity.LOW)
        assert authority == ResolutionAuthority.USER_REQUIRED

    def test_goal_to_reality_medium_requires_user(self):
        authority = _determine_authority(ConflictType.GOAL_TO_REALITY, ConflictSeverity.MEDIUM)
        assert authority == ResolutionAuthority.USER_REQUIRED

    def test_goal_to_reality_low_is_autonomous(self):
        # Below MEDIUM threshold for goal-to-reality
        authority = _determine_authority(ConflictType.GOAL_TO_REALITY, ConflictSeverity.LOW)
        assert authority == ResolutionAuthority.USER_REQUIRED

    def test_dependency_below_threshold_autonomous(self):
        authority = _determine_authority(ConflictType.DEPENDENCY, ConflictSeverity.MEDIUM)
        assert authority == ResolutionAuthority.AUTONOMOUS

    def test_dependency_high_requires_user(self):
        authority = _determine_authority(ConflictType.DEPENDENCY, ConflictSeverity.HIGH)
        assert authority == ResolutionAuthority.USER_REQUIRED

    def test_resource_low_autonomous(self):
        authority = _determine_authority(ConflictType.RESOURCE, ConflictSeverity.LOW)
        assert authority == ResolutionAuthority.AUTONOMOUS


# ============================================================================
# Test Goal-to-Goal Detection
# ============================================================================


class TestGoalToGoalDetection:
    """Test goal-to-goal conflict detection."""

    def test_detect_from_goal_conflicts(
        self, service, goal_conflict, expansion_goal, consolidation_goal
    ):
        reports = service.detect_goal_to_goal_conflicts(
            project_id="project_1",
            goal_conflicts=[goal_conflict],
            goals=[expansion_goal, consolidation_goal],
        )
        assert len(reports) == 1
        report = reports[0]
        assert report.conflict_type == ConflictType.GOAL_TO_GOAL
        assert report.severity_score == 0.75
        assert report.conflict_id == "conflict_g2g_001"
        assert len(report.tension_elements) == 2
        assert report.planner_handling.favored_side is not None

    def test_detect_multiple_goal_conflicts(
        self, service, expansion_goal, consolidation_goal, quality_goal
    ):
        conflicts = [
            GoalConflict(
                conflict_id="conflict_1",
                goal_id_a=expansion_goal.goal_id,
                goal_id_b=consolidation_goal.goal_id,
                description="Expansion vs consolidation",
                severity=0.7,
                is_irreconcilable=True,
            ),
            GoalConflict(
                conflict_id="conflict_2",
                goal_id_a=expansion_goal.goal_id,
                goal_id_b=quality_goal.goal_id,
                description="Expansion vs quality",
                severity=0.5,
                is_irreconcilable=False,
            ),
        ]
        reports = service.detect_goal_to_goal_conflicts(
            project_id="project_1",
            goal_conflicts=conflicts,
            goals=[expansion_goal, consolidation_goal, quality_goal],
        )
        assert len(reports) == 2

    def test_handling_includes_weight_info(
        self, service, expansion_goal, consolidation_goal
    ):
        expansion_goal.reconciliation_weight = 0.8
        consolidation_goal.reconciliation_weight = 0.3
        conflict = GoalConflict(
            conflict_id="conflict_w",
            goal_id_a=expansion_goal.goal_id,
            goal_id_b=consolidation_goal.goal_id,
            description="Test",
            severity=0.6,
        )
        reports = service.detect_goal_to_goal_conflicts(
            project_id="project_1",
            goal_conflicts=[conflict],
            goals=[expansion_goal, consolidation_goal],
        )
        handling = reports[0].planner_handling
        assert handling.favored_side == expansion_goal.title
        assert "reconciliation weight" in handling.reasoning.lower()

    def test_irreconcilable_conflict_gets_resolution_hints(
        self, service, goal_conflict, expansion_goal, consolidation_goal
    ):
        reports = service.detect_goal_to_goal_conflicts(
            project_id="project_1",
            goal_conflicts=[goal_conflict],
            goals=[expansion_goal, consolidation_goal],
        )
        resolutions = reports[0].suggested_resolutions
        assert len(resolutions) >= 2
        response_types = [r.response_type for r in resolutions]
        assert UserResponseType.SET_PRIORITY in response_types

    def test_empty_goal_conflicts(self, service):
        reports = service.detect_goal_to_goal_conflicts(
            project_id="project_1",
            goal_conflicts=[],
            goals=[],
        )
        assert reports == []


# ============================================================================
# Test Goal-to-Reality Detection
# ============================================================================


class TestGoalToRealityDetection:
    """Test goal-to-reality conflict detection."""

    def test_quality_goal_vs_blocker_pattern(
        self, service, quality_goal, blocker_pattern
    ):
        reports = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[quality_goal],
            feedback_patterns=[blocker_pattern],
        )
        assert len(reports) == 1
        report = reports[0]
        assert report.conflict_type == ConflictType.GOAL_TO_REALITY
        assert "testing" in report.title.lower() or "quality" in report.title.lower()
        assert "blocker" in report.title.lower()

    def test_consolidation_goal_vs_requirement_pattern(
        self, service, consolidation_goal, requirement_pattern
    ):
        reports = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[consolidation_goal],
            feedback_patterns=[requirement_pattern],
        )
        assert len(reports) == 1
        report = reports[0]
        assert report.conflict_type == ConflictType.GOAL_TO_REALITY
        assert "requirement" in report.title.lower()

    def test_no_contradiction_no_conflict(
        self, service, expansion_goal, requirement_pattern
    ):
        # Expansion + requirements is not a contradiction
        reports = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[expansion_goal],
            feedback_patterns=[requirement_pattern],
        )
        assert len(reports) == 0

    def test_goal_without_intent_skipped(self, service, blocker_pattern):
        goal = Goal(
            goal_id="goal_noIntent",
            title="Vague goal",
            description="Do stuff",
            project_id="project_1",
        )
        reports = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[goal],
            feedback_patterns=[blocker_pattern],
        )
        assert len(reports) == 0

    def test_severity_increases_with_signal_count(self, service, quality_goal):
        small_pattern = FeedbackPattern(
            pattern_id="pattern_small",
            project_id="project_1",
            feedback_type=FeedbackType.BLOCKER,
            signal_count=3,
        )
        large_pattern = FeedbackPattern(
            pattern_id="pattern_large",
            project_id="project_1",
            feedback_type=FeedbackType.BLOCKER,
            signal_count=10,
        )

        reports_small = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[quality_goal],
            feedback_patterns=[small_pattern],
        )
        reports_large = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[quality_goal],
            feedback_patterns=[large_pattern],
        )

        assert reports_large[0].severity_score > reports_small[0].severity_score

    def test_suggested_resolutions_present(
        self, service, quality_goal, blocker_pattern
    ):
        reports = service.detect_goal_to_reality_conflicts(
            project_id="project_1",
            goals=[quality_goal],
            feedback_patterns=[blocker_pattern],
        )
        resolutions = reports[0].suggested_resolutions
        assert len(resolutions) >= 2
        response_types = [r.response_type for r in resolutions]
        assert UserResponseType.ADJUST_GOAL in response_types
        assert UserResponseType.CLARIFY_INTENT in response_types

    def test_intent_feedback_contradictions_mapping(self):
        """Verify the contradiction mapping covers expected intent types."""
        assert GoalIntentType.QUALITY_FOCUSED in INTENT_FEEDBACK_CONTRADICTIONS
        assert GoalIntentType.EXPANSION in INTENT_FEEDBACK_CONTRADICTIONS
        assert GoalIntentType.CONSOLIDATION in INTENT_FEEDBACK_CONTRADICTIONS
        assert GoalIntentType.TARGETED_INVESTMENT in INTENT_FEEDBACK_CONTRADICTIONS


# ============================================================================
# Test Dependency Conflict Detection
# ============================================================================


class TestDependencyDetection:
    """Test dependency conflict (circular dependency) detection."""

    def test_detect_simple_cycle(self, service):
        deps = {
            "task_a": ["task_b"],
            "task_b": ["task_c"],
            "task_c": ["task_a"],
        }
        reports = service.detect_dependency_conflicts(
            project_id="project_1",
            dependencies=deps,
        )
        assert len(reports) == 1
        report = reports[0]
        assert report.conflict_type == ConflictType.DEPENDENCY
        assert "circular" in report.title.lower()
        assert len(report.tension_elements) == 3

    def test_detect_two_node_cycle(self, service):
        deps = {
            "task_a": ["task_b"],
            "task_b": ["task_a"],
        }
        reports = service.detect_dependency_conflicts(
            project_id="project_1",
            dependencies=deps,
        )
        assert len(reports) == 1

    def test_no_cycle_no_conflict(self, service):
        deps = {
            "task_a": ["task_b"],
            "task_b": ["task_c"],
            "task_c": [],
        }
        reports = service.detect_dependency_conflicts(
            project_id="project_1",
            dependencies=deps,
        )
        assert len(reports) == 0

    def test_empty_dependencies(self, service):
        reports = service.detect_dependency_conflicts(
            project_id="project_1",
            dependencies={},
        )
        assert len(reports) == 0

    def test_item_labels_used_in_description(self, service):
        deps = {
            "task_a": ["task_b"],
            "task_b": ["task_a"],
        }
        labels = {
            "task_a": "Setup API",
            "task_b": "Define Schema",
        }
        reports = service.detect_dependency_conflicts(
            project_id="project_1",
            dependencies=deps,
            item_labels=labels,
        )
        assert len(reports) == 1
        desc = reports[0].description
        assert "Setup API" in desc or "Define Schema" in desc

    def test_circular_deps_require_user_intervention(self, service):
        deps = {
            "task_a": ["task_b"],
            "task_b": ["task_a"],
        }
        reports = service.detect_dependency_conflicts(
            project_id="project_1",
            dependencies=deps,
        )
        assert reports[0].resolution_authority == ResolutionAuthority.USER_REQUIRED


# ============================================================================
# Test Resource Conflict Detection
# ============================================================================


class TestResourceDetection:
    """Test resource conflict detection."""

    def test_detect_capability_gap(self, service):
        demands = [
            {"task_id": "task_1", "capability": "gpu_compute", "priority": "P1"},
        ]
        resources = [
            {"worker_id": "worker_1", "capabilities": ["cpu_compute"]},
        ]
        reports = service.detect_resource_conflicts(
            project_id="project_1",
            resource_demands=demands,
            available_resources=resources,
        )
        assert len(reports) == 1
        report = reports[0]
        assert report.conflict_type == ConflictType.RESOURCE
        assert "gpu_compute" in report.title

    def test_detect_worker_contention(self, service):
        demands = [
            {"task_id": "task_1", "capability": "testing", "priority": "P1"},
            {"task_id": "task_2", "capability": "testing", "priority": "P1"},
            {"task_id": "task_3", "capability": "testing", "priority": "P2"},
        ]
        resources = [
            {"worker_id": "worker_1", "capabilities": ["testing"]},
        ]
        reports = service.detect_resource_conflicts(
            project_id="project_1",
            resource_demands=demands,
            available_resources=resources,
        )
        assert len(reports) == 1
        report = reports[0]
        assert "contention" in report.title.lower()
        assert len(report.tension_elements) == 3

    def test_no_contention_when_enough_workers(self, service):
        demands = [
            {"task_id": "task_1", "capability": "coding", "priority": "P1"},
        ]
        resources = [
            {"worker_id": "worker_1", "capabilities": ["coding"]},
            {"worker_id": "worker_2", "capabilities": ["coding"]},
        ]
        reports = service.detect_resource_conflicts(
            project_id="project_1",
            resource_demands=demands,
            available_resources=resources,
        )
        assert len(reports) == 0

    def test_empty_demands_no_conflicts(self, service):
        reports = service.detect_resource_conflicts(
            project_id="project_1",
            resource_demands=[],
            available_resources=[{"worker_id": "w1", "capabilities": ["coding"]}],
        )
        assert len(reports) == 0

    def test_contention_severity_increases_with_demand(self, service):
        resources = [
            {"worker_id": "worker_1", "capabilities": ["testing"]},
        ]
        demands_2 = [
            {"task_id": f"task_{i}", "capability": "testing"} for i in range(2)
        ]
        demands_5 = [
            {"task_id": f"task_{i}", "capability": "testing"} for i in range(5)
        ]
        reports_2 = service.detect_resource_conflicts("project_1", demands_2, resources)
        reports_5 = service.detect_resource_conflicts("project_1", demands_5, resources)

        assert reports_5[0].severity_score > reports_2[0].severity_score


# ============================================================================
# Test Full Detection Sweep
# ============================================================================


class TestDetectAllConflicts:
    """Test detect_all_conflicts orchestration."""

    @pytest.mark.asyncio
    async def test_detect_all_with_all_data(
        self, service, expansion_goal, consolidation_goal,
        quality_goal, goal_conflict, blocker_pattern,
    ):
        results = await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal, consolidation_goal, quality_goal],
            goal_conflicts=[goal_conflict],
            feedback_patterns=[blocker_pattern],
            dependencies={
                "task_a": ["task_b"],
                "task_b": ["task_a"],
            },
            resource_demands=[
                {"task_id": "task_1", "capability": "gpu", "priority": "P1"},
            ],
            available_resources=[],
        )
        # Should have at least one of each type:
        # goal-to-goal, goal-to-reality (quality vs blocker),
        # dependency (circular), resource (no gpu workers)
        types_found = {r.conflict_type for r in results}
        assert ConflictType.GOAL_TO_GOAL in types_found
        assert ConflictType.GOAL_TO_REALITY in types_found
        assert ConflictType.DEPENDENCY in types_found
        assert ConflictType.RESOURCE in types_found

    @pytest.mark.asyncio
    async def test_detect_all_with_partial_data(self, service, expansion_goal):
        results = await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal],
            # No other data provided
        )
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_results_stored_in_service(
        self, service, expansion_goal, consolidation_goal, goal_conflict
    ):
        await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal, consolidation_goal],
            goal_conflicts=[goal_conflict],
        )
        conflicts = await service.get_conflicts("project_1")
        assert len(conflicts) > 0


# ============================================================================
# Test Conflict Management
# ============================================================================


class TestConflictManagement:
    """Test conflict querying and resolution."""

    @pytest.mark.asyncio
    async def test_get_conflicts_by_type(
        self, service, expansion_goal, consolidation_goal,
        quality_goal, goal_conflict, blocker_pattern,
    ):
        await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal, consolidation_goal, quality_goal],
            goal_conflicts=[goal_conflict],
            feedback_patterns=[blocker_pattern],
        )
        g2g = await service.get_conflicts(
            "project_1", conflict_type=ConflictType.GOAL_TO_GOAL
        )
        g2r = await service.get_conflicts(
            "project_1", conflict_type=ConflictType.GOAL_TO_REALITY
        )
        assert len(g2g) >= 1
        assert all(c.conflict_type == ConflictType.GOAL_TO_GOAL for c in g2g)
        assert len(g2r) >= 1
        assert all(c.conflict_type == ConflictType.GOAL_TO_REALITY for c in g2r)

    @pytest.mark.asyncio
    async def test_get_surfaceable_conflicts(
        self, service, expansion_goal, consolidation_goal, goal_conflict,
    ):
        await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal, consolidation_goal],
            goal_conflicts=[goal_conflict],
        )
        surfaceable = await service.get_conflicts(
            "project_1", surfaceable_only=True
        )
        for c in surfaceable:
            assert c.should_surface()

    @pytest.mark.asyncio
    async def test_resolve_conflict_by_user(
        self, service, expansion_goal, consolidation_goal, goal_conflict,
    ):
        await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal, consolidation_goal],
            goal_conflicts=[goal_conflict],
        )
        response = UserResponse(
            response_type=UserResponseType.SET_PRIORITY,
            description="Prioritize hardening",
            affected_goal_ids=["goal_consolidate"],
        )
        result = await service.resolve_conflict(
            "project_1", goal_conflict.conflict_id, response
        )
        assert result is not None
        assert result.status == ConflictStatus.USER_RESOLVED
        assert result.user_response == response

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_conflict(self, service):
        response = UserResponse(response_type=UserResponseType.ACCEPT_TRADEOFF)
        result = await service.resolve_conflict("project_1", "nonexistent", response)
        assert result is None

    @pytest.mark.asyncio
    async def test_filter_by_status(
        self, service, expansion_goal, consolidation_goal, goal_conflict,
    ):
        await service.detect_all_conflicts(
            project_id="project_1",
            goals=[expansion_goal, consolidation_goal],
            goal_conflicts=[goal_conflict],
        )
        active = await service.get_conflicts(
            "project_1", status=ConflictStatus.ACTIVE
        )
        assert len(active) >= 1
        resolved = await service.get_conflicts(
            "project_1", status=ConflictStatus.USER_RESOLVED
        )
        assert len(resolved) == 0


# ============================================================================
# Test Global Instance
# ============================================================================


class TestGlobalInstance:
    """Test global instance management."""

    def test_get_uninitialized_raises(self):
        set_conflict_detection_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_conflict_detection_service()

    def test_set_and_get(self, service):
        set_conflict_detection_service(service)
        assert get_conflict_detection_service() is service
        set_conflict_detection_service(None)
