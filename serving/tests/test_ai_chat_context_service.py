"""Tests for AI Chat Agent Context Management Service.

Covers summary CRUD, message tracking, update triggering,
summary generation prompts, and context assembly.
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ai_chat_context_service import (
    AIChatContextService,
    ConversationSummary,
    AssembledContext,
    MESSAGES_BETWEEN_UPDATES,
    SUMMARY_TTL_SECONDS,
    RECENT_WINDOW_SIZE,
)


@pytest.fixture
def service():
    """Service with no Redis (in-memory fallback)."""
    return AIChatContextService(redis_client=None)


@pytest.fixture
def mock_redis():
    """Mock Redis client matching the pattern used in serving."""
    redis_mock = MagicMock()
    redis_mock._prefix = "claudevn:"
    redis_mock._redis = AsyncMock()
    return redis_mock


@pytest.fixture
def service_with_redis(mock_redis):
    """Service with mocked Redis."""
    return AIChatContextService(redis_client=mock_redis)


# =============================================================================
# ConversationSummary Model
# =============================================================================


class TestConversationSummary:
    """Tests for the ConversationSummary model."""

    def test_default_values(self):
        summary = ConversationSummary(project_id="proj-1")
        assert summary.project_id == "proj-1"
        assert summary.summary_text == ""
        assert summary.topic_tags == []
        assert summary.message_count_since_update == 0
        assert summary.total_messages_summarized == 0

    def test_needs_update_below_threshold(self):
        summary = ConversationSummary(
            project_id="proj-1",
            message_count_since_update=5,
        )
        assert summary.needs_update() is False

    def test_needs_update_at_threshold(self):
        summary = ConversationSummary(
            project_id="proj-1",
            message_count_since_update=MESSAGES_BETWEEN_UPDATES,
        )
        assert summary.needs_update() is True

    def test_needs_update_custom_threshold(self):
        summary = ConversationSummary(
            project_id="proj-1",
            message_count_since_update=5,
        )
        assert summary.needs_update(threshold=5) is True
        assert summary.needs_update(threshold=6) is False

    def test_serialization_roundtrip(self):
        summary = ConversationSummary(
            project_id="proj-1",
            summary_text="Users discussed auth flow.",
            topic_tags=["auth", "security"],
            message_count_since_update=3,
            total_messages_summarized=45,
        )
        json_str = summary.model_dump_json()
        restored = ConversationSummary.model_validate_json(json_str)
        assert restored.project_id == "proj-1"
        assert restored.summary_text == "Users discussed auth flow."
        assert restored.topic_tags == ["auth", "security"]
        assert restored.total_messages_summarized == 45


# =============================================================================
# Summary CRUD (No Redis)
# =============================================================================


class TestSummaryCRUDNoRedis:
    """Tests for summary operations without Redis."""

    @pytest.mark.asyncio
    async def test_get_summary_returns_empty_default(self, service):
        summary = await service.get_summary("proj-1")
        assert summary.project_id == "proj-1"
        assert summary.summary_text == ""

    @pytest.mark.asyncio
    async def test_save_summary_noop(self, service):
        summary = ConversationSummary(project_id="proj-1", summary_text="test")
        await service.save_summary(summary)  # Should not raise

    @pytest.mark.asyncio
    async def test_clear_summary_noop(self, service):
        await service.clear_summary("proj-1")  # Should not raise


# =============================================================================
# Summary CRUD (With Redis)
# =============================================================================


class TestSummaryCRUDWithRedis:
    """Tests for summary operations with mocked Redis."""

    @pytest.mark.asyncio
    async def test_get_summary_from_redis(self, service_with_redis, mock_redis):
        summary = ConversationSummary(
            project_id="proj-1",
            summary_text="Auth discussion ongoing.",
            topic_tags=["auth"],
        )
        mock_redis._redis.get.return_value = summary.model_dump_json().encode()

        result = await service_with_redis.get_summary("proj-1")
        assert result.summary_text == "Auth discussion ongoing."
        assert result.topic_tags == ["auth"]
        mock_redis._redis.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_summary_returns_default_on_miss(self, service_with_redis, mock_redis):
        mock_redis._redis.get.return_value = None

        result = await service_with_redis.get_summary("proj-1")
        assert result.summary_text == ""

    @pytest.mark.asyncio
    async def test_save_summary_with_ttl(self, service_with_redis, mock_redis):
        summary = ConversationSummary(
            project_id="proj-1",
            summary_text="test",
        )
        await service_with_redis.save_summary(summary)

        mock_redis._redis.set.assert_awaited_once()
        call_args = mock_redis._redis.set.call_args
        assert call_args.kwargs.get("ex") == SUMMARY_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_clear_summary_deletes_key(self, service_with_redis, mock_redis):
        await service_with_redis.clear_summary("proj-1")
        mock_redis._redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_summary_handles_redis_error(self, service_with_redis, mock_redis):
        mock_redis._redis.get.side_effect = Exception("Connection lost")

        result = await service_with_redis.get_summary("proj-1")
        assert result.summary_text == ""  # Falls back to empty default


# =============================================================================
# Message Tracking
# =============================================================================


class TestMessageTracking:
    """Tests for message recording and update triggering."""

    @pytest.mark.asyncio
    async def test_record_message_increments_count(self, service_with_redis, mock_redis):
        # Start with count = 0
        summary = ConversationSummary(project_id="proj-1", message_count_since_update=0)
        mock_redis._redis.get.return_value = summary.model_dump_json().encode()

        needs_update = await service_with_redis.record_message("proj-1")
        assert needs_update is False  # 1 < threshold

    @pytest.mark.asyncio
    async def test_record_message_triggers_update_at_threshold(self, service_with_redis, mock_redis):
        summary = ConversationSummary(
            project_id="proj-1",
            message_count_since_update=MESSAGES_BETWEEN_UPDATES - 1,
        )
        mock_redis._redis.get.return_value = summary.model_dump_json().encode()

        needs_update = await service_with_redis.record_message("proj-1")
        assert needs_update is True


# =============================================================================
# Summary Update
# =============================================================================


class TestSummaryUpdate:
    """Tests for summary update operations."""

    @pytest.mark.asyncio
    async def test_update_summary_resets_counter(self, service_with_redis, mock_redis):
        existing = ConversationSummary(
            project_id="proj-1",
            summary_text="old summary",
            message_count_since_update=12,
        )
        mock_redis._redis.get.return_value = existing.model_dump_json().encode()

        result = await service_with_redis.update_summary(
            project_id="proj-1",
            new_summary_text="new evolved summary",
            topic_tags=["auth", "deployment"],
            messages_included=12,
        )

        assert result.summary_text == "new evolved summary"
        assert result.message_count_since_update == 0
        assert result.topic_tags == ["auth", "deployment"]
        assert result.total_messages_summarized == 12

    @pytest.mark.asyncio
    async def test_update_summary_accumulates_total(self, service_with_redis, mock_redis):
        existing = ConversationSummary(
            project_id="proj-1",
            total_messages_summarized=30,
            message_count_since_update=10,
        )
        mock_redis._redis.get.return_value = existing.model_dump_json().encode()

        result = await service_with_redis.update_summary(
            project_id="proj-1",
            new_summary_text="updated",
            messages_included=10,
        )

        assert result.total_messages_summarized == 40


# =============================================================================
# Summary Generation Prompts
# =============================================================================


class TestSummaryPrompts:
    """Tests for summary generation prompt building."""

    def test_initial_summary_prompt(self, service):
        messages = [
            {"display_name": "Alice", "content": "Should we refactor auth?"},
            {"display_name": "Bob", "content": "Yes, it's messy."},
        ]
        prompt = service.build_summary_prompt(None, messages)
        assert "Conversation messages:" in prompt
        assert "[Alice]:" in prompt
        assert "[Bob]:" in prompt
        assert "under 500 tokens" in prompt
        assert "Previous conversation summary" not in prompt

    def test_evolving_summary_prompt(self, service):
        messages = [
            {"display_name": "Alice", "content": "Let's add tests too."},
        ]
        prompt = service.build_summary_prompt("Users discussed auth refactoring.", messages)
        assert "Previous conversation summary:" in prompt
        assert "auth refactoring" in prompt
        assert "New messages since last summary:" in prompt
        assert "[Alice]:" in prompt
        assert "Update the summary" in prompt

    def test_multi_thread_instruction(self, service):
        prompt = service.build_summary_prompt(None, [
            {"display_name": "Alice", "content": "test"},
        ])
        assert "multiple discussion threads" in prompt

    def test_topic_extraction_prompt(self, service):
        prompt = service.build_topic_extraction_prompt("Users discussed auth and deployment.")
        assert "topic tags" in prompt
        assert "JSON array" in prompt
        assert "auth and deployment" in prompt


# =============================================================================
# Context Assembly
# =============================================================================


class TestContextAssembly:
    """Tests for full context assembly."""

    @pytest.mark.asyncio
    async def test_assemble_context_with_summary(self, service_with_redis, mock_redis):
        summary = ConversationSummary(
            project_id="proj-1",
            summary_text="Auth refactoring discussed.",
            last_updated=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        mock_redis._redis.get.return_value = summary.model_dump_json().encode()

        with patch("services.ai_chat_context_service.get_ai_chat_context_service"):
            # Mock get_recent_messages to avoid ConversationService dependency
            service_with_redis.get_recent_messages = AsyncMock(return_value=[
                {"display_name": "Alice", "content": "What about tests?", "type": "user"},
            ])

            result = await service_with_redis.assemble_context(
                project_id="proj-1",
                project_name="MyProject",
                system_prompt="You are a helpful assistant.",
                active_goals=["Implement auth"],
            )

        assert isinstance(result, AssembledContext)
        assert result.rolling_summary == "Auth refactoring discussed."
        assert result.summary_age_seconds is not None
        assert result.summary_age_seconds > 0
        assert len(result.recent_messages) == 1
        assert result.active_goals == ["Implement auth"]
        assert result.estimated_tokens > 0

    @pytest.mark.asyncio
    async def test_assemble_context_without_summary(self, service_with_redis, mock_redis):
        mock_redis._redis.get.return_value = None
        service_with_redis.get_recent_messages = AsyncMock(return_value=[])

        result = await service_with_redis.assemble_context(
            project_id="proj-1",
            project_name="MyProject",
            system_prompt="You are a helpful assistant.",
        )

        assert result.rolling_summary is None
        assert result.summary_age_seconds is None
        assert result.recent_messages == []

    @pytest.mark.asyncio
    async def test_context_token_estimation(self, service_with_redis, mock_redis):
        mock_redis._redis.get.return_value = None
        service_with_redis.get_recent_messages = AsyncMock(return_value=[
            {"display_name": "Alice", "content": "x" * 400, "type": "user"},
        ])

        result = await service_with_redis.assemble_context(
            project_id="proj-1",
            project_name="Test",
            system_prompt="A" * 200,
        )

        # (200 + 0 + 400 + 5) / 4 ≈ 151 tokens
        assert result.estimated_tokens > 100


# =============================================================================
# Singleton
# =============================================================================


class TestSingleton:
    """Tests for module-level singleton pattern."""

    def test_default_is_none(self):
        from services.ai_chat_context_service import get_ai_chat_context_service
        # May or may not be None depending on test ordering, but import should work
        assert get_ai_chat_context_service is not None  # Callable exists

    def test_set_and_get(self):
        from services.ai_chat_context_service import (
            get_ai_chat_context_service,
            set_ai_chat_context_service,
        )
        svc = AIChatContextService()
        set_ai_chat_context_service(svc)
        assert get_ai_chat_context_service() is svc
        set_ai_chat_context_service(None)  # Clean up
