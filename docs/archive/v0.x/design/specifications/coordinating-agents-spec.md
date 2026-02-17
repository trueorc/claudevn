# Coordinating Agents Specification

## Overview

Coordinating agents are the "brain" of the ClaudeVN system. They are marketplace-aware, understand the full context of business processes, and orchestrate teams of specialized agents to accomplish complex goals. Unlike specialized agents that focus on specific tasks, coordinating agents manage the entire lifecycle of goal execution.

## Core Responsibilities

1. **Goal Understanding** - Parse and comprehend business objectives
2. **Decomposition** - Break complex goals into executable tasks
3. **Team Assembly** - Select optimal agents from marketplace
4. **Execution Planning** - Create dependency graphs and task sequences
5. **Progress Monitoring** - Track task completion and handle blockers
6. **Result Synthesis** - Assemble outputs into coherent final deliverables
7. **Error Recovery** - Handle failures and adapt plans dynamically

---

## Coordinating Agent Types

### 1. Goal Decomposer Agent

**Purpose:** Analyzes business goals and breaks them into structured execution plans.

**Capabilities:**
- Natural language goal understanding
- Domain knowledge application
- Task dependency analysis
- Complexity estimation
- Ambiguity resolution

**Process:**

```
Input: "Analyze Q4 sales data and create executive presentation"

Step 1: Parse Goal
  - Primary objective: Create presentation
  - Data source: Q4 sales data
  - Audience: Executives
  - Implicit requirements: Analysis, insights, visualization

Step 2: Identify Required Capabilities
  - Data loading and validation
  - Statistical analysis
  - Trend identification
  - Visualization creation
  - Document generation
  - Executive summary writing

Step 3: Create Task Graph
  Task 1: Load Q4 sales data
    └─> Task 2: Validate data quality
        └─> Task 3: Calculate key metrics
            ├─> Task 4: Identify trends
            └─> Task 5: Compare to Q3/previous year
                └─> Task 6: Generate insights
                    ├─> Task 7: Create visualizations
                    └─> Task 8: Write executive summary
                        └─> Task 9: Assemble presentation

Step 4: Output Execution Plan
  - Task list with dependencies
  - Required capabilities per task
  - Estimated complexity
  - Data flow between tasks
```

**LLM Prompt Template:**

```python
GOAL_DECOMPOSITION_PROMPT = """
You are a Goal Decomposer Agent. Your role is to analyze business goals and create detailed execution plans.

GOAL: {user_goal}

CONTEXT:
- Available agent capabilities: {available_capabilities}
- Available tools: {available_tools}
- User constraints: {constraints}

INSTRUCTIONS:
1. Parse the goal and identify the primary objective
2. List all subtasks required to achieve the goal
3. Identify dependencies between tasks
4. Specify required capabilities for each task
5. Estimate complexity (low/medium/high) for each task
6. Output as a structured execution plan in JSON format

OUTPUT FORMAT:
{{
  "goal_summary": "Brief description",
  "tasks": [
    {{
      "task_id": "task-1",
      "name": "Task name",
      "description": "What needs to be done",
      "dependencies": ["task-id-1", "task-id-2"],
      "required_capabilities": ["capability1", "capability2"],
      "complexity": "low|medium|high",
      "inputs": {{"key": "description"}},
      "outputs": {{"key": "description"}}
    }}
  ],
  "data_flow": "Description of how data moves between tasks"
}}

Think step by step and be thorough.
"""
```

**Example Output:**

