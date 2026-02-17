"""Tests for ClaudeClient - Claude API client service."""

import json
import pytest
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import BaseModel

from models.claude_client import (
    ClaudeConfig,
    ClaudeMessage,
    ClaudeModel,
    ClaudeResponse,
    ClaudeAPIError,
    ClaudeRateLimitError,
    ClaudeTimeoutError,
    ClaudeParseError,
)
from services.claude_client import (
    ClaudeClient,
    get_claude_client,
    set_claude_client,
)


# ============================================================================
# Pydantic Models for JSON Parsing Tests
# ============================================================================


class SampleIssue(BaseModel):
    """Sample model for JSON parsing tests."""
    temp_id: str
    title: str
    description: str
    priority: str = "P2"


class SampleDecomposition(BaseModel):
    """Sample model for complex JSON parsing."""
    issues: List[SampleIssue]
    confidence: float
    reasoning: str


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_anthropic_module():
    """Create a mock anthropic module."""
    mock_module = MagicMock()

    # Mock exception classes
    mock_module.RateLimitError = type("RateLimitError", (Exception,), {})
    mock_module.APITimeoutError = type("APITimeoutError", (Exception,), {})
    mock_module.APIConnectionError = type("APIConnectionError", (Exception,), {})
    mock_module.BadRequestError = type("BadRequestError", (Exception,), {})
    mock_module.AuthenticationError = type("AuthenticationError", (Exception,), {})
    mock_module.PermissionDeniedError = type("PermissionDeniedError", (Exception,), {})
    mock_module.NotFoundError = type("NotFoundError", (Exception,), {})
    mock_module.APIStatusError = type(
        "APIStatusError",
        (Exception,),
        {"__init__": lambda self, msg, status_code: setattr(self, "status_code", status_code) or Exception.__init__(self, msg)},
    )

    return mock_module


@pytest.fixture
def mock_anthropic_client():
    """Create a mock AsyncAnthropic client."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock()
    return client


@pytest.fixture
def sample_response():
    """Create a sample API response."""
    response = MagicMock()
    response.content = [MagicMock(text="Hello, world!")]
    response.model = "claude-sonnet-4-20250514"
    response.usage = MagicMock(input_tokens=10, output_tokens=5)
    response.stop_reason = "end_turn"
    return response


@pytest.fixture
def sample_json_response():
    """Create a sample JSON API response."""
    json_content = json.dumps({
        "issues": [
            {
                "temp_id": "issue-1",
                "title": "Test Issue",
                "description": "Test description",
                "priority": "P1"
            }
        ],
        "confidence": 0.85,
        "reasoning": "Test reasoning"
    })
    response = MagicMock()
    response.content = [MagicMock(text=json_content)]
    response.model = "claude-sonnet-4-20250514"
    response.usage = MagicMock(input_tokens=50, output_tokens=100)
    response.stop_reason = "end_turn"
    return response


# ============================================================================
# Model Tests - ClaudeConfig
# ============================================================================


class TestClaudeConfigModel:
    """Test ClaudeConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ClaudeConfig()

        assert config.model == ClaudeModel.SONNET_4.value
        assert config.max_tokens == 4096
        assert config.temperature == 0.3
        assert config.timeout_seconds == 60
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 1.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ClaudeConfig(
            model="claude-opus-4-20250514",
            max_tokens=8192,
            temperature=0.7,
            timeout_seconds=120,
            max_retries=5,
            retry_delay_seconds=2.0,
        )

        assert config.model == "claude-opus-4-20250514"
        assert config.max_tokens == 8192
        assert config.temperature == 0.7
        assert config.timeout_seconds == 120
        assert config.max_retries == 5
        assert config.retry_delay_seconds == 2.0

    def test_temperature_validation(self):
        """Test temperature must be between 0 and 1."""
        # Valid edge cases
        config = ClaudeConfig(temperature=0.0)
        assert config.temperature == 0.0

        config = ClaudeConfig(temperature=1.0)
        assert config.temperature == 1.0

        # Invalid values
        with pytest.raises(ValueError):
            ClaudeConfig(temperature=-0.1)

        with pytest.raises(ValueError):
            ClaudeConfig(temperature=1.1)


# ============================================================================
# Model Tests - ClaudeMessage
# ============================================================================


