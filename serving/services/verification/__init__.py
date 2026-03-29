"""Verification service package (Layer 3) — v2.0 architecture.

Verifies that independently-produced work unit outputs integrate
correctly and meet quality standards. Prefers computation over
judgment — every check that can be automated is automated.
"""

from .unit_verifier import UnitVerifier
from .integration_verifier import IntegrationVerifier, IntegrationReport
from .retry_handler import RetryHandler, RetryAction, RetryDecision

__all__ = [
    "UnitVerifier",
    "IntegrationVerifier",
    "IntegrationReport",
    "RetryHandler",
    "RetryAction",
    "RetryDecision",
]
