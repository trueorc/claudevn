# Slim Claude Code Specification

**Version**: 1.0.0
**Last Updated**: January 2026
**Status**: Design Specification

---

## Overview

Slim Claude Code is the **intent-based orchestration layer** that transforms natural language goals into executable work plans. It bridges human intent and AI execution, enabling ClaudeVN's core value proposition: AI determines how to approach work at the project level.

### Core Principle

> Humans express **what** they want. AI determines **how** to achieve it.

---

## Components

### 1. Goal Decomposer

Transforms a natural language goal into a structured set of issues with dependencies.

#### Input

```python
class GoalDecompositionRequest(BaseModel):
    goal_id: str                    # Reference to existing Goal
    goal_text: str                  # Natural language description
    project_context: dict           # Repository info, tech stack, conventions
    existing_issues: list[Issue]    # Current backlog for awareness
    constraints: Optional[dict]     # Budget, timeline, team size hints
```

#### Process

1. **Context Gathering**: Collect project information (tech stack, conventions, existing code patterns)
2. **Intent Parsing**: Use Claude to understand the goal's core objectives
3. **Task Identification**: Break goal into discrete, actionable issues
4. **Dependency Mapping**: Identify which issues block others
5. **Skill Assignment**: Determine required capabilities for each issue
6. **Priority Assignment**: Rank issues by importance and urgency

#### Output

```python
class GoalDecompositionResult(BaseModel):
    goal_id: str
    issues: list[DecomposedIssue]
    dependency_graph: dict[str, list[str]]  # issue_id -> blocked_by
    execution_phases: list[list[str]]       # Parallel execution groups
    confidence: float                        # 0-1 decomposition confidence
    reasoning: str                           # Explanation of approach
```

```python
class DecomposedIssue(BaseModel):
    temp_id: str                    # Temporary ID for dependency refs
    title: str
    description: str
    issue_type: IssueType           # feature, bug, refactor, test, docs
    priority: IssuePriority         # critical, high, normal, low
    area: IssueArea                 # frontend, backend, database, etc.
    required_skills: list[str]      # Skill IDs needed
    estimated_complexity: str       # xs, s, m, l, xl
    blocked_by: list[str]           # temp_ids of blocking issues
    acceptance_criteria: list[str]  # Definition of done
```

#### Claude Prompt Structure

```markdown
## Context
You are decomposing a goal into executable issues for a software project.

Project: {project_name}
Tech Stack: {tech_stack}
Conventions: {conventions}

## Goal
{goal_text}

## Existing Backlog
{existing_issues_summary}

## Constraints
{constraints}

## Instructions
Break this goal into discrete, implementable issues. For each issue:
1. Write a clear, actionable title
2. Describe what needs to be done (not how)
3. Identify dependencies on other issues
4. Assign appropriate priority and area
5. List required skills/capabilities
6. Define acceptance criteria

Think about:
- What must be done first? (dependencies)
- What can be done in parallel?
- What are the risks?
- Are there any missing pieces the user didn't mention?

Return structured JSON matching the schema.
```

---

### 2. Work Planner

Analyzes decomposed issues and creates an optimized execution plan.

#### Input

```python
class WorkPlanRequest(BaseModel):
    goal_id: str
    issues: list[DecomposedIssue]
    dependency_graph: dict[str, list[str]]
    available_compute: int              # Current compute capacity
    constraints: Optional[PlanConstraints]
```

```python
class PlanConstraints(BaseModel):
    max_parallel: Optional[int]         # Max concurrent issues
    priority_override: Optional[list[str]]  # Force these issues first
    deadline: Optional[datetime]        # Target completion
    excluded_skills: Optional[list[str]]  # Skills not available
```

#### Process

1. **Dependency Analysis**: Topological sort of issues
2. **Parallelization**: Identify issues that can run concurrently
3. **Resource Matching**: Map issues to available skills/compute
4. **Risk Assessment**: Identify blockers, unknowns, dependencies
5. **Phase Planning**: Group issues into execution phases
6. **Optimization**: Balance speed vs. resource utilization

#### Output

```python
class WorkPlan(BaseModel):
    goal_id: str
    phases: list[ExecutionPhase]
    estimated_duration: str             # Human-readable estimate
    critical_path: list[str]            # Issue IDs on critical path
    risks: list[PlanRisk]
    recommendations: list[str]
```

