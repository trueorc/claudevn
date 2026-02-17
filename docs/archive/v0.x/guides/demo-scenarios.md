# ClaudeVN Demo Scenarios

## Overview

This document describes three core demo scenarios that demonstrate ClaudeVN's capabilities. Each scenario showcases different aspects of the platform: multi-agent coordination, data processing, and cross-instance communication.

---

## Scenario 1: Sales Data Analysis & Reporting

### Goal

"Analyze Q4 2024 sales data and create an executive summary presentation"

### Description

This scenario demonstrates the full coordinating agent workflow, from goal decomposition through result synthesis. It shows how agents work together to process data, generate insights, and create a final deliverable.

### Input

- **Primary**: CSV file with sales transactions (`examples/demo-data/sales_q4_2024.csv`)
- **Format**: Columns: date, product_id, product_name, category, quantity, price, region, customer_id

### Expected Flow

```
User submits goal + CSV file
    ↓
[GoalDecomposerAgent]
    - Parses goal: "analyze sales data" + "create presentation"
    - Identifies required capabilities: data_loading, analysis, visualization, writing
    - Creates execution plan with 6 tasks
    ↓
[TeamAssemblerAgent]
    - Queries marketplace for agents
    - Selects: DataAnalystAgent (3 tasks), WriterAgent (2 tasks)
    - Creates task assignments
    ↓
[ExecutionCoordinatorAgent]
    - Task 1: Load and validate CSV → DataAnalystAgent (Compute 1)
    - Task 2: Calculate key metrics → DataAnalystAgent (Compute 1)
    - Task 3: Identify trends → DataAnalystAgent (Compute 2) [cross-instance]
    - Task 4: Generate insights → DataAnalystAgent (Compute 2)
    - Task 5: Create visualizations → DataAnalystAgent (Compute 1)
    - Task 6: Write executive summary → WriterAgent (Compute 1)
    ↓
[ProgressTrackerAgent] (monitors in parallel)
    - Tracks task completion
    - Reports: "3/6 tasks completed, 50% progress"
    - Detects no issues
    ↓
[ResultSynthesizerAgent]
    - Collects all task outputs
    - Assembles final presentation
    - Generates executive summary
    ↓
User receives: PDF presentation with charts, insights, and recommendations
```

### Execution Plan

```json
{
  "plan_id": "plan-001",
  "goal": "Analyze Q4 2024 sales data and create executive summary presentation",
  "tasks": [
    {
      "task_id": "task-1",
      "name": "Load and validate sales data",
      "agent": "DataAnalystAgent",
      "dependencies": [],
      "input": {
        "file_ref": "uploaded_csv",
        "validation_rules": ["check_missing", "check_types"]
      },
      "expected_output": {
        "validated_data": "DataFrame",
        "quality_report": "dict"
      }
    },
    {
      "task_id": "task-2",
      "name": "Calculate key metrics",
      "agent": "DataAnalystAgent",
      "dependencies": ["task-1"],
      "input": {
        "data_ref": "task-1.validated_data"
      },
      "expected_output": {
        "metrics": {
          "total_revenue": "float",
          "total_units": "int",
          "avg_order_value": "float",
          "top_products": "list",
          "regional_breakdown": "dict"
        }
      }
    },
    {
      "task_id": "task-3",
      "name": "Identify trends and patterns",
      "agent": "DataAnalystAgent",
      "dependencies": ["task-2"],
      "input": {
        "metrics": "task-2.metrics",
        "data_ref": "task-1.validated_data"
      },
      "expected_output": {
        "trends": ["trend1", "trend2", "..."],
        "patterns": "dict"
      }
    },
    {
      "task_id": "task-4",
      "name": "Generate business insights",
      "agent": "DataAnalystAgent",
      "dependencies": ["task-3"],
      "input": {
        "trends": "task-3.trends",
        "metrics": "task-2.metrics"
      },
      "expected_output": {
        "insights": ["insight1", "insight2", "..."],
        "recommendations": ["rec1", "rec2", "..."]
      }
    },
    {
      "task_id": "task-5",
      "name": "Create visualizations",
      "agent": "DataAnalystAgent",
      "dependencies": ["task-2", "task-3"],
      "input": {
        "metrics": "task-2.metrics",
        "trends": "task-3.trends"
      },
      "expected_output": {
        "charts": ["revenue_chart.png", "regional_chart.png", "trend_chart.png"]
      }
    },
    {
      "task_id": "task-6",
      "name": "Write executive summary",
      "agent": "WriterAgent",
      "dependencies": ["task-4", "task-5"],
      "input": {
        "insights": "task-4.insights",
        "recommendations": "task-4.recommendations",
        "charts": "task-5.charts"
      },
      "expected_output": {
        "presentation": "presentation.pdf"
      }
    }
  ]
}
```

