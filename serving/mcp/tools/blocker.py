"""claudevn_signal_blocker tool."""

import logging
import uuid
from typing import Optional

from ..models import SignalBlockerInput, BlockerResponse, MCPError
from ..models import BlockerType as MCPBlockerType
from services.work_map_service import get_work_map_service
from models.work_map import BlockerType as WorkBlockerType
from models.feedback import FeedbackSignal, FeedbackSeverity, FeedbackType

logger = logging.getLogger(__name__)

# Map MCP BlockerType to Work Map BlockerType
BLOCKER_TYPE_MAP = {
    MCPBlockerType.DEPENDENCY: WorkBlockerType.DEPENDENCY,
    MCPBlockerType.CLARIFICATION: WorkBlockerType.CLARIFICATION,
    MCPBlockerType.ACCESS: WorkBlockerType.RESOURCE,
    MCPBlockerType.TECHNICAL: WorkBlockerType.TECHNICAL,
    MCPBlockerType.OTHER: WorkBlockerType.EXTERNAL,
}


async def signal_blocker(input: SignalBlockerInput) -> tuple[Optional[BlockerResponse], Optional[MCPError]]:
    """Signal a blocker preventing task completion.

    Records a blocker in the Work Map service and updates the work
    status to BLOCKED. Blockers can be dependencies, clarification
    needs, access issues, or technical problems.
    """
    logger.warning(
        f"Blocker: task={input.task_id} type={input.blocker_type} - {input.description}"
    )

    try:
        service = get_work_map_service()

        # Verify work item exists
        work = await service.get_work(input.task_id)
        if not work:
            return None, MCPError(
                code="TASK_NOT_FOUND",
                message=f"Task {input.task_id} not found"
            )

        # Convert blocker type
        work_blocker_type = BLOCKER_TYPE_MAP.get(
            input.blocker_type,
            WorkBlockerType.EXTERNAL
        )

        # Build description with suggested resolution if provided
        description = input.description
        if input.suggested_resolution:
            description += f"\n\nSuggested resolution: {input.suggested_resolution}"

        # Add blocker
        blocker = await service.add_blocker(
            work_id=input.task_id,
            blocker_type=work_blocker_type,
            description=description,
            blocking_work_id=input.blocking_task_id
        )

        if not blocker:
            return None, MCPError(
                code="BLOCKER_ADD_FAILED",
                message="Failed to add blocker"
            )

        # Determine if there's a resolution task (for dependency blockers)
        resolution_task_id = None
        if work_blocker_type == WorkBlockerType.DEPENDENCY and input.blocking_task_id:
            resolution_task_id = input.blocking_task_id

        # Send feedback signal to aggregation service
        try:
            from services.feedback_aggregation_service import get_feedback_aggregation_service
            feedback_service = get_feedback_aggregation_service()
            signal = FeedbackSignal(
                signal_id=f"sig_{uuid.uuid4().hex[:12]}",
                project_id=work.project_id,
                worker_id=work.assigned_to or "unknown",
                task_id=input.task_id,
                feedback_type=FeedbackType.BLOCKER,
                severity=FeedbackSeverity.HIGH if work_blocker_type == WorkBlockerType.DEPENDENCY else FeedbackSeverity.MEDIUM,
                description=input.description,
                data={
                    "blocker_type": work_blocker_type.value,
                    "blocking_work_id": input.blocking_task_id or "",
                    "blocker_id": blocker.blocker_id,
                },
            )
            await feedback_service.process_signal(signal)
        except Exception as e:
            # Feedback processing is non-critical; don't fail the blocker
            logger.debug(f"Feedback aggregation unavailable: {e}")

        return BlockerResponse(
            acknowledged=True,
            blocker_id=blocker.blocker_id,
            resolution_task_id=resolution_task_id,
            status="blocked"
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error signaling blocker: {e}")
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
