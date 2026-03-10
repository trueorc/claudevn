"""Tests for AI Chat Agent Prompt Service.

Covers system prompt generation, evaluation prompt building,
response parsing, and test conversation scenarios.
"""

import json
import pytest

from models.ai_chat_agent import (
    AgentEvaluation,
    AIChatAgentConfig,
    AssertivenesLevel,
)
from services.ai_chat_prompt_service import AIChatPromptService


@pytest.fixture
def service():
    return AIChatPromptService()


@pytest.fixture
def default_config():
    return AIChatAgentConfig()


# =============================================================================
# System Prompt Generation
# =============================================================================


class TestBuildSystemPrompt:
    """Tests for system prompt template rendering."""

    def test_includes_project_name(self, service):
        prompt = service.build_system_prompt("MyProject")
        assert "MyProject" in prompt

    def test_default_assertiveness_is_balanced(self, service):
        prompt = service.build_system_prompt("Test")
        assert "asking rather than telling" in prompt

    def test_conservative_assertiveness(self, service):
        config = AIChatAgentConfig(assertiveness=AssertivenesLevel.CONSERVATIVE)
        prompt = service.build_system_prompt("Test", config=config)
        assert "lean heavily toward silence" in prompt

    def test_proactive_assertiveness(self, service):
        config = AIChatAgentConfig(assertiveness=AssertivenesLevel.PROACTIVE)
        prompt = service.build_system_prompt("Test", config=config)
        assert "actively participate" in prompt

    def test_includes_context_summary(self, service):
        prompt = service.build_system_prompt(
            "Test",
            context_summary="Users discussed auth flow improvements.",
        )
        assert "auth flow improvements" in prompt

    def test_includes_active_goals(self, service):
        prompt = service.build_system_prompt(
            "Test",
            active_goals=["Implement auth", "Fix performance"],
        )
        assert "Implement auth" in prompt
        assert "Fix performance" in prompt

    def test_personality_note_appended(self, service):
        config = AIChatAgentConfig(
            personality_note="This project prefers British English spelling."
        )
        prompt = service.build_system_prompt("Test", config=config)
        assert "British English" in prompt

    def test_no_context_shows_fallback(self, service):
        prompt = service.build_system_prompt("Test")
        assert "No prior context available" in prompt

    def test_response_rules_present(self, service):
        prompt = service.build_system_prompt("Test")
        assert "ALWAYS respond" in prompt
        assert "Stay SILENT" in prompt

    def test_action_detection_rules_present(self, service):
        prompt = service.build_system_prompt("Test")
        assert "Action Detection" in prompt
        assert "NEVER silently create" in prompt

    def test_no_sycophancy_instruction(self, service):
        prompt = service.build_system_prompt("Test")
        assert "Great question" in prompt  # In the "don't say" instruction

    def test_prompt_is_parameterizable(self, service):
        """Verify the prompt changes with different configs."""
        config_a = AIChatAgentConfig(assertiveness=AssertivenesLevel.CONSERVATIVE)
        config_b = AIChatAgentConfig(assertiveness=AssertivenesLevel.PROACTIVE)
        prompt_a = service.build_system_prompt("Test", config=config_a)
        prompt_b = service.build_system_prompt("Test", config=config_b)
        assert prompt_a != prompt_b


# =============================================================================
# Evaluation Prompt
# =============================================================================


class TestBuildEvaluationPrompt:
    """Tests for evaluation prompt building."""

    def test_formats_messages(self, service):
        messages = [
            {"display_name": "Alice", "content": "Should we refactor the auth module?"},
            {"display_name": "Bob", "content": "I think so, the code is messy."},
        ]
        prompt = service.build_evaluation_prompt(messages)
        assert "[Alice]:" in prompt
        assert "[Bob]:" in prompt
        assert "refactor the auth module" in prompt

    def test_includes_context_summary(self, service):
        prompt = service.build_evaluation_prompt(
            messages=[{"display_name": "Alice", "content": "test"}],
            context_summary="Prior discussion about deployment.",
        )
        assert "deployment" in prompt

    def test_empty_messages(self, service):
        prompt = service.build_evaluation_prompt(messages=[])
        assert "(no messages)" in prompt

    def test_no_context_summary(self, service):
        prompt = service.build_evaluation_prompt(
            messages=[{"display_name": "Alice", "content": "hello"}],
        )
        assert "(no prior context)" in prompt

    def test_json_output_instruction(self, service):
        prompt = service.build_evaluation_prompt(
            messages=[{"display_name": "Alice", "content": "test"}],
        )
        assert "should_respond" in prompt
        assert "detected_action" in prompt


# =============================================================================
# Response Parsing
# =============================================================================


