"""Tests for multi-goal profile reconciliation.

Covers:
- Reconciliation factor calculation (priority, recency, user weight overrides)
- Enhanced reconciliation with priority/recency weighting
- Conflict detection with irreconcilable flag and resolution hints
- User reconciliation weight override (service + API)
- GoalConflict model enhancements
- GoalSetReconciliationWeightRequest model
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.planner_profile import (
    ConfidenceBand,
    ConfidenceLevel,
    ProfileWeights,
    WeightedValue,
)
from models.work_map import (
    Goal,
    GoalConflict,
    GoalIntentType,
    GoalStatus,
    GoalSetReconciliationWeightRequest,
    GoalConflictListResponse,
    IssuePriority,
)
from services.planner_profile_service import PlannerProfileService
from services.goal_intent_service import GoalIntentService
from services.goal_service import GoalService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def profile_service():
    """PlannerProfileService with no Redis."""
    return PlannerProfileService(redis_client=None)


@pytest.fixture
def intent_service():
    """GoalIntentService instance."""
    return GoalIntentService()


@pytest.fixture
def goal_service():
    """GoalService with mocked Redis save."""
    svc = GoalService(redis_client=None)
    svc._save_goal_to_redis = AsyncMock()
    return svc


def _make_goal(
    goal_id: str,
    intent: GoalIntentType,
    strength: float,
    priority: IssuePriority = IssuePriority.P1,
    created_at: datetime = None,
    reconciliation_weight: float = None,
) -> Goal:
    """Helper to create a goal with specific intent, priority, and timestamps."""
    return Goal(
        goal_id=goal_id,
        title=f"Goal {goal_id}",
        description="Test goal",
        project_id="project-001",
        priority=priority,
        status=GoalStatus.IN_PROGRESS,
        primary_intent=intent,
        intent_strength=strength,
        created_at=created_at or datetime.now(timezone.utc),
        reconciliation_weight=reconciliation_weight,
    )


# ============================================================================
# Reconciliation Factor Calculation
# ============================================================================


class TestReconciliationFactor:
    """Test _calculate_reconciliation_factor with priority, recency, user weight."""

    def test_p0_higher_than_p3(self, profile_service):
        """P0 goals should produce higher reconciliation factor than P3."""
        goal_p0 = _make_goal("g1", GoalIntentType.EXPANSION, 0.8, IssuePriority.P0)
        goal_p3 = _make_goal("g2", GoalIntentType.EXPANSION, 0.8, IssuePriority.P3)

        factor_p0 = profile_service._calculate_reconciliation_factor(goal_p0)
        factor_p3 = profile_service._calculate_reconciliation_factor(goal_p3)

        assert factor_p0 > factor_p3

    def test_priority_factor_values(self, profile_service):
        """Check priority factors: P0=1.0, P1=0.75, P2=0.5, P3=0.25."""
        now = datetime.now(timezone.utc)
        # Use old goals so recency factor is 1.0
        old_time = now - timedelta(days=30)

        for priority, expected_base in [
            (IssuePriority.P0, 1.0),
            (IssuePriority.P1, 0.75),
            (IssuePriority.P2, 0.5),
            (IssuePriority.P3, 0.25),
        ]:
            goal = _make_goal(f"g_{priority.value}", GoalIntentType.EXPANSION, 0.8,
                              priority, created_at=old_time)
            factor = profile_service._calculate_reconciliation_factor(goal)
            # Old goal -> recency_factor=1.0, so factor = priority_factor * 1.0
            assert factor == pytest.approx(expected_base, abs=0.01)

    def test_recent_goal_gets_recency_boost(self, profile_service):
        """Goals created within 24 hours get a 1.5x recency multiplier."""
        now = datetime.now(timezone.utc)
        recent = _make_goal("g1", GoalIntentType.EXPANSION, 0.8,
                            IssuePriority.P1, created_at=now - timedelta(hours=1))
        old = _make_goal("g2", GoalIntentType.EXPANSION, 0.8,
                         IssuePriority.P1, created_at=now - timedelta(days=30))

        factor_recent = profile_service._calculate_reconciliation_factor(recent)
        factor_old = profile_service._calculate_reconciliation_factor(old)

        # Recent: 0.75 * 1.5 = 1.125, Old: 0.75 * 1.0 = 0.75
        assert factor_recent > factor_old
        assert factor_recent == pytest.approx(0.75 * 1.5, abs=0.01)

    def test_recency_decay_mid_range(self, profile_service):
        """Goals 3.5 days old should have recency factor between 1.0 and 1.5."""
        now = datetime.now(timezone.utc)
        mid_age = _make_goal("g1", GoalIntentType.EXPANSION, 0.8,
                             IssuePriority.P1, created_at=now - timedelta(days=3, hours=12))

        factor = profile_service._calculate_reconciliation_factor(mid_age)
        # P1 base = 0.75, recency between 1.0 and 1.5
        assert 0.75 < factor < 0.75 * 1.5

    def test_user_weight_overrides_priority_and_recency(self, profile_service):
        """User-set reconciliation_weight should override automatic calculation."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8,
                          IssuePriority.P3, reconciliation_weight=0.9)

        factor = profile_service._calculate_reconciliation_factor(goal)
        # User weight 0.9 -> 0.5 + 0.9*1.5 = 1.85
        assert factor == pytest.approx(1.85, abs=0.01)

    def test_user_weight_zero_gives_minimum_influence(self, profile_service):
        """User weight of 0.0 should give minimum factor of 0.5."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8,
                          IssuePriority.P0, reconciliation_weight=0.0)

        factor = profile_service._calculate_reconciliation_factor(goal)
        assert factor == pytest.approx(0.5)

    def test_user_weight_one_gives_maximum_influence(self, profile_service):
        """User weight of 1.0 should give maximum factor of 2.0."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8,
                          IssuePriority.P3, reconciliation_weight=1.0)

        factor = profile_service._calculate_reconciliation_factor(goal)
        assert factor == pytest.approx(2.0)