### Expected Output

**Executive Summary Presentation (PDF)**

```
Page 1: Title
- Q4 2024 Sales Analysis
- Executive Summary
- Date: November 21, 2024

Page 2: Key Metrics
- Total Revenue: $2.4M (+15% vs Q3)
- Total Units Sold: 45,230 (+8% vs Q3)
- Average Order Value: $53.12 (+6% vs Q3)
- Top Product: Widget Pro (18% of revenue)

Page 3: Regional Performance
[Bar chart showing revenue by region]
- West: $980K (41%)
- East: $720K (30%)
- Central: $480K (20%)
- South: $220K (9%)

Page 4: Trends & Insights
- Strong growth in premium products (+25%)
- Seasonal spike in November (Black Friday)
- Declining performance in South region (-12%)
- Mobile orders increased to 45% of total

Page 5: Recommendations
1. Increase inventory for premium products
2. Launch targeted campaign in South region
3. Optimize mobile checkout experience
4. Prepare for Q1 seasonal dip
```

### Agents Used

- **GoalDecomposerAgent**: Creates 6-task execution plan
- **TeamAssemblerAgent**: Selects DataAnalystAgent and WriterAgent
- **ExecutionCoordinatorAgent**: Manages task execution across 2 instances
- **ProgressTrackerAgent**: Monitors progress, reports 50% completion
- **DataAnalystAgent**: Performs 5 data analysis tasks
- **WriterAgent**: Creates final presentation
- **ResultSynthesizerAgent**: Assembles final deliverable

### Demonstrates

✅ Full coordinating agent workflow  
✅ Data processing and analysis  
✅ Multi-agent coordination  
✅ Cross-instance communication (Task 3 on different instance)  
✅ Data sharing via blob storage (CSV file)  
✅ Progress tracking  
✅ Result synthesis  

---

## Scenario 2: Research & Documentation

### Goal

"Research best practices for API security and create a technical guide"

### Description

This scenario demonstrates web research capability, content synthesis, and documentation generation. It shows how agents can gather information from external sources and create structured documentation.

### Input

- **Primary**: Text goal only (no files)
- **Optional**: Specific topics to cover (authentication, authorization, rate limiting, etc.)

### Expected Flow

```
User submits goal
    ↓
[GoalDecomposerAgent]
    - Parses goal: "research API security" + "create guide"
    - Identifies required capabilities: web_search, research, writing
    - Creates execution plan with 5 tasks
    ↓
[TeamAssemblerAgent]
    - Queries marketplace
    - Selects: ResearcherAgent (3 tasks), WriterAgent (2 tasks)
    ↓
[ExecutionCoordinatorAgent]
    - Task 1: Identify key API security topics → ResearcherAgent
    - Task 2: Research authentication best practices → ResearcherAgent
    - Task 3: Research authorization and rate limiting → ResearcherAgent
    - Task 4: Organize findings → WriterAgent
    - Task 5: Create technical guide → WriterAgent
    ↓
[ProgressTrackerAgent]
    - Monitors research progress
    - Reports: "Research phase complete, writing guide"
    ↓
[ResultSynthesizerAgent]
    - Assembles guide with all sections
    - Adds table of contents and references
    ↓
User receives: Markdown technical guide
```

### Execution Plan

