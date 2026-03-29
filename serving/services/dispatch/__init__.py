"""Dispatch service package (Layer 2) — v2.0 architecture.

Simple priority queue dispatch. Layer 2 should be boring — if it
needs intelligence, the decomposition in Layer 1 was insufficient.
"""

from .queue import DispatchQueue, QueueEntry
from .dispatcher import Dispatcher

__all__ = [
    "DispatchQueue",
    "QueueEntry",
    "Dispatcher",
]
