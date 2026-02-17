# Mock End-to-End Testing Guide

This guide explains how to test ClaudeVN's complete workflow using the **Mock LLM Provider** without hitting any real LLM APIs.

## Overview

The mock end-to-end example demonstrates:

1. **Mock LLM Provider** - Returns realistic responses without API calls or costs
2. **Agent Execution** - Compute instances execute agents with mock responses
3. **Task Routing** - Serving component routes tasks to appropriate compute instances
4. **Business Process Coordination** - Multi-agent workflows orchestrated by serving

## Prerequisites

- All three ClaudeVN services must be running:
  - Marketplace (port 8001)
  - Serving (port 8002) 
  - Compute (port 8003)

## Quick Start

### 1. Start Services

```bash
# From project root
./start_all.sh
```

Wait for all services to start (about 10-15 seconds).

### 2. Run the Test Script

```bash
./test_mock_e2e.sh
```

This script will:
- ✅ Verify all services are running
- ✅ Check compute instance registration
- ✅ List available agents
- ✅ Execute agents directly on compute
- ✅ Route tasks through serving
- ✅ Run a complete multi-agent business process

## What Gets Tested

### Test 1: Service Health Checks
Verifies that all three services are online and responding.

### Test 2: Compute Registration
Confirms that compute instances have registered with the serving component.

### Test 3: Agent Availability
Lists all available agents on compute instances.

### Test 4: Direct Agent Execution
Executes an agent directly on a compute instance:

```bash
curl -X POST http://localhost:8003/agents/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data-analyst-v1",
    "prompt": "Analyze Q4 sales data...",
    "context": {...}
  }'
```

### Test 5: Task Routing
Submits a task to serving, which routes it to a compute instance:

```bash
curl -X POST http://localhost:8002/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "content-writer-v1",
    "prompt": "Write an executive summary..."
  }'
```

### Test 6: Business Process Workflow
Runs a complete 3-step business process:

```bash
curl -X POST http://localhost:8002/api/v1/tasks/demo/business-process
```

This executes:
1. **Task Coordinator** - Plans the workflow
2. **Data Analyst** - Analyzes data and provides insights
3. **Content Writer** - Generates executive report

## Available Mock Agents

The mock environment includes three pre-configured agents:

### 1. Data Analyst Agent (`data-analyst-v1`)
- **Capabilities**: Data analysis, statistical analysis, trend identification
- **Use Case**: Analyze datasets, generate insights, identify patterns
- **Mock Response**: Comprehensive data analysis with statistics and recommendations

### 2. Task Coordinator Agent (`task-coordinator-v1`)
- **Capabilities**: Task planning, decomposition, agent coordination
- **Use Case**: Break down complex goals into steps, plan workflows
- **Mock Response**: Detailed execution plan with phases and required agents

### 3. Content Writer Agent (`content-writer-v1`)
- **Capabilities**: Content generation, report writing, technical writing
- **Use Case**: Create reports, documentation, marketing materials
- **Mock Response**: Professional formatted content tailored to audience

## Mock LLM Provider

The mock provider returns pre-programmed responses based on the prompt content:

### Features
- ✅ **Zero cost** - No API calls, no charges
- ✅ **Fast** - Responses in <1 second
- ✅ **Realistic** - Returns formatted, contextual responses
- ✅ **Predictable** - Same prompts yield consistent results
- ✅ **Offline** - Works without internet connection

### Response Types

The mock provider automatically detects task type from the prompt:

- **Data Analysis** - Keywords: analyze, analysis, data, statistics, trend
- **Content Generation** - Keywords: write, content, report, article
- **Code Review** - Keywords: code, review, refactor, bug
- **Task Planning** - Keywords: plan, steps, strategy, breakdown
- **Default** - Generic helpful response

### Configuration

Agents are configured to use the mock provider in their JSON definitions:

```json
{
  "agent_id": "data-analyst-v1",
  "llm_providers": [
    {
      "provider": "mock",
      "model": "mock-gpt-4",
      "temperature": 0.7,
      "priority": 1
    }
  ]
}
```

## Manual Testing Examples

### Example 1: Simple Agent Execution

Execute the data analyst agent:

```bash
curl -X POST http://localhost:8003/agents/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data-analyst-v1",
    "prompt": "Analyze sales trends for Q4 2024. Focus on regional performance and product categories.",
    "context": {
      "data_file": "sales_q4_2024.csv",
      "total_records": 95,
      "total_revenue": 24127.50
    },
    "output_format": "markdown"
  }' | python3 -m json.tool
```

### Example 2: Task Routing via Serving

Submit a task through the serving component:

```bash
curl -X POST http://localhost:8002/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "content-writer-v1",
    "prompt": "Write a product launch announcement for our new Smart Watch Pro.",
    "context": {
      "audience": "Customers and press",
      "tone": "exciting and professional",
      "length": "300 words"
    }
  }' | python3 -m json.tool
```

