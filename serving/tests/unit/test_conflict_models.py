"""Tests for conflict taxonomy models.

Tests cover:
- ConflictReport creation and field validation
- Severity score to severity level mapping
- Authority boundary rules
- Conflict lifecycle (should_surface, mark_surfaced, resolve_by_user, resolve_autonomously)
- TensionElement and PlannerHandling models
- SuggestedResolution and UserResponse models
- Default authority rules and detection criteria
"""

import pytest
from datetime import datetime, timezone

from models.conflict import (
    AuthorityRule,
    ConflictReport,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    DEFAULT_AUTHORITY_RULES,
    DEFAULT_DETECTION_CRITERIA,
    DetectionCriteria,
    PlannerHandling,
    ResolutionAuthority,
    SuggestedResolution,
    TensionElement,
    UserResponse,
    UserResponseType,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tension_elements():
    """Sample tension elements for testing."""
    return [
        TensionElement(
            element_type="goal",
            element_id="goal_1",
            label="Build reporting feature",
            detail="Primary intent: expansion",
        ),
        TensionElement(
            element_type="goal",
            element_id="goal_2",
            label="Harden current functionality",
            detail="Primary intent: consolidation",
        ),
    ]


@pytest.fixture
def planner_handling():
    """Sample planner handling for testing."""
    return PlannerHandling(
        approach="Reconciling by favoring 'Build reporting feature' in profile weights",
        favored_side="Build reporting feature",
        reasoning="Stronger intent signal for expansion (0.8 vs 0.5)",
    )


@pytest.fixture
def conflict_report(tension_elements, planner_handling):
    """Sample conflict report for testing."""
    return ConflictReport(
        conflict_id="conflict_test123",
        project_id="project_1",
        conflict_type=ConflictType.GOAL_TO_GOAL,
        severity=ConflictSeverity.HIGH,
        severity_score=0.75,
        title="Goal conflict: Build reporting vs Harden functionality",
        description="Expansion wants new features while consolidation wants stability",
        tension_elements=tension_elements,
        planner_handling=planner_handling,
        suggested_resolutions=[
            SuggestedResolution(
                response_type=UserResponseType.SET_PRIORITY,
                description="Set reconciliation_weight on one goal",
                expected_impact="Planner will weight goals accordingly",
            ),
        ],
        decision_trace_ids=["trace_abc"],
        resolution_authority=ResolutionAuthority.USER_REQUIRED,
    )


# ============================================================================
# Test Conflict Types and Enums
# ============================================================================


class TestConflictEnums:
    """Test conflict type and severity enumerations."""

    def test_conflict_types(self):
        assert ConflictType.GOAL_TO_GOAL == "goal_to_goal"
        assert ConflictType.GOAL_TO_REALITY == "goal_to_reality"
        assert ConflictType.DEPENDENCY == "dependency"
        assert ConflictType.RESOURCE == "resource"

    def test_conflict_severity_levels(self):
        assert ConflictSeverity.LOW == "low"
        assert ConflictSeverity.MEDIUM == "medium"
        assert ConflictSeverity.HIGH == "high"
        assert ConflictSeverity.CRITICAL == "critical"

    def test_conflict_status_values(self):
        assert ConflictStatus.ACTIVE == "active"
        assert ConflictStatus.AUTONOMOUSLY_RESOLVED == "autonomously_resolved"
        assert ConflictStatus.SURFACED == "surfaced"
        assert ConflictStatus.USER_RESOLVED == "user_resolved"
        assert ConflictStatus.SUPERSEDED == "superseded"

    def test_user_response_types(self):
        assert UserResponseType.ADJUST_GOAL == "adjust_goal"
        assert UserResponseType.ACCEPT_TRADEOFF == "accept_tradeoff"
        assert UserResponseType.CLARIFY_INTENT == "clarify_intent"
        assert UserResponseType.SET_PRIORITY == "set_priority"

    def test_resolution_authority_values(self):
        assert ResolutionAuthority.AUTONOMOUS == "autonomous"
        assert ResolutionAuthority.USER_REQUIRED == "user_required"


# ============================================================================
# Test TensionElement
# ============================================================================


class TestTensionElement:
    """Test TensionElement model."""

    def test_create_tension_element(self):
        elem = TensionElement(
            element_type="goal",
            element_id="goal_1",
            label="Test Goal",
            detail="Some detail",
        )
        assert elem.element_type == "goal"
        assert elem.element_id == "goal_1"
        assert elem.label == "Test Goal"
        assert elem.detail == "Some detail"

    def test_tension_element_default_detail(self):
        elem = TensionElement(
            element_type="task",
            element_id="task_1",
            label="Test Task",
        )
        assert elem.detail == ""


# ============================================================================
# Test ConflictReport
# ============================================================================


class TestConflictReport:
    """Test ConflictReport model creation and lifecycle."""

    def test_create_conflict_report(self, conflict_report):
        assert conflict_report.conflict_id == "conflict_test123"
        assert conflict_report.project_id == "project_1"
        assert conflict_report.conflict_type == ConflictType.GOAL_TO_GOAL
        assert conflict_report.severity == ConflictSeverity.HIGH
        assert conflict_report.severity_score == 0.75
        assert conflict_report.status == ConflictStatus.ACTIVE
        assert len(conflict_report.tension_elements) == 2
        assert len(conflict_report.suggested_resolutions) == 1
        assert conflict_report.resolution_authority == ResolutionAuthority.USER_REQUIRED

    def test_severity_score_validation(self):
        with pytest.raises(Exception):
            ConflictReport(
                conflict_id="test",
                project_id="proj",
                conflict_type=ConflictType.GOAL_TO_GOAL,
                severity=ConflictSeverity.LOW,
                severity_score=1.5,  # Invalid: > 1.0
                title="Test",
                description="Test",
                planner_handling=PlannerHandling(approach="test"),
                resolution_authority=ResolutionAuthority.AUTONOMOUS,
            )

    def test_should_surface_user_required(self, conflict_report):
        assert conflict_report.should_surface() is True

    def test_should_surface_high_severity(self):
        report = ConflictReport(
            conflict_id="test",
            project_id="proj",
            conflict_type=ConflictType.RESOURCE,
            severity=ConflictSeverity.HIGH,
            severity_score=0.7,
            title="Test",
            description="Test",
            planner_handling=PlannerHandling(approach="test"),
            resolution_authority=ResolutionAuthority.AUTONOMOUS,
        )
        assert report.should_surface() is True

    def test_should_not_surface_low_severity_autonomous(self):
        report = ConflictReport(
            conflict_id="test",
            project_id="proj",
            conflict_type=ConflictType.DEPENDENCY,
            severity=ConflictSeverity.LOW,
            severity_score=0.2,
            title="Test",
            description="Test",
            planner_handling=PlannerHandling(approach="test"),
            resolution_authority=ResolutionAuthority.AUTONOMOUS,
        )
        assert report.should_surface() is False

    def test_mark_surfaced(self, conflict_report):
        assert conflict_report.surfaced_at is None
        conflict_report.mark_surfaced()
        assert conflict_report.status == ConflictStatus.SURFACED
        assert conflict_report.surfaced_at is not None

    def test_resolve_autonomously(self, conflict_report):
        conflict_report.resolve_autonomously("Resequenced tasks by priority")
        assert conflict_report.status == ConflictStatus.AUTONOMOUSLY_RESOLVED
        assert conflict_report.autonomous_resolution == "Resequenced tasks by priority"
        assert conflict_report.resolved_at is not None

    def test_resolve_by_user(self, conflict_report):
        response = UserResponse(
            response_type=UserResponseType.SET_PRIORITY,
            description="Prioritize hardening over new features",
            affected_goal_ids=["goal_1", "goal_2"],
        )
        conflict_report.resolve_by_user(response)
        assert conflict_report.status == ConflictStatus.USER_RESOLVED
        assert conflict_report.user_response == response
        assert conflict_report.resolved_at is not None

    def test_default_timestamps(self, conflict_report):
        assert conflict_report.detected_at is not None
        assert conflict_report.surfaced_at is None
        assert conflict_report.resolved_at is None


# ============================================================================
# Test Authority Rules
# ============================================================================


class TestAuthorityRules:
    """Test authority boundary rules."""

    def test_default_authority_rules_count(self):
        assert len(DEFAULT_AUTHORITY_RULES) == 4

    def test_default_rules_cover_all_conflict_types(self):
        covered_types = {r.conflict_type for r in DEFAULT_AUTHORITY_RULES}
        assert covered_types == {
            ConflictType.GOAL_TO_GOAL,
            ConflictType.GOAL_TO_REALITY,
            ConflictType.DEPENDENCY,
            ConflictType.RESOURCE,
        }

    def test_goal_to_goal_threshold_is_high(self):
        rule = next(r for r in DEFAULT_AUTHORITY_RULES if r.conflict_type == ConflictType.GOAL_TO_GOAL)
        assert rule.severity_threshold == ConflictSeverity.HIGH

    def test_goal_to_reality_threshold_is_medium(self):
        rule = next(r for r in DEFAULT_AUTHORITY_RULES if r.conflict_type == ConflictType.GOAL_TO_REALITY)
        assert rule.severity_threshold == ConflictSeverity.MEDIUM

    def test_authority_rule_creation(self):
        rule = AuthorityRule(
            conflict_type=ConflictType.RESOURCE,
            severity_threshold=ConflictSeverity.CRITICAL,
            authority=ResolutionAuthority.AUTONOMOUS,
            condition="test_condition",
            description="Test rule",
        )
        assert rule.conflict_type == ConflictType.RESOURCE
        assert rule.authority == ResolutionAuthority.AUTONOMOUS


# ============================================================================
# Test Detection Criteria
# ============================================================================


class TestDetectionCriteria:
    """Test default detection criteria."""

    def test_default_criteria_exist(self):
        assert len(DEFAULT_DETECTION_CRITERIA) >= 4

    def test_criteria_cover_all_conflict_types(self):
        covered_types = {c.conflict_type for c in DEFAULT_DETECTION_CRITERIA}
        assert covered_types == {
            ConflictType.GOAL_TO_GOAL,
            ConflictType.GOAL_TO_REALITY,
            ConflictType.DEPENDENCY,
            ConflictType.RESOURCE,
        }

    def test_criteria_have_required_data(self):
        for criteria in DEFAULT_DETECTION_CRITERIA:
            assert len(criteria.required_data) > 0
            assert criteria.name != ""
            assert criteria.description != ""


# ============================================================================
# Test PlannerHandling
# ============================================================================


class TestPlannerHandling:
    """Test PlannerHandling model."""

    def test_create_with_all_fields(self):
        handling = PlannerHandling(
            approach="Favoring goal A",
            favored_side="Goal A",
            reasoning="Higher priority",
            profile_impact={"work_type_weights": {"feature": 0.8}},
        )
        assert handling.approach == "Favoring goal A"
        assert handling.favored_side == "Goal A"
        assert handling.profile_impact == {"work_type_weights": {"feature": 0.8}}

    def test_create_with_defaults(self):
        handling = PlannerHandling(approach="No action needed")
        assert handling.favored_side is None
        assert handling.reasoning == ""
        assert handling.profile_impact == {}


# ============================================================================
# Test SuggestedResolution
# ============================================================================


class TestSuggestedResolution:
    """Test SuggestedResolution model."""

    def test_create_suggested_resolution(self):
        resolution = SuggestedResolution(
            response_type=UserResponseType.ADJUST_GOAL,
            description="Modify goal to reduce tension",
            expected_impact="Intent will be reclassified",
        )
        assert resolution.response_type == UserResponseType.ADJUST_GOAL
        assert resolution.description == "Modify goal to reduce tension"

    def test_default_expected_impact(self):
        resolution = SuggestedResolution(
            response_type=UserResponseType.ACCEPT_TRADEOFF,
            description="Accept current approach",
        )
        assert resolution.expected_impact == ""


# ============================================================================
# Test UserResponse
# ============================================================================


class TestUserResponse:
    """Test UserResponse model."""

    def test_create_user_response(self):
        response = UserResponse(
            response_type=UserResponseType.CLARIFY_INTENT,
            description="I want both goals to be active",
            affected_goal_ids=["goal_1"],
        )
        assert response.response_type == UserResponseType.CLARIFY_INTENT
        assert response.affected_goal_ids == ["goal_1"]
        assert response.timestamp is not None

    def test_default_fields(self):
        response = UserResponse(response_type=UserResponseType.ACCEPT_TRADEOFF)
        assert response.description == ""
        assert response.affected_goal_ids == []
