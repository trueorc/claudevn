# Tool Execution Quick Reference

## Creating a New Python Tool

### 1. Create Tool Definition (JSON)

**File**: `compute/tools/my_tool.json`

```json
{
  "tool_id": "my_tool",
  "name": "My Tool Name",
  "description": "What this tool does",
  "function_name": "my_function",
  "parameters": {
    "type": "object",
    "properties": {
      "param1": {
        "type": "string",
        "description": "First parameter"
      },
      "param2": {
        "type": "number",
        "description": "Second parameter"
      }
    },
    "required": ["param1", "param2"]
  },
  "metadata": {
    "tool_type": "python",
    "module": "tool_functions.my_module",
    "version": "1.0.0"
  }
}
```

### 2. Create Tool Implementation (Python)

**File**: `compute/tool_functions/my_module.py`

```python
"""My tool implementation."""

def my_function(param1: str, param2: float) -> dict:
    """
    Tool function implementation.
    
    Args:
        param1: First parameter
        param2: Second parameter
        
    Returns:
        Result dictionary
    """
    # Your implementation here
    result = f"Processed {param1} with {param2}"
    
    return {
        "status": "success",
        "result": result,
        "input": {
            "param1": param1,
            "param2": param2
        }
    }
```

### 3. Test Your Tool

```python
from services.tool_registry import ToolRegistry
from services.tool_executor import ToolExecutor

# Initialize
tool_registry = ToolRegistry(tools_dir="./tools")
tool_registry.load_tools_from_directory()

tool_executor = ToolExecutor(
    tool_registry=tool_registry,
    tools_module_path="./tool_functions"
)

# Execute
result = await tool_executor.execute_tool(
    tool_id="my_tool",
    parameters={
        "param1": "test",
        "param2": 123.45
    }
)

print(result)
```

## Using Tools via API

### Execute Single Tool

```bash
curl -X POST http://localhost:8001/api/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "calculator",
    "parameters": {
      "operation": "add",
      "a": 10,
      "b": 5
    }
  }'
```

### Execute Multiple Tools

```bash
curl -X POST http://localhost:8001/api/v1/tools/execute/multiple \
  -H "Content-Type: application/json" \
  -d '{
    "tool_calls": [
      {
        "tool_id": "calculator",
        "parameters": {"operation": "add", "a": 5, "b": 3}
      },
      {
        "tool_id": "text_analyzer",
        "parameters": {"text": "Hello world!"}
      }
    ]
  }'
```

### Validate Parameters

```bash
curl -X POST http://localhost:8001/api/v1/tools/calculator/validate \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "add",
    "a": 10,
    "b": 5
  }'
```

## Using Tools in Agent Execution

### Execute Agent with Tool Access

```python
from services.agent_executor import AgentExecutor

result = await agent_executor.execute_agent(
    agent_id="my-agent",
    task_input={
        "prompt": "Calculate 10 + 5",
        "tools_enabled": True
    },
    session_id="session-123"
)

# Agent can request tool execution
tool_result = await agent_executor.execute_tool_for_agent(
    tool_id="calculator",
    parameters={"operation": "add", "a": 10, "b": 5},
    task_id=result['task_id'],
    session_id="session-123",
    agent_id="my-agent"
)
```

### Get Available Tools for Agent

```python
# Get all tools available to agent
tools = await agent_executor.get_available_tools_for_agent(
    agent_id="my-agent"
)

for tool in tools:
    print(f"{tool['tool_id']}: {tool['name']}")
    print(f"  {tool['description']}")
```

## Tool Types

### Python Function Tools

**Characteristics**:
- Executed in-process
- Fast (1-10ms typical)
- Full Python language support
- Access to compute environment

**Use cases**:
- Mathematical operations
- Text processing
- Data transformations
- File operations (within compute)

### MCP Service Tools

**Characteristics**:
- External HTTP services
- Network latency (50-500ms)
- Standardized protocol
- Scalable/distributed

**Use cases**:
- External API calls
- Database queries
- Third-party integrations
- Resource-intensive operations

## Error Handling

### Tool Not Found
```json
{
  "detail": "Tool not found: unknown_tool"
}
```

### Missing Required Parameter
```json
{
  "valid": false,
  "tool_id": "calculator",
  "error": "Missing required parameter: b"
}
```

### Execution Error
```json
{
  "detail": "Tool execution failed: Cannot divide by zero"
}
```

## Observability Events

Tool execution emits events:

### tool_execution_started
```json
{
  "event_type": "tool_execution_started",
  "session_id": "session-123",
  "task_id": "task-456",
  "agent_id": "my-agent",
  "tool_id": "calculator",
  "tool_name": "Calculator",
  "timestamp": "2025-01-XX..."
}
```

### tool_execution_completed
```json
{
  "event_type": "tool_execution_completed",
  "session_id": "session-123",
  "task_id": "task-456",
  "agent_id": "my-agent",
  "tool_id": "calculator",
  "tool_name": "Calculator",
  "duration_seconds": 0.005,
  "success": true,
  "timestamp": "2025-01-XX..."
}
```

## Best Practices

### Tool Design
1. **Single Responsibility**: One tool, one purpose
2. **Clear Parameters**: Well-defined, typed parameters
3. **Good Descriptions**: Help LLMs choose the right tool
4. **Error Handling**: Return meaningful errors
5. **Idempotency**: Same input → same output

### Performance
1. **Keep Tools Fast**: Target <100ms for Python tools
2. **Use Caching**: Cache expensive operations
3. **Async When Possible**: Use async/await for I/O
4. **Validate Early**: Validate parameters before heavy work

### Security
1. **Validate Input**: Don't trust tool parameters
2. **Limit Resources**: Set timeouts and memory limits
3. **Sandboxing**: Isolate untrusted code
4. **Access Control**: Restrict tools per agent/user

### Testing
1. **Unit Tests**: Test each tool function
2. **Integration Tests**: Test with ToolExecutor
3. **Error Cases**: Test validation and error handling
4. **Performance Tests**: Measure execution time

## Example: Advanced Tool

### Weather Tool (MCP Service)

**Definition** (`tools/weather.json`):
```json
{
  "tool_id": "weather",
  "name": "Weather Service",
  "description": "Get current weather for a location",
  "function_name": "get_weather",
  "parameters": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "City name or ZIP code"
      },
      "units": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "default": "fahrenheit"
      }
    },
    "required": ["location"]
  },
  "metadata": {
    "tool_type": "mcp",
    "implementation": {
      "service_url": "https://api.weather.com",
      "endpoint": "/v1/current",
      "auth_required": true
    },
    "version": "1.0.0"
  }
}
```

## Troubleshooting

### Tool Not Loading
- Check JSON syntax
- Verify `tools_dir` path
- Ensure file has `.json` extension
- Check logs for import errors

### Function Not Found
- Verify `module` path in metadata
- Check `function_name` matches actual function
- Ensure module is in `tools_module_path`
- Check for import errors in logs

### Parameter Validation Failing
- Match parameter names exactly
- Use correct types (string, number, boolean, etc.)
- Include all required parameters
- Check parameter schema syntax

### Execution Timeout
- Increase timeout in executor configuration
- Optimize tool function
- Consider async execution
- Use background processing for long tasks

## Additional Resources

- Phase 5 Documentation: `docs/development/PHASE_5_TOOL_EXECUTION.md`
- Complete Implementation: `docs/development/COMPUTE_MODULE_COMPLETE.md`
- Tool Executor Source: `compute/services/tool_executor.py`
- Example Tools: `compute/tools/` and `compute/tool_functions/`
