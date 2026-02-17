"""Claude API Client Service for Slim Claude Code.

Provides a reusable client for interacting with the Claude API,
with support for retries, rate limiting, and structured JSON output.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from models.claude_client import (
    ClaudeConfig,
    ClaudeMessage,
    ClaudeResponse,
    ClaudeAPIError,
    ClaudeRateLimitError,
    ClaudeTimeoutError,
    ClaudeParseError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ClaudeClient:
    """Client for interacting with Claude API.

    Provides methods for text completion and structured JSON output,
    with automatic retry handling for transient failures.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[ClaudeConfig] = None,
    ):
        """Initialize the Claude client.

        Args:
            api_key: Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
            config: Client configuration. Uses defaults if not provided.

        Raises:
            ValueError: If no API key is available
            ImportError: If anthropic package is not installed
        """
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required"
            )

        self._config = config or ClaudeConfig()
        self._client = None  # Lazy initialization
        self._initialized = False

    def _ensure_client(self) -> None:
        """Ensure the Anthropic client is initialized."""
        if self._client is not None:
            return

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required. Install with: pip install anthropic"
            )

        self._client = anthropic.AsyncAnthropic(
            api_key=self._api_key,
            timeout=self._config.timeout_seconds,
        )
        self._initialized = True

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        messages: Optional[List[ClaudeMessage]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> ClaudeResponse:
        """Complete a prompt using Claude.

        Args:
            prompt: The user prompt (appended to messages if provided)
            system: Optional system prompt for context
            messages: Optional conversation history
            max_tokens: Override config max_tokens
            temperature: Override config temperature
            model: Override config model

        Returns:
            ClaudeResponse with content and metadata

        Raises:
            ClaudeAPIError: For non-retryable API errors
            ClaudeRateLimitError: If rate limit exceeded after retries
            ClaudeTimeoutError: If request times out after retries
        """
        self._ensure_client()

        # Build messages list
        message_list = []
        if messages:
            message_list.extend([
                {"role": m.role, "content": m.content}
                for m in messages
            ])
        message_list.append({"role": "user", "content": prompt})

        # Request parameters
        request_params = {
            "model": model or self._config.model,
            "max_tokens": max_tokens or self._config.max_tokens,
            "temperature": temperature if temperature is not None else self._config.temperature,
            "messages": message_list,
        }
        if system:
            request_params["system"] = system

        # Execute with retry
        return await self._execute_with_retry(request_params)

    async def complete_json(
        self,
        prompt: str,
        schema: Type[T],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> T:
        """Complete a prompt and parse response as a Pydantic model.

        Args:
            prompt: The user prompt requesting JSON output
            schema: Pydantic model class to parse response into
            system: Optional system prompt
            max_tokens: Override config max_tokens
            temperature: Override config temperature

        Returns:
            Parsed Pydantic model instance

        Raises:
            ClaudeParseError: If response cannot be parsed as JSON or validated
            ClaudeAPIError: For non-retryable API errors
        """
        # Add JSON instruction to system prompt
        json_system = (system or "") + (
            "\n\nYou must respond with valid JSON only. "
            "Do not include any text before or after the JSON. "
            "Do not wrap the JSON in markdown code blocks."
        )

        response = await self.complete(
            prompt=prompt,
            system=json_system.strip(),
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return self._parse_json_response(response.content, schema)

    def _parse_json_response(
        self,
        content: str,
        schema: Type[T],
    ) -> T:
        """Parse response content as JSON into a Pydantic model.

        Args:
            content: Raw response content
            schema: Pydantic model class

        Returns:
            Parsed model instance

        Raises:
            ClaudeParseError: If parsing or validation fails
        """
        # Strip whitespace and potential markdown
        json_str = content.strip()

        # Handle markdown code blocks
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            json_str = "\n".join(json_lines)

        # Try to find JSON object/array in the content
        json_str = json_str.strip()
        if not json_str.startswith("{") and not json_str.startswith("["):
            # Try to extract JSON from text
            start_idx = json_str.find("{")
            if start_idx == -1:
                start_idx = json_str.find("[")
            if start_idx != -1:
                json_str = json_str[start_idx:]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ClaudeParseError(
                f"Failed to parse response as JSON: {e}. "
                f"Response content: {content[:200]}..."
            )

        try:
            return schema.model_validate(data)
        except ValidationError as e:
            raise ClaudeParseError(
                f"Response JSON does not match schema {schema.__name__}: {e}"
            )

    async def _execute_with_retry(
        self,
        request_params: Dict[str, Any],
    ) -> ClaudeResponse:
        """Execute API request with retry logic.

        Args:
            request_params: Parameters for messages.create

        Returns:
            ClaudeResponse with content and metadata

        Raises:
            ClaudeAPIError: For non-retryable errors
            ClaudeRateLimitError: If rate limit exceeded after retries
            ClaudeTimeoutError: If request times out after retries
        """
        import anthropic

        last_error = None
        delay = self._config.retry_delay_seconds

        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._client.messages.create(**request_params)

                # Extract content
                content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        content += block.text

                return ClaudeResponse(
                    content=content,
                    model=response.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    stop_reason=response.stop_reason,
                )

            except anthropic.RateLimitError as e:
                last_error = ClaudeRateLimitError(
                    f"Rate limit exceeded: {e}",
                    retry_after_seconds=delay,
                )
                if attempt < self._config.max_retries:
                    logger.warning(
                        f"Rate limited, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self._config.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff

            except anthropic.APITimeoutError as e:
                last_error = ClaudeTimeoutError(f"Request timed out: {e}")
                if attempt < self._config.max_retries:
                    logger.warning(
                        f"Timeout, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self._config.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2

            except anthropic.APIConnectionError as e:
                last_error = ClaudeAPIError(f"Connection error: {e}")
                if attempt < self._config.max_retries:
                    logger.warning(
                        f"Connection error, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self._config.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2

            except anthropic.BadRequestError as e:
                # Non-retryable error
                raise ClaudeAPIError(f"Bad request: {e}", status_code=400)

            except anthropic.AuthenticationError as e:
                # Non-retryable error
                raise ClaudeAPIError(f"Authentication failed: {e}", status_code=401)

            except anthropic.PermissionDeniedError as e:
                # Non-retryable error
                raise ClaudeAPIError(f"Permission denied: {e}", status_code=403)

            except anthropic.NotFoundError as e:
                # Non-retryable error
                raise ClaudeAPIError(f"Resource not found: {e}", status_code=404)

            except anthropic.APIStatusError as e:
                # Other API error - may be retryable for 5xx
                if e.status_code >= 500 and attempt < self._config.max_retries:
                    logger.warning(
                        f"Server error {e.status_code}, retrying in {delay}s "
                        f"(attempt {attempt + 1}/{self._config.max_retries + 1})"
                    )
                    last_error = ClaudeAPIError(str(e), status_code=e.status_code)
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise ClaudeAPIError(str(e), status_code=e.status_code)

        # All retries exhausted
        if last_error:
            raise last_error
        raise ClaudeAPIError("Unknown error occurred")


# Global service instance
_claude_client: Optional[ClaudeClient] = None


def get_claude_client() -> ClaudeClient:
    """Get the global Claude client instance."""
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient()
    return _claude_client


def set_claude_client(client: Optional[ClaudeClient]) -> None:
    """Set the global Claude client instance."""
    global _claude_client
    _claude_client = client
