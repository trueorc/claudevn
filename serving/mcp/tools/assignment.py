"""claudevn_get_assignment tool."""

import logging
from typing import Optional

from mcp.tools import emit_tool_error

from ..models import GetAssignmentInput, TaskAssignment, MCPError
from services.work_map_service import get_work_map_service

logger = logging.getLogger(__name__)


async def get_assignment(input: GetAssignmentInput) -> tuple[Optional[TaskAssignment], Optional[MCPError]]:
    """Get next task assignment for compute instance.

    Queries the Work Map service for the highest-priority work item
    that matches the compute's capabilities and has all dependencies met.
    """
    logger.info(f"get_assignment called by {input.compute_id}")

    try:
        service = get_work_map_service()

        # Get next available assignment
        assignment = await service.get_next_assignment(
            compute_id=input.compute_id,
            capabilities=input.capabilities or []
        )

        if not assignment:
            logger.info(f"No work available for compute {input.compute_id}")
            return None, MCPError(
                code="NO_WORK_AVAILABLE",
                message="No work items available matching your capabilities"
            )

        # Convert to MCP TaskAssignment format
        return TaskAssignment(
            task_id=assignment.work_id,
            title=assignment.title,
            description=assignment.description,
            skill_ids=assignment.skill_ids if assignment.skill_ids else assignment.skills,
            branch_name=assignment.branch_name,
            context={
                **assignment.context,
                "skills": assignment.skills,
                "base_branch": assignment.base_branch,
                "dependency_outputs": assignment.dependency_outputs
            },
            dependencies=assignment.dependencies,
            git_project_name=assignment.git_project_name,
            clone_url=assignment.clone_url,
            default_branch=assignment.default_branch,
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        await emit_tool_error(tool_name="get_assignment", error_code="SERVICE_UNAVAILABLE", error_msg=str(e))
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error getting assignment: {e}")
        await emit_tool_error(tool_name="get_assignment", error_code="INTERNAL_ERROR", error_msg=str(e))
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
