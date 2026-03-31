"""AI Chat Agent Prompt Service.

Parameterizable system prompt templates and response criteria for the
conversational AI agent. The agent participates in project chat,
responding intelligently and only initiating work when actionable
intent is clearly detected.

Design decisions:
- System prompt is templated with string.Template for per-project tuning
- Response criteria are codified as structured rules, not free-text
- Assertiveness is a tunable parameter (conservative/balanced/proactive)
- Prompt tested against Haiku for cost-effective conversational responses

Reference: Issue #251
"""

import logging
from string import Template
from typing import List, Optional

from models.ai_chat_agent import (
    AgentEvaluation,
    AIChatAgentConfig,
    AssertivenesLevel,
)

logger = logging.getLogger(__name__)


# =============================================================================
# System Prompt Template
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = Template("""\
You are an AI assistant participating in a project chat for "$project_name". \
You are one participant among human team members — not the leader, not the main character.

## Identity & Tone
- Professional but not stiff. Concise — chat messages, not essays.
- Helpful without being sycophantic. No filler phrases like "Great question!" or "Absolutely!"
- Use short, direct sentences. Match the conversational style of the chat.
- You may use markdown formatting sparingly (bold for emphasis, backticks for code references).
- Never start with "As an AI..." or similar self-referential preamble.

## Response Rules

You are the AI assistant in this project chat. When a user sends a message, **respond by default**. \
Users expect you to engage — silence feels broken.

### ALWAYS respond when:
- Any user sends a message in the chat (this is the default behavior)
- Someone asks a question, makes a request, or starts a discussion
- Someone shares information, an error, or a problem
- Someone greets you or starts a conversation

### Stay SILENT only when:
- Two or more humans are clearly in the middle of a back-and-forth exchange with each other
- Your last response already answered the question and nothing new was added
- The message is a simple acknowledgment like "ok", "thanks", "got it" with no follow-up needed

## Assertiveness
$assertiveness_instructions

## Your Role
You are NOT a code assistant. You do NOT write code, scaffold projects, or create files yourself. \
Your role is to help users clarify what they want, then **hand off work to the directive system** \
which assigns it to compute workers.

## Action Detection & Work Creation
Your primary job is to recognize when the user intends for work to be performed and kick it off \
via `[ACTION:create_work:...]` signal markers. Bias toward action — users are here to get things done.

### The cardinal rule: markers and questions are mutually exclusive.
- If you emit an ACTION marker → your response is a confident confirmation with NO open questions.
- If you still need to ask something → no markers in that response.

The marker kicks off **planning and decomposition** — not direct code changes. Your response \
should acknowledge that you're creating a plan (e.g., "I'll plan that out" or "Setting up the \
decomposition for that"). Do NOT say "I'll build" or "I'll add" as if you're making changes \
directly — the system creates a plan that the user reviews and approves before execution.

### Bias toward action
Most user messages contain enough information to act. Make reasonable assumptions and fill gaps yourself. \
You do NOT need the user to spell out every detail — infer tech choices, folder structure, and scope \
from context. If the user says "build me X" that's usually enough to go.

- At most ONE round of clarification if something is genuinely ambiguous.
- If the user has already provided a clear description of what they want, ACT — don't ask more questions.
- If the user says "let's go", "get started", "do it", "/start" → that's a go, emit the marker immediately.
- "Your choice" or "whatever you think" means make the decision and act.

### Work description quality
When you emit a marker, the description must be a complete, self-contained work directive. \
Include all decisions (yours and the user's) from the conversation. A compute worker reading \
only the description should know exactly what to build.

## Signal Markers
After your response text, append signal markers on their own line. These are stripped before display.

- **Action:** `[ACTION:create_work:0.85] full work description` or `[ACTION:adjust_priority:0.90] description`
  Confidence 0.0-1.0. Only include when confidence >= 0.6.
- **Escalation:** `[ESCALATE:sonnet]` if the question requires deeper reasoning than you can provide.

Example — user intent is clear:
```
I'll plan out the Rubik's cube project — React frontend with a JS-based cube renderer and FastAPI backend. You can review the decomposition on the Plan page once it's ready.
[ACTION:create_work:0.90] Build Rubik's cube simulator: React frontend with JavaScript-based cube rendering, FastAPI backend with cube state model and move validation API endpoints. No persistence — state lives in memory. Frontend calls API for all moves.
```

Most conversational responses have no markers. But when the user wants work done, emit them promptly.

## Context
$context_section

$personality_note\
""")

# Assertiveness-specific instruction blocks
_ASSERTIVENESS_INSTRUCTIONS = {
    AssertivenesLevel.CONSERVATIVE: """\
You lean heavily toward silence. Only respond when directly addressed or when \
someone is clearly stuck and no one else has helped. When you do respond, \
keep it brief — one or two sentences maximum. Never volunteer suggestions \
or offer to take action unless explicitly asked.""",

    AssertivenesLevel.BALANCED: """\
You lean toward asking rather than telling. "Should I set that up?" not \
"I'm setting that up." Prefer to contribute when you have specific, useful \
information rather than general commentary. When in doubt, respond — users \
expect engagement, and silence feels like something is broken.""",

    AssertivenesLevel.PROACTIVE: """\
You actively participate in discussions when you have relevant context. \
You proactively suggest actions when patterns emerge ("It looks like you're \
converging on X — should I create a work item?"). You still ask before \
acting, but you're more forward about offering help and noticing opportunities.""",
}


# =============================================================================
# Evaluation Prompt Template
# =============================================================================

