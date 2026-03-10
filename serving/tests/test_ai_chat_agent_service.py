"""Tests for AI Chat Agent Service.

Covers message handling, debounce mechanism, evaluation flow,
response posting, action detection handoff, and edge cases.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.ai_chat_agent import AgentEvaluation, AIChatAgentConfig, AssertivenesLevel, ComplexityTier
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
        assert config.debounce_seconds == 0.8

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
                mock_reset.assert_called_once_with("proj-1", 0.8)

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
    async def test_detected_action_triggers_handoff(self, service):
        """When action is detected, it should trigger the handoff flow."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="I'll create a work item for that.",
            detected_action="create_work",
            action_description="Create auth refactoring task",
            confidence=0.85,
        )

        mock_conv = MagicMock()
        mock_conv.add_message = AsyncMock()

        with patch(
            "services.conversation_service.get_conversation_service",
            return_value=mock_conv,
        ):
            with patch.object(
                service, '_handle_action_handoff', new_callable=AsyncMock
            ) as mock_handoff:
                await service._handle_evaluation("proj-1", evaluation)
                mock_conv.add_message.assert_awaited_once()
                mock_handoff.assert_awaited_once_with("proj-1", evaluation)

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
# Action Handoff (#248)
# =============================================================================


class TestActionHandoff:
    """Tests for action detection and directive handoff."""

    @pytest.mark.asyncio
    async def test_submits_directive_for_high_confidence_action(self, service):
        """High confidence action should submit a directive."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="I'll create that for you.",
            detected_action="create_work",
            action_description="Create auth refactoring task",
            confidence=0.85,
        )

        mock_directive_service = MagicMock()
        mock_directive = MagicMock()
        mock_directive.directive_id = "udir_test123"
        mock_directive_service.submit = AsyncMock(return_value=mock_directive)

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
            return_value=mock_directive_service,
        ):
            await service._handle_action_handoff("proj-1", evaluation)
            mock_directive_service.submit.assert_awaited_once_with(
                project_id="proj-1",
                text="Create auth refactoring task",
            )

    @pytest.mark.asyncio
    async def test_skips_directive_below_confidence_threshold(self, service):
        """Low confidence action should NOT submit a directive."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="Are you thinking of creating a task for that?",
            detected_action="create_work",
            action_description="Maybe create auth task",
            confidence=0.5,  # Below default threshold of 0.75
        )

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
        ) as mock_get:
            await service._handle_action_handoff("proj-1", evaluation)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_confidence_threshold(self, service):
        """Custom threshold should be respected."""
        service.set_config("proj-1", AIChatAgentConfig(
            action_confidence_threshold=0.9,
        ))

        evaluation = AgentEvaluation(
            should_respond=True,
            response="I'll set that up.",
            detected_action="create_work",
            action_description="Create deployment pipeline",
            confidence=0.85,  # Above default but below custom threshold
        )

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
        ) as mock_get:
            await service._handle_action_handoff("proj-1", evaluation)
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplication_prevents_repeat_submission(self, service):
        """Same action+description should not be submitted twice."""
        evaluation = AgentEvaluation(
            should_respond=True,
            response="Creating that now.",
            detected_action="create_work",
            action_description="Create auth refactoring task",
            confidence=0.85,
        )

        mock_directive_service = MagicMock()
        mock_directive = MagicMock()
        mock_directive.directive_id = "udir_test123"
        mock_directive_service.submit = AsyncMock(return_value=mock_directive)

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
            return_value=mock_directive_service,
        ):
            # First submission — should go through
            await service._handle_action_handoff("proj-1", evaluation)
            assert mock_directive_service.submit.await_count == 1

            # Second submission — should be deduplicated
            await service._handle_action_handoff("proj-1", evaluation)
            assert mock_directive_service.submit.await_count == 1

    @pytest.mark.asyncio
    async def test_different_actions_not_deduplicated(self, service):
        """Different action descriptions should both be submitted."""
        mock_directive_service = MagicMock()
        mock_directive = MagicMock()
        mock_directive.directive_id = "udir_test123"
        mock_directive_service.submit = AsyncMock(return_value=mock_directive)

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
            return_value=mock_directive_service,
        ):
            eval1 = AgentEvaluation(
                should_respond=True,
                detected_action="create_work",
                action_description="Create auth task",
                confidence=0.85,
            )
            await service._handle_action_handoff("proj-1", eval1)

            eval2 = AgentEvaluation(
                should_respond=True,
                detected_action="create_work",
                action_description="Create deploy task",
                confidence=0.85,
            )
            await service._handle_action_handoff("proj-1", eval2)

            assert mock_directive_service.submit.await_count == 2

    @pytest.mark.asyncio
    async def test_priority_adjustment_directive_text(self, service):
        """Priority adjustment actions should have prefixed text."""
        evaluation = AgentEvaluation(
            should_respond=True,
            detected_action="adjust_priority",
            action_description="Bump auth task to P0",
            confidence=0.85,
        )

        mock_directive_service = MagicMock()
        mock_directive = MagicMock()
        mock_directive.directive_id = "udir_test123"
        mock_directive_service.submit = AsyncMock(return_value=mock_directive)

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
            return_value=mock_directive_service,
        ):
            await service._handle_action_handoff("proj-1", evaluation)
            call_kwargs = mock_directive_service.submit.call_args.kwargs
            assert call_kwargs["text"] == "Priority adjustment: Bump auth task to P0"

    @pytest.mark.asyncio
    async def test_handles_directive_service_unavailable(self, service):
        """Should not crash if directive service is unavailable."""
        evaluation = AgentEvaluation(
            should_respond=True,
            detected_action="create_work",
            action_description="Create task",
            confidence=0.85,
        )

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
            return_value=None,
        ):
            # Should not raise
            await service._handle_action_handoff("proj-1", evaluation)

    @pytest.mark.asyncio
    async def test_handles_directive_submission_error(self, service):
        """Should not crash if directive submission fails."""
        evaluation = AgentEvaluation(
            should_respond=True,
            detected_action="create_work",
            action_description="Create task",
            confidence=0.85,
        )

        mock_directive_service = MagicMock()
        mock_directive_service.submit = AsyncMock(
            side_effect=Exception("Service unavailable")
        )

        with patch(
            "services.unified_directive_service.get_unified_directive_service",
            return_value=mock_directive_service,
        ):
            # Should not raise
            await service._handle_action_handoff("proj-1", evaluation)

    def test_stop_clears_recent_actions(self):
        """Stop should clear deduplication state."""
        svc = AIChatAgentService()
        svc.start()
        svc._recent_actions["proj-1"] = [("create_work", "task", time.monotonic())]
        svc.stop()
        assert len(svc._recent_actions) == 0

    def test_build_directive_text_create_work(self, service):
        """create_work actions use description directly."""
        text = service._build_directive_text("create_work", "Build auth system")
        assert text == "Build auth system"

    def test_build_directive_text_adjust_priority(self, service):
        """adjust_priority actions get prefixed."""
        text = service._build_directive_text("adjust_priority", "Bump auth to P0")
        assert text == "Priority adjustment: Bump auth to P0"


