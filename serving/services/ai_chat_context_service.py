"""AI Chat Agent Context Management Service.

Maintains a compressed rolling summary and recent message window per project,
providing the AI agent with accurate, bounded context for every evaluation.

Key design decisions:
- Rolling summary stored in Redis per project with metadata
- Summary updates triggered every N messages or on topic shift
- Summary evolves (append + compress) rather than resetting
- Recent window retrieves last N messages from existing conversation storage
- Context assembly produces bounded prompt (~1000-1500 tokens total)
- Inactive project summaries expire via TTL (24h no activity)

Reference: Issue #252
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Summary update triggers
MESSAGES_BETWEEN_UPDATES = 12  # Update summary every N messages
SUMMARY_MAX_TOKENS_ESTIMATE = 500  # Approximate max tokens for summary
SUMMARY_TTL_SECONDS = 86400  # 24h TTL for inactive projects
RECENT_WINDOW_SIZE = 20  # Number of recent raw messages to include


class ConversationSummary(BaseModel):
    """Rolling conversation summary with metadata."""
    project_id: str
    summary_text: str = ""
    topic_tags: List[str] = Field(default_factory=list)
    message_count_since_update: int = 0
    total_messages_summarized: int = 0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def needs_update(self, threshold: int = MESSAGES_BETWEEN_UPDATES) -> bool:
        """Check if the summary needs updating based on message count."""
        return self.message_count_since_update >= threshold


class AssembledContext(BaseModel):
    """Complete context assembled for an AI agent evaluation."""
    system_prompt: str
    rolling_summary: Optional[str] = None
    summary_age_seconds: Optional[float] = None
    recent_messages: List[dict] = Field(default_factory=list)
    active_goals: List[str] = Field(default_factory=list)
    estimated_tokens: int = 0


class AIChatContextService:
    """Manages conversation context for the AI chat agent.

    Provides:
    - Rolling summary storage and retrieval (Redis-backed)
    - Summary update triggering and generation
    - Recent message window retrieval
    - Full context assembly for AI evaluation
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _key(self, suffix: str) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}ai_agent:summary:{suffix}"

    # =========================================================================
    # Summary CRUD
    # =========================================================================

    async def get_summary(self, project_id: str) -> ConversationSummary:
        """Get the rolling summary for a project.

        Returns a default empty summary if none exists.
        """
        if self._redis:
            try:
                raw = await self._redis._redis.get(self._key(project_id))
                if raw:
                    data = raw.decode() if isinstance(raw, bytes) else raw
                    return ConversationSummary.model_validate_json(data)
            except Exception as e:
                logger.error(f"Failed to load summary for {project_id}: {e}")

        return ConversationSummary(project_id=project_id)

    async def save_summary(self, summary: ConversationSummary) -> None:
        """Save the rolling summary to Redis with TTL."""
        if not self._redis:
            return

        try:
            key = self._key(summary.project_id)
            data = summary.model_dump_json()
            await self._redis._redis.set(key, data, ex=SUMMARY_TTL_SECONDS)
        except Exception as e:
            logger.error(f"Failed to save summary for {summary.project_id}: {e}")

    async def clear_summary(self, project_id: str) -> None:
        """Clear the summary for a project (e.g., when conversation is cleared)."""
        if not self._redis:
            return

        try:
            await self._redis._redis.delete(self._key(project_id))
            logger.info(f"Cleared AI agent summary for {project_id}")
        except Exception as e:
            logger.error(f"Failed to clear summary for {project_id}: {e}")

    # =========================================================================
    # Message Tracking & Update Triggering
    # =========================================================================

    async def record_message(self, project_id: str) -> bool:
        """Record that a new message was added and check if summary needs updating.

        Returns True if the summary should be regenerated.
        """
        summary = await self.get_summary(project_id)
        summary.message_count_since_update += 1
        await self.save_summary(summary)
        return summary.needs_update()

    async def update_summary(
        self,
        project_id: str,
        new_summary_text: str,
        topic_tags: Optional[List[str]] = None,
        messages_included: int = 0,
    ) -> ConversationSummary:
        """Update the rolling summary with new content.

        The caller is responsible for generating the summary text
        (via ClaudeClient). This method handles storage and metadata.

        Args:
            project_id: Project to update.
            new_summary_text: The new/evolved summary text.
            topic_tags: Optional topic tags extracted from content.
            messages_included: Number of messages that were summarized.

        Returns:
            Updated ConversationSummary.
        """
        summary = await self.get_summary(project_id)
        summary.summary_text = new_summary_text
        summary.topic_tags = topic_tags or summary.topic_tags
        summary.total_messages_summarized += messages_included or summary.message_count_since_update
        summary.message_count_since_update = 0
        summary.last_updated = datetime.now(timezone.utc)
        await self.save_summary(summary)

        logger.info(
            f"Updated AI agent summary for {project_id} "
            f"(total summarized: {summary.total_messages_summarized})"
        )
        return summary

    # =========================================================================
    # Recent Message Window
    # =========================================================================

    async def get_recent_messages(
        self,
        project_id: str,
        limit: int = RECENT_WINDOW_SIZE,
    ) -> List[dict]:
        """Get recent messages from the conversation service.

        Uses the existing ConversationService for retrieval.

        Returns:
            List of message dicts with display_name, content, type, timestamp.
        """
        try:
            from services.conversation_service import get_conversation_service
            conv_service = get_conversation_service()
            if not conv_service:
                return []

            messages, _, _ = await conv_service.get_messages(project_id, limit=limit)
            return [
                {
                    "display_name": msg.display_name,
                    "content": msg.content,
                    "type": msg.type,
                    "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                    "user_id": msg.user_id,
                }
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"Failed to get recent messages for {project_id}: {e}")
            return []

    # =========================================================================
    # Summary Generation Prompt
    # =========================================================================

    def build_summary_prompt(
        self,
        previous_summary: Optional[str],
        new_messages: List[dict],
    ) -> str:
        """Build the prompt for generating/evolving a rolling summary.

        The summary evolves by combining the previous summary with new messages
        into a compressed update (append + compress, not reset).

        Args:
            previous_summary: Existing summary text (None if first time).
            new_messages: New messages to incorporate.

        Returns:
            Prompt string for the summary generation call.
        """
        formatted = []
        for msg in new_messages:
            name = msg.get("display_name", "Unknown")
            content = msg.get("content", "")
            formatted.append(f"[{name}]: {content}")
        messages_text = "\n".join(formatted)

        if previous_summary:
            return (
                f"Previous conversation summary:\n{previous_summary}\n\n"
                f"New messages since last summary:\n{messages_text}\n\n"
                "Update the summary to incorporate these new messages. "
                "Preserve key decisions, open questions, actionable items, "
                "and track multiple discussion threads if present. "
                "Keep the summary under 500 tokens. "
                "Output ONLY the updated summary text."
            )
        else:
            return (
                f"Conversation messages:\n{messages_text}\n\n"
                "Summarize the key points, decisions, open questions, "
                "current topics, and any actionable items from these messages. "
                "Track multiple discussion threads if present. "
                "Keep the summary under 500 tokens. "
                "Output ONLY the summary text."
            )

    def build_topic_extraction_prompt(self, summary_text: str) -> str:
        """Build prompt to extract topic tags from a summary.

        Args:
            summary_text: The summary to extract topics from.

        Returns:
            Prompt string for topic extraction.
        """
        return (
            f"Extract 3-5 short topic tags from this conversation summary. "
            f"Output as a JSON array of strings, nothing else.\n\n"
            f"Summary: {summary_text}"
        )

    # =========================================================================
    # Context Assembly
    # =========================================================================

    async def assemble_context(
        self,
        project_id: str,
        project_name: str,
        system_prompt: str,
        active_goals: Optional[List[str]] = None,
        recent_message_limit: int = RECENT_WINDOW_SIZE,
    ) -> AssembledContext:
        """Assemble the full context for an AI agent evaluation.

        Combines system prompt, rolling summary, and recent messages
        into a bounded context package.

        Args:
            project_id: Project to assemble context for.
            project_name: Project name for display.
            system_prompt: Pre-built system prompt from prompt service.
            active_goals: List of active goal titles.
            recent_message_limit: Number of recent messages to include.

        Returns:
            AssembledContext with all components.
        """
        summary = await self.get_summary(project_id)
        recent = await self.get_recent_messages(project_id, limit=recent_message_limit)

        # Estimate age of summary
        summary_age = None
        if summary.summary_text:
            now = datetime.now(timezone.utc)
            summary_age = (now - summary.last_updated).total_seconds()

        # Rough token estimation (4 chars ≈ 1 token)
        total_chars = len(system_prompt)
        total_chars += len(summary.summary_text)
        for msg in recent:
            total_chars += len(msg.get("content", "")) + len(msg.get("display_name", ""))
        estimated_tokens = total_chars // 4

        return AssembledContext(
            system_prompt=system_prompt,
            rolling_summary=summary.summary_text or None,
            summary_age_seconds=summary_age,
            recent_messages=recent,
            active_goals=active_goals or [],
            estimated_tokens=estimated_tokens,
        )


# =============================================================================
# Module-level singleton
# =============================================================================

_context_service: Optional[AIChatContextService] = None


def get_ai_chat_context_service() -> Optional[AIChatContextService]:
    """Get the global AI chat context service instance."""
    return _context_service


def set_ai_chat_context_service(service: Optional[AIChatContextService]) -> None:
    """Set the global AI chat context service instance."""
    global _context_service
    _context_service = service
