"""Claude Client models for Slim Claude Code.

Models for Claude API client configuration and responses.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClaudeModel(str, Enum):
    """Available Claude model aliases for CLI usage."""
    SONNET_4 = "sonnet"
    OPUS_4 = "opus"
    HAIKU_35 = "haiku"


class ClaudeConfig(BaseModel):
    """Configuration for Claude API client.

    Controls model selection, request parameters, and retry behavior.
    """
    model: str = Field(
        default=ClaudeModel.SONNET_4.value,
        description="Claude model identifier to use"
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        le=200000,
        description="Maximum tokens in response"
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Sampling temperature (lower = more deterministic)"
    )
    timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=600,
        description="Request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient failures"
    )
    retry_delay_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Base delay between retries (exponential backoff)"
    )


class ClaudeMessage(BaseModel):
    """A message in a Claude conversation."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ClaudeResponse(BaseModel):
    """Response from Claude API.

    Contains the response content and metadata about the request.
    """
    content: str = Field(..., description="Response text content")
    model: str = Field(..., description="Model used for completion")
    input_tokens: int = Field(default=0, description="Input tokens used")
    output_tokens: int = Field(default=0, description="Output tokens generated")
    stop_reason: Optional[str] = Field(
        default=None,
        description="Reason for stopping generation"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ClaudeError(Exception):
    """Base exception for Claude API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ClaudeAPIError(ClaudeError):
    """Error from Claude API (non-retryable)."""
    pass


class ClaudeRateLimitError(ClaudeError):
    """Rate limit exceeded (retryable after delay)."""

    def __init__(
        self,
        message: str,
        retry_after_seconds: Optional[float] = None,
    ):
        super().__init__(message, status_code=429)
        self.retry_after_seconds = retry_after_seconds


class ClaudeTimeoutError(ClaudeError):
    """Request timed out (retryable)."""
    pass


class ClaudeParseError(ClaudeError):
    """Failed to parse Claude response as expected format."""
    pass