```json
{
  "plan_id": "plan-002",
  "goal": "Research best practices for API security and create technical guide",
  "tasks": [
    {
      "task_id": "task-1",
      "name": "Identify key API security topics",
      "agent": "ResearcherAgent",
      "dependencies": [],
      "input": {
        "domain": "API security",
        "goal": "comprehensive coverage"
      },
      "expected_output": {
        "topics": ["authentication", "authorization", "rate_limiting", "..."]
      }
    },
    {
      "task_id": "task-2",
      "name": "Research authentication best practices",
      "agent": "ResearcherAgent",
      "dependencies": ["task-1"],
      "input": {
        "topic": "API authentication",
        "depth": "detailed"
      },
      "expected_output": {
        "findings": "dict with sources and summaries"
      }
    },
    {
      "task_id": "task-3",
      "name": "Research authorization and rate limiting",
      "agent": "ResearcherAgent",
      "dependencies": ["task-1"],
      "input": {
        "topics": ["authorization", "rate_limiting"],
        "depth": "detailed"
      },
      "expected_output": {
        "findings": "dict with sources and summaries"
      }
    },
    {
      "task_id": "task-4",
      "name": "Organize research findings",
      "agent": "WriterAgent",
      "dependencies": ["task-2", "task-3"],
      "input": {
        "findings": ["task-2.findings", "task-3.findings"],
        "structure": "technical guide"
      },
      "expected_output": {
        "outline": "dict with sections and content"
      }
    },
    {
      "task_id": "task-5",
      "name": "Create technical guide document",
      "agent": "WriterAgent",
      "dependencies": ["task-4"],
      "input": {
        "outline": "task-4.outline",
        "format": "markdown"
      },
      "expected_output": {
        "document": "api_security_guide.md"
      }
    }
  ]
}
```

### Expected Output

**API Security Best Practices Guide (Markdown)**

```markdown
# API Security Best Practices

## Table of Contents
1. Authentication
2. Authorization
3. Rate Limiting
4. Input Validation
5. Encryption
6. Monitoring & Logging

## 1. Authentication

### OAuth 2.0
OAuth 2.0 is the industry standard for API authentication...

### JWT Tokens
JSON Web Tokens provide stateless authentication...

### API Keys
For simpler use cases, API keys can be used...

## 2. Authorization

### Role-Based Access Control (RBAC)
RBAC provides fine-grained access control...

### Attribute-Based Access Control (ABAC)
For complex scenarios, ABAC offers flexible policies...

[... more sections ...]

## References
- OWASP API Security Top 10
- RFC 6749 (OAuth 2.0)
- NIST Guidelines for API Security
```

### Agents Used

- **GoalDecomposerAgent**: Creates research plan
- **TeamAssemblerAgent**: Selects research and writing agents
- **ExecutionCoordinatorAgent**: Manages research and writing tasks
- **ProgressTrackerAgent**: Monitors research progress
- **ResearcherAgent**: Performs web research (3 tasks)
- **WriterAgent**: Organizes and writes guide (2 tasks)
- **ResultSynthesizerAgent**: Assembles final document

### Demonstrates

✅ Web research capability  
✅ Content synthesis from multiple sources  
✅ Documentation generation  
✅ Structured output (Markdown)  
✅ No file input (text-only goal)  
✅ Parallel research tasks  

---

## Scenario 3: Code Analysis & Refactoring

### Goal

"Analyze this Python codebase and suggest refactoring improvements"

### Description

This scenario demonstrates code understanding, technical analysis, and structured recommendations. It shows how agents can analyze code and provide actionable feedback.

### Input

- **Primary**: Directory of Python files (`examples/demo-data/sample_codebase/`)
- **Contents**: 
  - `app.py` - Main application
  - `models.py` - Data models
  - `utils.py` - Utility functions
  - `tests.py` - Unit tests

### Expected Flow

