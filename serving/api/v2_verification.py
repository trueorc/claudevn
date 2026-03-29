"""v2.0 Verification API — per-unit results, integration reports, actions.

Layer 3 endpoints for verification review and actions.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification", tags=["verification"])


# -- Response models --

class CheckResultResponse(BaseModel):
    check_type: str
    status: str
    details: str = ""
    output: Optional[str] = None


class UnitVerificationResponse(BaseModel):
    work_unit_id: str
    description: str = ""
    target_files: List[str] = Field(default_factory=list)
    results: List[CheckResultResponse] = Field(default_factory=list)


class VerificationResultsResponse(BaseModel):
    results: List[UnitVerificationResponse] = Field(default_factory=list)


class IntegrationReportResponse(BaseModel):
    unit_pairs_checked: int = 0
    merge_conflicts: List[dict] = Field(default_factory=list)
    interface_mismatches: List[dict] = Field(default_factory=list)
    combined_test_failures: List[str] = Field(default_factory=list)
    all_passed: bool = True


# -- Endpoints --

@router.get("/{project_id}/results", response_model=VerificationResultsResponse)
async def get_verification_results(project_id: str):
    """Get all verification results for a project.

    Returns per-unit verification status including individual
    check results (build, test, lint, type check, scope containment).
    """
    # TODO: wire to verification result storage
    return VerificationResultsResponse(results=[])


@router.get("/{project_id}/integration", response_model=IntegrationReportResponse)
async def get_integration_report(project_id: str):
    """Get cross-unit integration verification report.

    Shows merge conflicts, interface mismatches, and combined
    test results across all completed work units.
    """
    # TODO: wire to integration verifier
    return IntegrationReportResponse()


@router.get("/unit/{unit_id}")
async def get_unit_verification(unit_id: str):
    """Get verification results for a specific work unit."""
    # TODO: wire to per-unit verification storage
    return {"work_unit_id": unit_id, "results": []}


@router.post("/unit/{unit_id}/retry")
async def retry_verification(unit_id: str):
    """Retry verification for a failed work unit.

    Resubmits the work unit to the same Claude Code instance
    with failure context. Single retry — not an infinite loop.
    """
    # TODO: wire to retry handler
    return {"retried": True, "work_unit_id": unit_id}


@router.post("/unit/{unit_id}/approve")
async def approve_unit(unit_id: str):
    """Approve a work unit that needs human review.

    For cases where verification surfaced ambiguous results
    (e.g., scope containment warning) and human judgment is needed.
    """
    # TODO: wire to work unit status update
    return {"approved": True, "work_unit_id": unit_id}
