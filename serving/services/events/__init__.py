"""Event system for v2.0 — queue-based pub/sub replacing all polling patterns."""

from .event_types import (
    EventCategory,
    Event,
    # Decomposition
    DecompositionStarted,
    DecompositionUpdated,
    DecompositionApproved,
    DecompositionFeedback,
    # Execution
    ExecutionQueued,
    ExecutionStarted,
    ExecutionCompleted,
    ExecutionFailed,
    # Verification
    VerificationStarted,
    VerificationCompleted,
    VerificationFailed,
    IntegrationConflict,
    # System
    SystemHealth,
    PresenceChanged,
)
from .event_bus import EventBus, Subscription, get_event_bus
from .sse_bridge import SSEBridge

__all__ = [
    # Bus
    "EventBus",
    "Subscription",
    "get_event_bus",
    "SSEBridge",
    # Types
    "EventCategory",
    "Event",
    "DecompositionStarted",
    "DecompositionUpdated",
    "DecompositionApproved",
    "DecompositionFeedback",
    "ExecutionQueued",
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "VerificationStarted",
    "VerificationCompleted",
    "VerificationFailed",
    "IntegrationConflict",
    "SystemHealth",
    "PresenceChanged",
]