```
User submits goal + code directory
    ↓
[GoalDecomposerAgent]
    - Parses goal: "analyze code" + "suggest refactoring"
    - Identifies required capabilities: code_analysis, static_analysis
    - Creates execution plan with 4 tasks
    ↓
[TeamAssemblerAgent]
    - Queries marketplace
    - Selects: CoderAgent (3 tasks), WriterAgent (1 task)
    ↓
[ExecutionCoordinatorAgent]
    - Task 1: Scan codebase structure → CoderAgent
    - Task 2: Identify code smells → CoderAgent
    - Task 3: Analyze complexity and patterns → CoderAgent
    - Task 4: Generate refactoring report → WriterAgent
    ↓
[ProgressTrackerAgent]
    - Monitors analysis progress
    - Reports: "Analyzing 4 files, 850 lines of code"
    ↓
[ResultSynthesizerAgent]
    - Compiles analysis results
    - Creates prioritized recommendations
    ↓
User receives: Refactoring report with specific suggestions
```

### Execution Plan

```json
{
  "plan_id": "plan-003",
  "goal": "Analyze Python codebase and suggest refactoring improvements",
  "tasks": [
    {
      "task_id": "task-1",
      "name": "Scan codebase structure",
      "agent": "CoderAgent",
      "dependencies": [],
      "input": {
        "directory_ref": "uploaded_code",
        "language": "python"
      },
      "expected_output": {
        "structure": "dict with files, classes, functions",
        "metrics": "dict with LOC, complexity, etc."
      }
    },
    {
      "task_id": "task-2",
      "name": "Identify code smells and anti-patterns",
      "agent": "CoderAgent",
      "dependencies": ["task-1"],
      "input": {
        "codebase": "task-1.structure"
      },
      "expected_output": {
        "issues": ["issue1", "issue2", "..."],
        "severity": "dict"
      }
    },
    {
      "task_id": "task-3",
      "name": "Analyze complexity and patterns",
      "agent": "CoderAgent",
      "dependencies": ["task-1"],
      "input": {
        "codebase": "task-1.structure",
        "metrics": "task-1.metrics"
      },
      "expected_output": {
        "complexity_analysis": "dict",
        "patterns": "list"
      }
    },
    {
      "task_id": "task-4",
      "name": "Generate refactoring report",
      "agent": "WriterAgent",
      "dependencies": ["task-2", "task-3"],
      "input": {
        "issues": "task-2.issues",
        "complexity": "task-3.complexity_analysis"
      },
      "expected_output": {
        "report": "refactoring_report.md"
      }
    }
  ]
}
```

### Expected Output

**Code Refactoring Report (Markdown)**

```markdown
# Code Analysis & Refactoring Report

## Summary
Analyzed 4 Python files (850 lines of code)
Found 12 issues (3 high, 5 medium, 4 low priority)

## Codebase Structure
- app.py: 320 LOC, 8 functions, 2 classes
- models.py: 180 LOC, 4 classes
- utils.py: 250 LOC, 15 functions
- tests.py: 100 LOC, 12 test functions

## High Priority Issues

### 1. Long Function in app.py (Line 45-120)
**Issue**: `process_request()` function is 75 lines long
**Impact**: Hard to test, maintain, and understand
**Recommendation**: Extract into smaller functions:
- `validate_request()`
- `transform_data()`
- `save_to_database()`

### 2. Circular Import in models.py
**Issue**: models.py imports from app.py, app.py imports from models.py
**Impact**: Can cause import errors, tight coupling
**Recommendation**: Extract shared code into separate module

### 3. Missing Error Handling in utils.py
**Issue**: Multiple functions lack try/except blocks
**Impact**: Unhandled exceptions can crash application
**Recommendation**: Add error handling for file operations and network calls

## Medium Priority Issues

### 4. Duplicate Code in utils.py (Lines 45-60, 120-135)
**Issue**: Similar validation logic repeated
**Recommendation**: Extract into `validate_input()` function

[... more issues ...]

## Code Metrics
- Average Cyclomatic Complexity: 8.5 (target: < 10)
- Functions > 50 lines: 3
- Classes > 200 lines: 1
- Test Coverage: ~60% (target: > 80%)

## Recommended Refactoring Steps
1. Split large functions (app.py:process_request)
2. Resolve circular imports
3. Add error handling
4. Extract duplicate code
5. Improve test coverage
6. Add type hints

## Estimated Effort
- High priority fixes: 4-6 hours
- Medium priority fixes: 3-4 hours
- Low priority fixes: 2-3 hours
- Total: 9-13 hours
```

### Agents Used

