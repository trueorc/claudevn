# AI Task Execution Testing Guide

## Overview

This guide covers testing actual AI calls in the ClaudeVN system, including:
1. Command-line testing with the `test_real_ai.sh` script
2. Interactive testing through the Serving Dashboard UI
3. Understanding the agent execution flow

## Prerequisites

### 1. Environment Setup

Ensure your OpenAI API key is configured in the `.env` file:

```bash
# .env
OPENAI_API_KEY=sk-proj-your-actual-key-here
```

### 2. All Services Running

Start all ClaudeVN services:

```bash
# From project root
./start_all.sh
```

This starts:
- **Marketplace** (Port 8001) - Agent registry and discovery
- **Serving** (Port 8002) - Task routing and orchestration
- **Compute** (Port 8003) - AI agent execution

Verify all services are healthy:

```bash
./status.sh
```

## Method 1: Command-Line Testing

### Running the AI Test Script

The `test_real_ai.sh` script performs comprehensive AI execution tests:

```bash
./test_real_ai.sh
```

### What the Script Tests

1. **Service Health Checks**
   - Verifies all services are running
   - Confirms OpenAI API key is configured

2. **Agent Discovery**
   - Lists available agents from compute instances
   - Shows capabilities

3. **Simple Problem Solving**
   - Submits a math/financial calculation task
   - Tests basic agent execution with OpenAI

4. **Complex Data Analysis**
   - Submits a multi-step analysis task
   - Tests agent reasoning and structured output

5. **Content Generation**
   - Tests creative/writing capabilities
   - Demonstrates professional content generation

### Example Output

```bash
============================================================
Step 4: Test Simple Problem (Math Calculation)
============================================================

▶ Submitting simple math problem to task-coordinator-v1...
✓ Task submitted successfully: task_abc123

=== Task Result ===
{
  "task_id": "task_abc123",
  "status": "completed",
  "output": {
    "content": "Here's the compound interest calculation...",
    "reasoning": "...",
    "result": "$11,614.72"
  }
}
```

## Method 2: UI Testing (Recommended for Interactive Use)

### Accessing the AI Tasks Interface

1. Open your browser to: http://localhost:8002
2. Click the **"AI Tasks"** tab in the navigation

### Using the Task Submission Interface

#### Quick Start with Example Prompts

The UI includes pre-built example prompts:

1. **💰 Financial Calculation** - Math and financial problems
2. **📊 Data Analysis** - Sales data analysis with insights
3. **✍️ Content Generation** - Professional writing tasks
4. **📋 Project Planning** - Multi-step project planning

Click any example button to load a pre-written prompt, then click **"Submit Task"**.

#### Custom Task Submission

1. **Select an Agent**
   - Choose from available agents (task-coordinator-v1, data-analyst-v1, content-writer-v1)
   - Each agent has specialized capabilities

2. **Enter Your Prompt**
   - Write a clear, detailed task description
   - Provide context and requirements
   - Specify desired output format

3. **Choose Output Format**
   - **Text** - Plain text response
   - **Markdown** - Formatted with headers, lists, etc.
   - **JSON** - Structured data

4. **Submit and View Results**
   - Click "Submit Task"
   - Results appear below with:
     - Task ID and status
     - Agent used
     - Compute instance
     - Full output
     - Metadata

### Running the Demo Business Process

Click **"Run Multi-Agent Business Process"** to execute a complete 3-step workflow:

1. **Task Coordinator** - Plans the workflow
2. **Data Analyst** - Analyzes Q4 sales data
3. **Content Writer** - Generates executive report

This demonstrates multi-agent collaboration and task chaining.

## Understanding Agent Capabilities

### Available Agents

#### 1. task-coordinator-v1
- **Purpose**: Planning and task breakdown
- **Best for**: 
  - Project planning
  - Workflow design
  - Task decomposition
  - Strategic planning

**Example Prompt**:
```
Plan a comprehensive website redesign project with the following goals:
- Improve user experience
- Modernize visual design
- Optimize for mobile
- Enhance SEO
Provide a detailed project plan with phases, timelines, and key deliverables.
```

#### 2. data-analyst-v1
- **Purpose**: Data analysis and insights
- **Best for**:
  - Sales analysis
  - Trend identification
  - Statistical summaries
  - Data-driven recommendations

**Example Prompt**:
```
Analyze this quarterly sales data:
[paste data table]

Provide:
1. Summary statistics
2. Regional comparison
3. Growth trends
4. Key insights and recommendations
```

#### 3. content-writer-v1
- **Purpose**: Professional content generation
- **Best for**:
  - Business emails
  - Reports and summaries
  - Marketing copy
  - Documentation

**Example Prompt**:
```
Write a professional email to stakeholders announcing our Q4 results.
Include key metrics, achievements, and outlook for next quarter.
Tone: Professional yet optimistic
Length: 300-400 words
```

## Testing Scenarios

### Scenario 1: Math Problem Solving

**Agent**: task-coordinator-v1  
**Prompt**:
```
A company has 3 investment options:
A) $50,000 at 6% annual interest, compounded quarterly for 5 years
B) $50,000 at 5.8% annual interest, compounded monthly for 5 years  
C) $50,000 at 6.2% annual interest, compounded annually for 5 years

Calculate the final value of each option and recommend the best investment.
Show all calculations.
```