EVALUATION_PROMPT_TEMPLATE = Template("""\
You are evaluating a batch of chat messages to decide if and how to respond.

## Recent Messages
$messages

## Rolling Context Summary
$context_summary

## Instructions
Evaluate the messages above and decide how to respond.
1. You should respond to the latest user message by default. Only set should_respond to false if the SILENT rules clearly apply.
2. Keep your response concise (1-3 sentences for chat, more only if explaining something technical).
3. Is there an actionable work intent? Only flag this if the intent is clear and specific.

4. What complexity tier does this require?
   - "haiku": Simple conversational responses, status updates, acknowledgments
   - "sonnet": Questions requiring reasoning, multi-step analysis, code explanation, architectural discussion
   - "compute": Deep research requiring codebase investigation, file reading, log analysis, comparative analysis

Indicators for sonnet: "why", "how should we", "compare", "explain the architecture", "what's the best approach"
Indicators for compute: "look at the code", "find where", "check the logs", "investigate the bug", "search for"

Respond with JSON only:
{
  "should_respond": true/false,
  "response": "your response text or null",
  "detected_action": "create_work" | "adjust_priority" | null,
  "action_description": "human-readable description of the action or null",
  "complexity_tier": "haiku" | "sonnet" | "compute",
  "confidence": 0.0-1.0,
  "reasoning": "brief internal reasoning"
}
""")


# =============================================================================
# Service
# =============================================================================

class AIChatPromptService:
    """Builds system prompts and evaluation prompts for the AI chat agent.

    The service is stateless — it generates prompts from config and context.
    Per-project configuration is passed in, not stored here.
    """

    def build_system_prompt(
        self,
        project_name: str,
        config: Optional[AIChatAgentConfig] = None,
        context_summary: Optional[str] = None,
        active_goals: Optional[List[str]] = None,
    ) -> str:
        """Build the system prompt for the AI chat agent.

        Args:
            project_name: Name of the project conversation.
            config: Agent configuration (uses defaults if None).
            context_summary: Rolling summary of conversation history.
            active_goals: List of currently active goal titles for context.

        Returns:
            Fully rendered system prompt string.
        """
        if config is None:
            config = AIChatAgentConfig()

        assertiveness_instructions = _ASSERTIVENESS_INSTRUCTIONS.get(
            config.assertiveness,
            _ASSERTIVENESS_INSTRUCTIONS[AssertivenesLevel.BALANCED],
        )

        # Build context section
        context_parts = []
        if context_summary:
            context_parts.append(f"Conversation summary so far: {context_summary}")
        if active_goals:
            goals_list = "\n".join(f"- {g}" for g in active_goals[:10])
            context_parts.append(f"Currently active goals:\n{goals_list}")
        context_section = "\n\n".join(context_parts) if context_parts else "No prior context available."

        personality_note = ""
        if config.personality_note:
            personality_note = f"\n## Project-Specific Notes\n{config.personality_note}\n"

        return SYSTEM_PROMPT_TEMPLATE.substitute(
            project_name=project_name,
            assertiveness_instructions=assertiveness_instructions,
            context_section=context_section,
            personality_note=personality_note,
        )

    def build_conversation_prompt(
        self,
        messages: List[dict],
        context_summary: Optional[str] = None,
    ) -> str:
        """Build a direct conversation prompt (no JSON, no meta-evaluation).

        Presents the recent messages and asks Claude to respond naturally.
        """
        formatted = []
        for msg in messages:
            name = msg.get("display_name", "Unknown")
            content = msg.get("content", "")
            formatted.append(f"[{name}]: {content}")

        messages_text = "\n".join(formatted) if formatted else "(no messages)"
        summary_text = f"\n\nConversation context: {context_summary}" if context_summary else ""

        return (
            f"Recent chat messages:\n{messages_text}{summary_text}\n\n"
            f"Respond to the latest message in the conversation above. "
            f"Be concise and conversational. Do not include any JSON or metadata. "
            f"You may append signal markers as described in your instructions."
        )

    def build_evaluation_prompt(
        self,
        messages: List[dict],
        context_summary: Optional[str] = None,
    ) -> str:
        """Build the evaluation prompt for a batch of messages.

        Args:
            messages: Recent messages to evaluate. Each dict should have
                      'display_name', 'content', and optionally 'type'.
            context_summary: Rolling conversation summary.

        Returns:
            Evaluation prompt string.
        """
        formatted_messages = []
        for msg in messages:
            name = msg.get("display_name", "Unknown")
            content = msg.get("content", "")
            formatted_messages.append(f"[{name}]: {content}")

        messages_text = "\n".join(formatted_messages) if formatted_messages else "(no messages)"
        summary_text = context_summary or "(no prior context)"

        return EVALUATION_PROMPT_TEMPLATE.substitute(
            messages=messages_text,
            context_summary=summary_text,
        )

    def parse_evaluation_response(self, response_text: str) -> AgentEvaluation:
        """Parse the AI's evaluation response into a structured model.

        Args:
            response_text: Raw text response from Claude.

        Returns:
            Parsed AgentEvaluation.

        Raises:
            ValueError: If response cannot be parsed.
        """
        import json

        text = response_text.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(json_lines)

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON object found in response: {text[:200]}")

        try:
            data = json.loads(text[start:end])
            return AgentEvaluation.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            raise ValueError(f"Failed to parse evaluation response: {e}")


# =============================================================================
# Module-level singleton
# =============================================================================

_prompt_service: Optional[AIChatPromptService] = None


def get_ai_chat_prompt_service() -> AIChatPromptService:
    """Get the global AI chat prompt service instance."""
    global _prompt_service
    if _prompt_service is None:
        _prompt_service = AIChatPromptService()
    return _prompt_service
