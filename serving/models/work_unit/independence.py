"""Independence assertion models for work units.

Defines how work units declare their independence from each other.
True independence means no shared mutable state during execution —
if units must share state, they should be a single unit.
"""

from typing import List
from pydantic import BaseModel, Field


class IndependenceAssertion(BaseModel):
    """Asserts how this work unit relates to others in terms of independence.

    The decomposition layer produces these assertions; the validation
    layer checks them. If shares_files_with is non-empty, the
    decomposition should be flagged for human review.
    """
    shares_files_with: List[str] = Field(
        default_factory=list,
        description="Other work unit IDs that touch the same files (should be empty)"
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="Work unit IDs that must complete before this one starts"
    )
    depended_by: List[str] = Field(
        default_factory=list,
        description="Work unit IDs waiting on this one to complete"
    )
