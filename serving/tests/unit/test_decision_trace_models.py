"""Unit tests for decision trace models.

Tests DecisionPointType enum, DecisionTrigger, DecisionContext,
DecisionImpact, and DecisionTrace models.
"""

import pytest
from datetime import datetime, timezone

from models.decision_trace import (
    DecisionContext,
    DecisionImpact,
    DecisionPointType,
    DecisionTrace,
    DecisionTrigger,
)


# =============================================================================
# DecisionPointType
# =============================================================================


class TestDecisionPointType:
    """Tests for the DecisionPointType enum."""

    def test_all_decision_types_exist(self):
        """All required decision point types are defined."""
        assert DecisionPointType.PROFILE_SHIFT == "profile_shift"
        assert DecisionPointType.BUCKET_REORGANIZATION == "bucket_reorganization"
        assert DecisionPointType.TASK_MOVEMENT == "task_movement"
        assert DecisionPointType.CONFLICT_IDENTIFIED == "conflict_identified"
        assert DecisionPointType.CONFLICT_RESOLVED == "conflict_resolved"
        assert DecisionPointType.WORKER_ASSIGNMENT == "worker_assignment"

    def test_decision_type_count(self):
        """All six decision point types are present."""
        assert len(DecisionPointType) == 6


# =============================================================================
# DecisionTrigger
# =============================================================================


class TestDecisionTrigger:
    """Tests for the DecisionTrigger model."""

    def test_required_fields(self):
        """Trigger requires trigger_type."""
        trigger = DecisionTrigger(trigger_type="new_goal")
        assert trigger.trigger_type == "new_goal"
        assert trigger.source_id == ""
        assert trigger.source_type == ""
        assert trigger.description == ""

    def test_full_trigger(self):
        """Trigger with all fields populated."""
        trigger = DecisionTrigger(
            trigger_type="worker_feedback",
            source_id="worker-123",
            source_type="feedback_signal",
            description="Worker reported blocker on authentication task",
        )
        assert trigger.trigger_type == "worker_feedback"
        assert trigger.source_id == "worker-123"
        assert trigger.source_type == "feedback_signal"
        assert trigger.description == "Worker reported blocker on authentication task"


# =============================================================================
# DecisionContext
# =============================================================================


class TestDecisionContext:
    """Tests for the DecisionContext model."""

    def test_empty_context(self):
        """Context with all defaults."""
        ctx = DecisionContext()
        assert ctx.profile_version is None
        assert ctx.profile_id is None
        assert ctx.bucket_tree_version is None
        assert ctx.active_goal_ids == []
        assert ctx.active_worker_count is None
        assert ctx.additional == {}

    def test_full_context(self):
        """Context with all fields populated."""
        ctx = DecisionContext(
            profile_version=3,
            profile_id="profile_abc",
            bucket_tree_version=5,
            active_goal_ids=["goal-1", "goal-2"],
            active_worker_count=4,
            additional={"total_items": 15},
        )
        assert ctx.profile_version == 3
        assert ctx.profile_id == "profile_abc"
        assert ctx.bucket_tree_version == 5
        assert len(ctx.active_goal_ids) == 2
        assert ctx.active_worker_count == 4
        assert ctx.additional["total_items"] == 15


# =============================================================================
# DecisionImpact
# =============================================================================


class TestDecisionImpact:
    """Tests for the DecisionImpact model."""

    def test_empty_impact(self):
        """Impact with all defaults."""
        impact = DecisionImpact()
        assert impact.affected_item_ids == []
        assert impact.affected_bucket_ids == []
        assert impact.profile_version_before is None
        assert impact.profile_version_after is None
        assert impact.tree_version_before is None
        assert impact.tree_version_after is None
        assert impact.cascading_effects == []

    def test_full_impact(self):
        """Impact with all fields populated."""
        impact = DecisionImpact(
            affected_item_ids=["item-1", "item-2"],
            affected_bucket_ids=["bucket-a"],
            profile_version_before=2,
            profile_version_after=3,
            tree_version_before=4,
            tree_version_after=5,
            cascading_effects=["3 items moved to higher-priority bucket"],
        )
        assert len(impact.affected_item_ids) == 2
        assert len(impact.affected_bucket_ids) == 1
        assert impact.profile_version_before == 2
        assert impact.profile_version_after == 3
        assert impact.tree_version_before == 4
        assert impact.tree_version_after == 5
        assert len(impact.cascading_effects) == 1


