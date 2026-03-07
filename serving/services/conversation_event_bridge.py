"""Bridge between observability events and conversation timeline."""

import logging
import time
from typing import Optional

from services.conversation_service import get_conversation_service
from services.observability_event_bus import get_event_bus
from models.observability import (
    WorkStatusChangeEvent,
    SessionCompletedEvent,
)

logger = logging.getLogger(__name__)


class ConversationEventBridge:
    """Subscribes to observability events and creates system messages in conversations."""

    def __init__(self):
        # Rate limiting: track last message time per (project_id, event_type)
        self._last_message_times: dict[tuple[str, str], float] = {}
        self._rate_limit_seconds = 30

    def _should_rate_limit(self, project_id: str, event_type: str) -> bool:
        key = (project_id, event_type)
        now = time.time()
        last = self._last_message_times.get(key, 0)
        if now - last < self._rate_limit_seconds:
            return True
        self._last_message_times[key] = now
        return False

    async def handle_event(self, event):
        """Event handler registered with ObservabilityEventBus."""
        try:
            await self._process_event(event)
        except Exception as e:
            logger.debug(f"Event bridge failed to process event: {e}")

    async def _process_event(self, event):
        service = get_conversation_service()
        if not service:
            return

        content = None
        project_id = None
        metadata = {}

        if isinstance(event, WorkStatusChangeEvent):
            # WorkStatusChangeEvent stores project_id in session_id field
            project_id = event.session_id
            if not project_id:
                return

            content = f"**{event.title}** moved to **{event.new_status}**"
            metadata = {
                'event_type': 'work_status_change',
                'work_id': event.work_id,
                'old_status': event.old_status,
                'new_status': event.new_status,
            }

        elif isinstance(event, SessionCompletedEvent):
            # SessionCompletedEvent has no project_id — skip
            return

        if not content or not project_id:
            return

        if self._should_rate_limit(project_id, metadata.get('event_type', '')):
            return

        await service.add_message(
            project_id=project_id,
            user_id="system",
            display_name="System",
            type="system",
            content=content,
            metadata=metadata,
        )


# Singleton
_bridge: Optional[ConversationEventBridge] = None


def get_event_bridge() -> Optional[ConversationEventBridge]:
    return _bridge


def init_event_bridge():
    """Initialize and register the event bridge with the event bus."""
    global _bridge
    _bridge = ConversationEventBridge()
    bus = get_event_bus()
    bus.add_handler(_bridge.handle_event)
    logger.info("ConversationEventBridge initialized")
    return _bridge
