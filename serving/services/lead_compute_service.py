"""Lead Compute Service.

Orchestrates PR review by a dedicated lead compute instance before
merge approval. The lead reviewer checks for:
- Cross-module consistency (imports, config, API contracts)
- Missing migrations or seed data
- Coding convention adherence
- Integration issues that individual modules can't see

The review is dispatched to a compute instance with the lead-reviewer
skill and returns structured feedback (approve/request-changes).
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Timeout for lead review (3 minutes)
REVIEW_TIMEOUT_SECONDS = 180


class LeadReviewResult:
    """Result of a lead compute review."""

    def __init__(
        self,
        approved: bool,
        reviewer_id: str,
        summary: str = "",
        issues: list[Dict[str, str]] | None = None,
    ):
        self.approved = approved
        self.reviewer_id = reviewer_id
        self.summary = summary
        self.issues = issues or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "reviewer_id": self.reviewer_id,
            "summary": self.summary,
            "issues": self.issues,
        }


class LeadComputeService:
    """Service that manages lead compute PR reviews.

    Dispatches review work to an idle compute instance with the
    lead-reviewer skill, waits for the result, and returns a
    structured review decision.
    """

    def __init__(self, timeout: int = REVIEW_TIMEOUT_SECONDS):
        self._timeout = timeout
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def review_pr(
        self,
        project: str,
        branch: str,
        compute_id: str,
        work_title: str = "",
        work_description: str = "",
        project_id: str = "",
    ) -> LeadReviewResult:
        """Request a lead compute review of a PR.

        Dispatches the review to an idle compute instance with the
        lead-reviewer skill. If no compute is available or review
        times out, auto-approves to avoid blocking the pipeline.

        Args:
            project: Git project name
            branch: Branch being reviewed
            compute_id: Compute that created the PR (excluded from review)
            work_title: Title of the work for context
            work_description: Description of the work
            project_id: Project ID for context enrichment

        Returns:
            LeadReviewResult with approval decision
        """
        if not self._enabled:
            return LeadReviewResult(
                approved=True,
                reviewer_id="lead-review-disabled",
                summary="Lead review is disabled",
            )

        review_id = f"lead-review-{uuid.uuid4().hex[:12]}"

        logger.info(
            f"Requesting lead review {review_id} for {project}/{branch}"
        )

        # Build review task context
        task_context = self._build_review_context(
            review_id=review_id,
            project=project,
            branch=branch,
            work_title=work_title,
            work_description=work_description,
        )

        # Try to dispatch to an idle compute
        try:
            result = await self._dispatch_review(
                review_id=review_id,
                task_context=task_context,
                exclude_compute_id=compute_id,
                project_id=project_id,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                f"Lead review {review_id} timed out after {self._timeout}s, "
                "auto-approving"
            )
            return LeadReviewResult(
                approved=True,
                reviewer_id="lead-review-timeout",
                summary=f"Review timed out after {self._timeout}s, auto-approved",
            )
        except Exception as e:
            logger.warning(
                f"Lead review {review_id} failed: {e}, auto-approving"
            )
            return LeadReviewResult(
                approved=True,
                reviewer_id="lead-review-error",
                summary=f"Review dispatch failed: {e}",
            )

    def _build_review_context(
        self,
        review_id: str,
        project: str,
        branch: str,
        work_title: str = "",
        work_description: str = "",
    ) -> str:
        """Build the task context for the lead reviewer compute."""
        return f"""# Lead PR Review Task

## Assignment Details
- **Review ID:** {review_id}
- **Project:** {project}
- **Branch:** {branch}
- **Work Title:** {work_title}

## Work Description
{work_description or 'No description provided.'}

## Your Task
Review the changes on branch `{branch}` in project `{project}`.

Check for:
1. **Import correctness** — Are all imports valid? Any missing dependencies?
2. **Config completeness** — Are environment variables and config keys defined?
3. **Consistency** — Do patterns match existing codebase conventions?
4. **Missing pieces** — Any missing migrations, seed data, or initialization?
5. **API contract alignment** — Do interfaces match between modules?

