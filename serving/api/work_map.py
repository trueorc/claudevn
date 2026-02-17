"""API endpoints for Work Map management.

Provides endpoints for:
- Goals: High-level objectives (/api/v1/goals)
- Issues: Units of work (/api/v1/issues)
- Work Items: Ephemeral assignments (/api/v1/work)
- WorkMap View: Aggregated views (/api/v1/workmap)
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from models.work_map import (
    # Goal models
    Goal, GoalStatus, GoalProgressMetrics, GoalCreateRequest, GoalListResponse, GoalDeleteResponse,
    GoalEvaluationSummary, EvaluationItemStatus,
    GoalAdjustIntentRequest, GoalConflictListResponse, GoalSetReconciliationWeightRequest,
    DecompositionPass,
    # Goal comment models
    GoalComment, GoalCommentCreateRequest, GoalCommentUpdateRequest,
    GoalCommentListResponse, EvaluationStatus,
    # Rollup models
    RollupStatusResponse, RollupConfig,
    # Issue models
    Issue, IssueStatus, IssueType, IssueArea, IssuePriority,
    IssueCreateRequest, IssueBatchCreateRequest, IssueBatchCreateResponse,
    IssueUpdateRequest, IssueListResponse, IssueStats, IssueResult, IssueHistory,
    # Release models
    Release, ReleaseStatus, ReleaseCreateRequest, ReleaseUpdateRequest, ReleaseListResponse,
    # Work item models
    WorkItem, WorkStatus, WorkPriority, WorkCreateRequest,
    WorkUpdateRequest, WorkAssignment, ProgressReport,
    WorkListResponse, WorkStats, BlockerType
)
from services.work_map_service import get_work_map_service
from services.goal_service import get_goal_service
from services.goal_comment_service import get_goal_comment_service
from services.goal_intent_service import get_goal_intent_service
from services.goal_evaluation_service import get_goal_evaluation_service
from services.comment_rollup_service import get_comment_rollup_service
from services.release_service import get_release_service
from services.bucket_tree_store import get_bucket_tree_store

logger = logging.getLogger(__name__)

# Create routers for each entity type
router = APIRouter(prefix="/work", tags=["work"])
goals_router = APIRouter(prefix="/goals", tags=["goals"])
issues_router = APIRouter(prefix="/issues", tags=["issues"])
releases_router = APIRouter(prefix="/releases", tags=["releases"])
workmap_router = APIRouter(prefix="/workmap", tags=["workmap"])


# ============ Stats Endpoint (must be before /{work_id}) ============

@router.get("/stats", response_model=WorkStats)
async def get_stats():
    """Get work map statistics.

    Returns:
        Work statistics including counts by status, priority, project
    """
    service = get_work_map_service()
    return await service.get_stats()


# ============ Assignment Endpoint (must be before /{work_id}) ============

@router.post("/next-assignment", response_model=Optional[WorkAssignment])
async def get_next_assignment(
    compute_id: str = Query(..., description="Compute instance ID"),
    capabilities: str = Query("", description="Comma-separated capability tags")
):
    """Get the next work assignment for a compute instance.

    Matches work based on required capabilities and dependency status.
    Highest priority items with met dependencies are assigned first.

    Args:
        compute_id: The compute instance requesting work
        capabilities: Comma-separated list of capability tags

    Returns:
        Work assignment if available, null otherwise
    """
    service = get_work_map_service()

    cap_list = [c.strip() for c in capabilities.split(",") if c.strip()]

    assignment = await service.get_next_assignment(compute_id, cap_list)

    if assignment:
        logger.info(f"Assigned work {assignment.work_id} to compute {compute_id}")
    else:
        logger.debug(f"No work available for compute {compute_id}")

    return assignment


# ============ Work CRUD Endpoints ============

@router.get("", response_model=WorkListResponse)
async def list_work(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    assigned_to: Optional[str] = Query(None, description="Filter by assignee"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """List work items with optional filtering.

    Args:
        status_filter: Filter by work status
        project_id: Filter by project ID
        assigned_to: Filter by compute instance ID
        priority: Filter by priority level
        limit: Maximum number of items

    Returns:
        List of work items with statistics
    """
    service = get_work_map_service()

    work_status = None
    if status_filter:
        try:
            work_status = WorkStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: {[s.value for s in WorkStatus]}"
            )

    work_priority = None
    if priority:
        try:
            work_priority = WorkPriority(priority)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {priority}. Must be one of: {[p.value for p in WorkPriority]}"
            )

    return await service.list_work(
        status=work_status,
        project_id=project_id,
        assigned_to=assigned_to,
        priority=work_priority,
        limit=limit
    )


@router.post("", response_model=WorkItem, status_code=status.HTTP_201_CREATED)
async def create_work(request: WorkCreateRequest):
    """Create a new work item.

    Args:
        request: Work creation request

    Returns:
        Created work item
    """
    service = get_work_map_service()

    try:
        work = await service.create_work(request)
        logger.info(f"Created work item {work.work_id}")
        return work
    except Exception as e:
        logger.error(f"Failed to create work item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create work item"
        )


@router.get("/{work_id}", response_model=WorkItem)
async def get_work(work_id: str):
    """Get a specific work item by ID.

    Args:
        work_id: Work item ID

    Returns:
        Work item details

    Raises:
        HTTPException: If work item not found
    """
    service = get_work_map_service()
    work = await service.get_work(work_id)

    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item '{work_id}' not found"
        )

    return work


@router.put("/{work_id}", response_model=WorkItem)
async def update_work(work_id: str, request: WorkUpdateRequest):
    """Update a work item.

    Args:
        work_id: Work item ID
        request: Update request

    Returns:
        Updated work item

    Raises:
        HTTPException: If work item not found
    """
    service = get_work_map_service()
    work = await service.update_work(work_id, request)

    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item '{work_id}' not found"
        )

    return work


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work(work_id: str):
    """Delete a work item.

    Args:
        work_id: Work item ID

    Raises:
        HTTPException: If work item not found
    """
    service = get_work_map_service()
    deleted = await service.delete_work(work_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item '{work_id}' not found"
        )


# ============ Status Operations ============

@router.post("/{work_id}/assign", response_model=WorkAssignment)
async def assign_work(
    work_id: str,
    compute_id: str = Query(..., description="Compute instance to assign to"),
    skills: str = Query("", description="Comma-separated skill IDs")
):
    """Assign work to a compute instance.

    Args:
        work_id: Work item ID
        compute_id: Compute instance ID
        skills: Comma-separated skill IDs

    Returns:
        Work assignment

    Raises:
        HTTPException: If assignment fails
    """
    service = get_work_map_service()

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]

    assignment = await service.assign_work(work_id, compute_id, skill_list)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign work item '{work_id}'. Check status and dependencies."
        )

    return assignment


@router.post("/{work_id}/unassign", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_work(work_id: str):
    """Unassign work from a compute instance.

    Args:
        work_id: Work item ID

    Raises:
        HTTPException: If unassignment fails
    """
    service = get_work_map_service()
    unassigned = await service.unassign_work(work_id)

    if not unassigned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot unassign work item '{work_id}'"
        )


@router.post("/{work_id}/status", response_model=WorkItem)
async def update_status(
    work_id: str,
    new_status: str = Query(..., alias="status", description="New status"),
    compute_id: Optional[str] = Query(None, description="Compute ID for authorization")
):
    """Update work status.

    Args:
        work_id: Work item ID
        new_status: New status value
        compute_id: Optional compute ID for authorization check

    Returns:
        Updated work item

    Raises:
        HTTPException: If status update fails
    """
    service = get_work_map_service()

    try:
        work_status = WorkStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {new_status}. Must be one of: {[s.value for s in WorkStatus]}"
        )

    work = await service.update_status(work_id, work_status, compute_id)

    if not work:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update status for work item '{work_id}'. Check authorization and transition rules."
        )

    return work


@router.post("/{work_id}/progress", response_model=WorkItem)
async def report_progress(work_id: str, report: ProgressReport):
    """Report progress on work.

    Args:
        work_id: Work item ID
        report: Progress report

    Returns:
        Updated work item

    Raises:
        HTTPException: If work item not found
    """
    service = get_work_map_service()
    work = await service.report_progress(work_id, report)

    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item '{work_id}' not found"
        )

    return work


@router.post("/{work_id}/complete", response_model=WorkItem)
async def complete_work(
    work_id: str,
    result: dict,
    compute_id: Optional[str] = Query(None, description="Compute ID for authorization")
):
    """Mark work as completed with result.

    Args:
        work_id: Work item ID
        result: Work result/output
        compute_id: Optional compute ID for authorization

    Returns:
        Completed work item

    Raises:
        HTTPException: If completion fails
    """
    service = get_work_map_service()
    work = await service.complete_work(work_id, result, compute_id)

    if not work:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete work item '{work_id}'. Check authorization."
        )

    return work


# ============ Blocker Operations ============

@router.post("/{work_id}/blockers")
async def add_blocker(
    work_id: str,
    blocker_type: str = Query(..., description="Type of blocker"),
    description: str = Query(..., description="Blocker description"),
    blocking_work_id: Optional[str] = Query(None, description="Blocking work ID if dependency type")
):
    """Add a blocker to work.

    Args:
        work_id: Work item ID
        blocker_type: Type of blocker
        description: Blocker description
        blocking_work_id: Blocking work ID for dependency type

    Returns:
        Created blocker

    Raises:
        HTTPException: If adding blocker fails
    """
    service = get_work_map_service()

    try:
        btype = BlockerType(blocker_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid blocker type: {blocker_type}. Must be one of: {[b.value for b in BlockerType]}"
        )

    blocker = await service.add_blocker(work_id, btype, description, blocking_work_id)

    if not blocker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item '{work_id}' not found"
        )

    return blocker


@router.post("/{work_id}/blockers/{blocker_id}/resolve")
async def resolve_blocker(
    work_id: str,
    blocker_id: str,
    resolution_note: Optional[str] = Query(None, description="Resolution note"),
    resolved_by: Optional[str] = Query(None, description="Who resolved it")
):
    """Resolve a blocker.

    Args:
        work_id: Work item ID
        blocker_id: Blocker ID
        resolution_note: Optional note about resolution
        resolved_by: Who resolved the blocker

    Raises:
        HTTPException: If resolution fails
    """
    service = get_work_map_service()
    resolved = await service.resolve_blocker(work_id, blocker_id, resolution_note, resolved_by)

    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Blocker '{blocker_id}' not found for work item '{work_id}'"
        )

    return {"status": "resolved", "blocker_id": blocker_id}


# ============ Dependency Operations ============

@router.get("/{work_id}/dependencies")
async def get_dependencies(work_id: str):
    """Get dependency information for work.

    Args:
        work_id: Work item ID

    Returns:
        Dependency graph information

    Raises:
        HTTPException: If work item not found
    """
    service = get_work_map_service()
    deps = await service.get_dependencies(work_id)

    if not deps:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work item '{work_id}' not found"
        )

    return deps


# =============================================================================
# Goal Endpoints
# =============================================================================


@goals_router.post("", response_model=Goal, status_code=status.HTTP_201_CREATED)
async def create_goal(request: GoalCreateRequest):
    """Create a new goal.

    Goals are high-level objectives that get broken into issues by the Planner.
    Goals must belong to a project.
    """
    if not request.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id is required. Goals must belong to a project."
        )

    service = get_work_map_service()
    try:
        goal = await service.create_goal(request)

        # Auto-classify intent from goal text
        try:
            intent_service = get_goal_intent_service()
            intent_service.update_goal_intent(goal)
            goal_service = get_goal_service()
            await goal_service._save_goal_to_redis(goal)
        except Exception:
            # Intent classification is best-effort on creation
            logger.debug(f"Skipped intent classification for goal {goal.goal_id}")

        logger.info(f"Created goal {goal.goal_id} with intent={goal.primary_intent}")
        return goal
    except Exception as e:
        logger.error(f"Failed to create goal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create goal"
        )


@goals_router.get("", response_model=GoalListResponse)
async def list_goals(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    include_deleted: bool = Query(False, description="Include soft-deleted goals"),
    include_archived: bool = Query(False, description="Include archived goals"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """List goals with optional filtering.

    By default, archived goals are hidden. Use include_archived=true to show them.
    When project_id is provided, only goals belonging to that project are returned.
    """
    service = get_work_map_service()

    goal_status = None
    if status_filter:
        try:
            goal_status = GoalStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: {[s.value for s in GoalStatus]}"
            )

    return await service.list_goals(
        status=goal_status,
        project_id=project_id,
        include_deleted=include_deleted,
        include_archived=include_archived,
        limit=limit
    )


# =============================================================================
# Goal Non-Parameterized Endpoints (must be before /{goal_id} to avoid shadowing)
# =============================================================================


@goals_router.get("/stale-planning", response_model=List[Goal])
async def get_stale_planning_goals(
    timeout: int = Query(300, ge=60, le=3600, description="Timeout in seconds (default 300)")
):
    """List goals stuck in PLANNING state past the timeout threshold.

    Returns goals that have been in PLANNING status longer than the
    specified timeout, indicating a failed or abandoned decomposition.
    """
    goal_service = get_goal_service()
    return await goal_service.get_stale_planning_goals(timeout)


@goals_router.post("/cleanup-stale")
async def cleanup_stale_planning_goals(
    timeout: int = Query(300, ge=60, le=3600, description="Timeout in seconds (default 300)")
):
    """Transition stale PLANNING goals to FAILED status.

    Finds all goals stuck in PLANNING past the timeout threshold
    and transitions them to FAILED with an appropriate error message.
    """
    goal_service = get_goal_service()
    failed_goals = await goal_service.fail_stale_planning_goals(timeout)
    return {
        "transitioned_count": len(failed_goals),
        "failed_goal_ids": [g.goal_id for g in failed_goals],
    }


@goals_router.get(
    "/project/{project_id}/conflicts",
    response_model=GoalConflictListResponse
)
async def get_goal_conflicts(project_id: str):
    """Get conflicts between active goals in a project.

    Analyzes all active goals' intent classifications and surfaces
    tensions where goals pull the planner in opposing directions.
    """
    goal_service = get_goal_service()
    intent_service = get_goal_intent_service()

    active_goals = await goal_service.list_active_goals(project_id)
    conflicts = intent_service.detect_conflicts(active_goals)

    return GoalConflictListResponse(
        project_id=project_id,
        conflicts=conflicts,
        total=len(conflicts),
        has_irreconcilable=any(c.is_irreconcilable for c in conflicts),
    )


# =============================================================================
# Goal CRUD Endpoints (parameterized routes)
# =============================================================================


@goals_router.get("/{goal_id}", response_model=Goal)
async def get_goal(goal_id: str):
    """Get a specific goal by ID."""
    service = get_work_map_service()
    goal = await service.get_goal(goal_id)

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return goal


@goals_router.get("/{goal_id}/decomposition")
async def get_goal_decomposition(goal_id: str):
    """Get the decomposition result for a goal.

    Returns the decomposition associated with this goal via its stored decomposition_id.
    Returns null if no decomposition has been performed or if the result has expired.
    """
    service = get_work_map_service()

    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    if not goal.decomposition_id:
        return {"goal_id": goal_id, "decomposition_id": None, "decomposition": None}

    # Retrieve from Redis
    from git.redis_client import get_redis
    from models.goal_decomposer import GoalDecompositionResult

    redis = await get_redis()
    key = f"claudevn:decomposition:{goal.decomposition_id}"
    data = await redis.get(key)

    if not data:
        return {
            "goal_id": goal_id,
            "decomposition_id": goal.decomposition_id,
            "decomposition": None,
            "expired": True,
        }

    result = GoalDecompositionResult.model_validate_json(data)
    return {
        "goal_id": goal_id,
        "decomposition_id": goal.decomposition_id,
        "decomposition": result,
    }


@goals_router.get(
    "/{goal_id}/decomposition-passes",
    response_model=List[DecompositionPass],
)
async def get_goal_decomposition_passes(goal_id: str):
    """Get the history of all decomposition passes for a goal.

    Returns each decomposition invocation with trigger info, pass number,
    and issue IDs created during that pass.
    """
    service = get_work_map_service()

    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return goal.decomposition_passes


@goals_router.get("/{goal_id}/evaluation-summary", response_model=GoalEvaluationSummary)
async def get_goal_evaluation_summary(goal_id: str):
    """Get evaluation status summary for a goal.

    Returns per-item evaluation status for the goal text and each comment,
    plus whether a decomposition exists. Used to power frontend indicators.
    """
    service = get_work_map_service()
    comment_service = get_goal_comment_service()

    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Build items list starting with goal text
    items = []
    goal_text_status = "evaluated" if goal.goal_text_evaluated else "not_evaluated"
    items.append(EvaluationItemStatus(
        item_type="goal_text",
        item_id=None,
        content_preview=goal.description[:200] if goal.description else "",
        evaluation_status=goal_text_status,
        created_at=goal.created_at,
        created_by=goal.created_by,
    ))

    # Add each comment
    comments_response = await comment_service.list_comments(goal_id, limit=1000)
    for comment in comments_response.items:
        items.append(EvaluationItemStatus(
            item_type="comment",
            item_id=comment.comment_id,
            content_preview=comment.content[:200] if comment.content else "",
            evaluation_status=comment.evaluation_status.value,
            created_at=comment.created_at,
            created_by=comment.created_by,
        ))

    evaluated_count = sum(1 for item in items if item.evaluation_status == "evaluated")
    pending_count = len(items) - evaluated_count
    all_evaluated = pending_count == 0

    return GoalEvaluationSummary(
        goal_id=goal_id,
        all_evaluated=all_evaluated,
        goal_text_evaluated=goal.goal_text_evaluated,
        has_decomposition=goal.decomposition_id is not None,
        decomposition_id=goal.decomposition_id,
        items=items,
        total_items=len(items),
        evaluated_count=evaluated_count,
        pending_count=pending_count,
    )


@goals_router.get("/{goal_id}/issues", response_model=List[Issue])
async def get_goal_issues(goal_id: str):
    """Get all issues for a goal."""
    service = get_work_map_service()

    goal = await service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return await service.get_goal_issues(goal_id)


@goals_router.get("/{goal_id}/progress", response_model=GoalProgressMetrics)
async def get_goal_progress(goal_id: str):
    """Get multi-dimensional progress metrics for a goal.

    Returns issue completion breakdown, characterization progress,
    and execution velocity indicators.
    """
    service = get_work_map_service()

    progress = await service.get_goal_progress(goal_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return progress


@goals_router.delete("/{goal_id}", response_model=GoalDeleteResponse)
async def delete_goal(
    goal_id: str,
    hard: bool = Query(False, description="Permanently delete (hard delete) if true"),
    cascade: bool = Query(False, description="Also delete child issues and work items (requires hard=true)")
):
    """Delete a goal.

    By default, performs a soft delete that preserves the goal data but marks it as deleted.
    Use hard=true query parameter to permanently delete the goal and associated data.
    Use cascade=true with hard=true to also delete all child issues and work items.

    Soft-deleted goals can be restored using POST /goals/{goal_id}/restore.
    """
    service = get_work_map_service()
    comment_service = get_goal_comment_service()

    # Get the goal first to check existence (include deleted for idempotency)
    goal = await service.get_goal(goal_id, include_deleted=True)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Count comments for the response
    comments = await comment_service.list_comments(goal_id, limit=1000)
    comment_count = comments.total if comments else 0

    # If hard delete, also delete all comments
    if hard:
        for comment in comments.items if comments else []:
            await comment_service.delete_comment(comment.comment_id)

    result = await service.delete_goal(goal_id, hard=hard, cascade=cascade)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Add comment count to response
    result.comment_count = comment_count
    return result


@goals_router.post("/{goal_id}/restore", response_model=Goal)
async def restore_goal(goal_id: str):
    """Restore a soft-deleted goal.

    Reverses a soft delete operation, making the goal visible again.
    """
    service = get_work_map_service()

    goal = await service.restore_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found or not deleted"
        )

    return goal


@goals_router.post("/{goal_id}/archive", response_model=Goal)
async def archive_goal(goal_id: str):
    """Archive a goal.

    Archives a goal so it's hidden by default from the goals list.
    Archived goals can still be accessed via direct link or by using include_archived=true.
    This is easily reversible using the unarchive endpoint.
    """
    service = get_work_map_service()

    # Get goal first to check it exists (include archived for idempotency)
    goal = await service.get_goal(goal_id, include_deleted=True)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Can't archive deleted goals
    if goal.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Goal '{goal_id}' is deleted and cannot be archived"
        )

    result = await service.archive_goal(goal_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return result


@goals_router.post("/{goal_id}/unarchive", response_model=Goal)
async def unarchive_goal(goal_id: str):
    """Unarchive a goal.

    Restores an archived goal to the default goals list view.
    """
    service = get_work_map_service()

    # Get goal (must include archived to find it)
    goal = await service._goal_service.goals.get(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    result = await service.unarchive_goal(goal_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return result


@goals_router.post("/{goal_id}/retry-planning", response_model=Goal)
async def retry_goal_planning(goal_id: str):
    """Retry planning/decomposition for a FAILED goal.

    Resets the goal from FAILED back to PLANNING status, clearing
    the error and decomposition references so decomposition can
    be retried.
    """
    goal_service = get_goal_service()

    goal = await goal_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    if goal.status != GoalStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Goal '{goal_id}' is not in FAILED status (current: {goal.status.value}). "
                   "Only FAILED goals can be retried."
        )

    result = await goal_service.retry_goal_planning(goal_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset goal for retry"
        )

    return result


# =============================================================================
# Goal Intent and Multi-Goal Endpoints
# =============================================================================


@goals_router.patch("/{goal_id}/intent", response_model=Goal)
async def adjust_goal_intent(goal_id: str, request: GoalAdjustIntentRequest):
    """Adjust a goal's intent classification without recreating.

    Allows modifying intent, strength, title, description, and priority.
    Set reparse_intent=true to re-analyze goal text after updating.
    """
    goal_service = get_goal_service()

    goal = await goal_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    result = await goal_service.adjust_goal_intent(goal_id, request)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to adjust goal intent"
        )

    return result


@goals_router.put("/{goal_id}/reconciliation-weight", response_model=Goal)
async def set_goal_reconciliation_weight(
    goal_id: str,
    request: GoalSetReconciliationWeightRequest,
):
    """Set or clear a goal's reconciliation weight for multi-goal balancing.

    When multiple goals coexist, the reconciliation algorithm automatically
    balances them using priority and recency. Use this endpoint to override
    that automatic weighting:
    - Set reconciliation_weight to 0.0-1.0 to control influence (higher = more)
    - Set reconciliation_weight to null to reset to automatic weighting

    This is the primary user mechanism for resolving irreconcilable goal
    conflicts surfaced by GET /goals/project/{project_id}/conflicts.
    """
    goal_service = get_goal_service()

    goal = await goal_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    result = await goal_service.set_reconciliation_weight(
        goal_id, request.reconciliation_weight
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set reconciliation weight"
        )

    return result


@goals_router.post("/{goal_id}/retire", response_model=Goal)
async def retire_goal(goal_id: str):
    """Retire a goal without deleting associated work.

    The goal transitions to RETIRED status and no longer influences
    the planner profile, but all associated issues continue to exist.
    """
    goal_service = get_goal_service()

    goal = await goal_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    result = await goal_service.retire_goal(goal_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retire goal"
        )

    return result


# =============================================================================
# Goal Comment Endpoints
# =============================================================================


@goals_router.post(
    "/{goal_id}/comments",
    response_model=GoalComment,
    status_code=status.HTTP_201_CREATED
)
async def create_goal_comment(
    goal_id: str,
    request: GoalCommentCreateRequest,
    force_evaluate: bool = Query(
        False,
        description="Skip rollup and immediately evaluate this comment"
    )
):
    """Add a comment to a goal conversation.

    Creates a new comment in the goal's conversation thread.
    The comment starts with evaluation_status=not_evaluated.

    If rollup is enabled (default), multiple comments submitted within
    the rollup window will be batched for efficient evaluation.
    Use force_evaluate=true to skip rollup and evaluate immediately.
    """
    work_map_service = get_work_map_service()
    comment_service = get_goal_comment_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    try:
        comment = await comment_service.create_comment(goal_id, request)
        logger.info(f"Created comment {comment.comment_id} for goal {goal_id}")

        # Add to rollup tracking (if service available)
        try:
            rollup_service = get_comment_rollup_service()
            await rollup_service.add_comment(goal_id, comment, force_evaluate=force_evaluate)
        except RuntimeError:
            # Rollup service not initialized - comments will be evaluated individually
            logger.debug("Rollup service not available, skipping rollup tracking")

        return comment
    except Exception as e:
        logger.error(f"Failed to create comment for goal {goal_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create comment"
        )


@goals_router.get("/{goal_id}/comments", response_model=GoalCommentListResponse)
async def list_goal_comments(
    goal_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """List comments for a goal.

    Returns comments in chronological order with aggregated conversation status.
    """
    work_map_service = get_work_map_service()
    comment_service = get_goal_comment_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    return await comment_service.list_comments(goal_id, limit=limit)


@goals_router.patch(
    "/{goal_id}/comments/{comment_id}",
    response_model=GoalComment
)
async def update_goal_comment(
    goal_id: str,
    comment_id: str,
    request: GoalCommentUpdateRequest
):
    """Update a goal comment.

    Can update content, priority, area, evaluation_status, and evaluation_result.
    """
    work_map_service = get_work_map_service()
    comment_service = get_goal_comment_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Verify comment exists and belongs to this goal
    comment = await comment_service.get_comment(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment '{comment_id}' not found"
        )

    if comment.goal_id != goal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Comment '{comment_id}' does not belong to goal '{goal_id}'"
        )

    updated = await comment_service.update_comment(comment_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment '{comment_id}' not found"
        )

    return updated


@goals_router.delete(
    "/{goal_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_goal_comment(goal_id: str, comment_id: str):
    """Delete a goal comment."""
    work_map_service = get_work_map_service()
    comment_service = get_goal_comment_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Verify comment exists and belongs to this goal
    comment = await comment_service.get_comment(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment '{comment_id}' not found"
        )

    if comment.goal_id != goal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Comment '{comment_id}' does not belong to goal '{goal_id}'"
        )

    deleted = await comment_service.delete_comment(comment_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment '{comment_id}' not found"
        )


@goals_router.post(
    "/{goal_id}/comments/{comment_id}/evaluate",
    response_model=GoalComment
)
async def evaluate_goal_comment(goal_id: str, comment_id: str):
    """Manually trigger evaluation for a comment.

    Runs evaluation synchronously and returns the updated comment with result.
    """
    work_map_service = get_work_map_service()
    comment_service = get_goal_comment_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    # Verify comment exists and belongs to this goal
    comment = await comment_service.get_comment(comment_id)
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comment '{comment_id}' not found"
        )

    if comment.goal_id != goal_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Comment '{comment_id}' does not belong to goal '{goal_id}'"
        )

    try:
        evaluation_service = get_goal_evaluation_service()
        await evaluation_service.evaluate_comment(comment_id)

        # Return updated comment
        updated_comment = await comment_service.get_comment(comment_id)
        return updated_comment

    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation service not available"
        )
    except Exception as e:
        logger.error(f"Failed to evaluate comment {comment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to evaluate comment"
        )


@goals_router.post("/{goal_id}/evaluate-all")
async def evaluate_all_goal_comments(goal_id: str):
    """Evaluate all pending comments for a goal (rollup processing).

    This is useful for batch evaluation of all comments in a goal conversation.
    """
    work_map_service = get_work_map_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    try:
        evaluation_service = get_goal_evaluation_service()
        results = await evaluation_service.evaluate_batch(goal_id)

        return {
            "goal_id": goal_id,
            "evaluated_count": len(results),
            "results": [
                {
                    "comment_type": r.comment_type.value,
                    "confidence": r.confidence,
                    "summary": r.summary
                }
                for r in results
            ]
        }

    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation service not available"
        )
    except Exception as e:
        logger.error(f"Failed to evaluate comments for goal {goal_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to evaluate comments"
        )


# =============================================================================
# Goal Comment Rollup Endpoints
# =============================================================================


@goals_router.get("/{goal_id}/rollup", response_model=RollupStatusResponse)
async def get_rollup_status(goal_id: str):
    """Get rollup status for a goal's conversation.

    Returns the current rollup batch status, pending comment count,
    and rollup configuration for the goal.
    """
    work_map_service = get_work_map_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    try:
        rollup_service = get_comment_rollup_service()
        return await rollup_service.get_status(goal_id)
    except RuntimeError:
        # Rollup service not initialized - return empty status
        return RollupStatusResponse(
            goal_id=goal_id,
            has_active_batch=False,
            batch=None,
            pending_comment_count=0,
            config=RollupConfig(enabled=False)
        )


@goals_router.post("/{goal_id}/rollup/evaluate", status_code=status.HTTP_200_OK)
async def force_evaluate_rollup(goal_id: str):
    """Force immediate evaluation of pending comments.

    Bypasses the rollup window and quiet period to immediately
    trigger evaluation of all pending comments for the goal.
    """
    work_map_service = get_work_map_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    try:
        rollup_service = get_comment_rollup_service()
        triggered = await rollup_service.force_evaluate(goal_id)
        return {
            "goal_id": goal_id,
            "triggered": triggered,
            "message": "Evaluation triggered" if triggered else "No pending comments to evaluate"
        }
    except RuntimeError:
        return {
            "goal_id": goal_id,
            "triggered": False,
            "message": "Rollup service not available"
        }


@goals_router.put("/{goal_id}/rollup/config", response_model=RollupConfig)
async def update_rollup_config(goal_id: str, config: RollupConfig):
    """Update rollup configuration for a goal.

    Sets goal-specific rollup configuration. This affects future
    comment submissions, not any active rollup batch.
    """
    work_map_service = get_work_map_service()

    # Verify goal exists
    goal = await work_map_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal '{goal_id}' not found"
        )

    try:
        rollup_service = get_comment_rollup_service()
        rollup_service.set_config(config, goal_id=goal_id)
        logger.info(f"Updated rollup config for goal {goal_id}: window={config.rollup_window_seconds}s, quiet={config.quiet_period_seconds}s, enabled={config.enabled}")
        return config
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rollup service not available"
        )


# =============================================================================
# Issue Endpoints
# =============================================================================


@issues_router.post("", response_model=Issue, status_code=status.HTTP_201_CREATED)
async def create_issue(request: IssueCreateRequest):
    """Create a new issue."""
    service = get_work_map_service()
    try:
        issue = await service.create_issue(request)
        logger.info(f"Created issue {issue.issue_id}")
        return issue
    except Exception as e:
        logger.error(f"Failed to create issue: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create issue"
        )


@issues_router.post("/batch", response_model=IssueBatchCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_issues_batch(request: IssueBatchCreateRequest):
    """Create multiple issues at once.

    Used by the Planner to submit issues for a goal.
    Supports batch-internal dependencies using array indices.
    """
    service = get_work_map_service()
    try:
        response = await service.create_issues_batch(request)
        logger.info(f"Created {len(response.created_issues)} issues for goal {request.goal_id}")
        return response
    except Exception as e:
        logger.error(f"Failed to create issues batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create issues"
        )


@issues_router.get("/stats", response_model=IssueStats)
async def get_issue_stats():
    """Get issue statistics."""
    service = get_work_map_service()
    return await service.get_issue_stats()


@issues_router.get("/evaluation/stats")
async def get_evaluation_stats():
    """Get evaluation statistics across all issues."""
    service = get_work_map_service()
    issues = await service.list_issues(limit=10000)

    by_eval_status = {}
    by_outcome = {}

    for issue in issues.items:
        eval_status = issue.evaluation_status.value
        by_eval_status[eval_status] = by_eval_status.get(eval_status, 0) + 1

        if issue.evaluation_result:
            outcome = issue.evaluation_result.outcome.value
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1

    return {
        "total_issues": issues.total,
        "by_evaluation_status": by_eval_status,
        "by_outcome": by_outcome,
    }


@issues_router.get("", response_model=IssueListResponse)
async def list_issues(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority (P0-P3)"),
    area: Optional[str] = Query(None, description="Filter by area"),
    goal_id: Optional[str] = Query(None, description="Filter by goal ID"),
    skill: Optional[str] = Query(None, description="Filter by required skill"),
    release_id: Optional[str] = Query(None, description="Filter by release ID (use 'unscheduled' for unassigned)"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    work_type: Optional[str] = Query(None, description="Filter by ontology work type (e.g., feature, bug_fix, test)"),
    lifecycle_stage: Optional[str] = Query(None, description="Filter by ontology lifecycle stage (e.g., design, build, test)"),
    technical_domain: Optional[str] = Query(None, description="Filter by ontology technical domain (e.g., frontend, backend, api)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """List issues with optional filtering.

    Issues are sorted by priority score (Priority * 1000 + Age).
    Supports both legacy filters (area, priority) and ontology-based filters
    (work_type, lifecycle_stage, technical_domain) for characterized issues.
    """
    service = get_work_map_service()

    issue_status = None
    if status_filter:
        try:
            issue_status = IssueStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: {[s.value for s in IssueStatus]}"
            )

    issue_priority = None
    if priority:
        try:
            issue_priority = IssuePriority(priority)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid priority: {priority}. Must be one of: {[p.value for p in IssuePriority]}"
            )

    issue_area = None
    if area:
        try:
            issue_area = IssueArea(area)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid area: {area}. Must be one of: {[a.value for a in IssueArea]}"
            )

    return await service.list_issues(
        status=issue_status,
        priority=issue_priority,
        area=issue_area,
        goal_id=goal_id,
        skill=skill,
        release_id=release_id,
        project_id=project_id,
        work_type=work_type,
        lifecycle_stage=lifecycle_stage,
        technical_domain=technical_domain,
        limit=limit
    )


@issues_router.get("/{issue_id}", response_model=Issue)
async def get_issue(issue_id: str):
    """Get a specific issue by ID."""
    service = get_work_map_service()
    issue = await service.get_issue(issue_id)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found"
        )

    return issue


@issues_router.get("/{issue_id}/history", response_model=IssueHistory)
async def get_issue_history(issue_id: str):
    """Get history of changes for an issue."""
    service = get_work_map_service()
    issue = await service.get_issue(issue_id)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found"
        )

    return await service.get_issue_history(issue_id)


@issues_router.patch("/{issue_id}", response_model=Issue)
async def update_issue(issue_id: str, request: IssueUpdateRequest):
    """Update an issue."""
    service = get_work_map_service()
    issue = await service.update_issue(issue_id, request)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found"
        )

    return issue


@issues_router.post("/{issue_id}/status", response_model=Issue)
async def update_issue_status(
    issue_id: str,
    new_status: str = Query(..., alias="status", description="New status"),
    compute_id: Optional[str] = Query(None, description="Compute ID")
):
    """Update issue status.

    Status flow: backlog → ready → in_progress → blocked → done → failed
    """
    service = get_work_map_service()

    try:
        issue_status = IssueStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {new_status}. Must be one of: {[s.value for s in IssueStatus]}"
        )

    issue = await service.update_issue_status(issue_id, issue_status, compute_id)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update status for issue '{issue_id}'. Check transition rules."
        )

    return issue


@issues_router.post("/{issue_id}/complete", response_model=Issue)
async def complete_issue(
    issue_id: str,
    result: IssueResult,
    compute_id: Optional[str] = Query(None, description="Compute ID")
):
    """Mark an issue as done with result."""
    service = get_work_map_service()
    issue = await service.complete_issue(issue_id, result, compute_id)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete issue '{issue_id}'"
        )

    return issue


@issues_router.delete("/{issue_id}")
async def delete_issue(
    issue_id: str,
    cascade: bool = Query(False, description="Also delete child issues and work items")
):
    """Delete an issue.

    Use cascade=true to also delete child issues and associated work items.
    """
    service = get_work_map_service()
    result = await service.delete_issue(issue_id, cascade=cascade)

    if not result.get("deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found"
        )

    from models.work_map import IssueDeleteResponse
    return IssueDeleteResponse(
        issue_id=issue_id,
        deleted=True,
        child_issue_count=result.get("child_issue_count", 0),
        work_item_count=result.get("work_item_count", 0),
    )


# =============================================================================
# Issue Evaluation Endpoints
# =============================================================================


@issues_router.get("/{issue_id}/evaluation")
async def get_issue_evaluation(issue_id: str):
    """Get evaluation result for an issue."""
    service = get_work_map_service()
    issue = await service.get_issue(issue_id)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found"
        )

    return {
        "issue_id": issue_id,
        "evaluation_status": issue.evaluation_status.value,
        "evaluation_result": issue.evaluation_result.model_dump() if issue.evaluation_result else None,
        "evaluation_retry_count": issue.evaluation_retry_count,
    }


@issues_router.post("/{issue_id}/evaluation/retry")
async def retry_issue_evaluation(issue_id: str):
    """Retry a failed evaluation for an issue."""
    service = get_work_map_service()
    issue = await service.get_issue(issue_id)

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found"
        )

    if issue.evaluation_status != EvaluationStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Issue evaluation status is '{issue.evaluation_status.value}', not 'failed'"
        )

    try:
        from services.issue_evaluation_service import get_issue_evaluation_service
        eval_service = get_issue_evaluation_service()

        # Reset status and re-queue
        issue.evaluation_status = EvaluationStatus.NOT_EVALUATED
        issue.evaluation_retry_count = 0
        issue.evaluation_result = None
        await service._issue_ops_service._save_issue_to_redis(issue)

        await eval_service.queue_for_evaluation(issue_id)

        return {"issue_id": issue_id, "status": "queued_for_retry"}
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Issue evaluation service not available"
        )


# =============================================================================
# Release Endpoints
# =============================================================================


@releases_router.post("", response_model=Release, status_code=status.HTTP_201_CREATED)
async def create_release(request: ReleaseCreateRequest):
    """Create a new release.

    Releases allow grouping issues by version or milestone for planning.
    """
    service = get_release_service()
    try:
        release = await service.create_release(request)
        logger.info(f"Created release {release.release_id}: {release.name}")
        return release
    except Exception as e:
        logger.error(f"Failed to create release: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create release"
        )


@releases_router.get("", response_model=ReleaseListResponse)
async def list_releases(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """List releases with optional filtering."""
    service = get_release_service()

    release_status = None
    if status_filter:
        try:
            release_status = ReleaseStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: {[s.value for s in ReleaseStatus]}"
            )

    return await service.list_releases(status=release_status, limit=limit)


@releases_router.get("/{release_id}", response_model=Release)
async def get_release(release_id: str):
    """Get a specific release by ID."""
    service = get_release_service()
    release = await service.get_release(release_id)

    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{release_id}' not found"
        )

    return release


@releases_router.patch("/{release_id}", response_model=Release)
async def update_release(release_id: str, request: ReleaseUpdateRequest):
    """Update a release."""
    service = get_release_service()
    release = await service.update_release(release_id, request)

    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{release_id}' not found"
        )

    return release


@releases_router.delete("/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_release(release_id: str):
    """Delete a release.

    Note: This does not delete issues assigned to this release,
    they will become unscheduled.
    """
    service = get_release_service()
    deleted = await service.delete_release(release_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{release_id}' not found"
        )


@releases_router.get("/{release_id}/issues", response_model=IssueListResponse)
async def get_release_issues(
    release_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return")
):
    """Get all issues assigned to a release."""
    release_service = get_release_service()
    work_map_service = get_work_map_service()

    # Verify release exists
    release = await release_service.get_release(release_id)
    if not release:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{release_id}' not found"
        )

    return await work_map_service.list_issues(release_id=release_id, limit=limit)


# =============================================================================
# WorkMap View Endpoints
# =============================================================================


@workmap_router.get("/bucket-tree")
async def get_bucket_tree(
    project_id: str = Query(..., description="Project ID"),
):
    """Get the current bucket tree for a project.

    Returns the priority bucket tree showing strategic work groupings.
    Each bucket contains ranked work items with readiness states.
    Returns null tree if no bucket tree exists for the project.

    Args:
        project_id: Project ID to get bucket tree for

    Returns:
        Response with project_id, tree (or None), and summary stats (or None)
    """
    try:
        store = get_bucket_tree_store()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bucket tree store not initialized"
        )

    tree = await store.load(project_id)

    if tree:
        return {
            "project_id": project_id,
            "tree": tree,
            "summary": {
                "total_buckets": len(tree.buckets),
                "total_items": tree.total_items,
                "total_ready": tree.total_ready,
                "version": tree.version,
            }
        }
    else:
        return {
            "project_id": project_id,
            "tree": None,
            "summary": None
        }


@workmap_router.get("/bucket-tree/{bucket_id}")
async def get_bucket_detail(
    bucket_id: str,
    project_id: str = Query(..., description="Project ID"),
):
    """Get detailed information about a specific bucket.

    Returns the bucket definition, all items in the bucket, and
    their readiness states. Useful for drilling down from the tree view.

    Args:
        bucket_id: Unique bucket identifier
        project_id: Project ID the bucket belongs to

    Returns:
        Bucket details including definition and all items

    Raises:
        404: Bucket tree not found for project
        404: Bucket not found in tree
        503: Bucket tree store not initialized
    """
    try:
        store = get_bucket_tree_store()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bucket tree store not initialized"
        )

    tree = await store.load(project_id)

    if not tree:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No bucket tree found for project '{project_id}'"
        )

    bucket = tree.get_bucket(bucket_id)

    if not bucket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bucket '{bucket_id}' not found in project '{project_id}'"
        )

    # Sort items for display
    bucket.sort_items()

    return {
        "bucket_id": bucket.bucket_id,
        "rank": bucket.rank,
        "definition": bucket.definition,
        "items": bucket.items,
        "stats": {
            "total_items": bucket.item_count,
            "ready_items": len(bucket.ready_items),
            "blocked_items": len(bucket.blocked_items),
        }
    }


@workmap_router.get("")
async def get_workmap(
    project_id: Optional[str] = Query(None, description="Filter by project ID")
):
    """Get full workmap state including goals, issues, and work items."""
    service = get_work_map_service()

    goals = await service.list_goals(project_id=project_id)
    issues = await service.list_issues(project_id=project_id)
    work = await service.list_work(project_id=project_id)
    issue_stats = await service.get_issue_stats()

    return {
        "goals": goals,
        "issues": issues,
        "work_items": work,
        "stats": issue_stats
    }


@workmap_router.get("/ready", response_model=List[Issue])
async def get_ready_queue(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum items")
):
    """Get the ready queue of issues waiting for assignment.

    Issues are sorted by priority score: (Priority * 1000) + Age.
    Lower score = higher priority.
    """
    service = get_work_map_service()
    items = await service.get_ready_queue(limit=limit)
    if project_id:
        items = [i for i in items if i.project_id == project_id]
    return items


@workmap_router.get("/in-progress", response_model=IssueListResponse)
async def get_in_progress(
    project_id: Optional[str] = Query(None, description="Filter by project ID")
):
    """Get issues currently in progress."""
    service = get_work_map_service()
    return await service.list_issues(status=IssueStatus.IN_PROGRESS, project_id=project_id)


@workmap_router.get("/blocked", response_model=IssueListResponse)
async def get_blocked(
    project_id: Optional[str] = Query(None, description="Filter by project ID")
):
    """Get blocked issues."""
    service = get_work_map_service()
    return await service.list_issues(status=IssueStatus.BLOCKED, project_id=project_id)


@workmap_router.get("/stats", response_model=IssueStats)
async def get_workmap_stats(
    project_id: Optional[str] = Query(None, description="Filter by project ID")
):
    """Get workmap statistics.

    When project_id is provided, stats are scoped to that project.
    """
    service = get_work_map_service()
    if project_id:
        # Get issues for this project and derive stats
        issue_response = await service.list_issues(project_id=project_id, limit=1000)
        items = issue_response.items if hasattr(issue_response, 'items') else []
        by_status = {}
        by_priority = {}
        by_area = {}
        for issue in items:
            status_val = issue.status.value if hasattr(issue.status, 'value') else str(issue.status)
            by_status[status_val] = by_status.get(status_val, 0) + 1
            priority_val = issue.priority.value if hasattr(issue.priority, 'value') else str(issue.priority)
            by_priority[priority_val] = by_priority.get(priority_val, 0) + 1
            area_val = issue.area.value if hasattr(issue.area, 'value') else str(issue.area) if issue.area else 'other'
            by_area[area_val] = by_area.get(area_val, 0) + 1
        return IssueStats(
            total=len(items),
            by_status=by_status,
            by_priority=by_priority,
            by_area=by_area,
            ready_count=by_status.get('ready', 0),
            in_progress_count=by_status.get('in_progress', 0),
            blocked_count=by_status.get('blocked', 0)
        )
    return await service.get_issue_stats()


@workmap_router.post("/next-issue")
async def get_next_issue_assignment(
    compute_id: str = Query(..., description="Compute instance ID"),
    skills: str = Query("", description="Comma-separated skill IDs")
):
    """Get the next issue assignment for a compute instance.

    Matches based on required skills and returns highest priority ready issue.
    """
    service = get_work_map_service()

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]

    issue = await service.get_next_issue_assignment(compute_id, skill_list)

    if issue:
        logger.info(f"Assigned issue {issue.issue_id} to compute {compute_id}")
        return {"assigned": True, "issue": issue}
    else:
        logger.debug(f"No issues available for compute {compute_id}")
        return {"assigned": False, "issue": None}
