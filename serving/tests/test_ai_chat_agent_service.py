"""Tests for AI Chat Agent Service.

Covers message handling, debounce mechanism, evaluation flow,
response posting, and edge cases.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.ai_chat_agent import AgentEvaluation, AIChatAgentConfig, AssertivenesLevel
from services.ai_chat_agent_service import (
    AIChatAgentService,
    AI_AGENT_USER_ID,
    AI_AGENT_DISPLAY_NAME,
)


@pytest.fixture
def service():
    svc = AIChatAgentService()
    svc.start()
    yield svc
    svc.stop()


# =============================================================================
# Lifecycle
# =============================================================================


class TestLifecycle:
    """Tests for service start/stop."""

    def test_start(self):
        svc = AIChatAgentService()
        assert svc._started is False
        svc.start()
        assert svc._started is True
        svc.stop()

    def test_stop_clears_state(self):
        svc = AIChatAgentService()
        svc.start()
        svc._evaluating.add("proj-1")
        svc.stop()
        assert svc._started is False
        assert len(svc._evaluating) == 0
        assert len(svc._debounce_tasks) == 0

    def test_double_start_is_noop(self):
        svc = AIChatAgentService()
        svc.start()
        svc.start()  # Should not raise
        assert svc._started is True
        svc.stop()


# =============================================================================
# Config
# =============================================================================


class TestConfig:
    """Tests for per-project configuration."""

    def test_default_config(self, service):
        config = service.get_config("proj-1")
        assert config.enabled is True
        assert config.assertiveness == AssertivenesLevel.BALANCED
        assert config.debounce_seconds == 4.0

    def test_set_config(self, service):
        config = AIChatAgentConfig(
            assertiveness=AssertivenesLevel.CONSERVATIVE,
            debounce_seconds=8.0,
        )
        service.set_config("proj-1", config)
        result = service.get_config("proj-1")
        assert result.assertiveness == AssertivenesLevel.CONSERVATIVE
        assert result.debounce_seconds == 8.0


# =============================================================================
# Message Callback
# =============================================================================


class TestOnMessage:
    """Tests for the message callback."""

    @pytest.mark.asyncio
    async def test_ignores_own_messages(self, service):
        """AI agent should ignore its own messages to prevent loops."""
        with patch.object(service, '_reset_debounce') as mock_reset:
            await service.on_message("proj-1", AI_AGENT_USER_ID, "assistant", "hello")
            mock_reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_system_messages(self, service):
        """Should only react to user/assistant messages."""
        with patch.object(service, '_reset_debounce') as mock_reset:
            await service.on_message("proj-1", "user-1", "system", "joined")
            mock_reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_when_disabled(self, service):
        """Should not trigger when agent is disabled for the project."""
        service.set_config("proj-1", AIChatAgentConfig(enabled=False))
        with patch.object(service, '_reset_debounce') as mock_reset:
            await service.on_message("proj-1", "user-1", "user", "hello")
            mock_reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_when_not_started(self):
        """Should not trigger if service hasn't been started."""
        svc = AIChatAgentService()  # Not started
        with patch.object(svc, '_reset_debounce') as mock_reset:
            await svc.on_message("proj-1", "user-1", "user", "hello")
            mock_reset.assert_not_called()

    @pytest.mark.asyncio
    async def test_triggers_debounce_for_user_message(self, service):
        """User messages should trigger the debounce timer."""
        mock_ctx = MagicMock()
        mock_ctx.record_message = AsyncMock(return_value=False)

        with patch.object(service, '_reset_debounce') as mock_reset:
            with patch(
                "services.ai_chat_context_service.get_ai_chat_context_service",
                return_value=mock_ctx,
            ):
                await service.on_message("proj-1", "user-1", "user", "hello")
                mock_reset.assert_called_once_with("proj-1", 4.0)

    @pytest.mark.asyncio
    async def test_records_message_for_context_tracking(self, service):
        """Should record the message for context tracking."""
        mock_ctx = MagicMock()
        mock_ctx.record_message = AsyncMock(return_value=False)

        with patch(
            "services.ai_chat_context_service.get_ai_chat_context_service",
            return_value=mock_ctx,
        ):
            with patch.object(service, '_reset_debounce'):
                await service.on_message("proj-1", "user-1", "user", "hello")
                mock_ctx.record_message.assert_awaited_once_with("proj-1")


# =============================================================================
# Debounce
# =============================================================================