# =============================================================================
# Model Escalation (#249)
# =============================================================================


class TestComplexityTier:
    """Tests for complexity tier resolution."""

    def test_haiku_tier_default(self, service):
        """No complexity_tier defaults to haiku."""
        evaluation = AgentEvaluation(should_respond=True, confidence=0.8)
        config = service.get_config("proj-1")
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.HAIKU

    def test_haiku_tier_explicit(self, service):
        """Explicit haiku tier stays haiku."""
        evaluation = AgentEvaluation(
            should_respond=True, complexity_tier="haiku", confidence=0.8,
        )
        config = service.get_config("proj-1")
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.HAIKU

    def test_sonnet_tier(self, service):
        """Sonnet tier is resolved when within rate limit."""
        evaluation = AgentEvaluation(
            should_respond=True, complexity_tier="sonnet", confidence=0.8,
        )
        config = service.get_config("proj-1")
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.SONNET

    def test_compute_tier(self, service):
        """Compute tier is resolved when within rate limit."""
        evaluation = AgentEvaluation(
            should_respond=True, complexity_tier="compute", confidence=0.8,
        )
        config = service.get_config("proj-1")
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.COMPUTE

    def test_sonnet_rate_limit_downgrades_to_haiku(self, service):
        """When sonnet rate limit exceeded, downgrade to haiku."""
        config = AIChatAgentConfig(sonnet_escalations_per_hour=2)
        service.set_config("proj-1", config)

        # Exhaust rate limit
        now = time.monotonic()
        service._sonnet_usage["proj-1"] = [now, now]

        evaluation = AgentEvaluation(
            should_respond=True, complexity_tier="sonnet", confidence=0.8,
        )
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.HAIKU

    def test_compute_rate_limit_downgrades_to_sonnet(self, service):
        """When compute rate limit exceeded, downgrade to sonnet."""
        config = AIChatAgentConfig(compute_offloads_per_hour=1)
        service.set_config("proj-1", config)

        now = time.monotonic()
        service._compute_usage["proj-1"] = [now]

        evaluation = AgentEvaluation(
            should_respond=True, complexity_tier="compute", confidence=0.8,
        )
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.SONNET

    def test_compute_and_sonnet_both_exhausted_falls_to_haiku(self, service):
        """When both compute and sonnet exhausted, fall to haiku."""
        config = AIChatAgentConfig(
            compute_offloads_per_hour=1,
            sonnet_escalations_per_hour=1,
        )
        service.set_config("proj-1", config)

        now = time.monotonic()
        service._compute_usage["proj-1"] = [now]
        service._sonnet_usage["proj-1"] = [now]

        evaluation = AgentEvaluation(
            should_respond=True, complexity_tier="compute", confidence=0.8,
        )
        tier = service._resolve_complexity_tier(evaluation, "proj-1", config)
        assert tier == ComplexityTier.HAIKU