class TestClaudeMessageModel:
    """Test ClaudeMessage model."""

    def test_create_message(self):
        """Test creating a message."""
        message = ClaudeMessage(role="user", content="Hello")

        assert message.role == "user"
        assert message.content == "Hello"

    def test_assistant_message(self):
        """Test creating an assistant message."""
        message = ClaudeMessage(role="assistant", content="Hi there!")

        assert message.role == "assistant"
        assert message.content == "Hi there!"


# ============================================================================
# Model Tests - ClaudeResponse
# ============================================================================


class TestClaudeResponseModel:
    """Test ClaudeResponse model."""

    def test_create_response(self):
        """Test creating a response."""
        response = ClaudeResponse(
            content="Hello!",
            model="claude-sonnet-4-20250514",
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
        )

        assert response.content == "Hello!"
        assert response.model == "claude-sonnet-4-20250514"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.stop_reason == "end_turn"
        assert response.created_at is not None

    def test_response_defaults(self):
        """Test response default values."""
        response = ClaudeResponse(
            content="Hello!",
            model="claude-sonnet-4-20250514",
        )

        assert response.input_tokens == 0
        assert response.output_tokens == 0
        assert response.stop_reason is None


# ============================================================================
# Model Tests - Error Classes
# ============================================================================


class TestErrorModels:
    """Test error class models."""

    def test_claude_api_error(self):
        """Test ClaudeAPIError."""
        error = ClaudeAPIError("Bad request", status_code=400)

        assert error.message == "Bad request"
        assert error.status_code == 400
        assert str(error) == "Bad request"

    def test_claude_rate_limit_error(self):
        """Test ClaudeRateLimitError."""
        error = ClaudeRateLimitError(
            "Rate limit exceeded",
            retry_after_seconds=30.0,
        )

        assert error.message == "Rate limit exceeded"
        assert error.status_code == 429
        assert error.retry_after_seconds == 30.0

    def test_claude_timeout_error(self):
        """Test ClaudeTimeoutError."""
        error = ClaudeTimeoutError("Request timed out")

        assert error.message == "Request timed out"
        assert error.status_code is None

    def test_claude_parse_error(self):
        """Test ClaudeParseError."""
        error = ClaudeParseError("Invalid JSON")

        assert error.message == "Invalid JSON"


# ============================================================================
# Service Tests - Initialization
# ============================================================================


