"""AI Chat Agent models.

Configuration and response models for the conversational AI agent
that participates in project chat.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ResponseDecision(str, Enum):
    """The AI agent's decision on whether/how to respond."""
    RESPOND = "respond"
    SILENT = "silent"
    ACTION = "action"


class AgentResponseCriteria(str, Enum):
    """Categories for response likelihood."""
    ALWAYS = "always"
    LIKELY = "likely"
    MAYBE = "maybe"
    NEVER = "never"


class AssertivenesLevel(str, Enum):
    """How assertive the AI agent should be."""
    CONSERVATIVE = "conservative"  # Rarely speaks, only when directly asked
    BALANCED = "balanced"          # Default — asks before acting, responds when helpful
    PROACTIVE = "proactive"        # Actively participates, offers suggestions


class AIChatAgentConfig(BaseModel):
    """Per-project configuration for the AI chat agent.

    Controls personality, response thresholds, and behavior tuning.
    """
    enabled: bool = Field(
        default=True,
        description="Whether the AI agent is active in this project",
    )
    assertiveness: AssertivenesLevel = Field(
        default=AssertivenesLevel.BALANCED,
        description="How proactive the agent should be in conversations",
    )
    debounce_seconds: float = Field(
        default=4.0,
        ge=1.0,
        le=30.0,
        description="Seconds of silence before the agent evaluates messages",
    )
    max_response_tokens: int = Field(
        default=300,
        ge=50,
        le=1000,
        description="Maximum tokens for a conversational response",
    )
    context_window_messages: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Number of recent raw messages to include in context",
    )
    personality_note: str = Field(
        default="",
        description="Optional per-project personality adjustment (appended to system prompt)",
    )


class AgentEvaluation(BaseModel):
    """The AI agent's evaluation of a conversation batch.

    Returned by the agent when evaluating whether to respond.
    """
    should_respond: bool = Field(
        ...,
        description="Whether the agent should respond to this conversation",
    )
    response: Optional[str] = Field(
        default=None,
        description="The agent's response text (if should_respond is True)",
    )
    detected_action: Optional[str] = Field(
        default=None,
        description="Detected actionable intent (e.g., 'create_work', 'adjust_priority')",
    )
    action_description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the detected action",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the response/action decision",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief internal reasoning (for logging/debugging, not shown to users)",
    )