# ============================================================================
# Enhanced Reconciliation (Priority/Recency in Weight Merging)
# ============================================================================


class TestEnhancedReconciliation:
    """Test that reconciliation respects priority and recency factors."""

    @pytest.mark.asyncio
    async def test_p0_goal_dominates_p3_in_reconciliation(self, profile_service):
        """A P0 goal's weights should dominate a P3 goal's for the same key."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)

        p0_goal = _make_goal("g_p0", GoalIntentType.CONSOLIDATION, 0.8,
                             IssuePriority.P0, created_at=old_time)
        p3_goal = _make_goal("g_p3", GoalIntentType.EXPANSION, 0.8,
                             IssuePriority.P3, created_at=old_time)

        profile = await profile_service.construct_profile(
            "project-001", [p0_goal, p3_goal]
        )

        # Feature weight: P0-consolidation contributes 0.15 (HIGH conf, 1.0 recon)
        # P3-expansion contributes 0.9 (HIGH conf, 0.25 recon)
        # P0 consolidation's low-feature signal should pull feature down
        feature_weight = profile.weights.get_weight("work_type", "feature")
        # With P0's 4x higher recon factor, result should be pulled toward P0's value
        # This should be noticeably lower than 0.9
        assert feature_weight < 0.7

    @pytest.mark.asyncio
    async def test_user_weight_override_shifts_reconciliation(self, profile_service):
        """Setting reconciliation_weight should shift the balance."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)

        # Two equal-priority goals, but user weights one higher
        expansion = _make_goal("g_exp", GoalIntentType.EXPANSION, 0.8,
                               IssuePriority.P1, created_at=old_time,
                               reconciliation_weight=0.2)
        consolidation = _make_goal("g_con", GoalIntentType.CONSOLIDATION, 0.8,
                                   IssuePriority.P1, created_at=old_time,
                                   reconciliation_weight=0.9)

        profile = await profile_service.construct_profile(
            "project-001", [expansion, consolidation]
        )

        # Test weight should lean toward consolidation (high user weight)
        test_weight = profile.weights.get_weight("work_type", "test")
        assert test_weight > 0.7

    @pytest.mark.asyncio
    async def test_recent_goal_influences_more(self, profile_service):
        """A very recent goal should have more influence than an old one."""
        now = datetime.now(timezone.utc)

        recent_exp = _make_goal("g_recent", GoalIntentType.EXPANSION, 0.7,
                                IssuePriority.P2, created_at=now - timedelta(hours=2))
        old_con = _make_goal("g_old", GoalIntentType.CONSOLIDATION, 0.7,
                             IssuePriority.P2, created_at=now - timedelta(days=30))

        profile = await profile_service.construct_profile(
            "project-001", [recent_exp, old_con]
        )

        # Feature weight should lean toward recent expansion goal
        feature_weight = profile.weights.get_weight("work_type", "feature")
        assert feature_weight > 0.4  # Should be pulled up by recency of expansion

    @pytest.mark.asyncio
    async def test_single_goal_passthrough_unaffected(self, profile_service):
        """Single goal should pass through weights unchanged (no reconciliation needed)."""
        goal = _make_goal("g1", GoalIntentType.CONSOLIDATION, 0.8, IssuePriority.P0)

        profile = await profile_service.construct_profile("project-001", [goal])

        # Single goal: weight should match the raw intent weight (scaled by strength)
        test_weight = profile.weights.get_weight("work_type", "test")
        assert test_weight > 0.8  # Consolidation test weight is 0.9, scaled by 1.3

    @pytest.mark.asyncio
    async def test_backwards_compatible_3_tuple(self, profile_service):
        """Old-style 3-tuples (without recon_factor) should still work."""
        all_weights = {
            "work_type": {
                "test": [
                    (0.9, ConfidenceLevel.HIGH, "goal-1"),
                    (0.3, ConfidenceLevel.LOW, "goal-2"),
                ],
            },
        }

        reconciled = profile_service._reconcile_weights(all_weights)
        test_weight = reconciled.get_weight("work_type", "test")
        # Should still compute correctly with default recon_factor=1.0
        assert test_weight > 0.7

    @pytest.mark.asyncio
    async def test_4_tuple_with_recon_factor(self, profile_service):
        """4-tuples with recon_factor should bias toward higher-factor entries."""
        all_weights = {
            "work_type": {
                "feature": [
                    (0.9, ConfidenceLevel.HIGH, "goal-1", 2.0),  # High recon factor
                    (0.1, ConfidenceLevel.HIGH, "goal-2", 0.5),  # Low recon factor
                ],
            },
        }

        reconciled = profile_service._reconcile_weights(all_weights)
        feature_weight = reconciled.get_weight("work_type", "feature")
        # goal-1 has 4x combined multiplier vs goal-2, should be close to 0.9
        assert feature_weight > 0.7