```json
{
  "goal_summary": "Analyze Q4 sales data and create executive presentation",
  "tasks": [
    {
      "task_id": "task-1",
      "name": "Load sales data",
      "description": "Read Q4 sales data from provided source",
      "dependencies": [],
      "required_capabilities": ["file_reading", "data_parsing"],
      "complexity": "low",
      "inputs": {"file_path": "Path to Q4 sales data"},
      "outputs": {"data": "Parsed sales records"}
    },
    {
      "task_id": "task-2",
      "name": "Validate data",
      "description": "Check for missing values, outliers, data quality issues",
      "dependencies": ["task-1"],
      "required_capabilities": ["data_validation", "statistical_analysis"],
      "complexity": "medium",
      "inputs": {"data": "Sales records from task-1"},
      "outputs": {"validated_data": "Clean dataset", "quality_report": "Data quality summary"}
    },
    {
      "task_id": "task-3",
      "name": "Calculate metrics",
      "description": "Compute total revenue, growth rate, top products, regional performance",
      "dependencies": ["task-2"],
      "required_capabilities": ["data_analysis", "aggregation"],
      "complexity": "medium",
      "inputs": {"validated_data": "Clean dataset from task-2"},
      "outputs": {"metrics": "Key performance indicators"}
    }
    // ... more tasks
  ]
}
```

---

### 2. Team Assembler Agent

**Purpose:** Selects optimal agents from marketplace to execute the plan.

**Capabilities:**
- Marketplace querying and filtering
- Capability matching
- Agent performance evaluation
- Resource availability checking
- Team composition optimization

**Process:**

```
Input: Execution Plan from Goal Decomposer

Step 1: Extract Required Capabilities
  - From all tasks: [data_parsing, data_validation, statistical_analysis, 
    visualization, document_generation, writing]

Step 2: Query Marketplace
  - Search for agents with required capabilities
  - Filter by access permissions
  - Get performance metrics (if available)

Step 3: Match Agents to Tasks
  - For each task, find agents with matching capabilities
  - Consider agent specialization depth
  - Check for multi-capability agents (can handle multiple tasks)

Step 4: Optimize Team Composition
  - Minimize number of agents (reduce coordination overhead)
  - Balance workload across agents
  - Prefer agents with proven performance
  - Consider instance locality (prefer same-instance agents)

Step 5: Create Agent Assignment Map
  - Map each task to specific agent
  - Include fallback agents for critical tasks
  - Note cross-instance invocations
```

**LLM Prompt Template:**

```python
TEAM_ASSEMBLY_PROMPT = """
You are a Team Assembler Agent. Your role is to select the best agents from the marketplace to execute a plan.

EXECUTION PLAN:
{execution_plan}

AVAILABLE AGENTS:
{marketplace_agents}

INSTRUCTIONS:
1. For each task in the plan, identify which agents can perform it
2. Consider agent capabilities, specialization, and performance
3. Optimize for minimal team size while ensuring all tasks are covered
4. Assign primary and backup agents for critical tasks
5. Note which agents are on the same instance vs. require cross-instance calls

OUTPUT FORMAT:
{{
  "team": [
    {{
      "agent_id": "agent-123",
      "agent_name": "DataAnalystAgent",
      "assigned_tasks": ["task-1", "task-2", "task-3"],
      "capabilities": ["data_analysis", "statistical_analysis"],
      "instance": "compute-1",
      "role": "primary"
    }}
  ],
  "task_assignments": {{
    "task-1": {{
      "primary_agent": "agent-123",
      "backup_agent": "agent-456",
      "cross_instance": false
    }}
  }},
  "team_summary": "Brief description of team composition"
}}
"""
```

**Marketplace Query Example:**

```python
async def query_marketplace(self, required_capabilities):
    """Query marketplace for agents with required capabilities"""
    
    # Build query
    query = {
        "capabilities": required_capabilities,
        "access_level": "allowed",
        "status": "active"
    }
    
    # Query all configured marketplaces
    agents = []
    for marketplace_url in self.config.marketplace_urls:
        response = await self.http_client.get(
            f"{marketplace_url}/api/agents",
            params=query
        )
        agents.extend(response.json())
    
    # Deduplicate and rank
    unique_agents = self.deduplicate_agents(agents)
    ranked_agents = self.rank_agents(unique_agents, required_capabilities)
    
    return ranked_agents

def rank_agents(self, agents, required_capabilities):
    """Rank agents by suitability"""
    
    scored_agents = []
    for agent in agents:
        score = 0
        
        # Capability match score
        matched_caps = set(agent['capabilities']) & set(required_capabilities)
        score += len(matched_caps) * 10
        
        # Specialization bonus (fewer capabilities = more specialized)
        if len(agent['capabilities']) <= 3:
            score += 5
        
        # Performance metrics (if available)
        if 'performance' in agent:
            score += agent['performance'].get('success_rate', 0) * 10
        
        # Instance locality bonus
        if agent.get('instance') == self.instance_id:
            score += 20
        
        scored_agents.append((agent, score))
    
    # Sort by score descending
    scored_agents.sort(key=lambda x: x[1], reverse=True)
    
    return [agent for agent, score in scored_agents]
```

