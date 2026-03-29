"""Verification models for work units.

Defines how work unit output is verified — both automated per-unit
checks and cross-unit integration criteria.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AutomatedCheckType(str, Enum):
    """Types of automated verification checks."""
    TEST_PASS = "test_pass"
    LINT_CLEAN = "lint_clean"
    TYPE_CHECK = "type_check"
    BUILD_SUCCESS = "build_success"


class IntegrationCheckType(str, Enum):
    """Types of cross-unit integration checks."""
    INTERFACE_COMPATIBLE = "interface_compatible"
    MERGE_CLEAN = "merge_clean"
    COMBINED_TESTS_PASS = "combined_tests_pass"


class AutomatedCheck(BaseModel):
    """A computational verification check for a single work unit.

    These run as CI-style checks — no LLM judgment involved.
    """
    type: AutomatedCheckType = Field(..., description="Kind of check")
    target: str = Field(
        ...,
        description="What to check (e.g., test file path, lint config, build target)"
    )


class IntegrationCheck(BaseModel):
    """A cross-unit integration verification check.

    Verifies that independently-produced outputs integrate correctly.
    This is ClaudeVN's unique value — what no single instance can do.
    """
    type: IntegrationCheckType = Field(..., description="Kind of integration check")
    with_unit: str = Field(
        ...,
        description="Work unit ID to check integration against"
    )
    contract: str = Field(
        default="",
        description="The interface contract to verify compatibility against"
    )


class VerificationCriteria(BaseModel):
    """Complete verification criteria for a work unit.

    Separates automated (computational) checks from integration
    (cross-unit) checks. Automated checks run per-unit; integration
    checks run when multiple units complete.
    """
    automated: List[AutomatedCheck] = Field(
        default_factory=list,
        description="Per-unit computational checks"
    )
    integration: List[IntegrationCheck] = Field(
        default_factory=list,
        description="Cross-unit integration checks"
    )


class VerificationStatus(str, Enum):
    """Status of verification for a work unit."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class VerificationResult(BaseModel):
    """Result of running verification on a work unit."""
    check_type: str = Field(..., description="Which check produced this result")
    status: VerificationStatus = Field(..., description="Pass/fail status")
    details: str = Field(default="", description="Human-readable result details")
    output: Optional[str] = Field(
        default=None,
        description="Raw output from the check (test output, lint output, etc.)"
    )
