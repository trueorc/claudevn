"""Tests for decomposition submission idempotency.

Regression: decomposition results were submitted twice — once via MCP tool
during Claude Code execution and again via REST POST after exit.

See: https://github.com/Guarrdon/claudevn/issues/664
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.tools.decomposition import (
    SubmitDecompositionInput,
    SubmitDecompositionResponse,
    DecomposedIssueInput,
    submit_decomposition,
)


def make_issue_input(**overrides):
    defaults = dict(
        temp_id="issue-1",
        title="Test Issue",
        description="A test issue",
        issue_type="feature",
        priority="P2",
        area="api",
        required_skills=["code-writer"],
        estimated_complexity="m",
        blocked_by=[],
        acceptance_criteria=["Works correctly"],
    )
    defaults.update(overrides)
    return DecomposedIssueInput(**defaults)


def make_submit_input(**overrides):
    defaults = dict(
        decomposition_id="decomp-test123",
        goal_id="goal-abc",
        issues=[make_issue_input()],
        confidence=0.85,
        reasoning="Test reasoning",
    )
    defaults.update(overrides)
    return SubmitDecompositionInput(**defaults)


class TestDecompositionIdempotency:
    """Test that duplicate decomposition submissions are handled correctly."""

    @patch("git.redis_client.get_redis")
    async def test_first_submission_stores_normally(self, mock_get_redis):
        """First submission should store in Redis normally."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=False)
        mock_get_redis.return_value = mock_redis

        with patch("services.goal_service.get_goal_service") as mock_goal:
            mock_goal.return_value.update_goal_decomposition_id = AsyncMock()

            response, error = await submit_decomposition(make_submit_input())

        assert error is None
        assert response is not None
        assert response.status == "stored"
        assert response.issues_count == 1
        mock_redis.setex.assert_awaited()

    @patch("git.redis_client.get_redis")
    async def test_duplicate_submission_returns_already_stored(self, mock_get_redis):
        """Second submission should return 'already_stored' without writing."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=True)  # Already exists
        mock_get_redis.return_value = mock_redis

        response, error = await submit_decomposition(make_submit_input())

        assert error is None
        assert response is not None
        assert response.status == "already_stored"
        assert response.acknowledged is True
        # Should NOT call setex (no re-write)
        mock_redis.setex.assert_not_awaited()

    @patch("git.redis_client.get_redis")
    async def test_duplicate_does_not_update_goal(self, mock_get_redis):
        """Duplicate submission should not call update_goal_decomposition_id."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=True)
        mock_get_redis.return_value = mock_redis

        with patch("services.goal_service.get_goal_service") as mock_goal:
            mock_goal_service = MagicMock()
            mock_goal_service.update_goal_decomposition_id = AsyncMock()
            mock_goal.return_value = mock_goal_service

            await submit_decomposition(make_submit_input())

            mock_goal_service.update_goal_decomposition_id.assert_not_awaited()

    @patch("git.redis_client.get_redis")
    async def test_duplicate_preserves_issue_count(self, mock_get_redis):
        """Duplicate response should reflect correct issue count from input."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=True)
        mock_get_redis.return_value = mock_redis

        input_data = make_submit_input(issues=[
            make_issue_input(temp_id="i1"),
            make_issue_input(temp_id="i2"),
            make_issue_input(temp_id="i3"),
        ])

        response, error = await submit_decomposition(input_data)

        assert response.issues_count == 3
        assert response.decomposition_id == "decomp-test123"