class TestClaudeClientInit:
    """Test ClaudeClient initialization."""

    def test_init_with_api_key(self, mock_anthropic_module):
        """Test initialization with explicit API key."""
        with patch.dict("os.environ", {}, clear=True):
            client = ClaudeClient(api_key="test-api-key")

            assert client._api_key == "test-api-key"
            assert client._config is not None
            assert client._initialized is False

    def test_init_with_env_api_key(self, mock_anthropic_module):
        """Test initialization with environment variable."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-api-key"}):
            client = ClaudeClient()

            assert client._api_key == "env-api-key"

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                ClaudeClient()

            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_init_with_custom_config(self):
        """Test initialization with custom config."""
        config = ClaudeConfig(temperature=0.7, max_retries=5)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient(config=config)

            assert client._config.temperature == 0.7
            assert client._config.max_retries == 5


# ============================================================================
# Service Tests - Complete Method
# ============================================================================


class TestClaudeClientComplete:
    """Test ClaudeClient.complete method."""

    @pytest.mark.asyncio
    async def test_complete_simple(
        self,
        mock_anthropic_client,
        sample_response,
    ):
        """Test simple completion."""
        mock_anthropic_client.messages.create.return_value = sample_response

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            response = await client.complete(prompt="Hello!")

            assert isinstance(response, ClaudeResponse)
            assert response.content == "Hello, world!"
            assert response.model == "claude-sonnet-4-20250514"
            assert response.input_tokens == 10
            assert response.output_tokens == 5

    @pytest.mark.asyncio
    async def test_complete_with_system_prompt(
        self,
        mock_anthropic_client,
        sample_response,
    ):
        """Test completion with system prompt."""
        mock_anthropic_client.messages.create.return_value = sample_response

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            await client.complete(
                prompt="Hello!",
                system="You are a helpful assistant.",
            )

            # Verify system prompt was passed
            call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
            assert call_kwargs["system"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_complete_with_messages(
        self,
        mock_anthropic_client,
        sample_response,
    ):
        """Test completion with conversation history."""
        mock_anthropic_client.messages.create.return_value = sample_response

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            messages = [
                ClaudeMessage(role="user", content="Hi"),
                ClaudeMessage(role="assistant", content="Hello!"),
            ]

            await client.complete(
                prompt="How are you?",
                messages=messages,
            )

            # Verify messages were passed correctly
            call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
            assert len(call_kwargs["messages"]) == 3
            assert call_kwargs["messages"][0]["content"] == "Hi"
            assert call_kwargs["messages"][1]["content"] == "Hello!"
            assert call_kwargs["messages"][2]["content"] == "How are you?"

    @pytest.mark.asyncio
    async def test_complete_with_parameter_overrides(
        self,
        mock_anthropic_client,
        sample_response,
    ):
        """Test completion with parameter overrides."""
        mock_anthropic_client.messages.create.return_value = sample_response

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            config = ClaudeConfig(max_tokens=1000, temperature=0.5)
            client = ClaudeClient(config=config)
            client._client = mock_anthropic_client
            client._initialized = True

            await client.complete(
                prompt="Hello!",
                max_tokens=2000,
                temperature=0.9,
                model="claude-opus-4-20250514",
            )

            call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
            assert call_kwargs["max_tokens"] == 2000
            assert call_kwargs["temperature"] == 0.9
            assert call_kwargs["model"] == "claude-opus-4-20250514"


# ============================================================================
# Service Tests - Complete JSON Method
# ============================================================================


class TestClaudeClientCompleteJson:
    """Test ClaudeClient.complete_json method."""

    @pytest.mark.asyncio
    async def test_complete_json_simple(
        self,
        mock_anthropic_client,
        sample_json_response,
    ):
        """Test JSON completion with simple model."""
        mock_anthropic_client.messages.create.return_value = sample_json_response

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            result = await client.complete_json(
                prompt="Create an issue",
                schema=SampleDecomposition,
            )

            assert isinstance(result, SampleDecomposition)
            assert len(result.issues) == 1
            assert result.issues[0].title == "Test Issue"
            assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_complete_json_adds_instruction(
        self,
        mock_anthropic_client,
        sample_json_response,
    ):
        """Test that JSON completion adds JSON instruction to system."""
        mock_anthropic_client.messages.create.return_value = sample_json_response

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            await client.complete_json(
                prompt="Create an issue",
                schema=SampleDecomposition,
                system="You are an architect.",
            )

            call_kwargs = mock_anthropic_client.messages.create.call_args.kwargs
            system = call_kwargs["system"]
            assert "You are an architect." in system
            assert "valid JSON" in system


# ============================================================================
# Service Tests - JSON Parsing
# ============================================================================


class TestJsonParsing:
    """Test JSON parsing functionality."""

    def test_parse_json_clean(self):
        """Test parsing clean JSON."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()

            content = json.dumps({
                "issues": [{"temp_id": "1", "title": "Test", "description": "Desc"}],
                "confidence": 0.9,
                "reasoning": "Test",
            })

            result = client._parse_json_response(content, SampleDecomposition)

            assert isinstance(result, SampleDecomposition)
            assert result.confidence == 0.9

    def test_parse_json_with_markdown(self):
        """Test parsing JSON wrapped in markdown code block."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()

            content = """```json
{
    "issues": [{"temp_id": "1", "title": "Test", "description": "Desc"}],
    "confidence": 0.9,
    "reasoning": "Test"
}
```"""

            result = client._parse_json_response(content, SampleDecomposition)

            assert isinstance(result, SampleDecomposition)
            assert result.confidence == 0.9

    def test_parse_json_with_prefix_text(self):
        """Test parsing JSON with text before it."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()

            content = """Here is the decomposition:

{
    "issues": [{"temp_id": "1", "title": "Test", "description": "Desc"}],
    "confidence": 0.9,
    "reasoning": "Test"
}"""

            result = client._parse_json_response(content, SampleDecomposition)

            assert isinstance(result, SampleDecomposition)

    def test_parse_json_invalid(self):
        """Test parsing invalid JSON raises error."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()

            content = "This is not JSON"

            with pytest.raises(ClaudeParseError) as exc_info:
                client._parse_json_response(content, SampleDecomposition)

            assert "Failed to parse" in str(exc_info.value)

    def test_parse_json_validation_error(self):
        """Test parsing JSON that doesn't match schema."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()

            # Missing required fields
            content = json.dumps({"confidence": 0.9})

            with pytest.raises(ClaudeParseError) as exc_info:
                client._parse_json_response(content, SampleDecomposition)

            assert "does not match schema" in str(exc_info.value)