## Output
Submit your review using `claudevn_submit_review` with:
- review_id: "{review_id}"
- approved: true/false
- summary: Brief summary of your findings
- issues: Array of {{severity, file, message}} for any problems found
"""

    async def _dispatch_review(
        self,
        review_id: str,
        task_context: str,
        exclude_compute_id: str = "",
        project_id: str = "",
    ) -> LeadReviewResult:
        """Dispatch review to an idle compute instance.

        Uses the SSE connection manager to find an idle compute and
        the completion event system to wait for the result.

        Args:
            review_id: Unique review identifier
            task_context: Review task description
            exclude_compute_id: Compute to exclude (PR author)
            project_id: Project ID for routing

        Returns:
            LeadReviewResult from the compute
        """
        from services.completion_events import create_event, get_event, cleanup as cleanup_event

        # Register completion event
        create_event(review_id)

        try:
            # Find an idle compute (exclude the PR author)
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()

            connection = sse_manager.find_matching_connection(
                idle_only=True,
                phase="review",
                exclude_compute_ids={exclude_compute_id} if exclude_compute_id else None,
            )

            if not connection:
                logger.info(
                    f"No idle compute available for lead review {review_id}, "
                    "auto-approving"
                )
                return LeadReviewResult(
                    approved=True,
                    reviewer_id="no-reviewer-available",
                    summary="No idle compute available for review",
                )

            # Get lead-reviewer skill instructions
            skill_instructions = await self._get_reviewer_skill_instructions()

            # Generate API key for review task
            from mcp.auth import generate_api_key, register_compute_key
            task_api_key = generate_api_key()
            await register_compute_key(connection.compute_id, task_api_key)

            mcp_config = {
                "server_url": "http://serving:8002",
                "api_key": task_api_key,
            }

            # Send review work to compute
            success = await sse_manager.send_work_assigned(
                compute_id=connection.compute_id,
                task_id=review_id,
                title=f"Lead PR Review {review_id}",
                description=task_context,
                branch_name="",
                skills={
                    "ids": ["lead-reviewer"],
                    "merged_instructions": skill_instructions,
                },
                context={
                    "review_id": review_id,
                    "task_type": "review",
                    "project_id": project_id,
                },
                mcp_config=mcp_config,
            )

            if not success:
                return LeadReviewResult(
                    approved=True,
                    reviewer_id="dispatch-failed",
                    summary="Failed to dispatch review to compute",
                )

            logger.info(
                f"Lead review {review_id} dispatched to compute {connection.compute_id}"
            )

            # Wait for result
            event = get_event(review_id)
            await asyncio.wait_for(event.wait(), timeout=self._timeout)

            # Fetch result from Redis
            from git.redis_client import get_redis
            redis = await get_redis()
            result_data = await redis.get(f"claudevn:review:{review_id}")

            if not result_data:
                return LeadReviewResult(
                    approved=True,
                    reviewer_id=connection.compute_id,
                    summary="Review completed but no result found",
                )

            data = json.loads(result_data)
            return LeadReviewResult(
                approved=data.get("approved", True),
                reviewer_id=connection.compute_id,
                summary=data.get("summary", ""),
                issues=data.get("issues", []),
            )

        finally:
            cleanup_event(review_id)

    async def _get_reviewer_skill_instructions(self) -> str:
        """Get lead-reviewer skill instructions from marketplace."""
        try:
            from services.marketplace_client import get_marketplace_client
            client = get_marketplace_client()
            skill = await client.get_skill("lead-reviewer")
            if skill and skill.get("instructions"):
                return skill["instructions"]
        except Exception as e:
            logger.debug(f"Could not fetch lead-reviewer skill: {e}")

        return """# Lead Reviewer
You are reviewing a PR for consistency and correctness.
Check imports, config, conventions, and cross-module integration.
Submit your review using claudevn_submit_review.
"""


# Module-level singleton
_service: Optional[LeadComputeService] = None


def get_lead_compute_service() -> LeadComputeService:
    """Get the singleton LeadComputeService."""
    global _service
    if _service is None:
        _service = LeadComputeService()
    return _service


def set_lead_compute_service(service: LeadComputeService) -> None:
    """Set the singleton LeadComputeService."""
    global _service
    _service = service