---

### 3. Execution Coordinator Agent

**Purpose:** Manages the execution of the plan, invoking agents and handling task flow.

**Capabilities:**
- Task scheduling and sequencing
- Agent invocation (local and cross-instance)
- Dependency resolution
- Parallel execution management
- State tracking

**Process:**

```
Input: Execution Plan + Agent Assignments

Step 1: Initialize Session State
  - Create session record
  - Store execution plan
  - Initialize task statuses (all pending)

Step 2: Build Execution Queue
  - Identify tasks with no dependencies (ready to execute)
  - Sort by priority/complexity

Step 3: Execute Tasks
  For each ready task:
    - Get assigned agent
    - Prepare task input (from previous task outputs)
    - Invoke agent (local or via A2A)
    - Update task status (working)
    - Wait for completion or monitor async

Step 4: Handle Task Completion
  - Store task output
  - Update task status (completed)
  - Check dependent tasks
  - Add newly-ready tasks to queue

Step 5: Handle Task Failure
  - Log error
  - Attempt retry with backup agent
  - If critical task fails, escalate to Progress Tracker
  - Update execution plan if needed

Step 6: Continue Until All Tasks Complete
  - Monitor progress
  - Handle parallel execution
  - Manage resource constraints
```

**Implementation Example:**

```python
class ExecutionCoordinatorAgent(BaseAgent):
    """Coordinates execution of tasks across agents"""
    
    async def execute(self, task_input, context):
        """Main execution loop"""
        
        execution_plan = task_input['execution_plan']
        agent_assignments = task_input['agent_assignments']
        session_id = context['session_id']
        
        # Initialize state
        state = ExecutionState(
            session_id=session_id,
            plan=execution_plan,
            assignments=agent_assignments
        )
        
        # Execution loop
        while not state.is_complete():
            # Get ready tasks (dependencies satisfied)
            ready_tasks = state.get_ready_tasks()
            
            if not ready_tasks:
                # Wait for in-progress tasks
                await asyncio.sleep(1)
                continue
            
            # Execute tasks in parallel (up to max_parallel)
            tasks_to_execute = ready_tasks[:self.config.max_parallel_tasks]
            
            await asyncio.gather(*[
                self.execute_task(task, state)
                for task in tasks_to_execute
            ])
        
        # All tasks complete
        return {
            'status': 'completed',
            'results': state.get_all_results(),
            'execution_summary': state.get_summary()
        }
    
    async def execute_task(self, task, state):
        """Execute a single task"""
        
        # Mark as working
        state.update_task_status(task['task_id'], 'working')
        
        try:
            # Get assigned agent
            assignment = state.get_assignment(task['task_id'])
            agent = assignment['primary_agent']
            
            # Prepare input
            task_input = self.prepare_task_input(task, state)
            
            # Invoke agent
            if assignment['cross_instance']:
                # Use A2A protocol
                result = await self.invoke_remote_agent(
                    agent_id=agent['agent_id'],
                    input=task_input,
                    context={'session_id': state.session_id, 'task_id': task['task_id']}
                )
            else:
                # Local invocation
                result = await self.invoke_local_agent(
                    agent_id=agent['agent_id'],
                    input=task_input,
                    context={'session_id': state.session_id, 'task_id': task['task_id']}
                )
            
            # Store result
            state.store_task_result(task['task_id'], result)
            state.update_task_status(task['task_id'], 'completed')
            
        except Exception as e:
            # Handle failure
            await self.handle_task_failure(task, state, e)
    
    async def invoke_remote_agent(self, agent_id, input, context):
        """Invoke agent on different instance via A2A"""
        
        # Submit task via A2A protocol
        response = await self.a2a_client.submit_task(
            agent_id=agent_id,
            input=input,
            context=context
        )
        
        task_id = response['task_id']
        
        # Poll for completion (or use SSE/WebSocket)
        while True:
            status = await self.a2a_client.get_task_status(task_id)
            
            if status['status'] == 'completed':
                return status['result']
            elif status['status'] == 'failed':
                raise Exception(f"Remote task failed: {status['error']}")
            elif status['status'] == 'input_required':
                # Handle input request
                additional_input = await self.handle_input_request(status)
                await self.a2a_client.provide_input(task_id, additional_input)
            
            await asyncio.sleep(1)
```

