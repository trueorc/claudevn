"""Tests for decision trace integration at planning decision points.

Tests cover:
- DecisionTraceService emitting events to ObservabilityEventBus
- PlannerProfileService recording traces on profile construction and feedback
- AssignmentService recording traces on worker assignment
- ConflictDetectionService recording traces on conflict identification and resolution
- All integrations are non-critical (failures logged, not raised)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from models.conflict import (
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    PlannerHandling,
    ResolutionAuthority,
    UserResponse,
    UserResponseType,
)
from models.decision_trace import (
    DecisionImpact,
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)
from models.feedback import FeedbackPattern, FeedbackType
from models.work_map import Goal, GoalConflict, GoalIntentType, GoalStatus, IssuePriority


# =============================================================================
# Helpers
# =============================================================================


def make_mock_redis():
    """Create a mock Redis client."""
    mock_redis = MagicMock()
    mock_redis._prefix = "claudevn:"
    mock_redis._redis = AsyncMock()
    return mock_redis


def make_mock_trace_service():
    """Create a mock DecisionTraceService."""
    mock = MagicMock()
    mock.record = AsyncMock(return_value=DecisionTrace(
        trace_id="trace-test-mock",
        project_id="proj-1",
        decision_type=DecisionPointType.PROFILE_SHIFT,
        trigger=DecisionTrigger(trigger_type="test"),
        decision_summary="Test trace",
    ))
    mock.record_trace = AsyncMock()
    return mock


# =============================================================================
# Test EventBus Integration in DecisionTraceService
# =============================================================================


class TestDecisionTraceEventEmission:
    """Test that DecisionTraceService emits events to the event bus."""

    @pytest.mark.asyncio
    async def test_record_trace_emits_event(self):
        """Recording a trace emits a DecisionTraceEvent."""
        from services.decision_trace_service import DecisionTraceService

        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)

        trace = DecisionTrace(
            trace_id="trace-emit-test",
            project_id="proj-1",
            decision_type=DecisionPointType.PROFILE_SHIFT,
            trigger=DecisionTrigger(trigger_type="new_goal"),
            decision_summary="Test emission",
        )

        mock_bus = MagicMock()
        mock_bus.emit_event = AsyncMock()

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_bus):
            await service.record_trace(trace)

        mock_bus.emit_event.assert_called_once()
        event = mock_bus.emit_event.call_args[0][0]
        assert event.trace_id == "trace-emit-test"
        assert event.decision_type == DecisionPointType.PROFILE_SHIFT
        assert event.session_id == "proj-1"

    @pytest.mark.asyncio
    async def test_event_emission_failure_does_not_raise(self):
        """Event bus failure doesn't interrupt trace recording."""
        from services.decision_trace_service import DecisionTraceService

        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)

        trace = DecisionTrace(
            trace_id="trace-fail-test",
            project_id="proj-1",
            decision_type=DecisionPointType.TASK_MOVEMENT,
            trigger=DecisionTrigger(trigger_type="test"),
            decision_summary="Test",
        )

        with patch("services.observability_event_bus.get_event_bus", side_effect=RuntimeError("No bus")):
            # Should not raise
            await service.record_trace(trace)

    @pytest.mark.asyncio
    async def test_event_contains_impact_counts(self):
        """Emitted event contains affected item and bucket counts."""
        from services.decision_trace_service import DecisionTraceService

        mock_redis = make_mock_redis()
        service = DecisionTraceService(redis_client=mock_redis)

        trace = DecisionTrace(
            trace_id="trace-impact-test",
            project_id="proj-1",
            decision_type=DecisionPointType.BUCKET_REORGANIZATION,
            trigger=DecisionTrigger(trigger_type="profile_shift"),
            decision_summary="Reorg",
            impact=DecisionImpact(
                affected_item_ids=["item-1", "item-2", "item-3"],
                affected_bucket_ids=["bucket-a"],
            ),
        )

        mock_bus = MagicMock()
        mock_bus.emit_event = AsyncMock()

        with patch("services.observability_event_bus.get_event_bus", return_value=mock_bus):
            await service.record_trace(trace)

        event = mock_bus.emit_event.call_args[0][0]
        assert event.affected_item_count == 3
        assert event.affected_bucket_count == 1


# =============================================================================
# Test Profile Shift Trace Integration
# =============================================================================


