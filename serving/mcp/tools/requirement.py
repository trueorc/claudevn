"""claudevn_add_requirement tool - Add work discovered during execution.

This tool allows Compute instances to submit new work items discovered
during task execution. The serving component decides when and where
to assign these new requirements.
"""

import logging
import uuid
from typing import Optional

from ..models import AddRequirementInput, RequirementResponse, MCPError
from services.work_map_service import get_work_map_service
from models.work_map import IssueCreateRequest, IssueType, IssueArea, IssuePriority
from models.feedback import FeedbackSignal, FeedbackSeverity, FeedbackType

logger = logging.getLogger(__name__)

# Map MCP priority strings to IssuePriority enum
PRIORITY_MAP = {
    "critical": IssuePriority.P0,
    "high": IssuePriority.P1,
    "normal": IssuePriority.P2,
    "low": IssuePriority.P3,
}


async def add_requirement(
    input: AddRequirementInput
) -> tuple[Optional[RequirementResponse], Optional[MCPError]]:
    """Add a new requirement discovered during task execution.

    When a Compute instance identifies additional work needed that
    wasn't in the original task, it uses this tool to report it.
    The serving component will add it to the backlog for later
    assignment.
    """
    logger.info(
        f"New requirement from task {input.parent_task_id}: {input.title}"
    )

    try:
        service = get_work_map_service()

        # Verify parent task exists and get its goal_id
        parent_work = await service.get_work(input.parent_task_id)
        if not parent_work:
            # Try looking up as an issue ID instead
            parent_issue = await service.get_issue(input.parent_task_id)
            if not parent_issue:
                return None, MCPError(
                    code="PARENT_TASK_NOT_FOUND",
                    message=f"Parent task {input.parent_task_id} not found"
                )
            goal_id = parent_issue.goal_id
        else:
            # Work item exists - get goal_id from associated issue
            parent_issue = await service.get_issue(parent_work.work_id)
            goal_id = parent_issue.goal_id if parent_issue else None

        # Convert priority string to IssuePriority enum
        priority = IssuePriority.P2  # default to medium
        if input.priority:
            priority = PRIORITY_MAP.get(input.priority.lower(), IssuePriority.P2)

        # Build dependencies list
        depends_on = []
        if input.dependencies:
            depends_on = input.dependencies
        # Always include parent task as a dependency if not already specified
        if input.parent_task_id not in depends_on:
            depends_on.append(input.parent_task_id)

        # Create the issue
        request = IssueCreateRequest(
            title=input.title,
            description=input.description,
            issue_type=IssueType.FEATURE,  # Requirements are typically features
            area=IssueArea.OTHER,  # Could be enhanced later to infer from context
            priority=priority,
            required_skills=input.suggested_skills or [],
            depends_on=depends_on,
            goal_id=goal_id,
            parent_issue_id=input.parent_task_id,
        )

        issue = await service.create_issue(request)

        logger.info(
            f"Created requirement issue {issue.issue_id}: {issue.title} "
            f"(parent: {input.parent_task_id}, status: {issue.status})"
        )

        # Send feedback signal to aggregation service
        try:
            from services.feedback_aggregation_service import get_feedback_aggregation_service
            feedback_service = get_feedback_aggregation_service()

            # Determine project_id from parent work or issue
            project_id = ""
            if parent_work:
                project_id = parent_work.project_id
            elif parent_issue:
                project_id = parent_issue.project_id

            if project_id:
                severity_map = {
                    IssuePriority.P0: FeedbackSeverity.CRITICAL,
                    IssuePriority.P1: FeedbackSeverity.HIGH,
                    IssuePriority.P2: FeedbackSeverity.MEDIUM,
                    IssuePriority.P3: FeedbackSeverity.LOW,
                }
                signal = FeedbackSignal(
                    signal_id=f"sig_{uuid.uuid4().hex[:12]}",
                    project_id=project_id,
                    worker_id="unknown",  # requirement tool doesn't have worker_id
                    task_id=input.parent_task_id,
                    feedback_type=FeedbackType.REQUIREMENT,
                    severity=severity_map.get(priority, FeedbackSeverity.MEDIUM),
                    description=f"New requirement discovered: {input.title}",
                    data={
                        "new_issue_id": issue.issue_id,
                        "priority": priority.value,
                        "suggested_skills": input.suggested_skills or [],
                    },
                )
                await feedback_service.process_signal(signal)
        except Exception as e:
            # Feedback processing is non-critical; don't fail the requirement
            logger.debug(f"Feedback aggregation unavailable: {e}")

        return RequirementResponse(
            acknowledged=True,
            new_task_id=issue.issue_id,
            status="added_to_backlog"
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error adding requirement: {e}", exc_info=True)
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
