"""Async event bus for v2.0 inter-layer communication.

Queue-based pub/sub — no polling. Components publish events,
subscribers receive them through async queues. The SSE bridge
forwards events to frontend clients.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Awaitable, Optional, Set
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Subscription:
    """A subscriber's connection to the event bus.

    Each subscription has its own async queue. Events matching
    the subscription's patterns are delivered to the queue.
    """

    def __init__(self, patterns: Set[str], subscriber_id: str):
        self.patterns = patterns
        self.subscriber_id = subscriber_id
        self._queue: asyncio.Queue[BaseModel] = asyncio.Queue()
        self._active = True

    async def receive(self) -> BaseModel:
        """Wait for and return the next event. Blocks until available."""
        return await self._queue.get()

    async def receive_timeout(self, timeout: float) -> Optional[BaseModel]:
        """Wait for the next event with a timeout. Returns None on timeout."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def matches(self, event_name: str) -> bool:
        """Check if this subscription wants this event.

        Supports exact match ("execution.started") and prefix
        match ("execution.*", "verification.*").
        """
        for pattern in self.patterns:
            if pattern == "*":
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event_name.startswith(prefix + "."):
                    return True
            elif pattern == event_name:
                return True
        return False

    def cancel(self):
        """Cancel this subscription."""
        self._active = False


class EventBus:
    """Async event bus for the v2.0 system.

    Replaces all polling patterns with push-based event delivery.
    Components subscribe to event patterns and receive events
    through async queues.

    Usage:
        bus = EventBus()

        # Subscribe
        sub = bus.subscribe({"execution.*"}, "dashboard")

        # Publish (from any layer)
        await bus.publish(ExecutionStarted(work_unit_id="wu-001", ...))

        # Receive (in subscriber's async loop)
        event = await sub.receive()
    """

    def __init__(self):
        self._subscriptions: list[Subscription] = []
        self._handlers: dict[str, list[Callable[[BaseModel], Awaitable[None]]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        logger.info("EventBus initialized")

    def subscribe(self, patterns: Set[str], subscriber_id: str = "") -> Subscription:
        """Create a subscription for events matching the given patterns.

        Args:
            patterns: Event name patterns to match. Supports exact
                ("execution.started") and prefix ("execution.*").
            subscriber_id: Identifier for logging/debugging.

        Returns:
            A Subscription whose receive() method delivers matching events.
        """
        sub = Subscription(patterns, subscriber_id)
        self._subscriptions.append(sub)
        logger.debug(f"New subscription: {subscriber_id} -> {patterns}")
        return sub

    def unsubscribe(self, subscription: Subscription):
        """Remove a subscription."""
        subscription.cancel()
        self._subscriptions = [s for s in self._subscriptions if s._active]
        logger.debug(f"Unsubscribed: {subscription.subscriber_id}")

    def on(self, event_name: str, handler: Callable[[BaseModel], Awaitable[None]]):
        """Register a handler for a specific event type.

        Handlers run inline during publish — use for lightweight
        reactions (status updates, logging). For heavy work, use
        subscribe() and process in a separate task.
        """
        self._handlers[event_name].append(handler)

    async def publish(self, event: BaseModel):
        """Publish an event to all matching subscribers and handlers.

        Args:
            event: A Pydantic event model with an 'event' field.
        """
        event_name = getattr(event, "event", "unknown")

        # Run registered handlers
        for handler in self._handlers.get(event_name, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Handler error for {event_name}: {e}")

        # Deliver to matching subscriptions
        dead = []
        for sub in self._subscriptions:
            if not sub._active:
                dead.append(sub)
                continue
            if sub.matches(event_name):
                try:
                    sub._queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(
                        f"Queue full for {sub.subscriber_id}, dropping {event_name}"
                    )

        # Clean up dead subscriptions
        if dead:
            self._subscriptions = [s for s in self._subscriptions if s._active]

        logger.debug(f"Published {event_name}")


# Singleton instance — import and use directly
_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the singleton EventBus instance."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