### Example 3: Business Process

Run the full demo workflow:

```bash
curl -X POST http://localhost:8002/api/v1/tasks/demo/business-process \
  | python3 -m json.tool
```

This returns:
```json
{
  "process": "Q4 Sales Analysis and Reporting",
  "status": "completed",
  "steps": [
    {
      "step": 1,
      "agent": "task-coordinator-v1",
      "status": "completed",
      "output": {...}
    },
    {
      "step": 2,
      "agent": "data-analyst-v1",
      "status": "completed",
      "output": {...}
    },
    {
      "step": 3,
      "agent": "content-writer-v1",
      "status": "completed",
      "output": {...}
    }
  ],
  "summary": {
    "total_steps": 3,
    "successful_steps": 3,
    "total_agents_used": 3
  }
}
```

## Exploring the Results

### View Agent Output

To see the actual content generated by agents:

```bash
# In the response JSON, look for:
{
  "output": {
    "content": "... the generated text ...",
    "format": "markdown"
  }
}
```

### Check Metadata

Each response includes execution metadata:

```json
{
  "metadata": {
    "started_at": "2024-11-24T10:30:00",
    "completed_at": "2024-11-24T10:30:01",
    "duration_seconds": 0.52,
    "llm_provider": "mock",
    "llm_model": "mock-gpt-4",
    "tokens_used": 456,
    "cost_estimate": 0.0
  }
}
```

### Monitor Logs

Watch real-time execution:

```bash
# All logs
tail -f logs/*.log

# Just serving
tail -f logs/serving.log

# Just compute
tail -f logs/compute.log
```

## Architecture Flow

### Direct Execution (Test 4)
```
User → Compute API → Agent Executor → Mock LLM → Response
```

### Routed Execution (Test 5)
```
User → Serving API → Compute Registry (find instance)
     → Compute API → Agent Executor → Mock LLM → Response
     → User
```

### Business Process (Test 6)
```
User → Serving API → Demo Endpoint
     → Task 1: Coordinator Agent (plan)
     → Task 2: Data Analyst Agent (analyze)
     → Task 3: Content Writer Agent (report)
     → Aggregated Results → User
```

## Switching to Real LLM Providers

To use real LLM providers instead of mock:

### 1. Update Agent Configuration

Edit agent JSON files (e.g., `compute/data/compute/agents/data-analyst-agent.json`):

```json
{
  "llm_providers": [
    {
      "provider": "openai",
      "model": "gpt-4",
      "temperature": 0.7,
      "priority": 1
    },
    {
      "provider": "mock",
      "model": "mock-gpt-4",
      "temperature": 0.7,
      "priority": 2
    }
  ]
}
```

The agent will try OpenAI first, fall back to mock if it fails.

### 2. Set API Keys

```bash
# In your .env file
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Restart Compute

```bash
cd compute
./stop.sh
./start.sh
```

## Troubleshooting

### Services Not Starting

```bash
# Check what's running
./status.sh

# Stop all
./stop_all.sh

# Start fresh
./start_all.sh
```

### Compute Not Registered

```bash
# Check serving registry
curl http://localhost:8002/api/v1/compute

# Check compute logs
tail -f logs/compute.log | grep -i register
```

### Agent Not Found

```bash
# List available agents
curl http://localhost:8003/agents | python3 -m json.tool

# Check agent files exist
ls -la compute/data/compute/agents/
```

### Task Execution Failed

```bash
# Check the error message in response
curl -X POST http://localhost:8003/agents/execute \
  -H "Content-Type: application/json" \
  -d '...' | python3 -m json.tool

# Check compute logs
tail -f logs/compute.log
```

## Performance

Mock provider performance:
- **Response time**: ~0.5 seconds
- **Throughput**: ~100 requests/second
- **Cost**: $0 (no API calls)
- **Rate limits**: None

## Next Steps

After testing with mocks:

1. **Add Custom Agents** - Create your own agent definitions
2. **Connect Real LLMs** - Configure OpenAI, Anthropic, etc.
3. **Build Custom Workflows** - Create multi-agent business processes
4. **Scale Compute** - Run multiple compute instances
5. **Production Deploy** - Use Docker for deployment

## API Documentation

Full API docs available at:
- Serving: http://localhost:8002/docs
- Compute: http://localhost:8003/docs
- Marketplace: http://localhost:8001/docs

## Additional Resources

- **Project Overview**: `README.md`
- **Architecture**: `docs/design/architecture/platform-overview.md`
- **Configuration**: `docs/guides/CONFIGURATION_GUIDE.md`
- **Agent Development**: `compute/README.md`

---

**Happy Testing! 🚀**

