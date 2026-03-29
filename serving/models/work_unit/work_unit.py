"""Core work unit model — the contract between all three layers.

A work unit is the atomic unit of work in v2.0. It is produced by
Layer 1 (decomposition), executed by Layer 2 (dispatch to Claude Code),
and verified by Layer 3 (integration verification).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .formal_spec import FormalSpec
from .verification import VerificationCriteria
from .context import ContextPackage
from .independence import IndependenceAssertion


class WorkUnitStatus(str, Enum):
    """Lifecycle status of a work unit."""
    DRAFT = "draft"                     # Being refined in Layer 1
    READY = "ready"                     # Approved, waiting for dispatch
    QUEUED = "queued"                   # In the dispatch queue
    EXECUTING = "executing"             # Claude Code instance is working
    SUBMITTED = "submitted"             # PR submitted, awaiting verification
    VERIFYING = "verifying"             # Layer 3 verification running
    VERIFIED = "verified"               # All checks passed
    FAILED_VERIFICATION = "failed_verification"  # Verification failed
    RETRYING = "retrying"               # Single retry in progress
    NEEDS_HUMAN_REVIEW = "needs_human_review"    # Escalated to human
    COMPLETED = "completed"             # Merged and done
    CANCELLED = "cancelled"             # Cancelled by user or system


class WorkUnit(BaseModel):
    """The atomic unit of work in ClaudeVN v2.0.

    Produced by decomposition, executed by Claude Code, verified
    by the integration layer. This is the contract between all
    three layers of the system.
    """
    # Identity
    id: str = Field(..., description="Unique work unit identifier")
    project_id: str = Field(..., description="Project this work unit belongs to")
    goal_ref: str = Field(..., description="Reference to the parent goal")

    # What to do
    description: str = Field(
        ...,
        description="Natural language description for human review"
    )
    formal_spec: FormalSpec = Field(
        ...,
        description="Structured specification of what to produce"
    )

    # How to verify
    verification_criteria: VerificationCriteria = Field(
        default_factory=VerificationCriteria,
        description="Automated and integration verification checks"
    )

    # Context to inject
    context_package: ContextPackage = Field(
        default_factory=ContextPackage,
        description="Pre-assembled context for the executing instance"
    )

    # Independence assertion
    independence: IndependenceAssertion = Field(
        default_factory=IndependenceAssertion,
        description="How this unit relates to others in terms of independence"
    )

    # Quality metadata (from LLM decomposition)
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Testable conditions that prove this unit is done"
    )
    estimated_complexity: str = Field(
        default="m",
        description="Estimated complexity: xs, s, m, l, xl"
    )
    interface_produces: List[Dict[str, str]] = Field(
        default_factory=list,
        description="What this unit produces for others (type + definition)"
    )
    interface_consumes: List[Dict[str, str]] = Field(
        default_factory=list,
        description="What this unit expects from its dependencies (type + definition)"
    )

    # Lifecycle
    status: WorkUnitStatus = Field(
        default=WorkUnitStatus.DRAFT,
        description="Current lifecycle status"
    )
    assigned_instance: Optional[str] = Field(
        default=None,
        description="Compute instance ID executing this unit"
    )
    branch: Optional[str] = Field(
        default=None,
        description="Git branch for this unit's work"
    )
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts (max 1)"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
