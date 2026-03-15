"""Conversation persistence service using Redis."""

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

from models.conversation import ConversationMessage

logger = logging.getLogger(__name__)

# Max messages per project conversation
MAX_MESSAGES = 500
# Default page size
DEFAULT_LIMIT = 50

# Type for message listener: (project_id, user_id, message_type, content) -> None
MessageListener = Callable[[str, str, str, str], Awaitable[None]]


class ConversationService:
    """Manages project conversation persistence in Redis."""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._message_listener: Optional[MessageListener] = None

    def set_message_listener(self, listener: MessageListener) -> None:
        """Register a listener called after each message is persisted."""
        self._message_listener = listener

    def _key(self, project_id: str) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}conversation:{project_id}"

    async def get_messages(
        self,
        project_id: str,
        limit: int = DEFAULT_LIMIT,
        before: Optional[str] = None,
    ) -> tuple[list[ConversationMessage], int, bool]:
        """Get conversation messages for a project.

        Returns (messages, total_count, has_more).
        Messages are returned in chronological order (oldest first).
        """
        if not self._redis:
            return [], 0, False

        key = self._key(project_id)
        try:
            total = await self._redis._redis.llen(key)

            if before:
                # Find the index of the 'before' message and return messages before it
                all_raw = await self._redis._redis.lrange(key, 0, -1)
                found_idx = None
                for idx, raw in enumerate(all_raw):
                    msg = self._deserialize(raw)
                    if msg and msg.message_id == before:
                        found_idx = idx
                        break

                if found_idx is not None and found_idx > 0:
                    start = max(0, found_idx - limit)
                    raw_slice = all_raw[start:found_idx]
                    messages = [self._deserialize(r) for r in raw_slice]
                    messages = [m for m in messages if m is not None]
                    has_more = start > 0
                    return messages, total, has_more
                return [], total, False

            # Get last N messages
            start = max(0, total - limit)
            raw_messages = await self._redis._redis.lrange(key, start, -1)
            messages = [self._deserialize(r) for r in raw_messages]
            messages = [m for m in messages if m is not None]
            has_more = start > 0
            return messages, total, has_more
        except Exception as e:
            logger.error(f"Failed to get conversation for {project_id}: {e}")
            return [], 0, False

    async def add_message(
        self,
        project_id: str,
        user_id: str,
        display_name: str,
        type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> ConversationMessage:
        """Add a message to a project conversation."""
        msg = ConversationMessage(
            project_id=project_id,
            user_id=user_id,
            display_name=display_name,
            type=type,
            content=content,
            metadata=metadata or {},
        )

        if self._redis:
            key = self._key(project_id)
            try:
                await self._redis._redis.rpush(key, msg.model_dump_json())
                # Cap the list to MAX_MESSAGES
                await self._redis._redis.ltrim(key, -MAX_MESSAGES, -1)
            except Exception as e:
                logger.error(f"Failed to persist message for {project_id}: {e}")

        await self._broadcast_message(msg)

        # Notify AI agent (fire-and-forget, never blocks message delivery).
        # Only for user messages — system/status messages should not trigger
        # AI review as they create chat clutter.
        if self._message_listener and type == "user":
            try:
                logger.info(f"Notifying AI agent for {project_id} (type={type}, user={user_id})")
                asyncio.create_task(
                    self._message_listener(project_id, user_id, type, content)
                )
            except Exception as e:
                logger.warning(f"Message listener notification failed: {e}")

        return msg

    async def _broadcast_message(self, msg: ConversationMessage) -> None:
        """Broadcast a conversation message to all WebSocket clients."""
        try:
            from services.observability_event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                payload = json.dumps({
                    'type': 'conversation_message',
                    'event': {
                        'project_id': msg.project_id,
                        'message': msg.model_dump(mode='json'),
                    },
                }, default=str)
                # Reuse the _broadcast_to_all plumbing by sending raw text to all connections
                await bus._broadcast_raw(payload)
        except Exception as e:
            logger.debug(f"Failed to broadcast conversation message: {e}")

    async def remove_message(self, project_id: str, message_id: str) -> bool:
        """Remove a specific message from the conversation (e.g., thinking indicators)."""
        if not self._redis:
            return False
        key = self._key(project_id)
        try:
            # Scan the list for the message and remove it
            all_raw = await self._redis._redis.lrange(key, 0, -1)
            for raw in all_raw:
                msg = self._deserialize(raw)
                if msg and msg.message_id == message_id:
                    await self._redis._redis.lrem(key, 1, raw)
                    return True
        except Exception as e:
            logger.error(f"Failed to remove message {message_id}: {e}")
        return False

    async def clear(self, project_id: str) -> None:
        """Clear all messages for a project conversation."""
        if not self._redis:
            return
        try:
            await self._redis._redis.delete(self._key(project_id))
        except Exception as e:
            logger.error(f"Failed to clear conversation for {project_id}: {e}")

    def _deserialize(self, raw) -> Optional[ConversationMessage]:
        """Deserialize a Redis value to ConversationMessage."""
        try:
            data = raw.decode() if isinstance(raw, bytes) else raw
            return ConversationMessage.model_validate_json(data)
        except Exception:
            return None


# Module-level singleton
_conversation_service: Optional[ConversationService] = None


def get_conversation_service() -> Optional[ConversationService]:
    """Get the global conversation service instance."""
    return _conversation_service


def set_conversation_service(service: Optional[ConversationService]) -> None:
    """Set the global conversation service instance."""
    global _conversation_service
    _conversation_service = service
