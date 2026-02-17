# AI Testing Quick Start

## 🚀 Quick Start (30 seconds)

1. **Start all services**:
   ```bash
   ./start_all.sh
   ```

2. **Run AI test**:
   ```bash
   ./test_real_ai.sh
   ```

3. **Open UI**:
   - Go to http://localhost:8002
   - Click **"AI Tasks"** tab
   - Click any example prompt button
   - Click **"Submit Task"**
   - View AI-generated results!

## 🎯 Two Ways to Test AI

### Option 1: Command Line (Automated)
```bash
./test_real_ai.sh
```
Tests 3 scenarios automatically:
- Math calculation
- Data analysis  
- Content generation

### Option 2: Web UI (Interactive)
1. Open http://localhost:8002
2. Click **"AI Tasks"** tab
3. Try example prompts:
   - 💰 Financial Calculation
   - 📊 Data Analysis
   - ✍️ Content Generation
   - 📋 Project Planning
4. Or write your own custom prompt

## 📋 Available Agents

| Agent | Purpose | Example Use |
|-------|---------|-------------|
| **task-coordinator-v1** | Planning & breakdown | Project plans, workflow design |
| **data-analyst-v1** | Data analysis | Sales reports, trend analysis |
| **content-writer-v1** | Content creation | Emails, reports, documentation |

## 🎬 Demo Workflow

Click **"Run Multi-Agent Business Process"** in the UI to see:
1. Task Coordinator plans the workflow
2. Data Analyst analyzes Q4 sales
3. Content Writer generates executive report

This demonstrates multi-agent collaboration!

## ⚙️ Requirements

- OpenAI API key in `.env` file
- All services running (use `./start_all.sh`)
- Ports 8001-8003 available

## 📖 Full Documentation

See [AI Testing Guide](AI_TESTING_GUIDE.md) for:
- Detailed testing scenarios
- Prompt writing best practices
- Troubleshooting guide
- Advanced multi-agent workflows

## 🔍 Monitoring

- **Dashboard**: http://localhost:8002 (Dashboard tab)
- **Observability**: http://localhost:8002 (Observability tab)
- **Logs**: `tail -f serving/logs/serving.log`

## 💡 Example Prompts to Try

### Math/Finance
```
Calculate the compound interest for a $10,000 investment 
at 5% annual rate compounded monthly for 3 years.
```

### Data Analysis
```
Analyze this sales data and provide insights on trends,
top performers, and recommendations...
[paste your data]
```

### Content Writing
```
Write a professional email announcing our Q4 results to
stakeholders. Include key metrics and next quarter outlook.
```

### Planning
```
Create a 90-day plan to launch a new mobile app, including
development phases, milestones, and resource requirements.
```

## ❓ Troubleshooting

**Services won't start?**
```bash
./stop_all.sh
./start_all.sh
./status.sh
```

**No agents available?**
```bash
# Check compute service
curl http://localhost:8003/agents
```

**OpenAI errors?**
- Check `.env` has valid `OPENAI_API_KEY`
- Restart services after updating `.env`

## 🎓 Next Steps

1. Try the example prompts
2. Create your own custom tasks
3. Explore the Observability dashboard
4. Review the full [AI Testing Guide](AI_TESTING_GUIDE.md)