```python
class ExecutionPhase(BaseModel):
    phase_number: int
    issues: list[str]                   # Issue IDs to execute
    parallel: bool                      # Can these run concurrently?
    gate: Optional[str]                 # Approval needed before next phase?
    description: str                    # What this phase accomplishes
```

```python
class PlanRisk(BaseModel):
    risk_id: str
    description: str
    severity: str                       # low, medium, high
    mitigation: str                     # Suggested mitigation
    affected_issues: list[str]
```

---

## Integration Points

### With Issue Service

```python
# After decomposition and approval, create issues
async def create_issues_from_plan(
    goal_id: str,
    decomposition: GoalDecompositionResult,
    plan: WorkPlan
) -> IssueBatchCreateResponse:
    """Create all issues from approved plan."""

    issue_service = get_issue_service()

    # Map temp_ids to real issue IDs as we create
    id_mapping: dict[str, str] = {}

    for phase in plan.phases:
        for temp_id in phase.issues:
            issue_data = find_issue_by_temp_id(decomposition.issues, temp_id)

            # Resolve dependencies to real IDs
            real_blocked_by = [
                id_mapping[dep]
                for dep in issue_data.blocked_by
                if dep in id_mapping
            ]

            created = await issue_service.create_issue(
                IssueCreateRequest(
                    title=issue_data.title,
                    description=issue_data.description,
                    priority=issue_data.priority,
                    area=issue_data.area,
                    required_skills=issue_data.required_skills,
                    blocked_by=real_blocked_by,
                    goal_id=goal_id
                )
            )

            id_mapping[temp_id] = created.issue_id

    return IssueBatchCreateResponse(
        success=True,
        goal_id=goal_id,
        created_issues=[{"temp_id": k, "id": v} for k, v in id_mapping.items()]
    )
```

### With Work Orchestrator

The Work Orchestrator requires no changes. Once issues are created with proper dependencies, the existing orchestrator will:
1. Find issues with no blockers (ready state)
2. Assign to available compute
3. Track completion and unblock dependent issues

### With Serving UI

New UI components needed:

1. **Goal Input Form**
   - Rich text input for goal description
   - Optional constraints (timeline, priorities)
   - Submit for decomposition

2. **Plan Review Interface**
   - Visual dependency graph
   - Phase-by-phase breakdown
   - Edit/adjust before approval
   - Approve or request re-planning

3. **Execution Dashboard**
   - Phase progress indicators
   - Issue status within phases
   - Critical path highlighting

---

## API Endpoints

### Decompose Goal

```http
POST /api/v1/goals/{goal_id}/decompose
Content-Type: application/json

{
  "constraints": {
    "max_issues": 20,
    "focus_areas": ["backend", "api"]
  }
}
```

Response:
```json
{
  "goal_id": "goal-001",
  "decomposition_id": "decomp-abc123",
  "issues": [...],
  "dependency_graph": {...},
  "execution_phases": [[...], [...], ...],
  "confidence": 0.85,
  "reasoning": "Broke down into 8 issues across 3 phases..."
}
```

### Create Execution Plan

```http
POST /api/v1/goals/{goal_id}/plan
Content-Type: application/json

{
  "decomposition_id": "decomp-abc123",
  "constraints": {
    "max_parallel": 3
  }
}
```

### Approve and Execute Plan

```http
POST /api/v1/goals/{goal_id}/execute
Content-Type: application/json

{
  "plan_id": "plan-xyz789",
  "approved_by": "user-001"
}
```

This creates all issues and triggers the Work Orchestrator.

---

## Service Architecture

