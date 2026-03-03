"""claudevn_submit_decomposition tool - Return goal decomposition results.

This tool allows a compute instance to submit the results of goal decomposition
back to the serving component. The decomposition is performed by the compute
instance using Claude Code (with OAuth credentials), not by serving directly.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..models import MCPError

logger = logging.getLogger(__name__)


class DecomposedIssueInput(BaseModel):
    """A single decomposed issue from the compute instance."""
    temp_id: str = Field(..., description="Temporary ID (e.g., 'issue-1')")
    title: str = Field(..., description="Issue title")
    description: str = Field(default="", description="Issue description")
    issue_type: str = Field(default="feature", description="Issue type: feature, bug, refactor, test, docs")
    priority: str = Field(default="P2", description="Priority: P0, P1, P2, P3")
    area: str = Field(default="api", description="Area: api, database, frontend, infra, other")
    required_skills: List[str] = Field(default_factory=list, description="Required skill IDs")
    required_tools: List[str] = Field(default_factory=list, description="Runtime tools required (e.g., runtime:node, runtime:python:3.12)")
    estimated_complexity: str = Field(default="m", description="Complexity: xs, s, m, l, xl")
    blocked_by: List[str] = Field(default_factory=list, description="Temp IDs this issue is blocked by")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Acceptance criteria")


class SubmitDecompositionInput(BaseModel):
    """Input for claudevn_submit_decomposition tool."""
    decomposition_id: str = Field(..., description="Decomposition ID assigned by serving")
    goal_id: str = Field(..., description="Goal being decomposed")
    issues: List[DecomposedIssueInput] = Field(..., description="List of decomposed issues")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(default="", description="Explanation of decomposition approach")


class SubmitDecompositionResponse(BaseModel):
    """Response for claudevn_submit_decomposition tool."""
    acknowledged: bool
    decomposition_id: str
    goal_id: str
    issues_count: int
    status: str = Field(description="Status: received, stored, error")


async def submit_decomposition(
    input: SubmitDecompositionInput
) -> tuple[Optional[SubmitDecompositionResponse], Optional[MCPError]]:
    """Submit goal decomposition results from a compute instance.

    This tool is called by compute instances that have been assigned a
    goal decomposition task. The compute instance uses Claude Code to
    perform the actual decomposition (leveraging OAuth credentials),
    then submits the results back to serving via this tool.

    The serving component stores the results and can then be retrieved
    via the existing decomposition APIs.
    """
    logger.info(
        f"Received decomposition {input.decomposition_id} for goal {input.goal_id} "
        f"with {len(input.issues)} issues"
    )

    try:
        from git.redis_client import get_redis
        from models.goal_decomposer import (
            DecomposedIssue,
            EstimatedComplexity,
            GoalDecompositionResult,
        )

        # Idempotency check: skip if already stored
        redis = await get_redis()
        existing_key = f"claudevn:decomposition:{input.decomposition_id}"
        if await redis.exists(existing_key):
            logger.info(
                f"Decomposition {input.decomposition_id} already stored, "
                "skipping duplicate submission"
            )
            return SubmitDecompositionResponse(
                acknowledged=True,
                decomposition_id=input.decomposition_id,
                goal_id=input.goal_id,
                issues_count=len(input.issues),
                status="already_stored",
            ), None

        # Convert input issues to DecomposedIssue models
        decomposed_issues = []
        for issue_input in input.issues:
            try:
                complexity = EstimatedComplexity(issue_input.estimated_complexity.lower())
            except ValueError:
                complexity = EstimatedComplexity.M

            issue = DecomposedIssue(
                temp_id=issue_input.temp_id,
                title=issue_input.title,
                description=issue_input.description,
                issue_type=issue_input.issue_type,
                priority=issue_input.priority,
                area=issue_input.area,
                required_skills=issue_input.required_skills,
                required_tools=issue_input.required_tools,
                estimated_complexity=complexity,
                blocked_by=issue_input.blocked_by,
                acceptance_criteria=issue_input.acceptance_criteria,
            )
            decomposed_issues.append(issue)

        # Build dependency graph
        dependency_graph = {
            issue.temp_id: issue.blocked_by
            for issue in decomposed_issues
            if issue.blocked_by
        }

        # Calculate execution phases
        execution_phases = _calculate_execution_phases(decomposed_issues)

        # Create result object
        result = GoalDecompositionResult(
            goal_id=input.goal_id,
            decomposition_id=input.decomposition_id,
            issues=decomposed_issues,
            dependency_graph=dependency_graph,
            execution_phases=execution_phases,
            confidence=input.confidence,
            reasoning=input.reasoning,
        )

        # Store in Redis (redis already fetched above for idempotency check)
        key = f"claudevn:decomposition:{input.decomposition_id}"
        TTL_SECONDS = 24 * 3600  # 24 hours
        await redis.setex(key, TTL_SECONDS, result.model_dump_json())

        # Signal completion via Redis key (legacy fallback) and in-process asyncio.Event
        completion_key = f"claudevn:decomposition_complete:{input.decomposition_id}"
        await redis.setex(completion_key, 300, "1")  # 5 minute TTL for completion signal

        # In-process event: instant unblock for _wait_for_result() (no polling)
        try:
            from services.completion_events import signal as signal_completion
            signal_completion(input.decomposition_id)
        except Exception:
            pass  # Graceful degradation — legacy Redis polling still works

        # Persist decomposition_id on the goal record
        try:
            from services.goal_service import get_goal_service
            goal_service = get_goal_service()
            await goal_service.update_goal_decomposition_id(
                input.goal_id, input.decomposition_id
            )
        except Exception as e:
            logger.warning(f"Could not update goal with decomposition_id: {e}")

        logger.info(
            f"Stored decomposition {input.decomposition_id}: "
            f"{len(decomposed_issues)} issues, confidence {input.confidence:.2f}"
        )

        return SubmitDecompositionResponse(
            acknowledged=True,
            decomposition_id=input.decomposition_id,
            goal_id=input.goal_id,
            issues_count=len(decomposed_issues),
            status="stored",
        ), None

    except Exception as e:
        logger.error(f"Error storing decomposition: {e}", exc_info=True)
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=f"Failed to store decomposition: {str(e)}",
        )


def _calculate_execution_phases(issues: List[Any]) -> List[List[str]]:
    """Calculate execution phases using topological sort.

    Groups issues that can run in parallel into phases.
    """
    if not issues:
        return []

    # Build dependency counts
    in_degree = {issue.temp_id: 0 for issue in issues}
    dependents = {issue.temp_id: [] for issue in issues}

    for issue in issues:
        for dep in issue.blocked_by:
            if dep in in_degree:
                in_degree[issue.temp_id] += 1
                dependents[dep].append(issue.temp_id)

    phases = []

    while in_degree:
        # Find all issues with no remaining dependencies
        ready = [tid for tid, count in in_degree.items() if count == 0]

        if not ready:
            # Circular dependency detected
            logger.warning("Circular dependency detected in decomposition")
            phases.append(list(in_degree.keys()))
            break

        phases.append(ready)

        # Remove ready issues and update dependents
        for tid in ready:
            del in_degree[tid]
            for dependent in dependents.get(tid, []):
                if dependent in in_degree:
                    in_degree[dependent] -= 1

    return phases