class TestProfileShiftTracing:
    """Test that planner profile service records traces on profile changes."""

    @pytest.mark.asyncio
    async def test_construct_profile_records_trace(self):
        """Profile construction records a PROFILE_SHIFT trace."""
        from services.planner_profile_service import PlannerProfileService

        service = PlannerProfileService(redis_client=None)
        goal = Goal(
            goal_id="goal-1",
            title="Build reporting",
            description="Add reporting dashboard with new features",
            project_id="proj-1",
            primary_intent=GoalIntentType.EXPANSION,
            intent_strength=0.7,
        )

        mock_trace_svc = make_mock_trace_service()

        with patch("services.decision_trace_service.get_decision_trace_service", return_value=mock_trace_svc):
            await service.construct_profile("proj-1", [goal])

        mock_trace_svc.record.assert_called_once()
        call_kwargs = mock_trace_svc.record.call_args[1]
        assert call_kwargs["decision_type"] == DecisionPointType.PROFILE_SHIFT
        assert call_kwargs["project_id"] == "proj-1"
        assert "goal" in call_kwargs["trigger"].trigger_type

    @pytest.mark.asyncio
    async def test_worker_feedback_records_trace(self):
        """Worker feedback profile update records a PROFILE_SHIFT trace."""
        from services.planner_profile_service import PlannerProfileService

        service = PlannerProfileService(redis_client=None)
        goal = Goal(
            goal_id="goal-1",
            title="Build things",
            description="Build new features and expand",
            project_id="proj-1",
        )

        mock_trace_svc = make_mock_trace_service()

        with patch("services.decision_trace_service.get_decision_trace_service", return_value=mock_trace_svc):
            await service.construct_profile("proj-1", [goal])
            mock_trace_svc.record.reset_mock()

            await service.update_for_worker_feedback(
                project_id="proj-1",
                feedback_type="blocker",
                feedback_data={
                    "worker_id": "worker-1",
                    "task_id": "task-1",
                    "blocking_item_id": "item-42",
                },
            )

        mock_trace_svc.record.assert_called_once()
        call_kwargs = mock_trace_svc.record.call_args[1]
        assert call_kwargs["decision_type"] == DecisionPointType.PROFILE_SHIFT
        assert "worker_feedback" in call_kwargs["trigger"].trigger_type

    @pytest.mark.asyncio
    async def test_profile_trace_failure_does_not_raise(self):
        """Trace service failure doesn't interrupt profile construction."""
        from services.planner_profile_service import PlannerProfileService

        service = PlannerProfileService(redis_client=None)
        goal = Goal(
            goal_id="goal-1",
            title="Build things",
            description="Build new features",
            project_id="proj-1",
        )

        with patch("services.decision_trace_service.get_decision_trace_service", side_effect=RuntimeError("Not available")):
            profile = await service.construct_profile("proj-1", [goal])
            assert profile is not None


# =============================================================================
# Test Worker Assignment Trace Integration
# =============================================================================


class TestAssignmentTracing:
    """Test that assignment service records traces on worker assignments."""

    @pytest.mark.asyncio
    async def test_assign_work_records_trace(self):
        """Worker assignment records a WORKER_ASSIGNMENT trace."""
        from services.assignment_service import AssignmentService
        from models.work_map import WorkItem, WorkStatus

        service = AssignmentService(redis_client=None)

        work = WorkItem(
            work_id="work-1",
            title="Implement auth",
            description="Add authentication",
            project_id="proj-1",
            status=WorkStatus.PENDING,
            branch_name="feat/work-1",
        )
        service._work_items["work-1"] = work

        mock_trace_svc = make_mock_trace_service()

        with patch("services.decision_trace_service.get_decision_trace_service", return_value=mock_trace_svc):
            result = await service.assign_work(
                work_id="work-1",
                compute_id="compute-5",
                skills=["python", "testing"],
            )

        assert result is not None
        mock_trace_svc.record.assert_called_once()
        call_kwargs = mock_trace_svc.record.call_args[1]
        assert call_kwargs["decision_type"] == DecisionPointType.WORKER_ASSIGNMENT
        assert "compute-5" in call_kwargs["trigger"].source_id

    @pytest.mark.asyncio
    async def test_assignment_trace_failure_does_not_raise(self):
        """Trace failure doesn't interrupt assignment."""
        from services.assignment_service import AssignmentService
        from models.work_map import WorkItem, WorkStatus

        service = AssignmentService(redis_client=None)
        work = WorkItem(
            work_id="work-2",
            title="Test item",
            description="Test",
            project_id="proj-1",
            status=WorkStatus.PENDING,
            branch_name="feat/work-2",
        )
        service._work_items["work-2"] = work

        with patch("services.decision_trace_service.get_decision_trace_service", side_effect=RuntimeError("Not available")):
            result = await service.assign_work(
                work_id="work-2",
                compute_id="compute-1",
                skills=["coding"],
            )
            assert result is not None