# ============================================================================
# Enhanced Conflict Detection
# ============================================================================


class TestEnhancedConflictDetection:
    """Test conflict detection with irreconcilable flag and resolution hints."""

    def test_high_severity_marked_irreconcilable(self, intent_service):
        """Conflicts with severity >= 0.7 should be marked irreconcilable."""
        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.8, IssuePriority.P0)
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.8, IssuePriority.P0)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        conflict = conflicts[0]
        # Base severity: (0.8 + 0.8) / 2 = 0.8, with recency boost 1.2 -> 0.96
        assert conflict.severity >= 0.7
        assert conflict.is_irreconcilable is True

    def test_low_severity_not_irreconcilable(self, intent_service):
        """Conflicts with severity < 0.7 should not be irreconcilable."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)

        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.3,
                            created_at=old_time)
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.3,
                            created_at=old_time)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        conflict = conflicts[0]
        # Base severity: (0.3 + 0.3) / 2 = 0.3, old -> recency 1.0
        assert conflict.severity < 0.7
        assert conflict.is_irreconcilable is False

    def test_resolution_hint_when_irreconcilable(self, intent_service):
        """Irreconcilable conflicts should have a resolution hint."""
        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.9)
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.9)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        assert conflicts[0].resolution_hint is not None
        assert "reconciliation_weight" in conflicts[0].resolution_hint

    def test_no_hint_when_reconcilable(self, intent_service):
        """Low-severity conflicts should not have a resolution hint."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)

        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.3,
                            created_at=old_time)
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.3,
                            created_at=old_time)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        assert conflicts[0].resolution_hint is None

    def test_hint_acknowledges_existing_weights(self, intent_service):
        """When both goals already have weights, hint should mention adjusting."""
        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.9,
                            reconciliation_weight=0.8)
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.9,
                            reconciliation_weight=0.5)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        if conflicts[0].is_irreconcilable:
            assert "Both goals have reconciliation weights" in conflicts[0].resolution_hint

    def test_recency_boost_both_recent(self, intent_service):
        """Two goals created within 48 hours should get 1.2x severity boost."""
        now = datetime.now(timezone.utc)
        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.5,
                            created_at=now - timedelta(hours=1))
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.5,
                            created_at=now - timedelta(hours=2))

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        # Base severity: 0.5, with 1.2x boost = 0.6
        assert conflicts[0].severity == pytest.approx(0.6, abs=0.01)

    def test_recency_boost_one_recent(self, intent_service):
        """One recent + one old goal should get 1.1x severity boost."""
        now = datetime.now(timezone.utc)
        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.5,
                            created_at=now - timedelta(hours=1))
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.5,
                            created_at=now - timedelta(days=10))

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])

        assert len(conflicts) == 1
        assert conflicts[0].severity == pytest.approx(0.55, abs=0.01)

    def test_no_conflict_between_compatible_intents(self, intent_service):
        """Compatible intents (e.g., expansion + targeted) should not conflict."""
        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.9)
        goal_b = _make_goal("g2", GoalIntentType.TARGETED_INVESTMENT, 0.9)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])
        assert len(conflicts) == 0

    def test_no_conflict_when_no_intent(self, intent_service):
        """Goals without primary_intent should be skipped."""
        goal_a = Goal(
            goal_id="g1", title="Test", description="Test",
            project_id="project-001", status=GoalStatus.IN_PROGRESS,
        )
        goal_b = _make_goal("g2", GoalIntentType.EXPANSION, 0.9)

        conflicts = intent_service.detect_conflicts([goal_a, goal_b])
        assert len(conflicts) == 0

    def test_multiple_conflict_pairs(self, intent_service):
        """Three goals with two conflicting pairs should detect both."""
        goal_exp = _make_goal("g_exp", GoalIntentType.EXPANSION, 0.7)
        goal_con = _make_goal("g_con", GoalIntentType.CONSOLIDATION, 0.7)
        goal_qual = _make_goal("g_qual", GoalIntentType.QUALITY_FOCUSED, 0.7)

        conflicts = intent_service.detect_conflicts([goal_exp, goal_con, goal_qual])

        # EXPANSION vs CONSOLIDATION, EXPANSION vs QUALITY_FOCUSED
        assert len(conflicts) == 2


