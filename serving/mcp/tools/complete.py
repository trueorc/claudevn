"""claudevn_complete_task tool."""

import logging
from typing import Optional

from ..models import (
    CompleteTaskInput, CompleteResponse, TaskAssignment,
    MergeStatus, MCPError, NotifyConflictInput
)
from services.work_map_service import get_work_map_service
from models.work_map import WorkStatus

logger = logging.getLogger(__name__)


async def complete_task(input: CompleteTaskInput) -> tuple[Optional[CompleteResponse], Optional[MCPError]]:
    """Complete a task and request merge.

    Marks the work as completed in the Work Map service, records the
    result, and initiates the PR/merge process with conflict detection.
    Also checks if there's another task available for the compute instance.
    """
    logger.info(f"Task completed: {input.task_id} on branch {input.branch}")
    logger.info(f"Summary: {input.summary}")

    try:
        from git.pr_service import PRService
        from .conflict import notify_conflict

        service = get_work_map_service()

        # Get work item to find compute_id and project
        work = await service.get_work(input.task_id)
        if not work:
            return None, MCPError(
                code="TASK_NOT_FOUND",
                message=f"Task {input.task_id} not found"
            )

        compute_id = work.assigned_to
        project = work.project_id

        # Build result from completion data
        result = {
            "summary": input.summary,
            "branch": input.branch,
            "deliverables": input.deliverables or [],
            "test_results": input.test_results or {}
        }

        # Complete the work
        completed_work = await service.complete_work(
            work_id=input.task_id,
            result=result,
            compute_id=compute_id
        )

        if not completed_work:
            return None, MCPError(
                code="COMPLETION_FAILED",
                message="Failed to complete task"
            )

        # Perform dry-run merge to detect conflicts
        pr_service = PRService()
        merge_check = await pr_service.dry_run_merge(project, input.branch)

        # Determine merge status based on dry-run result
        merge_status = MergeStatus.QUEUED

        if not merge_check.get("can_merge", False):
            conflicting_files = merge_check.get("conflicting_files", [])

            if conflicting_files:
                # Real conflicts — notify compute
                logger.warning(
                    f"Merge conflicts detected for {project}/{input.branch}: {conflicting_files}"
                )

                # Set merge status to conflict
                merge_status = MergeStatus.CONFLICT

                # Notify compute of conflicts
                conflict_input = NotifyConflictInput(
                    task_id=input.task_id,
                    branch=input.branch,
                    conflicting_files=conflicting_files,
                    base_branch=work.base_branch
                )

                conflict_response, conflict_error = await notify_conflict(conflict_input)

                if conflict_error:
                    logger.error(
                        f"Failed to notify conflict for {input.task_id}: {conflict_error.message}"
                    )
                else:
                    logger.info(
                        f"Conflict notification sent for {input.task_id}, "
                        f"work status updated to BLOCKED"
                    )
            else:
                # Branch not yet pushed or transient git error — don't block.
                # PR will be created and dry-run re-run when claude_code_completed fires.
                error = merge_check.get("error", "")
                logger.info(
                    f"Dry-run returned can_merge=False with no conflicting files for "
                    f"{project}/{input.branch}: {error}. Branch may not be pushed yet "
                    f"— proceeding with QUEUED."
                )
                merge_status = MergeStatus.QUEUED
        else:
            # No conflicts - ready for merge
            logger.info(
                f"Dry-run merge successful for {project}/{input.branch}, ready for merge"
            )
            merge_status = MergeStatus.QUEUED

        # Check for next available work
        next_task = None
        if compute_id:
            # Get compute capabilities from assigned skills
            capabilities = work.required_capabilities or []

            next_assignment = await service.get_next_assignment(
                compute_id=compute_id,
                capabilities=capabilities
            )

            if next_assignment:
                next_task = TaskAssignment(
                    task_id=next_assignment.work_id,
                    title=next_assignment.title,
                    description=next_assignment.description,
                    skill_ids=next_assignment.skills,
                    branch_name=next_assignment.branch_name,
                    context={
                        **next_assignment.context,
                        "skills": next_assignment.skills,
                        "base_branch": next_assignment.base_branch,
                        "dependency_outputs": next_assignment.dependency_outputs
                    },
                    dependencies=next_assignment.dependencies
                )

        return CompleteResponse(
            task_id=input.task_id,
            status="implemented",
            merge_status=merge_status,
            next_task=next_task
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
