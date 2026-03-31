"""API endpoints for Slim Claude Code services.

Provides REST endpoints for:
- Auto-Process: /goals/{goal_id}/auto-process (decompose + create issues)
- Supplemental Decompose: /goals/{goal_id}/supplemental-decompose (re-invocable)
- Processing Status: /goals/{goal_id}/processing-status (poll for progress)
- Goal Decomposition: /goals/{goal_id}/decompose
- Work Planning: /goals/{goal_id}/plan
- Plan Execution: /goals/{goal_id}/execute
- Get Decomposition: /goals/{goal_id}/decompositions/{decomposition_id}
- Get Plan: /goals/{goal_id}/plans/{plan_id}
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from git.redis_client import get_redis
from models.characterization import CharacterizationRequest, CharacterizationResult
from models.goal_decomposer import GoalDecompositionResult
from models.work_map import (
    GoalCommentCreateRequest, IssueBatchCreateResponse, IssueCreateRequest,
    SupplementalDecomposeRequest, DecompositionTrigger,
)
from models.work_planner import PlanConstraints, WorkPlan
from services.characterization_service import get_characterization_service
from services.goal_comment_service import get_goal_comment_service
from services.goal_decomposer import get_goal_decomposer_service, DecompositionTimeoutError
from services.goal_service import get_goal_service
from services.project_service import get_project_service
from services.work_map_service import get_work_map_service
from services.work_planner import CyclicDependencyError, get_work_planner_service

logger = logging.getLogger(__name__)

# TTL for stored decompositions and plans (24 hours)
DECOMPOSITION_TTL_SECONDS = 24 * 3600
PLAN_TTL_SECONDS = 24 * 3600


# =============================================================================
# Request/Response Models
# =============================================================================


class DecomposeRequest(BaseModel):
    """Request body for goal decomposition."""

    constraints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional constraints (max_issues, focus_areas, etc.)",
    )


class CreatePlanRequest(BaseModel):
    """Request body for plan creation."""

    decomposition_id: str = Field(..., description="ID of decomposition to plan from")
    constraints: Optional[PlanConstraints] = Field(
        default=None, description="Optional planning constraints"
    )


class ExecutePlanRequest(BaseModel):
    """Request body for plan execution."""

    plan_id: str = Field(..., description="ID of plan to execute")
    approved_by: Optional[str] = Field(
        default=None, description="User ID approving execution"
    )


class AutoProcessRequest(BaseModel):
    """Request body for auto-process (decompose + create issues in one step)."""

    constraints: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional constraints (max_issues, focus_areas, etc.)",
    )


class AutoProcessResponse(BaseModel):
    """Response for auto-process endpoint."""

    success: bool
    goal_id: str
    decomposition_id: str
    created_issues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {temp_id, issue_id, title, status} mappings",
    )
    ready_count: int = 0
    backlog_count: int = 0
    confidence: float = 0.0
    reasoning: str = ""


class ProcessingStage(str, Enum):
    """Stages of goal auto-processing."""
    QUEUED = "queued"
    DECOMPOSING = "decomposing"
    CREATING_ISSUES = "creating_issues"
    CHARACTERIZING = "characterizing"
    COMPLETE = "complete"
    FAILED = "failed"


class AutoProcessAcceptedResponse(BaseModel):
    """Response returned immediately when auto-process is accepted."""
    goal_id: str
    status: str = "accepted"
    stage: ProcessingStage = ProcessingStage.QUEUED
    message: str = "Goal processing started. Poll /processing-status for progress."


class ProcessingStatusResponse(BaseModel):
    """Response for processing status polling endpoint."""
    goal_id: str
    stage: ProcessingStage
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[AutoProcessResponse] = None


# TTL for processing status in Redis (1 hour)
PROCESSING_STATUS_TTL_SECONDS = 3600


# =============================================================================
# Storage Helpers
# =============================================================================


async def _store_decomposition(result: GoalDecompositionResult) -> None:
    """Store decomposition result in Redis.

    Args:
        result: The decomposition result to store
    """
    redis = await get_redis()
    key = f"claudevn:decomposition:{result.decomposition_id}"
    data = result.model_dump_json()
    await redis.setex(key, DECOMPOSITION_TTL_SECONDS, data)
    logger.debug(f"Stored decomposition {result.decomposition_id}")


async def _get_decomposition(
    decomposition_id: str,
) -> Optional[GoalDecompositionResult]:
    """Retrieve stored decomposition from Redis.

    Args:
        decomposition_id: The decomposition ID to retrieve

    Returns:
        GoalDecompositionResult or None if not found
    """
    redis = await get_redis()
    key = f"claudevn:decomposition:{decomposition_id}"
    data = await redis.get(key)
    if data:
        return GoalDecompositionResult.model_validate_json(data)
    return None


async def _store_plan(plan: WorkPlan) -> None:
    """Store work plan in Redis.

    Args:
        plan: The work plan to store
    """
    redis = await get_redis()
    key = f"claudevn:plan:{plan.plan_id}"
    data = plan.model_dump_json()
    await redis.setex(key, PLAN_TTL_SECONDS, data)
    logger.debug(f"Stored plan {plan.plan_id}")


async def _set_processing_status(
    goal_id: str,
    stage: ProcessingStage,
    error: Optional[str] = None,
    result: Optional[AutoProcessResponse] = None,
) -> None:
    """Store processing status for a goal in Redis."""
    redis = await get_redis()
    key = f"claudevn:processing:{goal_id}"
    now = datetime.now(timezone.utc).isoformat()

    data: Dict[str, Any] = {"goal_id": goal_id, "stage": stage.value}

    # Preserve started_at from existing status
    existing = await redis.get(key)
    if existing:
        existing_data = json.loads(existing)
        data["started_at"] = existing_data.get("started_at", now)
    else:
        data["started_at"] = now

    if stage in (ProcessingStage.COMPLETE, ProcessingStage.FAILED):
        data["completed_at"] = now
    if error:
        data["error"] = error
    if result:
        data["result"] = result.model_dump()

    await redis.setex(key, PROCESSING_STATUS_TTL_SECONDS, json.dumps(data))

    # Push stage change to WebSocket subscribers in real-time
    try:
        from services.observability_event_bus import get_event_bus
        from models.observability import GoalProcessingStageEvent
        import uuid as _uuid

        event_bus = get_event_bus()
        if event_bus:
            previous_stage = existing_data.get("stage") if existing else None
            # Look up project_id from goal for frontend filtering
            project_id = None
            try:
                goal_key = f"claudevn:workmap:goal:{goal_id}"
                goal_data = await redis.hget(goal_key, "project_id")
                if goal_data:
                    project_id = goal_data
            except Exception:
                pass

            event = GoalProcessingStageEvent(
                event_id=f"gps_{_uuid.uuid4().hex[:12]}",
                goal_id=goal_id,
                project_id=project_id,
                stage=stage.value,
                previous_stage=previous_stage,
                error=error,
            )
            await event_bus.emit_event(event)
    except Exception as e:
        logger.debug(f"Could not emit processing stage event: {e}")


async def _get_processing_status(goal_id: str) -> Optional[ProcessingStatusResponse]:
    """Retrieve processing status for a goal from Redis."""
    redis = await get_redis()
    key = f"claudevn:processing:{goal_id}"
    data = await redis.get(key)
    if not data:
        return None
    parsed = json.loads(data)
    return ProcessingStatusResponse(**parsed)


async def _get_plan(plan_id: str) -> Optional[WorkPlan]:
    """Retrieve stored plan from Redis.

    Args:
        plan_id: The plan ID to retrieve

    Returns:
        WorkPlan or None if not found
    """
    redis = await get_redis()
    key = f"claudevn:plan:{plan_id}"
    data = await redis.get(key)
    if data:
        return WorkPlan.model_validate_json(data)
    return None


# =============================================================================
# Router Definitions
# =============================================================================

router = APIRouter(prefix="/goals", tags=["slim-claude-code"])


async def _build_project_context(project_id: str) -> Dict[str, Any]:
    """Build project context from actual project metadata.

    Loads the project and extracts tech_stack, conventions, name,
    description, and repo names. Falls back gracefully when metadata
    is incomplete.

    Args:
        project_id: The project ID to load context for

    Returns:
        Dict with project context for goal decomposition
    """
    project_context: Dict[str, Any] = {
        "tech_stack": "Not specified",
        "conventions": "Not specified",
    }

    project_service = get_project_service()
    project = await project_service.get_project(project_id)
    if project:
        project_context["project_name"] = project.name
        project_context["project_description"] = project.description or ""
        project_context["repos"] = [r.name for r in project.repos] if project.repos else []
        if project.metadata:
            project_context.update({
                k: v for k, v in project.metadata.items()
                if k in ("tech_stack", "conventions", "language", "framework")
            })

    return project_context


# =============================================================================
# Decompose Endpoint
# =============================================================================


@router.post(
    "/{goal_id}/decompose",
    response_model=GoalDecompositionResult,
    status_code=status.HTTP_201_CREATED,
)
async def decompose_goal(
    goal_id: str,
    request: Optional[DecomposeRequest] = None,
):
    """Decompose a goal into structured issues.

    Transforms a natural language goal into a set of discrete,
    actionable issues with dependencies using Claude.

    Args:
        goal_id: Reference to existing Goal
        request: Optional decomposition constraints

    Returns:
        GoalDecompositionResult with:
        - issues: List of DecomposedIssue
        - dependency_graph: Issue dependencies
        - execution_phases: Parallel execution groups
        - confidence: 0-1 confidence score
        - reasoning: Explanation of approach

    Raises:
        HTTPException 404: Goal not found
        HTTPException 500: Decomposition failed
    """
    decomposer = get_goal_decomposer_service()
    work_map_service = get_work_map_service()

    try:
        # Get goal from work map
        goal = await work_map_service.get_goal(goal_id)
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal '{goal_id}' not found",
            )

        # Validate goal has a project_id before decomposition
        if not goal.project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Goal must have a project_id before decomposition. "
                       "Update the goal with a project_id first.",
            )

        # Build project context from actual project metadata
        project_context = await _build_project_context(goal.project_id)

        # Get existing issues for context
        existing_issues = await work_map_service.get_goal_issues(goal_id)

        # Extract constraints from request
        constraints = None
        if request and request.constraints:
            constraints = request.constraints

        # Mark planning started for timeout tracking
        goal_service = get_goal_service()
        await goal_service.mark_planning_started(goal_id)

        # Decompose the goal
        result = await decomposer.decompose_goal(
            goal_id=goal_id,
            goal_text=goal.description,
            project_context=project_context,
            existing_issues=existing_issues,
            constraints=constraints,
        )

        # Store the decomposition for later retrieval
        await _store_decomposition(result)

        # Persist decomposition_id on the goal record
        await work_map_service.update_goal_decomposition_id(
            goal_id, result.decomposition_id
        )

        logger.info(
            f"Decomposed goal {goal_id} into {len(result.issues)} issues "
            f"(decomposition_id={result.decomposition_id})"
        )

        return result

    except HTTPException:
        raise
    except DecompositionTimeoutError as e:
        logger.error(f"Decomposition timed out for goal {goal_id}: {e}")
        goal_service = get_goal_service()
        await goal_service.mark_planning_failed(goal_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Decomposition timed out: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Failed to decompose goal {goal_id}: {e}")
        goal_service = get_goal_service()
        await goal_service.mark_planning_failed(goal_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to decompose goal: {str(e)}",
        )


# =============================================================================
# Auto-Process Endpoint (Decompose + Create Issues — async background)
# =============================================================================

# In-memory guard to prevent duplicate concurrent decompositions.
# The check-and-add is atomic (no await between) so asyncio cannot interleave.
_active_decompositions: set = set()


async def _auto_process_background(goal_id: str, constraints: Optional[Dict[str, Any]]) -> None:
    """Background task that performs decomposition and issue creation.

    Updates processing status in Redis at each stage so the frontend
    can poll for progress.
    """
    # Guard: prevent duplicate concurrent decompositions for the same goal.
    # This check + add has no await between them, so it is atomic in asyncio.
    if goal_id in _active_decompositions:
        logger.info(f"Skipping decomposition for goal {goal_id}: already in progress")
        return
    _active_decompositions.add(goal_id)

    decomposer = get_goal_decomposer_service()
    work_map_service = get_work_map_service()

    try:
        goal = await work_map_service.get_goal(goal_id)
        if not goal:
            await _set_processing_status(goal_id, ProcessingStage.FAILED, error="Goal not found")
            return

        # Build project context
        project_context = await _build_project_context(goal.project_id)

        # Mark planning started for timeout tracking
        goal_service = get_goal_service()
        await goal_service.mark_planning_started(goal_id)

        # Gather full conversation context for passthrough
        conversation_comments = []
        existing_decomposition_context = None
        try:
            comment_service = get_goal_comment_service()
            comments_response = await comment_service.list_comments(goal_id, limit=100)
            conversation_comments = [
                {
                    "content": c.content,
                    "created_by": c.created_by,
                    "evaluation_status": c.evaluation_status.value,
                    "priority": c.priority.value if c.priority else None,
                    "area": c.area.value if c.area else None,
                }
                for c in comments_response.items
            ]
        except Exception as e:
            logger.warning(f"Failed to load comments for context: {e}")

        # Load existing decomposition if present
        if goal.decomposition_id:
            try:
                redis = await get_redis()
                decomp_key = f"claudevn:decomposition:{goal.decomposition_id}"
                decomp_data = await redis.get(decomp_key)
                if decomp_data:
                    existing_decomposition_context = json.loads(decomp_data)
            except Exception as e:
                logger.warning(f"Failed to load existing decomposition: {e}")

        # =====================================================================
        # v2.0 DECOMPOSITION PIPELINE
        # Replaces v1.0 decompose → characterize → create issues flow.
        # Runs: LLM decompose → codebase analysis → build work units →
        #       validate → analyze environment
        # Each step emits events for Plan page observability.
        # =====================================================================
        await _set_processing_status(goal_id, ProcessingStage.DECOMPOSING)

        from services.decomposition.pipeline import DecompositionPipeline
        from services.decomposition.storage import (
            store_pipeline_result,
            get_project_units,
            rebuild_project_units_index,
            rebuild_project_environment,
        )

        # Load existing project plan for cross-directive awareness
        existing_plan = await get_project_units(goal.project_id or "")

        pipeline = DecompositionPipeline(repo_path=".")
        pipeline_result = await pipeline.run(
            goal_id=goal_id,
            project_id=goal.project_id or "",
            goal_text=goal.description,
            project_context=project_context,
            existing_issues=[],
            conversation_comments=conversation_comments,
            existing_project_units=existing_plan,
        )

        # Store pipeline result in Redis for Plan page
        await store_pipeline_result(
            project_id=goal.project_id or "",
            goal_id=goal_id,
            result_dict=pipeline_result.to_dict(),
        )

        # Rebuild unified project index and environment
        await rebuild_project_units_index(goal.project_id or "")
        await rebuild_project_environment(goal.project_id or "")

        if not pipeline_result.success:
            raise ValueError(f"Decomposition pipeline failed: {pipeline_result.error}")

        logger.info(
            f"v2.0 pipeline complete for {goal_id}: "
            f"{len(pipeline_result.work_units)} work units, "
            f"{len(pipeline_result.steps)} steps"
        )

        # Also create v1.0 backlog issues from work units (compatibility)
        await _set_processing_status(goal_id, ProcessingStage.CREATING_ISSUES)

        created_issues: List[Dict[str, Any]] = []
        issue_ids: List[str] = []

        for wu in pipeline_result.work_units:
            try:
                issue_request = IssueCreateRequest(
                    title=wu.description[:120],
                    description=wu.description,
                    issue_type="feature",
                    area="api",
                    priority="P2",
                    required_skills=[],
                    required_tools=[],
                    depends_on=[],
                    project_id=goal.project_id,
                    goal_id=goal_id,
                )
                issue = await work_map_service.create_issue(issue_request)
                issue_ids.append(issue.issue_id)
                created_issues.append({
                    "work_unit_id": wu.id,
                    "issue_id": issue.issue_id,
                    "title": issue.title,
                    "status": issue.status.value,
                })
            except Exception as issue_err:
                logger.error(f"Failed to create issue for work unit {wu.id}: {issue_err}")

        # Update goal with issue IDs
        if issue_ids:
            await work_map_service.update_goal_issues(goal_id, issue_ids)

        # Record decomposition pass
        decomposition_id = f"v2-{goal_id}"
        await work_map_service.update_goal_decomposition_id(goal_id, decomposition_id)
        await goal_service.record_decomposition_pass(
            goal_id=goal_id,
            decomposition_id=decomposition_id,
            trigger=DecompositionTrigger.INITIAL,
            issue_ids_created=issue_ids,
        )

        # Mark goal text as evaluated and persist completion data
        goal = await work_map_service.get_goal(goal_id)
        if goal:
            goal.goal_text_evaluated = True
            goal.completed_at = datetime.now(timezone.utc)
            goal.decomposition_reasoning = f"v2.0 pipeline: {len(pipeline_result.work_units)} work units"
            goal.updated_at = datetime.now(timezone.utc)

        # Add system comment documenting results
        try:
            comment_service = get_goal_comment_service()
            # Build step summary for comment
            step_summary = ", ".join(
                f"{s['name']}={s['status']}" for s in pipeline_result.to_dict().get("steps", [])
            )
            comment_lines = [
                f"**v2.0 Decomposition complete** — {len(pipeline_result.work_units)} work units",
                "",
                f"Pipeline steps: {step_summary}",
                "",
                f"**{len(created_issues)} backlog issues created:**",
            ]
            for item in created_issues:
                status_label = item["status"].upper()
                comment_lines.append(f"- [{status_label}] {item['title']}")

            if pipeline_result.environment:
                comment_lines.append("")
                comment_lines.append(f"**Compute environment:** {pipeline_result.environment.base_image} ({len(pipeline_result.environment.requirements)} requirements)")

            comment_request = GoalCommentCreateRequest(
                content="\n".join(comment_lines),
                created_by="system",
            )
            await comment_service.create_comment(goal_id, comment_request)
        except Exception as e:
            logger.warning(f"Failed to add system comment to goal {goal_id}: {e}")

        # Stage: COMPLETE
        result = AutoProcessResponse(
            success=True,
            goal_id=goal_id,
            decomposition_id=decomposition_id,
            created_issues=created_issues,
            ready_count=len(created_issues),
            backlog_count=0,
            confidence=0.0,
            reasoning=f"v2.0 pipeline: {len(pipeline_result.work_units)} work units",
        )
        await _set_processing_status(goal_id, ProcessingStage.COMPLETE, result=result)

        logger.info(
            f"Auto-processed goal {goal_id}: {len(pipeline_result.work_units)} work units, "
            f"{len(created_issues)} issues created"
        )

    except DecompositionTimeoutError as e:
        logger.error(f"Auto-process decomposition timed out for goal {goal_id}: {e}")
        goal_service = get_goal_service()
        await goal_service.mark_planning_failed(goal_id, str(e))
        await _set_processing_status(
            goal_id, ProcessingStage.FAILED, error=f"Decomposition timed out: {e}"
        )
    except Exception as e:
        logger.error(f"Failed to auto-process goal {goal_id}: {e}")
        goal_service = get_goal_service()
        await goal_service.mark_planning_failed(goal_id, str(e))
        await _set_processing_status(
            goal_id, ProcessingStage.FAILED, error=str(e)
        )
    finally:
        _active_decompositions.discard(goal_id)


@router.post(
    "/{goal_id}/auto-process",
    response_model=AutoProcessAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def auto_process_goal(
    goal_id: str,
    request: Optional[AutoProcessRequest] = None,
):
    """Start async goal decomposition and issue creation.

    Returns immediately with 202 Accepted. The actual processing runs
    in a background task. Poll GET /goals/{goal_id}/processing-status
    for progress updates.

    Args:
        goal_id: Goal to auto-process
        request: Optional constraints for decomposition

    Returns:
        AutoProcessAcceptedResponse with goal_id and initial status

    Raises:
        HTTPException 400: Goal missing project_id or already has issues
        HTTPException 404: Goal not found
    """
    work_map_service = get_work_map_service()

    # Validate goal synchronously before launching background task
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found",
        )

    if not goal.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal must have a project_id before auto-processing. "
                   "Update the goal with a project_id first.",
        )

    # Check if decomposition is already in progress (persistent guard)
    if goal.planning_started_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Goal '{goal_id}' already has decomposition in progress "
                   f"(started at {goal.planning_started_at.isoformat()})",
        )

    # Check if goal already has issues
    existing_issues = await work_map_service.get_goal_issues(goal_id)
    if existing_issues:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Goal '{goal_id}' already has {len(existing_issues)} issues created",
        )

    # Extract constraints
    constraints = None
    if request and request.constraints:
        constraints = request.constraints

    # Set initial processing status
    await _set_processing_status(goal_id, ProcessingStage.QUEUED)

    # Launch background task
    asyncio.create_task(_auto_process_background(goal_id, constraints))

    return AutoProcessAcceptedResponse(goal_id=goal_id)


# =============================================================================
# Supplemental Decomposition (Re-invocable from planner/worker feedback)
# =============================================================================


class SupplementalDecomposeResponse(BaseModel):
    """Response for supplemental decomposition endpoint."""
    goal_id: str
    status: str = "accepted"
    stage: ProcessingStage = ProcessingStage.QUEUED
    pass_number: int
    trigger: str
    message: str = "Supplemental decomposition started. Poll /processing-status for progress."


async def _supplemental_decompose_background(
    goal_id: str,
    request: SupplementalDecomposeRequest,
) -> None:
    """Background task for supplemental decomposition.

    Similar to auto-process but:
    - Passes existing issues as context (not empty list)
    - Only creates NEW issues (doesn't replace existing)
    - Records the decomposition pass on the goal
    - Includes gap description and trigger context
    """
    decomposer = get_goal_decomposer_service()
    work_map_service = get_work_map_service()

    try:
        goal = await work_map_service.get_goal(goal_id)
        if not goal:
            await _set_processing_status(goal_id, ProcessingStage.FAILED, error="Goal not found")
            return

        # Build project context
        project_context = await _build_project_context(goal.project_id)

        # Mark planning started
        goal_service = get_goal_service()
        await goal_service.mark_planning_started(goal_id)

        # Gather existing issues for this goal (critical for supplemental)
        existing_issues = await work_map_service.get_goal_issues(goal_id)

        # Gather conversation comments
        conversation_comments = []
        try:
            comment_service = get_goal_comment_service()
            comments_response = await comment_service.list_comments(goal_id, limit=100)
            conversation_comments = [
                {
                    "content": c.content,
                    "created_by": c.created_by,
                    "evaluation_status": c.evaluation_status.value,
                    "priority": c.priority.value if c.priority else None,
                    "area": c.area.value if c.area else None,
                }
                for c in comments_response.items
            ]
        except Exception as e:
            logger.warning(f"Failed to load comments for supplemental context: {e}")

        # Load existing decomposition context
        existing_decomposition_context = None
        if goal.decomposition_id:
            try:
                redis = await get_redis()
                decomp_key = f"claudevn:decomposition:{goal.decomposition_id}"
                decomp_data = await redis.get(decomp_key)
                if decomp_data:
                    existing_decomposition_context = json.loads(decomp_data)
            except Exception as e:
                logger.warning(f"Failed to load existing decomposition: {e}")

        # Build supplemental context
        pass_number = len(goal.decomposition_passes) + 1
        supplemental_context = {
            "trigger": request.trigger.value,
            "triggered_by": request.triggered_by,
            "gap_description": request.gap_description,
            "context": request.context,
            "pass_number": pass_number,
        }

        # Stage: DECOMPOSING + CHARACTERIZING
        # Pipeline: Decompose → Characterize → Create Issues (per spec Section 5)
        await _set_processing_status(goal_id, ProcessingStage.DECOMPOSING)

        decomposition, characterization_map = await decomposer.decompose_and_characterize(
            goal_id=goal_id,
            goal_text=goal.description,
            project_id=goal.project_id or "",
            project_context=project_context,
            existing_issues=existing_issues,
            constraints=request.constraints,
            conversation_comments=conversation_comments,
            existing_decomposition=existing_decomposition_context,
            supplemental_context=supplemental_context,
        )

        # Store decomposition
        await _store_decomposition(decomposition)

        if characterization_map:
            await _set_processing_status(goal_id, ProcessingStage.CHARACTERIZING)

        # Stage: CREATING_ISSUES (with characterization metadata)
        await _set_processing_status(goal_id, ProcessingStage.CREATING_ISSUES)

        issue_data_list = decomposer.map_to_issue_models(
            decomposed_issues=decomposition.issues,
            goal_id=goal_id,
            characterization_results=characterization_map,
        )

        # Use execution_phases for ordering
        issue_order = []
        for phase in decomposition.execution_phases:
            for temp_id in phase:
                issue_order.append(temp_id)
        for issue_data in issue_data_list:
            if issue_data["temp_id"] not in issue_order:
                issue_order.append(issue_data["temp_id"])

        # Build map of existing issue IDs for dependency resolution
        existing_issue_ids = {i.issue_id for i in existing_issues}

        temp_to_real: Dict[str, str] = {}
        created_issues: List[Dict[str, Any]] = []
        ready_count = 0
        backlog_count = 0
        failed_issues: List[str] = []

        for temp_id in issue_order:
            issue_data = next(
                (d for d in issue_data_list if d["temp_id"] == temp_id), None
            )
            if not issue_data:
                continue

            # Map temp_id dependencies to real IDs
            real_depends_on = []
            for blocked_by_temp in issue_data.get("blocked_by_temp_ids", []):
                if blocked_by_temp in temp_to_real:
                    real_depends_on.append(temp_to_real[blocked_by_temp])
                elif blocked_by_temp in existing_issue_ids:
                    real_depends_on.append(blocked_by_temp)

            try:
                issue_request = IssueCreateRequest(
                    title=issue_data["title"],
                    description=issue_data["description"],
                    issue_type=issue_data["type"],
                    area=issue_data["area"],
                    priority=issue_data["priority"],
                    required_skills=issue_data.get("required_skills", []),
                    required_tools=issue_data.get("required_tools", []),
                    depends_on=real_depends_on,
                    project_id=goal.project_id,
                    goal_id=goal_id,
                    ontology_tags=issue_data.get("ontology_tags"),
                )

                issue = await work_map_service.create_issue(issue_request)
                temp_to_real[temp_id] = issue.issue_id

                created_issues.append({
                    "temp_id": temp_id,
                    "issue_id": issue.issue_id,
                    "title": issue.title,
                    "status": issue.status.value,
                })

                if issue.status.value == "ready":
                    ready_count += 1
                else:
                    backlog_count += 1
            except Exception as issue_err:
                logger.error(
                    f"Failed to create supplemental issue '{issue_data.get('title', temp_id)}' "
                    f"for goal {goal_id}: {issue_err}"
                )
                failed_issues.append(temp_id)

        if failed_issues and not created_issues:
            raise ValueError(
                f"All {len(failed_issues)} supplemental issues failed for goal {goal_id}"
            )

        # Record decomposition pass on the goal
        new_issue_ids = [item["issue_id"] for item in created_issues]
        await goal_service.record_decomposition_pass(
            goal_id=goal_id,
            decomposition_id=decomposition.decomposition_id,
            trigger=request.trigger,
            issue_ids_created=new_issue_ids,
            triggered_by=request.triggered_by,
            trigger_context=request.gap_description,
        )

        # Create or update bucket tree with new items
        try:
            from services.bucket_tree_store import create_initial_bucket_tree
            # create_initial_bucket_tree skips if tree already exists,
            # and trigger_bucket_tree_reorganization handles existing trees.
            # For supplemental, we need to handle both cases:
            # gather ALL issues (existing + new) for a complete tree.
            all_issues = await work_map_service.get_goal_issues(goal_id)
            if all_issues and goal.project_id:
                from models.goal_decomposer import DecomposedIssue
                all_decomposed = []
                full_dep_graph = {}
                for issue in all_issues:
                    all_decomposed.append(DecomposedIssue(
                        temp_id=issue.issue_id,
                        title=issue.title,
                        description=issue.description,
                        issue_type=issue.issue_type.value if hasattr(issue.issue_type, 'value') else str(issue.issue_type),
                        priority=issue.priority.value if hasattr(issue.priority, 'value') else str(issue.priority),
                        blocked_by=issue.depends_on,
                    ))
                    if issue.depends_on:
                        full_dep_graph[issue.issue_id] = issue.depends_on

                await create_initial_bucket_tree(
                    project_id=goal.project_id,
                    decomposed_issues=all_decomposed,
                    dependency_graph=full_dep_graph,
                    characterization_map=characterization_map,
                    replace_existing=True,
                )
        except Exception as bt_err:
            logger.warning(
                f"Failed to create/update bucket tree for supplemental "
                f"decomposition of goal {goal_id}: {bt_err}"
            )

        # Add system comment documenting results
        try:
            comment_service = get_goal_comment_service()
            trigger_label = request.trigger.value.replace("_", " ").title()
            characterized_count = len(characterization_map)
            comment_lines = [
                f"**Supplemental decomposition (pass #{pass_number})** "
                f"(trigger: {trigger_label}, confidence: {decomposition.confidence:.0%})",
                "",
                f"{decomposition.reasoning}",
                "",
                f"**{len(created_issues)} new issues created** "
                f"({ready_count} ready, {backlog_count} backlog, "
                f"{characterized_count} characterized):",
            ]
            for item in created_issues:
                status_label = item["status"].upper()
                comment_lines.append(f"- [{status_label}] {item['title']}")

            comment_request = GoalCommentCreateRequest(
                content="\n".join(comment_lines),
                created_by="system",
            )
            await comment_service.create_comment(goal_id, comment_request)
        except Exception as e:
            logger.warning(f"Failed to add system comment for supplemental decomposition: {e}")

        # Stage: COMPLETE
        result = AutoProcessResponse(
            success=True,
            goal_id=goal_id,
            decomposition_id=decomposition.decomposition_id,
            created_issues=created_issues,
            ready_count=ready_count,
            backlog_count=backlog_count,
            confidence=decomposition.confidence,
            reasoning=decomposition.reasoning,
        )
        await _set_processing_status(goal_id, ProcessingStage.COMPLETE, result=result)

        logger.info(
            f"Supplemental decomposition for goal {goal_id} (pass #{pass_number}): "
            f"created {len(created_issues)} issues "
            f"(trigger={request.trigger.value}, "
            f"ready={ready_count}, backlog={backlog_count})"
        )

    except DecompositionTimeoutError as e:
        logger.error(f"Supplemental decomposition timed out for goal {goal_id}: {e}")
        goal_service = get_goal_service()
        await goal_service.mark_planning_failed(goal_id, str(e))
        await _set_processing_status(
            goal_id, ProcessingStage.FAILED, error=f"Decomposition timed out: {e}"
        )
    except Exception as e:
        logger.error(f"Failed supplemental decomposition for goal {goal_id}: {e}")
        goal_service = get_goal_service()
        await goal_service.mark_planning_failed(goal_id, str(e))
        await _set_processing_status(
            goal_id, ProcessingStage.FAILED, error=str(e)
        )


@router.post(
    "/{goal_id}/supplemental-decompose",
    response_model=SupplementalDecomposeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def supplemental_decompose_goal(
    goal_id: str,
    request: Optional[SupplementalDecomposeRequest] = None,
):
    """Trigger supplemental decomposition for an existing goal.

    Re-invocable decomposition that identifies additional missing work
    based on planner gaps, worker feedback, or manual request. Unlike
    auto-process, this endpoint:
    - Requires the goal to already have issues (initial decomposition done)
    - Passes existing issues as context to avoid duplication
    - Only creates NEW issues, preserving existing work
    - Records the decomposition pass in the goal's history

    Args:
        goal_id: Goal to supplementally decompose
        request: Trigger context and constraints

    Returns:
        SupplementalDecomposeResponse with accepted status

    Raises:
        HTTPException 400: Goal missing project_id or no initial decomposition
        HTTPException 404: Goal not found
    """
    work_map_service = get_work_map_service()

    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found",
        )

    if not goal.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal must have a project_id before supplemental decomposition.",
        )

    # Supplemental decomposition requires initial decomposition to have been done
    existing_issues = await work_map_service.get_goal_issues(goal_id)
    if not existing_issues and not goal.decomposition_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Goal '{goal_id}' has no initial decomposition. "
                   "Use auto-process for initial decomposition first.",
        )

    if request is None:
        request = SupplementalDecomposeRequest()

    pass_number = len(goal.decomposition_passes) + 1

    # Set initial processing status
    await _set_processing_status(goal_id, ProcessingStage.QUEUED)

    # Launch background task
    asyncio.create_task(_supplemental_decompose_background(goal_id, request))

    return SupplementalDecomposeResponse(
        goal_id=goal_id,
        pass_number=pass_number,
        trigger=request.trigger.value,
    )


# =============================================================================
# Processing Status Endpoint (Poll for auto-process progress)
# =============================================================================


@router.get(
    "/{goal_id}/processing-status",
    response_model=ProcessingStatusResponse,
)
async def get_processing_status(goal_id: str):
    """Poll for auto-process progress.

    Returns the current stage of goal processing. Frontend should poll
    this endpoint every 2-3 seconds during processing.

    Stages: queued -> decomposing -> creating_issues -> complete/failed

    Args:
        goal_id: Goal ID to check status for

    Returns:
        ProcessingStatusResponse with current stage and optional result

    Raises:
        HTTPException 404: No processing status found for this goal
    """
    status_data = await _get_processing_status(goal_id)

    if not status_data:
        # Check if goal exists and is in PLANNING state (might be a page refresh
        # where processing status expired but goal is still being processed)
        goal_service = get_goal_service()
        goal = await goal_service.get_goal(goal_id)
        if goal and goal.planning_started_at and goal.status.value == "planning":
            return ProcessingStatusResponse(
                goal_id=goal_id,
                stage=ProcessingStage.DECOMPOSING,
                started_at=goal.planning_started_at.isoformat(),
            )

        raise HTTPException(
            status_code=404,
            detail=f"No processing status found for goal '{goal_id}'",
        )

    return status_data


# =============================================================================
# Get Decomposition Endpoint
# =============================================================================


@router.get(
    "/{goal_id}/decompositions/{decomposition_id}",
    response_model=GoalDecompositionResult,
)
async def get_decomposition(goal_id: str, decomposition_id: str):
    """Get a stored decomposition by ID.

    Args:
        goal_id: Goal ID (for URL consistency)
        decomposition_id: Decomposition ID to retrieve

    Returns:
        GoalDecompositionResult

    Raises:
        HTTPException 404: Decomposition not found or expired
    """
    result = await _get_decomposition(decomposition_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decomposition '{decomposition_id}' not found or expired",
        )

    # Verify goal_id matches
    if result.goal_id != goal_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decomposition '{decomposition_id}' does not belong to goal '{goal_id}'",
        )

    return result


# =============================================================================
# Create Plan Endpoint
# =============================================================================


@router.post(
    "/{goal_id}/plan",
    response_model=WorkPlan,
    status_code=status.HTTP_201_CREATED,
)
async def create_plan(
    goal_id: str,
    request: CreatePlanRequest,
):
    """Create an execution plan from goal decomposition.

    Analyzes decomposed issues and creates an optimized execution plan
    with phased execution, critical path analysis, and risk assessment.

    Args:
        goal_id: Reference to goal being planned
        request: Plan creation request with decomposition_id and optional constraints

    Returns:
        WorkPlan with:
        - phases: Execution phases with parallel grouping
        - estimated_duration: Human-readable estimate
        - critical_path: Issues affecting total duration
        - risks: Identified risks and mitigations
        - recommendations: Optimization suggestions

    Raises:
        HTTPException 404: Goal or decomposition not found
        HTTPException 400: Cyclic dependency detected
        HTTPException 500: Planning failed
    """
    planner = get_work_planner_service()
    work_map_service = get_work_map_service()

    try:
        # Verify goal exists
        goal = await work_map_service.get_goal(goal_id)
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal '{goal_id}' not found",
            )

        # Load decomposition
        decomposition = await _get_decomposition(request.decomposition_id)
        if not decomposition:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Decomposition '{request.decomposition_id}' not found or expired",
            )

        # Verify decomposition belongs to goal
        if decomposition.goal_id != goal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Decomposition '{request.decomposition_id}' does not belong to goal '{goal_id}'",
            )

        # Create plan
        plan = await planner.create_plan_from_decomposition(
            decomposition=decomposition,
            constraints=request.constraints,
        )

        # Store the plan for later retrieval
        await _store_plan(plan)

        logger.info(
            f"Created plan {plan.plan_id} for goal {goal_id} "
            f"with {len(plan.phases)} phases"
        )

        return plan

    except CyclicDependencyError as e:
        logger.warning(f"Cyclic dependency in plan for goal {goal_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cyclic dependency detected: {str(e)}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create plan for goal {goal_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create plan: {str(e)}",
        )


# =============================================================================
# Get Plan Endpoint
# =============================================================================


@router.get(
    "/{goal_id}/plans/{plan_id}",
    response_model=WorkPlan,
)
async def get_plan(goal_id: str, plan_id: str):
    """Get a stored plan by ID.

    Args:
        goal_id: Goal ID (for URL consistency)
        plan_id: Plan ID to retrieve

    Returns:
        WorkPlan

    Raises:
        HTTPException 404: Plan not found or expired
    """
    plan = await _get_plan(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' not found or expired",
        )

    # Verify goal_id matches
    if plan.goal_id != goal_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_id}' does not belong to goal '{goal_id}'",
        )

    return plan


# =============================================================================
# Execute Plan Endpoint
# =============================================================================


@router.post(
    "/{goal_id}/execute",
    response_model=IssueBatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_plan(
    goal_id: str,
    request: ExecutePlanRequest,
):
    """Execute an approved plan by creating all issues.

    Takes an approved WorkPlan and creates all decomposed issues
    with proper dependencies, then updates the goal status.

    Args:
        goal_id: Goal being executed
        request: Execution request with plan_id and optional approver

    Returns:
        IssueBatchCreateResponse with:
        - success: Whether execution succeeded
        - created_issues: List of created issue mappings (temp_id -> real_id)
        - ready_count: Count of issues ready to work
        - backlog_count: Count of issues in backlog

    Raises:
        HTTPException 404: Goal, plan, or decomposition not found
        HTTPException 400: Plan already executed or invalid state
        HTTPException 500: Execution failed
    """
    work_map_service = get_work_map_service()
    decomposer = get_goal_decomposer_service()

    try:
        # Verify goal exists
        goal = await work_map_service.get_goal(goal_id)
        if not goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal '{goal_id}' not found",
            )

        # Check if goal already has issues
        existing_issues = await work_map_service.get_goal_issues(goal_id)
        if existing_issues:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Goal '{goal_id}' already has {len(existing_issues)} issues created",
            )

        # Load plan
        plan = await _get_plan(request.plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan '{request.plan_id}' not found or expired",
            )

        # Verify plan belongs to goal
        if plan.goal_id != goal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Plan '{request.plan_id}' does not belong to goal '{goal_id}'",
            )

        # Load decomposition for issue details
        decomposition = await _get_decomposition(plan.decomposition_id)
        if not decomposition:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Decomposition '{plan.decomposition_id}' not found or expired",
            )

        # Map decomposed issues to IssueCreateRequest format
        issue_data_list = decomposer.map_to_issue_models(
            decomposed_issues=decomposition.issues,
            goal_id=goal_id,
        )

        # Build temp_id -> real dependency mapping as issues are created
        temp_to_real: Dict[str, str] = {}
        created_issues: List[Dict[str, Any]] = []
        ready_count = 0
        backlog_count = 0

        # Sort issues by execution phase for proper dependency ordering
        issue_order = []
        for phase in plan.phases:
            for issue_temp_id in phase.issues:
                issue_order.append(issue_temp_id)

        # Add any issues not in phases (edge case)
        for issue_data in issue_data_list:
            if issue_data["temp_id"] not in issue_order:
                issue_order.append(issue_data["temp_id"])

        # Create issues in order
        for temp_id in issue_order:
            # Find issue data
            issue_data = next(
                (d for d in issue_data_list if d["temp_id"] == temp_id), None
            )
            if not issue_data:
                continue

            # Map temp_id dependencies to real IDs
            real_depends_on = []
            for blocked_by_temp in issue_data.get("blocked_by_temp_ids", []):
                if blocked_by_temp in temp_to_real:
                    real_depends_on.append(temp_to_real[blocked_by_temp])

            # Create issue request
            issue_request = IssueCreateRequest(
                title=issue_data["title"],
                description=issue_data["description"],
                issue_type=issue_data["type"],
                area=issue_data["area"],
                priority=issue_data["priority"],
                required_skills=issue_data.get("required_skills", []),
                required_tools=issue_data.get("required_tools", []),
                depends_on=real_depends_on,
                project_id=goal.project_id,
                goal_id=goal_id,
            )

            # Create the issue
            issue = await work_map_service.create_issue(issue_request)
            temp_to_real[temp_id] = issue.issue_id

            created_issues.append({
                "temp_id": temp_id,
                "issue_id": issue.issue_id,
                "title": issue.title,
                "status": issue.status.value,
            })

            if issue.status.value == "ready":
                ready_count += 1
            else:
                backlog_count += 1

        # Update goal with issue IDs and decomposition reference
        issue_ids = [item["issue_id"] for item in created_issues]
        await work_map_service.update_goal_issues(goal_id, issue_ids)
        await work_map_service.update_goal_decomposition_id(
            goal_id, plan.decomposition_id
        )

        # Create initial bucket tree for execution plan display
        try:
            from services.bucket_tree_store import create_initial_bucket_tree, get_bucket_tree_store
            await create_initial_bucket_tree(
                project_id=goal.project_id or "",
                decomposed_issues=decomposition.issues,
                dependency_graph=decomposition.dependency_graph,
            )
            # Remap temp IDs (e.g. "issue-1") to real persisted issue IDs
            if temp_to_real:
                bt_store = get_bucket_tree_store()
                tree = await bt_store.load(goal.project_id or "")
                if tree:
                    tree.remap_item_ids(temp_to_real)
                    await bt_store.save(tree)
        except Exception as bt_err:
            logger.warning(
                f"Failed to create initial bucket tree for goal {goal_id}: {bt_err}"
            )

        logger.info(
            f"Executed plan {request.plan_id} for goal {goal_id}: "
            f"created {len(created_issues)} issues "
            f"(ready={ready_count}, backlog={backlog_count})"
        )

        return IssueBatchCreateResponse(
            success=True,
            goal_id=goal_id,
            created_issues=created_issues,
            ready_count=ready_count,
            backlog_count=backlog_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute plan {request.plan_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute plan: {str(e)}",
        )