# ============================================================================
# User Reconciliation Weight (GoalService)
# ============================================================================


class TestGoalServiceReconciliationWeight:
    """Test GoalService.set_reconciliation_weight."""

    @pytest.mark.asyncio
    async def test_set_weight(self, goal_service):
        """Setting weight should persist on the goal."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8)
        goal_service._goals["g1"] = goal

        result = await goal_service.set_reconciliation_weight("g1", 0.75)

        assert result is not None
        assert result.reconciliation_weight == 0.75
        goal_service._save_goal_to_redis.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_weight(self, goal_service):
        """Setting weight to None should reset to auto."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8,
                          reconciliation_weight=0.75)
        goal_service._goals["g1"] = goal

        result = await goal_service.set_reconciliation_weight("g1", None)

        assert result is not None
        assert result.reconciliation_weight is None

    @pytest.mark.asyncio
    async def test_set_weight_not_found(self, goal_service):
        """Setting weight on non-existent goal should return None."""
        result = await goal_service.set_reconciliation_weight("nonexistent", 0.5)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_weight_deleted_goal(self, goal_service):
        """Setting weight on deleted goal should return None."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8)
        goal.deleted_at = datetime.now(timezone.utc)
        goal_service._goals["g1"] = goal

        result = await goal_service.set_reconciliation_weight("g1", 0.5)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_weight_updates_timestamp(self, goal_service):
        """Setting weight should update the goal's updated_at timestamp."""
        goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8)
        original_updated = goal.updated_at
        goal_service._goals["g1"] = goal

        result = await goal_service.set_reconciliation_weight("g1", 0.5)

        assert result.updated_at >= original_updated


