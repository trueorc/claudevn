"""Unit tests for AI-generated goal summaries (#70).

Tests the summary field on Goal model, summary generation via ClaudeClient,
and the fire-and-forget scheduling in UnifiedDirectiveService.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.work_map import Goal, GoalStatus, IssuePriority


class TestGoalSummaryField:
    """Tests for the summary field on the Goal model."""

    def test_summary_defaults_to_none(self):
        """Summary field defaults to None when not provided."""
        goal = Goal(
            goal_id="goal_abc123",
            title="Test goal",
            description="A detailed description",
        )
        assert goal.summary is None

    def test_summary_can_be_set(self):
        """Summary field accepts a string value."""
        goal = Goal(
            goal_id="goal_abc123",
            title="Test goal",
            description="A detailed description",
            summary="Set up user auth system",
        )
        assert goal.summary == "Set up user auth system"

    def test_summary_serializes_in_json(self):
        """Summary field appears in model JSON serialization."""
        goal = Goal(
            goal_id="goal_abc123",
            title="Test goal",
            description="A detailed description",
            summary="Quick summary",
        )
        data = goal.model_dump()
        assert data["summary"] == "Quick summary"

    def test_summary_none_serializes_in_json(self):
        """Summary field appears as None in model JSON when not set."""
        goal = Goal(
            goal_id="goal_abc123",
            title="Test goal",
            description="A detailed description",
        )
        data = goal.model_dump()
        assert data["summary"] is None


class TestGoalSummaryRedis:
    """Tests for summary persistence in Redis via GoalService."""

    @pytest.mark.asyncio
    async def test_save_goal_includes_summary(self):
        """_save_goal_to_redis includes summary in the Redis hash mapping."""
        from services.goal_service import GoalService

        mock_redis = MagicMock()
        mock_redis._redis = AsyncMock()
        mock_redis._redis.hset = AsyncMock()
        mock_redis._redis.sadd = AsyncMock()
        mock_redis._prefix = "claudevn:"

        service = GoalService(redis_client=mock_redis)
        goal = Goal(
            goal_id="goal_test1",
            title="Test goal",
            description="Long description here",
            summary="Short summary",
        )
        service._goals[goal.goal_id] = goal

        await service._save_goal_to_redis(goal)

        call_args = mock_redis._redis.hset.call_args
        mapping = call_args.kwargs.get("mapping") or call_args[1].get("mapping")
        assert mapping["summary"] == "Short summary"

    @pytest.mark.asyncio
    async def test_save_goal_empty_summary(self):
        """_save_goal_to_redis stores empty string for None summary."""
        from services.goal_service import GoalService

        mock_redis = MagicMock()
        mock_redis._redis = AsyncMock()
        mock_redis._redis.hset = AsyncMock()
        mock_redis._redis.sadd = AsyncMock()
        mock_redis._prefix = "claudevn:"

        service = GoalService(redis_client=mock_redis)
        goal = Goal(
            goal_id="goal_test2",
            title="Test goal",
            description="Description",
        )
        service._goals[goal.goal_id] = goal

        await service._save_goal_to_redis(goal)

        call_args = mock_redis._redis.hset.call_args
        mapping = call_args.kwargs.get("mapping") or call_args[1].get("mapping")
        assert mapping["summary"] == ""


class TestSummaryGeneration:
    """Tests for _generate_summary in UnifiedDirectiveService."""

    @pytest.mark.asyncio
    async def test_generate_summary_calls_haiku(self):
        """_generate_summary uses Haiku model for cost efficiency."""
        from services.unified_directive_service import UnifiedDirectiveService

        service = UnifiedDirectiveService()

        mock_response = MagicMock()
        mock_response.content = "Add user authentication"

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value=mock_response)

        mock_goal = MagicMock()
        mock_goal.summary = None

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)
        mock_goal_service._save_goal_to_redis = AsyncMock()

        with patch(
            "services.claude_client.get_claude_client",
            return_value=mock_client,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service._generate_summary("goal_123", "Build a user authentication system with OAuth2")

        # Verify Haiku model was used
        call_kwargs = mock_client.complete.call_args.kwargs
        assert "haiku" in call_kwargs["model"]
        assert call_kwargs["max_tokens"] == 80
        assert call_kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_generate_summary_saves_to_goal(self):
        """_generate_summary persists the summary on the Goal."""
        from services.unified_directive_service import UnifiedDirectiveService

        service = UnifiedDirectiveService()

        mock_response = MagicMock()
        mock_response.content = "Implement OAuth2 authentication"

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value=mock_response)

        mock_goal = MagicMock()
        mock_goal.summary = None

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)
        mock_goal_service._save_goal_to_redis = AsyncMock()

        with patch(
            "services.claude_client.get_claude_client",
            return_value=mock_client,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service._generate_summary("goal_123", "Some directive text")

        assert mock_goal.summary == "Implement OAuth2 authentication"
        mock_goal_service._save_goal_to_redis.assert_called_once_with(mock_goal)

    @pytest.mark.asyncio
    async def test_generate_summary_truncates_long_output(self):
        """_generate_summary enforces 80-char limit on AI output."""
        from services.unified_directive_service import UnifiedDirectiveService

        service = UnifiedDirectiveService()

        long_summary = "A" * 100
        mock_response = MagicMock()
        mock_response.content = long_summary

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value=mock_response)

        mock_goal = MagicMock()
        mock_goal.summary = None

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)
        mock_goal_service._save_goal_to_redis = AsyncMock()

        with patch(
            "services.claude_client.get_claude_client",
            return_value=mock_client,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service._generate_summary("goal_123", "Some text")

        assert len(mock_goal.summary) <= 80
        assert mock_goal.summary.endswith("...")

    @pytest.mark.asyncio
    async def test_generate_summary_strips_quotes(self):
        """_generate_summary strips wrapping quotes from AI output."""
        from services.unified_directive_service import UnifiedDirectiveService

        service = UnifiedDirectiveService()

        mock_response = MagicMock()
        mock_response.content = '"Set up user auth"'

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value=mock_response)

        mock_goal = MagicMock()
        mock_goal.summary = None

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=mock_goal)
        mock_goal_service._save_goal_to_redis = AsyncMock()

        with patch(
            "services.claude_client.get_claude_client",
            return_value=mock_client,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            await service._generate_summary("goal_123", "text")

        assert mock_goal.summary == "Set up user auth"

    @pytest.mark.asyncio
    async def test_generate_summary_handles_api_failure_gracefully(self):
        """_generate_summary logs warning but doesn't raise on API failure."""
        from services.unified_directive_service import UnifiedDirectiveService

        service = UnifiedDirectiveService()

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(side_effect=RuntimeError("API down"))

        with patch(
            "services.claude_client.get_claude_client",
            return_value=mock_client,
        ):
            # Should not raise
            await service._generate_summary("goal_123", "Some text")

    @pytest.mark.asyncio
    async def test_generate_summary_handles_missing_goal(self):
        """_generate_summary handles goal not found after API call."""
        from services.unified_directive_service import UnifiedDirectiveService

        service = UnifiedDirectiveService()

        mock_response = MagicMock()
        mock_response.content = "A summary"

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value=mock_response)

        mock_goal_service = AsyncMock()
        mock_goal_service.get_goal = AsyncMock(return_value=None)

        with patch(
            "services.claude_client.get_claude_client",
            return_value=mock_client,
        ), patch(
            "services.goal_service.get_goal_service",
            return_value=mock_goal_service,
        ):
            # Should not raise
            await service._generate_summary("goal_nonexistent", "Some text")

        mock_goal_service._save_goal_to_redis.assert_not_called()
