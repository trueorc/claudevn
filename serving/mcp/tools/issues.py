"""claudevn_add_issues tool - Batch issue creation for Planner.

This tool allows a Planner Compute instance to submit batches of issues
with internal dependencies. Array indices in depends_on fields are
resolved to actual issue IDs.
"""

import logging
from typing import Any, Dict, List, Optional

from ..models import MCPError
from pydantic import BaseModel, Field
from services.work_map_service import get_work_map_service
from models.work_map import (
    IssueBatchCreateRequest, IssueBatchCreateResponse,
    IssueCreateRequest, IssueType, IssueArea, IssuePriority
)

logger = logging.getLogger(__name__)


class AddIssuesInput(BaseModel):
    """Input for claudevn_add_issues tool.

    Accepts a goal_id and a list of issues with their details.
    Dependencies can reference other issues in the batch using array indices.
    """
    goal_id: str = Field(..., description="Goal ID that these issues belong to")
    issues: List[Dict[str, Any]] = Field(
        ...,
        description="List of issues to create. Each issue can have: title, description, type, area, priority, required_skills, depends_on"
    )


class AddIssuesResponse(BaseModel):
    """Response for claudevn_add_issues tool."""
    success: bool
    goal_id: str
    created_issues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {index, id} mappings for created issues"
    )
    ready_count: int = Field(description="Number of issues ready for assignment (no unmet dependencies)")
    backlog_count: int = Field(description="Number of issues in backlog (have unmet dependencies)")


async def add_issues(input: AddIssuesInput) -> tuple[Optional[AddIssuesResponse], Optional[MCPError]]:
    """Add a batch of issues from Planner.

    This tool allows the Planner Compute to submit multiple issues at once,
    with dependencies specified using array indices that get resolved to
    actual issue IDs.

    Example input:
        {
            "goal_id": "goal-001",
            "issues": [
                {"title": "Design schema", "description": "...", "type": "feature"},
                {"title": "Implement model", "depends_on": [0]}  // depends on first issue
            ]
        }
    """
    logger.info(f"Adding {len(input.issues)} issues for goal {input.goal_id}")

    try:
        service = get_work_map_service()

        # Validate goal exists
        goal = await service.get_goal(input.goal_id)
        if not goal:
            return None, MCPError(
                code="GOAL_NOT_FOUND",
                message=f"Goal {input.goal_id} not found"
            )

        # Inherit project_id from the parent goal
        project_id = goal.project_id

        # Convert dict issues to IssueCreateRequest models
        issue_requests = []
        for i, issue_dict in enumerate(input.issues):
            try:
                # Handle enum conversions
                if "type" in issue_dict:
                    issue_dict["issue_type"] = IssueType(issue_dict.pop("type"))
                if "area" in issue_dict:
                    issue_dict["area"] = IssueArea(issue_dict["area"])
                if "priority" in issue_dict:
                    issue_dict["priority"] = IssuePriority(issue_dict["priority"])

                # Create request with project_id from goal
                issue_request = IssueCreateRequest(
                    goal_id=input.goal_id,
                    project_id=project_id,
                    **issue_dict
                )
                issue_requests.append(issue_request)
            except Exception as e:
                return None, MCPError(
                    code="INVALID_ISSUE",
                    message=f"Invalid issue at index {i}: {str(e)}",
                    details={"index": i, "issue": issue_dict}
                )

        # Create batch using existing service method
        batch_request = IssueBatchCreateRequest(
            goal_id=input.goal_id,
            issues=issue_requests
        )

        response = await service.create_issues_batch(batch_request)

        logger.info(
            f"Created {len(response.created_issues)} issues: "
            f"{response.ready_count} ready, {response.backlog_count} backlog"
        )

        return AddIssuesResponse(
            success=response.success,
            goal_id=response.goal_id,
            created_issues=response.created_issues,
            ready_count=response.ready_count,
            backlog_count=response.backlog_count
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error adding issues: {e}", exc_info=True)
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
