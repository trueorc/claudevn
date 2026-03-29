"""Verification-driven retry logic.

When verification fails, determines whether to:
1. Retry automatically (clear failure with specific fix info)
2. Send back to decomposition (scope violation, interface mismatch)
3. Escalate to human (ambiguous failure, repeated failure)

Single retry only — not an infinite loop.
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

from models.work_unit import WorkUnit, VerificationResult, VerificationStatus

logger = logging.getLogger(__name__)


class RetryDecision(str, Enum):
    """What to do when verification fails."""
    RETRY = "retry"                     # Resubmit to same instance with failure context
    REDECOMPOSE = "redecompose"         # Send back to Layer 1 (decomposition was wrong)
    ESCALATE = "escalate"               # Human review needed


@dataclass
class RetryAction:
    """The determined action for a failed verification."""
    decision: RetryDecision
    reason: str
    failure_context: str = ""  # Context to include in retry prompt
    work_unit_id: str = ""


class RetryHandler:
    """Determines the appropriate action for verification failures.

    Implements the v2.0 verification-driven iteration model:
    - Single retry for clear, fixable failures
    - Decomposition feedback for structural problems
    - Human escalation for ambiguity
    """

    MAX_RETRIES = 1

    def determine_action(
        self,
        unit: WorkUnit,
        results: List[VerificationResult],
    ) -> RetryAction:
        """Determine what to do about failed verification results.

        Args:
            unit: The work unit that failed verification.
            results: The verification results (some failed).

        Returns:
            RetryAction with the decision and context.
        """
        failed = [r for r in results if r.status == VerificationStatus.FAILED]
        needs_review = [r for r in results if r.status == VerificationStatus.NEEDS_HUMAN_REVIEW]

        if not failed and not needs_review:
            # Shouldn't be called if nothing failed, but handle gracefully
            return RetryAction(
                decision=RetryDecision.RETRY,
                reason="No failures detected",
                work_unit_id=unit.id,
            )

        # Scope violations → redecompose (the decomposition was wrong)
        scope_violations = [r for r in needs_review if r.check_type == "scope_containment"]
        if scope_violations:
            return RetryAction(
                decision=RetryDecision.REDECOMPOSE,
                reason="Work unit modified files outside its target scope",
                failure_context=scope_violations[0].details,
                work_unit_id=unit.id,
            )

        # Interface mismatches → redecompose
        iface_failures = [r for r in failed if r.check_type == "interface_compatible"]
        if iface_failures:
            return RetryAction(
                decision=RetryDecision.REDECOMPOSE,
                reason="Interface contract mismatch between work units",
                failure_context=iface_failures[0].details,
                work_unit_id=unit.id,
            )

        # Already retried → escalate
        if unit.retry_count >= self.MAX_RETRIES:
            return RetryAction(
                decision=RetryDecision.ESCALATE,
                reason=f"Failed after {unit.retry_count} retry(s)",
                failure_context=self._summarize_failures(failed),
                work_unit_id=unit.id,
            )

        # Clear failures (test, build, lint, type) → retry with context
        retryable_types = {"test_pass", "build_success", "lint_clean", "type_check"}
        retryable = [r for r in failed if r.check_type in retryable_types]
        if retryable:
            return RetryAction(
                decision=RetryDecision.RETRY,
                reason=f"Retryable failure: {retryable[0].check_type}",
                failure_context=self._build_retry_context(unit, retryable),
                work_unit_id=unit.id,
            )

        # Anything else → escalate
        return RetryAction(
            decision=RetryDecision.ESCALATE,
            reason="Ambiguous verification failure",
            failure_context=self._summarize_failures(failed + needs_review),
            work_unit_id=unit.id,
        )

    def _build_retry_context(
        self,
        unit: WorkUnit,
        failures: List[VerificationResult],
    ) -> str:
        """Build context to include in the retry prompt."""
        lines = [
            f"## Retry Context for {unit.id}",
            "",
            "Your previous attempt failed the following checks:",
            "",
        ]
        for f in failures:
            lines.append(f"### {f.check_type}: FAILED")
            lines.append(f.details)
            if f.output:
                lines.append(f"```\n{f.output[-1000:]}\n```")
            lines.append("")

        lines.append("Please fix the issues above and resubmit.")
        return "\n".join(lines)

    def _summarize_failures(self, failures: List[VerificationResult]) -> str:
        """Summarize failures for human review."""
        return "; ".join(
            f"{f.check_type}: {f.details}" for f in failures
        )