---

### 4. Progress Tracker Agent

**Purpose:** Monitors execution, identifies issues, and reports status.

**Capabilities:**
- Real-time progress monitoring
- Bottleneck detection
- Failure pattern recognition
- Status reporting
- Alert generation

**Responsibilities:**

1. **Monitor Task Progress**
   - Track task durations
   - Identify stuck tasks
   - Detect slow agents

2. **Identify Issues**
   - Tasks exceeding expected duration
   - Repeated failures
   - Dependency deadlocks
   - Resource constraints

3. **Generate Status Reports**
   - Overall progress percentage
   - Completed vs. pending tasks
   - Current bottlenecks
   - Estimated completion time

4. **Alert on Problems**
   - Critical task failures
   - Session stalls
   - Agent unavailability

**Implementation Example:**

```python
class ProgressTrackerAgent(BaseAgent):
    """Monitors and reports on execution progress"""
    
    async def monitor_session(self, session_id):
        """Continuously monitor session progress"""
        
        while True:
            # Get current state
            state = await self.get_session_state(session_id)
            
            if state.is_complete():
                break
            
            # Check for issues
            issues = self.detect_issues(state)
            
            if issues:
                await self.handle_issues(issues, state)
            
            # Generate progress report
            report = self.generate_progress_report(state)
            await self.publish_progress(session_id, report)
            
            await asyncio.sleep(5)
    
    def detect_issues(self, state):
        """Detect execution issues"""
        
        issues = []
        
        # Check for stuck tasks
        for task in state.get_in_progress_tasks():
            duration = time.time() - task['started_at']
            expected_duration = task.get('estimated_duration', 300)
            
            if duration > expected_duration * 2:
                issues.append({
                    'type': 'stuck_task',
                    'task_id': task['task_id'],
                    'duration': duration,
                    'severity': 'high'
                })
        
        # Check for repeated failures
        failed_tasks = state.get_failed_tasks()
        if len(failed_tasks) > 3:
            issues.append({
                'type': 'multiple_failures',
                'count': len(failed_tasks),
                'severity': 'critical'
            })
        
        # Check for dependency deadlocks
        if state.has_circular_dependencies():
            issues.append({
                'type': 'deadlock',
                'severity': 'critical'
            })
        
        return issues
    
    def generate_progress_report(self, state):
        """Generate progress report"""
        
        total_tasks = len(state.plan['tasks'])
        completed_tasks = len(state.get_completed_tasks())
        failed_tasks = len(state.get_failed_tasks())
        in_progress_tasks = len(state.get_in_progress_tasks())
        pending_tasks = len(state.get_pending_tasks())
        
        return {
            'session_id': state.session_id,
            'progress_percentage': (completed_tasks / total_tasks) * 100,
            'total_tasks': total_tasks,
            'completed': completed_tasks,
            'failed': failed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'estimated_completion': self.estimate_completion_time(state),
            'current_bottlenecks': self.identify_bottlenecks(state)
        }
```

---

### 5. Result Synthesizer Agent

**Purpose:** Assembles outputs from all tasks into final deliverable.

