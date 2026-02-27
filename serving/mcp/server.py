"""MCP Server - HTTP-based MCP endpoint for compute instances."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from typing import Tuple

from .models import MCPToolCall, MCPResponse, MCPError
from .auth import verify_compute_auth
from .tools import assignment, progress, review, context, blocker, complete, skill, conflict, issues, requirement, decomposition, characterization, challenge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# Tool registry
TOOLS = {
    "claudevn_get_assignment": assignment.get_assignment,
    "claudevn_report_progress": progress.report_progress,
    "claudevn_request_review": review.request_review,
    "claudevn_get_context": context.get_context,
    "claudevn_signal_blocker": blocker.signal_blocker,
    "claudevn_complete_task": complete.complete_task,
    "claudevn_get_skill": skill.get_skill,
    "claudevn_notify_conflict": conflict.notify_conflict,
    "claudevn_add_issues": issues.add_issues,
    "claudevn_add_requirement": requirement.add_requirement,
    "claudevn_submit_decomposition": decomposition.submit_decomposition,
    "claudevn_submit_characterization": characterization.submit_characterization,
    "claudevn_submit_challenge": challenge.report_challenge,
}

# Input model mapping
from .models import (
    GetAssignmentInput, ReportProgressInput, RequestReviewInput,
    GetContextInput, SignalBlockerInput, CompleteTaskInput, GetSkillInput,
    NotifyConflictInput, AddIssuesInput, AddRequirementInput, SubmitDecompositionInput,
    SubmitCharacterizationInput, ReportChallengeInput,
)

INPUT_MODELS = {
    "claudevn_get_assignment": GetAssignmentInput,
    "claudevn_report_progress": ReportProgressInput,
    "claudevn_request_review": RequestReviewInput,
    "claudevn_get_context": GetContextInput,
    "claudevn_signal_blocker": SignalBlockerInput,
    "claudevn_complete_task": CompleteTaskInput,
    "claudevn_get_skill": GetSkillInput,
    "claudevn_notify_conflict": NotifyConflictInput,
    "claudevn_add_issues": AddIssuesInput,
    "claudevn_add_requirement": AddRequirementInput,
    "claudevn_submit_decomposition": SubmitDecompositionInput,
    "claudevn_submit_characterization": SubmitCharacterizationInput,
    "claudevn_submit_challenge": ReportChallengeInput,
}


@router.post("/tools/call", response_model=MCPResponse)
async def call_tool(
    request: MCPToolCall,
    auth: Tuple[str, str] = Depends(verify_compute_auth)
) -> MCPResponse:
    """Execute an MCP tool call.

    This is the main endpoint for compute instances to call tools.
    """
    compute_id, api_key = auth
    logger.info(f"MCP call: tool={request.name} compute={compute_id}")

    # Check tool exists
    if request.name not in TOOLS:
        return MCPResponse(
            success=False,
            error={
                "code": "UNKNOWN_TOOL",
                "message": f"Tool '{request.name}' not found",
                "details": {"available_tools": list(TOOLS.keys())}
            }
        )

    # Parse input
    try:
        input_model = INPUT_MODELS[request.name]
        parsed_input = input_model(**request.arguments)
    except Exception as e:
        return MCPResponse(
            success=False,
            error={
                "code": "INVALID_INPUT",
                "message": f"Invalid arguments for tool '{request.name}'",
                "details": {"error": str(e)}
            }
        )

    # Execute tool with timing instrumentation
    call_start = datetime.now(timezone.utc)
    try:
        tool_fn = TOOLS[request.name]
        result, error = await tool_fn(parsed_input)

        if error:
            return MCPResponse(
                success=False,
                error=error.model_dump()
            )

        return MCPResponse(
            success=True,
            result=result.model_dump() if result else None
        )

    except Exception as e:
        logger.error(f"Tool execution failed: {e}", exc_info=True)
        return MCPResponse(
            success=False,
            error={
                "code": "INTERNAL_ERROR",
                "message": "Tool execution failed",
                "details": {"error": str(e)}
            }
        )
    finally:
        # Record MCP tool call timing
        call_end = datetime.now(timezone.utc)
        try:
            from models.timing import TimingPhase
            from services.timing_service import get_timing_service
            timing_svc = get_timing_service()
            # Extract work_id from arguments (most tools include task_id)
            work_id = (
                request.arguments.get("task_id")
                or request.arguments.get("work_id")
                or request.arguments.get("decomposition_id")
                or compute_id
            )
            await timing_svc.record_phase(
                work_id, compute_id, TimingPhase.MCP_TOOL_CALL,
                call_start, call_end,
                {"tool_name": request.name}
            )
        except Exception:
            pass


@router.get("/tools/list")
async def list_tools():
    """List available MCP tools."""
    return {
        "tools": [
            {
                "name": name,
                "description": fn.__doc__.split("\n")[0] if fn.__doc__ else ""
            }
            for name, fn in TOOLS.items()
        ]
    }


@router.get("/health")
async def mcp_health():
    """MCP server health check."""
    return {
        "status": "healthy",
        "tools_available": len(TOOLS)
    }