class TestDebounce:
    """Tests for the debounce mechanism."""

    @pytest.mark.asyncio
    async def test_debounce_fires_evaluation(self, service):
        """After the debounce delay, evaluation should fire."""
        with patch.object(service, '_evaluate', new_callable=AsyncMock) as mock_eval:
            service._reset_debounce("proj-1", 0.05)
            await asyncio.sleep(0.1)
            mock_eval.assert_awaited_once_with("proj-1")

    @pytest.mark.asyncio
    async def test_debounce_resets_on_new_message(self, service):
        """A new message should cancel and restart the timer."""
        call_count = 0

        async def counting_evaluate(project_id):
            nonlocal call_count
            call_count += 1

        with patch.object(service, '_evaluate', side_effect=counting_evaluate):
            service._reset_debounce("proj-1", 0.15)
            await asyncio.sleep(0.05)
            service._reset_debounce("proj-1", 0.15)
            await asyncio.sleep(0.05)
            service._reset_debounce("proj-1", 0.15)
            await asyncio.sleep(0.25)

            assert call_count == 1

    @pytest.mark.asyncio
    async def test_debounce_cleanup(self, service):
        """Debounce task should be cleaned up after firing."""
        with patch.object(service, '_evaluate', new_callable=AsyncMock):
            service._reset_debounce("proj-1", 0.05)
            await asyncio.sleep(0.1)
            assert "proj-1" not in service._debounce_tasks


# =============================================================================
# Evaluation
# =============================================================================


class TestEvaluation:
    """Tests for the evaluation flow."""

    @pytest.mark.asyncio
    async def test_skips_if_already_evaluating(self, service):
        """Only one evaluation per project at a time."""
        service._evaluating.add("proj-1")
        with patch.object(service, '_run_evaluation', new_callable=AsyncMock) as mock_run:
            await service._evaluate("proj-1")
            mock_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clears_evaluating_flag_after_error(self, service):
        """Evaluating flag should be cleared even on error."""
        async def failing_eval(project_id):
            raise Exception("test error")

        with patch.object(service, '_run_evaluation', side_effect=failing_eval):
            await service._evaluate("proj-1")
            assert "proj-1" not in service._evaluating

    @pytest.mark.asyncio
    async def test_clears_evaluating_flag_on_success(self, service):
        """Evaluating flag should be cleared on success."""
        with patch.object(service, '_run_evaluation', new_callable=AsyncMock):
            await service._evaluate("proj-1")
            assert "proj-1" not in service._evaluating


# =============================================================================
# Handle Evaluation
# =============================================================================


class TestHandleEvaluation:
    """Tests for handling evaluation results."""

    @pytest.mark.asyncio
    async def test_silent_evaluation_does_nothing(self, service):
        """When should_respond is False and no action, do nothing."""
        evaluation = AgentEvaluation(
            should_respond=False,
            confidence=0.9,
            reasoning="Social chat",
        )
        # If it tried to import and call conversation_service, it would error.
        # So no error = success.
        await service._handle_evaluation("proj-1", evaluation)

    @pytest.mark.asyncio
    async def test_posts_response_as_assistant(self, service):
        """When should_respond is True, post as assistant message."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="I can help with that.",
            confidence=0.85,
        )

        mock_conv = MagicMock()
        mock_conv.add_message = AsyncMock()

        with patch(
            "services.conversation_service.get_conversation_service",
            return_value=mock_conv,
        ):
            await service._handle_evaluation("proj-1", evaluation)

            mock_conv.add_message.assert_awaited_once()
            call_kwargs = mock_conv.add_message.call_args.kwargs
            assert call_kwargs["project_id"] == "proj-1"
            assert call_kwargs["user_id"] == AI_AGENT_USER_ID
            assert call_kwargs["display_name"] == AI_AGENT_DISPLAY_NAME
            assert call_kwargs["type"] == "assistant"
            assert call_kwargs["content"] == "I can help with that."

    @pytest.mark.asyncio
    async def test_detected_action_logged(self, service):
        """When action is detected, it should be logged (handoff to #248)."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="Should I create a work item for that?",
            detected_action="create_work",
            action_description="Create auth refactoring task",
            confidence=0.8,
        )

        mock_conv = MagicMock()
        mock_conv.add_message = AsyncMock()

        with patch(
            "services.conversation_service.get_conversation_service",
            return_value=mock_conv,
        ):
            # Should not raise — action detection logged for #248
            await service._handle_evaluation("proj-1", evaluation)
            mock_conv.add_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_conv_service_error(self, service):
        """Should not crash if ConversationService errors."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="Test response",
            confidence=0.9,
        )

        mock_conv = MagicMock()
        mock_conv.add_message = AsyncMock(side_effect=Exception("Redis down"))

        with patch(
            "services.conversation_service.get_conversation_service",
            return_value=mock_conv,
        ):
            # Should not raise
            await service._handle_evaluation("proj-1", evaluation)


# =============================================================================
# Singleton
# =============================================================================


class TestSingleton:
    def test_set_and_get(self):
        from services.ai_chat_agent_service import (
            get_ai_chat_agent_service,
            set_ai_chat_agent_service,
        )
        svc = AIChatAgentService()
        set_ai_chat_agent_service(svc)
        assert get_ai_chat_agent_service() is svc
        set_ai_chat_agent_service(None)
