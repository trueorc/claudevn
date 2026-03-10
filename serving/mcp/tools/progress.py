"""claudevn_report_progress tool."""

import logging
from datetime import datetime, timezone
from typing import Optional

from ..models import ReportProgressInput, ProgressAck, MCPError, TaskStatus
from services.work_map_service import get_work_map_service
from models.work_map import WorkStatus, ProgressReport

logger = logging.getLogger(__name__)

# Map MCP TaskStatus to Work Map WorkStatus
STATUS_MAP = {
    TaskStatus.STARTED: WorkStatus.IN_PROGRESS,
    TaskStatus.IN_PROGRESS: WorkStatus.IN_PROGRESS,
    TaskStatus.BLOCKED: WorkStatus.BLOCKED,
    TaskStatus.REVIEW_REQUESTED: WorkStatus.REVIEW,
    TaskStatus.IMPLEMENTED: WorkStatus.IMPLEMENTED,
    TaskStatus.COMPLETED: WorkStatus.IMPLEMENTED,
}


async def report_progress(input: ReportProgressInput) -> tuple[Optional[ProgressAck], Optional[MCPError]]:
    """Report task progress.

    Updates the Work Map service with progress information including
    status, completion percentage, and optional notes.
    """
    logger.info(f"Progress: task={input.task_id} status={input.status} progress={input.progress_percent}%")

    try:
        service = get_work_map_service()

        # Convert MCP status to Work Map status
        work_status = STATUS_MAP.get(input.status, WorkStatus.IN_PROGRESS)

        # Create progress report
        report = ProgressReport(
            work_id=input.task_id,
            progress_percent=input.progress_percent or 0,
            status=work_status,
            note=input.message,
            blockers=[]
        )

        # Update work item
        work = await service.report_progress(input.task_id, report)

        if not work:
            return None, MCPError(
                code="TASK_NOT_FOUND",
                message=f"Task {input.task_id} not found"
            )

        return ProgressAck(
            acknowledged=True,
            task_id=input.task_id,
            updated_at=datetime.now(timezone.utc)
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error reporting progress: {e}")
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )
