"""AI Chat Agent Service - Backend Conversation Watcher.

Watches project conversations via a callback from ConversationService,
maintains a debounce timer per project, evaluates whether to respond
using the prompt framework (#251) and context layer (#252), and posts
responses as 'assistant' type messages.

Key design decisions:
- 4-second debounce per project (resets on each new message)
- Haiku-first for cost-effective conversational responses
- One evaluation at a time per project (skip if previous still running)
- Failed evaluations logged and silently dropped
- Fully async, non-blocking

Reference: Issue #246
"""

import asyncio
import logging
from typing import Dict, Optional, Set

from models.ai_chat_agent import AgentEvaluation, AIChatAgentConfig
from models.claude_client import ClaudeModel

logger = logging.getLogger(__name__)

# AI agent identity
AI_AGENT_USER_ID = "ai-agent"
AI_AGENT_DISPLAY_NAME = "Claude"

# Default debounce (can be overridden per project via AIChatAgentConfig)
DEFAULT_DEBOUNCE_SECONDS = 4.0


class AIChatAgentService:
    """Watches project conversations and responds when appropriate.

    Lifecycle:
    1. Registered as a message callback on ConversationService
    2. On each message: resets debounce timer for that project
    3. After silence: evaluates context and optionally responds
    4. Responses posted via ConversationService as 'assistant' messages
    """

    def __init__(self):
        # Per-project debounce timers (asyncio.Task)
        self._debounce_tasks: Dict[str, asyncio.Task] = {}
        # Track which projects have an evaluation in flight
        self._evaluating: Set[str] = set()
        # Per-project configs (lazy-loaded, defaults used if absent)
        self._configs: Dict[str, AIChatAgentConfig] = {}
        self._started = False

    def start(self) -> None:
        """Register as a message listener on the ConversationService."""
        if self._started:
            return
        self._started = True
        logger.info("AI Chat Agent Service started")

    def stop(self) -> None:
        """Cancel all pending debounce timers and shut down."""
        for task in self._debounce_tasks.values():
            task.cancel()
        self._debounce_tasks.clear()
        self._evaluating.clear()
        self._started = False
        logger.info("AI Chat Agent Service stopped")

    def get_config(self, project_id: str) -> AIChatAgentConfig:
        """Get the config for a project (returns defaults if not set)."""
        return self._configs.get(project_id, AIChatAgentConfig())

    def set_config(self, project_id: str, config: AIChatAgentConfig) -> None:
        """Set per-project agent configuration."""
        self._configs[project_id] = config

    # =========================================================================
    # Message Callback (called by ConversationService)
    # =========================================================================

    async def on_message(
        self,
        project_id: str,
        user_id: str,
        message_type: str,
        content: str,
    ) -> None:
        """Called when a new message is added to a project conversation.

        Ignores messages from the AI agent itself to prevent loops.
        Resets the debounce timer for the project.
        """
        if not self._started:
            return

        # Ignore our own messages to prevent feedback loops
        if user_id == AI_AGENT_USER_ID:
            return

        # Only react to user messages (not system, thinking, etc.)
        if message_type not in ("user", "assistant"):
            return

        config = self.get_config(project_id)
        if not config.enabled:
            return

        # Record message for context tracking
        try:
            from services.ai_chat_context_service import get_ai_chat_context_service
            context_service = get_ai_chat_context_service()
            if context_service:
                needs_summary = await context_service.record_message(project_id)
                if needs_summary:
                    asyncio.create_task(
                        self._update_summary(project_id)
                    )
        except Exception as e:
            logger.debug(f"Context tracking failed for {project_id}: {e}")

        # Reset debounce timer
        self._reset_debounce(project_id, config.debounce_seconds)

    # =========================================================================
    # Debounce
    # =========================================================================

    def _reset_debounce(self, project_id: str, delay: float) -> None:
        """Reset the debounce timer for a project."""
        # Cancel existing timer if any
        existing = self._debounce_tasks.get(project_id)
        if existing and not existing.done():
            existing.cancel()

        # Create new timer
        self._debounce_tasks[project_id] = asyncio.create_task(
            self._debounce_fire(project_id, delay)
        )

    async def _debounce_fire(self, project_id: str, delay: float) -> None:
        """Wait for the debounce period, then trigger evaluation."""
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(delay)
            await self._evaluate(project_id)
        except asyncio.CancelledError:
            pass  # Timer was reset by a new message
        except Exception as e:
            logger.error(f"Debounce evaluation failed for {project_id}: {e}")
        finally:
            # Only clean up if we're still the active task (not replaced by a reset)
            if self._debounce_tasks.get(project_id) is current_task:
                self._debounce_tasks.pop(project_id, None)

    # =========================================================================
    # Evaluation
    # =========================================================================

    async def _evaluate(self, project_id: str) -> None:
        """Evaluate the conversation and optionally respond.

        Only one evaluation runs per project at a time. If a previous
        evaluation is still in flight, this one is skipped.
        """
        if project_id in self._evaluating:
            logger.debug(f"Skipping evaluation for {project_id} — already in flight")
            return

        self._evaluating.add(project_id)
        try:
            await self._run_evaluation(project_id)
        except Exception as e:
            logger.warning(f"Evaluation failed for {project_id}: {e}")
        finally:
            self._evaluating.discard(project_id)

    async def _run_evaluation(self, project_id: str) -> None:
        """Core evaluation logic."""
        config = self.get_config(project_id)

        # Get services
        from services.ai_chat_context_service import get_ai_chat_context_service
        from services.ai_chat_prompt_service import get_ai_chat_prompt_service

        context_service = get_ai_chat_context_service()
        prompt_service = get_ai_chat_prompt_service()

        if not context_service or not prompt_service:
            logger.debug("Context or prompt service not available, skipping evaluation")
            return

        # Get project name
        project_name = await self._get_project_name(project_id)

        # Build system prompt
        summary = await context_service.get_summary(project_id)
        active_goals = await self._get_active_goals(project_id)

        system_prompt = prompt_service.build_system_prompt(
            project_name=project_name,
            config=config,
            context_summary=summary.summary_text or None,
            active_goals=active_goals,
        )

        # Get recent messages for evaluation
        recent = await context_service.get_recent_messages(
            project_id,
            limit=config.context_window_messages,
        )

        if not recent:
            logger.debug(f"No recent messages for {project_id}, skipping evaluation")
            return

        # Build evaluation prompt
        eval_prompt = prompt_service.build_evaluation_prompt(
            messages=recent,
            context_summary=summary.summary_text or None,
        )

        # Call Haiku
        try:
            from services.claude_client import get_claude_client
            client = get_claude_client()

            response = await client.complete(
                prompt=eval_prompt,
                system=system_prompt,
                model=ClaudeModel.HAIKU_35.value,
                max_tokens=config.max_response_tokens,
                temperature=0.3,
            )

            evaluation = prompt_service.parse_evaluation_response(response.content)
        except Exception as e:
            logger.warning(f"AI evaluation failed for {project_id}: {e}")
            return

        # Act on the evaluation
        await self._handle_evaluation(project_id, evaluation)

    async def _handle_evaluation(
        self,
        project_id: str,
        evaluation: AgentEvaluation,
    ) -> None:
        """Handle an evaluation result — post response and/or flag action."""
        if not evaluation.should_respond and not evaluation.detected_action:
            logger.debug(
                f"AI agent staying silent for {project_id}: {evaluation.reasoning}"
            )
            return

        # Post response as assistant message
        if evaluation.should_respond and evaluation.response:
            try:
                from services.conversation_service import get_conversation_service
                conv_service = get_conversation_service()
                if conv_service:
                    await conv_service.add_message(
                        project_id=project_id,
                        user_id=AI_AGENT_USER_ID,
                        display_name=AI_AGENT_DISPLAY_NAME,
                        type="assistant",
                        content=evaluation.response,
                        metadata={
                            "confidence": evaluation.confidence,
                            "detected_action": evaluation.detected_action,
                        },
                    )
                    logger.info(
                        f"AI agent responded in {project_id} "
                        f"(confidence={evaluation.confidence:.2f})"
                    )
            except Exception as e:
                logger.error(f"Failed to post AI response for {project_id}: {e}")

        # Flag detected action for handoff to action detection (#248)
        if evaluation.detected_action:
            logger.info(
                f"AI agent detected action in {project_id}: "
                f"{evaluation.detected_action} — {evaluation.action_description}"
            )
            # Action handoff will be implemented in #248

    # =========================================================================
    # Summary Update (background)
    # =========================================================================

    async def _update_summary(self, project_id: str) -> None:
        """Generate an updated rolling summary for a project."""
        try:
            from services.ai_chat_context_service import get_ai_chat_context_service
            from services.claude_client import get_claude_client

            context_service = get_ai_chat_context_service()
            if not context_service:
                return

            summary = await context_service.get_summary(project_id)
            recent = await context_service.get_recent_messages(project_id, limit=20)

            if not recent:
                return

            prompt = context_service.build_summary_prompt(
                previous_summary=summary.summary_text or None,
                new_messages=recent,
            )

            client = get_claude_client()
            response = await client.complete(
                prompt=prompt,
                system="You are a concise conversation summarizer. Output only the summary text.",
                model=ClaudeModel.HAIKU_35.value,
                max_tokens=600,
                temperature=0.0,
            )

            new_summary_text = response.content.strip()

            # Extract topic tags
            topic_tags = None
            try:
                topic_prompt = context_service.build_topic_extraction_prompt(new_summary_text)
                tag_response = await client.complete(
                    prompt=topic_prompt,
                    system="Output a JSON array of strings only.",
                    model=ClaudeModel.HAIKU_35.value,
                    max_tokens=100,
                    temperature=0.0,
                )
                import json
                topic_tags = json.loads(tag_response.content.strip())
                if not isinstance(topic_tags, list):
                    topic_tags = None
            except Exception:
                pass  # Topic extraction is best-effort

            await context_service.update_summary(
                project_id=project_id,
                new_summary_text=new_summary_text,
                topic_tags=topic_tags,
                messages_included=len(recent),
            )
        except Exception as e:
            logger.warning(f"Failed to update summary for {project_id}: {e}")

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_project_name(self, project_id: str) -> str:
        """Get the project name, falling back to ID."""
        try:
            from services.project_service import get_project_service
            project_service = get_project_service()
            if project_service:
                project = await project_service.get_project(project_id)
                if project:
                    return project.name
        except Exception:
            pass
        return project_id

    async def _get_active_goals(self, project_id: str) -> list:
        """Get active goal titles for a project."""
        try:
            from services.goal_service import get_goal_service
            goal_service = get_goal_service()
            if goal_service:
                goals = await goal_service.list_goals(
                    project_id=project_id,
                    status="active",
                )
                return [g.title for g in goals.items[:10]]
        except Exception:
            pass
        return []


# =============================================================================
# Module-level singleton
# =============================================================================

_ai_chat_agent_service: Optional[AIChatAgentService] = None


def get_ai_chat_agent_service() -> Optional[AIChatAgentService]:
    """Get the global AI chat agent service instance."""
    return _ai_chat_agent_service


def set_ai_chat_agent_service(service: Optional[AIChatAgentService]) -> None:
    """Set the global AI chat agent service instance."""
    global _ai_chat_agent_service
    _ai_chat_agent_service = service