- **GoalDecomposerAgent**: Creates analysis plan
- **TeamAssemblerAgent**: Selects coder and writer agents
- **ExecutionCoordinatorAgent**: Manages analysis tasks
- **ProgressTrackerAgent**: Monitors analysis progress
- **CoderAgent**: Performs code analysis (3 tasks)
- **WriterAgent**: Creates refactoring report
- **ResultSynthesizerAgent**: Compiles final report

### Demonstrates

✅ Code understanding and analysis  
✅ Technical analysis capabilities  
✅ Structured recommendations  
✅ File/directory input handling  
✅ Detailed, actionable output  
✅ Prioritization of issues  

---

## Running the Demos

### Prerequisites

```bash
# Start all components
cd examples/all-in-one
./start.sh

# Verify services are running
curl http://localhost:8001/health  # Marketplace
curl http://localhost:8002/health  # Serving
curl http://localhost:8003/health  # Compute 1
curl http://localhost:8004/health  # Compute 2
```

### Scenario 1: Sales Analysis

```bash
# Via API
curl -X POST http://localhost:8002/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-sales-001",
    "goal": "Analyze Q4 2024 sales data and create executive summary presentation",
    "metadata": {"demo": "scenario-1"}
  }'

# Upload CSV file
curl -X POST http://localhost:8002/api/storage/upload \
  -F "file=@examples/demo-data/sales_q4_2024.csv" \
  -F "session_id=demo-sales-001"

# Monitor progress
curl http://localhost:8002/api/sessions/demo-sales-001

# Via UI
# 1. Open http://localhost:3000
# 2. Click "Submit Goal"
# 3. Enter goal text
# 4. Upload sales_q4_2024.csv
# 5. Click "Submit"
# 6. View progress on Session Detail page
```

### Scenario 2: API Security Research

```bash
# Via API
curl -X POST http://localhost:8002/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-research-001",
    "goal": "Research best practices for API security and create a technical guide",
    "metadata": {"demo": "scenario-2"}
  }'

# Monitor progress
curl http://localhost:8002/api/sessions/demo-research-001
```

### Scenario 3: Code Analysis

```bash
# Via API
curl -X POST http://localhost:8002/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-code-001",
    "goal": "Analyze this Python codebase and suggest refactoring improvements",
    "metadata": {"demo": "scenario-3"}
  }'

# Upload code directory (as zip)
zip -r codebase.zip examples/demo-data/sample_codebase/
curl -X POST http://localhost:8002/api/storage/upload \
  -F "file=@codebase.zip" \
  -F "session_id=demo-code-001"

# Monitor progress
curl http://localhost:8002/api/sessions/demo-code-001
```

---

## Success Criteria

### Scenario 1
✅ All 6 tasks complete successfully  
✅ Cross-instance communication works (Task 3)  
✅ CSV file uploaded and processed  
✅ Final presentation generated  
✅ Progress tracking shows 0% → 50% → 100%  

### Scenario 2
✅ All 5 tasks complete successfully  
✅ Web research returns relevant content  
✅ Technical guide is well-structured  
✅ References included  
✅ No file uploads needed  

### Scenario 3
✅ All 4 tasks complete successfully  
✅ Code directory uploaded and analyzed  
✅ Issues identified and prioritized  
✅ Specific line numbers referenced  
✅ Actionable recommendations provided  

---

## Troubleshooting

### "Session stuck in pending"
- Check compute instances are registered
- Verify agents are enabled in config
- Check logs for errors

### "File upload failed"
- Check file size < 100MB
- Verify storage backend is configured
- Check disk space

### "Task failed"
- Check agent logs for errors
- Verify LLM API key is set
- Check network connectivity

### "No results returned"
- Verify all tasks completed
- Check ResultSynthesizerAgent ran
- Review session context for outputs

---

## Next Steps

After running these demos:

1. **Customize Scenarios**: Modify goals and inputs
2. **Add More Agents**: Create specialized agents for your domain
3. **Extend Capabilities**: Add new tools and integrations
4. **Scale Up**: Deploy to cloud with multiple instances
5. **Monitor Performance**: Track costs, latency, success rates

