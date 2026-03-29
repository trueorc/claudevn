"""claudevn_submit_challenge tool — structured worker challenges.

Allows compute instances to report structured challenges beyond simple
blockers. Challenges represent situations where a task may not be
achievable as specified, requiring planner attention.

Unlike blockers (which pause work), challenges inform the planner that
the task landscape has shifted and may need replanning.

Challenge types:
- task_infeasibility: Task as defined is not achievable
- scope_discovery: Area needs more work than anticipated
- dependency_correction: Dependency is wrong or missing
- quality_concern: Area too unstable to build on
"""

import logging
import uuid
from typing import Optional

from ..models import ReportChallengeInput, ChallengeResponse, MCPError
from models.feedback import (
    ChallengeType,
    FeedbackSignal,
    FeedbackSeverity,
    FeedbackType,
)
# v2.0: removed — from services.feedback_aggregation_service import get_feedback_aggregation_service
from services.work_map_service import get_work_map_service

logger = logging.getLogger(__name__)

# Map challenge severity strings to FeedbackSeverity
SEVERITY_MAP = {
    "low": FeedbackSeverity.LOW,
    "medium": FeedbackSeverity.MEDIUM,
    "high": FeedbackSeverity.HIGH,
    "critical": FeedbackSeverity.CRITICAL,
}

# Valid challenge type values
VALID_CHALLENGE_TYPES = {t.value for t in ChallengeType}


async def report_challenge(
    input: ReportChallengeInput,
) -> tuple[Optional[ChallengeResponse], Optional[MCPError]]:
    """Submit a structured challenge encountered during task execution.

    Challenges go beyond simple blockers — they indicate that a task
    may not be achievable as currently defined, or that the task's
    complexity/scope has changed significantly.
    """
    logger.warning(
        f"Challenge: task={input.task_id} type={input.challenge_type} "
        f"severity={input.severity} - {input.description}"
    )

    # Validate challenge type
    if input.challenge_type not in VALID_CHALLENGE_TYPES:
        return None, MCPError(
            code="INVALID_CHALLENGE_TYPE",
            message=(
                f"Invalid challenge_type '{input.challenge_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_CHALLENGE_TYPES))}"
            ),
        )

    try:
        work_map_service = get_work_map_service()

        # Verify task exists
        work = await work_map_service.get_work(input.task_id)
        if not work:
            return None, MCPError(
                code="TASK_NOT_FOUND",
                message=f"Task {input.task_id} not found"
            )

        project_id = work.project_id

        # Build feedback signal
        signal = FeedbackSignal(
            signal_id=f"sig_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            worker_id=input.worker_id,
            task_id=input.task_id,
            feedback_type=FeedbackType.CHALLENGE,
            severity=SEVERITY_MAP.get(input.severity, FeedbackSeverity.MEDIUM),
            description=input.description,
            data={
                "challenge_type": input.challenge_type,
                "impact_assessment": input.impact_assessment or "",
                "suggested_approach": input.suggested_approach or "",
                "affected_tasks": input.affected_tasks or [],
                "cluster_id": work.issue_id or "",
            },
        )

        # v2.0: Feedback aggregation service removed. Challenges are acknowledged
        # but no longer feed into planner profile adjustments.
        profile_updated = False
        pattern_detected = False

        # Record decision trace for challenge processing
        await _record_challenge_trace(
            project_id=project_id,
            signal=signal,
            input=input,
            profile_updated=profile_updated,
        )

        return ChallengeResponse(
            acknowledged=True,
            signal_id=signal.signal_id,
            profile_updated=profile_updated,
            pattern_detected=pattern_detected,
            status="challenge_recorded",
        ), None

    except RuntimeError as e:
        logger.error(f"Work map service not available: {e}")
        return None, MCPError(
            code="SERVICE_UNAVAILABLE",
            message="Work map service not initialized"
        )
    except Exception as e:
        logger.error(f"Error reporting challenge: {e}", exc_info=True)
        return None, MCPError(
            code="INTERNAL_ERROR",
            message=str(e)
        )


async def _record_challenge_trace(
    project_id: str,
    signal: FeedbackSignal,
    input: ReportChallengeInput,
    profile_updated: bool,
) -> None:
    """Record a decision trace for challenge processing."""
    try:
        from services.decision_trace_service import get_decision_trace_service
        from models.decision_trace import (
            DecisionImpact,
            DecisionPointType,
            DecisionTrigger,
        )

        service = get_decision_trace_service()

        affected_ids = [input.task_id] + (input.affected_tasks or [])

        await service.record(
            project_id=project_id,
            decision_type=DecisionPointType.PROFILE_SHIFT,
            trigger=DecisionTrigger(
                trigger_type="worker_challenge",
                source_id=signal.signal_id,
                source_type="challenge",
                description=(
                    f"Worker {input.worker_id} submitted {input.challenge_type} "
                    f"challenge for task {input.task_id}"
                ),
            ),
            decision_summary=(
                f"Challenge ({input.challenge_type}): {input.description[:100]}"
            ),
            key_factors=[
                f"Challenge type: {input.challenge_type}",
                f"Severity: {input.severity}",
                f"Profile updated: {profile_updated}",
            ],
            impact=DecisionImpact(
                affected_item_ids=affected_ids,
            ),
        )
    except Exception as e:
        logger.debug(f"Could not record challenge trace: {e}")
