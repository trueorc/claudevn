"""claudevn_request_review tool."""

import logging
from typing import Optional

from ..models import RequestReviewInput, ReviewResponse, MCPError
from mcp.tools import emit_tool_error

logger = logging.getLogger(__name__)


async def request_review(input: RequestReviewInput) -> tuple[Optional[ReviewResponse], Optional[MCPError]]:
    """Request review/merge for a branch.

    Creates a PR in the queue for the specified branch. The PR will
    be reviewed and merged according to the project's workflow.
    """
    try:
        from git.pr_service import PRService
        from services.work_map_service import get_work_map_service

        pr_service = PRService()

        # Try to get project from work context
        project = "default"
        compute_id = "unknown"

        if input.task_id:
            try:
                work_map = get_work_map_service()
                work = await work_map.get_work(input.task_id)
                if work:
                    project = work.project_id
                    compute_id = work.assigned_to or "unknown"
            except Exception as e:
                logger.debug(f"Could not get work context: {e}")

        # Create PR in queue
        pr = await pr_service.create_pr(
            project=project,
            branch=input.branch,
            compute_id=compute_id,
            task_id=input.task_id,
            title=input.title,
            description=input.description
        )

        logger.info(f"PR created: {project}/{input.branch} (position: {pr.queue_position})")

        return ReviewResponse(
            pr_id=f"pr-{pr.project}-{pr.branch}",
            branch=pr.branch,
            status=pr.status.value,
            queue_position=pr.queue_position
        ), None

    except ValueError as e:
        err_msg = str(e)
        if "Branch not found" in err_msg:
            # Branch not pushed yet — PR will be auto-created on claude_code_completed event
            logger.debug(
                f"Branch not yet in Git for review request ({err_msg}); "
                f"PR will be created automatically on completion."
            )
            return ReviewResponse(
                pr_id=f"pr-pending-{input.branch}",
                branch=input.branch,
                status="pending",
                queue_position=0
            ), None
        elif "PR already exists" in err_msg:
            logger.debug(f"PR already exists for {input.branch}")
            return ReviewResponse(
                pr_id=f"pr-{input.branch}",
                branch=input.branch,
                status="pending",
                queue_position=0
            ), None
        else:
            logger.warning(f"Could not create PR: {e}")
            return None, MCPError(code="PR_CREATE_FAILED", message=err_msg)

    except Exception as e:
        logger.error(f"Failed to request review: {e}")
        await emit_tool_error(tool_name="request_review", error_code="INTERNAL_ERROR", error_msg=str(e))
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