# =============================================================================
# DecisionTrace
# =============================================================================


class TestDecisionTrace:
    """Tests for the DecisionTrace model."""

    def test_minimal_trace(self):
        """Trace with only required fields."""
        trace = DecisionTrace(
            trace_id="trace-profile_shift-abc123",
            project_id="proj-1",
            decision_type=DecisionPointType.PROFILE_SHIFT,
            trigger=DecisionTrigger(trigger_type="new_goal"),
            decision_summary="Profile updated for new expansion goal",
        )
        assert trace.trace_id == "trace-profile_shift-abc123"
        assert trace.project_id == "proj-1"
        assert trace.decision_type == DecisionPointType.PROFILE_SHIFT
        assert trace.trigger.trigger_type == "new_goal"
        assert trace.decision_summary == "Profile updated for new expansion goal"
        assert trace.key_factors == []
        assert trace.related_trace_ids == []
        assert isinstance(trace.timestamp, datetime)

    def test_full_trace(self):
        """Trace with all fields populated."""
        trace = DecisionTrace(
            trace_id="trace-bucket_reorganization-def456",
            project_id="proj-2",
            decision_type=DecisionPointType.BUCKET_REORGANIZATION,
            trigger=DecisionTrigger(
                trigger_type="profile_shift",
                source_id="goal-42",
                source_type="goal",
                description="Profile weights shifted after new goal",
            ),
            context=DecisionContext(
                profile_version=3,
                profile_id="profile_xyz",
                bucket_tree_version=7,
                active_goal_ids=["goal-42", "goal-43"],
            ),
            decision_summary="Reorganized 5 buckets, moved 8 items",
            key_factors=[
                "Profile weights shifted, changing bucket membership criteria",
                "Bucket structure changed: +2 -1 buckets",
                "3 in-progress items protected from disruption",
            ],
            impact=DecisionImpact(
                affected_item_ids=["item-1", "item-2", "item-3"],
                affected_bucket_ids=["bucket-a", "bucket-b"],
                tree_version_before=7,
                tree_version_after=8,
            ),
            related_trace_ids=["trace-profile_shift-abc123"],
        )
        assert trace.decision_type == DecisionPointType.BUCKET_REORGANIZATION
        assert len(trace.key_factors) == 3
        assert len(trace.impact.affected_item_ids) == 3
        assert trace.related_trace_ids == ["trace-profile_shift-abc123"]

    def test_trace_serialization(self):
        """Trace can be serialized to JSON and back."""
        trace = DecisionTrace(
            trace_id="trace-test-ser",
            project_id="proj-1",
            decision_type=DecisionPointType.WORKER_ASSIGNMENT,
            trigger=DecisionTrigger(trigger_type="assignment"),
            decision_summary="Assigned worker-5 to item-10",
            key_factors=["Context affinity with domain"],
        )
        json_str = trace.model_dump_json()
        restored = DecisionTrace.model_validate_json(json_str)
        assert restored.trace_id == trace.trace_id
        assert restored.decision_type == trace.decision_type
        assert restored.key_factors == trace.key_factors

    def test_trace_timestamp_is_utc(self):
        """Trace timestamp defaults to UTC."""
        trace = DecisionTrace(
            trace_id="trace-tz-test",
            project_id="proj-1",
            decision_type=DecisionPointType.TASK_MOVEMENT,
            trigger=DecisionTrigger(trigger_type="manual"),
            decision_summary="Task moved between buckets",
        )
        assert trace.timestamp.tzinfo == timezone.utc