### Scenario 2: Business Data Analysis

**Agent**: data-analyst-v1  
**Prompt**:
```
Our customer service team has the following metrics:

Month    | Tickets | Resolved | Avg Response Time | Satisfaction
---------|---------|----------|-------------------|-------------
January  | 450     | 425      | 4.2 hours         | 87%
February | 520     | 480      | 5.1 hours         | 82%
March    | 610     | 570      | 6.3 hours         | 79%
April    | 580     | 560      | 4.8 hours         | 85%

Analyze this data and provide:
1. Trend analysis
2. Areas of concern
3. Correlation between metrics
4. Actionable recommendations to improve satisfaction
```

### Scenario 3: Content Creation

**Agent**: content-writer-v1  
**Prompt**:
```
Create a LinkedIn post announcing our company's achievement of carbon neutrality.

Key points:
- Achieved 100% carbon neutral operations
- Reduced emissions by 45% since 2020
- Invested in renewable energy and reforestation
- Commitment to sustainability

Tone: Professional, proud, inspiring
Length: 200-250 words
Include relevant hashtags
```

### Scenario 4: Complex Multi-Step Task

**Agent**: task-coordinator-v1  
**Prompt**:
```
Design a comprehensive employee onboarding program for a tech startup.

Requirements:
- 30-day onboarding timeline
- Technical training for engineering roles
- Culture and values integration
- Mentorship program
- Success metrics

Provide a detailed plan including week-by-week activities, resources needed,
responsible parties, and how to measure onboarding success.
```

## Monitoring and Debugging

### View Task Execution

1. **Serving Dashboard** - Overview of system health
2. **Observability Tab** - Real-time event stream
   - Activity state changes
   - Agent exchanges
   - Tool executions
   - Blockers and issues

### Check Logs

```bash
# Serving logs
tail -f serving/logs/serving.log

# Compute logs
tail -f compute/logs/compute.log

# Marketplace logs
tail -f marketplace/logs/marketplace.log
```

### API Direct Testing

You can also test directly via curl:

```bash
# Submit a task
curl -X POST http://localhost:8002/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "task-coordinator-v1",
    "prompt": "What is 2+2? Explain your reasoning.",
    "output_format": "markdown"
  }'
```

## Troubleshooting

### "No online compute instance found with agent"

**Problem**: No compute instance has registered the requested agent.

**Solution**:
1. Check compute instance is running: `curl http://localhost:8003/health`
2. Verify agent registration: `curl http://localhost:8003/agents`
3. Restart compute service: `cd compute && ./stop.sh && ./start.sh`

### "OpenAI API key not configured"

**Problem**: The OPENAI_API_KEY is not set or invalid.

**Solution**:
1. Check `.env` file has valid key
2. Restart services after updating: `./stop_all.sh && ./start_all.sh`
3. Verify with: `curl http://localhost:8003/info`

### "Task execution timed out"

**Problem**: The AI task took longer than expected.

**Solution**:
1. Complex tasks may need more time - this is expected
2. Check compute logs for progress
3. Consider breaking complex tasks into smaller subtasks

### UI Not Loading

**Problem**: Frontend won't load or shows errors.

**Solution**:
1. Rebuild frontend: `cd serving && ./build_frontend.sh`
2. Clear browser cache
3. Check browser console for errors

## Best Practices

### Writing Effective Prompts

1. **Be Specific**
   - Clear objectives
   - Detailed requirements
   - Expected output format

2. **Provide Context**
   - Background information
   - Constraints and limitations
   - Target audience

3. **Structure Your Request**
   - Break down into numbered points
   - Use clear sections
   - Specify deliverables

4. **Set Expectations**
   - Desired length
   - Tone and style
   - Output format

### Example: Poor vs Good Prompt

❌ **Poor Prompt**:
```
Analyze sales data
```

✅ **Good Prompt**:
```
Analyze the Q4 2024 sales data provided below and create a comprehensive report.

Data:
[include actual data]

Required Analysis:
1. Total revenue and growth vs Q3
2. Top 5 performing products by revenue
3. Regional performance breakdown
4. Trend analysis (month-over-month)
5. Recommendations for Q1 2025

Format: Markdown with clear sections and bullet points
```

## Advanced: Multi-Agent Workflows

For complex tasks, chain multiple agents:

1. **Planning**: Use task-coordinator-v1 to break down the problem
2. **Analysis**: Use data-analyst-v1 for data processing
3. **Documentation**: Use content-writer-v1 for final report

The demo business process shows this pattern in action.

## Next Steps

- Explore the [Observability Dashboard](http://localhost:8002) (Observability tab)
- Review [Process Maps](http://localhost:8002) (Process Maps tab)
- Check [Compute Registry](http://localhost:8002) (Compute Registry tab)
- Read the [Architecture Documentation](../docs/ARCHITECTURE_RESOLUTION_SUMMARY.md)

## Support

For issues or questions:
- Check logs in `serving/logs/`, `compute/logs/`, `marketplace/logs/`
- Review test scripts for examples
- Consult API documentation in respective `README.md` files
