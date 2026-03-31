"""claudevn_get_context tool."""

import logging
from typing import Optional

from ..models import GetContextInput, ContextResponse, ContextType, MCPError
from mcp.tools import emit_tool_error
from services.work_map_service import get_work_map_service

logger = logging.getLogger(__name__)


async def get_context(input: GetContextInput) -> tuple[Optional[ContextResponse], Optional[MCPError]]:
    """Fetch relevant context for a task.

    Retrieves task details, dependencies, and related information
    from the Work Map service to help compute instances understand
    the full context of their assigned work.
    """
    logger.info(f"get_context called for task {input.task_id}")

    try:
        service = get_work_map_service()

        # Get work item
        work = await service.get_work(input.task_id)
        if not work:
            return None, MCPError(
                code="TASK_NOT_FOUND",
                message=f"Task {input.task_id} not found"
            )

        # Get dependency information
        deps = await service.get_dependencies(input.task_id)

        # Build task context
        task_info = {
            "task_id": work.work_id,
            "title": work.title,
            "description": work.description,
            "work_type": work.work_type,
            "priority": work.priority.value,
            "status": work.status.value,
            "branch_name": work.branch_name,
            "base_branch": work.base_branch,
            "project_id": work.project_id,
            "context": work.context,
            "required_skills": work.required_skills,
            "assigned_skills": work.assigned_skills,
            "progress_percent": work.progress_percent,
            "progress_notes": work.progress_notes,
        }

        # Build related tasks from dependencies
        related_tasks = []

        # Add dependencies (work this task depends on)
        for dep in deps.get("depends_on", []):
            related_tasks.append({
                "task_id": dep["work_id"],
                "title": dep["title"],
                "status": dep["status"],
                "relationship": "depends_on",
                "completed": dep["completed"]
            })

        # Add dependents (work blocked by this task)
        for blocked in deps.get("blocks", []):
            related_tasks.append({
                "task_id": blocked["work_id"],
                "title": blocked["title"],
                "status": blocked["status"],
                "relationship": "blocks"
            })

        # Get active blockers
        blockers = []
        for blocker in work.active_blockers:
            blockers.append({
                "blocker_id": blocker.blocker_id,
                "type": blocker.blocker_type.value,
                "description": blocker.description,
                "blocking_work_id": blocker.blocking_work_id
            })

        # Add blockers to task info
        task_info["blockers"] = blockers
        task_info["is_blocked"] = work.is_blocked
        task_info["all_dependencies_met"] = deps.get("all_dependencies_met", True)

        # Get dependency outputs (results from completed dependencies)
        dependency_outputs = {}
        for dep_id in work.depends_on:
            dep_work = await service.get_work(dep_id)
            if dep_work and dep_work.result:
                dependency_outputs[dep_id] = dep_work.result

        if dependency_outputs:
            task_info["dependency_outputs"] = dependency_outputs

        return ContextResponse(
            task=task_info,
            relevant_files=[],  # TODO: Integrate with Git service for file tracking
            related_tasks=related_tasks,
            recent_commits=[]  # TODO: Integrate with Git service for commit history
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        await emit_tool_error(tool_name="get_context", error_code="SERVICE_UNAVAILABLE", error_msg=str(e))
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        await emit_tool_error(tool_name="get_context", error_code="INTERNAL_ERROR", error_msg=str(e))
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