# =============================================================================
# Test Conflict Trace Integration
# =============================================================================


class TestConflictTracing:
    """Test that conflict detection records traces on identification and resolution."""

    @pytest.mark.asyncio
    async def test_detect_all_records_identification_traces(self):
        """Conflict detection records CONFLICT_IDENTIFIED traces."""
        from services.conflict_detection_service import ConflictDetectionService

        service = ConflictDetectionService(redis_client=None)

        goal_a = Goal(
            goal_id="goal-a",
            title="Expand features",
            description="Build new",
            project_id="proj-1",
            primary_intent=GoalIntentType.EXPANSION,
            intent_strength=0.8,
        )
        goal_b = Goal(
            goal_id="goal-b",
            title="Stabilize",
            description="Harden",
            project_id="proj-1",
            primary_intent=GoalIntentType.CONSOLIDATION,
            intent_strength=0.6,
        )
        gc = GoalConflict(
            conflict_id="conflict-1",
            goal_id_a="goal-a",
            goal_id_b="goal-b",
            description="Expansion vs consolidation",
            severity=0.7,
            is_irreconcilable=True,
        )

        mock_trace_svc = make_mock_trace_service()

        with patch("services.decision_trace_service.get_decision_trace_service", return_value=mock_trace_svc):
            results = await service.detect_all_conflicts(
                project_id="proj-1",
                goals=[goal_a, goal_b],
                goal_conflicts=[gc],
            )

        assert len(results) >= 1
        mock_trace_svc.record.assert_called()
        calls = mock_trace_svc.record.call_args_list
        identified_calls = [
            c for c in calls
            if c[1].get("decision_type") == DecisionPointType.CONFLICT_IDENTIFIED
        ]
        assert len(identified_calls) >= 1

    @pytest.mark.asyncio
    async def test_resolve_conflict_records_resolution_trace(self):
        """Conflict resolution records CONFLICT_RESOLVED trace."""
        from services.conflict_detection_service import ConflictDetectionService

        service = ConflictDetectionService(redis_client=None)

        goal_a = Goal(
            goal_id="goal-a",
            title="Expand",
            description="Build",
            project_id="proj-1",
            primary_intent=GoalIntentType.EXPANSION,
            intent_strength=0.8,
        )
        goal_b = Goal(
            goal_id="goal-b",
            title="Stabilize",
            description="Harden",
            project_id="proj-1",
            primary_intent=GoalIntentType.CONSOLIDATION,
            intent_strength=0.6,
        )
        gc = GoalConflict(
            conflict_id="conflict-resolve-1",
            goal_id_a="goal-a",
            goal_id_b="goal-b",
            description="Test",
            severity=0.7,
        )

        mock_trace_svc = make_mock_trace_service()

        with patch("services.decision_trace_service.get_decision_trace_service", return_value=mock_trace_svc):
            await service.detect_all_conflicts(
                project_id="proj-1",
                goals=[goal_a, goal_b],
                goal_conflicts=[gc],
            )
            mock_trace_svc.record.reset_mock()

            response = UserResponse(
                response_type=UserResponseType.SET_PRIORITY,
                description="Prioritize stability",
                affected_goal_ids=["goal-b"],
            )
            result = await service.resolve_conflict(
                "proj-1", "conflict-resolve-1", response
            )

        assert result is not None
        mock_trace_svc.record.assert_called_once()
        call_kwargs = mock_trace_svc.record.call_args[1]
        assert call_kwargs["decision_type"] == DecisionPointType.CONFLICT_RESOLVED
        assert "user_response" in call_kwargs["trigger"].trigger_type

    @pytest.mark.asyncio
    async def test_conflict_trace_failure_does_not_raise(self):
        """Trace failure doesn't interrupt conflict detection."""
        from services.conflict_detection_service import ConflictDetectionService

        service = ConflictDetectionService(redis_client=None)

        with patch("services.decision_trace_service.get_decision_trace_service", side_effect=RuntimeError("Not available")):
            results = await service.detect_all_conflicts(
                project_id="proj-1",
                dependencies={"a": ["b"], "b": ["a"]},
            )
            assert len(results) >= 1