class TestSonnetEscalation:
    """Tests for Sonnet model escalation."""

    @pytest.mark.asyncio
    async def test_escalation_posts_thinking_indicator(self, service):
        """Sonnet escalation should post a thinking indicator."""
        mock_conv = MagicMock()
        mock_conv.add_message = AsyncMock()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"should_respond": true, "response": "Deep analysis...", "confidence": 0.9}'
        mock_client.complete = AsyncMock(return_value=mock_response)

        haiku_eval = AgentEvaluation(
            should_respond=True, response="placeholder", confidence=0.8,
        )

        with patch(
            "services.conversation_service.get_conversation_service",
            return_value=mock_conv,
        ):
            with patch(
                "services.claude_client.get_claude_client",
                return_value=mock_client,
            ):
                with patch(
                    "services.ai_chat_prompt_service.get_ai_chat_prompt_service",
                ) as mock_prompt_svc:
                    mock_prompt_svc.return_value.parse_evaluation_response.return_value = (
                        AgentEvaluation(
                            should_respond=True,
                            response="Deep analysis...",
                            confidence=0.9,
                        )
                    )
                    config = service.get_config("proj-1")
                    result = await service._escalate_to_sonnet(
                        "proj-1", config, "system", "eval", haiku_eval
                    )

        # Check thinking indicator was posted
        mock_conv.add_message.assert_awaited_once()
        call_kwargs = mock_conv.add_message.call_args.kwargs
        assert call_kwargs["type"] == "thinking"
        assert call_kwargs["content"] == "Thinking..."

    @pytest.mark.asyncio
    async def test_escalation_uses_sonnet_model(self, service):
        """Escalation should use Sonnet model."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"should_respond": true, "response": "Answer", "confidence": 0.9}'
        mock_client.complete = AsyncMock(return_value=mock_response)

        haiku_eval = AgentEvaluation(
            should_respond=True, response="placeholder", confidence=0.8,
        )

        with patch.object(service, '_post_thinking_indicator', new_callable=AsyncMock):
            with patch(
                "services.claude_client.get_claude_client",
                return_value=mock_client,
            ):
                with patch(
                    "services.ai_chat_prompt_service.get_ai_chat_prompt_service",
                ) as mock_prompt_svc:
                    mock_prompt_svc.return_value.parse_evaluation_response.return_value = (
                        AgentEvaluation(should_respond=True, response="Answer", confidence=0.9)
                    )
                    config = service.get_config("proj-1")
                    await service._escalate_to_sonnet(
                        "proj-1", config, "system", "eval", haiku_eval
                    )

        # Verify Sonnet model was used
        call_kwargs = mock_client.complete.call_args.kwargs
        assert "sonnet" in call_kwargs["model"]

    @pytest.mark.asyncio
    async def test_escalation_records_rate_limit(self, service):
        """Escalation should record usage for rate limiting."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"should_respond": true, "response": "Answer", "confidence": 0.9}'
        mock_client.complete = AsyncMock(return_value=mock_response)

        haiku_eval = AgentEvaluation(
            should_respond=True, response="placeholder", confidence=0.8,
        )

        with patch.object(service, '_post_thinking_indicator', new_callable=AsyncMock):
            with patch(
                "services.claude_client.get_claude_client",
                return_value=mock_client,
            ):
                with patch(
                    "services.ai_chat_prompt_service.get_ai_chat_prompt_service",
                ) as mock_prompt_svc:
                    mock_prompt_svc.return_value.parse_evaluation_response.return_value = (
                        AgentEvaluation(should_respond=True, response="Answer", confidence=0.9)
                    )
                    config = service.get_config("proj-1")
                    await service._escalate_to_sonnet(
                        "proj-1", config, "system", "eval", haiku_eval
                    )

        assert len(service._sonnet_usage.get("proj-1", [])) == 1

    @pytest.mark.asyncio
    async def test_escalation_fallback_on_error(self, service):
        """On Sonnet failure, should fall back to Haiku evaluation."""
        mock_client = MagicMock()
        mock_client.complete = AsyncMock(side_effect=Exception("API error"))

        haiku_eval = AgentEvaluation(
            should_respond=True, response="Haiku answer", confidence=0.7,
        )

        with patch.object(service, '_post_thinking_indicator', new_callable=AsyncMock):
            with patch(
                "services.claude_client.get_claude_client",
                return_value=mock_client,
            ):
                config = service.get_config("proj-1")
                result = await service._escalate_to_sonnet(
                    "proj-1", config, "system", "eval", haiku_eval
                )

        # Should return the original haiku evaluation
        assert result.response == "Haiku answer"

    def test_stop_clears_escalation_state(self):
        """Stop should clear rate limiting state."""
        svc = AIChatAgentService()
        svc.start()
        svc._sonnet_usage["proj-1"] = [time.monotonic()]
        svc._compute_usage["proj-1"] = [time.monotonic()]
        svc.stop()
        assert len(svc._sonnet_usage) == 0
        assert len(svc._compute_usage) == 0


