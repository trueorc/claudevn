"""Common LLM types and data structures."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    MOCK = "mock"


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider: LLMProvider
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    priority: int = 1
    timeout: int = 60
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    provider: LLMProvider
    model: str
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    cost_estimate: Optional[float] = None
    finish_reason: Optional[str] = None
    created_at: Optional[str] = None
    response_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMUsageStats:
    """Token usage statistics."""
    provider: LLMProvider
    model: str
    total_requests: int = 0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    failed_requests: int = 0


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LLMProviderError(LLMError):
    """Error from LLM provider (API error, rate limit, etc.)."""
    def __init__(self, message: str, provider: LLMProvider, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    pass


class LLMConfigError(LLMError):
    """Invalid LLM configuration."""
    pass

