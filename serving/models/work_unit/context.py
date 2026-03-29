"""Context package models for work units.

Defines the pre-assembled context injected into a Claude Code
instance before execution. The goal: everything needed in one shot,
no exploration phase required.
"""

from typing import List
from pydantic import BaseModel, Field


class ContextPackage(BaseModel):
    """Pre-assembled context for a Claude Code instance.

    Assembled during decomposition (Layer 1), injected at dispatch
    (Layer 2). The instance receives everything it needs without
    spending turns exploring the codebase.
    """
    files: List[str] = Field(
        default_factory=list,
        description="Pre-identified file paths to include as context"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="Output specs from upstream work units (for dependent units)"
    )
    relevant_tests: List[str] = Field(
        default_factory=list,
        description="Existing test files that must continue passing"
    )
