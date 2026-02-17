# LLM Integration Guide

## Overview

ClaudeVN uses a flexible LLM provider abstraction that allows agents to work with multiple LLM providers. Each agent can be configured with one or more LLM providers with automatic fallback support.

## Architecture

### Provider Abstraction Layer

All LLM providers implement the `BaseLLMProvider` interface:

```python
class BaseLLMProvider(ABC):
    async def generate(self, prompt: str, **kwargs) -> LLMResponse
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]
    def estimate_tokens(self, text: str) -> int
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float
```

### Supported Providers

| Provider | Status | Models | Streaming |
|----------|--------|--------|-----------|
| OpenAI | ✅ Implemented | GPT-4, GPT-3.5-turbo | ✅ Yes |
| Anthropic | 🚧 Phase 2 | Claude 3 | 🚧 Planned |
| Ollama | 🚧 Phase 3 | Local models | 🚧 Planned |

## Configuration

### Agent LLM Configuration

Agents are configured with one or more LLM providers in their configuration:

```json
{
  "agents": {
    "GoalDecomposerAgent": {
      "enabled": true,
      "llm_providers": [
        {
          "provider": "openai",
          "model": "gpt-4",
          "temperature": 0.7,
          "max_tokens": 2000,
          "priority": 1
        },
        {
          "provider": "anthropic",
          "model": "claude-3-sonnet",
          "temperature": 0.7,
          "priority": 2
        }
      ],
      "fallback_strategy": "next_priority",
      "max_retries": 3,
      "retry_delay": 1.0
    }
  }
}
```

### Configuration Parameters

**Per-Provider Parameters:**
- `provider` (required): Provider name ("openai", "anthropic", "ollama")
- `model` (required): Model identifier (e.g., "gpt-4", "claude-3-sonnet")
- `temperature` (default: 0.7): Sampling temperature (0.0-2.0)
- `max_tokens` (optional): Maximum tokens in completion
- `top_p` (optional): Nucleus sampling parameter
- `frequency_penalty` (optional): Frequency penalty (-2.0 to 2.0)
- `presence_penalty` (optional): Presence penalty (-2.0 to 2.0)
- `stop_sequences` (optional): List of stop sequences
- `priority` (default: 1): Provider priority (lower = higher priority)
- `timeout` (default: 60): Request timeout in seconds

**Agent-Level Parameters:**
- `fallback_strategy`: "next_priority" (try next provider on failure)
- `max_retries`: Maximum retry attempts per provider (default: 3)
- `retry_delay`: Initial delay between retries in seconds (default: 1.0)

### Environment Variables

API keys are provided via environment variables:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic (Phase 2)
ANTHROPIC_API_KEY=sk-ant-...

# Ollama (Phase 3) - typically no API key needed for local
OLLAMA_BASE_URL=http://localhost:11434
```

## Usage

### Basic Usage in Agents

```python
from compute.runtime.llm_client import create_llm_client_from_config

class MyAgent(BaseAgent):
    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        
        # Create LLM client from config
        self.llm = create_llm_client_from_config(
            agent_config=config,
            api_keys={
                "openai": os.getenv("OPENAI_API_KEY"),
                "anthropic": os.getenv("ANTHROPIC_API_KEY")
            }
        )
    
    async def execute(self, task_input, context):
        prompt = self.build_prompt(task_input)
        
        # Generate completion with automatic fallback
        response = await self.llm.generate(prompt)
        
        return {
            "result": response.content,
            "tokens_used": response.tokens_used,
            "cost": response.cost_estimate
        }
```

### Streaming Responses

```python
async def execute_with_streaming(self, task_input, context):
    prompt = self.build_prompt(task_input)
    
    # Stream tokens as they're generated
    full_response = ""
    async for chunk in self.llm.stream(prompt):
        full_response += chunk
        # Optionally send progress updates
        await self.send_progress_update(chunk)
    
    return {"result": full_response}
```

### Token Estimation

```python
# Estimate tokens before making request
prompt = "Analyze this data..."
estimated_tokens = self.llm.estimate_tokens(prompt)

if estimated_tokens > 4000:
    # Prompt is too long, truncate or split
    prompt = self.truncate_prompt(prompt, max_tokens=4000)
```

### Usage Statistics

```python
# Get usage stats for all providers
stats = self.llm.get_usage_stats()

for provider_name, stats in stats.items():
    print(f"{provider_name}:")
    print(f"  Total requests: {stats.total_requests}")
    print(f"  Total tokens: {stats.total_tokens}")
    print(f"  Total cost: ${stats.total_cost:.4f}")
    print(f"  Failed requests: {stats.failed_requests}")