class TestSignalMarkerParsing:
    """Tests for inline signal marker parsing."""

    def test_no_markers(self, service):
        """Plain text should pass through unchanged."""
        text = "I can help with that."
        clean, action, escalate = service._parse_signal_markers(text)
        assert clean == "I can help with that."
        assert action is None
        assert escalate is False

    def test_action_marker_parsed(self, service):
        """Action marker should be extracted and stripped."""
        text = "Should I create a work item for that?\n[ACTION:create_work:0.85] Create auth refactor task"
        clean, action, escalate = service._parse_signal_markers(text)
        assert clean == "Should I create a work item for that?"
        assert action is not None
        assert action[0] == "create_work"
        assert action[1] == 0.85
        assert action[2] == "Create auth refactor task"
        assert escalate is False

    def test_escalate_marker_parsed(self, service):
        """Escalate marker should be detected and stripped."""
        text = "Let me look into that more deeply.\n[ESCALATE:sonnet]"
        clean, action, escalate = service._parse_signal_markers(text)
        assert clean == "Let me look into that more deeply."
        assert action is None
        assert escalate is True

    def test_both_markers(self, service):
        """Both action and escalation markers together."""
        text = "I'll create that and investigate.\n[ACTION:create_work:0.90] Build auth system\n[ESCALATE:sonnet]"
        clean, action, escalate = service._parse_signal_markers(text)
        assert clean == "I'll create that and investigate."
        assert action is not None
        assert action[0] == "create_work"
        assert escalate is True

    def test_adjust_priority_action(self, service):
        """Priority adjustment action type."""
        text = "I'll bump that up.\n[ACTION:adjust_priority:0.80] Bump auth to P0"
        clean, action, escalate = service._parse_signal_markers(text)
        assert action[0] == "adjust_priority"
        assert action[1] == 0.80
        assert action[2] == "Bump auth to P0"

    def test_invalid_confidence_not_matched(self, service):
        """Non-numeric confidence value should not match the pattern."""
        text = "Test\n[ACTION:create_work:invalid] Do thing"
        clean, action, escalate = service._parse_signal_markers(text)
        assert action is None

    def test_marker_only_response(self, service):
        """Response that is only markers should result in empty clean text."""
        text = "[ACTION:create_work:0.85] Do thing\n[ESCALATE:sonnet]"
        clean, action, escalate = service._parse_signal_markers(text)
        assert clean == ""
        assert action is not None
        assert escalate is True


class TestRateLimiting:
    """Tests for rate limiting helpers."""

    def test_check_rate_limit_allows_within_limit(self, service):
        """Should allow when under the limit."""
        assert service._check_rate_limit(
            service._sonnet_usage, "proj-1", 5
        ) is True

    def test_check_rate_limit_blocks_at_limit(self, service):
        """Should block when at the limit."""
        now = time.monotonic()
        service._sonnet_usage["proj-1"] = [now] * 5
        assert service._check_rate_limit(
            service._sonnet_usage, "proj-1", 5
        ) is False

    def test_check_rate_limit_cleans_expired(self, service):
        """Should clean expired entries and allow new ones."""
        old = time.monotonic() - 3700  # More than 1 hour ago
        service._sonnet_usage["proj-1"] = [old] * 5
        assert service._check_rate_limit(
            service._sonnet_usage, "proj-1", 5
        ) is True
        # Expired entries should be cleaned
        assert len(service._sonnet_usage["proj-1"]) == 0

    def test_record_rate_limit(self, service):
        """Should record a timestamp."""
        service._record_rate_limit(service._sonnet_usage, "proj-1")
        assert len(service._sonnet_usage["proj-1"]) == 1


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