# ============================================================================
# Service Tests - Retry Logic
# ============================================================================


class TestRetryLogic:
    """Test retry logic for transient failures."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, mock_anthropic_client, sample_response):
        """Test retry on rate limit error."""
        import anthropic

        # First call raises rate limit, second succeeds
        mock_anthropic_client.messages.create.side_effect = [
            anthropic.RateLimitError(
                message="Rate limited",
                response=MagicMock(status_code=429),
                body=None,
            ),
            sample_response,
        ]

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            config = ClaudeConfig(retry_delay_seconds=0.1)  # Fast retry for test
            client = ClaudeClient(config=config)
            client._client = mock_anthropic_client
            client._initialized = True

            response = await client.complete(prompt="Hello!")

            assert response.content == "Hello, world!"
            assert mock_anthropic_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, mock_anthropic_client, sample_response):
        """Test retry on timeout error."""
        import anthropic

        mock_anthropic_client.messages.create.side_effect = [
            anthropic.APITimeoutError(request=MagicMock()),
            sample_response,
        ]

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            config = ClaudeConfig(retry_delay_seconds=0.1)
            client = ClaudeClient(config=config)
            client._client = mock_anthropic_client
            client._initialized = True

            response = await client.complete(prompt="Hello!")

            assert response.content == "Hello, world!"

    @pytest.mark.asyncio
    async def test_no_retry_on_bad_request(self, mock_anthropic_client):
        """Test no retry on bad request error."""
        import anthropic

        mock_anthropic_client.messages.create.side_effect = anthropic.BadRequestError(
            message="Invalid request",
            response=MagicMock(status_code=400),
            body=None,
        )

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            with pytest.raises(ClaudeAPIError) as exc_info:
                await client.complete(prompt="Hello!")

            assert exc_info.value.status_code == 400
            assert mock_anthropic_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self, mock_anthropic_client):
        """Test no retry on authentication error."""
        import anthropic

        mock_anthropic_client.messages.create.side_effect = anthropic.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = ClaudeClient()
            client._client = mock_anthropic_client
            client._initialized = True

            with pytest.raises(ClaudeAPIError) as exc_info:
                await client.complete(prompt="Hello!")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, mock_anthropic_client):
        """Test error raised when max retries exhausted."""
        import anthropic

        mock_anthropic_client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            config = ClaudeConfig(max_retries=2, retry_delay_seconds=0.1)
            client = ClaudeClient(config=config)
            client._client = mock_anthropic_client
            client._initialized = True

            with pytest.raises(ClaudeRateLimitError):
                await client.complete(prompt="Hello!")

            # Initial attempt + 2 retries = 3 calls
            assert mock_anthropic_client.messages.create.call_count == 3


# ============================================================================
# Service Tests - Global Instance
# ============================================================================


class TestGlobalInstance:
    """Test global client instance management."""

    def test_get_client_returns_instance(self):
        """Test get_claude_client returns an instance."""
        set_claude_client(None)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client = get_claude_client()

            assert isinstance(client, ClaudeClient)

    def test_set_client_replaces_instance(self):
        """Test set_claude_client replaces the global instance."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            config = ClaudeConfig(temperature=0.9)
            custom_client = ClaudeClient(config=config)

            set_claude_client(custom_client)

            assert get_claude_client() is custom_client

    def test_get_client_returns_same_instance(self):
        """Test get_claude_client returns the same instance."""
        set_claude_client(None)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            client1 = get_claude_client()
            client2 = get_claude_client()

            assert client1 is client2


# ============================================================================
# Model Tests - ClaudeModel Enum
# ============================================================================


class TestClaudeModelEnum:
    """Test ClaudeModel enum."""

    def test_model_values(self):
        """Test model enum values."""
        assert ClaudeModel.SONNET_4.value == "claude-sonnet-4-20250514"
        assert ClaudeModel.OPUS_4.value == "claude-opus-4-20250514"
        assert ClaudeModel.HAIKU_35.value == "claude-3-5-haiku-20241022"