# Reset stats
self.llm.reset_stats()
```

## Fallback Behavior

When a provider fails, the LLM client automatically tries the next provider based on priority:

1. **Primary Provider Fails** → Try with exponential backoff (up to `max_retries`)
2. **All Retries Exhausted** → Move to next provider by priority
3. **All Providers Fail** → Raise `LLMProviderError`

### Retryable Errors

The following errors trigger automatic retry:
- Rate limit errors (429)
- Server errors (500, 502, 503, 504)
- Timeout errors

### Non-Retryable Errors

The following errors fail immediately:
- Authentication errors (401)
- Invalid request errors (400)
- Model not found errors (404)

## Cost Management

### Cost Estimation

Each LLM response includes a cost estimate based on current pricing:

```python
response = await self.llm.generate(prompt)
print(f"Estimated cost: ${response.cost_estimate:.4f}")
```

### OpenAI Pricing (as of Nov 2024)

| Model | Prompt (per 1K tokens) | Completion (per 1K tokens) |
|-------|------------------------|----------------------------|
| GPT-4 | $0.03 | $0.06 |
| GPT-4 Turbo | $0.01 | $0.03 |
| GPT-3.5 Turbo | $0.0005 | $0.0015 |

### Tracking Costs

```python
# Track costs per session
session_cost = 0.0

for task in execution_plan.tasks:
    response = await agent.execute(task)
    session_cost += response.cost_estimate

print(f"Total session cost: ${session_cost:.4f}")
```

## Adding New Providers

### Step 1: Implement Provider Class

Create a new provider in `compute/runtime/providers/`:

```python
from .base import BaseLLMProvider
from claudevn_shared.llm_types import LLMConfig, LLMResponse, LLMProvider

class MyProvider(BaseLLMProvider):
    def __init__(self, config: LLMConfig, api_key: Optional[str] = None):
        super().__init__(config)
        # Initialize your provider client
        self.client = MyProviderClient(api_key=api_key)
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # Implement generation logic
        pass
    
    def estimate_tokens(self, text: str) -> int:
        # Implement token estimation
        pass
    
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        # Implement cost estimation
        pass
```

### Step 2: Register Provider

Add to `compute/runtime/llm_client.py`:

```python
def _create_provider(self, config: LLMConfig) -> BaseLLMProvider:
    if config.provider == LLMProvider.MY_PROVIDER:
        return MyProvider(config, api_key=api_key)
    # ... existing providers
```

### Step 3: Add to Enum

Add to `shared/claudevn_shared/llm_types.py`:

```python
class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MY_PROVIDER = "my_provider"
```

### Step 4: Update Documentation

Document pricing, models, and configuration options.

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("compute.runtime.llm_client")
logger.setLevel(logging.DEBUG)
```

### Log Prompts and Responses

```python
# In agent code
logger.debug(f"Prompt: {prompt}")
response = await self.llm.generate(prompt)
logger.debug(f"Response: {response.content}")
logger.debug(f"Tokens: {response.tokens_used}, Cost: ${response.cost_estimate:.4f}")
```

### Test Provider Connectivity

```python
from compute.runtime.providers import OpenAIProvider
from claudevn_shared.llm_types import LLMConfig, LLMProvider

# Test OpenAI connectivity
config = LLMConfig(
    provider=LLMProvider.OPENAI,
    model="gpt-3.5-turbo",
    temperature=0.7
)

provider = OpenAIProvider(config, api_key="your-key")
response = await provider.generate("Hello, world!")
print(response.content)
```

## Best Practices

### 1. Use Appropriate Models

- **GPT-4**: Complex reasoning, planning, analysis
- **GPT-3.5 Turbo**: Simple tasks, fast responses, lower cost
- **Claude**: Long context, detailed analysis

### 2. Configure Fallbacks

Always configure at least one fallback provider:

```json
{
  "llm_providers": [
    {"provider": "openai", "model": "gpt-4", "priority": 1},
    {"provider": "openai", "model": "gpt-3.5-turbo", "priority": 2}
  ]
}
```

### 3. Set Reasonable Timeouts

Adjust timeouts based on expected response time:

```json
{
  "provider": "openai",
  "model": "gpt-4",
  "timeout": 120  // 2 minutes for complex tasks
}
```

### 4. Monitor Token Usage

Track token usage to avoid unexpected costs:

```python
# Before generation
estimated = self.llm.estimate_tokens(prompt)
if estimated > threshold:
    logger.warning(f"Large prompt: {estimated} tokens")

# After generation
if response.tokens_used > 4000:
    logger.warning(f"Large response: {response.tokens_used} tokens")
```

### 5. Handle Errors Gracefully

```python
try:
    response = await self.llm.generate(prompt)
except LLMProviderError as e:
    logger.error(f"LLM generation failed: {e}")
    # Return fallback response or raise to caller
    return {"error": "LLM service unavailable"}
```

## Troubleshooting

### "openai package not installed"

```bash
pip install openai tiktoken
```

### "Authentication failed"

Check that `OPENAI_API_KEY` is set:

```bash
echo $OPENAI_API_KEY
```

### "Rate limit exceeded"

Configure retry with longer delays:

```json
{
  "max_retries": 5,
  "retry_delay": 2.0
}
```

### "Request timeout"

Increase timeout or use streaming:

```json
{
  "timeout": 120
}
```

## Future Enhancements

- [ ] Prompt caching to reduce costs
- [ ] Response caching for identical prompts
- [ ] Batch request support
- [ ] Fine-tuned model support
- [ ] Custom model endpoints
- [ ] Token budget enforcement per session
- [ ] Cost alerts and limits

