# Mock Testing Quick Start

Test ClaudeVN end-to-end **without** hitting any LLM APIs!

## 🚀 Quick Test (2 minutes)

```bash
# 1. Start all services
./start_all.sh

# 2. Run the test
./test_mock_e2e.sh
```

That's it! The test will:
- ✅ Verify all services are running
- ✅ Execute agents with mock LLM responses
- ✅ Test task routing through serving
- ✅ Run a complete 3-agent business process

## What's the Mock Provider?

The **Mock LLM Provider** returns realistic, pre-programmed responses:
- 💰 **Zero cost** - No API calls
- ⚡ **Fast** - Responses in <1 second
- 🔌 **Offline** - No internet needed
- 🎯 **Smart** - Context-aware responses

## Manual Testing Examples

### Execute an Agent
```bash
curl -X POST http://localhost:8003/agents/execute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data-analyst-v1",
    "prompt": "Analyze Q4 sales data",
    "context": {"total_revenue": 24127.50}
  }' | python3 -m json.tool
```

### Route a Task via Serving
```bash
curl -X POST http://localhost:8002/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "content-writer-v1",
    "prompt": "Write an executive summary"
  }' | python3 -m json.tool
```

### Run Full Business Process
```bash
curl -X POST http://localhost:8002/api/v1/tasks/demo/business-process \
  | python3 -m json.tool
```

## Available Mock Agents

Three agents are pre-configured with mock responses:

1. **Data Analyst** (`data-analyst-v1`)
   - Analyzes data, generates insights
   - Returns statistics, trends, recommendations

2. **Task Coordinator** (`task-coordinator-v1`)
   - Plans multi-step workflows
   - Returns execution plans with phases

3. **Content Writer** (`content-writer-v1`)
   - Generates reports, documentation
   - Returns formatted professional content

## Architecture

```
┌─────────────────────────────────────────┐
│  User Request                           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  Serving Component (Port 8002)           │
│  • Routes tasks to compute instances     │
│  • Manages compute registry              │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  Compute Instance (Port 8003)            │
│  • Executes agents                       │
│  • Uses Mock LLM Provider                │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  Mock LLM Provider                       │
│  • Returns canned responses              │
│  • No API calls, zero cost               │
└──────────────────────────────────────────┘
```

## View Results

Results include:
```json
{
  "task_id": "task-123",
  "agent_id": "data-analyst-v1",
  "status": "completed",
  "output": {
    "content": "Based on my analysis...",
    "format": "markdown"
  },
  "metadata": {
    "duration_seconds": 0.52,
    "llm_provider": "mock",
    "tokens_used": 456,
    "cost_estimate": 0.0
  }
}
```

## Switching to Real LLMs

To use OpenAI/Anthropic instead of mock:

1. **Set API keys** in `.env`:
   ```
   OPENAI_API_KEY=sk-...
   ```

2. **Update agent config** in `compute/data/compute/agents/*.json`:
   ```json
   {
     "llm_providers": [
       {"provider": "openai", "model": "gpt-4", "priority": 1},
       {"provider": "mock", "model": "mock-gpt-4", "priority": 2}
     ]
   }
   ```

3. **Restart compute**:
   ```bash
   cd compute && ./stop.sh && ./start.sh
   ```

## Troubleshooting

### Services not running?
```bash
./status.sh
./start_all.sh
```

### Compute not registered?
```bash
curl http://localhost:8002/api/v1/compute
```

### Agent not found?
```bash
curl http://localhost:8003/agents
```

## More Info

- **Full Guide**: `docs/guides/MOCK_E2E_GUIDE.md`
- **API Docs**: 
  - http://localhost:8002/docs (Serving)
  - http://localhost:8003/docs (Compute)
- **Logs**: `tail -f logs/*.log`

---

**Ready to test? Run: `./test_mock_e2e.sh`** 🎉