# ============================================================================
# Model Tests
# ============================================================================


class TestGoalConflictModel:
    """Test GoalConflict model enhancements."""

    def test_default_not_irreconcilable(self):
        """GoalConflict should default to not irreconcilable."""
        conflict = GoalConflict(
            conflict_id="c1",
            goal_id_a="g1",
            goal_id_b="g2",
            description="Test",
            severity=0.5,
        )
        assert conflict.is_irreconcilable is False
        assert conflict.resolution_hint is None

    def test_irreconcilable_with_hint(self):
        """GoalConflict can be created with irreconcilable flag and hint."""
        conflict = GoalConflict(
            conflict_id="c1",
            goal_id_a="g1",
            goal_id_b="g2",
            description="Test conflict",
            severity=0.85,
            is_irreconcilable=True,
            resolution_hint="Set weights",
        )
        assert conflict.is_irreconcilable is True
        assert conflict.resolution_hint == "Set weights"


class TestGoalReconciliationWeightRequest:
    """Test GoalSetReconciliationWeightRequest model."""

    def test_valid_weight(self):
        """Valid weight between 0.0 and 1.0 should be accepted."""
        req = GoalSetReconciliationWeightRequest(reconciliation_weight=0.75)
        assert req.reconciliation_weight == 0.75

    def test_null_weight(self):
        """Null weight should be accepted (reset to auto)."""
        req = GoalSetReconciliationWeightRequest(reconciliation_weight=None)
        assert req.reconciliation_weight is None

    def test_boundary_zero(self):
        """Weight of 0.0 should be valid."""
        req = GoalSetReconciliationWeightRequest(reconciliation_weight=0.0)
        assert req.reconciliation_weight == 0.0

    def test_boundary_one(self):
        """Weight of 1.0 should be valid."""
        req = GoalSetReconciliationWeightRequest(reconciliation_weight=1.0)
        assert req.reconciliation_weight == 1.0


class TestGoalModelReconciliationWeight:
    """Test reconciliation_weight field on Goal model."""

    def test_default_none(self):
        """reconciliation_weight should default to None (auto)."""
        goal = Goal(
            goal_id="g1", title="Test", description="Test",
            project_id="project-001",
        )
        assert goal.reconciliation_weight is None

    def test_set_weight(self):
        """reconciliation_weight can be set to a float."""
        goal = Goal(
            goal_id="g1", title="Test", description="Test",
            project_id="project-001",
            reconciliation_weight=0.75,
        )
        assert goal.reconciliation_weight == 0.75


class TestGoalConflictListResponse:
    """Test GoalConflictListResponse model enhancements."""

    def test_has_irreconcilable_true(self):
        """has_irreconcilable should be True when any conflict is irreconcilable."""
        resp = GoalConflictListResponse(
            project_id="p1",
            conflicts=[
                GoalConflict(
                    conflict_id="c1", goal_id_a="g1", goal_id_b="g2",
                    description="Test", severity=0.85, is_irreconcilable=True,
                ),
            ],
            total=1,
            has_irreconcilable=True,
        )
        assert resp.has_irreconcilable is True

    def test_has_irreconcilable_false(self):
        """has_irreconcilable should be False when no conflicts are irreconcilable."""
        resp = GoalConflictListResponse(
            project_id="p1",
            conflicts=[
                GoalConflict(
                    conflict_id="c1", goal_id_a="g1", goal_id_b="g2",
                    description="Test", severity=0.3,
                ),
            ],
            total=1,
            has_irreconcilable=False,
        )
        assert resp.has_irreconcilable is False