**Capabilities:**
- Multi-source data aggregation
- Format conversion
- Quality validation
- Narrative generation
- Final output packaging

**Process:**

```
Input: All task results from execution

Step 1: Collect Results
  - Gather outputs from all completed tasks
  - Organize by task dependencies
  - Identify final output tasks

Step 2: Validate Completeness
  - Check all required outputs present
  - Verify data quality
  - Identify any gaps

Step 3: Synthesize Results
  - Combine related outputs
  - Generate summary/overview
  - Create narrative connecting results
  - Format for end user

Step 4: Package Deliverable
  - Create final document/artifact
  - Include supporting data
  - Add metadata (execution time, agents used, etc.)
  - Generate executive summary

Step 5: Quality Check
  - Verify deliverable meets original goal
  - Check for consistency
  - Validate format and completeness
```

**LLM Prompt Template:**

```python
RESULT_SYNTHESIS_PROMPT = """
You are a Result Synthesizer Agent. Your role is to combine outputs from multiple tasks into a coherent final deliverable.

ORIGINAL GOAL: {original_goal}

TASK RESULTS:
{task_results}

INSTRUCTIONS:
1. Review all task outputs
2. Identify the key findings and outputs
3. Create a narrative that connects the results
4. Generate an executive summary
5. Package everything into a final deliverable

OUTPUT FORMAT:
{{
  "executive_summary": "High-level overview for executives",
  "key_findings": ["Finding 1", "Finding 2", ...],
  "detailed_results": {{
    "section1": "...",
    "section2": "..."
  }},
  "supporting_data": {{
    "charts": [...],
    "tables": [...],
    "raw_data": [...]
  }},
  "metadata": {{
    "execution_time": "...",
    "agents_used": [...],
    "tasks_completed": ...
  }}
}}
"""
```

---

## Coordinating Agent Collaboration

The five coordinating agents work together in sequence:

```
User Goal
    ↓
[Goal Decomposer] → Execution Plan
    ↓
[Team Assembler] → Agent Assignments
    ↓
[Execution Coordinator] → Task Execution
    ↓                          ↓
[Progress Tracker] ←─────────┘ (monitors)
    ↓
[Result Synthesizer] → Final Deliverable
    ↓
User
```

**Coordination Flow:**

1. **Goal Decomposer** receives user goal, creates execution plan
2. **Team Assembler** receives plan, selects agents from marketplace
3. **Execution Coordinator** receives plan + assignments, executes tasks
4. **Progress Tracker** monitors execution in parallel, reports issues
5. **Result Synthesizer** receives all results, creates final deliverable

---

## Configuration

Each coordinating agent can be configured independently:

```json
{
  "coordinating_agents": {
    "GoalDecomposerAgent": {
      "enabled": true,
      "model": "gpt-4",
      "temperature": 0.7,
      "max_tasks_per_plan": 20,
      "complexity_threshold": "high"
    },
    "TeamAssemblerAgent": {
      "enabled": true,
      "model": "gpt-4",
      "temperature": 0.5,
      "max_team_size": 10,
      "prefer_local_agents": true,
      "marketplace_cache_ttl": 300
    },
    "ExecutionCoordinatorAgent": {
      "enabled": true,
      "max_parallel_tasks": 5,
      "task_timeout": 600,
      "retry_attempts": 3,
      "retry_delay": 10
    },
    "ProgressTrackerAgent": {
      "enabled": true,
      "monitoring_interval": 5,
      "alert_threshold": "high",
      "report_interval": 30
    },
    "ResultSynthesizerAgent": {
      "enabled": true,
      "model": "gpt-4",
      "temperature": 0.7,
      "include_metadata": true,
      "generate_summary": true
    }
  }
}
```

---

## Next Steps

1. Implement base coordinating agent framework
2. Build Goal Decomposer with LLM integration
3. Build Team Assembler with marketplace querying
4. Build Execution Coordinator with A2A client
5. Build Progress Tracker with monitoring
6. Build Result Synthesizer with output formatting
7. Test end-to-end coordination flow


