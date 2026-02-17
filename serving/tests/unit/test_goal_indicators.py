"""Tests for goal completion indicators and evaluation tracking (#460).

Tests:
- Goal text evaluation tracking (goal_text_evaluated field)
- Updated conversation status calculation (factors in goal_text_evaluated)
- GoalEvaluationSummary model
- Evaluation summary API endpoint
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.goal_comment_service import GoalCommentService
from models.work_map import (
    Goal,
    GoalStatus,
    GoalCreateRequest,
    GoalComment,
    GoalCommentCreateRequest,
    GoalCommentUpdateRequest,
    GoalEvaluationSummary,
    EvaluationItemStatus,
    EvaluationStatus,
    ConversationStatus,
    IssuePriority,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create GoalCommentService without Redis."""
    return GoalCommentService(redis_client=None)


@pytest.fixture
def sample_goal():
    """Create a sample goal."""
    return Goal(
        goal_id="goal_test460",
        title="Test Goal",
        description="A test goal description for indicators",
        priority=IssuePriority.P1,
        status=GoalStatus.PLANNING,
    )


@pytest.fixture
def evaluated_goal():
    """Create a goal with goal_text_evaluated=True."""
    return Goal(
        goal_id="goal_eval460",
        title="Evaluated Goal",
        description="A goal that has been decomposed",
        priority=IssuePriority.P1,
        status=GoalStatus.IN_PROGRESS,
        goal_text_evaluated=True,
        decomposition_id="decomp_test123",
    )


# =============================================================================
# Goal Text Evaluation Field Tests
# =============================================================================


class TestGoalTextEvaluated:
    """Test the goal_text_evaluated field on Goal model."""

    def test_default_is_false(self):
        """New goals should have goal_text_evaluated=False by default."""
        goal = Goal(
            goal_id="goal_new",
            title="New Goal",
            description="Description",
        )
        assert goal.goal_text_evaluated is False

    def test_can_set_to_true(self):
        """goal_text_evaluated can be set to True."""
        goal = Goal(
            goal_id="goal_set",
            title="Set Goal",
            description="Description",
            goal_text_evaluated=True,
        )
        assert goal.goal_text_evaluated is True

    def test_serialization(self):
        """goal_text_evaluated should serialize to JSON."""
        goal = Goal(
            goal_id="goal_ser",
            title="Serialize Goal",
            description="Description",
            goal_text_evaluated=True,
        )
        data = goal.model_dump()
        assert "goal_text_evaluated" in data
        assert data["goal_text_evaluated"] is True


# =============================================================================
# Conversation Status Calculation Tests (with goal_text_evaluated)
# =============================================================================


