"""Data models for the Serving Component."""

from .compute import (
    ComputeInstance,
    InstanceStatus,
    InstanceCapabilities,
    InstanceResources,
    RegistrationRequest,
    RegistrationResponse,
    HeartbeatRequest,
)

__all__ = [
    "ComputeInstance",
    "InstanceStatus",
    "InstanceCapabilities",
    "InstanceResources",
    "RegistrationRequest",
    "RegistrationResponse",
    "HeartbeatRequest",
]

