"""Issue Evaluation Service for post-completion review.

Evaluates completed issues to determine whether they achieved their intent:
- SUCCESS: Issue fully accomplished its goals
- PARTIAL: Some work done but gaps remain
- FAILURE: Issue did not achieve its intent

Failed/partial issues trigger follow-up issue creation for remediation.
Mirrors the GoalEvaluationService pattern for consistency.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from models.work_map import (
    Issue,
    IssueCreateRequest,
    IssueEvaluationOutcome,
    IssueEvaluationResult,
    IssueStatus,
    EvaluationStatus,
    RootCauseCategory,
)
from models.observability import IssueEvaluationStatusEvent

logger = logging.getLogger(__name__)


MAX_EVALUATION_RETRIES = 3
RETRY_DELAY_SECONDS = 5


class IssueEvaluationService:
    """Service for evaluating completed issues.

    Provides:
    - Async evaluation queue processing
    - Status transition management (NOT_EVALUATED -> EVALUATING -> EVALUATED/FAILED)
    - Retry logic for failed evaluations
    - Follow-up issue creation for partial/failed outcomes
    - Callback hooks for notifications
    - WebSocket event broadcasting
    """

    def __init__(
        self,
        issue_ops_service,
        max_retries: int = MAX_EVALUATION_RETRIES,
        retry_delay: float = RETRY_DELAY_SECONDS,
    ):
        """Initialize issue evaluation service.

        Args:
            issue_ops_service: IssueOpsService for issue access and follow-up creation
            max_retries: Maximum retry attempts for failed evaluations
            retry_delay: Delay between retries in seconds
        """
        self._issue_ops_service = issue_ops_service
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        # Evaluation queue
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._running = False

        # Status change callbacks
        self._on_status_change_callbacks: List[
            Callable[[str, EvaluationStatus, Optional[IssueEvaluationResult]], None]
        ] = []

        # Custom evaluator (can be replaced for testing or future LLM)
        self._evaluator: Optional[Callable[[Issue], IssueEvaluationResult]] = None

        self._initialized = False

    def set_evaluator(
        self,
        evaluator: Callable[[Issue], IssueEvaluationResult],
    ) -> None:
        """Set custom evaluator function.

        Args:
            evaluator: Async function that takes an Issue and returns IssueEvaluationResult
        """
        self._evaluator = evaluator

    def on_status_change(
        self,
        callback: Callable[[str, EvaluationStatus, Optional[IssueEvaluationResult]], None],
    ) -> None:
        """Register callback for status changes.

        Args:
            callback: Function called with (issue_id, new_status, result)
        """
        self._on_status_change_callbacks.append(callback)

    async def start(self) -> None:
        """Start the evaluation processing loop."""
        if self._running:
            return

        self._running = True
        self._processing_task = asyncio.create_task(self._process_queue())
        self._initialized = True
        logger.info("Issue evaluation service started")

    async def stop(self) -> None:
        """Stop the evaluation processing loop."""
        self._running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self._processing_task = None
        logger.info("Issue evaluation service stopped")

    async def queue_for_evaluation(self, issue_id: str) -> bool:
        """Queue a completed issue for evaluation.

        Args:
            issue_id: ID of the issue to evaluate

        Returns:
            True if queued successfully
        """
        issue = await self._issue_ops_service.get_issue(issue_id)
        if not issue:
            logger.warning(f"Cannot queue unknown issue {issue_id}")
            return False

        if issue.evaluation_status != EvaluationStatus.NOT_EVALUATED:
            logger.debug(f"Issue {issue_id} already processed, skipping queue")
            return False

        await self._queue.put(issue_id)
        logger.debug(f"Queued issue {issue_id} for evaluation")
        return True

    async def evaluate_issue(self, issue_id: str) -> Optional[IssueEvaluationResult]:
        """Evaluate a single issue synchronously.

        Full lifecycle: set EVALUATING -> run eval -> set EVALUATED/FAILED.

        Args:
            issue_id: ID of the issue to evaluate

        Returns:
            Evaluation result or None if evaluation failed
        """
        issue = await self._issue_ops_service.get_issue(issue_id)
        if not issue:
            logger.warning(f"Issue {issue_id} not found for evaluation")
            return None

        # Update status to evaluating
        await self._update_status(issue_id, EvaluationStatus.EVALUATING)

        try:
            result = await self._run_evaluation(issue)

            # Update with result
            await self._update_status(
                issue_id,
                EvaluationStatus.EVALUATED,
                result=result,
            )

            logger.info(
                f"Evaluated issue {issue_id}: outcome={result.outcome.value}"
            )

            # Create follow-up issue for partial/failure outcomes
            if result.requires_followup and result.outcome != IssueEvaluationOutcome.SUCCESS:
                followup_id = await self._create_followup_issue(issue, result)
                if followup_id:
                    result = IssueEvaluationResult(
                        outcome=result.outcome,
                        confidence=result.confidence,
                        summary=result.summary,
                        accomplishments=result.accomplishments,
                        gaps=result.gaps,
                        root_cause_category=result.root_cause_category,
                        root_cause_analysis=result.root_cause_analysis,
                        requires_followup=result.requires_followup,
                        followup_issue_id=followup_id,
                        evaluated_at=result.evaluated_at,
                        evaluator_version=result.evaluator_version,
                    )
                    # Update again with followup_issue_id
                    await self._update_status(
                        issue_id,
                        EvaluationStatus.EVALUATED,
                        result=result,
                    )

            return result

        except Exception as e:
            logger.error(f"Evaluation failed for issue {issue_id}: {e}")

            # Check retry count
            if issue.evaluation_retry_count < self._max_retries:
                issue.evaluation_retry_count += 1
                issue.evaluation_status = EvaluationStatus.NOT_EVALUATED
                await self._issue_ops_service._save_issue_to_redis(issue)
                self._notify_status_change(
                    issue_id,
                    EvaluationStatus.NOT_EVALUATED,
                    None,
                )
            else:
                await self._update_status(
                    issue_id,
                    EvaluationStatus.FAILED,
                    error=str(e),
                )

            return None

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def is_running(self) -> bool:
        """Check if the service is running."""
        return self._running

    # ============ Internal Methods ============

    async def _process_queue(self) -> None:
        """Background task that processes the evaluation queue."""
        while self._running:
            try:
                try:
                    issue_id = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                await self.evaluate_issue(issue_id)
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in issue evaluation queue processor: {e}")
                await asyncio.sleep(self._retry_delay)

    async def _run_evaluation(self, issue: Issue) -> IssueEvaluationResult:
        """Run the actual evaluation logic.

        Dispatches to custom evaluator if set, otherwise uses default heuristic.

        Args:
            issue: Issue to evaluate

        Returns:
            Evaluation result
        """
        if self._evaluator:
            return await self._evaluator(issue)

        return self._default_evaluation(issue)

    def _default_evaluation(self, issue: Issue) -> IssueEvaluationResult:
        """Default evaluation based on simple heuristics.

        Placeholder for future LLM-based evaluation.
        Heuristic: has result with summary + commits = SUCCESS,
        has result but no commits = PARTIAL, no result = FAILURE.

        Args:
            issue: Issue to evaluate

        Returns:
            Evaluation result based on heuristics
        """
        accomplishments = []
        gaps = []

        if issue.result and issue.result.summary:
            accomplishments.append(issue.result.summary)

        if issue.result and issue.result.commits:
            accomplishments.append(
                f"{len(issue.result.commits)} commit(s) produced"
            )

        if issue.result and issue.result.branch:
            accomplishments.append(f"Work branch: {issue.result.branch}")

        # Determine outcome
        has_result = issue.result is not None
        has_summary = has_result and bool(issue.result.summary)
        has_commits = has_result and len(issue.result.commits) > 0

        if has_summary and has_commits:
            outcome = IssueEvaluationOutcome.SUCCESS
            confidence = 0.7
            summary = "Issue completed with commits and summary"
            requires_followup = False
        elif has_result and (has_summary or has_commits):
            outcome = IssueEvaluationOutcome.PARTIAL
            confidence = 0.5
            summary = "Issue partially completed - missing commits or summary"
            requires_followup = True
            if not has_commits:
                gaps.append("No commits produced")
            if not has_summary:
                gaps.append("No completion summary provided")
        else:
            outcome = IssueEvaluationOutcome.FAILURE
            confidence = 0.6
            summary = "Issue completed without meaningful result"
            requires_followup = True
            gaps.append("No result data available")

        root_cause = None
        root_cause_analysis = None
        if outcome != IssueEvaluationOutcome.SUCCESS:
            root_cause = RootCauseCategory.OTHER
            root_cause_analysis = (
                "Default heuristic evaluation - manual review recommended"
            )

        return IssueEvaluationResult(
            outcome=outcome,
            confidence=confidence,
            summary=summary,
            accomplishments=accomplishments,
            gaps=gaps,
            root_cause_category=root_cause,
            root_cause_analysis=root_cause_analysis,
            requires_followup=requires_followup,
            evaluator_version="1.0-heuristic",
        )

    async def _update_status(
        self,
        issue_id: str,
        status: EvaluationStatus,
        result: Optional[IssueEvaluationResult] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update issue evaluation status and notify callbacks.

        Args:
            issue_id: Issue ID
            status: New evaluation status
            result: Optional evaluation result
            error: Optional error message
        """
        issue = await self._issue_ops_service.get_issue(issue_id)
        if not issue:
            return

        old_status = issue.evaluation_status
        issue.evaluation_status = status
        if result is not None:
            issue.evaluation_result = result
        issue.updated_at = datetime.now(timezone.utc)
        await self._issue_ops_service._save_issue_to_redis(issue)

        self._notify_status_change(issue_id, status, result)

        await self._broadcast_status_event(
            issue_id=issue_id,
            goal_id=issue.goal_id or "",
            old_status=old_status,
            new_status=status,
            result=result,
            error=error,
        )

    async def _broadcast_status_event(
        self,
        issue_id: str,
        goal_id: str,
        old_status: EvaluationStatus,
        new_status: EvaluationStatus,
        result: Optional[IssueEvaluationResult] = None,
        error: Optional[str] = None,
    ) -> None:
        """Broadcast evaluation status change via WebSocket.

        Args:
            issue_id: Issue ID
            goal_id: Parent goal ID
            old_status: Previous status
            new_status: New status
            result: Optional evaluation result
            error: Optional error message
        """
        try:
            from services.observability_event_bus import get_event_bus

            event = IssueEvaluationStatusEvent(
                event_id=f"issue_eval_{uuid.uuid4().hex[:12]}",
                session_id=goal_id,
                issue_id=issue_id,
                old_status=old_status.value,
                new_status=new_status.value,
                outcome=result.outcome.value if result else None,
                confidence=result.confidence if result else None,
                summary=result.summary if result else None,
                followup_issue_id=result.followup_issue_id if result else None,
                error=error,
            )

            event_bus = get_event_bus()
            await event_bus.emit_event(event)
            logger.debug(f"Broadcast issue evaluation status event for {issue_id}")

        except Exception as e:
            logger.warning(f"Failed to broadcast issue evaluation status event: {e}")

    def _notify_status_change(
        self,
        issue_id: str,
        status: EvaluationStatus,
        result: Optional[IssueEvaluationResult],
    ) -> None:
        """Notify all registered callbacks of status change.

        Args:
            issue_id: Issue ID
            status: New status
            result: Optional evaluation result
        """
        for callback in self._on_status_change_callbacks:
            try:
                callback(issue_id, status, result)
            except Exception as e:
                logger.error(f"Error in issue evaluation status change callback: {e}")

    async def _create_followup_issue(
        self,
        original: Issue,
        eval_result: IssueEvaluationResult,
    ) -> Optional[str]:
        """Create a follow-up issue for remediation.

        Inherits lineage and metadata from the original issue.

        Args:
            original: Original issue that was evaluated
            eval_result: Evaluation result with gaps and root cause

        Returns:
            Follow-up issue ID or None if creation failed
        """
        try:
            gaps_text = "\n".join(f"- {g}" for g in eval_result.gaps) if eval_result.gaps else "N/A"
            root_cause_text = eval_result.root_cause_analysis or "Not determined"
            accomplishments_text = (
                "\n".join(f"- {a}" for a in eval_result.accomplishments)
                if eval_result.accomplishments
                else "None"
            )

            description = (
                f"Follow-up for issue: {original.issue_id}\n\n"
                f"## Original Issue\n"
                f"**Title:** {original.title}\n"
                f"**Outcome:** {eval_result.outcome.value}\n\n"
                f"## Accomplishments\n{accomplishments_text}\n\n"
                f"## Gaps\n{gaps_text}\n\n"
                f"## Root Cause\n"
                f"**Category:** {eval_result.root_cause_category.value if eval_result.root_cause_category else 'N/A'}\n"
                f"**Analysis:** {root_cause_text}\n\n"
                f"## Remediation\n"
                f"Address the gaps identified above to complete the original intent."
            )

            request = IssueCreateRequest(
                title=f"[Follow-up] {original.title}",
                description=description,
                issue_type=original.issue_type,
                area=original.area,
                priority=original.priority,
                required_skills=list(original.required_skills),
                required_labels=list(original.required_labels),
                required_tools=list(original.required_tools),
                project_id=original.project_id,
                goal_id=original.goal_id,
                parent_issue_id=original.issue_id,
            )

            followup = await self._issue_ops_service.create_issue(request)
            logger.info(
                f"Created follow-up issue {followup.issue_id} for {original.issue_id}"
            )
            return followup.issue_id

        except Exception as e:
            logger.error(
                f"Failed to create follow-up issue for {original.issue_id}: {e}"
            )
            return None


# Global instance
_issue_evaluation_service: Optional[IssueEvaluationService] = None


def get_issue_evaluation_service() -> IssueEvaluationService:
    """Get the global issue evaluation service instance."""
    if _issue_evaluation_service is None:
        raise RuntimeError("Issue evaluation service not initialized")
    return _issue_evaluation_service


def set_issue_evaluation_service(service: Optional[IssueEvaluationService]) -> None:
    """Set the global issue evaluation service instance."""
    global _issue_evaluation_service
    _issue_evaluation_service = service