# ============================================================================
# API Endpoint Tests
# ============================================================================


class TestReconciliationWeightAPI:
    """Test the PUT /goals/{goal_id}/reconciliation-weight endpoint."""

    def test_set_weight_endpoint(self):
        """Test the reconciliation weight endpoint via TestClient."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.work_map import goals_router

        app = FastAPI()
        app.include_router(goals_router)

        mock_goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8)
        mock_goal.reconciliation_weight = 0.75

        with patch("api.work_map.get_goal_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_goal = AsyncMock(return_value=mock_goal)
            mock_svc.set_reconciliation_weight = AsyncMock(return_value=mock_goal)
            mock_get_svc.return_value = mock_svc

            client = TestClient(app)
            resp = client.put(
                "/goals/g1/reconciliation-weight",
                json={"reconciliation_weight": 0.75},
            )

            assert resp.status_code == 200
            assert resp.json()["reconciliation_weight"] == 0.75
            mock_svc.set_reconciliation_weight.assert_called_once_with("g1", 0.75)

    def test_set_weight_not_found(self):
        """Test 404 when goal not found."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.work_map import goals_router

        app = FastAPI()
        app.include_router(goals_router)

        with patch("api.work_map.get_goal_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_goal = AsyncMock(return_value=None)
            mock_get_svc.return_value = mock_svc

            client = TestClient(app)
            resp = client.put(
                "/goals/nonexistent/reconciliation-weight",
                json={"reconciliation_weight": 0.5},
            )

            assert resp.status_code == 404

    def test_clear_weight_endpoint(self):
        """Test setting weight to null (auto mode)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.work_map import goals_router

        app = FastAPI()
        app.include_router(goals_router)

        mock_goal = _make_goal("g1", GoalIntentType.EXPANSION, 0.8)
        mock_goal.reconciliation_weight = None

        with patch("api.work_map.get_goal_service") as mock_get_svc:
            mock_svc = MagicMock()
            mock_svc.get_goal = AsyncMock(return_value=mock_goal)
            mock_svc.set_reconciliation_weight = AsyncMock(return_value=mock_goal)
            mock_get_svc.return_value = mock_svc

            client = TestClient(app)
            resp = client.put(
                "/goals/g1/reconciliation-weight",
                json={"reconciliation_weight": None},
            )

            assert resp.status_code == 200
            assert resp.json()["reconciliation_weight"] is None


class TestConflictsAPIEnhancement:
    """Test that conflicts endpoint returns enhanced fields."""

    def test_conflicts_include_irreconcilable(self):
        """Test that conflicts endpoint returns is_irreconcilable and has_irreconcilable."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.work_map import goals_router

        app = FastAPI()
        app.include_router(goals_router)

        goal_a = _make_goal("g1", GoalIntentType.EXPANSION, 0.9)
        goal_b = _make_goal("g2", GoalIntentType.CONSOLIDATION, 0.9)

        with (
            patch("api.work_map.get_goal_service") as mock_goal_svc,
            patch("api.work_map.get_goal_intent_service") as mock_intent_svc,
        ):
            mock_gs = MagicMock()
            mock_gs.list_active_goals = AsyncMock(return_value=[goal_a, goal_b])
            mock_goal_svc.return_value = mock_gs

            intent_svc = GoalIntentService()
            mock_intent_svc.return_value = intent_svc

            client = TestClient(app)
            resp = client.get("/goals/project/project-001/conflicts")

            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["has_irreconcilable"] is True
            assert data["conflicts"][0]["is_irreconcilable"] is True
            assert data["conflicts"][0]["resolution_hint"] is not None