class TestConversationStatusWithGoalText:
    """Test updated conversation status calculation that factors in goal_text_evaluated."""

    @pytest.mark.asyncio
    async def test_no_comments_not_evaluated_goal(self, service, sample_goal):
        """Goal with no comments and not evaluated -> NO_COMMENTS."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})
        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.NO_COMMENTS

    @pytest.mark.asyncio
    async def test_no_comments_evaluated_goal(self, service, evaluated_goal):
        """Goal with no comments but evaluated text -> COMPLETE."""
        service.set_goals_reference({evaluated_goal.goal_id: evaluated_goal})
        result = await service.list_comments(evaluated_goal.goal_id)
        assert result.conversation_status == ConversationStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_evaluated_goal_with_unevaluated_comment(self, service, evaluated_goal):
        """Goal text evaluated but comment not evaluated -> PENDING."""
        service.set_goals_reference({evaluated_goal.goal_id: evaluated_goal})

        await service.create_comment(
            evaluated_goal.goal_id,
            GoalCommentCreateRequest(content="New unevaluated comment"),
        )

        result = await service.list_comments(evaluated_goal.goal_id)
        assert result.conversation_status == ConversationStatus.PENDING

    @pytest.mark.asyncio
    async def test_evaluated_goal_with_all_evaluated_comments(self, service, evaluated_goal):
        """Goal text evaluated and all comments evaluated -> COMPLETE."""
        service.set_goals_reference({evaluated_goal.goal_id: evaluated_goal})

        comment = await service.create_comment(
            evaluated_goal.goal_id,
            GoalCommentCreateRequest(content="Comment to evaluate"),
        )
        await service.update_comment(
            comment.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATED),
        )

        result = await service.list_comments(evaluated_goal.goal_id)
        assert result.conversation_status == ConversationStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_unevaluated_goal_with_evaluated_comments(self, service, sample_goal):
        """Goal text not evaluated, even with all comments evaluated -> PENDING."""
        service.set_goals_reference({sample_goal.goal_id: sample_goal})
        assert sample_goal.goal_text_evaluated is False

        comment = await service.create_comment(
            sample_goal.goal_id,
            GoalCommentCreateRequest(content="Evaluated comment"),
        )
        await service.update_comment(
            comment.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATED),
        )

        result = await service.list_comments(sample_goal.goal_id)
        assert result.conversation_status == ConversationStatus.PENDING

    @pytest.mark.asyncio
    async def test_evaluating_takes_precedence(self, service, evaluated_goal):
        """EVALUATING status takes precedence regardless of goal text state."""
        service.set_goals_reference({evaluated_goal.goal_id: evaluated_goal})

        comment = await service.create_comment(
            evaluated_goal.goal_id,
            GoalCommentCreateRequest(content="Evaluating comment"),
        )
        await service.update_comment(
            comment.comment_id,
            GoalCommentUpdateRequest(evaluation_status=EvaluationStatus.EVALUATING),
        )

        result = await service.list_comments(evaluated_goal.goal_id)
        assert result.conversation_status == ConversationStatus.EVALUATING


# =============================================================================
# GoalEvaluationSummary Model Tests
# =============================================================================


class TestGoalEvaluationSummary:
    """Test the GoalEvaluationSummary response model."""

    def test_all_evaluated_summary(self):
        """Test summary when everything is evaluated."""
        summary = GoalEvaluationSummary(
            goal_id="goal_test",
            all_evaluated=True,
            goal_text_evaluated=True,
            has_decomposition=True,
            decomposition_id="decomp_123",
            items=[
                EvaluationItemStatus(
                    item_type="goal_text",
                    content_preview="Goal description",
                    evaluation_status="evaluated",
                ),
                EvaluationItemStatus(
                    item_type="comment",
                    item_id="comment_1",
                    content_preview="Comment content",
                    evaluation_status="evaluated",
                ),
            ],
            total_items=2,
            evaluated_count=2,
            pending_count=0,
        )
        assert summary.all_evaluated is True
        assert summary.evaluated_count == 2
        assert summary.pending_count == 0

    def test_partial_evaluated_summary(self):
        """Test summary when some items are not evaluated."""
        summary = GoalEvaluationSummary(
            goal_id="goal_test",
            all_evaluated=False,
            goal_text_evaluated=True,
            has_decomposition=True,
            items=[
                EvaluationItemStatus(
                    item_type="goal_text",
                    content_preview="Goal description",
                    evaluation_status="evaluated",
                ),
                EvaluationItemStatus(
                    item_type="comment",
                    item_id="comment_1",
                    content_preview="Unevaluated comment",
                    evaluation_status="not_evaluated",
                ),
            ],
            total_items=2,
            evaluated_count=1,
            pending_count=1,
        )
        assert summary.all_evaluated is False
        assert summary.evaluated_count == 1
        assert summary.pending_count == 1


# =============================================================================
# Evaluation Summary API Endpoint Tests
# =============================================================================


class TestEvaluationSummaryEndpoint:
    """Test GET /goals/{goal_id}/evaluation-summary endpoint."""

    @pytest.fixture
    def app(self):
        """Create test FastAPI app with goals router."""
        from api.work_map import goals_router
        app = FastAPI()
        app.include_router(goals_router, prefix="/api/v1")
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_evaluation_summary_returns_data(self, client):
        """Test that evaluation summary endpoint returns proper structure."""
        mock_goal = Goal(
            goal_id="goal_api_test",
            title="API Test Goal",
            description="A goal for testing the API endpoint",
            priority=IssuePriority.P1,
            goal_text_evaluated=True,
            decomposition_id="decomp_api_test",
        )

        mock_comment = GoalComment(
            comment_id="comment_api_1",
            goal_id="goal_api_test",
            content="A test comment",
            evaluation_status=EvaluationStatus.EVALUATED,
        )

        mock_work_map_service = MagicMock()
        mock_work_map_service.get_goal = AsyncMock(return_value=mock_goal)

        mock_comment_service = MagicMock()
        mock_comment_service.list_comments = AsyncMock(return_value=MagicMock(
            items=[mock_comment],
            total=1,
        ))

        with patch("api.work_map.get_work_map_service", return_value=mock_work_map_service), \
             patch("api.work_map.get_goal_comment_service", return_value=mock_comment_service):
            response = client.get("/api/v1/goals/goal_api_test/evaluation-summary")

        assert response.status_code == 200
        data = response.json()
        assert data["goal_id"] == "goal_api_test"
        assert data["all_evaluated"] is True
        assert data["goal_text_evaluated"] is True
        assert data["has_decomposition"] is True
        assert data["decomposition_id"] == "decomp_api_test"
        assert data["total_items"] == 2  # goal_text + 1 comment
        assert data["evaluated_count"] == 2
        assert data["pending_count"] == 0

    def test_evaluation_summary_goal_not_found(self, client):
        """Test 404 when goal doesn't exist."""
        mock_work_map_service = MagicMock()
        mock_work_map_service.get_goal = AsyncMock(return_value=None)

        mock_comment_service = MagicMock()

        with patch("api.work_map.get_work_map_service", return_value=mock_work_map_service), \
             patch("api.work_map.get_goal_comment_service", return_value=mock_comment_service):
            response = client.get("/api/v1/goals/nonexistent/evaluation-summary")

        assert response.status_code == 404

    def test_evaluation_summary_unevaluated_goal(self, client):
        """Test summary for a goal that hasn't been evaluated."""
        mock_goal = Goal(
            goal_id="goal_uneval",
            title="Unevaluated Goal",
            description="Not yet decomposed",
            priority=IssuePriority.P2,
            goal_text_evaluated=False,
        )

        mock_work_map_service = MagicMock()
        mock_work_map_service.get_goal = AsyncMock(return_value=mock_goal)

        mock_comment_service = MagicMock()
        mock_comment_service.list_comments = AsyncMock(return_value=MagicMock(
            items=[],
            total=0,
        ))

        with patch("api.work_map.get_work_map_service", return_value=mock_work_map_service), \
             patch("api.work_map.get_goal_comment_service", return_value=mock_comment_service):
            response = client.get("/api/v1/goals/goal_uneval/evaluation-summary")

        assert response.status_code == 200
        data = response.json()
        assert data["all_evaluated"] is False
        assert data["goal_text_evaluated"] is False
        assert data["has_decomposition"] is False
        assert data["total_items"] == 1  # just goal_text
        assert data["evaluated_count"] == 0
        assert data["pending_count"] == 1
