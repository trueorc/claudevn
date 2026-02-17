"""Tests for DirectiveService — interpretation, application, and history.

Tests cover:
- Directive interpretation from natural language
- Intent detection (accelerate, deprioritize, focus, unblock, balance)
- Target area detection from text
- Weight adjustment generation
- Policy adjustment generation
- Directive application to profile
- Directive rejection
- History tracking
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.directive import (
    Directive,
    DirectiveInterpretation,
    DirectiveStatus,
    PolicyAdjustment,
    WeightAdjustment,
)
from models.planner_profile import (
    ConfidenceLevel,
    PlannerProfile,
    ProfileWeights,
    WeightedValue,
    ConfidenceBand,
)
from services.directive_service import (
    DirectiveService,
    get_directive_service,
    set_directive_service,
    DIRECTIVE_PATTERNS,
    AREA_KEYWORDS,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service():
    """DirectiveService with no Redis."""
    return DirectiveService(redis_client=None)


@pytest.fixture
def service_with_redis():
    """DirectiveService with mocked Redis."""
    mock_redis = MagicMock()
    mock_redis._prefix = "claudevn:"
    mock_redis._redis = AsyncMock()
    svc = DirectiveService(redis_client=mock_redis)
    svc._save_directive_to_redis = AsyncMock()
    return svc


@pytest.fixture
def sample_profile():
    """A sample planner profile for testing."""
    return PlannerProfile(
        profile_id="profile_test_001",
        project_id="project-001",
        weights=ProfileWeights(
            work_type_weights={
                "feature": WeightedValue(
                    weight=0.7,
                    confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
                ),
                "test": WeightedValue(
                    weight=0.4,
                    confidence=ConfidenceBand(level=ConfidenceLevel.LOW),
                ),
            },
            technical_domain_weights={
                "frontend": WeightedValue(
                    weight=0.6,
                    confidence=ConfidenceBand(level=ConfidenceLevel.MEDIUM),
                ),
            },
        ),
        version=3,
    )


# ============================================================================
# Intent Detection
# ============================================================================


class TestIntentDetection:
    """Tests for directive intent detection."""

    def test_detect_accelerate_intent(self, service):
        intent, conf = service._detect_directive_intent(
            "Accelerate payment flow validation"
        )
        assert intent == "accelerate"
        assert conf == ConfidenceLevel.HIGH

    def test_detect_deprioritize_intent(self, service):
        intent, conf = service._detect_directive_intent(
            "Deprioritize new feature development"
        )
        assert intent == "deprioritize"
        assert conf == ConfidenceLevel.HIGH

    def test_detect_focus_intent(self, service):
        intent, conf = service._detect_directive_intent(
            "Focus on testing for the authentication domain"
        )
        assert intent == "focus"
        assert conf == ConfidenceLevel.HIGH

    def test_detect_unblock_intent(self, service):
        intent, conf = service._detect_directive_intent(
            "Unblock the API integration cluster"
        )
        assert intent == "unblock"
        assert conf == ConfidenceLevel.MEDIUM

    def test_detect_balance_intent(self, service):
        intent, conf = service._detect_directive_intent(
            "Balance work across all domains"
        )
        assert intent == "balance"
        assert conf == ConfidenceLevel.LOW

    def test_default_intent_on_unknown(self, service):
        intent, conf = service._detect_directive_intent(
            "Do something with the system"
        )
        assert intent == "focus"
        assert conf == ConfidenceLevel.LOW

    def test_multiple_keywords_picks_strongest(self, service):
        intent, conf = service._detect_directive_intent(
            "Speed up and fast-track the expedite process"
        )
        assert intent == "accelerate"


# ============================================================================
# Target Area Detection
# ============================================================================


class TestTargetAreaDetection:
    """Tests for target area detection from text."""

    def test_detect_work_type(self, service):
        areas = service._detect_target_areas("Focus on testing")
        assert any(a["category"] == "work_type" and a["key"] == "test" for a in areas)

    def test_detect_technical_domain(self, service):
        areas = service._detect_target_areas("Accelerate frontend work")
        assert any(
            a["category"] == "technical_domain" and a["key"] == "frontend"
            for a in areas
        )

    def test_detect_lifecycle_stage(self, service):
        areas = service._detect_target_areas("Focus on deployment")
        assert any(
            a["category"] == "lifecycle_stage" and a["key"] == "deploy"
            for a in areas
        )

    def test_detect_multiple_areas(self, service):
        areas = service._detect_target_areas(
            "Focus on testing and frontend security"
        )
        categories = {(a["category"], a["key"]) for a in areas}
        assert ("work_type", "test") in categories
        assert ("technical_domain", "frontend") in categories
        assert ("technical_domain", "security") in categories

    def test_no_areas_detected(self, service):
        areas = service._detect_target_areas("Make everything better")
        assert areas == []

    def test_deduplication(self, service):
        areas = service._detect_target_areas(
            "testing tests test"
        )
        test_areas = [
            a for a in areas
            if a["category"] == "work_type" and a["key"] == "test"
        ]
        assert len(test_areas) == 1


# ============================================================================
# Weight Adjustment Generation
# ============================================================================


class TestWeightAdjustmentGeneration:
    """Tests for weight adjustment generation."""

    def test_accelerate_boosts_weights(self, service, sample_profile):
        areas = [{"category": "work_type", "key": "test"}]
        adjustments = service._generate_weight_adjustments(
            "accelerate", ConfidenceLevel.HIGH, areas, sample_profile
        )
        assert len(adjustments) == 1
        adj = adjustments[0]
        assert adj.category == "work_type"
        assert adj.key == "test"
        assert adj.proposed_weight > 0.4  # Current is 0.4, should boost
        assert adj.confidence == "high"

    def test_deprioritize_reduces_weights(self, service, sample_profile):
        areas = [{"category": "work_type", "key": "feature"}]
        adjustments = service._generate_weight_adjustments(
            "deprioritize", ConfidenceLevel.HIGH, areas, sample_profile
        )
        assert len(adjustments) == 1
        adj = adjustments[0]
        assert adj.proposed_weight < 0.7  # Current is 0.7, should reduce

    def test_balance_normalizes_weights(self, service, sample_profile):
        areas = [{"category": "work_type", "key": "feature"}]
        adjustments = service._generate_weight_adjustments(
            "balance", ConfidenceLevel.LOW, areas, sample_profile
        )
        assert len(adjustments) == 1
        assert adjustments[0].proposed_weight == 0.5

    def test_no_profile_uses_defaults(self, service):
        areas = [{"category": "work_type", "key": "test"}]
        adjustments = service._generate_weight_adjustments(
            "accelerate", ConfidenceLevel.HIGH, areas, None
        )
        assert len(adjustments) == 1
        # Default 0.5 + 0.3 boost = 0.8
        assert adjustments[0].proposed_weight == 0.8

    def test_weight_capped_at_bounds(self, service):
        areas = [{"category": "work_type", "key": "feature"}]
        # Create a profile with weight at 0.9
        profile = PlannerProfile(
            profile_id="p1",
            project_id="proj",
            weights=ProfileWeights(
                work_type_weights={
                    "feature": WeightedValue(weight=0.9, confidence=ConfidenceBand()),
                }
            ),
        )
        adjustments = service._generate_weight_adjustments(
            "accelerate", ConfidenceLevel.HIGH, areas, profile
        )
        assert adjustments[0].proposed_weight <= 1.0


# ============================================================================
# Policy Adjustment Generation
# ============================================================================


class TestPolicyAdjustmentGeneration:
    """Tests for policy adjustment generation."""

    def test_accelerate_creates_elevate_rule(self, service):
        areas = [{"category": "work_type", "key": "test"}]
        adjustments = service._generate_policy_adjustments(
            "accelerate", areas, "dir_001"
        )
        assert len(adjustments) == 1
        assert adjustments[0].action == "add"
        assert adjustments[0].action_type == "elevate_priority"

    def test_deprioritize_creates_deprioritize_rule(self, service):
        areas = [{"category": "work_type", "key": "feature"}]
        adjustments = service._generate_policy_adjustments(
            "deprioritize", areas, "dir_001"
        )
        assert len(adjustments) == 1
        assert adjustments[0].action == "add"
        assert adjustments[0].action_type == "deprioritize"

    def test_unblock_creates_blocker_rule(self, service):
        areas = [{"category": "work_type", "key": "test"}]
        adjustments = service._generate_policy_adjustments(
            "unblock", areas, "dir_001"
        )
        assert len(adjustments) == 1
        assert adjustments[0].action_type == "elevate_priority"
        assert adjustments[0].condition_type == "blocking_count_above"

    def test_focus_creates_no_policies(self, service):
        areas = [{"category": "work_type", "key": "test"}]
        adjustments = service._generate_policy_adjustments(
            "focus", areas, "dir_001"
        )
        assert len(adjustments) == 0

    def test_balance_creates_no_policies(self, service):
        areas = [{"category": "work_type", "key": "test"}]
        adjustments = service._generate_policy_adjustments(
            "balance", areas, "dir_001"
        )
        assert len(adjustments) == 0


# ============================================================================
# Directive Interpretation (End-to-End)
# ============================================================================


class TestInterpretation:
    """Tests for full directive interpretation flow."""

    @pytest.mark.asyncio
    async def test_interpret_accelerate_directive(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Accelerate testing",
        )
        assert directive.status == DirectiveStatus.PENDING_REVIEW
        assert directive.interpretation is not None
        assert directive.interpretation.detected_intent == "accelerate"
        assert len(directive.interpretation.weight_adjustments) > 0
        assert "work_type/test" in directive.interpretation.affected_areas

    @pytest.mark.asyncio
    async def test_interpret_deprioritize_directive(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Deprioritize new feature development",
        )
        assert directive.interpretation.detected_intent == "deprioritize"
        assert any(
            adj.key == "feature"
            for adj in directive.interpretation.weight_adjustments
        )

    @pytest.mark.asyncio
    async def test_interpret_stores_directive(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Focus on backend testing",
        )
        # Should be retrievable
        stored = service._get_directive("project-001", directive.directive_id)
        assert stored is not None
        assert stored.directive_id == directive.directive_id

    @pytest.mark.asyncio
    async def test_interpret_with_no_target_areas(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Make everything better",
        )
        assert directive.interpretation is not None
        assert directive.interpretation.detected_intent == "focus"
        assert len(directive.interpretation.weight_adjustments) == 0

    @pytest.mark.asyncio
    async def test_interpret_summary_populated(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Focus on testing",
        )
        assert directive.interpretation.summary != ""
        assert "test" in directive.interpretation.summary.lower()


# ============================================================================
# Directive Application
# ============================================================================


class TestApplication:
    """Tests for directive application to profile."""

    @pytest.mark.asyncio
    async def test_apply_updates_status(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Focus on testing",
        )
        with patch(
            "services.directive_service.DirectiveService._apply_to_profile",
            new_callable=AsyncMock,
            return_value=MagicMock(version=4),
        ):
            result = await service.apply("project-001", directive.directive_id)
        assert result.status == DirectiveStatus.APPLIED
        assert result.applied_at is not None

    @pytest.mark.asyncio
    async def test_apply_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.apply("project-001", "nonexistent")

    @pytest.mark.asyncio
    async def test_apply_already_applied_raises(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Focus on testing",
        )
        with patch(
            "services.directive_service.DirectiveService._apply_to_profile",
            new_callable=AsyncMock,
            return_value=MagicMock(version=4),
        ):
            await service.apply("project-001", directive.directive_id)
        with pytest.raises(ValueError, match="applied"):
            await service.apply("project-001", directive.directive_id)


# ============================================================================
# Directive Rejection
# ============================================================================


class TestRejection:
    """Tests for directive rejection."""

    @pytest.mark.asyncio
    async def test_reject_updates_status(self, service):
        directive = await service.interpret(
            project_id="project-001",
            text="Deprioritize features",
        )
        result = await service.reject("project-001", directive.directive_id)
        assert result.status == DirectiveStatus.REJECTED
        assert result.rejected_at is not None

    @pytest.mark.asyncio
    async def test_reject_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.reject("project-001", "nonexistent")


# ============================================================================
# Directive History
# ============================================================================


class TestHistory:
    """Tests for directive history tracking."""

    @pytest.mark.asyncio
    async def test_history_returns_directives(self, service):
        await service.interpret("project-001", "Focus on testing")
        await service.interpret("project-001", "Accelerate frontend")
        history = await service.get_history("project-001")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_history_most_recent_first(self, service):
        d1 = await service.interpret("project-001", "Focus on testing")
        d2 = await service.interpret("project-001", "Accelerate frontend")
        history = await service.get_history("project-001")
        assert history[0].directive_id == d2.directive_id

    @pytest.mark.asyncio
    async def test_history_empty_project(self, service):
        history = await service.get_history("nonexistent-project")
        assert history == []

    @pytest.mark.asyncio
    async def test_history_respects_limit(self, service):
        for i in range(5):
            await service.interpret("project-001", f"Directive {i}")
        history = await service.get_history("project-001", limit=3)
        assert len(history) == 3


# ============================================================================
# Global Instance
# ============================================================================


class TestGlobalInstance:
    """Tests for global service singleton."""

    def test_get_before_set_raises(self):
        set_directive_service(None)
        with pytest.raises(RuntimeError, match="not initialized"):
            get_directive_service()

    def test_set_and_get(self):
        svc = DirectiveService()
        set_directive_service(svc)
        assert get_directive_service() is svc
        set_directive_service(None)
