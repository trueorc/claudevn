"""Unified Directive Service — single entry point for all user intents.

Accepts natural language input, classifies it as new_work / priority_shift /
combined / clarification / conversation, and routes to the appropriate handler.

Intent classification:
1. Attempt via compute instance (SSE dispatch, same pattern as GoalDecomposerService)
2. Fallback to deterministic pattern matching (DirectiveService._detect_directive_intent)

References:
- Issue #613: Unified Directives Backend
- Issue #604: Evaluation callback wiring
- Issue #607: Directive doubling fix (in directive_service.py)
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models.unified_directive import (
    DirectiveComment,
    DirectiveIntent,
    DirectiveLifecycleStatus,
    DirectiveOutcome,
    UnifiedDirective,
)

logger = logging.getLogger(__name__)

# Timeout for intent classification via compute (seconds)
CLASSIFICATION_TIMEOUT = 30

# Polling interval for checking classification result
CLASSIFICATION_POLL_INTERVAL = 1

# Keywords that suggest new work creation
NEW_WORK_KEYWORDS = [
    "create", "build", "implement", "add", "develop", "design",
    "write", "make", "set up", "scaffold", "generate", "introduce",
    "need", "want", "should have", "must have", "let's",
]

# Keywords that suggest priority/profile shift
PRIORITY_SHIFT_KEYWORDS = [
    "accelerate", "speed up", "fast-track", "rush", "expedite",
    "deprioritize", "defer", "delay", "park", "shelve", "pause",
    "focus", "concentrate", "prioritize", "emphasize",
    "unblock", "clear", "resolve blockers",
    "balance", "normalize", "rebalance",
    "slow down", "back-burner",
]


# Maximum length for auto-generated goal titles
_TITLE_MAX_LENGTH = 80


def _generate_goal_title(text: str) -> str:
    """Generate a concise goal title from directive text.

    Extracts the first sentence and truncates at a word boundary if needed.
    Falls back to word-boundary truncation when no sentence ending is found.
    """
    text = text.strip()
    if len(text) <= _TITLE_MAX_LENGTH:
        return text

    # Try to extract the first sentence (end at . ! or ?)
    match = re.match(r"^(.+?[.!?])\s", text)
    if match and len(match.group(1)) <= _TITLE_MAX_LENGTH:
        return match.group(1)

    # Truncate at a word boundary
    truncated = text[:_TITLE_MAX_LENGTH]
    last_space = truncated.rfind(" ")
    if last_space > _TITLE_MAX_LENGTH // 2:
        truncated = truncated[:last_space]
    return truncated


class UnifiedDirectiveService:
    """Service for processing unified user directives.

    Provides:
    - Natural language submission and intent classification
    - Routing to GoalService (new_work) or DirectiveService (priority_shift)
    - Comment threads on directives
    - Redis-backed persistence
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._directives: Dict[str, Dict[str, UnifiedDirective]] = {}  # project_id -> {directive_id -> directive}

    def _key(self, key: str) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}unified_directive:{key}"

    # =========================================================================
    # Submit
    # =========================================================================

    async def submit(
        self,
        project_id: str,
        text: str,
        parent_directive_id: Optional[str] = None,
    ) -> UnifiedDirective:
        """Submit a new unified directive.

        Creates the directive, classifies intent, and begins processing.

        Args:
            project_id: Target project.
            text: Natural language input.
            parent_directive_id: If this is a follow-up on an existing directive.

        Returns:
            The created UnifiedDirective (processing may continue in background).
        """
        directive_id = f"udir_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Handle conversation follow-ups
        if parent_directive_id:
            return await self._handle_conversation(
                directive_id=directive_id,
                project_id=project_id,
                text=text,
                parent_directive_id=parent_directive_id,
            )

        directive = UnifiedDirective(
            directive_id=directive_id,
            project_id=project_id,
            text=text,
            lifecycle_status=DirectiveLifecycleStatus.RECEIVED,
            created_at=now,
            updated_at=now,
        )

        # Store
        self._store(directive)
        await self._save_directive_to_redis(directive)
        await self._append_to_history(directive)

        # Classify intent
        intent = await self._classify_intent(directive)
        directive.intent = intent
        directive.lifecycle_status = DirectiveLifecycleStatus.CLASSIFIED
        directive.updated_at = datetime.now(timezone.utc)
        await self._save_directive_to_redis(directive)

        # Route to handler
        await self._route(directive)

        return directive

    # =========================================================================
    # Comments
    # =========================================================================

    async def add_comment(
        self,
        project_id: str,
        directive_id: str,
        content: str,
        created_by: str = "user",
    ) -> UnifiedDirective:
        """Add a comment to an existing directive.

        Args:
            project_id: Project ID.
            directive_id: Directive to comment on.
            content: Comment text.
            created_by: Who created the comment.

        Returns:
            Updated directive with comment appended.

        Raises:
            ValueError: If directive not found.
        """
        directive = self._get(project_id, directive_id)
        if not directive:
            raise ValueError(f"Directive {directive_id} not found")

        comment = DirectiveComment(
            comment_id=f"cmt_{uuid.uuid4().hex[:12]}",
            directive_id=directive_id,
            content=content,
            created_by=created_by,
        )
        directive.comments.append(comment)
        directive.updated_at = datetime.now(timezone.utc)

        await self._save_directive_to_redis(directive)

        logger.info(f"Added comment to directive {directive_id}")
        return directive

    # =========================================================================
    # Queries
    # =========================================================================

    async def get_directive(
        self,
        project_id: str,
        directive_id: str,
    ) -> Optional[UnifiedDirective]:
        """Get a specific unified directive by ID."""
        return self._get(project_id, directive_id)

    async def list_directives(
        self,
        project_id: str,
        limit: int = 50,
    ) -> List[UnifiedDirective]:
        """List unified directives for a project (most recent first).

        Args:
            project_id: Project to list directives for.
            limit: Maximum results.

        Returns:
            List of UnifiedDirective, most recent first.
        """
        # Try Redis first
        directives = await self._load_history_from_redis(project_id, limit)
        if directives:
            return directives

        # Fallback to in-memory
        project_directives = self._directives.get(project_id, {})
        sorted_directives = sorted(
            project_directives.values(),
            key=lambda d: d.created_at,
            reverse=True,
        )
        return sorted_directives[:limit]

    # =========================================================================
    # Intent Classification
    # =========================================================================

    async def _classify_intent(self, directive: UnifiedDirective) -> DirectiveIntent:
        """Classify the intent of a directive.

        Attempts compute-based classification first, falls back to
        deterministic pattern matching.

        Args:
            directive: The directive to classify.

        Returns:
            Classified DirectiveIntent.
        """
        directive.lifecycle_status = DirectiveLifecycleStatus.CLASSIFYING
        directive.updated_at = datetime.now(timezone.utc)
        await self._save_directive_to_redis(directive)

        # Try compute-based classification
        try:
            intent = await self._classify_via_compute(directive)
            if intent:
                return intent
        except Exception as e:
            logger.debug(f"Compute classification unavailable: {e}")

        # Fallback: deterministic pattern matching
        return self._classify_deterministic(directive.text)

    async def _classify_via_compute(
        self,
        directive: UnifiedDirective,
    ) -> Optional[DirectiveIntent]:
        """Attempt intent classification via a compute instance.

        Follows the GoalDecomposerService pattern: send task via SSE to an
        idle compute, poll Redis for result.

        Returns:
            DirectiveIntent if compute classification succeeds, None otherwise.
        """
        try:
            from services.sse_connection_manager import get_sse_connection_manager
            sse_manager = get_sse_connection_manager()
            if not sse_manager:
                return None

            idle_connections = sse_manager.get_idle_connections()
            if not idle_connections:
                logger.debug("No idle compute connections for classification")
                return None

            # Pick first idle connection
            compute_id = idle_connections[0]

            # Build classification task
            task_data = {
                "type": "intent_classification",
                "directive_id": directive.directive_id,
                "text": directive.text,
                "instructions": (
                    "Classify this user directive into exactly one of: "
                    "new_work, priority_shift, combined, clarification. "
                    "Respond with ONLY the classification value."
                ),
            }

            # Send via SSE
            await sse_manager.send_event(
                compute_id=compute_id,
                event_type="task",
                data=task_data,
            )

            # Poll for result in Redis
            result_key = self._key(f"classification:{directive.directive_id}")
            result = await self._poll_for_result(result_key, CLASSIFICATION_TIMEOUT)

            if result:
                intent_str = result.strip().lower().replace('"', '').replace("'", "")
                try:
                    return DirectiveIntent(intent_str)
                except ValueError:
                    logger.warning(f"Unknown intent from compute: {intent_str}")

        except Exception as e:
            logger.debug(f"Compute-based classification failed: {e}")

        return None

    async def _poll_for_result(
        self,
        redis_key: str,
        timeout: int,
    ) -> Optional[str]:
        """Poll a Redis key for a result string.

        Args:
            redis_key: Key to poll.
            timeout: Max seconds to wait.

        Returns:
            Result string or None if timed out.
        """
        if not self._redis:
            return None

        elapsed = 0
        while elapsed < timeout:
            try:
                result = await self._redis._redis.get(redis_key)
                if result:
                    val = result.decode() if isinstance(result, bytes) else result
                    # Clean up
                    await self._redis._redis.delete(redis_key)
                    return val
            except Exception:
                pass

            await asyncio.sleep(CLASSIFICATION_POLL_INTERVAL)
            elapsed += CLASSIFICATION_POLL_INTERVAL

        return None

    def _classify_deterministic(self, text: str) -> DirectiveIntent:
        """Classify intent using deterministic keyword matching.

        Reuses the pattern-matching approach from DirectiveService as a
        fallback when no compute is available.

        Args:
            text: User directive text.

        Returns:
            DirectiveIntent based on keyword analysis.
        """
        text_lower = text.lower()

        new_work_score = sum(1 for kw in NEW_WORK_KEYWORDS if kw in text_lower)
        shift_score = sum(1 for kw in PRIORITY_SHIFT_KEYWORDS if kw in text_lower)

        if new_work_score > 0 and shift_score > 0:
            return DirectiveIntent.COMBINED
        elif shift_score > new_work_score:
            return DirectiveIntent.PRIORITY_SHIFT
        elif new_work_score > 0:
            return DirectiveIntent.NEW_WORK
        else:
            # Default: treat ambiguous text as new work
            return DirectiveIntent.NEW_WORK

    # =========================================================================
    # Routing
    # =========================================================================

    async def _route(self, directive: UnifiedDirective) -> None:
        """Route a classified directive to the appropriate handler.

        Args:
            directive: Classified directive to route.
        """
        directive.lifecycle_status = DirectiveLifecycleStatus.PROCESSING
        directive.updated_at = datetime.now(timezone.utc)
        await self._save_directive_to_redis(directive)

        try:
            if directive.intent == DirectiveIntent.NEW_WORK:
                await self._handle_new_work(directive)
            elif directive.intent == DirectiveIntent.PRIORITY_SHIFT:
                await self._handle_priority_shift(directive)
            elif directive.intent == DirectiveIntent.COMBINED:
                await self._handle_combined(directive)
            elif directive.intent == DirectiveIntent.CLARIFICATION:
                await self._handle_clarification(directive)
            else:
                await self._handle_new_work(directive)

            # Preserve handler-set terminal statuses (e.g. NEEDS_CLARIFICATION)
            if directive.lifecycle_status == DirectiveLifecycleStatus.PROCESSING:
                directive.lifecycle_status = DirectiveLifecycleStatus.COMPLETE
        except Exception as e:
            logger.error(f"Failed to process directive {directive.directive_id}: {e}")
            directive.lifecycle_status = DirectiveLifecycleStatus.FAILED
            if not directive.outcome:
                directive.outcome = DirectiveOutcome()

        directive.updated_at = datetime.now(timezone.utc)
        await self._save_directive_to_redis(directive)

    async def _handle_new_work(self, directive: UnifiedDirective) -> None:
        """Handle a new_work directive by creating a goal and triggering decomposition."""
        try:
            from models.work_map import (
                GoalCreateRequest, GoalIntentType, IntentSignal,
            )
            from services.goal_service import get_goal_service

            goal_service = get_goal_service()

            # Deduplication: check if a goal with matching description already
            # exists for this project (guards against double submissions).
            existing = await goal_service.list_goals(project_id=directive.project_id)
            for existing_goal in existing.items:
                if existing_goal.description == directive.text:
                    logger.info(
                        f"Directive {directive.directive_id} matches existing goal "
                        f"{existing_goal.goal_id} — reusing instead of creating duplicate"
                    )
                    directive.outcome = DirectiveOutcome(
                        goal_id_created=existing_goal.goal_id,
                    )
                    return

            request = GoalCreateRequest(
                title=_generate_goal_title(directive.text),
                description=directive.text,
                project_id=directive.project_id,
            )
            goal = await goal_service.create_goal(request)

            # Propagate directive_id to goal for lineage tracing (#122)
            goal.directive_id = directive.directive_id
            await goal_service._save_goal_to_redis(goal)

            # Set outcome immediately so it's available even if
            # subsequent intent mapping fails (prevents frontend
            # fallback from creating a duplicate goal).
            directive.outcome = DirectiveOutcome(
                goal_id_created=goal.goal_id,
            )

            # Map directive intent to goal intent fields (best-effort)
            try:
                intent_type = self._map_directive_to_goal_intent(directive.intent)
                if intent_type:
                    signal = IntentSignal(
                        intent_type=intent_type,
                        strength=0.8,
                        detected_from="directive",
                        source_id=directive.directive_id,
                    )
                    goal.intent_signals = [signal]
                    goal.primary_intent = intent_type
                    goal.intent_strength = signal.strength
                    await goal_service._save_goal_to_redis(goal)
            except Exception as e:
                logger.warning(
                    f"Intent mapping failed for directive {directive.directive_id}: {e}"
                )

            # Generate AI summary in background (fire-and-forget, #70)
            self._schedule_summary_generation(goal.goal_id, directive.text)

            # Trigger auto-process in background (fire-and-forget).
            # Pass directive info so the outcome can be updated with
            # issue IDs once decomposition completes (#714).
            self._schedule_auto_process(
                goal.goal_id,
                directive_id=directive.directive_id,
                project_id=directive.project_id,
            )

            logger.info(
                f"Directive {directive.directive_id} -> created goal {goal.goal_id}"
            )
        except Exception as e:
            logger.error(f"Failed to create goal for directive {directive.directive_id}: {e}")
            raise

    async def _handle_priority_shift(self, directive: UnifiedDirective) -> None:
        """Handle a priority_shift directive via the existing DirectiveService."""
        try:
            from services.directive_service import get_directive_service

            directive_service = get_directive_service()

            # Interpret the directive (generates weight/policy adjustments)
            old_directive = await directive_service.interpret(
                project_id=directive.project_id,
                text=directive.text,
            )

            # Store interpretation on the unified directive
            directive.interpretation = old_directive.interpretation

            # Auto-apply (unified flow skips manual approval)
            applied = await directive_service.apply(
                project_id=directive.project_id,
                directive_id=old_directive.directive_id,
            )

            directive.outcome = DirectiveOutcome(
                profile_changes_applied=True,
                profile_version_before=applied.profile_version_before,
                profile_version_after=applied.profile_version_after,
            )

            logger.info(
                f"Directive {directive.directive_id} -> applied priority shift "
                f"(profile v{applied.profile_version_before} -> v{applied.profile_version_after})"
            )
        except Exception as e:
            logger.error(
                f"Failed priority shift for directive {directive.directive_id}: {e}"
            )
            raise

    async def _handle_combined(self, directive: UnifiedDirective) -> None:
        """Handle a combined directive — both new work and priority shift."""
        outcome = DirectiveOutcome()

        # Priority shift first
        try:
            from services.directive_service import get_directive_service

            directive_service = get_directive_service()
            old_directive = await directive_service.interpret(
                project_id=directive.project_id,
                text=directive.text,
            )
            directive.interpretation = old_directive.interpretation
            applied = await directive_service.apply(
                project_id=directive.project_id,
                directive_id=old_directive.directive_id,
            )
            outcome.profile_changes_applied = True
            outcome.profile_version_before = applied.profile_version_before
            outcome.profile_version_after = applied.profile_version_after
        except Exception as e:
            logger.warning(f"Priority shift portion failed for {directive.directive_id}: {e}")

        # Then new work
        try:
            from models.work_map import GoalCreateRequest, GoalIntentType, IntentSignal
            from services.goal_service import get_goal_service

            goal_service = get_goal_service()

            # Deduplication: reuse existing goal with matching description
            existing = await goal_service.list_goals(project_id=directive.project_id)
            reused = False
            for existing_goal in existing.items:
                if existing_goal.description == directive.text:
                    logger.info(
                        f"Directive {directive.directive_id} matches existing goal "
                        f"{existing_goal.goal_id} — reusing (combined)"
                    )
                    outcome.goal_id_created = existing_goal.goal_id
                    reused = True
                    break

            if not reused:
                request = GoalCreateRequest(
                    title=_generate_goal_title(directive.text),
                    description=directive.text,
                    project_id=directive.project_id,
                )
                goal = await goal_service.create_goal(request)
                outcome.goal_id_created = goal.goal_id

                # Propagate directive_id to goal for lineage tracing (#122)
                goal.directive_id = directive.directive_id
                await goal_service._save_goal_to_redis(goal)

                # Map directive intent to goal intent fields (best-effort)
                try:
                    intent_type = self._map_directive_to_goal_intent(directive.intent)
                    if intent_type:
                        signal = IntentSignal(
                            intent_type=intent_type,
                            strength=0.8,
                            detected_from="directive",
                            source_id=directive.directive_id,
                        )
                        goal.intent_signals = [signal]
                        goal.primary_intent = intent_type
                        goal.intent_strength = signal.strength
                        await goal_service._save_goal_to_redis(goal)
                except Exception as e:
                    logger.warning(
                        f"Intent mapping failed for combined directive "
                        f"{directive.directive_id}: {e}"
                    )

                # Generate AI summary in background (fire-and-forget, #70)
                self._schedule_summary_generation(goal.goal_id, directive.text)

                # Trigger auto-process in background (fire-and-forget)
                self._schedule_auto_process(
                    goal.goal_id,
                    directive_id=directive.directive_id,
                    project_id=directive.project_id,
                )
        except Exception as e:
            logger.warning(f"New work portion failed for {directive.directive_id}: {e}")

        directive.outcome = outcome

        if not outcome.goal_id_created and not outcome.profile_changes_applied:
            raise RuntimeError("Both new work and priority shift failed")

    async def _handle_clarification(self, directive: UnifiedDirective) -> None:
        """Handle a clarification request — the AI couldn't classify."""
        directive.lifecycle_status = DirectiveLifecycleStatus.NEEDS_CLARIFICATION
        directive.outcome = DirectiveOutcome(
            clarification_question=(
                "I'm not sure what you'd like to do. Could you clarify whether "
                "you want to create new work items, adjust priorities, or both?"
            ),
        )

    async def _handle_conversation(
        self,
        directive_id: str,
        project_id: str,
        text: str,
        parent_directive_id: str,
    ) -> UnifiedDirective:
        """Handle a conversation follow-up on an existing directive."""
        now = datetime.now(timezone.utc)

        directive = UnifiedDirective(
            directive_id=directive_id,
            project_id=project_id,
            text=text,
            intent=DirectiveIntent.CONVERSATION,
            lifecycle_status=DirectiveLifecycleStatus.COMPLETE,
            parent_directive_id=parent_directive_id,
            created_at=now,
            updated_at=now,
        )

        # Also add as a comment on the parent
        parent = self._get(project_id, parent_directive_id)
        if parent:
            comment = DirectiveComment(
                comment_id=f"cmt_{uuid.uuid4().hex[:12]}",
                directive_id=parent_directive_id,
                content=text,
                created_by="user",
            )
            parent.comments.append(comment)
            parent.updated_at = now
            await self._save_directive_to_redis(parent)

        self._store(directive)
        await self._save_directive_to_redis(directive)
        await self._append_to_history(directive)

        return directive

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _schedule_summary_generation(self, goal_id: str, text: str) -> None:
        """Schedule AI summary generation for a goal as a background task.

        Uses the cheapest model (Haiku) to generate a one-line summary
        of the directive text for display in the history panel (#70).
        """
        asyncio.create_task(self._generate_summary(goal_id, text))

    async def _generate_summary(self, goal_id: str, text: str) -> None:
        """Generate a one-line AI summary for a goal and persist it.

        Uses Claude Haiku for minimal cost and latency. Falls back to
        truncation if the API call fails (the frontend also has a
        truncation fallback, so this is belt-and-suspenders).
        """
        try:
            from models.claude_client import ClaudeModel
            from services.claude_client import get_claude_client

            client = get_claude_client()
            response = await client.complete(
                prompt=(
                    f"Summarize this user directive in one short sentence "
                    f"(max 60 characters). Output ONLY the summary, no quotes "
                    f"or punctuation wrapping:\n\n{text}"
                ),
                system="You are a concise summarizer. Output only the summary text.",
                model=ClaudeModel.HAIKU_35.value,
                max_tokens=80,
                temperature=0.0,
            )

            summary = response.content.strip().strip('"\'')
            # Enforce length limit
            if len(summary) > 80:
                summary = summary[:77] + "..."

            # Save to goal
            from services.goal_service import get_goal_service

            goal_service = get_goal_service()
            goal = await goal_service.get_goal(goal_id)
            if goal:
                goal.summary = summary
                goal.updated_at = datetime.now(timezone.utc)
                await goal_service._save_goal_to_redis(goal)
                logger.info(f"Generated summary for goal {goal_id}: {summary}")

        except Exception as e:
            logger.warning(f"Failed to generate summary for goal {goal_id}: {e}")

    def _schedule_auto_process(
        self,
        goal_id: str,
        directive_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Schedule auto-process for a newly created goal as a background task.

        Uses asyncio.create_task to fire-and-forget, same pattern as the
        auto-process API endpoint. Errors are logged but do not propagate
        to the caller — the directive still completes successfully.

        If directive_id/project_id are provided, the directive outcome will
        be updated with created issue IDs once decomposition finishes (#714).
        """
        asyncio.create_task(
            self._run_auto_process(goal_id, directive_id, project_id)
        )

    async def _run_auto_process(
        self,
        goal_id: str,
        directive_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Run auto-process for a goal. Wraps the API background function.

        After successful completion, updates the originating directive's
        outcome with the created issue IDs (if directive info provided).
        """
        try:
            from api.slim_claude_code import (
                _auto_process_background,
                _set_processing_status,
                ProcessingStage,
            )

            await _set_processing_status(goal_id, ProcessingStage.QUEUED)
            await _auto_process_background(goal_id, constraints=None)

            # Update the directive outcome with created issue IDs (#714)
            if directive_id and project_id:
                await self._backfill_directive_issue_ids(
                    directive_id, project_id, goal_id
                )
        except Exception as e:
            logger.error(f"Auto-process failed for goal {goal_id}: {e}")

    async def _backfill_directive_issue_ids(
        self,
        directive_id: str,
        project_id: str,
        goal_id: str,
    ) -> None:
        """Update a directive's outcome with issue IDs from goal decomposition.

        Called after auto-process completes successfully. Reads the goal's
        issue_ids and patches the directive outcome.
        """
        try:
            from services.goal_service import get_goal_service

            goal_service = get_goal_service()
            goal = await goal_service.get_goal(goal_id)
            if not goal or not goal.issue_ids:
                return

            directive = self._get(project_id, directive_id)
            if not directive or not directive.outcome:
                return

            directive.outcome.issue_ids_created = list(goal.issue_ids)
            directive.updated_at = datetime.now(timezone.utc)
            await self._save_directive_to_redis(directive)

            logger.info(
                f"Backfilled directive {directive_id} outcome with "
                f"{len(goal.issue_ids)} issue IDs from goal {goal_id}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to backfill directive {directive_id} with "
                f"issue IDs from goal {goal_id}: {e}"
            )

    @staticmethod
    def _map_directive_to_goal_intent(intent: DirectiveIntent):
        """Map a directive intent to a GoalIntentType.

        Returns None for intents that don't map to a goal intent
        (e.g., clarification, conversation).
        """
        from models.work_map import GoalIntentType

        mapping = {
            DirectiveIntent.NEW_WORK: GoalIntentType.EXPANSION,
            DirectiveIntent.PRIORITY_SHIFT: GoalIntentType.TARGETED_INVESTMENT,
            DirectiveIntent.COMBINED: GoalIntentType.EXPANSION,
        }
        return mapping.get(intent)

    def _store(self, directive: UnifiedDirective) -> None:
        """Store directive in memory."""
        if directive.project_id not in self._directives:
            self._directives[directive.project_id] = {}
        self._directives[directive.project_id][directive.directive_id] = directive

    def _get(
        self,
        project_id: str,
        directive_id: str,
    ) -> Optional[UnifiedDirective]:
        """Get a directive from in-memory store."""
        return self._directives.get(project_id, {}).get(directive_id)

    # =========================================================================
    # Redis Persistence
    # =========================================================================

    async def delete_project_directives(self, project_id: str) -> int:
        """Delete all directives for a project from both memory and Redis.

        Removes:
        - All item keys matching claudevn:unified_directive:item:{project_id}:*
        - The history list key claudevn:unified_directive:history:{project_id}

        Returns:
            Number of directive item keys deleted
        """
        deleted = 0

        # Clear in-memory cache for this project
        to_remove = [
            key for key in self._directives
            if key.startswith(f"{project_id}:")
        ]
        for key in to_remove:
            del self._directives[key]
            deleted += 1

        # Clean Redis
        if self._redis:
            try:
                # Scan and delete item keys
                pattern = self._key(f"item:{project_id}:*")
                cursor = 0
                while True:
                    cursor, keys = await self._redis._redis.scan(
                        cursor, match=pattern, count=100
                    )
                    if keys:
                        await self._redis._redis.delete(*keys)
                        deleted += len(keys)
                    if cursor == 0:
                        break

                # Delete history list
                history_key = self._key(f"history:{project_id}")
                await self._redis._redis.delete(history_key)
            except Exception as e:
                logger.error(f"Error deleting directives for project {project_id}: {e}")

        logger.info(f"Deleted {deleted} directives for project {project_id}")
        return deleted

    async def _save_directive_to_redis(self, directive: UnifiedDirective) -> None:
        """Save a unified directive to Redis (individual key only)."""
        if not self._redis:
            return

        try:
            key = self._key(f"item:{directive.project_id}:{directive.directive_id}")
            data = directive.model_dump_json()
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Error saving unified directive to Redis: {e}")

    async def _append_to_history(self, directive: UnifiedDirective) -> None:
        """Append a directive ID to the project history list (called once on creation).

        Only stores the directive_id — current state is always read from
        the individual item key to avoid stale snapshots.
        """
        if not self._redis:
            return

        try:
            history_key = self._key(f"history:{directive.project_id}")
            await self._redis._redis.lpush(history_key, directive.directive_id)
            await self._redis._redis.ltrim(history_key, 0, 99)
        except Exception as e:
            logger.error(f"Error appending unified directive to history: {e}")

    async def _load_history_from_redis(
        self,
        project_id: str,
        limit: int = 50,
    ) -> List[UnifiedDirective]:
        """Load unified directive history from Redis.

        The history list stores only directive IDs (most recent first).
        Current state is fetched from individual item keys so the list
        endpoint always returns up-to-date data.
        """
        if not self._redis:
            return []

        try:
            history_key = self._key(f"history:{project_id}")
            raw_ids = await self._redis._redis.lrange(history_key, 0, limit - 1)

            directives = []
            for raw in raw_ids:
                directive_id = raw.decode() if isinstance(raw, bytes) else raw

                # Fetch current state from individual item key
                item_key = self._key(f"item:{project_id}:{directive_id}")
                item_data = await self._redis._redis.get(item_key)
                if item_data:
                    data = item_data.decode() if isinstance(item_data, bytes) else item_data
                    directives.append(UnifiedDirective(**json.loads(data)))

            return directives
        except Exception as e:
            logger.error(f"Error loading unified directive history: {e}")
            return []


# =============================================================================
# Global Instance
# =============================================================================


_unified_directive_service: Optional[UnifiedDirectiveService] = None


def get_unified_directive_service() -> UnifiedDirectiveService:
    """Get the global unified directive service instance."""
    if _unified_directive_service is None:
        raise RuntimeError("Unified directive service not initialized")
    return _unified_directive_service


def set_unified_directive_service(service: Optional[UnifiedDirectiveService]) -> None:
    """Set the global unified directive service instance."""
    global _unified_directive_service
    _unified_directive_service = service