```python
class SlimClaudeCodeService:
    """Orchestrates goal decomposition and work planning."""

    def __init__(
        self,
        claude_client: ClaudeClient,
        issue_service: IssueService,
        skill_service: SkillSelectionService,
        project_service: ProjectService
    ):
        self.claude = claude_client
        self.issues = issue_service
        self.skills = skill_service
        self.projects = project_service

    async def decompose_goal(
        self,
        goal_id: str,
        constraints: Optional[dict] = None
    ) -> GoalDecompositionResult:
        """Decompose a goal into issues."""
        # 1. Gather context
        goal = await self.issues.get_goal(goal_id)
        project = await self.projects.get_project(goal.project_id)
        existing = await self.issues.list_issues(project_id=goal.project_id)

        # 2. Build prompt
        prompt = self._build_decomposition_prompt(goal, project, existing, constraints)

        # 3. Call Claude
        response = await self.claude.complete(prompt)

        # 4. Parse and validate
        result = self._parse_decomposition(response)

        # 5. Store for later approval
        await self._store_decomposition(goal_id, result)

        return result

    async def create_plan(
        self,
        goal_id: str,
        decomposition_id: str,
        constraints: Optional[PlanConstraints] = None
    ) -> WorkPlan:
        """Create execution plan from decomposition."""
        decomposition = await self._get_decomposition(decomposition_id)

        # Use Claude for intelligent planning
        prompt = self._build_planning_prompt(decomposition, constraints)
        response = await self.claude.complete(prompt)

        plan = self._parse_plan(response)
        await self._store_plan(goal_id, plan)

        return plan

    async def execute_plan(
        self,
        goal_id: str,
        plan_id: str,
        approved_by: str
    ) -> IssueBatchCreateResponse:
        """Execute approved plan by creating issues."""
        plan = await self._get_plan(plan_id)
        decomposition = await self._get_decomposition(plan.decomposition_id)

        # Create issues with proper dependencies
        result = await create_issues_from_plan(goal_id, decomposition, plan)

        # Log approval
        await self._log_execution(goal_id, plan_id, approved_by, result)

        return result
```

---

## Configuration

```python
class SlimClaudeCodeConfig(BaseModel):
    """Configuration for Slim Claude Code service."""

    # Claude settings
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3  # Lower for more consistent decomposition

    # Decomposition limits
    max_issues_per_goal: int = 50
    max_decomposition_depth: int = 3  # Nested sub-issues

    # Planning settings
    default_max_parallel: int = 5
    phase_gate_threshold: int = 5  # Issues before requiring approval gate

    # Storage
    decomposition_ttl_hours: int = 24  # How long to keep unapproved plans
```

---

## Error Handling

### Decomposition Failures

```python
class DecompositionError(Exception):
    """Goal could not be decomposed."""
    pass

class AmbiguousGoalError(DecompositionError):
    """Goal is too vague to decompose."""
    suggestion: str  # What to clarify

class InfeasibleGoalError(DecompositionError):
    """Goal cannot be achieved with available resources."""
    missing: list[str]  # What's missing
```

### Planning Failures

```python
class PlanningError(Exception):
    """Plan could not be created."""
    pass

class CyclicDependencyError(PlanningError):
    """Circular dependency detected."""
    cycle: list[str]  # Issue IDs in cycle

class ResourceConstraintError(PlanningError):
    """Cannot meet constraints with available resources."""
    constraint: str
    required: Any
    available: Any
```

---

## Metrics and Observability

### Key Metrics

| Metric | Description |
|--------|-------------|
| `decomposition_duration_seconds` | Time to decompose goal |
| `decomposition_issue_count` | Issues generated per goal |
| `decomposition_confidence` | Claude's confidence score |
| `plan_phase_count` | Phases in execution plan |
| `plan_approval_rate` | % of plans approved without edits |
| `execution_success_rate` | % of plans that complete successfully |

### Logging

```python
logger.info(
    "Goal decomposed",
    extra={
        "goal_id": goal_id,
        "issue_count": len(result.issues),
        "phase_count": len(result.execution_phases),
        "confidence": result.confidence,
        "duration_ms": duration
    }
)
```

---

## Security Considerations

1. **Prompt Injection**: Sanitize goal text before including in Claude prompts
2. **Resource Limits**: Cap max issues, phases, and Claude calls per goal
3. **Approval Required**: No automatic execution without human approval in v1.0
4. **Audit Trail**: Log all decompositions, plans, and approvals

---

## Future Enhancements (v1.1+)

1. **Result Synthesizer**: Combine completed work into coherent deliverable
2. **Learning Loop**: Improve decomposition based on execution outcomes
3. **Multi-Source Intents**: Accept goals from integrations (Jira, Slack, etc.)
4. **Autonomous Execution**: Skip approval for low-risk, small goals
5. **Cross-Project Planning**: Coordinate work across multiple projects

---

## Related Documents

- [ADR-004: Slim Claude Code Decision](../adr/004-slim-claude-code-orchestration.md)
- [v1.0 Architecture](../architecture/v1.0-architecture.md)
- [WorkMap Specification](./workmap.md)
- [MCP Tools Specification](./mcp-tools.md)
