"""Tests for comment evaluation API endpoints.

Tests the endpoints:
- POST /{goal_id}/comments/{comment_id}/evaluate
- POST /{goal_id}/evaluate-all

These endpoints were affected by issue #711 where get_goal_evaluation_service
was used but not imported, causing a NameError (500 error).
"""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from models.work_map import (
    Goal,
    GoalStatus,
    GoalComment,
    CommentType,
    EvaluationStatus,
    EvaluationResult,
)
from api.work_map import goals_router


def _make_goal(
    goal_id="goal-001",
    title="Test Goal",
    status=GoalStatus.IN_PROGRESS,
):
    """Create a test Goal instance."""
    return Goal(
        goal_id=goal_id,
        title=title,
        description="Test goal description",
        status=status,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _make_comment(
    comment_id="comment-001",
    goal_id="goal-001",
    content="Test comment",
    evaluation_status=EvaluationStatus.NOT_EVALUATED,
    evaluation_result=None,
):
    """Create a test GoalComment instance."""
    return GoalComment(
        comment_id=comment_id,
        goal_id=goal_id,
        content=content,
        evaluation_status=evaluation_status,
        evaluation_result=evaluation_result,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        created_by="user",
    )


def _make_evaluation_result(
    comment_type=CommentType.SUGGESTION,
    confidence=0.85,
    summary="Test evaluation summary",
):
    """Create a test EvaluationResult instance."""
    return EvaluationResult(
        comment_type=comment_type,
        confidence=confidence,
        summary=summary,
        entities=["feature-1", "component-2"],
        suggested_actions=[],
        evaluated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        evaluator_version="1.0",
    )


@pytest.fixture
def mock_work_map_service():
    """Mock WorkMapService."""
    service = AsyncMock()
    service.get_goal = AsyncMock(return_value=_make_goal())
    return service


@pytest.fixture
def mock_comment_service():
    """Mock GoalCommentService."""
    service = AsyncMock()
    service.get_comment = AsyncMock(return_value=_make_comment())
    return service


@pytest.fixture
def mock_evaluation_service():
    """Mock GoalEvaluationService."""
    service = AsyncMock()
    service.evaluate_comment = AsyncMock()
    service.evaluate_batch = AsyncMock(return_value=[])
    return service


@pytest.fixture
def client(mock_work_map_service, mock_comment_service, mock_evaluation_service):
    """Create test client with mocked services."""
    app = FastAPI()
    app.include_router(goals_router)

    with patch("api.work_map.get_work_map_service", return_value=mock_work_map_service), \
         patch("api.work_map.get_goal_comment_service", return_value=mock_comment_service), \
         patch("api.work_map.get_goal_evaluation_service", return_value=mock_evaluation_service):
        yield TestClient(app)


class TestEvaluateGoalComment:
    """Tests for POST /{goal_id}/comments/{comment_id}/evaluate."""

    @pytest.mark.asyncio
    async def test_successful_evaluation(
        self, client, mock_comment_service, mock_evaluation_service
    ):
        """Test successful evaluation of a single comment."""
        # Setup: Return evaluated comment after evaluation
        evaluated_comment = _make_comment(
            comment_id="comment-001",
            evaluation_status=EvaluationStatus.EVALUATED,
            evaluation_result=_make_evaluation_result(),
        )
        mock_comment_service.get_comment.side_effect = [
            _make_comment(),  # First call: verify comment exists
            evaluated_comment,  # Second call: return updated comment
        ]

        resp = client.post("/goals/goal-001/comments/comment-001/evaluate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["comment_id"] == "comment-001"
        assert data["evaluation_status"] == "evaluated"
        assert data["evaluation_result"] is not None

        # Verify service was called
        mock_evaluation_service.evaluate_comment.assert_awaited_once_with("comment-001")

    @pytest.mark.asyncio
    async def test_import_no_error(self, client):
        """Test that get_goal_evaluation_service import works (issue #711 fix)."""
        # This test verifies the NameError from issue #711 is fixed
        resp = client.post("/goals/goal-001/comments/comment-001/evaluate")

        # Should not get 500 NameError, should get 200 or other expected status
        assert resp.status_code != 500

    @pytest.mark.asyncio
    async def test_goal_not_found(self, client, mock_work_map_service):
        """Test 404 when goal doesn't exist."""
        mock_work_map_service.get_goal.return_value = None

        resp = client.post("/goals/goal-999/comments/comment-001/evaluate")

        assert resp.status_code == 404
        assert "Goal 'goal-999' not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_comment_not_found(self, client, mock_comment_service):
        """Test 404 when comment doesn't exist."""
        mock_comment_service.get_comment.return_value = None

        resp = client.post("/goals/goal-001/comments/comment-999/evaluate")

        assert resp.status_code == 404
        assert "Comment 'comment-999' not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_comment_does_not_belong_to_goal(self, client, mock_comment_service):
        """Test 400 when comment doesn't belong to the specified goal."""
        # Comment belongs to different goal
        mock_comment_service.get_comment.return_value = _make_comment(
            comment_id="comment-001",
            goal_id="different-goal",
        )

        resp = client.post("/goals/goal-001/comments/comment-001/evaluate")

        assert resp.status_code == 400
        assert "does not belong to goal" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_evaluation_service_unavailable(self, client):
        """Test 503 when evaluation service is not available."""
        app = FastAPI()
        app.include_router(goals_router)

        with patch("api.work_map.get_work_map_service", return_value=AsyncMock(get_goal=AsyncMock(return_value=_make_goal()))), \
             patch("api.work_map.get_goal_comment_service", return_value=AsyncMock(get_comment=AsyncMock(return_value=_make_comment()))), \
             patch("api.work_map.get_goal_evaluation_service", side_effect=RuntimeError("not initialized")):
            test_client = TestClient(app)
            resp = test_client.post("/goals/goal-001/comments/comment-001/evaluate")

            assert resp.status_code == 503
            assert "Evaluation service not available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_evaluation_fails(self, client, mock_evaluation_service):
        """Test 500 when evaluation fails with unexpected error."""
        mock_evaluation_service.evaluate_comment.side_effect = Exception("Evaluation error")

        resp = client.post("/goals/goal-001/comments/comment-001/evaluate")

        assert resp.status_code == 500
        assert "Failed to evaluate comment" in resp.json()["detail"]


class TestEvaluateAllGoalComments:
    """Tests for POST /{goal_id}/evaluate-all."""

    @pytest.mark.asyncio
    async def test_successful_batch_evaluation(
        self, client, mock_evaluation_service
    ):
        """Test successful batch evaluation of all comments."""
        # Setup: Return multiple evaluation results
        results = [
            _make_evaluation_result(comment_type=CommentType.SUGGESTION, confidence=0.85),
            _make_evaluation_result(comment_type=CommentType.BUG, confidence=0.92),
            _make_evaluation_result(comment_type=CommentType.ENHANCEMENT, confidence=0.78),
        ]
        mock_evaluation_service.evaluate_batch.return_value = results

        resp = client.post("/goals/goal-001/evaluate-all")

        assert resp.status_code == 200
        data = resp.json()
        assert data["goal_id"] == "goal-001"
        assert data["evaluated_count"] == 3
        assert len(data["results"]) == 3

        # Verify result structure
        assert data["results"][0]["comment_type"] == "suggestion"
        assert data["results"][0]["confidence"] == 0.85
        assert "summary" in data["results"][0]

        # Verify service was called
        mock_evaluation_service.evaluate_batch.assert_awaited_once_with("goal-001")

    @pytest.mark.asyncio
    async def test_batch_evaluation_empty_results(
        self, client, mock_evaluation_service
    ):
        """Test batch evaluation with no comments to evaluate."""
        mock_evaluation_service.evaluate_batch.return_value = []

        resp = client.post("/goals/goal-001/evaluate-all")

        assert resp.status_code == 200
        data = resp.json()
        assert data["goal_id"] == "goal-001"
        assert data["evaluated_count"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_import_no_error(self, client):
        """Test that get_goal_evaluation_service import works (issue #711 fix)."""
        # This test verifies the NameError from issue #711 is fixed
        resp = client.post("/goals/goal-001/evaluate-all")

        # Should not get 500 NameError, should get 200 or other expected status
        assert resp.status_code != 500

    @pytest.mark.asyncio
    async def test_goal_not_found(self, client, mock_work_map_service):
        """Test 404 when goal doesn't exist."""
        mock_work_map_service.get_goal.return_value = None

        resp = client.post("/goals/goal-999/evaluate-all")

        assert resp.status_code == 404
        assert "Goal 'goal-999' not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_evaluation_service_unavailable(self, client):
        """Test 503 when evaluation service is not available."""
        app = FastAPI()
        app.include_router(goals_router)

        with patch("api.work_map.get_work_map_service", return_value=AsyncMock(get_goal=AsyncMock(return_value=_make_goal()))), \
             patch("api.work_map.get_goal_evaluation_service", side_effect=RuntimeError("not initialized")):
            test_client = TestClient(app)
            resp = test_client.post("/goals/goal-001/evaluate-all")

            assert resp.status_code == 503
            assert "Evaluation service not available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_batch_evaluation_fails(self, client, mock_evaluation_service):
        """Test 500 when batch evaluation fails with unexpected error."""
        mock_evaluation_service.evaluate_batch.side_effect = Exception("Batch evaluation error")

        resp = client.post("/goals/goal-001/evaluate-all")

        assert resp.status_code == 500
        assert "Failed to evaluate comments" in resp.json()["detail"]