class TestParseEvaluationResponse:
    """Tests for parsing AI evaluation responses."""

    def test_parses_valid_json(self, service):
        response = json.dumps({
            "should_respond": True,
            "response": "I can help with that.",
            "detected_action": None,
            "action_description": None,
            "confidence": 0.85,
            "reasoning": "Direct question to the AI.",
        })
        result = service.parse_evaluation_response(response)
        assert isinstance(result, AgentEvaluation)
        assert result.should_respond is True
        assert result.response == "I can help with that."
        assert result.confidence == 0.85

    def test_parses_silent_response(self, service):
        response = json.dumps({
            "should_respond": False,
            "response": None,
            "detected_action": None,
            "action_description": None,
            "confidence": 0.9,
            "reasoning": "Users having social chat.",
        })
        result = service.parse_evaluation_response(response)
        assert result.should_respond is False
        assert result.response is None

    def test_parses_action_detection(self, service):
        response = json.dumps({
            "should_respond": True,
            "response": "It sounds like you want to create a work item. Should I set that up?",
            "detected_action": "create_work",
            "action_description": "Create auth refactoring task",
            "confidence": 0.8,
            "reasoning": "Clear action signal from user.",
        })
        result = service.parse_evaluation_response(response)
        assert result.detected_action == "create_work"
        assert result.action_description is not None

    def test_handles_markdown_wrapped_json(self, service):
        response = "```json\n" + json.dumps({
            "should_respond": True,
            "response": "Test",
            "confidence": 0.5,
        }) + "\n```"
        result = service.parse_evaluation_response(response)
        assert result.should_respond is True

    def test_handles_json_with_surrounding_text(self, service):
        response = 'Here is my evaluation:\n{"should_respond": false, "confidence": 0.9}\nDone.'
        result = service.parse_evaluation_response(response)
        assert result.should_respond is False

    def test_raises_on_invalid_json(self, service):
        with pytest.raises(ValueError, match="No JSON object found"):
            service.parse_evaluation_response("I think I should respond.")

    def test_raises_on_malformed_json(self, service):
        with pytest.raises(ValueError, match="Failed to parse"):
            service.parse_evaluation_response('{"should_respond": }')


# =============================================================================
# Test Conversation Scenarios
# =============================================================================


class TestConversationScenarios:
    """Test scenarios documenting expected AI behavior.

    These validate that the prompt structure supports the right decisions.
    They test prompt content, not actual AI inference.
    """

    def test_scenario_direct_question(self, service):
        """Scenario: User asks the AI a direct question.
        Expected: AI should always respond."""
        prompt = service.build_system_prompt("Test")
        # The prompt should instruct the agent to always respond to questions
        assert "asks a question" in prompt

    def test_scenario_user_to_user_social(self, service):
        """Scenario: Two users chatting socially.
        Expected: AI should stay silent."""
        prompt = service.build_system_prompt("Test")
        assert "back-and-forth exchange with each other" in prompt

    def test_scenario_debating_approach(self, service):
        """Scenario: Two users debating a technical approach.
        Expected: AI should wait, maybe contribute if stuck."""
        prompt = service.build_system_prompt("Test")
        assert "back-and-forth exchange" in prompt

    def test_scenario_clear_action_intent(self, service):
        """Scenario: User says 'Let's build the auth module'.
        Expected: AI should detect action and confirm."""
        prompt = service.build_system_prompt("Test")
        assert "Let's build X" in prompt
        assert "ask for confirmation" in prompt

    def test_scenario_ambiguous_intent(self, service):
        """Scenario: User says 'We should probably fix the auth flow'.
        Expected: AI should ask clarifying question."""
        prompt = service.build_system_prompt("Test")
        assert "We should probably fix" in prompt
        assert "clarifying question" in prompt

    def test_scenario_rapid_fire(self, service):
        """Scenario: Multiple messages in quick succession.
        Expected: AI should wait for the pause (debounce)."""
        prompt = service.build_system_prompt("Test")
        # Debounce is handled at the service layer, prompt just instructs response behavior
        assert "respond by default" in prompt

    def test_scenario_user_corrects_ai(self, service):
        """Scenario: User tells the AI to stop or corrects it.
        Expected: Prompt doesn't enforce persistence."""
        prompt = service.build_system_prompt("Test")
        # Balanced mode asks before acting, which allows graceful correction
        assert "asking rather than telling" in prompt

    def test_scenario_unanswered_question(self, service):
        """Scenario: A question goes unanswered after the silence window.
        Expected: AI should likely respond."""
        prompt = service.build_system_prompt("Test")
        assert "asks a question" in prompt

    def test_scenario_mixed_conversation(self, service):
        """Scenario: Social + technical + actionable in one thread.
        Expected: Prompt has rules for each type."""
        prompt = service.build_system_prompt("Test")
        # All categories are covered in the prompt
        assert "ALWAYS respond" in prompt
        assert "Stay SILENT" in prompt
        assert "Action Detection" in prompt


# =============================================================================
# Configuration Model
# =============================================================================


class TestAIChatAgentConfig:
    """Tests for AIChatAgentConfig model."""

    def test_default_values(self):
        config = AIChatAgentConfig()
        assert config.enabled is True
        assert config.assertiveness == AssertivenesLevel.BALANCED
        assert config.debounce_seconds == 0.8
        assert config.max_response_tokens == 300
        assert config.context_window_messages == 20
        assert config.personality_note == ""

    def test_custom_values(self):
        config = AIChatAgentConfig(
            assertiveness=AssertivenesLevel.CONSERVATIVE,
            debounce_seconds=8.0,
            max_response_tokens=150,
        )
        assert config.assertiveness == AssertivenesLevel.CONSERVATIVE
        assert config.debounce_seconds == 8.0
        assert config.max_response_tokens == 150

    def test_debounce_bounds(self):
        with pytest.raises(Exception):
            AIChatAgentConfig(debounce_seconds=0.05)
        with pytest.raises(Exception):
            AIChatAgentConfig(debounce_seconds=31.0)

    def test_response_tokens_bounds(self):
        with pytest.raises(Exception):
            AIChatAgentConfig(max_response_tokens=10)
        with pytest.raises(Exception):
            AIChatAgentConfig(max_response_tokens=1500)
