"""Claude API Client Service.

Uses the Claude Code CLI (`claude -p`) for API calls, leveraging the
platform's existing OAuth credential infrastructure. The CLI inherits
CLAUDE_CODE_OAUTH_TOKEN from the process environment, set by
ClaudeAuthService at startup.
"""

import asyncio
import json
import logging
import os
import shutil
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
    """Client for interacting with Claude via the Claude Code CLI.

    Uses `claude -p` (print mode) which reads from stdin and writes
    the response to stdout. Inherits OAuth credentials from the
    process environment (CLAUDE_CODE_OAUTH_TOKEN).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[ClaudeConfig] = None,
    ):
        self._config = config or ClaudeConfig()
        self._claude_path = self._find_claude_cli()
        if not self._claude_path:
            raise RuntimeError(
                "Claude Code CLI not found. Ensure 'claude' is installed and on PATH."
            )
        logger.info(f"ClaudeClient initialized (CLI: {self._claude_path})")

    @staticmethod
    def _find_claude_cli() -> Optional[str]:
        """Find the claude CLI binary."""
        # Check common locations
        path = shutil.which("claude")
        if path:
            return path
        for candidate in ["/usr/local/bin/claude", "/usr/bin/claude", "/app/.npm-global/bin/claude"]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        messages: Optional[List[ClaudeMessage]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> ClaudeResponse:
        """Complete a prompt using Claude Code CLI.

        Args:
            prompt: The user prompt
            system: Optional system prompt
            messages: Optional conversation history (prepended to prompt)
            max_tokens: Max output tokens
            temperature: Not directly supported by CLI (ignored)
            model: Model to use (passed via --model)

        Returns:
            ClaudeResponse with content and metadata
        """
        selected_model = model or self._config.model

        # Build CLI command
        cmd = [
            self._claude_path, "-p",
            "--output-format", "json",
            "--no-session-persistence",
        ]
        if selected_model:
            cmd.extend(["--model", selected_model])
        if system:
            cmd.extend(["--system-prompt", system])

        # Build the full prompt with context
        full_prompt = ""
        if messages:
            for m in messages:
                full_prompt += f"[{m.role}]: {m.content}\n\n"
        full_prompt += prompt

        logger.info(
            f"Claude CLI call: model={selected_model}, "
            f"cmd_args={len(cmd)}, prompt_len={len(full_prompt)}, "
            f"system_len={len(system) if system else 0}"
        )

        return await self._execute_cli(cmd, full_prompt, selected_model)

    async def complete_json(
        self,
        prompt: str,
        schema: Type[T],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> T:
        """Complete a prompt and parse response as a Pydantic model."""
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
        """Parse response content as JSON into a Pydantic model."""
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

        json_str = json_str.strip()
        if not json_str.startswith("{") and not json_str.startswith("["):
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

    async def _execute_cli(
        self,
        cmd: List[str],
        prompt: str,
        model: str,
    ) -> ClaudeResponse:
        """Execute Claude CLI and parse the response."""
        timeout = self._config.timeout_seconds

        has_token = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
        logger.info(
            f"Claude CLI exec: model={model}, prompt_len={len(prompt)}, "
            f"has_oauth_token={has_token}"
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt.encode()),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            process.kill()
            raise ClaudeTimeoutError(
                f"Claude CLI timed out after {timeout}s"
            )
        except FileNotFoundError:
            raise ClaudeAPIError(
                f"Claude CLI not found at {self._claude_path}"
            )

        raw_output = stdout.decode().strip()
        stderr_text = stderr.decode().strip() if stderr else ""

        if not raw_output:
            raise ClaudeAPIError(
                f"Claude CLI returned empty output. stderr: {stderr_text}"
            )

        # Parse JSON output (claude -p --output-format json always writes JSON to stdout)
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError:
            if process.returncode != 0:
                raise ClaudeAPIError(
                    f"Claude CLI failed (exit {process.returncode}): {raw_output[:300]}"
                )
            return ClaudeResponse(
                content=raw_output,
                model=model or "unknown",
                input_tokens=0,
                output_tokens=0,
                stop_reason="end_turn",
            )

        # Check for CLI-level errors (e.g. "Not logged in")
        if data.get("is_error"):
            error_msg = data.get("result", "unknown CLI error")
            raise ClaudeAPIError(f"Claude CLI error: {error_msg}")

        content = data.get("result", "")
        usage = data.get("usage", {})
        return ClaudeResponse(
            content=content,
            model=model or "unknown",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            stop_reason=data.get("stop_reason", "end_turn"),
        )


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
