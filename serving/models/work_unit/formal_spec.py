"""Formal specification models for work units.

Defines what a work unit must accomplish — target files, interface
contracts, and expected outputs. This is the structured specification
that replaces natural-language-only task descriptions.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class InterfaceType(str, Enum):
    """Types of interface contracts a work unit must respect."""
    IMPORTS = "imports"
    EXPORTS = "exports"
    SCHEMA = "schema"
    API = "api"


class OutputType(str, Enum):
    """Types of expected file-level outputs."""
    FILE_MODIFIED = "file_modified"
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"


class InterfaceContract(BaseModel):
    """A contract this work unit must conform to.

    Defines an interface boundary — the work unit's changes must
    respect this contract to integrate correctly with adjacent code.
    """
    file: str = Field(..., description="File containing the interface")
    type: InterfaceType = Field(..., description="Kind of interface")
    definition: str = Field(
        ...,
        description="The interface definition (e.g., function signature, schema shape)"
    )


class ExpectedOutput(BaseModel):
    """An expected file-level change from this work unit."""
    type: OutputType = Field(..., description="Kind of file change")
    path: str = Field(..., description="File path affected")
    constraints: List[str] = Field(
        default_factory=list,
        description="Constraints on the change (e.g., 'must export function X with signature Y')"
    )


class FormalSpec(BaseModel):
    """The formal specification of what a work unit must produce.

    Moves beyond natural language descriptions to structured,
    verifiable specifications that Layer 3 can check computationally.
    """
    target_files: List[str] = Field(
        ...,
        description="Exact files this work unit will modify"
    )
    interface_contracts: List[InterfaceContract] = Field(
        default_factory=list,
        description="Interface boundaries this unit must respect"
    )
    input_state: str = Field(
        ...,
        description="Git ref / branch this work unit starts from"
    )
    expected_outputs: List[ExpectedOutput] = Field(
        default_factory=list,
        description="Expected file-level changes"
    )
