"""Work unit models — the v2.0 contract between decomposition, execution, and verification."""

from .formal_spec import (
    FormalSpec,
    InterfaceContract,
    InterfaceType,
    ExpectedOutput,
    OutputType,
)
from .verification import (
    VerificationCriteria,
    AutomatedCheck,
    AutomatedCheckType,
    IntegrationCheck,
    IntegrationCheckType,
    VerificationStatus,
    VerificationResult,
)
from .context import ContextPackage
from .independence import IndependenceAssertion
from .work_unit import WorkUnit, WorkUnitStatus

__all__ = [
    # Core
    "WorkUnit",
    "WorkUnitStatus",
    # Formal spec
    "FormalSpec",
    "InterfaceContract",
    "InterfaceType",
    "ExpectedOutput",
    "OutputType",
    # Verification
    "VerificationCriteria",
    "AutomatedCheck",
    "AutomatedCheckType",
    "IntegrationCheck",
    "IntegrationCheckType",
    "VerificationStatus",
    "VerificationResult",
    # Context
    "ContextPackage",
    # Independence
    "IndependenceAssertion",
]
